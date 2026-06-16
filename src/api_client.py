"""
B站API客户端
参考biliTickerBuy和BHYG的API设计
"""

import httpx
import json
import time
import hashlib
import uuid
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from .cp2312 import Cp2312Generator, create_generator
from .config import Config
from .sign import SignGenerator, get_sign_generator
from .wbi import WbiSigner, get_wbi_signer, fetch_wbi_keys
from .error_recovery import safe_request, ErrorRecovery, get_error_recovery, NetworkError, APIError
from .logger import logger


@dataclass
class ProjectInfo:
    """项目信息"""
    id: int
    name: str
    start_time: int
    sale_begin: int
    screens: List[Dict]
    status: str
    cover: str = ""
    description: str = ""
    buyer_info: str = ""
    id_bind: int = 0
    hot_project: bool = False


@dataclass
class ScreenInfo:
    """场次信息"""
    id: int
    name: str
    start_time: str
    end_time: str
    skus: List[Dict]


class BilibiliAPI:
    """
    B站API客户端
    
    参考BHYG的API设计
    """
    
    # API基础URL
    BASE_URL = "https://show.bilibili.com/api"
    
    # 🔑 使用移动端 UA（对齐 BHYG，PC UA 容易被 B 站限速）
    # BHYG 使用 Android WebView UA，B站会员购对移动端请求更宽容
    MOBILE_UA = (
        "Mozilla/5.0 (Linux; Android 15; 23013RK75C Build/AQ3A.240812.002; wv) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 "
        "Chrome/135.0.7049.79 Mobile Safari/537.36 "
        "BiliApp/100100 mobi_app/android"
    )
    
    # 请求头模板（对齐 BHYG mobile headers）
    DEFAULT_HEADERS = {
        "User-Agent": MOBILE_UA,
        "Referer": "https://show.bilibili.com/",
        "Origin": "https://show.bilibili.com",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "env": "prod",
    }
    
    def __init__(self, config: Config, cp2312_generator: Optional[Cp2312Generator] = None):
        """
        初始化API客户端
        
        Args:
            config: 配置对象
            cp2312_generator: cp2312生成器
        """
        self.config = config
        self.cp2312 = cp2312_generator or create_generator()
        self.sign_generator = get_sign_generator()
        self.wbi_signer = get_wbi_signer()
        self.error_recovery = get_error_recovery()
        
        # 生成设备ID
        self.device_id = hashlib.md5(str(uuid.uuid4()).encode()).hexdigest()
        
        # 构建Cookie（对齐 BHYG show.bilibili.com 专属 cookie）
        self.cookies = {
            "SESSDATA": config.user.sessdata,
            "bili_jct": config.user.bili_jct,
            "DedeUserID": config.user.dede_user_id,
            "DedeUserID__ckMd5": config.user.dede_user_id_ckmd5,
            # BHYG 风格：show.bilibili.com 专属 cookie
            "msource": "bilibiliapp",
            "kfcSource": "bilibiliapp",
            "deviceFingerprint": self.device_id,
        }
        
        # 代理配置
        self.proxy = None
        if config.proxy.enabled:
            if config.proxy.socks5:
                self.proxy = config.proxy.socks5
            elif config.proxy.https:
                self.proxy = config.proxy.https
            elif config.proxy.http:
                self.proxy = config.proxy.http
        
        # 初始化WBI密钥
        self._init_wbi_keys()
    
    def _init_wbi_keys(self) -> None:
        """初始化WBI密钥"""
        if not self.wbi_signer.is_initialized():
            logger.info("正在获取WBI密钥...")
            if fetch_wbi_keys(self.cookies):
                logger.info("WBI密钥获取成功")
            else:
                logger.warning("WBI密钥获取失败，部分功能可能不可用")
    
    def _create_client(self) -> httpx.Client:
        """创建HTTP客户端"""
        return httpx.Client(
            http2=True,
            timeout=self.config.strategy.timeout_seconds,
            proxy=self.proxy,
            follow_redirects=True,
        )
    
    def _get_headers(
        self,
        method: str,
        url: str,
        data: Optional[str] = None,
        extra_headers: Optional[Dict] = None,
    ) -> Dict:
        """构建请求头"""
        headers = self.sign_generator.get_signed_headers(
            method=method,
            url=url,
            cookie=self.cookies,
            data=data,
            extra_headers=extra_headers,
        )
        return headers
    
    def _check_response(self, result: Dict) -> None:
        """
        检查响应状态
        
        B站API有两种状态码格式：
        1. code/message 格式（通用API）
        2. errno/msg 格式（会员购API）
        """
        # 检查errno格式（会员购API）
        errno = result.get("errno", None)
        if errno is not None:
            if errno != 0:
                msg = result.get("msg", "未知错误")
                logger.warning(f"API错误 errno={errno}: {msg}, 响应: {str(result)[:500]}")
                raise APIError(code=errno, message=msg)
            return
        
        # 检查code格式（通用API）
        code = result.get("code", None)
        if code is not None:
            if code != 0:
                message = result.get("message", result.get("msg", "未知错误"))
                raise APIError(code=code, message=message)
            return
        
        # 如果都没有找到，检查是否有data字段
        if "data" not in result:
            raise APIError(code=-1, message="响应格式异常")
    
    def _request(
        self,
        method: str,
        url: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
        extra_headers: Optional[Dict] = None,
        use_wbi: bool = False,
    ) -> Dict:
        """发送HTTP请求"""
        # WBI签名
        if use_wbi and params:
            params = self.wbi_signer.sign(params.copy())
        
        # 准备请求体数据
        body_data = None
        if json_data:
            body_data = json.dumps(json_data)
        elif data:
            body_data = "&".join([f"{k}={v}" for k, v in data.items()])
        
        # 构建请求头
        headers = self._get_headers(method, url, body_data, extra_headers)
        
        try:
            with self._create_client() as client:
                response = client.request(
                    method=method,
                    url=url,
                    params=params,
                    data=data,
                    json=json_data,
                    headers=headers,
                    cookies=self.cookies,
                )
                
                # 检查Content-Type
                content_type = response.headers.get("content-type", "")
                if "json" not in content_type:
                    # 打印调试信息
                    logger.debug(f"请求URL: {method} {url}")
                    logger.debug(f"响应状态码: {response.status_code}")
                    logger.debug(f"响应Content-Type: {content_type}")
                    logger.debug(f"响应内容前200字符: {response.text[:200]}")
                    raise Exception(f"API返回非JSON响应，Content-Type: {content_type}")
                
                result = response.json()
                
                # 检查响应状态
                self._check_response(result)
                
                return result
                
        except APIError:
            raise
        except httpx.TimeoutException:
            raise NetworkError("请求超时")
        except httpx.NetworkError as e:
            raise NetworkError(f"网络错误: {e}")
        except Exception as e:
            raise NetworkError(f"请求错误: {e}")
    
    def get_project_info(self, project_id: int) -> ProjectInfo:
        """
        获取项目信息
        
        使用正确的API端点: /api/ticket/project/get
        """
        url = f"{self.BASE_URL}/ticket/project/get"
        params = {"id": project_id}
        
        result = self._request("GET", url, params=params)
        data = result["data"]
        
        screens = data.get("screen_list", [])
        
        return ProjectInfo(
            id=data["id"],
            name=data["name"],
            start_time=data.get("start_time", 0),
            sale_begin=data.get("sale_begin", 0),
            screens=screens,
            status=data.get("status", ""),
            cover=data.get("cover", ""),
            description=data.get("description", ""),
            buyer_info=data.get("buyer_info", ""),
            id_bind=data.get("id_bind", 0),
            hot_project=data.get("hotProject", False),
        )
    
    def get_screen_info(self, project_id: int, screen_id: int) -> ScreenInfo:
        """获取场次信息"""
        project = self.get_project_info(project_id)
        
        for screen in project.screens:
            if screen["id"] == screen_id:
                return ScreenInfo(
                    id=screen["id"],
                    name=screen.get("name", ""),
                    start_time=screen.get("start_time", ""),
                    end_time=screen.get("end_time", ""),
                    skus=screen.get("ticket_list", []),
                )
        
        raise Exception(f"未找到场次: {screen_id}")
    
    def get_sku_list(self, project_id: int, screen_id: int) -> List[Dict]:
        """获取票档列表"""
        screen = self.get_screen_info(project_id, screen_id)
        return screen.skus
    
    def prepare_token(self, project_id: int, screen_id: int, sku_id: int, count: int,
                      buyer_info=None, id_bind: int = 0, viewers: list = None) -> Dict:
        """
        准备token（参考BHYG实现）
        """
        url = f"{self.BASE_URL}/ticket/order/prepare?project_id={project_id}"
        
        # prepare 用原始 API buyer_info 值（BHYG 就是这样做的）
        buyer_info_data = buyer_info if buyer_info else ""
        
        # 生成 ctoken（参考 BHYG hotProject 处理）
        ctoken = ""
        try:
            from .cp2312 import get_ctoken
            ctoken = get_ctoken(project_id, screen_id, sku_id, count)
        except Exception as e:
            logger.debug(f"ctoken 生成失败: {e}")
        
        data = {
            "project_id": project_id,
            "screen_id": screen_id,
            "order_type": 1,
            "count": count,
            "sku_id": sku_id,
            "buyer_info": buyer_info_data,
            "ignoreRequestLimit": True,
            "ticket_agent": "",
            "newRisk": True,
            "requestSource": "neul-next",
        }
        if ctoken:
            data["token"] = ctoken
        
        logger.info(f"prepare_token 请求: {url}")
        logger.info(f"ctoken: {ctoken[:30] if ctoken else '空'}...")
        logger.debug(f"prepare_token data: {data}")
        
        # prepare 接口的 errno 含义不同于 create，不能用 _check_response
        # 直接发请求，手动解析
        body_data = json.dumps(data)
        headers = self._get_headers("POST", url, body_data)
        try:
            with self._create_client() as client:
                response = client.post(url, json=data, headers=headers, cookies=self.cookies)
                result = response.json()
        except Exception as e:
            logger.warning(f"prepare_token 请求异常: {e}")
            return {}
        
        errno = result.get("errno", -1)
        logger.info(f"prepare_token 响应: errno={errno}, msg={result.get('msg', '')}")
        
        if errno == 0:
            return result.get("data", {})
        else:
            logger.warning(f"prepare_token errno={errno}: {result.get('msg', '')}")
            return result.get("data", {}) or {}
    
    def create_order(
        self,
        project_id: int,
        screen_id: int,
        sku_id: int,
        count: int,
        buyer_name: str = "",
        buyer_tel: str = "",
        viewer_id: Optional[int] = None,
        viewers: list = None,
        cached_token: str = "",
        cached_ptoken: str = "",
    ) -> tuple:
        """
        创建订单（参考 BHYG do_order_create）
        
        关键设计（对齐 BHYG）：
        - 不使用 _request()（它会抛异常导致 token 无法返回）
        - 直接发 HTTP 请求，手动解析响应
        - 无论成功失败，都返回 (result_dict, token, ptoken)
        - 调用方可以缓存 token 避免重复 prepare 被限速
        """
        url = f"{self.BASE_URL}/ticket/order/createV2?project_id={project_id}"
        
        project = self.get_project_info(project_id)
        id_bind = project.id_bind
        
        # 获取 token（有缓存就用，避免重复 prepare 被限速）
        if cached_token:
            token = cached_token
            ptoken = cached_ptoken
            logger.info("使用缓存 token，跳过 prepare")
        else:
            buyer_info = project.buyer_info
            logger.info(f"准备token: project={project_id}, screen={screen_id}, sku={sku_id}, count={count}")
            prepare_data = self.prepare_token(project_id, screen_id, sku_id, count,
                                               buyer_info=buyer_info, id_bind=id_bind,
                                               viewers=viewers)
            token = prepare_data.get("token", "") or ""
            ptoken = prepare_data.get("ptoken", "") or ""
        
        ptoken_clean = ptoken.replace("=", "") if ptoken else ""
        logger.info(f"Token: {token[:20] if token else '空'}...")
        logger.info(f"Ptoken: {ptoken_clean[:20] if ptoken_clean else '空'}...")
        
        # prepare 和 create 之间延迟（BHYG 默认 order_interval=0.3s）
        time.sleep(0.3)
        
        # 获取价格
        pay_money = 0
        for screen in project.screens:
            if screen["id"] == screen_id:
                for sku in screen.get("ticket_list", []):
                    if sku["id"] == sku_id:
                        pay_money = sku.get("price", 0)
                        break
        
        # 构建订单数据（严格对齐 BHYG do_order_create 格式）
        now_ms = int(time.time() * 1000)
        
        order_data = {
            "project_id": project_id,
            "screen_id": screen_id,
            "count": count,
            "pay_money": pay_money,
            "order_type": 1,
            "timestamp": now_ms,
            "id_bind": id_bind,
            "need_contact": 1 if id_bind == 0 else 0,
            "is_package": 0,
            "package_num": 1,
            "contactInfo": {
                "uid": int(self.config.user.dede_user_id) if self.config.user.dede_user_id else 0,
                "username": buyer_name if id_bind == 0 else None,
                "tel": buyer_tel if id_bind == 0 else None,
            } if id_bind == 0 else None,
            "sku_id": sku_id,
            "coupon_code": "",
            "again": 0,
            "token": token,
            "ptoken": ptoken_clean,
            "deviceId": self.device_id,
            "version": "1.1.0",
        }
        
        if id_bind == 0:
            order_data["buyer"] = buyer_name
            order_data["tel"] = buyer_tel
        elif id_bind >= 1 and viewers:
            order_data["buyer_info"] = json.dumps([{
                "id": v.get("id"),
                "name": v.get("name"),
                "tel": v.get("tel"),
                "personal_id": v.get("personal_id"),
                "id_type": v.get("id_type", 0),
            } for v in viewers])
            order_data["buyer"] = buyer_name
            order_data["tel"] = buyer_tel
        
        # BHYG 风格：clickPosition + requestSource + newRisk
        # 注意 BHYG 没有 deviceInfo 和 riskParams（它们可能触发风控）
        order_data["clickPosition"] = {
            "x": 284,
            "y": 768,
            "origin": now_ms,
            "now": now_ms,
        }
        order_data["requestSource"] = "neul-next"
        order_data["newRisk"] = True
        
        # csrf token（B站创建订单必需）
        order_data["csrf"] = self.cookies.get("bili_jct", "")
        
        logger.info(f"订单数据: {order_data}")
        
        # 🔑 关键：不使用 _request()（它会抛异常），直接发 HTTP 请求
        # 这样无论 errno 是什么，都能正确返回 token 给调用方缓存
        body_data = json.dumps(order_data)
        headers = self._get_headers("POST", url, body_data)
        
        try:
            with self._create_client() as client:
                response = client.post(url, json=order_data, headers=headers, cookies=self.cookies)
                result = response.json()
        except Exception as e:
            logger.warning(f"create_order 网络异常: {e}")
            # 网络异常也返回 token，让调用方缓存
            return {"errno": -999, "msg": str(e), "data": {}}, token, ptoken_clean
        
        errno = result.get("errno", result.get("code", -1))
        msg = result.get("msg", result.get("message", ""))
        logger.info(f"create_order 响应: errno={errno}, msg={msg}")
        
        # 无论成功失败，都返回 (result, token, ptoken)
        return result, token, ptoken_clean
    
    def get_order_info(self, order_id: str) -> Dict:
        """获取订单信息"""
        url = f"{self.BASE_URL}/ticket/order/info"
        params = {"order_id": order_id}
        return self._request("GET", url, params=params)
    
    def create_pay(self, order_id: str) -> Dict:
        """创建支付"""
        url = f"{self.BASE_URL}/ticket/order/createPay"
        data = {"order_id": order_id}
        return self._request("POST", url, json_data=data)
    
    def check_login(self) -> bool:
        """检查登录状态"""
        try:
            url = "https://api.bilibili.com/x/web-interface/nav"
            with self._create_client() as client:
                response = client.get(
                    url,
                    headers=self.DEFAULT_HEADERS,
                    cookies=self.cookies,
                )
                result = response.json()
                return result.get("code") == 0
        except:
            return False
    
    def get_user_info(self) -> Dict:
        """获取用户信息"""
        url = "https://api.bilibili.com/x/web-interface/nav"
        result = self._request("GET", url)
        return result["data"]


def create_api_client(config: Config) -> BilibiliAPI:
    """创建API客户端"""
    return BilibiliAPI(config)
