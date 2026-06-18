"""
Gaia 验证流程模块
处理B站风控验证
"""

import httpx
import time
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class VerifyStatus(Enum):
    """验证状态"""
    SUCCESS = "success"
    NEED_CAPTCHA = "need_captcha"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class GaiaResult:
    """Gaia验证结果"""
    status: VerifyStatus
    grisk_id: Optional[str] = None
    message: str = ""


class GaiaVerifier:
    """
    Gaia 验证器
    
    流程：
    1. 请求API返回-352
    2. POST /x/gaia-vgate/v1/register 获取极验challenge
    3. 完成极验验证（滑块/点选）
    4. POST /x/gaia-vgate/v1/validate 获取grisk_id
    5. 重新请求API
    """
    
    # API端点
    REGISTER_URL = "https://api.bilibili.com/x/gaia-vgate/v1/register"
    VALIDATE_URL = "https://api.bilibili.com/x/gaia-vgate/v1/validate"
    
    # 风控错误码
    RISK_CODE = -352
    
    def __init__(self, cookies: Dict[str, str]):
        """
        初始化验证器
        
        Args:
            cookies: Cookie字典
        """
        self.cookies = cookies
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.bilibili.com/",
            "Origin": "https://www.bilibili.com",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/x-www-form-urlencoded",
        }
    
    def register(self, risk_params) -> Tuple[bool, Dict]:
        """
        注册风控验证（对标 BHYG: 直接传 riskParams dict）
        """
        data = risk_params if isinstance(risk_params, dict) else {"v_voucher": risk_params}
        
        with httpx.Client() as client:
            response = client.post(
                self.REGISTER_URL,
                data=data,
                headers=self.headers,
                cookies=self.cookies,
            )
            result = response.json()
            if result.get("code") == 0:
                return True, result["data"]
            return False, result

    def validate_direct(self, token: str, csrf: str) -> Tuple[bool, Dict]:
        """empty 类型直接验证（token + csrf）"""
        data = {"token": token, "csrf": csrf}
        with httpx.Client() as client:
            response = client.post(
                self.VALIDATE_URL,
                data=data,
                headers=self.headers,
                cookies=self.cookies,
            )
            result = response.json()
            if result.get("code") == 0:
                return True, result.get("data", {})
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
                self.VALIDATE_URL,
                data=data,
                headers=self.headers,
                cookies=self.cookies,
            )
            
            result = response.json()
            
            if result.get("code") == 0:
                return True, result["data"]
            else:
                return False, result
    
    def check_risk_response(self, response: Dict) -> bool:
        """
        检查是否是风控响应
        
        Args:
            response: API响应
            
        Returns:
            是否是风控响应
        """
        return response.get("code") == self.RISK_CODE
    
    def get_v_voucher(self, response: Dict) -> Optional[str]:
        """
        从风控响应中获取v_voucher
        
        Args:
            response: 风控响应
            
        Returns:
            v_voucher字符串
        """
        data = response.get("data", {})
        return data.get("v_voucher")
    
    def get_grisk_id(self, response: Dict) -> Optional[str]:
        """
        从验证响应中获取grisk_id
        
        Args:
            response: 验证响应
            
        Returns:
            grisk_id字符串
        """
        data = response.get("data", {})
        return data.get("grisk_id")
    
    def verify_with_captcha(
        self,
        v_voucher: str,
        captcha_solver=None,
    ) -> GaiaResult:
        """
        执行完整的验证流程
        
        Args:
            v_voucher: 验证凭证
            captcha_solver: 验证码求解器（可选）
            
        Returns:
            GaiaResult对象
        """
        # 1. 注册验证
        success, data = self.register(v_voucher)
        if not success:
            return GaiaResult(
                status=VerifyStatus.FAILED,
                message=f"注册验证失败: {data.get('message', '未知错误')}",
            )
        
        # 获取极验challenge
        challenge = data.get("challenge")
        if not challenge:
            return GaiaResult(
                status=VerifyStatus.FAILED,
                message="未获取到challenge",
            )
        
        # 2. 处理验证码
        if captcha_solver:
            # 使用验证码求解器
            try:
                captcha_result = captcha_solver.solve(challenge)
                validate = captcha_result.get("validate")
                seccode = captcha_result.get("seccode")
            except Exception as e:
                return GaiaResult(
                    status=VerifyStatus.FAILED,
                    message=f"验证码求解失败: {str(e)}",
                )
        else:
            # 需要手动处理验证码
            return GaiaResult(
                status=VerifyStatus.NEED_CAPTCHA,
                message=f"需要手动完成验证码，challenge: {challenge}",
            )
        
        # 3. 提交验证结果
        success, result_data = self.validate(challenge, validate, seccode)
        if not success:
            return GaiaResult(
                status=VerifyStatus.FAILED,
                message=f"验证失败: {result_data.get('message', '未知错误')}",
            )
        
        # 4. 获取grisk_id
        grisk_id = self.get_grisk_id({"data": result_data})
        
        return GaiaResult(
            status=VerifyStatus.SUCCESS,
            grisk_id=grisk_id,
            message="验证成功",
        )
    
