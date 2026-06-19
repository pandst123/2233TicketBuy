"""
B站API客户端
参考biliTickerBuy和BHYG的API设计
"""

import httpx
import json
import time
import random
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
    sale_flag_number: int = 0


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
    
    # API 基础 URL
    BASE_URL = "https://show.bilibili.com/api"
    
    # 请求头模板（对齐 BHYG mobile headers）
    def _get_default_headers(self) -> Dict:
        """获取默认请求头（含动态 UA）"""
        return {
            "User-Agent": self.mobile_ua,
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
        
        # ========== 设备指纹系统（对齐 BHYG） ==========
        self._init_fingerprint()
        
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
            # 设备指纹 cookie
            "buvid3": self.buvid3,
            "buvid4": self.buvid4,
            "buvid_fp": self.buvid_fp,
            "_uuid": self._uuid,
        }
        
        # 持久 HTTP Session（对齐 BHYG）
        self._client = None
        
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
    
    # ==================== 设备指纹系统 ====================

    @staticmethod
    def _gen_hex(n: int) -> str:
        """生成随机 hex 字符串"""
        return "".join(random.choices("0123456789abcdef", k=n))

    def _gen_ua(self) -> str:
        """动态生成 Android UA 并存储设备属性"""
        devices = {
            "Xiaomi": ["23013RK75C", "2312DRA50C", "2211133C", "2304FPN6DC"],
            "HUAWEI": ["ALN-AL10", "BRA-AL00", "CET-AL00", "VDE-AL00"],
            "Samsung": ["SM-S9110", "SM-S9080", "SM-S9180", "SM-F9460"],
            "OPPO": ["PHW110", "PJW110", "PHT110"],
            "vivo": ["V2301A", "V2241A", "V2338A"],
        }
        self._brand = random.choice(list(devices.keys()))
        self._model = random.choice(devices[self._brand])
        self._android_ver = random.choice(["15", "14", "12"])
        chrome_ver = f"{random.randint(100, 140)}.0.{random.randint(1000, 9999)}.{random.randint(100, 999)}"
        return (
            f"Mozilla/5.0 (Linux; Android {self._android_ver}; {self._model} Build/"
            f"AQ3A.{random.randint(240000, 249999)}.{random.randint(100, 999)}; wv) "
            f"AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 "
            f"Chrome/{chrome_ver} Mobile Safari/537.36 "
            f"BiliApp/100100 mobi_app/android"
        )

    @staticmethod
    def _gen_buvid3() -> str:
        """生成 buvid3（B站设备标识）"""
        import uuid as _uuid
        parts = [
            _uuid.uuid4().hex[:8].upper(),
            _uuid.uuid4().hex[:4].upper(),
            _uuid.uuid4().hex[:4].upper(),
            _uuid.uuid4().hex[:4].upper(),
            _uuid.uuid4().hex[:12].upper() + str(random.randint(10000, 99999)) + "infoc",
        ]
        return "-".join(parts)

    @staticmethod
    def _gen_buvid4() -> str:
        """生成 buvid4"""
        import uuid as _uuid
        parts = [
            _uuid.uuid4().hex[:16].upper(),
            _uuid.uuid4().hex[:4].upper(),
            _uuid.uuid4().hex[:4].upper(),
            _uuid.uuid4().hex[:4].upper(),
            _uuid.uuid4().hex[:12].upper() + str(random.randint(10000, 99999)),
        ]
        return "-".join(parts)

    @staticmethod
    def _gen_uuid_infoc() -> str:
        """生成 _uuid（infoc 格式）"""
        import uuid as _uuid
        hex_str = _uuid.uuid4().hex.upper()
        return (
            f"{hex_str[:8]}-{hex_str[8:12]}-{hex_str[12:16]}"
            f"-{hex_str[16:20]}-{hex_str[20:32]}{random.randint(10000, 99999)}infoc"
        )

    def _init_fingerprint(self) -> None:
        """初始化设备指纹体系"""
        self.mobile_ua = self._gen_ua()
        self._fetch_buvid_from_spi()
        self._uuid = self._gen_uuid_infoc()

        # 会话级静态指纹（对齐 BHYG：init 时生成一次，会话内不变）
        self._refresh_fingerprints()

    def _fetch_buvid_from_spi(self) -> None:
        """从 B站 SPi 指纹服务获取真实 buvid3/4（对齐 BHYG），失败时本地生成"""
        import hashlib

        # 本地计算 buvid_fp（含校验码，对齐 BHYG）
        random_md5 = hashlib.md5(str(random.random()).encode()).hexdigest()
        fp_raw = random_md5 + time.strftime("%Y%m%d%H%M%S", time.localtime()) + self._gen_hex(16)
        fp_sub = [fp_raw[i:i+2] for i in range(0, len(fp_raw), 2)]
        veri = 0
        for i in range(0, len(fp_sub), 2):
            veri += int(fp_sub[i], 16)
        self.buvid_fp = f"{fp_raw}{hex(veri % 256)[2:]}"

        try:
            client = httpx.Client(timeout=5, http2=True)
            resp = client.get(
                "https://api.bilibili.com/x/frontend/finger/spi",
                headers={"User-Agent": self.mobile_ua},
            )
            data = resp.json()
            if data.get("code") == 0:
                self.buvid3 = data["data"].get("b_3", "")
                self.buvid4 = data["data"].get("b_4", "")
                logger.debug(f"SPi buvid 获取成功")
                return
        except Exception as e:
            logger.debug(f"SPi 获取失败，回退本地生成: {e}")

        # Fallback: 本地生成
        self.buvid3 = self._gen_buvid3()
        self.buvid4 = self._gen_buvid4()

    def _refresh_fingerprints(self) -> None:
        """生成会话级静态指纹（init 时调用一次，不在每次请求时刷新）"""
        self.canvas_fp = self._gen_hex(32)
        self.webgl_fp = self._gen_hex(32)
        self.fe_sign = self._gen_hex(32)
        self.screen_info = f"{362}*{795}*{24}"

    # ==================== 持久 HTTP Session ====================

    def _get_client(self) -> httpx.Client:
        """获取持久 HTTP 客户端（对齐 BHYG session 管理）"""
        if self._client is None:
            self._client = httpx.Client(
                http2=True,
                timeout=self.config.strategy.timeout_seconds,
                proxy=self.proxy,
                follow_redirects=True,
                event_hooks={
                    "request": [self._on_request],
                },
            )
        return self._client

    def _on_request(self, request: httpx.Request) -> None:
        """请求前 hook：WBI 自动签名 + Cookie 注入设备指纹"""
        # WBI 自动签名（对标 BHYG on_request）
        if self.wbi_signer.is_initialized() and request.url.host in (
            "api.bilibili.com", "show.bilibili.com", "passport.bilibili.com"
        ):
            params = dict(request.url.params)
            if params:
                signed = self.wbi_signer.sign(params)
                request.url = request.url.copy_merge_params(signed)
        
        # Cookie 注入设备指纹
        identify_str = self._build_identify()
        self._client.cookies.update({
            "identify": identify_str,
            "screenInfo": self.screen_info,
            "canvasFp": self.canvas_fp,
            "webglFp": self.webgl_fp,
            "feSign": self.fe_sign,
        })

    def _build_identify(self) -> str:
        """构建复杂 identify 字符串（对标 BHYG _app_sign + _gen_risk_header）"""
        from urllib.parse import quote, urlencode
        uid = self.cookies.get("DedeUserID", "0")
        params = {
            "appkey": "1d8b6e7d45233436",
            "brand": self._brand,
            "localBuvid": self.buvid3,
            "mVersion": "296",
            "mallVersion": "100100",
            "model": self._model,
            "osver": self._android_ver,
            "platform": "h5",
            "uid": uid,
            "ts": str(int(time.time() * 1000)),
        }
        return quote(urlencode(params))

    def close(self) -> None:
        """关闭持久 session"""
        if self._client is not None:
            self._client.close()
            self._client = None
    
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
        # 覆盖 sign.py 的 PC UA 为动态 Android UA
        headers["User-Agent"] = self.mobile_ua
        headers["env"] = "prod"
        return headers
    
    def _check_response(self, result: Dict) -> None:
        """检查响应状态（支持 errno 和 code 两种格式）"""
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
        """发送 HTTP 请求"""
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
            client = self._get_client()
            response = client.request(
                method=method,
                url=url,
                params=params,
                data=data,
                json=json_data,
                headers=headers,
                cookies=self.cookies,
            )
            
            # 调试日志：每次请求的方法/URL/状态码
            logger.debug(f"{method} {url} → {response.status_code}")
            if response.status_code >= 400:
                logger.debug(f"  响应头: {dict(response.headers)}")
            
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
            sale_flag_number=data.get("sale_flag_number", 0),
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
                      buyer_info=None, id_bind: int = 0, viewers: list = None, is_hot: bool = False) -> Dict:
        """
        准备token（参考BHYG实现）
        """
        url = f"{self.BASE_URL}/ticket/order/prepare?project_id={project_id}"
        
        # prepare 用原始 API buyer_info 值（BHYG 就是这样做的）
        buyer_info_data = buyer_info if buyer_info else ""
        
        # 生成 ctoken（prepare 接口用，仅 hot 项目）
        ctoken = ""
        if is_hot:
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
        
        # prepare 接口直接请求，手动解析
        body_data = json.dumps(data)
        headers = self._get_headers("POST", url, body_data)
        try:
            client = self._get_client()
            response = client.post(url, json=data, headers=headers, cookies=self.cookies)
            result = response.json()
        except Exception as e:
            logger.warning(f"prepare_token 请求异常: {e}")
            return {}
        
        errno = result.get("errno", -1)
        if errno == 0:
            data = result.get("data", {})
            ga = data.get("ga_data", {})
            shield = data.get("shield", {})
            if shield.get("open"):
                logger.warning(f"prepare_token shield 开启: {shield}")
            if ga.get("decisions"):
                logger.debug(f"ga decisions: {ga.get('decisions')}")
            if ga.get("riskResult", 0) != 0:
                logger.warning(f"ga riskResult={ga['riskResult']}")
        if errno != 0:
            logger.debug(f"prepare_token errno={errno}: {result.get('msg', '')}")
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
        is_hot: bool = False,
        cached_pay_money: int = 0,
    ) -> tuple:
        """创建订单（BHYG do_order_create 风格）"""
        url = f"{self.BASE_URL}/ticket/order/createV2?project_id={project_id}"
        
        project = self.get_project_info(project_id)
        id_bind = project.id_bind
        
        # 获取 token
        if cached_token:
            token = cached_token
            ptoken = cached_ptoken
        else:
            buyer_info = project.buyer_info
            logger.info(f"准备token: project={project_id}, screen={screen_id}, sku={sku_id}, count={count}")
            prepare_data = self.prepare_token(project_id, screen_id, sku_id, count,
                                               buyer_info=buyer_info, id_bind=id_bind,
                                               viewers=viewers, is_hot=is_hot)
            token = prepare_data.get("token", "") or ""
            ptoken = prepare_data.get("ptoken", "") or ""

        ptoken_clean = ptoken.replace("=", "") if ptoken else ""
        
        # prepare 和 create 之间延迟
        time.sleep(0.3)
        
        # 获取价格（优先使用缓存价格，BHYG: 100034 自动更新）
        pay_money = cached_pay_money if cached_pay_money else 0
        if not pay_money:
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
        
        # BHYG 风格：clickPosition + requestSource + newRisk
        # origin 应比 now 早 10-20 秒（模拟用户浏览耗时）
        # 如果有 token_gen 则用作随机种子（BHYG 行为）
        cp_seed = self.cp2312.token_gen if hasattr(self.cp2312, 'token_gen') and self.cp2312.token_gen else None
        if cp_seed:
            random.seed(int(cp_seed))
        click_origin = now_ms - random.randint(10000, 20000)
        order_data["clickPosition"] = {
            "x": random.randint(100, 500),
            "y": random.randint(500, 900),
            "origin": click_origin,
            "now": now_ms,
        }
        order_data["requestSource"] = "neul-next"
        order_data["newRisk"] = True
        
        # csrf token（B站创建订单必需）
        order_data["csrf"] = self.cookies.get("bili_jct", "")
        
        # 🔑 BHYG hot 项目专项处理
        if is_hot:
            # 生成 ctoken（hot 项目 createV2 用，区别于 prepare 的 ctoken）
            ctoken = ""
            try:
                from .cp2312 import get_ctoken
                ctoken = get_ctoken(project_id, screen_id, sku_id, count)
                logger.hot(f"ctoken 生成成功: {ctoken[:20]}...")
            except Exception as e:
                logger.hot(f"ctoken 生成失败: {e}")
            if ctoken:
                order_data["ctoken"] = ctoken
            order_data["ptoken"] = ptoken_clean
            order_data["orderCreateUrl"] = "https://show.bilibili.com/api/ticket/order/createV2"
            # 记录完整请求（脱敏）
            _safe = {k: v for k, v in order_data.items() if k not in ("csrf", "buyer", "tel", "contactInfo")}
            logger.hot(f"create_order 请求: url={url}, payload={json.dumps(_safe, ensure_ascii=False)[:800]}")
        else:
            order_data["ptoken"] = ptoken_clean
        
        # 直接发 HTTP 请求，不使用 _request()
        body_data = json.dumps(order_data)
        headers = self._get_headers("POST", url, body_data)
        
        # BHYG hot 项目: ptoken 加入 URL query
        request_url = url
        if is_hot:
            request_url = f"{url}&ptoken={ptoken_clean}"
        
        try:
            client = self._get_client()
            response = client.post(request_url, json=order_data, headers=headers, cookies=self.cookies)
            result = response.json()
        except Exception as e:
            logger.warning(f"create_order 网络异常: {e}")
            # 网络异常也返回 token，让调用方缓存
            return {"errno": -999, "msg": str(e), "data": {}}, token, ptoken_clean
        
        errno = result.get("errno", result.get("code", -1))
        msg = result.get("msg", result.get("message", ""))
        
        # 🔥 Hot 项目：记录完整响应
        if is_hot:
            logger.hot(f"create_order 响应: errno={errno}, msg={msg}")
            if errno != 0:
                logger.hot(f"create_order 完整响应: {json.dumps(result, ensure_ascii=False)[:1000]}")

        
        # 返回 (result, token, ptoken)
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
            client = self._get_client()
            response = client.get(
                url,
                headers=self._get_default_headers(),
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

    def get_server_time(self) -> float:
        """获取 show.bilibili.com 服务器时间（通过 HTTP Date 头，用于精确同步）"""
        try:
            client = self._get_client()
            resp = client.head("https://show.bilibili.com")
            date_str = resp.headers.get("Date", "")
            if date_str:
                from email.utils import parsedate_to_datetime
                server_dt = parsedate_to_datetime(date_str)
                ts = server_dt.timestamp()
                offset = ts - time.time()
                logger.debug(f"服务器时间(Date头): {date_str}, 本地偏移: {offset:+.2f}s")
                return ts
        except Exception as e:
            logger.debug(f"获取服务器时间失败: {e}")
        return time.time()


def create_api_client(config: Config) -> BilibiliAPI:
    """创建API客户端"""
    return BilibiliAPI(config)
