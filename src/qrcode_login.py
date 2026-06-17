"""
二维码登录模块
实现B站二维码登录流程
"""

import time
import httpx
import qrcode
import io
from typing import Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class LoginResult:
    """登录结果"""
    success: bool
    sessdata: str = ""
    bili_jct: str = ""
    dede_user_id: str = ""
    dede_user_id_ckmd5: str = ""
    message: str = ""


class QRCodeLogin:
    """B站二维码登录"""
    
    QR_GET_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
    QR_POLL_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
    
    STATUS_SUCCESS = 0
    STATUS_EXPIRED = 86038
    STATUS_SCANNED = 86090
    STATUS_NOT_SCANNED = 86101
    
    def __init__(self, timeout: int = 180):
        """
        初始化登录模块
        
        Args:
            timeout: 二维码有效期（秒）
        """
        self.timeout = timeout
        self.qrcode_key: Optional[str] = None
        self.qrcode_url: Optional[str] = None
        
    def get_qrcode_url(self) -> Tuple[str, str]:
        """获取二维码URL，返回 (url, qrcode_key)"""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.bilibili.com/",
        }
        
        with httpx.Client() as client:
            response = client.get(self.QR_GET_URL, headers=headers)
            data = response.json()
            
            if data["code"] != 0:
                raise Exception(f"获取二维码失败: {data['message']}")
            
            self.qrcode_url = data["data"]["url"]
            self.qrcode_key = data["data"]["qrcode_key"]
            
            return self.qrcode_url, self.qrcode_key
    
    def generate_qrcode_image(self, url: str) -> bytes:
        """
        生成二维码图片
        
        Args:
            url: 二维码内容
            
        Returns:
            PNG图片数据
        """
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(url)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # 转换为PNG字节
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return buffer.getvalue()
    
    def display_qrcode(self, url: str, show_window: bool = True) -> None:
        """显示二维码：终端 ASCII + 图片窗口弹出"""
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=1,
            border=1,
        )
        qr.add_data(url)
        qr.make(fit=True)
        qr.print_ascii(invert=True)

        if show_window:
            try:
                img = qr.make_image(fill_color="black", back_color="white")
                img = img.resize((img.width * 8, img.height * 8))
                img.show()
            except Exception:
                pass
    
    def poll_scan_status(self) -> Dict:
        """轮询扫码状态"""
        if not self.qrcode_key:
            raise Exception("请先获取二维码")
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.bilibili.com/",
        }
        
        params = {
            "qrcode_key": self.qrcode_key,
        }
        
        with httpx.Client(follow_redirects=True) as client:
            response = client.get(self.QR_POLL_URL, params=params, headers=headers)
            result = response.json()
            # 保存响应头，用于获取cookie
            result["_headers"] = dict(response.headers)
            result["_cookies"] = dict(response.cookies)
            return result
    
    def login(self, display_qrcode: bool = True) -> LoginResult:
        """执行登录流程"""
        try:
            # 获取二维码
            print("正在获取二维码...")
            url, key = self.get_qrcode_url()
            
            # 显示二维码
            if display_qrcode:
                print("\n请使用B站APP扫描以下二维码：\n")
                self.display_qrcode(url)
                print(f"\n二维码链接: {url}")
                print(f"\n二维码有效期: {self.timeout}秒")
                print("请尽快扫描...\n")
            
            # 轮询扫码状态
            start_time = time.time()
            while time.time() - start_time < self.timeout:
                result = self.poll_scan_status()
                # 状态码在 data.code 中，不是顶层 code
                data = result.get("data", {})
                code = data.get("code", -1)
                
                if code == self.STATUS_SUCCESS:
                    # 登录成功 - 尝试多种方式获取cookie
                    print(f"[调试] 登录成功，data keys: {list(data.keys())}")
                    
                    # 方式1：从data.cookie_info获取
                    cookie_info = data.get("cookie_info", {})
                    cookies = cookie_info.get("cookies", [])
                    
                    if cookies:
                        print(f"[调试] 从cookie_info获取到 {len(cookies)} 个cookie")
                        return LoginResult(
                            success=True,
                            sessdata=cookies[0]["value"] if len(cookies) > 0 else "",
                            bili_jct=cookies[1]["value"] if len(cookies) > 1 else "",
                            dede_user_id=cookies[2]["value"] if len(cookies) > 2 else "",
                            dede_user_id_ckmd5=cookies[3]["value"] if len(cookies) > 3 else "",
                            message="登录成功",
                        )
                    
                    # 方式2：从响应头Set-Cookie获取
                    all_cookies = result.get("_cookies", {})
                    if all_cookies:
                        print(f"[调试] 从响应头获取到cookie: {list(all_cookies.keys())}")
                        return LoginResult(
                            success=True,
                            sessdata=all_cookies.get("SESSDATA", ""),
                            bili_jct=all_cookies.get("bili_jct", ""),
                            dede_user_id=all_cookies.get("DedeUserID", ""),
                            dede_user_id_ckmd5=all_cookies.get("DedeUserID__ckMd5", ""),
                            message="登录成功",
                        )
                    
                    # 方式3：检查是否有其他字段
                    print(f"[调试] 完整data: {data}")
                    return LoginResult(
                        success=False,
                        message="登录成功但未获取到cookie，请重试",
                    )
                elif code == self.STATUS_EXPIRED:
                    return LoginResult(success=False, message="二维码已过期，请重新获取")
                elif code == self.STATUS_SCANNED:
                    print("已扫码，请在手机上确认登录...")
                elif code == self.STATUS_NOT_SCANNED:
                    # 等待扫码
                    pass
                else:
                    return LoginResult(success=False, message=f"未知状态: {code}")
                
                # 等待1秒再轮询
                time.sleep(1)
            
            return LoginResult(success=False, message="登录超时")
            
        except Exception as e:
            return LoginResult(success=False, message=f"登录失败: {str(e)}")
    
    def login_with_browser(self) -> LoginResult:
        """
        使用浏览器打开二维码（可选）
        
        Returns:
            LoginResult对象
        """
        try:
            import webbrowser
            
            # 获取二维码URL
            url, key = self.get_qrcode_url()
            
            # 打开浏览器
            webbrowser.open(url)
            
            print("已在浏览器中打开二维码链接")
            print("请使用B站APP扫描浏览器中的二维码")
            
            # 轮询扫码状态
            start_time = time.time()
            while time.time() - start_time < self.timeout:
                result = self.poll_scan_status()
                # 状态码在 data.code 中，不是顶层 code
                data = result.get("data", {})
                code = data.get("code", -1)
                
                if code == self.STATUS_SUCCESS:
                    cookie_info = data.get("cookie_info", {})
                    cookies = cookie_info.get("cookies", [])
                    
                    if cookies:
                        return LoginResult(
                            success=True,
                            sessdata=cookies[0]["value"] if len(cookies) > 0 else "",
                            bili_jct=cookies[1]["value"] if len(cookies) > 1 else "",
                            dede_user_id=cookies[2]["value"] if len(cookies) > 2 else "",
                            dede_user_id_ckmd5=cookies[3]["value"] if len(cookies) > 3 else "",
                            message="登录成功",
                        )
                    
                    all_cookies = result.get("_cookies", {})
                    if all_cookies:
                        return LoginResult(
                            success=True,
                            sessdata=all_cookies.get("SESSDATA", ""),
                            bili_jct=all_cookies.get("bili_jct", ""),
                            dede_user_id=all_cookies.get("DedeUserID", ""),
                            dede_user_id_ckmd5=all_cookies.get("DedeUserID__ckMd5", ""),
                            message="登录成功",
                        )
                    
                    print(f"[调试] data keys: {list(data.keys())}")
                    print(f"[调试] 完整data: {data}")
                    return LoginResult(
                        success=False,
                        message="登录成功但未获取到cookie",
                    )
                elif code == self.STATUS_EXPIRED:
                    return LoginResult(success=False, message="二维码已过期，请重新获取")
                elif code == self.STATUS_SCANNED:
                    print("已扫码，请在手机上确认登录...")
                
                time.sleep(1)
            
            return LoginResult(success=False, message="登录超时")
            
        except Exception as e:
            return LoginResult(success=False, message=f"登录失败: {str(e)}")


def login_interactive() -> LoginResult:
    """
    交互式登录
    
    Returns:
        LoginResult对象
    """
    loginer = QRCodeLogin()
    
    print("=" * 50)
    print("B站二维码登录")
    print("=" * 50)
    
    result = loginer.login(display_qrcode=True)
    
    if result.success:
        print("\n" + "=" * 50)
        print("登录成功！")
        print("=" * 50)
        print(f"SESSDATA: {result.sessdata[:20]}...")
        print(f"bili_jct: {result.bili_jct[:20]}...")
        print(f"DedeUserID: {result.dede_user_id}")
    else:
        print(f"\n登录失败: {result.message}")
    
    return result


if __name__ == "__main__":
    # 测试登录
    result = login_interactive()
