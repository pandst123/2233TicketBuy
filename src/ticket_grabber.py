"""
抢票核心逻辑模块
参考biliTickerBuy和BHYG的高级抢票策略

核心策略：
1. 持续打请求直到成功
2. 429/-412时降速，只检测票量不打订单
3. 不同错误码不同处理
4. 智能间隔调整
"""

import time
import threading
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
from enum import Enum

from .config import Config
from .api_client import BilibiliAPI, create_api_client
from .gaia import GaiaVerifier, create_gaia_verifier
from .logger import logger


class GrabPhase(Enum):
    """抢票阶段"""
    WAITING = "waiting"          # 等待开售
    MONITORING = "monitoring"    # 监控票量（不打订单）
    GRABBING = "grabbing"        # 抢票中
    SUCCESS = "success"          # 成功
    FAILED = "failed"            # 失败


@dataclass
class TicketResult:
    """抢票结果"""
    success: bool
    order_id: Optional[str] = None
    message: str = ""
    timestamp: float = 0.0
    attempts: int = 0


class TicketGrabber:
    """抢票核心逻辑"""
    
    # 错误码
    ERROR_CODE_SUCCESS = 0
    ERROR_CODE_NOT_LOGIN = -101       # 未登录
    ERROR_CODE_RISK = -352            # 风控
    ERROR_CODE_NO_PERMISSION = -403   # 无权限
    ERROR_CODE_412 = -412             # 请求过于频繁
    ERROR_CODE_429 = 429              # 请求过于频繁
    ERROR_CODE_STOCK_NOT_ENOUGH = 10007  # 库存不足
    ERROR_CODE_ORDER_FAIL = 100009    # 订单创建失败
    ERROR_CODE_SOLD_OUT = 100001      # 售罄
    ERROR_CODE_NOT_START = 100002     # 未开售
    ERROR_CODE_LIMIT = 100003         # 超出限购
    ERROR_CODE_SYSTEM = 100004        # 系统繁忙
    
    def __init__(self, config: Config, viewers: list = None):
        """初始化抢票器"""
        self.config = config
        self.api = create_api_client(config)
        self.viewers = viewers or []
        self.phase = GrabPhase.WAITING
        self.result: Optional[TicketResult] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        
        # 从 viewers 提取购票人信息
        self.buyer_name = ""
        self.buyer_tel = ""
        if self.viewers:
            v = self.viewers[0]
            self.buyer_name = v.get("name", "")
            self.buyer_tel = v.get("tel", "")
        logger.info(f"购票人: {self.buyer_name}, 电话: {self.buyer_tel}")
        
        # 抢票参数
        self.grab_interval = 0.3      # 抢票间隔（秒，对齐 BHYG order_interval=0.3）
        self.monitor_interval = 1.0   # 监控间隔（秒）
        self.max_429_count = 5        # 最大429次数
        self._429_count = 0           # 当前429次数
        self._risk_cooldown = 60      # 风控冷却时间（秒）
        self._is_hot = getattr(config.event, 'hot_project', False)
        
        # 智能间隔（对齐 BHYG last_order_time / last_order_check_time）
        self.last_order_time = 0
        self.last_order_check_time = 0
        
        # Gaia 风控验证器
        self.gaia = GaiaVerifier(self.api.cookies)
        
        # Token 缓存（参考 BHYG get_token）
        self._cached_token = None
        self._cached_ptoken = None
        self._token_exp = 0
    
    def check_login(self) -> bool:
        """检查登录状态"""
        logger.info("检查登录状态...")
        if not self.api.check_login():
            logger.error("未登录或登录已过期")
            return False
        logger.info("登录状态正常")
        return True
    
    def get_project_info(self) -> Dict:
        """获取项目信息"""
        logger.info(f"获取项目信息: {self.config.event.project_id}")
        project = self.api.get_project_info(self.config.event.project_id)
        
        logger.info(f"项目名称: {project.name}")
        if project.sale_begin > 0:
            from datetime import datetime
            sale_time = datetime.fromtimestamp(project.sale_begin).strftime('%Y-%m-%d %H:%M:%S')
            logger.info(f"开售时间: {sale_time}")
        
        return {
            "id": project.id,
            "name": project.name,
            "sale_begin": project.sale_begin,
            "screens": project.screens,
        }
    
    def get_screen_info(self) -> Dict:
        """获取场次信息"""
        logger.info(f"获取场次信息: {self.config.event.screen_id}")
        screen = self.api.get_screen_info(
            self.config.event.project_id,
            self.config.event.screen_id,
        )
        
        logger.info(f"场次名称: {screen.name}")
        
        # 显示票档信息（带状态）
        logger.info("可用票档:")
        for sku in screen.skus:
            desc = sku.get("desc", "未知")
            price = sku.get("price", 0) / 100
            stock = sku.get("stock", None)
            count = -1
            if isinstance(stock, dict):
                count = stock.get("count", -1)
            elif isinstance(stock, (int, float)):
                count = int(stock)
            
            clickable = sku.get("clickable", None)
            sale_start = sku.get("sale_start", "")
            
            if clickable is False:
                if count == 0:
                    status = "已售罄"
                elif sale_start:
                    status = f"未开售({sale_start}开售)"
                else:
                    status = "未开售"
            elif clickable is True:
                if count == 0:
                    status = "已售罄"
                elif count > 0:
                    status = f"余{count}"
                else:
                    status = "可购买"
            else:
                if count == 0:
                    status = "已售罄"
                elif count > 0:
                    status = f"余{count}"
                else:
                    status = "未知"
            
            logger.info(f"  - {desc}: ¥{price} [{status}]")
        
        return {
            "id": screen.id,
            "name": screen.name,
            "skus": screen.skus,
        }
    
    def check_ticket_stock(self) -> bool:
        """
        检查票量（BHYG 风格：使用专用 stock/check API）
        
        Returns:
            是否有票
        """
        try:
            # BHYG 使用专门的库存检查 API
            url = "https://show.bilibili.com/api/ticket/stock/check"
            data = {
                "projectId": str(self.config.event.project_id),
                "skuId": self.config.event.sku_id,
                "screenId": self.config.event.screen_id,
            }
            headers = self.api._get_default_headers()
            headers["Content-Type"] = "application/json"
            
            client = self.api._get_client()
            response = client.post(url, json=data, headers=headers, cookies=self.api.cookies)
            result = response.json()
            
            code = result.get("code", result.get("errno", -1))
            if code != 0:
                logger.debug(f"stock/check 返回非0: {code}")
                return False
            
            # stockStatus: 1=TEMP_SOLD_OUT, 2=SOLD_OUT, 3=HAS_STOCK
            stock_status = result.get("data", {}).get("stockStatus", 0)
            return stock_status == 3
            
        except Exception as e:
            logger.debug(f"检查票量失败: {e}")
            # 回退：通过 get_screen_info 检查
            try:
                screen = self.api.get_screen_info(
                    self.config.event.project_id,
                    self.config.event.screen_id,
                )
                for sku in screen.skus:
                    if sku["id"] == self.config.event.sku_id:
                        stock = sku.get("stock", {})
                        count = stock.get("count", -1) if isinstance(stock, dict) else -1
                        return count > 0 or count == -1  # -1 表示未知，保守认为有票
                return False
            except:
                return False
    
    def wait_for_start(self, sale_begin: int) -> None:
        """
        等待开售时间
        
        Args:
            sale_begin: 开售时间戳（秒）
        """
        advance_ms = self.config.strategy.advance_ms
        advance_seconds = advance_ms / 1000
        target_time = sale_begin - advance_seconds
        
        logger.info("等待开售...")
        logger.info(f"开售时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(sale_begin))}")
        logger.info(f"提前开始: {advance_ms}ms")
        
        while True:
            current_time = time.time()
            remaining = target_time - current_time
            
            if remaining <= 0:
                logger.info("时间到！开始抢票...")
                break
            
            # 显示倒计时
            if remaining > 3600:
                hours = int(remaining // 3600)
                minutes = int((remaining % 3600) // 60)
                logger.info(f"倒计时: {hours}小时{minutes}分钟")
                time.sleep(30)
            elif remaining > 60:
                minutes = int(remaining // 60)
                seconds = int(remaining % 60)
                logger.info(f"倒计时: {minutes}分{seconds}秒")
                time.sleep(5)
            elif remaining > 10:
                logger.info(f"倒计时: {int(remaining)}秒")
                time.sleep(1)
            else:
                # 🔑 最后 10 秒：高频检查（对标 BHYG 忙等）
                time.sleep(0.1)
        
        # 🔑 BHYG 风格：prereq 预热连接
        try:
            import httpx
            client = self.api._get_client()
            prereq = client.head("https://show.bilibili.com")
            logger.debug(f"预热连接完成, CDN: {prereq.headers.get('X-Cache-Webcdn', '未知')}")
        except Exception as e:
            logger.debug(f"预热连接异常（可忽略）: {e}")
        
        # 🔑 精确忙等：最后 delta 秒内用 while True 忙等
        delta = 0.05
        while sale_begin - advance_seconds + delta > time.time():
            pass
        logger.info("时间到！开始抢票...")
    
    def _try_gaia_verify(self, result: dict) -> bool:
        """
        尝试 gaia 风控验证（BHYG handle_gaia）
        
        Args:
            result: create_order 返回的完整 result dict
        
        Returns:
            是否成功获取 grisk_id
        """
        if not self.gaia.check_risk_response(result):
            return False
        
        v_voucher = result.get("data", {}).get("v_voucher") if result.get("data") else None
        if not v_voucher:
            risk_params = result.get("data", {}).get("riskParams") if result.get("data") else None
            if risk_params and isinstance(risk_params, dict):
                v_voucher = risk_params.get("v_voucher")
        
        if not v_voucher:
            logger.warning("gaia 风控但无法提取 v_voucher")
            return False
        
        logger.info("触发 gaia 风控，开始验证流程...")
        
        # 使用已有的 GeetestHandler 处理验证码
        from .captcha import GeetestHandler
        try:
            handler = GeetestHandler(self.api.cookies)
            captcha_result = handler.handle_captcha(v_voucher)
            if captcha_result.get("success"):
                grisk_id = captcha_result.get("grisk_id", "")
                if grisk_id:
                    logger.info(f"gaia 验证成功, grisk_id: {grisk_id[:20] if grisk_id else '空'}...")
                    self.api.cookies["grisk_id"] = grisk_id
                    return True
                else:
                    logger.warning("gaia handle_captcha 成功但未获取到 grisk_id")
            else:
                logger.warning(f"gaia 验证未通过: {captcha_result.get('message', '未知')}")
        except Exception as e:
            logger.warning(f"gaia 验证流程异常: {e}")
        
        return False

    def _try_create_order(self) -> TicketResult:
        """尝试创建订单（单次）"""
        new_token = None
        new_ptoken = None
        
        # 🔑 检查 token 是否过期（对齐 BHYG get_token 的过期检查）
        if self._cached_token and time.time() > self._token_exp - 60:
            logger.info(f"Token 即将过期（已缓存 {int(time.time() - (self._token_exp - 300))}s），将重新获取")
            self._cached_token = None
            self._cached_ptoken = None
        
        try:
            result, new_token, new_ptoken = self.api.create_order(
                project_id=self.config.event.project_id,
                screen_id=self.config.event.screen_id,
                sku_id=self.config.event.sku_id,
                count=self.config.event.count,
                buyer_name=self.buyer_name,
                buyer_tel=self.buyer_tel,
                viewer_id=self.config.event.viewer_id if self.config.event.viewer_id else None,
                viewers=self.viewers,
                cached_token=self._cached_token or "",
                cached_ptoken=self._cached_ptoken or "",
                is_hot=self._is_hot,
            )
            
            errno = result.get("errno", result.get("code", -1))
            msg = result.get("msg", result.get("message", ""))
            
            if errno == self.ERROR_CODE_SUCCESS:
                order_id = result.get("data", {}).get("orderId") or result.get("data", {}).get("order_id")
                logger.success(f"订单创建成功！订单ID: {order_id}")
                # 🔑 生成支付二维码（对标 BHYG）
                _show_pay_qrcode(self.api, order_id, token)
                return TicketResult(
                    success=True,
                    order_id=order_id,
                    message="抢票成功",
                    timestamp=time.time(),
                )
            # 🔑 -352 gaia 风控：尝试自动验证
            elif errno == -352:
                logger.warning(f"触发 gaia 风控 (errno=-352): {msg}")
                if self._try_gaia_verify(result):
                    logger.info("gaia 验证成功，立即重试")
                    # 立即重试（不 sleep，递归调用消耗 cached token 直接重试）
                    self._cached_token = new_token  # 更新缓存
                    self._cached_ptoken = new_ptoken or ""
                    return TicketResult(
                        success=False,
                        message=f"gaia 验证通过, 需重试",
                        timestamp=time.time(),
                    )
                else:
                    logger.warning("gaia 验证未通过，等待冷却后重试")
                    time.sleep(self._risk_cooldown)
            else:
                # errno=1 "请慢一点" → 较长冷却（BHYG风格：5秒+退避）
                if errno == 1:
                    self.grab_interval = min(self.grab_interval * 1.5, 5.0)
                    logger.warning(f"被限速 (errno=1)，等待 5 秒后重试... (间隔调整至 {self.grab_interval:.1f}s)")
                    time.sleep(5)
                return TicketResult(
                    success=False,
                    message=f"errno={errno}: {msg}",
                    timestamp=time.time(),
                )
                
        except Exception as e:
            logger.warning(f"create_order 异常: {type(e).__name__}: {e}")
            return TicketResult(
                success=False,
                message=str(e),
                timestamp=time.time(),
            )
        finally:
            # 🔑 关键：无论成功、失败还是异常，都缓存 token
            # 避免下次重试时再次调用 prepare_token 被 B 站限速
            if new_token:
                self._cached_token = new_token
                self._cached_ptoken = new_ptoken or ""
                self._token_exp = time.time() + 300
                logger.info(f"Token 已缓存: {new_token[:20]}...")
    
    def _handle_grab_result(self, result: TicketResult) -> bool:
        """处理抢票结果（BHYG 错误码策略）"""
        if result.success:
            self.result = result
            self.phase = GrabPhase.SUCCESS
            return False
        
        message = result.message
        
        # 提取 errno 用于精确匹配
        errno = None
        if message.startswith("errno="):
            try:
                errno_str = message.split(":")[0].replace("errno=", "").strip()
                errno = int(errno_str)
            except (ValueError, IndexError):
                pass
        
        # 显示错误信息
        logger.warning(f"抢票失败: {message}")
        
        # === 致命错误（停止抢票） ===
        if errno == -101:
            logger.error("未登录，请先登录")
            return False
        # -401 有时是 gaia 风控（需要在 _try_create_order 中处理），这里作为后备
        if errno == -401:
            logger.warning("errno=-401，可能存在 gaia 风控，等待冷却")
            time.sleep(self._risk_cooldown)
            return True
        if errno == -403:
            logger.error("无权限访问")
            return False
        if errno == 100003:
            logger.error("超出限购数量")
            return False
        
        # === 限流/风控 ===
        if errno == 1:
            # "请慢一点" → 已在 _try_create_order 中等待5秒，这里再增加间隔
            self.grab_interval = min(self.grab_interval * 2, 5.0)
            return True
        
        if errno in (-412, 412, 429):
            self._429_count += 1
            self.last_order_time = time.time()
            logger.warning(f"触发限流 ({self._429_count}/{self.max_429_count})")
            if self._429_count >= self.max_429_count:
                logger.warning("限流次数过多，切换到监控模式（BHYG: 412累计20次等300秒）")
                self.phase = GrabPhase.MONITORING
                time.sleep(60)  # 等待60秒冷却
                return True
            self.grab_interval = min(self.grab_interval * 2, 5.0)
            logger.info(f"增加抢票间隔到 {self.grab_interval:.1f}秒")
            return True
        
        if errno == -352:
            logger.warning(f"触发 gaia 风控，等待{self._risk_cooldown}秒（BHYG: handle_gaia）")
            time.sleep(self._risk_cooldown)
            return True
        
        # === 库存相关（继续监控） ===
        if errno in (10007, 100001, 100009, 900001, 900002, 219):
            logger.debug(f"票务状态异常 (errno={errno})，继续监控...")
            return True
        
        # === 未开售 ===
        if errno == 100002:
            logger.debug("未开售，等待...")
            time.sleep(1)
            return True
        
        # === 系统繁忙/屏蔽 ===
        if errno in (100004, 3, 221):
            logger.debug(f"系统繁忙/屏蔽 (errno={errno})，短暂等待...")
            time.sleep(0.5)
            self.last_order_check_time = time.time()
            return True

        # === 验证码（BHYG: solve_captcha） ===
        if errno == 100044:
            logger.warning("触发验证码 (errno=100044)，需要手动处理")
            logger.info("请在B站App或网页完成验证后继续")
            time.sleep(10)
            self.last_order_check_time = time.time()
            return True
        
        # === pay_money 自动更新（BHYG: 100034） ===
        if errno == 100034:
            # 暂不处理，B站改价时会通知
            logger.warning("pay_money 不匹配，可能需要更新价格")
            self.last_order_check_time = time.time()
            return True
        
        # errno=1 "请慢一点" 已经在 _try_create_order 中处理了延迟
        # 如果走到这里说明是其他未知错误
        
        # === 回退到字符串匹配（兼容未提取到 errno 的情况） ===
        if errno is None:
            if "429" in message or "412" in message or "频繁" in message:
                self._429_count += 1
                if self._429_count >= self.max_429_count:
                    self.phase = GrabPhase.MONITORING
                    return True
                self.grab_interval = min(self.grab_interval * 2, 5.0)
                return True
            if "352" in message or "风控" in message:
                time.sleep(self._risk_cooldown)
                return True
            if "售罄" in message or "库存不足" in message or "10007" in message:
                return True
            if "未开售" in message:
                time.sleep(1)
                return True
            if "限购" in message:
                return False
        
        # 其他错误：默认继续重试
        logger.debug(f"未识别的错误，继续重试: {message}")
        return True
    
    def grab_ticket(self) -> TicketResult:
        """执行抢票（BHYG rush_mode 风格）"""
        self.phase = GrabPhase.GRABBING
        logger.info("开始抢票...")
        
        # 强制刷新 token（对齐 BHYG: token_exp = 0）
        self._cached_token = None
        self._cached_ptoken = None
        self._token_exp = 0
        
        attempt = 0
        stock_check_count = 0
        last_order_time = 0
        enable_stock_check = getattr(self.config.strategy, 'enable_stock_check', False)
        
        while not self._stop_event.is_set():
            attempt += 1
            
            # 可选：BHYG 模式库存检查（默认关闭，避免额外延迟）
            if enable_stock_check and stock_check_count == 0 and self._429_count < self.max_429_count:
                if not self.check_ticket_stock():
                    logger.debug(f"暂无库存，等待 {self.monitor_interval}s...")
                    time.sleep(self.monitor_interval)
                    continue
                else:
                    stock_check_count += 1
            
            if enable_stock_check:
                stock_check_count += 1
                if stock_check_count % 30 == 0:
                    stock_check_count = 0
            
            # 根据阶段选择策略
            if self.phase == GrabPhase.MONITORING:
                has_ticket = self.check_ticket_stock()
                if has_ticket:
                    logger.info("检测到有票，切回抢票模式")
                    self.phase = GrabPhase.GRABBING
                    self.grab_interval = 0.1
                    continue
                else:
                    time.sleep(self.monitor_interval)
                    continue
            
            # 抢票模式
            result = self._try_create_order()
            
            if result.success:
                self.result = result
                self.result.attempts = attempt
                self.phase = GrabPhase.SUCCESS
                logger.success(f"抢票成功！第{attempt}次尝试")
                return result
            
            # 处理失败结果
            should_continue = self._handle_grab_result(result)
            if not should_continue:
                break
            
            # 显示进度
            if attempt % 30 == 0:
                buyers = self.buyer_name or "未设置"
                logger.info(f"持续抢票中... 第{attempt}次, 购票人: {buyers}")
            
            # 智能等待间隔（参考 BHYG 三重判断）
            # 三重条件：last_order 后 > 5s、last_check 后 > 1s、默认间隔
            now = time.time()
            if (self.last_order_time + 5 - 0.05) - now > 0:
                sleep_time = (self.last_order_time + 5 - 0.05) - now
            elif (self.last_order_check_time + 1 - 0.05) - now > 0:
                sleep_time = (self.last_order_check_time + 1 - 0.05) - now
            else:
                sleep_time = self.grab_interval
            time.sleep(sleep_time)
        
        return TicketResult(
            success=False,
            message="已停止抢票",
            timestamp=time.time(),
            attempts=attempt,
        )
    
    def run(self) -> TicketResult:
        """
        运行完整的抢票流程
        """
        logger.info("-" * 50)
        logger.info("  2233TicketBuy - B站抢票工具")
        logger.info("-" * 50)
        
        # 1. 检查登录
        if not self.check_login():
            return TicketResult(success=False, message="未登录")
        
        # 2. 获取项目信息
        try:
            project_info = self.get_project_info()
        except Exception as e:
            return TicketResult(success=False, message=f"获取项目信息失败: {e}")
        
        # 3. 获取场次信息
        try:
            screen_info = self.get_screen_info()
        except Exception as e:
            return TicketResult(success=False, message=f"获取场次信息失败: {e}")
        
        # 4. 等待开售
        sale_begin = project_info.get("sale_begin", 0)
        now = time.time()
        
        if sale_begin > 0 and now < sale_begin:
            self.wait_for_start(sale_begin)
        else:
            logger.info("已开售，立即开始抢票")
        
        # 5. 执行抢票
        result = self.grab_ticket()
        
        # 6. 显示结果
        logger.info("-" * 50)
        if result.success:
            logger.success("抢票成功！")
            logger.info(f"订单ID: {result.order_id}")
            logger.info(f"尝试次数: {result.attempts}")
            logger.info("请尽快完成支付！")
        else:
            logger.fail("抢票失败")
            logger.info(f"原因: {result.message}")
        logger.info("-" * 50)
        
        return result
    
    def stop(self) -> None:
        """停止抢票"""
        self._stop_event.set()
        self.phase = GrabPhase.FAILED


def _show_pay_qrcode(api, order_id: str, order_token: str):
    """显示支付二维码（对标 BHYG）"""
    try:
        import qrcode
        project_id = api.config.event.project_id
        url = f"https://show.bilibili.com/api/ticket/order/createstatus?orderId={order_id}&project_id={project_id}&token={order_token}"
        client = api._get_client()
        resp = client.get(url)
        data = resp.json()
        code_url = data.get("data", {}).get("payParam", {}).get("code_url", "")
        if code_url:
            logger.info("\n请扫描以下支付二维码完成支付：")
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(code_url)
            qr.make(fit=True)
            qr.print_ascii(invert=True)
            logger.info(f"或打开链接: {code_url}")
    except Exception as e:
        logger.warning(f"支付二维码生成失败: {e}")
        logger.info(f"请手动完成支付，订单ID: {order_id}")


def grab_ticket_interactive(config: Config, viewers: list = None) -> TicketResult:
    """交互式抢票"""
    grabber = TicketGrabber(config, viewers=viewers)
    
    try:
        result = grabber.run()
        return result
    except KeyboardInterrupt:
        logger.info("\n用户取消操作")
        grabber.stop()
        return TicketResult(success=False, message="用户取消")
