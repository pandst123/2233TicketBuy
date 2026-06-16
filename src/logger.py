"""
日志模块
提供统一的日志记录功能
"""

import logging
import os
from datetime import datetime
from pathlib import Path


class Logger:
    """
    日志管理器
    
    功能：
    - 控制台输出
    - 文件记录
    - 不同级别日志
    """
    
    def __init__(self, name: str = "2233TicketBuy", log_dir: str = "logs"):
        """
        初始化日志管理器
        
        Args:
            name: 日志名称
            log_dir: 日志目录
        """
        self.name = name
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        # 创建logger
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        
        # 避免重复添加handler
        if not self.logger.handlers:
            self._setup_handlers()
    
    def _setup_handlers(self):
        """设置日志处理器（参考 BHYG loguru 风格）"""
        # BHYG 格式: YYYY-MM-DD HH:mm:ss.SSS | LEVEL | message
        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_format = logging.Formatter(
            '%(asctime)s.%(msecs)03d | %(levelname)-7s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(console_format)
        self.logger.addHandler(console_handler)
        
        # 文件处理器（更详细）
        log_file = self.log_dir / f"{self.name}_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_format = logging.Formatter(
            '%(asctime)s.%(msecs)03d | %(levelname)-7s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_format)
        self.logger.addHandler(file_handler)
    
    def debug(self, message: str):
        """调试日志"""
        self.logger.debug(message)
    
    def info(self, message: str):
        """信息日志"""
        self.logger.info(message)
    
    def warning(self, message: str):
        """警告日志"""
        self.logger.warning(message)
    
    def error(self, message: str):
        """错误日志"""
        self.logger.error(message)
    
    def success(self, message: str):
        """成功日志"""
        self.logger.info(f"[OK] {message}")
    
    def fail(self, message: str):
        """失败日志"""
        self.logger.error(f"[FAIL] {message}")


# 全局日志实例
logger = Logger()
