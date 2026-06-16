"""
监控模块
监控票务状态和开售时间
"""

import time
import threading
from typing import Callable, Optional
from datetime import datetime

from .api_client import BilibiliAPI, ProjectInfo
from .logger import logger


class TicketMonitor:
    """
    票务监控器
    
    功能：
    - 监控开售时间
    - 监控票务状态
    - 触发抢票
    """
    
    def __init__(self, api: BilibiliAPI):
        """
        初始化监控器
        
        Args:
            api: API客户端
        """
        self.api = api
        self._stop_event = threading.Event()
        self._monitor_thread: Optional[threading.Thread] = None
    
    def wait_for_sale(self, project_id: int, advance_ms: int = 500) -> int:
        """
        等待开售时间
        
        Args:
            project_id: 项目ID
            advance_ms: 提前开始时间（毫秒）
            
        Returns:
            开售时间戳
        """
        logger.info(f"获取项目信息: {project_id}")
        project = self.api.get_project_info(project_id)
        
        sale_begin = project.sale_begin
        if sale_begin <= 0:
            logger.warning("未获取到开售时间，立即开始")
            return int(time.time())
        
        advance_seconds = advance_ms / 1000
        target_time = sale_begin - advance_seconds
        
        logger.info(f"项目: {project.name}")
        logger.info(f"开售时间: {datetime.fromtimestamp(sale_begin).strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"提前开始: {advance_ms}ms")
        
        while True:
            current_time = time.time()
            remaining = target_time - current_time
            
            if remaining <= 0:
                logger.success("时间到！开始抢票...")
                return sale_begin
            
            # 显示倒计时
            hours = int(remaining // 3600)
            minutes = int((remaining % 3600) // 60)
            seconds = int(remaining % 60)
            
            if remaining > 60:
                logger.info(f"倒计时: {hours:02d}:{minutes:02d}:{seconds:02d}")
                time.sleep(10)  # 剩余时间大于1分钟时，每10秒更新
            else:
                logger.info(f"倒计时: {seconds}秒")
                time.sleep(0.1)  # 最后1分钟，每0.1秒更新
    
    def check_ticket_status(self, project_id: int, screen_id: int, sku_id: int) -> dict:
        """
        检查票务状态
        
        Args:
            project_id: 项目ID
            screen_id: 场次ID
            sku_id: 票档ID
            
        Returns:
            票务状态信息
        """
        try:
            project = self.api.get_project_info(project_id)
            
            for screen in project.screens:
                if screen["id"] == screen_id:
                    for sku in screen.get("ticket_list", []):
                        if sku["id"] == sku_id:
                            return {
                                "available": sku.get("stock", {}).get("count", 0) > 0,
                                "stock": sku.get("stock", {}).get("count", 0),
                                "price": sku.get("price", 0),
                                "desc": sku.get("desc", ""),
                            }
            
            return {"available": False, "stock": 0, "error": "未找到票档"}
            
        except Exception as e:
            logger.error(f"检查票务状态失败: {e}")
            return {"available": False, "stock": 0, "error": str(e)}
    
    def start_monitor(
        self,
        project_id: int,
        screen_id: int,
        sku_id: int,
        callback: Callable,
        interval: float = 1.0,
    ):
        """
        启动监控
        
        Args:
            project_id: 项目ID
            screen_id: 场次ID
            sku_id: 票档ID
            callback: 有票时的回调函数
            interval: 检查间隔（秒）
        """
        def _monitor():
            logger.info("开始监控票务状态...")
            while not self._stop_event.is_set():
                status = self.check_ticket_status(project_id, screen_id, sku_id)
                
                if status.get("available"):
                    logger.success(f"有票了！库存: {status.get('stock')}")
                    callback()
                    break
                
                logger.debug(f"暂无余票，{interval}秒后重试...")
                self._stop_event.wait(interval)
        
        self._monitor_thread = threading.Thread(target=_monitor, daemon=True)
        self._monitor_thread.start()
    
    def stop_monitor(self):
        """停止监控"""
        self._stop_event.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2)
        logger.info("监控已停止")


def create_monitor(api: BilibiliAPI) -> TicketMonitor:
    """创建监控器"""
    return TicketMonitor(api)
