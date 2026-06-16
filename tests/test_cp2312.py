"""
cp2312 算法测试脚本
用于验证cp2312签名算法的正确性
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.cp2312 import Cp2312Generator, BrowserEnvironment, create_generator


def test_derive_d():
    """
    测试 derive_d 算法
    """
    print("=" * 60)
    print("测试 derive_d 算法")
    print("=" * 60)
    
    env = BrowserEnvironment()
    generator = Cp2312Generator(env)
    
    # 测试所有索引
    print("\n测试所有索引 (0-15):")
    for i in range(16):
        value = generator.derive_d(i)
        print(f"  derive_d({i}) = {value}")
    
    # 验证范围
    print("\n验证值范围 (0-255):")
    all_in_range = all(0 <= generator.derive_d(i) <= 255 for i in range(16))
    print(f"  所有值都在0-255范围内: {all_in_range}")
    
    return all_in_range


def test_init_ctoken_state():
    """
    测试 init_ctoken_state 函数
    """
    print("\n" + "=" * 60)
    print("测试 init_ctoken_state 函数")
    print("=" * 60)
    
    generator = Cp2312Generator()
    state = generator.init_ctoken_state()
    
    print("\n生成的状态值:")
    for key, value in state.items():
        print(f"  {key}: {value}")
    
    # 验证状态完整性
    expected_keys = [
        "m1", "touchend", "m2", "visibilitychange",
        "m3", "m4", "openWindow", "m5",
        "timer", "timediff",
        "m6", "m7", "m8", "m9"
    ]
    
    print(f"\n验证状态完整性:")
    print(f"  期望的键: {expected_keys}")
    print(f"  实际的键: {list(state.keys())}")
    print(f"  键匹配: {set(expected_keys) == set(state.keys())}")
    
    return set(expected_keys) == set(state.keys())


def test_generate_ctoken():
    """
    测试 generate_ctoken 函数
    """
    print("\n" + "=" * 60)
    print("测试 generate_ctoken 函数")
    print("=" * 60)
    
    generator = Cp2312Generator()
    generator.init_ctoken_state()
    
    # 模拟状态变化
    import time
    ticket_time = int(time.time() * 1000) - 5000  # 5秒前
    generator.update_state(ticket_time)
    
    # 生成ctoken
    ctoken = generator.generate_ctoken()
    
    print(f"\n生成的ctoken: {ctoken}")
    print(f"ctoken长度: {len(ctoken)}")
    
    # 验证Base64格式
    import base64
    try:
        decoded = base64.b64decode(ctoken)
        print(f"Base64解码成功，长度: {len(decoded)} 字节")
        is_valid = True
    except Exception as e:
        print(f"Base64解码失败: {e}")
        is_valid = False
    
    return is_valid


def test_generate_token():
    """
    测试 generate_token 函数
    """
    print("\n" + "=" * 60)
    print("测试 generate_token 函数")
    print("=" * 60)
    
    generator = Cp2312Generator()
    
    # 测试参数
    project_id = 12345
    screen_id = 67890
    sku_id = 111
    count = 1
    
    token = generator.generate_token(
        project_id=project_id,
        screen_id=screen_id,
        order_type=1,
        count=count,
        sku_id=sku_id,
    )
    
    print(f"\n生成的token: {token}")
    print(f"token长度: {len(token)}")
    
    # 验证字符映射
    has_invalid_chars = any(c in token for c in "/+=")
    print(f"包含无效字符 (/+=): {has_invalid_chars}")
    
    return not has_invalid_chars


def test_get_full_token():
    """
    测试 get_full_token 函数
    """
    print("\n" + "=" * 60)
    print("测试 get_full_token 函数")
    print("=" * 60)
    
    generator = Cp2312Generator()
    
    # 测试参数
    project_id = 12345
    screen_id = 67890
    sku_id = 111
    count = 1
    
    tokens = generator.get_full_token(
        project_id=project_id,
        screen_id=screen_id,
        sku_id=sku_id,
        count=count,
    )
    
    print(f"\n生成的tokens:")
    print(f"  ctoken: {tokens['ctoken']}")
    print(f"  token: {tokens['token']}")
    
    # 验证两个token都生成了
    has_both = "ctoken" in tokens and "token" in tokens
    print(f"\n两个token都生成了: {has_both}")
    
    return has_both


def test_create_generator():
    """
    测试 create_generator 函数
    """
    print("\n" + "=" * 60)
    print("测试 create_generator 函数")
    print("=" * 60)
    
    # 测试不同屏幕分辨率
    resolutions = [
        (1920, 1080),
        (2560, 1440),
        (3840, 2160),
    ]
    
    all_passed = True
    for width, height in resolutions:
        generator = create_generator(
            screen_width=width,
            screen_height=height,
            inner_width=1280,
            inner_height=720,
        )
        
        print(f"\n分辨率 {width}x{height}:")
        print(f"  screen_width: {generator.env.screen_width}")
        print(f"  screen_height: {generator.env.screen_height}")
        
        # 生成token验证
        tokens = generator.get_full_token(12345, 67890, 111)
        print(f"  ctoken生成成功: {bool(tokens['ctoken'])}")
        
        if not tokens["ctoken"]:
            all_passed = False
    
    return all_passed


def test_consistency():
    """
    测试一致性（相同输入应该产生相同输出）
    """
    print("\n" + "=" * 60)
    print("测试一致性")
    print("=" * 60)
    
    import time
    
    # 固定时间戳
    fixed_time = int(time.time() * 1000)
    
    # 创建两个相同配置的生成器
    env = BrowserEnvironment()
    gen1 = Cp2312Generator(env)
    gen2 = Cp2312Generator(env)
    
    # 初始化状态
    gen1.init_ctoken_state()
    gen2.init_ctoken_state()
    
    # 使用相同的时间戳更新状态
    gen1.update_state(fixed_time)
    gen2.update_state(fixed_time)
    
    # 生成ctoken
    ctoken1 = gen1.generate_ctoken()
    ctoken2 = gen2.generate_ctoken()
    
    print(f"\nctoken1: {ctoken1}")
    print(f"ctoken2: {ctoken2}")
    print(f"一致性: {ctoken1 == ctoken2}")
    
    return ctoken1 == ctoken2


def run_all_tests():
    """
    运行所有测试
    """
    print("\n" + "=" * 60)
    print("开始运行所有测试")
    print("=" * 60)
    
    tests = [
        ("derive_d", test_derive_d),
        ("init_ctoken_state", test_init_ctoken_state),
        ("generate_ctoken", test_generate_ctoken),
        ("generate_token", test_generate_token),
        ("get_full_token", test_get_full_token),
        ("create_generator", test_create_generator),
        ("consistency", test_consistency),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"\n测试 {name} 发生异常: {e}")
            results.append((name, False))
    
    # 打印测试结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    all_passed = True
    for name, passed in results:
        status = "✓ 通过" if passed else "✗ 失败"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False
    
    print(f"\n总体结果: {'全部通过' if all_passed else '存在失败'}")
    
    return all_passed


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
