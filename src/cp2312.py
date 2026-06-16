"""
cp2312 签名算法实现
基于B站抢票工具技术调研文档中的算法原理
"""

import struct
import base64
import time
import random
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class BrowserEnvironment:
    """
    浏览器环境参数
    用于模拟真实浏览器环境
    """
    scroll_x: int = 0
    scroll_y: int = 350
    inner_width: int = 1280
    inner_height: int = 720
    outer_width: int = 1280
    outer_height: int = 800
    screen_x: int = 0
    screen_y: int = 350
    screen_width: int = 1920
    screen_height: int = 1080
    screen_avail_width: int = 1920
    history_length: int = 2
    user_agent_length: int = 111
    href_length: int = 80
    device_pixel_ratio: float = 1.0


class Cp2312Generator:
    """
    cp2312 token 生成器
    
    核心算法：
    1. derive_d: 将浏览器环境参数映射到 0-255 的字节范围
    2. init_ctoken_state: 初始化14个状态参数
    3. generate_ctoken: 生成最终的ctoken字符串
    
    struct打包格式：>8B2H4B
    - > = 大端序（Big-endian）
    - 8B = 8个无符号字节（uint8，范围 0-255）
    - 2H = 2个无符号短整数（uint16，范围 0-65535）
    - 4B = 4个无符号字节（uint8）
    - 总计：8×1 + 2×2 + 4×1 = 16字节
    """
    
    def __init__(self, env: Optional[BrowserEnvironment] = None):
        """
        初始化cp2312生成器
        
        Args:
            env: 浏览器环境参数，如果不提供则使用默认值
        """
        self.env = env or BrowserEnvironment()
        self.state: Optional[Dict[str, int]] = None
        
    def derive_d(self, index: int) -> int:
        """
        derive_d 算法：根据浏览器环境参数计算派生值
        
        核心公式：
        (values[index % 16] + values[(3 * index) % 16] + 17 * index) & 255
        
        作用：将浏览器环境参数映射到 0-255 的字节范围
        
        Args:
            index: 索引值（0-15）
            
        Returns:
            0-255范围内的派生值
        """
        # 获取当前时间戳对256取模
        now_mod_256 = int(time.time() * 1000) % 256
        
        # 16个浏览器环境参数
        values = [
            self.env.scroll_x,
            self.env.scroll_y,
            self.env.inner_width,
            self.env.inner_height,
            self.env.outer_width,
            self.env.outer_height,
            self.env.screen_x,
            self.env.screen_y,
            self.env.screen_width,
            self.env.screen_height,
            self.env.screen_avail_width,
            self.env.history_length,
            self.env.user_agent_length,
            self.env.href_length,
            round(10 * self.env.device_pixel_ratio),
            now_mod_256,
        ]
        
        # 核心算法：双重索引 + 偏移
        # 使用 index % 16 和 (3 * index) % 16 两个索引
        # 加上 17 * index 的偏移量
        # 最后 & 255 限制在 0-255 范围内
        result = (values[index % 16] + values[(3 * index) % 16] + 17 * index) & 255
        return result
    
    def init_ctoken_state(self) -> Dict[str, int]:
        """
        初始化 ctoken 状态
        
        根据浏览器环境参数生成14个初始状态值
        
        Returns:
            包含14个状态参数的字典
        """
        self.state = {
            "m1": self.derive_d(0),
            "touchend": self.derive_d(1),
            "m2": self.derive_d(2),
            "visibilitychange": self.derive_d(3),
            "m3": self.derive_d(4),
            "m4": self.derive_d(5),
            "openWindow": self.derive_d(6),
            "m5": self.derive_d(7),
            "timer": 0,
            "timediff": 0.0,
            "m6": self.derive_d(8),
            "m7": self.derive_d(9),
            "m8": self.derive_d(10),
            "m9": self.derive_d(11),
        }
        return self.state
    
    def update_state(self, ticket_collection_time_ms: int) -> Dict[str, int]:
        """
        更新状态（模拟用户行为）
        
        Args:
            ticket_collection_time_ms: 票务收集时间（毫秒时间戳）
            
        Returns:
            更新后的状态字典
        """
        if self.state is None:
            raise ValueError("请先调用 init_ctoken_state() 初始化状态")
        
        now_ms = int(time.time() * 1000)
        
        # 模拟定时器递增（随机 0-3）
        timer_increment = random.randint(0, 3)
        
        # 计算时间差（秒）
        timediff = (now_ms - ticket_collection_time_ms) / 1000.0
        
        self.state["timer"] += timer_increment
        self.state["timediff"] = round(timediff, 1)
        
        return self.state
    
    def generate_ctoken(self, state: Optional[Dict[str, int]] = None) -> str:
        """
        生成 ctoken
        
        核心流程：
        1. 参数打包为二进制格式（struct.pack）
        2. latin1 解码
        3. utf-16le 编码
        4. Base64 编码
        
        Args:
            state: 状态字典，如果不提供则使用内部状态
            
        Returns:
            Base64编码的ctoken字符串
        """
        if state is None:
            state = self.state
        
        if state is None:
            raise ValueError("请先初始化状态")
        
        # 步骤1：struct 打包
        # 格式：>8B2H4B
        # 8个uint8 + 2个uint16 + 4个uint8 = 16字节
        binary_data = struct.pack(
            ">8B2H4B",
            state["m1"],
            state["touchend"],
            state["m2"],
            state["visibilitychange"],
            state["m3"],
            state["m4"],
            state["openWindow"],
            state["m5"],
            state["timer"],
            int(state["timediff"] * 1000),  # 转换为毫秒
            state["m6"],
            state["m7"],
            state["m8"],
            state["m9"],
        )
        
        # 步骤2：编码转换
        # latin1 解码 → utf-16le 编码
        decoded = binary_data.decode("latin1")
        encoded = decoded.encode("utf-16le")
        
        # 步骤3：Base64 编码
        ctoken = base64.b64encode(encoded).decode()
        
        return ctoken
    
    def generate_token(
        self,
        project_id: int,
        screen_id: int,
        order_type: int,
        count: int,
        sku_id: int,
        ts: Optional[int] = None,
    ) -> str:
        """
        生成token（用于购票请求）
        
        Token结构：
        - 1 byte header: 0xC0
        - 4 bytes timestamp
        - 4 bytes project_id
        - 4 bytes screen_id
        - 1 byte order_type
        - 2 bytes count
        - 4 bytes sku_id
        
        编码方式：
        - 标准 base64 编码
        - 自定义字符映射：/+= → _-.
        
        Args:
            project_id: 项目ID
            screen_id: 场次ID
            order_type: 订单类型
            count: 购票数量
            sku_id: 票档ID
            ts: 时间戳（可选，默认使用当前时间）
            
        Returns:
            编码后的token字符串
        """
        if ts is None:
            ts = int(time.time())
        
        # 打包token数据
        # 格式：B4sIIBH I
        # B = uint8 (header)
        # 4s = 4字节字符串 (timestamp)
        # I = uint32 (project_id)
        # I = uint32 (screen_id)
        # B = uint8 (order_type)
        # H = uint16 (count)
        # I = uint32 (sku_id)
        token_data = struct.pack(
            ">B4sIIBHI",
            0xC0,  # header
            ts.to_bytes(4, "big"),  # timestamp
            project_id,
            screen_id,
            order_type,
            count,
            sku_id,
        )
        
        # Base64编码
        token = base64.b64encode(token_data).decode()
        
        # 自定义字符映射：/+= → _-.
        token = token.replace("/", "_").replace("+", "-").replace("=", ".")
        
        return token
    
    def get_full_token(self, project_id: int, screen_id: int, sku_id: int, count: int = 1) -> Dict[str, str]:
        """
        获取完整的token（ctoken + token）
        
        Args:
            project_id: 项目ID
            screen_id: 场次ID
            sku_id: 票档ID
            count: 购票数量
            
        Returns:
            包含ctoken和token的字典
        """
        # 初始化状态
        if self.state is None:
            self.init_ctoken_state()
        
        # 更新状态（模拟用户行为）
        ticket_time = int(time.time() * 1000) - random.randint(1000, 5000)
        self.update_state(ticket_time)
        
        # 生成ctoken
        ctoken = self.generate_ctoken()
        
        # 生成token
        token = self.generate_token(
            project_id=project_id,
            screen_id=screen_id,
            order_type=1,  # 普通订单
            count=count,
            sku_id=sku_id,
        )
        
        return {
            "ctoken": ctoken,
            "token": token,
        }


