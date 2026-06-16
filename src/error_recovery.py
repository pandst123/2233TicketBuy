"""
错误恢复模块
处理网络错误、API错误等异常情况
"""

import time
import httpx
from typing import Optional, Callable, Any
from functools import wraps
from .logger import logger


class RetryError(Exception):
    """重试错误"""
    pass


class NetworkError(Exception):
    """网络错误"""
    pass


class APIError(Exception):
    """API错误"""
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"API错误 [{code}]: {message}")


def retry_on_error(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,),
):
    """
    重试装饰器
    
    Args:
        max_retries: 最大重试次数
        delay: 初始延迟时间（秒）
        backoff: 延迟倍数
        exceptions: 需要重试的异常类型
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            retries = 0
            current_delay = delay
            
            while True:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    retries += 1
                    if retries > max_retries:
                        logger.error(f"重试{max_retries}次后仍然失败: {e}")
                        raise RetryError(f"重试{max_retries}次后仍然失败: {e}")
                    
                    logger.warning(f"操作失败，{current_delay}秒后重试 ({retries}/{max_retries}): {e}")
                    time.sleep(current_delay)
                    current_delay *= backoff
            
        return wrapper
    return decorator


def safe_request(
    method: str,
    url: str,
    max_retries: int = 3,
    timeout: float = 10.0,
    **kwargs,
) -> dict:
    """
    安全的HTTP请求
    
    Args:
        method: 请求方法
        url: 请求URL
        max_retries: 最大重试次数
        timeout: 超时时间
        **kwargs: 其他请求参数
        
    Returns:
        响应数据
        
    Raises:
        NetworkError: 网络错误
        APIError: API错误
    """
    retries = 0
    delay = 1.0
    
    while True:
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.request(method=method, url=url, **kwargs)
                
                # 检查HTTP状态码
                if response.status_code != 200:
                    raise NetworkError(f"HTTP错误: {response.status_code}")
                
                # 解析JSON
                result = response.json()
                
                # 检查API状态码
                code = result.get("code", -1)
                if code != 0:
                    message = result.get("message", result.get("msg", "未知错误"))
                    raise APIError(code=code, message=message)
                
                return result
                
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            retries += 1
            if retries > max_retries:
                raise NetworkError(f"网络错误，重试{max_retries}次后仍然失败: {e}")
            
            logger.warning(f"网络错误，{delay}秒后重试 ({retries}/{max_retries}): {e}")
            time.sleep(delay)
            delay *= 2
            
        except APIError:
            raise
            
        except Exception as e:
            retries += 1
            if retries > max_retries:
                raise NetworkError(f"请求错误，重试{max_retries}次后仍然失败: {e}")
            
            logger.warning(f"请求错误，{delay}秒后重试 ({retries}/{max_retries}): {e}")
            time.sleep(delay)
            delay *= 2


class ErrorRecovery:
    """
    错误恢复管理器
    
    处理各种错误情况
    """
    
    def __init__(self):
        self.error_count = 0
        self.max_errors = 10
        self.last_error_time = 0
        self.cooldown_period = 60  # 冷却时间（秒）
    
    def should_continue(self) -> bool:
        """
        检查是否应该继续
        
        Returns:
            是否应该继续
        """
        # 检查错误次数
        if self.error_count >= self.max_errors:
            logger.error(f"错误次数过多 ({self.error_count})，停止操作")
            return False
        
        # 检查冷却时间
        current_time = time.time()
        if current_time - self.last_error_time < self.cooldown_period:
            remaining = self.cooldown_period - (current_time - self.last_error_time)
            logger.warning(f"冷却中，{remaining:.0f}秒后继续")
            time.sleep(remaining)
        
        return True
    
    def record_error(self, error: Exception) -> None:
        """
        记录错误
        
        Args:
            error: 异常对象
        """
        self.error_count += 1
        self.last_error_time = time.time()
        logger.error(f"错误 ({self.error_count}/{self.max_errors}): {error}")
    
    def reset(self) -> None:
        """重置错误计数"""
        self.error_count = 0
        self.last_error_time = 0
    
    def handle_network_error(self, error: NetworkError) -> bool:
        """
        处理网络错误
        
        Args:
            error: 网络错误
            
        Returns:
            是否应该重试
        """
        self.record_error(error)
        
        if not self.should_continue():
            return False
        
        # 网络错误通常可以重试
        return True
    
    def handle_api_error(self, error: APIError) -> bool:
        """
        处理API错误
        
        Args:
            error: API错误
            
        Returns:
            是否应该重试
        """
        self.record_error(error)
        
        # 特定错误码处理
        if error.code == -352:
            # 风控错误，需要验证码
            logger.warning("触发风控，需要验证码")
            return True
        elif error.code == -412:
            # 请求过于频繁
            logger.warning("请求过于频繁，等待冷却")
            time.sleep(5)
            return True
        elif error.code == 100001:
            # 未登录
            logger.error("未登录")
            return False
        else:
            # 其他错误
            if not self.should_continue():
                return False
            return True


# 全局错误恢复实例
error_recovery = ErrorRecovery()


def get_error_recovery() -> ErrorRecovery:
    """获取错误恢复实例"""
    return error_recovery
