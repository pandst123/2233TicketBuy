"""
签名模块
实现B站API请求的各种签名
"""

import hashlib
import hmac
import time
import uuid
from typing import Dict, Optional


class SignGenerator:
    """
    签名生成器
    
    功能：
    - 生成 x-bili-sign 签名
    - 生成 risk_params
    - 生成 ptoken
    """
    
    # 默认密钥（可能需要更新）
    DEFAULT_SECRET = "fd869ce808144b29a75c81f59f3f59c0"
    
    def __init__(self, secret: Optional[str] = None):
        """
        初始化签名生成器
        
        Args:
            secret: 签名密钥
        """
        self.secret = secret or self.DEFAULT_SECRET
    
    def generate_x_bili_sign(
        self,
        method: str,
        url: str,
        timestamp: int,
        data: Optional[str] = None,
    ) -> str:
        """
        生成 x-bili-sign 签名
        
        Args:
            method: 请求方法（GET/POST）
            url: 请求URL（不含域名）
            timestamp: 时间戳
            data: 请求体数据（可选）
            
        Returns:
            签名字符串
        """
        # 构建签名内容
        content_parts = [
            method.upper(),
            url,
            str(timestamp),
        ]
        
        if data:
            content_parts.append(data)
        
        content = "\n".join(content_parts)
        
        # 使用HMAC-SHA256签名
        signature = hmac.new(
            self.secret.encode(),
            content.encode(),
            hashlib.sha256,
        ).hexdigest()
        
        return signature
    
    def generate_risk_params(
        self,
        user_agent: str,
        referer: str,
        timestamp: Optional[int] = None,
    ) -> Dict[str, str]:
        """
        生成 risk_params 风控参数
        
        Args:
            user_agent: User-Agent
            referer: Referer
            timestamp: 时间戳（可选）
            
        Returns:
            risk_params 字典
        """
        if timestamp is None:
            timestamp = int(time.time())
        
        # 生成设备指纹
        device_id = str(uuid.uuid4())
        
        # 构建risk_params
        risk_params = {
            "platform": "pc",
            "device": "pc",
            "timestamp": str(timestamp),
            "device_id": device_id,
            "refer": referer,
            "user_agent": user_agent,
        }
        
        return risk_params
    
    def generate_ptoken(
        self,
        mid: str,
        timestamp: Optional[int] = None,
    ) -> str:
        """
        生成 ptoken
        
        Args:
            mid: 用户ID
            timestamp: 时间戳（可选）
            
        Returns:
            ptoken字符串
        """
        if timestamp is None:
            timestamp = int(time.time())
        
        # 构建ptoken内容
        content = f"{mid}:{timestamp}:{self.secret}"
        
        # 使用SHA256生成token
        ptoken = hashlib.sha256(content.encode()).hexdigest()
        
        return ptoken
    
    def generate_csrf_token(self, bili_jct: str) -> str:
        """
        生成CSRF token（通常直接使用bili_jct）
        
        Args:
            bili_jct: bili_jct cookie值
            
        Returns:
            CSRF token
        """
        return bili_jct
    
    def get_signed_headers(
        self,
        method: str,
        url: str,
        cookie: Dict[str, str],
        data: Optional[str] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        """
        获取完整的签名请求头
        
        Args:
            method: 请求方法
            url: 请求URL
            cookie: Cookie字典
            data: 请求体数据
            extra_headers: 额外的请求头
            
        Returns:
            完整的请求头字典
        """
        timestamp = int(time.time())
        
        # 生成签名
        sign = self.generate_x_bili_sign(method, url, timestamp, data)
        
        # 生成ptoken
        mid = cookie.get("DedeUserID", "")
        ptoken = self.generate_ptoken(mid, timestamp)
        
        # 构建请求头
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://show.bilibili.com/",
            "Origin": "https://show.bilibili.com",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "x-bili-sign": sign,
            "x-bili-ptoken": ptoken,
            "x-bili-mid": mid,
            "x-bili-timestamp": str(timestamp),
        }
        
        # 添加额外请求头
        if extra_headers:
            headers.update(extra_headers)
        
        return headers


# 全局实例
_sign_generator = SignGenerator()


def get_sign_generator() -> SignGenerator:
    """
    获取全局签名生成器实例
    
    Returns:
        SignGenerator实例
    """
    return _sign_generator


def generate_x_bili_sign(
    method: str,
    url: str,
    timestamp: int,
    data: Optional[str] = None,
) -> str:
    """
    生成 x-bili-sign 签名的便捷函数
    
    Args:
        method: 请求方法
        url: 请求URL
        timestamp: 时间戳
        data: 请求体数据
        
    Returns:
        签名字符串
    """
    return _sign_generator.generate_x_bili_sign(method, url, timestamp, data)


def generate_risk_params(
    user_agent: str,
    referer: str,
    timestamp: Optional[int] = None,
) -> Dict[str, str]:
    """
    生成 risk_params 的便捷函数
    
    Args:
        user_agent: User-Agent
        referer: Referer
        timestamp: 时间戳
        
    Returns:
        risk_params 字典
    """
    return _sign_generator.generate_risk_params(user_agent, referer, timestamp)
