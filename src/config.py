"""
配置管理模块
负责加载、保存和验证配置
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class UserConfig:
    """用户配置"""
    sessdata: str = ""
    bili_jct: str = ""
    dede_user_id: str = ""
    dede_user_id_ckmd5: str = ""


@dataclass
class EventConfig:
    """活动配置"""
    project_id: int = 0
    screen_id: int = 0
    sku_id: int = 0
    count: int = 1
    viewer_id: int = 0
    hot_project: bool = False


@dataclass
class StrategyConfig:
    """策略配置"""
    retry_count: int = 3
    retry_delay_ms: int = 100
    concurrency: int = 1
    advance_ms: int = 0
    timeout_seconds: int = 10
    after_sale_begin_delay: float = 0.2
    order_interval: float = 0.3
    delta: float = 0.05
    enable_stock_check: bool = True
    stock_check_available_delay: float = 0


@dataclass
class ProxyConfig:
    """代理配置"""
    enabled: bool = False
    http: str = ""
    https: str = ""
    socks5: str = ""


@dataclass
class LoggingConfig:
    """日志配置"""
    level: str = "INFO"
    save_to_file: bool = True
    file_path: str = "logs/ticket_grabber.log"
    verbose: bool = False


@dataclass
class NotificationConfig:
    """通知配置"""
    enabled: bool = False


@dataclass
class Config:
    """主配置类"""
    user: UserConfig = field(default_factory=UserConfig)
    event: EventConfig = field(default_factory=EventConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    notification: NotificationConfig = field(default_factory=NotificationConfig)


class ConfigManager:
    """
    配置管理器
    
    功能：
    - 加载配置文件
    - 保存配置文件
    - 验证配置完整性
    - 提供默认配置
    """
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        初始化配置管理器
        
        Args:
            config_path: 配置文件路径
        """
        self.config_path = Path(config_path)
        self.config: Optional[Config] = None
        
    def load(self) -> Config:
        """
        加载配置文件
        
        Returns:
            Config对象
            
        Raises:
            FileNotFoundError: 配置文件不存在
            yaml.YAMLError: 配置文件格式错误
        """
        if not self.config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {self.config_path}")
        
        with open(self.config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        
        if data is None:
            data = {}
        
        # 解析配置
        self.config = Config(
            user=UserConfig(**data.get("user", {})),
            event=EventConfig(**data.get("event", {})),
            strategy=StrategyConfig(**data.get("strategy", {})),
            proxy=ProxyConfig(**data.get("proxy", {})),
            logging=LoggingConfig(**data.get("logging", {})),
            notification=NotificationConfig(**data.get("notification", {})),
        )
        
        return self.config
    
    def save(self, config: Optional[Config] = None) -> None:
        """
        保存配置文件
        
        Args:
            config: 要保存的配置，如果不提供则保存当前配置
        """
        if config is None:
            config = self.config
        
        if config is None:
            raise ValueError("没有可保存的配置")
        
        # 转换为字典
        data = {
            "user": {
                "sessdata": config.user.sessdata,
                "bili_jct": config.user.bili_jct,
                "dede_user_id": config.user.dede_user_id,
                "dede_user_id_ckmd5": config.user.dede_user_id_ckmd5,
            },
            "event": {
                "project_id": config.event.project_id,
                "screen_id": config.event.screen_id,
                "sku_id": config.event.sku_id,
                "count": config.event.count,
                "viewer_id": config.event.viewer_id,
            },
            "strategy": {
                "retry_count": config.strategy.retry_count,
                "retry_delay_ms": config.strategy.retry_delay_ms,
                "concurrency": config.strategy.concurrency,
                "advance_ms": config.strategy.advance_ms,
                "timeout_seconds": config.strategy.timeout_seconds,
            },
            "proxy": {
                "enabled": config.proxy.enabled,
                "http": config.proxy.http,
                "https": config.proxy.https,
                "socks5": config.proxy.socks5,
            },
            "logging": {
                "level": config.logging.level,
                "save_to_file": config.logging.save_to_file,
                "file_path": config.logging.file_path,
                "verbose": config.logging.verbose,
            },
            "notification": {
                "enabled": config.notification.enabled,
            },
        }
        
        # 确保目录存在
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 保存配置
        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
    
    def validate(self, config: Optional[Config] = None) -> list:
        """
        验证配置完整性
        
        Args:
            config: 要验证的配置，如果不提供则验证当前配置
            
        Returns:
            错误信息列表，空列表表示验证通过
        """
        if config is None:
            config = self.config
        
        if config is None:
            return ["配置未加载"]
        
        errors = []
        
        # 验证用户配置
        if not config.user.sessdata:
            errors.append("缺少用户配置: sessdata")
        if not config.user.bili_jct:
            errors.append("缺少用户配置: bili_jct")
        if not config.user.dede_user_id:
            errors.append("缺少用户配置: dede_user_id")
        
        # 验证活动配置
        if config.event.project_id <= 0:
            errors.append("缺少活动配置: project_id")
        if config.event.screen_id <= 0:
            errors.append("缺少活动配置: screen_id")
        if config.event.sku_id <= 0:
            errors.append("缺少活动配置: sku_id")
        if config.event.count <= 0:
            errors.append("购票数量必须大于0")
        
        # 验证策略配置
        if config.strategy.retry_count < 0:
            errors.append("重试次数不能为负数")
        if config.strategy.retry_delay_ms < 0:
            errors.append("重试间隔不能为负数")
        if config.strategy.concurrency <= 0:
            errors.append("并发数必须大于0")
        
        return errors
    
    def get_default_config(self) -> Config:
        """
        获取默认配置
        
        Returns:
            默认Config对象
        """
        return Config()
    
    def create_example_config(self) -> None:
        """
        创建示例配置文件
        """
        example_path = self.config_path.with_suffix(".yaml.example")
        config = self.get_default_config()
        
        # 保存示例配置
        with open(example_path, "w", encoding="utf-8") as f:
            yaml.dump(
                {
                    "user": {
                        "sessdata": "你的SESSDATA",
                        "bili_jct": "你的bili_jct",
                        "dede_user_id": "你的DedeUserID",
                        "dede_user_id_ckmd5": "你的DedeUserID__ckMd5",
                    },
                    "event": {
                        "project_id": 12345,
                        "screen_id": 67890,
                        "sku_id": 111,
                        "count": 1,
                        "viewer_id": 0,
                    },
                    "strategy": {
                        "retry_count": 3,
                        "retry_delay_ms": 100,
                        "concurrency": 1,
                        "advance_ms": 500,
                        "timeout_seconds": 10,
                    },
                    "proxy": {
                        "enabled": False,
                        "http": "",
                        "https": "",
                        "socks5": "",
                    },
                    "logging": {
                        "level": "INFO",
                        "save_to_file": True,
                        "file_path": "logs/ticket_grabber.log",
                        "verbose": False,
                    },
                    "notification": {
                        "enabled": False,
                    },
                },
                f,
                default_flow_style=False,
                allow_unicode=True,
            )
        
        print(f"示例配置文件已创建: {example_path}")


# 便捷的全局实例
config_manager = ConfigManager()


def load_config(config_path: str = "config.yaml") -> Config:
    """
    加载配置的便捷函数
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        Config对象
    """
    manager = ConfigManager(config_path)
    return manager.load()


def save_config(config: Config, config_path: str = "config.yaml") -> None:
    """
    保存配置的便捷函数
    
    Args:
        config: 配置对象
        config_path: 配置文件路径
    """
    manager = ConfigManager(config_path)
    manager.save(config)
