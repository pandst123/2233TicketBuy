"""
2233TicketBuy - B站抢票工具主入口
参考biliTickerBuy的主程序逻辑
"""

import sys
import os
import argparse
import time
from pathlib import Path
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme
from rich import print as rprint

MAIN_THEME = Theme({
    "info": "green",
    "warning": "yellow",
    "error": "red bold",
    "time": "blue",
    "title": "bold cyan",
})
console = Console(theme=MAIN_THEME)

if getattr(sys, 'frozen', False):
    BASE_DIR = Path(getattr(sys, '_MEIPASS', ''))
else:
    BASE_DIR = Path(__file__).parent

sys.path.insert(0, str(BASE_DIR / 'src'))

from src.config import ConfigManager, Config
from src.qrcode_login import login_interactive
from src.api_client import create_api_client
from src.ticket_grabber import TicketGrabber, grab_ticket_interactive
from src import __version__


def print_banner():
    console.print()
    console.print(Panel.fit(
        f"[bold cyan]2233TicketBuy[/bold cyan] [dim]v{__version__}[/dim] [dim]— B站会员购抢票工具[/dim]",
        border_style="cyan",
        subtitle="[dim]纯本地运行 · 仅供学习研究[/dim]"
    ))
    console.print()


def login(config_manager):
    console.print("[bold cyan]  步骤 1 : 登录B站账号[/bold cyan]")
    console.print("─" * 50)
    
    result = login_interactive()
    
    if not result.success:
        print(f"\n登录失败: {result.message}")
        return config_manager.config or config_manager.get_default_config()
    
    config = config_manager.config or config_manager.get_default_config()
    config.user.sessdata = result.sessdata
    config.user.bili_jct = result.bili_jct
    config.user.dede_user_id = result.dede_user_id
    config.user.dede_user_id_ckmd5 = result.dede_user_id_ckmd5
    
    config_manager.save(config)
    print("\n登录信息已保存到配置文件")
    
    return config


def get_ticket_status_desc(sku):
    """获取票档状态描述（sale_flag_number 为主，stock 为辅）"""
    flag = sku.get("sale_flag_number", 0)
    FLAG_MAP = {
        1: "未开售", 2: "售卖中", 3: "已停售", 4: "已售罄",
        5: "不可售", 6: "库存紧张", 8: "暂时售罄", 9: "无购买资格",
    }
    status = FLAG_MAP.get(flag, "未知")
    # flag=2 时尝试用 stock.count 显示余量
    if flag == 2:
        stock = sku.get("stock", None)
        if isinstance(stock, dict) and stock.get("count", -1) >= 0:
            status = f"余{stock['count']}"
        elif isinstance(stock, (int, float)) and stock >= 0:
            status = f"余{int(stock)}"
    return status


def get_viewers(api):
    """获取观演人列表（使用 nomask=1 获取真实手机号，对齐 BHYG）"""
    try:
        # BHYG: https://show.bilibili.com/api/ticket/buyer/list?nomask=1
        url = "https://show.bilibili.com/api/ticket/buyer/list?nomask=1"
        client = api._get_client()
        response = client.get(url, headers=api._get_default_headers(), cookies=api.cookies)
        result = response.json()
        errno = result.get("errno", -1)
        if errno == 0:
            data = result.get("data", {})
            if isinstance(data, dict):
                viewer_list = data.get("list", [])
                # 保存到缓存文件，下次直接抢票时可用
                _save_viewers_cache(viewer_list)
                return viewer_list
            else:
                return []
        else:
            msg = result.get("msg", "")
            if msg:
                print(f"获取观演人列表: {msg}")
    except Exception as e:
        print(f"获取观演人列表失败: {e}")
    return []


# viewers 缓存文件路径
VIEWERS_CACHE_FILE = "viewers_cache.json"


