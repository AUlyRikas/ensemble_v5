# shuju_loader.py - 数据调用模块（优化版 + 繁体转简体）
import json
import os
import requests
from datetime import datetime

# ========== 配置 ==========
DATA_DIR = os.path.dirname(os.path.abspath(__file__))
YEARS = [2020, 2021, 2022, 2023, 2024, 2025, 2026]
HISTORY_API = "https://history.macaumarksix.com/history/macaujc2/y/{year}"
LIVE_API = "https://macaumarksix.com/api/live2"

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

# 繁体转简体映射
TRAD_TO_SIMP = {
    "馬": "马", "羊": "羊", "猴": "猴", "雞": "鸡", "狗": "狗",
    "豬": "猪", "鼠": "鼠", "牛": "牛", "虎": "虎", "兔": "兔",
    "龍": "龙", "蛇": "蛇",
}

def to_simplified(zodiac_str):
    """将繁体生肖字符串转为简体"""
    if not zodiac_str:
        return zodiac_str
    result = []
    for z in zodiac_str.split(','):
        z = z.strip()
        result.append(TRAD_TO_SIMP.get(z, z))
    return ','.join(result)

def convert_record_to_simplified(record):
    """将单条记录中的繁体转为简体"""
    if 'zodiac' in record and record['zodiac']:
        record['zodiac'] = to_simplified(record['zodiac'])
    if 'wave' in record and record['wave']:
        # 波色已经是简体，不用转
        pass
    return record

# ========== 基础文件操作 ==========
def load_local_data(year):
    fp = os.path.join(DATA_DIR, f"{year}.json")
    if not os.path.exists(fp):
        return []
    try:
        with open(fp, 'r', encoding='utf-8') as f:
            data = json.load(f)
            records = data.get('data', [])
            # 确保已转换
            for r in records:
                if not str(r.get('expect', '')).startswith(str(year)):  # ← 新增这一行
                    continue                                              # ← 新增这一行
                convert_record_to_simplified(r)
            return records
    except Exception as e:
        print(f"⚠️ 读取 {year}.json 失败: {e}")
        return []

def save_local_data(year, records):
    fp = os.path.join(DATA_DIR, f"{year}.json")
    data = {
        "result": True,
        "message": "操作成功",
        "code": 200,
        "data": records,
        "timestamp": int(datetime.now().timestamp() * 1000)
    }
    if os.path.exists(fp):
        backup = fp + ".bak"
        try:
            os.replace(fp, backup)
        except Exception as e:
            print(f"⚠️ 备份失败: {e}")
    
    with open(fp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ 已保存 {year}.json ({len(records)} 期)")

# ========== API 调用 ==========
def fetch_api_data(year):
    url = HISTORY_API.format(year=year)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            print(f"⚠️ {year}年 API 返回 HTTP {resp.status_code}")
            return []
        data = resp.json()
        if data.get('code') == 200 and 'data' in data:
            records = data['data']
            # 转换繁体到简体
            for r in records:
                convert_record_to_simplified(r)
            records = [r for r in records if str(r.get('expect', '')).startswith(str(year))]  # ← 新增这一行
            return records
        else:
            print(f"⚠️ {year}年 API 返回格式异常")
            return []
    except Exception as e:
        print(f"❌ {year}年 API 错误: {e}")
        return []

def update_year_data(year):
    local = load_local_data(year)
    remote = fetch_api_data(year)
    if not remote:
        return local
    
    filtered_remote = [r for r in remote if r.get('expect', '').startswith(str(year))]
    data_dict = {r['expect']: r for r in local}
    new_count = 0
    for r in filtered_remote:
        exp = r.get('expect')
        if exp and exp not in data_dict:
            data_dict[exp] = r
            new_count += 1
    
    merged = sorted(data_dict.values(), key=lambda x: x.get('expect', ''))
    if new_count > 0:
        save_local_data(year, merged)
        print(f"📥 {year}年: 新增 {new_count} 期")
    return merged

def ensure_data_years(start_year=2015, end_year=2026):
    missing = []
    for year in range(start_year, end_year + 1):
        fp = os.path.join(DATA_DIR, f"{year}.json")
        if not os.path.exists(fp):
            print(f"📥 缺失 {year} 年数据，尝试从 API 获取...")
            data = fetch_api_data(year)
            if data:
                save_local_data(year, data)
                print(f"   ✅ 已获取 {len(data)} 期")
            else:
                print(f"   ❌ API 无 {year} 年数据")
                missing.append(year)
    if missing:
        print(f"\n⚠️ 缺失年份: {missing}")
    return missing

# ========== 数据加载 ==========
def load_all_data(auto_update=True):
    all_data = []
    seen_expect = set()
    for year in YEARS:
        if auto_update:
            records = update_year_data(year)
        else:
            records = load_local_data(year)
        for r in records:
            expect = r.get('expect')
            if expect and expect not in seen_expect:
                seen_expect.add(expect)
                r['_year'] = year
                all_data.append(r)
    all_data.sort(key=lambda x: x.get('openTime', ''))
    return all_data

def get_latest_record():
    try:
        resp = requests.get(LIVE_API, headers=HEADERS, timeout=10)
        data = resp.json()
        if isinstance(data, list) and len(data) > 0:
            record = data[0]
            convert_record_to_simplified(record)
            return record
        if isinstance(data, dict) and data.get('data'):
            record = data['data'][0]
            convert_record_to_simplified(record)
            return record
        if isinstance(data, dict) and data.get('openCode'):
            convert_record_to_simplified(data)
            return data
    except Exception as e:
        print(f"⚠️ 获取最新开奖失败: {e}")
    all_data = load_all_data(auto_update=False)
    if all_data:
        return all_data[-1]
    return None

def get_history_data(year=None):
    if year:
        return load_local_data(year) if year in YEARS else []
    return load_all_data(auto_update=False)

def check_api_status():
    test_url = HISTORY_API.format(year=2026)
    try:
        resp = requests.get(test_url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            print("✅ API 服务正常")
            return True
        else:
            print(f"⚠️ API 返回 HTTP {resp.status_code}")
            return False
    except Exception as e:
        print(f"❌ API 不可用: {e}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("数据调用模块自检")
    print("=" * 50)
    check_api_status()
    latest = get_latest_record()
    print(f"\n最新期号: {latest.get('expect') if latest else '无'}")
    if latest:
        print(f"  开奖号码: {latest.get('openCode', '未知')}")
        print(f"  生肖(简体): {latest.get('zodiac', '未知')}")
    all_data = load_all_data(auto_update=True)
    print(f"\n总数据量: {len(all_data)} 期")
    if all_data:
        print(f"  时间范围: {all_data[0].get('openTime', '')[:10]} 至 {all_data[-1].get('openTime', '')[:10]}")
    test_2026 = get_history_data(2026)
    print(f"\n2026年数据: {len(test_2026)} 期")
    print("\n" + "=" * 50)
    print("✅ 自检完成")