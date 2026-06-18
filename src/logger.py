"""
日志模块
提供统一的日志记录功能，支持 rich 彩色输出
"""

import logging
import os
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.theme import Theme
from rich.logging import RichHandler
from rich.text import Text


# Rich 主题颜色: time=蓝, info=绿, warning=黄, error=红
RICH_THEME = Theme({
    "logging.level.info": "green",
    "logging.level.warning": "yellow",
    "logging.level.error": "red bold",
    "logging.level.debug": "dim",
    "time": "blue",
})


class MillisecondRichHandler(RichHandler):
    """RichHandler 子类：时间戳精确到毫秒（3位小数）"""
    
    def get_time_text(self, record):
        """覆盖时间格式化，精确到毫秒"""
        dt = datetime.fromtimestamp(record.created)
        ts = dt.strftime('%H:%M:%S') + f'.{record.msecs:03d}'
        return Text(f"[{ts}]", style="log.time")


class Logger:
    """
    日志管理器
    
    功能：
    - 控制台彩色输出（rich）
    - 文件记录
    - 不同级别的日志
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
        
        # Rich 控制台
        self.console = Console(theme=RICH_THEME)
        
        # 创建logger
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        
        # 避免重复添加handler
        if not self.logger.handlers:
            self._setup_handlers()
    
    def _setup_handlers(self):
        """设置日志处理器"""
        # Rich 控制台处理器（彩色，毫秒精度）
        console_handler = MillisecondRichHandler(
            console=self.console,
            show_time=True,
            show_level=True,
            show_path=False,
            rich_tracebacks=True,
        )
        console_handler.setLevel(logging.INFO)
        console_format = logging.Formatter('%(message)s')
        console_handler.setFormatter(console_format)
        self.logger.addHandler(console_handler)
        
        # 文件处理器
        log_file = self.log_dir / f"{self.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
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
        """信息日志（绿色）"""
        self.logger.info(message)
    
    def warning(self, message: str):
        """警告日志（黄色）"""
        self.logger.warning(message)
    
    def error(self, message: str):
        """错误日志（红色）"""
        self.logger.error(message)
    
    def time(self, message: str):
        """时间相关日志（蓝色，带毫秒时间戳）"""
        ts = datetime.now().strftime('%H:%M:%S') + f'.{datetime.now().microsecond // 1000:03d}'
        self.console.print(f"[dim][{ts}][/dim] [time]{message}[/time]")
    
    def success(self, message: str):
        """成功日志（绿色）"""
        self.logger.info(f"[green][OK][/green] {message}")
    
    def fail(self, message: str):
        """失败日志（红色）"""
        self.logger.error(f"[red][FAIL][/red] {message}")

    def hot(self, message: str):
        """Hot项目日志（🔥 前缀，控制台可见 + 写入常规日志）"""
        ts = datetime.now().strftime('%H:%M:%S') + f'.{datetime.now().microsecond // 1000:03d}'
        self.console.print(f"[dim][{ts}][/dim] [bold yellow]🔥 {message}[/bold yellow]")
        self.logger.debug(f"[HOT] {message}")


# 全局日志实例
logger = Logger()
