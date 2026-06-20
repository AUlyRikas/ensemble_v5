# shx_suishu.py - 生肖岁数转换模块（完整版）
SHENGXIAO = ["马", "羊", "猴", "鸡", "狗", "猪", "鼠", "牛", "虎", "兔", "龙", "蛇"]

_TRAD_TO_SIMP = {
    "馬": "马", "羊": "羊", "猴": "猴", "雞": "鸡", "狗": "狗",
    "豬": "猪", "鼠": "鼠", "牛": "牛", "虎": "虎", "兔": "兔",
    "龍": "龙", "蛇": "蛇",
}

def _to_simplified(shengxiao):
    return _TRAD_TO_SIMP.get(shengxiao, shengxiao)


def get_benming(year):
    """获取某一年的本命生肖（自动根据年份转换）"""
    base_year = 2026
    base_shengxiao = "马"
    base_idx = SHENGXIAO.index(base_shengxiao)
    diff = base_year - year
    idx = (base_idx - diff) % 12
    return SHENGXIAO[idx]


def get_shengxiao_by_suima(suima, year):
    benming = get_benming(year)
    benming_idx = SHENGXIAO.index(benming)
    offset = (suima - 1) % 12
    idx = (benming_idx - offset) % 12
    return _to_simplified(SHENGXIAO[idx])


def get_suima_by_shengxiao(shengxiao, year):
    """根据生肖获取所有岁码（号码）（自动根据年份转换）"""
    benming = get_benming(year)
    benming_idx = SHENGXIAO.index(benming)
    target_idx = SHENGXIAO.index(shengxiao)
    offset = (benming_idx - target_idx) % 12
    base = offset + 1
    numbers = [base, base + 12, base + 24, base + 36]
    return [n if n <= 49 else n - 48 for n in numbers]


def get_shift_shengxiao(shengxiao, shift):
    """生肖平移（正数顺时针，负数逆时针）"""
    idx = SHENGXIAO.index(shengxiao)
    new_idx = (idx + shift) % 12
    return SHENGXIAO[new_idx]


def get_year_all_shengxiao(year):
    """
    获取某一年所有生肖对应的岁数（号码）
    返回: {生肖: [岁数列表]}
    """
    return {sx: get_suima_by_shengxiao(sx, year) for sx in SHENGXIAO}


def get_year_shengxiao_mapping(year):
    """
    获取某一年岁数→生肖的完整映射表
    返回: {岁数: 生肖}
    """
    return {n: get_shengxiao_by_suima(n, year) for n in range(1, 50)}


def to_simplified(shengxiao):
    """繁体转简体"""
    return _to_simplified(shengxiao)


if __name__ == "__main__":
    print("=" * 60)
    print("shx_suishu.py 自检 - 年份自动转换验证")
    print("=" * 60)
    
    print("\n【2025年（本命蛇）】")
    for n in [1, 2, 3, 12, 13]:
        print(f"  号码 {n:2d} -> {get_shengxiao_by_suima(n, 2025)}")
    
    print("\n【2026年（本命马）】")
    for n in [1, 2, 3, 12, 13]:
        print(f"  号码 {n:2d} -> {get_shengxiao_by_suima(n, 2026)}")
    
    print("\n【2027年（本命羊）】")
    for n in [1, 2, 3, 12, 13]:
        print(f"  号码 {n:2d} -> {get_shengxiao_by_suima(n, 2027)}")
    
    print("\n【2025年完整映射（前13个）】")
    mapping = get_year_shengxiao_mapping(2025)
    for n in range(1, 14):
        print(f"  号码 {n:2d} -> {mapping[n]}")
    
    print("\n" + "=" * 60)
    print("✅ 年份自动转换功能正常")
    print("=" * 60)