def create_generator(
    screen_width: int = 1920,
    screen_height: int = 1080,
    inner_width: int = 1280,
    inner_height: int = 720,
) -> Cp2312Generator:
    """
    创建cp2312生成器的便捷函数
    
    Args:
        screen_width: 屏幕宽度
        screen_height: 屏幕高度
        inner_width: 浏览器窗口宽度
        inner_height: 浏览器窗口高度
        
    Returns:
        Cp2312Generator实例
    """
    env = BrowserEnvironment(
        screen_width=screen_width,
        screen_height=screen_height,
        inner_width=inner_width,
        inner_height=inner_height,
        outer_width=inner_width,
        outer_height=inner_height + 80,  # 包含工具栏高度
        screen_avail_width=screen_width,
    )
    return Cp2312Generator(env)


# 便捷的全局实例
default_generator = create_generator()


def get_ctoken(project_id: int, screen_id: int, sku_id: int, count: int = 1) -> str:
    """
    快速获取ctoken的便捷函数
    
    Args:
        project_id: 项目ID
        screen_id: 场次ID
        sku_id: 票档ID
        count: 购票数量
        
    Returns:
        ctoken字符串
    """
    tokens = default_generator.get_full_token(project_id, screen_id, sku_id, count)
    return tokens["ctoken"]


def get_token(project_id: int, screen_id: int, sku_id: int, count: int = 1) -> str:
    """
    快速获取token的便捷函数
    
    Args:
        project_id: 项目ID
        screen_id: 场次ID
        sku_id: 票档ID
        count: 购票数量
        
    Returns:
        token字符串
    """
    tokens = default_generator.get_full_token(project_id, screen_id, sku_id, count)
    return tokens["token"]