def _save_viewers_cache(viewers: list):
    """保存观演人列表到本地缓存（含真实手机号）"""
    try:
        import json
        with open(VIEWERS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(viewers, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _load_viewers_cache() -> list:
    """从本地缓存加载观演人列表"""
    try:
        import json
        with open(VIEWERS_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def select_viewers(api, count):
    """选择观演人"""
    print("\n" + "-" * 50)
    print("  选择购票人")
    print("-" * 50)
    
    viewers = get_viewers(api)
    
    if not viewers:
        print("\n未找到观演人信息")
        print("请先在B站APP或网页端添加观演人")
        input_id = input("\n请输入观演人ID（如果不需要实名制可直接回车）: ").strip()
        if input_id:
            return [int(input_id)]
        return []
    
    print("\n可用观演人:")
    for i, viewer in enumerate(viewers, 1):
        name = viewer.get("name", "未知")
        id_card = viewer.get("personal_id", viewer.get("id_card", ""))
        tel = viewer.get("tel", "")
        # 显示完整姓名和身份证号（已通过 nomask=1 获取真实数据）
        print(f"  {i}. {name}  {tel}  {id_card}")
    
    selected = []
    for i in range(count):
        while True:
            try:
                choice = input(f"\n请选择第{i+1}个观演人（输入序号）: ").strip()
                if not choice:
                    break
                idx = int(choice) - 1
                if 0 <= idx < len(viewers):
                    selected.append(viewers[idx])
                    break
                else:
                    print("序号超出范围")
            except ValueError:
                print("请输入有效的数字")
    
    return selected


def select_event(config, api):
    """选择活动"""
    console.print("\n[bold cyan]  步骤 2 : 选择活动[/bold cyan]")
    console.print("─" * 50)
    print("\n  热门活动参考:")
    print("    上海·BILIBILI MACRO LINK-PLAY! 2026 : 1001701")
    print("    上海·BilibiliWorld 2026           : 1001653")
    
    while True:
        try:
            project_id = int(input("\n请输入活动ID（从URL获取）: "))
            if project_id <= 0:
                print("活动ID必须大于0")
                continue
            break
        except ValueError:
            print("请输入有效的数字")
    
    try:
        project = api.get_project_info(project_id)
        
        # 显示活动信息
        print(f"\n活动名称: {project.name}")
        print(f"开售时间: {datetime.fromtimestamp(project.sale_begin).strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 检查是否已开售
        now = time.time()
        if project.sale_begin > 0:
            if now < project.sale_begin:
                print("状态: 未开售")
            else:
                print("状态: 已开售")
        
        # 显示场次列表（过滤 sale_flag_number=5 不可售，匹配 App 行为）
        print("\n可用场次:")
        SALE_FLAG_MAP = {1:"未开售", 2:"售卖中", 3:"已停售", 4:"已售罄", 5:"不可售", 6:"库存紧张", 8:"暂时售罄", 9:"无购买资格"}
        available_screens = [
            s for s in project.screens 
            if s.get('sale_flag_number', 2) != 5  # 排除不可售
        ]
        for i, screen in enumerate(available_screens, 1):
            name = screen.get('name', '未知')
            flag = screen.get('sale_flag_number', 0)
            status = SALE_FLAG_MAP.get(flag, "")
            line = f"  {i}. {name}"
            if status:
                line += f" [{status}]"
            print(line)
        
        if not available_screens:
            print("  ⚠️ 暂无可选场次")
            return config, []
        
        # 选择场次
        while True:
            try:
                screen_index = int(input("\n请选择场次（输入序号）: ")) - 1
                if 0 <= screen_index < len(available_screens):
                    screen = available_screens[screen_index]
                    break
                else:
                    print("序号超出范围")
            except ValueError:
                print("请输入有效的数字")
        
        # 显示票档列表（带状态）
        print(f"\n场次: {screen.get('name', '未知')}")
        print("\n可用票档:")
        ticket_list = screen.get("ticket_list", [])
        for i, sku in enumerate(ticket_list, 1):
            desc = sku.get("desc", "未知")
            price = sku.get("price", 0) / 100
            status_desc = get_ticket_status_desc(sku)
            print(f"  {i}. {desc}: ¥{price} [{status_desc}]")
        
        # 选择票档
        while True:
            try:
                sku_index = int(input("\n请选择票档（输入序号）: ")) - 1
                if 0 <= sku_index < len(ticket_list):
                    sku = ticket_list[sku_index]
                    # 售罄/暂时售罄：允许选择，提示将进入监控模式
                    status_desc = get_ticket_status_desc(sku)
                    if "售罄" in status_desc:
                        print(f"⚠ 该票档当前「{status_desc}」，将继续但进入监控模式等待回流")
                    break
                else:
                    print("序号超出范围")
            except ValueError:
                print("请输入有效的数字")
        
        # 获取购票数量
        while True:
            try:
                count = int(input("\n请输入购票数量: "))
                if count <= 0:
                    print("购票数量必须大于0")
                    continue
                break
            except ValueError:
                print("请输入有效的数字")
        
        # 选择购票人（所有票都可以选择购票人）
        viewers = select_viewers(api, count)
        if viewers:
            _save_viewers_cache(viewers)
        
        # 更新配置
        config.event.project_id = project_id
        config.event.screen_id = screen["id"]
        config.event.sku_id = sku["id"]
        config.event.count = count
        # 自动检测 hot 项目
        if getattr(project, 'hot_project', False):
            config.event.hot_project = True
            print("\n  🔥 检测到热门项目，已启用 hot 模式")
        
        # 显示选择摘要
        print("\n" + "-" * 50)
        print("  选择摘要")
        print("-" * 50)
        print(f"活动: {project.name}")
        print(f"场次: {screen.get('name', '未知')}")
        print(f"票档: {sku.get('desc', '未知')}")
        print(f"数量: {count}")
        print(f"单价: ¥{sku.get('price', 0) / 100}")
        print(f"总价: ¥{sku.get('price', 0) * count / 100}")
        print(f"状态: {get_ticket_status_desc(sku)}")
        if viewers:
            print(f"观演人: {', '.join([v.get('name', '未知') for v in viewers if isinstance(v, dict)])}")
        
        return config, viewers
        
    except Exception as e:
        print(f"\n获取活动信息失败: {e}")
        return config, []


def show_config(config, api=None):
    """显示当前配置"""
    console.print()
    console.print(Panel.fit("[bold]当前运行配置[/bold]", border_style="blue"))
    
    # ── 登录信息 ──
    uid = config.user.dede_user_id or "未设置"
    print(f"\n  [登录信息]")
    print(f"    UID       : {uid}")
    if api:
        try:
            user_info = api.get_user_info()
            uname = user_info.get("uname", "未知")
            is_vip = "是" if user_info.get("vipStatus") == 1 else "否"
            level_info = user_info.get("level_info") or {}
            level = level_info.get("current_level", "?")
            print(f"    用户名     : {uname}")
            print(f"    等级       : Lv{level}")
            print(f"    大会员     : {is_vip}")
        except:
            print(f"    用户名     : (获取失败)")
    
    # ── 活动信息 ──
    pid = config.event.project_id
    print(f"\n  [活动信息]")
    if pid > 0 and api:
        try:
            project = api.get_project_info(pid)
            print(f"    活动名称   : {project.name}")
            print(f"    活动ID     : {project.id}")
            
            # 场次
            screen_name = "未知"
            for s in project.screens:
                if s["id"] == config.event.screen_id:
                    screen_name = s.get("name", "未知")
                    break
            print(f"    场次       : {screen_name}")
            print(f"    场次ID     : {config.event.screen_id}")
            
            # 票档
            sku_name, sku_price, sku_status = "未知", 0, "未知"
            for s in project.screens:
                if s["id"] == config.event.screen_id:
                    for sku in s.get("ticket_list", []):
                        if sku["id"] == config.event.sku_id:
                            sku_name = sku.get("desc", "未知")
                            sku_price = sku.get("price", 0) / 100
                            sku_status = get_ticket_status_desc(sku)
                            break
            print(f"    票档       : {sku_name} (¥{sku_price}) [{sku_status}]")
            print(f"    票档ID     : {config.event.sku_id}")
            
            # 限购信息
            id_bind = getattr(project, 'id_bind', 0)
            if id_bind > 0:
                print(f"    实名方式   : 单票单证 (id_bind={id_bind})")
            else:
                print(f"    实名方式   : 单号单证")
            hot = getattr(project, 'hot_project', False) or getattr(config.event, 'hot_project', False)
            if hot:
                print(f"    项目类型   : 🔥 热门项目 (hotProject)")
            
            # 开售信息
            if project.sale_begin > 0:
                from datetime import datetime
                sale_str = datetime.fromtimestamp(project.sale_begin).strftime('%Y-%m-%d %H:%M:%S')
                now = time.time()
                if now < project.sale_begin:
                    remaining = project.sale_begin - now
                    h, m = int(remaining // 3600), int((remaining % 3600) // 60)
                    print(f"    开售时间   : {sale_str} (剩余 {h}h{m}m)")
                else:
                    print(f"    开售时间   : {sale_str} (已开售)")
            else:
                print(f"    开售时间   : 未设置")
        except Exception as e:
            print(f"    活动ID     : {pid}")
            print(f"    详细信息   : 获取失败 ({e})")
    else:
        print(f"    活动ID     : {'未设置' if pid <= 0 else pid}")
        print(f"    场次/票档  : 未选择")
    
    # ── 购票人 ──
    print(f"\n  [购票信息]")
    print(f"    购票数量   : {config.event.count}")
    viewers = _load_viewers_cache()
    if viewers:
        names = ", ".join([f"{v.get('name','?')} ({v.get('tel','?')})" for v in viewers[:3]])
        print(f"    观演人     : {names}")
        if len(viewers) > 3:
            print(f"                ...共 {len(viewers)} 人")
    else:
        print(f"    观演人     : 未设置")
    
    # ── 策略配置 ──
    print(f"\n  [策略配置]")
    print(f"    提前开始   : {config.strategy.advance_ms}ms")
    print(f"    开售延迟   : {getattr(config.strategy, 'after_sale_begin_delay', 0.3)}s")
    print(f"    下单间隔   : {getattr(config.strategy, 'order_interval', 0.3)}s")
    print(f"    速率偏差   : {getattr(config.strategy, 'delta', 0.05)}s")
    print(f"    请求超时   : {config.strategy.timeout_seconds}s")
    print(f"    并发数     : {config.strategy.concurrency}")
    print(f"    库存检查   : {'开启' if getattr(config.strategy, 'enable_stock_check', False) else '关闭'}")
    proxy_enabled = config.proxy.enabled
    print(f"    代理       : {'已配置' if proxy_enabled else '未设置'}")
    if proxy_enabled:
        proxy_type = "SOCKS5" if config.proxy.socks5 else ("HTTPS" if config.proxy.https else "HTTP")
        print(f"    代理类型   : {proxy_type}")
    
    # ── 设备指纹 ──
    if api:
        print(f"\n  [设备指纹]")
        ua = getattr(api, 'mobile_ua', '')
        if ua and 'Linux' in ua:
            import re
            m = re.search(r'Android (\d+); ([^)]+)\)', ua)
            if m:
                print(f"    UA 类型    : Android {m.group(1)}")
                print(f"    UA 设备    : {m.group(2)}")
            else:
                print(f"    UA 类型    : 移动端")
        else:
            print(f"    UA 类型    : 默认")
        buvid3 = getattr(api, 'buvid3', '')
        if buvid3:
            print(f"    buvid3     : {buvid3[:20]}...")
        if getattr(api, '_client', None):
            print(f"    Session    : 持久连接")
    
    print("-" * 50)


def _tweak_params(config, config_manager):
    """参数微调"""
    console.print()
    console.print(Panel.fit(
        "[bold yellow]⚠ 参数微调[/bold yellow]\n\n"
        "[dim]这些参数影响抢票策略，[/dim][bold red]绝大多数情况下不需要修改[/bold red][dim]。\n"
        "不当修改可能导致风控概率增加或抢票失败。[/dim]",
        border_style="yellow"
    ))
    s = config.strategy
    console.print(f"  [cyan]1.[/cyan] 开售延迟 : [bold]{s.after_sale_begin_delay}s[/bold]")
    console.print(f"  [cyan]2.[/cyan] 下单间隔 : [bold]{getattr(s, 'order_interval', 0.3)}s[/bold]")
    console.print(f"  [cyan]3.[/cyan] 速率偏差 : [bold]{getattr(s, 'delta', 0.05)}s[/bold]")
    console.print(f"  [cyan]4.[/cyan] 提前开始 : [bold]{s.advance_ms}ms[/bold]")
    console.print(f"  [cyan]0.[/cyan] 返回")
    console.print()
    c = input("选择参数 (0-4): ").strip()
    try:
        if c == "1":
            s.after_sale_begin_delay = float(input("开售延迟(秒): ") or "0.3")
        elif c == "2":
            s.order_interval = float(input("下单间隔(秒): ") or "0.3")
        elif c == "3":
            s.delta = float(input("速率偏差(秒): ") or "0.05")
        elif c == "4":
            s.advance_ms = int(input("提前开始(毫秒, 默认0): ") or "0")
        else:
            return
        config_manager.save(config)
        console.print("[green]已保存[/green]")
    except ValueError:
        console.print("[red]无效输入[/red]")


def confirm_and_grab(config, api, viewers=None):
    """确认信息并开始抢票"""
    console.print("\n[bold green]  步骤 3 : 确认信息[/bold green]")
    console.print("─" * 50)
    
    # 获取完整信息
    try:
        project = api.get_project_info(config.event.project_id)
        
        # 查找场次
        screen_name = "未知"
        screen_data = None
        for s in project.screens:
            if s["id"] == config.event.screen_id:
                screen_name = s.get("name", "未知")
                screen_data = s
                break
        
        # 查找票档
        sku_name = "未知"
        sku_price = 0
        sku_status = "未知"
        if screen_data:
            for sku in screen_data.get("ticket_list", []):
                if sku["id"] == config.event.sku_id:
                    sku_name = sku.get("desc", "未知")
                    sku_price = sku.get("price", 0) / 100
                    sku_status = get_ticket_status_desc(sku)
                    break
        
        print(f"\n活动: {project.name}")
        print(f"场次: {screen_name}")
        print(f"票档: {sku_name} (¥{sku_price})")
        print(f"状态: {sku_status}")
        print(f"数量: {config.event.count}")
        print(f"总价: ¥{sku_price * config.event.count}")
        
        # VIP 状态
        try:
            user_info = api.get_user_info()
            is_vip = user_info.get("vipStatus") == 1
            print(f"大会员: {'是' if is_vip else '否'}")
            if not is_vip:
                console.print("[yellow]  注意：非大会员，若本项目有VIP提前购将无法参与[/yellow]")
        except:
            pass
        if viewers:
            print(f"观演人: {', '.join([v.get('name', '未知') for v in viewers if isinstance(v, dict)])}")
        
        # 显示开售时间
        if project.sale_begin > 0:
            sale_time = datetime.fromtimestamp(project.sale_begin).strftime('%Y-%m-%d %H:%M:%S')
            print(f"\n开售时间: {sale_time}")
            
            now = time.time()
            if now < project.sale_begin:
                remaining = project.sale_begin - now
                hours = int(remaining // 3600)
                minutes = int((remaining % 3600) // 60)
                print(f"距离开售: {hours}小时{minutes}分钟")
            else:
                print("状态: 已开售")
        
    except Exception as e:
        print(f"\n获取活动信息失败: {e}")
        print(f"活动ID: {config.event.project_id}")
        print(f"场次ID: {config.event.screen_id}")
        print(f"票档ID: {config.event.sku_id}")
        print(f"数量: {config.event.count}")
    
    confirm = input("\n确认以上信息正确？(y/n): ").strip().lower()
    if confirm != "y":
        print("已取消")
        return
    
    # 开始抢票
    console.print("\n[bold red]  步骤 4 : 开始抢票[/bold red]")
    console.print("─" * 50)
    
    result = grab_ticket_interactive(config, viewers=viewers or [])
    
    print("\n" + "-" * 50)
    if result.success:
        print("[OK] 抢票成功！")
        print(f"订单ID: {result.order_id}")
        print("请尽快完成支付！")
    else:
        print("[FAIL] 抢票失败")
        print(f"原因: {result.message}")
    print("-" * 50)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="2233TicketBuy - B站抢票工具",
        epilog="""
示例:
  python main.py              # 交互模式
  python main.py --login      # 仅登录
  python main.py --grab       # 直接抢票
        """
    )
    parser.add_argument('-c', '--config', default='config.yaml', help='配置文件路径')
    parser.add_argument('--login', action='store_true', help='仅执行登录')
    parser.add_argument('--grab', action='store_true', help='直接开始抢票')
    parser.add_argument('--create-example', action='store_true', help='创建示例配置文件')
    
    args = parser.parse_args()
    
    print_banner()
    
    config_manager = ConfigManager(args.config)
    
    if args.create_example:
        config_manager.create_example_config()
        print("示例配置文件已创建")
        return
    
    try:
        config = config_manager.load()
    except FileNotFoundError:
        print(f"配置文件不存在: {args.config}")
        print("将使用默认配置")
        config = config_manager.get_default_config()
    
    if args.login:
        login(config_manager)
        return
    
    api = create_api_client(config)
    
    if args.grab:
        if not config.user.sessdata:
            print("\n未登录，请先登录")
            config = login(config_manager)
        
        api = create_api_client(config)
        if not api.check_login():
            print("\n登录已过期，请重新登录")
            config = login(config_manager)
            api = create_api_client(config)
        
        # 从缓存加载观演人
        viewers = _load_viewers_cache()
        if not viewers:
            print("\n未找到购票人缓存，请先交互模式选择活动")
            return
        
        confirm_and_grab(config, api, viewers)
        return
    
    # 交互模式
    viewers = []
    while True:
        console.print()
        console.print(Panel.fit(
            "[bold]主菜单[/bold]",
            border_style="blue"
        ))
        console.print("  [cyan]1.[/cyan] 登录B站账号")
        console.print("  [cyan]2.[/cyan] 选择活动")
        console.print("  [cyan]3.[/cyan] [bold green]开始抢票[/bold green]")
        console.print("  [cyan]4.[/cyan] 查看配置")
        console.print("  [cyan]5.[/cyan] 参数微调")
        console.print("  [cyan]6.[/cyan] 退出")
        console.print()
        
        choice = input("请选择操作: ").strip()
        
        if choice == "1":
            config = login(config_manager)
        elif choice == "2":
            if not config.user.sessdata:
                print("\n请先登录！")
                continue
            
            api = create_api_client(config)
            if not api.check_login():
                print("\n登录已过期，请重新登录")
                config = login(config_manager)
                continue
            
            config, viewers = select_event(config, api)
            config_manager.save(config)
            print("\n配置已保存")
            
        elif choice == "3":
            if config.event.project_id <= 0:
                print("\n请先选择活动！")
                continue
            
            # 确保使用最新的配置创建 API 客户端
            api = create_api_client(config)
            if not api.check_login():
                print("\n登录已过期，请重新登录")
                config = login(config_manager)
                api = create_api_client(config)
                if not api.check_login():
                    continue
            
            # 如果没有当前选择的观演人，尝试从缓存加载
            if not viewers:
                viewers = _load_viewers_cache()
                if viewers:
                    print(f"\n从缓存加载了 {len(viewers)} 个观演人")
                else:
                    print("\n未找到购票人信息，请先执行「选择活动」")
                    continue
            
            confirm_and_grab(config, api, viewers)
            
        elif choice == "4":
            # 尝试创建 API 客户端以获取详细信息
            try:
                api = create_api_client(config)
            except:
                api = None
            show_config(config, api)

        elif choice == "5":
            _tweak_params(config, config_manager)

        elif choice == "6":
            console.print("\n再见！")
            break


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n用户取消操作")
    except Exception as e:
        print(f"\n发生错误: {e}")
    finally:
        if getattr(sys, 'frozen', False):
            input("\n按回车键退出...")
