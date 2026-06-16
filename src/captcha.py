"""
验证码识别服务模块
支持极验滑块、点选验证码
"""

import time
import httpx
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class CaptchaType(Enum):
    """验证码类型"""
    GEETEST_SLIDE = "geetest_slide"      # 极验滑块
    GEETEST_CLICK = "geetest_click"      # 极验点选
    GEETEST_MANNEKIN = "geetest_mannekin" # 极验空间推理
    UNKNOWN = "unknown"


@dataclass
class CaptchaResult:
    """验证码识别结果"""
    success: bool
    validate: str = ""
    seccode: str = ""
    message: str = ""


class CaptchaService:
    """
    验证码识别服务
    
    支持：
    1. 第三方识别服务API
    2. 本地识别（需要额外模型）
    """
    
    # 第三方识别服务API（示例）
    THIRD_PARTY_APIS = {
        "ttshitu": {
            "url": "http://api.ttshitu.com/predict",
            "username": "",
            "password": "",
        },
        "yunsu": {
            "url": "http://api.yunsue.com/recognize",
            "api_key": "",
        },
    }
    
    def __init__(self, service: str = "manual", api_key: str = ""):
        """
        初始化验证码服务
        
        Args:
            service: 识别服务名称（manual/ttshitu/yunsu）
            api_key: API密钥
        """
        self.service = service
        self.api_key = api_key
    
    def recognize_slide(
        self,
        bg_image: str,
        slice_image: str,
        challenge: str,
    ) -> CaptchaResult:
        """
        识别滑块验证码
        
        Args:
            bg_image: 背景图片URL或Base64
            slice_image: 滑块图片URL或Base64
            challenge: 极验challenge
            
        Returns:
            CaptchaResult对象
        """
        if self.service == "manual":
            return self._manual_slide(bg_image, slice_image, challenge)
        elif self.service == "ttshitu":
            return self._ttshitu_slide(bg_image, slice_image, challenge)
        else:
            return CaptchaResult(
                success=False,
                message=f"不支持的识别服务: {self.service}",
            )
    
    def recognize_click(
        self,
        image: str,
        question: str,
        challenge: str,
    ) -> CaptchaResult:
        """
        识别点选验证码
        
        Args:
            image: 验证码图片URL或Base64
            question: 点选提示（如"请依次点击：猫、狗、鸟"）
            challenge: 极验challenge
            
        Returns:
            CaptchaResult对象
        """
        if self.service == "manual":
            return self._manual_click(image, question, challenge)
        else:
            return CaptchaResult(
                success=False,
                message=f"不支持的识别服务: {self.service}",
            )
    
    def _manual_slide(
        self,
        bg_image: str,
        slice_image: str,
        challenge: str,
    ) -> CaptchaResult:
        """手动滑块识别"""
        print("\n" + "=" * 50)
        print("  滑块验证码")
        print("=" * 50)
        print(f"\n请完成滑块验证")
        print(f"背景图片: {bg_image[:50]}...")
        print(f"滑块图片: {slice_image[:50]}...")
        
        try:
            distance = int(input("\n请输入滑块距离（像素）: "))
            
            # 生成validate（简化版本，实际需要调用极验API）
            import hashlib
            validate = hashlib.md5(f"{challenge}:{distance}".encode()).hexdigest()
            seccode = f"{validate}|jordan"
            
            return CaptchaResult(
                success=True,
                validate=validate,
                seccode=seccode,
                message="手动识别完成",
            )
        except ValueError:
            return CaptchaResult(
                success=False,
                message="输入无效",
            )
    
    def _manual_click(
        self,
        image: str,
        question: str,
        challenge: str,
    ) -> CaptchaResult:
        """手动点选识别"""
        print("\n" + "=" * 50)
        print("  点选验证码")
        print("=" * 50)
        print(f"\n提示: {question}")
        print(f"图片: {image[:50]}...")
        
        try:
            positions = input("\n请输入点击位置（格式: x1,y1;x2,y2;x3,y3）: ")
            
            # 生成validate
            import hashlib
            validate = hashlib.md5(f"{challenge}:{positions}".encode()).hexdigest()
            seccode = f"{validate}|jordan"
            
            return CaptchaResult(
                success=True,
                validate=validate,
                seccode=seccode,
                message="手动识别完成",
            )
        except Exception as e:
            return CaptchaResult(
                success=False,
                message=f"输入无效: {e}",
            )
    
    def _ttshitu_slide(
        self,
        bg_image: str,
        slice_image: str,
        challenge: str,
    ) -> CaptchaResult:
        """使用图图识别服务"""
        api_config = self.THIRD_PARTY_APIS.get("ttshitu", {})
        url = api_config.get("url", "")
        
        if not url:
            return CaptchaResult(
                success=False,
                message="图图识别服务未配置",
            )
        
        try:
            # 发送识别请求
            data = {
                "username": api_config.get("username", ""),
                "password": api_config.get("password", ""),
                "typeid": 27,  # 滑块类型
                "image": bg_image,
            }
            
            with httpx.Client(timeout=30) as client:
                response = client.post(url, json=data)
                result = response.json()
                
                if result.get("success"):
                    distance = result.get("data", {}).get("result", 0)
                    
                    # 生成validate
                    import hashlib
                    validate = hashlib.md5(f"{challenge}:{distance}".encode()).hexdigest()
                    seccode = f"{validate}|jordan"
                    
                    return CaptchaResult(
                        success=True,
                        validate=validate,
                        seccode=seccode,
                        message="识别成功",
                    )
                else:
                    return CaptchaResult(
                        success=False,
                        message=result.get("message", "识别失败"),
                    )
                    
        except Exception as e:
            return CaptchaResult(
                success=False,
                message=f"识别请求失败: {e}",
            )


