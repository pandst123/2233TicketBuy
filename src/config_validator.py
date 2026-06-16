"""
配置验证模块
验证配置文件的完整性和正确性
"""

from typing import List, Tuple
from .config import Config


class ConfigValidator:
    """
    配置验证器
    
    验证配置文件的完整性和正确性
    """
    
    @staticmethod
    def validate(config: Config) -> Tuple[bool, List[str]]:
        """
        验证配置
        
        Args:
            config: 配置对象
            
        Returns:
            (是否有效, 错误信息列表)
        """
        errors = []
        
        # 验证用户配置
        user_errors = ConfigValidator._validate_user(config)
        errors.extend(user_errors)
        
        # 验证活动配置
        event_errors = ConfigValidator._validate_event(config)
        errors.extend(event_errors)
        
        # 验证策略配置
        strategy_errors = ConfigValidator._validate_strategy(config)
        errors.extend(strategy_errors)
        
        return len(errors) == 0, errors
    
    @staticmethod
    def _validate_user(config: Config) -> List[str]:
        """验证用户配置"""
        errors = []
        
        if not config.user.sessdata:
            errors.append("缺少用户配置: sessdata")
        
        if not config.user.bili_jct:
            errors.append("缺少用户配置: bili_jct")
        
        if not config.user.dede_user_id:
            errors.append("缺少用户配置: dede_user_id")
        
        return errors
    
    @staticmethod
    def _validate_event(config: Config) -> List[str]:
        """验证活动配置"""
        errors = []
        
        if config.event.project_id <= 0:
            errors.append("缺少活动配置: project_id")
        
        if config.event.screen_id <= 0:
            errors.append("缺少活动配置: screen_id")
        
        if config.event.sku_id <= 0:
            errors.append("缺少活动配置: sku_id")
        
        if config.event.count <= 0:
            errors.append("购票数量必须大于0")
        
        return errors
    
    @staticmethod
    def _validate_strategy(config: Config) -> List[str]:
        """验证策略配置"""
        errors = []
        
        if config.strategy.retry_count < 0:
            errors.append("重试次数不能为负数")
        
        if config.strategy.retry_delay_ms < 0:
            errors.append("重试间隔不能为负数")
        
        if config.strategy.concurrency <= 0:
            errors.append("并发数必须大于0")
        
        if config.strategy.timeout_seconds <= 0:
            errors.append("请求超时必须大于0")
        
        return errors
    
    @staticmethod
    def validate_for_grab(config: Config) -> Tuple[bool, List[str]]:
        """
        验证配置是否可以开始抢票
        
        Args:
            config: 配置对象
            
        Returns:
            (是否有效, 错误信息列表)
        """
        errors = []
        
        # 验证用户配置
        if not config.user.sessdata:
            errors.append("未登录，请先登录")
        
        # 验证活动配置
        if config.event.project_id <= 0:
            errors.append("未选择活动，请先选择活动")
        
        if config.event.screen_id <= 0:
            errors.append("未选择场次，请先选择场次")
        
        if config.event.sku_id <= 0:
            errors.append("未选择票档，请先选择票档")
        
        if config.event.count <= 0:
            errors.append("购票数量必须大于0")
        
        return len(errors) == 0, errors


def validate_config(config: Config) -> Tuple[bool, List[str]]:
    """
    验证配置的便捷函数
    
    Args:
        config: 配置对象
        
    Returns:
        (是否有效, 错误信息列表)
    """
    return ConfigValidator.validate(config)


def validate_for_grab(config: Config) -> Tuple[bool, List[str]]:
    """
    验证配置是否可以开始抢票的便捷函数
    
    Args:
        config: 配置对象
        
    Returns:
        (是否有效, 错误信息列表)
    """
    return ConfigValidator.validate_for_grab(config)
