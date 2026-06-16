"""
WBI 签名算法实现
参考biliTickerBuy的WBI签名实现
"""

import hashlib
import time
import urllib.parse
from typing import Dict, Optional, Tuple

import httpx


class WbiSigner:
    """
    WBI 签名器
    
    用于生成B站API请求的WBI签名
    
    WBI签名原理：
    1. 从nav接口获取wbi_img_url和wbi_sub_url
    2. 提取key并混淆
    3. 对参数进行排序和拼接
    4. 使用MD5生成签名
    """
    
    # 混淆密钥表
    MIXIN_KEY_ENC_TAB = [
        46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
        27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
        37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
        22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
    ]
    
    def __init__(self):
        """初始化WBI签名器"""
        self.mixin_key: Optional[str] = None
        self.wbi_img_url: Optional[str] = None
        self.wbi_sub_url: Optional[str] = None
        
    def _get_mixin_key(self, orig: str) -> str:
        """
        获取混淆密钥
        
        Args:
            orig: 原始密钥字符串
            
        Returns:
            混淆后的32位密钥
        """
        return "".join([orig[i] for i in self.MIXIN_KEY_ENC_TAB])[:32]
    
    def _extract_key_from_url(self, url: str) -> str:
        """
        从URL中提取密钥
        
        Args:
            url: wbi_img_url 或 wbi_sub_url
            
        Returns:
            提取的密钥
        """
        # 从URL中提取文件名（不含扩展名）
        filename = url.split("/")[-1].split(".")[0]
        return filename
    
    def update_keys(self, wbi_img_url: str, wbi_sub_url: str) -> None:
        """
        更新WBI密钥
        
        Args:
            wbi_img_url: wbi_img URL
            wbi_sub_url: wbi_sub URL
        """
        self.wbi_img_url = wbi_img_url
        self.wbi_sub_url = wbi_sub_url
        
        # 提取两个key
        img_key = self._extract_key_from_url(wbi_img_url)
        sub_key = self._extract_key_from_url(wbi_sub_url)
        
        # 拼接并混淆
        orig_key = img_key + sub_key
        self.mixin_key = self._get_mixin_key(orig_key)
    
    def fetch_keys_from_nav(self, cookies: Optional[Dict[str, str]] = None) -> bool:
        """
        从nav接口获取WBI密钥
        
        Args:
            cookies: Cookie字典（可选）
            
        Returns:
            是否成功获取
        """
        url = "https://api.bilibili.com/x/web-interface/nav"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.bilibili.com/",
        }
        
        try:
            with httpx.Client() as client:
                response = client.get(url, headers=headers, cookies=cookies)
                result = response.json()
                
                if result.get("code") == 0:
                    data = result.get("data", {})
                    wbi_img = data.get("wbi_img", {})
                    img_url = wbi_img.get("img_url", "")
                    sub_url = wbi_img.get("sub_url", "")
                    
                    if img_url and sub_url:
                        self.update_keys(img_url, sub_url)
                        return True
            
            return False
            
        except Exception:
            return False
    
    def get_wbi_keys_from_nav(self, nav_data: Dict) -> None:
        """
        从导航接口数据中获取WBI密钥
        
        Args:
            nav_data: /x/web-interface/nav 接口返回的数据
        """
        wbi_img = nav_data.get("wbi_img", {})
        img_url = wbi_img.get("img_url", "")
        sub_url = wbi_img.get("sub_url", "")
        
        if img_url and sub_url:
            self.update_keys(img_url, sub_url)
    
    def sign(self, params: Dict[str, str]) -> Dict[str, str]:
        """
        对参数进行WBI签名
        
        Args:
            params: 原始参数字典
            
        Returns:
            包含签名的参数字典
            
        Raises:
            ValueError: 未初始化密钥
        """
        if not self.mixin_key:
            raise ValueError("WBI密钥未初始化，请先调用 fetch_keys_from_nav 或 update_keys")
        
        # 添加当前时间戳
        params["wts"] = str(int(time.time()))
        
        # 按key排序
        sorted_params = sorted(params.items())
        
        # 过滤特殊字符
        filtered_params = []
        for key, value in sorted_params:
            # 过滤特殊字符
            value = "".join([c for c in value if c not in "!'()*"])
            filtered_params.append((key, value))
        
        # 拼接参数
        query = urllib.parse.urlencode(filtered_params)
        
        # 计算签名
        sign_str = query + self.mixin_key
        w_rid = hashlib.md5(sign_str.encode()).hexdigest()
        
        # 添加签名到参数
        params["w_rid"] = w_rid
        
        return params
    
    def sign_url(self, url: str, params: Optional[Dict[str, str]] = None) -> str:
        """
        对URL进行WBI签名
        
        Args:
            url: 原始URL
            params: 额外参数（可选）
            
        Returns:
            签名后的完整URL
        """
        if params is None:
            params = {}
        
        # 解析URL中的参数
        parsed = urllib.parse.urlparse(url)
        url_params = dict(urllib.parse.parse_qsl(parsed.query))
        
        # 合并参数
        all_params = {**url_params, **params}
        
        # 签名
        signed_params = self.sign(all_params)
        
        # 构建新URL
        query = urllib.parse.urlencode(signed_params)
        signed_url = urllib.parse.urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            query,
            parsed.fragment,
        ))
        
        return signed_url
    
    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return self.mixin_key is not None


# 全局实例
_wbi_signer = WbiSigner()


def get_wbi_signer() -> WbiSigner:
    """
    获取全局WBI签名器实例
    
    Returns:
        WbiSigner实例
    """
    return _wbi_signer


def sign_params(params: Dict[str, str]) -> Dict[str, str]:
    """
    对参数进行WBI签名的便捷函数
    
    Args:
        params: 原始参数字典
        
    Returns:
        包含签名的参数字典
    """
    return _wbi_signer.sign(params)


def init_wbi_keys(wbi_img_url: str, wbi_sub_url: str) -> None:
    """
    初始化WBI密钥的便捷函数
    
    Args:
        wbi_img_url: wbi_img URL
        wbi_sub_url: wbi_sub URL
    """
    _wbi_signer.update_keys(wbi_img_url, wbi_sub_url)


def fetch_wbi_keys(cookies: Optional[Dict[str, str]] = None) -> bool:
    """
    从nav接口获取WBI密钥的便捷函数
    
    Args:
        cookies: Cookie字典
        
    Returns:
        是否成功获取
    """
    return _wbi_signer.fetch_keys_from_nav(cookies)