class GeetestHandler:
    """
    极验验证码处理器
    
    处理B站的极验验证码流程
    """
    
    # B站极验API
    GEETEST_REGISTER_URL = "https://api.bilibili.com/x/gaia-vgate/v1/register"
    GEETEST_VALIDATE_URL = "https://api.bilibili.com/x/gaia-vgate/v1/validate"
    
    def __init__(self, cookies: Dict[str, str], captcha_service: Optional[CaptchaService] = None):
        """
        初始化极验处理器
        
        Args:
            cookies: Cookie字典
            captcha_service: 验证码识别服务
        """
        self.cookies = cookies
        self.captcha_service = captcha_service or CaptchaService(service="manual")
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.bilibili.com/",
            "Origin": "https://www.bilibili.com",
        }
    
    def register(self, v_voucher: str) -> Tuple[bool, Dict]:
        """
        注册验证
        
        Args:
            v_voucher: 验证凭证
            
        Returns:
            (是否成功, 响应数据)
        """
        data = {"v_voucher": v_voucher}
        
        with httpx.Client() as client:
            response = client.post(
                self.GEETEST_REGISTER_URL,
                data=data,
                headers=self.headers,
                cookies=self.cookies,
            )
            result = response.json()
            
            if result.get("code") == 0:
                return True, result["data"]
            else:
                return False, result
    
    def validate(
        self,
        challenge: str,
        validate: str,
        seccode: str,
    ) -> Tuple[bool, Dict]:
        """
        提交验证结果
        
        Args:
            challenge: 极验challenge
            validate: 极验validate
            seccode: 极验seccode
            
        Returns:
            (是否成功, 响应数据)
        """
        data = {
            "challenge": challenge,
            "validate": validate,
            "seccode": seccode,
        }
        
        with httpx.Client() as client:
            response = client.post(
                self.GEETEST_VALIDATE_URL,
                data=data,
                headers=self.headers,
                cookies=self.cookies,
            )
            result = response.json()
            
            if result.get("code") == 0:
                return True, result["data"]
            else:
                return False, result
    
    def handle_captcha(self, v_voucher: str) -> Dict:
        """
        处理验证码
        
        Args:
            v_voucher: 验证凭证
            
        Returns:
            处理结果
        """
        # 1. 注册验证
        success, data = self.register(v_voucher)
        if not success:
            return {
                "success": False,
                "message": f"注册验证失败: {data.get('message', '未知错误')}",
            }
        
        # 获取极验信息
        challenge = data.get("challenge", "")
        gt = data.get("gt", "")
        captcha_type = data.get("type", "")
        
        # 2. 根据验证码类型处理
        if captcha_type == "1":
            # 滑块验证码
            bg_image = data.get("bg", "")
            slice_image = data.get("slice", "")
            
            result = self.captcha_service.recognize_slide(
                bg_image=bg_image,
                slice_image=slice_image,
                challenge=challenge,
            )
        elif captcha_type == "2":
            # 点选验证码
            image = data.get("img", "")
            question = data.get("question", "")
            
            result = self.captcha_service.recognize_click(
                image=image,
                question=question,
                challenge=challenge,
            )
        else:
            return {
                "success": False,
                "message": f"不支持的验证码类型: {captcha_type}",
            }
        
        if not result.success:
            return {
                "success": False,
                "message": f"验证码识别失败: {result.message}",
            }
        
        # 3. 提交验证结果
        success, validate_data = self.validate(
            challenge=challenge,
            validate=result.validate,
            seccode=result.seccode,
        )
        
        if success:
            return {
                "success": True,
                "grisk_id": validate_data.get("grisk_id", ""),
                "message": "验证成功",
            }
        else:
            return {
                "success": False,
                "message": f"验证提交失败: {validate_data.get('message', '未知错误')}",
            }


def create_captcha_service(service: str = "manual", api_key: str = "") -> CaptchaService:
    """创建验证码服务"""
    return CaptchaService(service=service, api_key=api_key)


def create_geetest_handler(
    cookies: Dict[str, str],
    captcha_service: Optional[CaptchaService] = None,
) -> GeetestHandler:
    """创建极验处理器"""
    return GeetestHandler(cookies=cookies, captcha_service=captcha_service)
