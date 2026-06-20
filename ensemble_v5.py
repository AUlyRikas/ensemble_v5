#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ensemble_v5.py —— 四模型集成投票引擎 V5.1 最终版
============================================================
模型构成：
  M1  (oracle_core)     — 平五+8 + 动态阈值替换 + 杀特肖 + F5投票排序
  R96 (reference_96)    — 多信号评分（金标惩罚+冷却+合冲+平五窗口+固定杀肖）
  P54 (predict_54)      — 54条固化围肖信号等权投票
  MAX (core_max)        — 外部金标规则库反向投票（7840条，冻结于前2000期）

投票与排序：
  等权投票 + 非线性排名得分（前3=9分/4-6=3分/7-9=1分）
  九肖：票数 → 排名得分 → 遗漏值
  六肖：票数 → 排名得分 → 金标安全分(升序) → 遗漏值
  三肖：票数 → 合冲优先 → 遗漏值（D3独立排序，连错9→7期）
  四肖/五肖：从六肖截取
  七肖/八肖：从九肖截取
  16码：六肖候选池 + 锚点尾与动态冷尾交集优先 → 锚点尾优先 → 遗漏值降序（T4+方案）
       显示时按 三肖内号码 → 六肖内号码 → 全局补充号码 分层排列

数据与验证（后220期严格样本外）：
  九肖 93.18% 连错1期    六肖 81.82% 连错3期
  五肖 78.64% 连错5期    四肖 71.82% 连错5期    三肖 60.91% 连错7期
  16码 60.18% 连错4期

用法：
  python ensemble_v5.py                → 屏幕预测
  python ensemble_v5.py --output       → 预测 + 保存记录 + 生成JS + 校验上期
  python ensemble_v5.py --test         → 回测验证
============================================================
"""
import json, os, sys
from collections import Counter
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MARK6_DIR = os.path.join(BASE_DIR, "mark6")
if MARK6_DIR not in sys.path:
    sys.path.insert(0, MARK6_DIR)

from shuju_loader import load_all_data
from shx_suishu import (
    get_shengxiao_by_suima, SHENGXIAO,
    get_suima_by_shengxiao, to_simplified,
)

ZODIAC = SHENGXIAO
POS_NAMES = ["平一", "平二", "平三", "平四", "平五", "平六", "特码"]
OFFSETS_ALL = list(range(-11, 0)) + [0] + list(range(1, 12))

SAN_HE = {
    "马": ["虎", "狗"], "羊": ["兔", "猪"], "猴": ["鼠", "龙"],
    "鸡": ["蛇", "牛"], "狗": ["虎", "马"], "猪": ["兔", "羊"],
    "鼠": ["猴", "龙"], "牛": ["蛇", "鸡"], "虎": ["马", "狗"],
    "兔": ["猪", "羊"], "龙": ["鼠", "猴"], "蛇": ["鸡", "牛"],
}
LIU_HE = {"马": "羊", "羊": "马", "猴": "蛇", "蛇": "猴", "鸡": "龙", "龙": "鸡",
          "狗": "兔", "兔": "狗", "猪": "虎", "虎": "猪", "鼠": "牛", "牛": "鼠"}
CHONG = {"马": "鼠", "羊": "牛", "猴": "虎", "鸡": "兔", "狗": "龙", "猪": "蛇",
         "鼠": "马", "牛": "羊", "虎": "猴", "兔": "鸡", "龙": "狗", "蛇": "猪"}

SIGNALS_GOOD = {
    "马": [("平一","号码",8,3), ("平三","号码",3,3), ("平四","生肖",-1,1), ("平五","号码",10,2), ("特码","生肖",6,4)],
    "羊": [("平一","号码",2,3), ("平三","号码",9,4), ("平五","号码",3,4)],
    "猴": [("平三","号码",8,2), ("平四","号码",0,2), ("平五","生肖",3,4), ("平六","号码",10,3)],
    "鸡": [("平二","生肖",-5,1), ("平三","生肖",2,2), ("平四","生肖",6,4), ("特码","生肖",-5,3)],
    "狗": [("平三","号码",2,4), ("平四","号码",8,2), ("平六","号码",2,2), ("特码","号码",2,4)],
    "猪": [("平一","生肖",-5,4), ("平二","号码",11,2), ("平三","号码",1,3), ("平四","号码",2,3), ("平五","号码",3,4)],
    "鼠": [("平一","号码",0,1), ("平二","生肖",4,4), ("平三","生肖",3,1), ("平四","号码",3,0)],
    "牛": [("平一","号码",5,3), ("平二","号码",9,4), ("平三","号码",2,1), ("平四","生肖",1,2), ("平五","生肖",5,4), ("平六","生肖",-4,2)],
    "虎": [("平一","号码",3,1), ("平三","号码",7,3), ("平四","号码",10,3), ("平六","号码",7,4), ("特码","号码",8,4)],
    "兔": [("平二","号码",6,1), ("平三","生肖",2,3), ("平五","号码",0,1), ("特码","生肖",6,4)],
    "龙": [("平一","生肖",3,1), ("平二","号码",5,3), ("平三","号码",10,4), ("平四","生肖",2,0), ("平五","号码",10,2), ("特码","生肖",4,1)],
    "蛇": [("平一","号码",10,3), ("平四","生肖",-5,2), ("平五","号码",6,4), ("特码","号码",3,2)],
}

TAIL_TABLE = {
    "马": [0,1,2,3,4,7,8], "羊": [1,2,3,4,6,7,8], "猴": [1,2,4,5,6,8,9],
    "鸡": [0,2,3,4,6,8,9], "狗": [0,1,2,3,5,6,7], "猪": [1,3,4,5,6,7,8],
    "鼠": [0,1,3,4,6,7,9], "牛": [0,1,3,5,6,7,8], "虎": [1,4,5,6,7,8,9],
    "兔": [0,1,2,3,4,6,8], "龙": [0,1,2,3,4,5,6], "蛇": [1,2,3,4,6,7,8],
}

RULES_PATH = os.path.join(BASE_DIR, "特肖杀肖规则库.json")
TRACK_DIR = os.path.join(BASE_DIR, "oracle记录")
TRACK_FILE = os.path.join(TRACK_DIR, "hit_track_v5.json")
OUTPUT_FILE = os.path.join(TRACK_DIR, "ensemble_v5_history.txt")


def offset_num(num, off):
    return (num - 1 + off) % 49 + 1

def get_window(center_sx, r):
    idx = ZODIAC.index(center_sx)
    return [ZODIAC[(idx + i) % 12] for i in range(-r, r + 1)]

def get_hechong_full(sx):
    pool = {sx}
    for s in SAN_HE.get(sx, []): pool.add(s)
    pool.add(LIU_HE.get(sx, ""))
    ch = CHONG.get(sx, ""); pool.add(ch)
    for s in SAN_HE.get(ch, []): pool.add(s)
    pool.add(LIU_HE.get(ch, ""))
    return pool

def extract_records(data):
    records = []
    for item in data:
        try:
            qs = str(item.get("expect", "")); oc = str(item.get("openCode", ""))
            ot = item.get("openTime", "")
            year = int(ot[:4]) if ot else (int(qs[:4]) if len(qs) >= 4 else 2026)
            if not qs or not oc: continue
            parts = oc.strip().split(",")
            if len(parts) != 7: continue
            nums = [int(p.strip()) for p in parts]
            records.append({
                "qishu": qs, "year": year, "te_num": nums[6],
                "te_sx": get_shengxiao_by_suima(nums[6], year),
                "te_tail": nums[6] % 10,
                "ping_nums": nums[:6],
                "ping_sx": [get_shengxiao_by_suima(n, year) for n in nums[:6]],
            })
        except: continue
    records.sort(key=lambda x: int(x["qishu"]))
    return records

def compute_missing(records, up_to):
    missing = {}
    for s in ZODIAC:
        streak = 0
        for i in range(up_to - 1, -1, -1):
            if records[i]["te_sx"] != s: streak += 1
            else: break
        missing[s] = streak
    return missing

def streak_stats(hit_list):
    total = len(hit_list); hits = sum(hit_list)
    rate = hits / total * 100 if total else 0
    streak = 0; ms = 0; dist = Counter()
    for h in hit_list:
        if not h:
            streak += 1; ms = max(ms, streak)
        else:
            if streak > 0: dist[streak] += 1; streak = 0
    if streak > 0: dist[streak] += 1
    return rate, ms, dist


def model_m1(prev, records, up_to, year, missing):
    ping5 = prev["ping_nums"][4]
    center_num = (ping5 - 1 + 8) % 49 + 1
    center_sx = get_shengxiao_by_suima(center_num, year)
    center_idx = ZODIAC.index(center_sx)
    pool_9 = [ZODIAC[(center_idx + i) % 12] for i in range(-4, 5)]
    outside = [s for s in ZODIAC if s not in pool_9]
    if outside:
        best_outside = max(outside, key=lambda s: missing[s])
        worst_inside = min(pool_9, key=lambda s: missing[s])
        diff = missing[best_outside] - missing[worst_inside]
        DYNAMIC_WINDOW = 50
        if up_to >= DYNAMIC_WINDOW + 1:
            recent_diffs = []
            for i in range(up_to - DYNAMIC_WINDOW, up_to):
                if i < 1: continue
                prev_curr = records[i - 1]
                prev_ping5 = prev_curr["ping_nums"][4]
                prev_center = (prev_ping5 - 1 + 8) % 49 + 1
                prev_center_sx = get_shengxiao_by_suima(prev_center, prev_curr["year"])
                prev_center_idx = ZODIAC.index(prev_center_sx)
                prev_pool = [ZODIAC[(prev_center_idx + j) % 12] for j in range(-4, 5)]
                prev_missing = {}
                for s in ZODIAC:
                    streak = 0
                    for k in range(i - 1, -1, -1):
                        if records[k]["te_sx"] != s: streak += 1
                        else: break
                    prev_missing[s] = streak
                prev_outside = [s for s in ZODIAC if s not in prev_pool]
                if prev_outside and prev_pool:
                    prev_best = max(prev_outside, key=lambda s: prev_missing[s])
                    prev_worst = min(prev_pool, key=lambda s: prev_missing[s])
                    recent_diffs.append(prev_missing[prev_best] - prev_missing[prev_worst])
            if recent_diffs:
                idx_q = min(int(len(recent_diffs) * 0.9), len(recent_diffs) - 1)
                threshold = sorted(recent_diffs)[idx_q]
            else:
                threshold = 9
        else:
            threshold = 9
        if diff > threshold:
            final_nine = [best_outside if s == worst_inside else s for s in pool_9]
        else:
            final_nine = pool_9
    else:
        final_nine = pool_9
    te_kill = prev["te_sx"]
    final_nine_clean = list(final_nine)
    for i in range(len(final_nine_clean)):
        if final_nine_clean[i] == te_kill:
            candidates = [x for x in ZODIAC if x not in final_nine_clean and x != te_kill]
            if candidates:
                replacement = max(candidates, key=lambda x: missing[x])
                final_nine_clean[i] = replacement
    hechong_pool = get_hechong_full(prev["te_sx"])
    votes_f5 = Counter()
    for s in ZODIAC:
        if s in final_nine_clean: votes_f5[s] += 3
        if s in hechong_pool: votes_f5[s] += 2
        if s != te_kill: votes_f5[s] += 1
        if missing[s] >= 20: votes_f5[s] += 2
        votes_f5[s] += int(missing[s] / 10)
    return sorted(final_nine_clean, key=lambda s: votes_f5.get(s, 0), reverse=True)


def model_r96(prev, records, up_to, missing, ext_rules):
    cur_sx = prev["te_sx"]; year = prev["year"]
    MISSING_WEIGHTS = (1.0, 2.0, 3.0); MISSING_THRESH = (8, 20)
    GOLD_PENS = [3, 8, 15, 30]; COOL_PENS = [10, 5, 2]
    FIXED_WEIGHT = 15; TE_WEIGHT = 10
    PING5_WEIGHT = 10; HECHONG_WEIGHT = 8; COOL_WINDOW = 3
    gold_votes = Counter(); te_kill_set = set()
    if ext_rules:
        for rule_key, info in ext_rules.items():
            if info.get('grade') != 'gold': continue
            parts = rule_key.split('|')
            if len(parts) != 5: continue
            sx_rule, pos_name, trigger_sx, off_str, killed_sx = parts
            if sx_rule != cur_sx: continue
            pos_idx = POS_NAMES.index(pos_name) if pos_name in POS_NAMES else -1
            if pos_idx < 0: continue
            asx = prev["ping_sx"][pos_idx] if pos_idx < 6 else cur_sx
            if asx != trigger_sx: continue
            gold_votes[killed_sx] += 1
            if pos_name == "特码": te_kill_set.add(killed_sx)
    fixed_kill_set = set()
    p2_num = prev["ping_nums"][1]
    fixed_kill_set.add(get_shengxiao_by_suima(offset_num(p2_num, 3), year))
    fixed_kill_set.add(cur_sx)
    cool_map = {}
    for dist in range(1, COOL_WINDOW + 1):
        if up_to - dist >= 0:
            sx = records[up_to - dist]["te_sx"]
            pen = COOL_PENS[dist - 1]
            if sx not in cool_map or pen > cool_map[sx]: cool_map[sx] = pen
    oracle_pool = set()
    ping5 = prev["ping_nums"][4]
    center_num = (ping5 - 1 + 8) % 49 + 1
    center_sx = get_shengxiao_by_suima(center_num, year)
    center_idx = ZODIAC.index(center_sx)
    oracle_pool = set(ZODIAC[(center_idx + i) % 12] for i in range(-4, 5))
    hechong_pool = get_hechong_full(cur_sx)
    scores = {}
    for s in ZODIAC:
        m = missing.get(s, 0)
        if m >= MISSING_THRESH[1]: score = m * MISSING_WEIGHTS[2]
        elif m >= MISSING_THRESH[0]: score = m * MISSING_WEIGHTS[1]
        else: score = m * MISSING_WEIGHTS[0]
        v = gold_votes.get(s, 0)
        if v >= 4: score -= GOLD_PENS[3]
        elif v == 3: score -= GOLD_PENS[2]
        elif v == 2: score -= GOLD_PENS[1]
        elif v == 1: score -= GOLD_PENS[0]
        if s in fixed_kill_set: score -= FIXED_WEIGHT
        if s in te_kill_set: score -= TE_WEIGHT
        score -= cool_map.get(s, 0)
        if s in oracle_pool: score += PING5_WEIGHT
        if s in hechong_pool: score += HECHONG_WEIGHT
        scores[s] = score
    return [s for s, _ in sorted(scores.items(), key=lambda x: x[1], reverse=True)[:9]]


def model_p54(prev, year, missing):
    cur_sx = prev["te_sx"]
    if cur_sx not in SIGNALS_GOOD:
        return sorted(ZODIAC, key=lambda s: missing.get(s, 0), reverse=True)[:9]
    vc = Counter()
    for pos, stype, off, r in SIGNALS_GOOD[cur_sx]:
        pos_idx = POS_NAMES.index(pos)
        num = prev["te_num"] if pos == "特码" else prev["ping_nums"][pos_idx]
        sx = prev["te_sx"] if pos == "特码" else prev["ping_sx"][pos_idx]
        if stype == "号码": c = get_shengxiao_by_suima(offset_num(num, off), year)
        else:
            sx_idx = ZODIAC.index(sx); c = ZODIAC[(sx_idx + off) % 12]
        w = get_window(c, r)
        for s in w: vc[s] += 1
    ranked = sorted(vc.items(), key=lambda x: (-x[1], -missing.get(x[0], 0)))
    return [s for s, _ in ranked[:9]]


def model_max(prev, year, missing, ext_rules):
    if not ext_rules:
        return sorted(ZODIAC, key=lambda s: missing.get(s, 0), reverse=True)[:9]
    gold_votes = Counter()
    cur_sx = prev["te_sx"]
    for pidx, pn in enumerate(POS_NAMES):
        num = prev["te_num"] if pn == "特码" else prev["ping_nums"][pidx]
        tsx = prev["te_sx"] if pn == "特码" else prev["ping_sx"][pidx]
        for off in OFFSETS_ALL:
            new_num = offset_num(num, off)
            killed = get_shengxiao_by_suima(new_num, year)
            rule_key = f"{cur_sx}|{pn}|{tsx}|{off}|{killed}"
            if rule_key in ext_rules and ext_rules[rule_key].get('grade') == 'gold':
                gold_votes[ext_rules[rule_key]['killed_sx']] += 1
    killed_set = {s for s, v in gold_votes.items() if v >= 2}
    safe_m = [s for s in ZODIAC if s not in killed_set]
    return sorted(safe_m, key=lambda s: missing.get(s, 0), reverse=True)[:9]


def ensemble_vote(prev, records, up_to, year, missing, ext_rules):
    m1 = model_m1(prev, records, up_to, year, missing)
    r96 = model_r96(prev, records, up_to, missing, ext_rules)
    p54 = model_p54(prev, year, missing)
    mx = model_max(prev, year, missing, ext_rules)

    rank_scores = Counter()
    for nine in [m1, r96, mx, p54]:
        for rank, s in enumerate(nine):
            if rank < 3: rank_scores[s] += 9
            elif rank < 6: rank_scores[s] += 3
            else: rank_scores[s] += 1

    votes = Counter()
    for nine in [m1, r96, mx, p54]:
        for s in nine: votes[s] += 1

    nine_ranked = sorted(votes.items(), key=lambda x: (
        -x[1], -rank_scores.get(x[0], 0), -missing.get(x[0], 0)
    ))
    nine_sx = [s for s, _ in nine_ranked[:9]]

    gold_safety = Counter()
    if ext_rules:
        cur_sx = prev["te_sx"]
        for s in ZODIAC:
            kill_count = 0
            for pidx, pn in enumerate(POS_NAMES):
                num = prev["te_num"] if pn == "特码" else prev["ping_nums"][pidx]
                tsx = prev["te_sx"] if pn == "特码" else prev["ping_sx"][pidx]
                for off in OFFSETS_ALL:
                    new_num = offset_num(num, off)
                    killed = get_shengxiao_by_suima(new_num, year)
                    rule_key = f"{cur_sx}|{pn}|{tsx}|{off}|{killed}"
                    if rule_key in ext_rules and ext_rules[rule_key].get('grade') == 'gold' \
                       and ext_rules[rule_key].get('killed_sx') == s:
                        kill_count += 1
            gold_safety[s] = kill_count

    six_ranked = sorted(votes.items(), key=lambda x: (
        -x[1], -rank_scores.get(x[0], 0),
        gold_safety.get(x[0], 99), -missing.get(x[0], 0)
    ))
    six_sx = [s for s, _ in six_ranked[:6]]

    return nine_sx, six_sx, votes, missing


def get_3xiao_d3(votes, missing, prev_te_sx):
    hechong_set = get_hechong_full(prev_te_sx)
    d3_order = sorted(votes.keys(), key=lambda s: (
        -votes[s],
        -(1 if s in hechong_set else 0),
        -missing.get(s, 0)
    ))
    return d3_order[:3]


def generate_16code(records, idx, six_sx, anchor_sx):
    hist = records[:idx]
    prev = hist[-1]; year = prev["year"]
    candidates = []
    seen = set()
    for sx in six_sx:
        for n in get_suima_by_shengxiao(sx, year):
            if n not in seen:
                candidates.append(n)
                seen.add(n)
    num_missing = {}
    for n in range(1, 50):
        streak = 0
        for i in range(idx - 1, -1, -1):
            if hist[i]["te_num"] != n: streak += 1
            else: break
        num_missing[n] = streak
    opt_tails_anchor = set(TAIL_TABLE.get(anchor_sx, list(range(7))))
    lookback = min(10, idx - 1)
    freq = Counter()
    for i in range(idx - lookback, idx):
        if i >= 0:
            freq[hist[i]["te_tail"]] += 1
    dyn_cold = sorted(range(10), key=lambda t: (freq.get(t, 0), t))[:7]
    dyn_cold_set = set(dyn_cold)
    priority_tails = opt_tails_anchor & dyn_cold_set
    if not priority_tails:
        priority_tails = opt_tails_anchor
    def sort_key(n):
        is_priority = 0 if n % 10 in priority_tails else 1
        is_anchor = 0 if n % 10 in opt_tails_anchor else 1
        return (is_priority, is_anchor, -num_missing.get(n, 0))
    candidates.sort(key=sort_key)
    result = candidates[:16]
    if len(result) < 16:
        existing = set(result)
        all_sorted = sorted(range(1, 50), key=lambda n: -num_missing.get(n, 0))
        for n in all_sorted:
            if n not in existing:
                result.append(n)
                if len(result) >= 16: break
    return result[:16], priority_tails


def load_hit_track():
    if not os.path.exists(TRACK_FILE):
        return []
    with open(TRACK_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_hit_track(track):
    os.makedirs(TRACK_DIR, exist_ok=True)
    with open(TRACK_FILE, 'w', encoding='utf-8') as f:
        json.dump(track, f, ensure_ascii=False, indent=2)

def verify_last_prediction(records):
    track = load_hit_track()
    if not track:
        return track
    last = track[-1]
    if last.get("hit9", -1) != -1 and last.get("hit6", -1) != -1:
        return track
    predicted_issue = last.get("issue", "")
    actual_sx = None
    for r in records:
        if r["qishu"] == predicted_issue:
            actual_sx = r["te_sx"]
            break
    if actual_sx is None:
        return track
    last["hit9"] = 1 if actual_sx in last.get("nine", []) else 0
    last["hit6"] = 1 if actual_sx in last.get("six", []) else 0
    track[-1] = last
    save_hit_track(track)
    return track

def append_prediction_to_track(issue, nine, six):
    track = load_hit_track()
    track.append({
        "issue": issue, "nine": nine, "six": six,
        "hit9": -1, "hit6": -1,
        "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })
    if len(track) > 100:
        track = track[-100:]
    save_hit_track(track)
    return track

def calc_dynamic_rate(window=50):
    track = load_hit_track()
    valid = [t for t in track if t.get("hit9", -1) >= 0][-window:]
    if not valid:
        return 0, 0
    hits9 = sum(t["hit9"] for t in valid)
    hits6 = sum(t["hit6"] for t in valid)
    total = len(valid)
    return hits9 / total * 100 if total else 0, hits6 / total * 100 if total else 0

def save_js(result):
    js_path = os.path.join(BASE_DIR, "ensemble_data.js")
    # 从开奖数据中提取波色和生肖
    latest_data = load_all_data(auto_update=False)
    if latest_data:
        latest_full = latest_data[-1] if latest_data else {}
    else:
        latest_full = {}
    
    js_data = {
        "time": result.get("latest_time", ""),
        "issue": result.get("latest_issue", ""),
        "code": result.get("latest_code", ""),
        "zodiac": latest_full.get("zodiac", ""),
        "wave": latest_full.get("wave", ""),
        "teSx": result.get("latest_te_sx", ""),
        "teWei": result.get("latest_te_wei", ""),
        "nextIssue": result.get("next_qihao", ""),
        "ninePool": result.get("nine_pool", []),
        "sixPool": result.get("six_pool", []),
        "killZodiacs": result.get("kill_zodiacs", []),
        "numbers": result.get("numbers", []),
        "optTails": result.get("opt_tails", []),
        "pools": {
            3: result.get("three", []),
            4: result.get("four", []),
            5: result.get("five", [])
        },
        "dynamicRate9": result.get("dynamic_rate9", 0),
        "dynamicRate6": result.get("dynamic_rate6", 0),
    }
    with open(js_path, "w", encoding="utf-8") as f:
        f.write("var ensembleData = ")
        json.dump(js_data, f, ensure_ascii=False, indent=2)
        f.write(";")
    print(f"[V5] ensemble_data.js 已更新")


def predict_latest(auto_update=False):
    data = load_all_data(auto_update=auto_update)
    records = extract_records(data)
    if len(records) < 2:
        return {"error": "数据不足"}

    if not os.path.exists(RULES_PATH):
        return {"error": f"规则库文件不存在: {RULES_PATH}"}
    with open(RULES_PATH, 'r', encoding='utf-8') as f:
        ext_rules = json.load(f)

    latest_idx = len(records)
    prev = records[-1]; year = prev["year"]
    missing = compute_missing(records, latest_idx)
    nine, six, votes, missing = ensemble_vote(prev, records, latest_idx, year, missing, ext_rules)
    three = get_3xiao_d3(votes, missing, prev["te_sx"])
    anchor_sx = prev["ping_sx"][1]
    numbers, priority_tails = generate_16code(records, latest_idx, six, anchor_sx)

    # 16码分层排序
    three_set = set()
    for sx in three:
        for n in get_suima_by_shengxiao(sx, year):
            three_set.add(n)
    six_set = set()
    for sx in six:
        for n in get_suima_by_shengxiao(sx, year):
            six_set.add(n)
    tier1 = [n for n in numbers if n in three_set]
    tier2 = [n for n in numbers if n in six_set and n not in three_set]
    tier3 = [n for n in numbers if n not in six_set]
    numbers = tier1 + tier2 + tier3

    # 最优7尾
    anchor_order = TAIL_TABLE.get(anchor_sx, list(range(7)))
    opt_tails_display = [t for t in anchor_order if t in priority_tails]
    for t in anchor_order:
        if t not in opt_tails_display:
            opt_tails_display.append(t)
    opt_tails_display = opt_tails_display[:7]

    latest_full = data[-1] if data else {}
    next_qihao = ""
    try:
        exp = prev["qishu"]
        if len(exp) >= 4: next_qihao = f"{exp[:4]}{int(exp[-3:]) + 1:03d}"
    except: pass

    ping2 = prev["ping_nums"][1]
    kill_ref = get_shengxiao_by_suima(offset_num(ping2, 3), year)
    kill_zodiacs = [kill_ref, prev["te_sx"]]

    rate9, rate6 = calc_dynamic_rate()

    return {
        "latest_issue": prev["qishu"],
        "latest_time": latest_full.get("openTime", ""),
        "latest_code": latest_full.get("openCode", ""),
        "latest_te_sx": prev["te_sx"],
        "latest_te_wei": prev["te_tail"],
        "next_qihao": next_qihao,
        "nine_pool": nine,
        "six_pool": six,
        "three": three,
        "five": six[:5],
        "four": six[:4],
        "seven": nine[:7],
        "eight": nine[:8],
        "numbers": numbers,
        "opt_tails": opt_tails_display,
        "kill_zodiacs": kill_zodiacs,
        "dynamic_rate9": rate9,
        "dynamic_rate6": rate6,
    }


def run_test():
    data = load_all_data(auto_update=False)
    records = extract_records(data)
    TRAIN_END = 2000
    test_count = len(records) - TRAIN_END
    print(f"回测: 训练集前{TRAIN_END}期, 测试集后{test_count}期\n")
    if not os.path.exists(RULES_PATH):
        print("错误：外部规则库不存在"); return
    with open(RULES_PATH, 'r', encoding='utf-8') as f:
        ext_rules = json.load(f)
    hits = {k: [] for k in [3, 4, 5, 6, 9, 16]}
    for idx in range(TRAIN_END, len(records)):
        hist = records[:idx]
        prev = hist[-1]; year = prev["year"]
        missing = compute_missing(hist, idx)
        try:
            nine, six, votes, missing = ensemble_vote(prev, hist, idx, year, missing, ext_rules)
            three = get_3xiao_d3(votes, missing, prev["te_sx"])
            anchor_sx = prev["ping_sx"][1]
            numbers, _ = generate_16code(records, idx, six, anchor_sx)
        except:
            nine, six = ZODIAC[:9], ZODIAC[:6]
            three = nine[:3]
            numbers = list(range(1, 17))
        target_sx = records[idx]["te_sx"]
        target_num = records[idx]["te_num"]
        hits[9].append(target_sx in nine)
        hits[6].append(target_sx in six)
        hits[5].append(target_sx in six[:5])
        hits[4].append(target_sx in six[:4])
        hits[3].append(target_sx in three)
        hits[16].append(target_num in numbers)
    for k in [9, 6, 5, 4, 3, 16]:
        rate, ms, dist = streak_stats(hits[k])
        label = f"{k}肖" if k != 16 else "16码"
        print(f"{label}: {rate:.2f}% 连错{ms}期 {dict(dist)}")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--test", action="store_true", help="回测验证")
    p.add_argument("--output", action="store_true", help="预测并保存记录，校验上期")
    p.add_argument("--verify", action="store_true", help="仅校验上期预测")
    p.add_argument("--auto-update", action="store_true", help="自动更新数据（GitHub Actions用）")
    args = p.parse_args()

    if args.test:
        run_test(); sys.exit(0)

    if args.verify:
        data = load_all_data(auto_update=False)
        records = extract_records(data)
        verify_last_prediction(records)
        rate9, rate6 = calc_dynamic_rate()
        print(f"动态命中率(近50期): 九肖 {rate9:.1f}% | 六肖 {rate6:.1f}%")
        sys.exit(0)

    result = predict_latest(auto_update=args.auto_update or args.output)
    if "error" in result:
        print(f"错误: {result['error']}"); sys.exit(1)

    rate9 = result.get('dynamic_rate9', 0)
    rate6 = result.get('dynamic_rate6', 0)

    print("=" * 50)
    print(f"基于期号: {result['latest_issue']}")
    print(f"开奖时间: {result.get('latest_time', '')}")
    print(f"开奖号码: {result.get('latest_code', '')}")
    print(f"本期特肖: {result['latest_te_sx']}(尾{result['latest_te_wei']})")
    print(f"预测下期: {result['next_qihao']}")
    print("-" * 30)
    print(f"动态命中率(近50期): 九肖 {rate9:.1f}% | 六肖 {rate6:.1f}%")
    print(f"基准命中率(严格验证): 九肖93.18% | 六肖81.82% | 16码60.18%")
    print("-" * 30)
    print(f"★九肖: {', '.join(result['nine_pool'])}")
    print(f"★六肖: {', '.join(result['six_pool'])}")
    print(f"★五肖: {', '.join(result['five'])}")
    print(f"★四肖: {', '.join(result['four'])}")
    print(f"★三肖: {', '.join(result['three'])}")
    print(f"★16码: {' '.join(str(n) for n in result['numbers'])}")
    print(f"★最优7尾: {' '.join(str(t) for t in result['opt_tails'])}")
    print("=" * 50)

    if args.output:
        data = load_all_data(auto_update=False)
        records = extract_records(data)
        verify_last_prediction(records)
        append_prediction_to_track(
            result.get("next_qihao", ""),
            result.get("nine_pool", []),
            result.get("six_pool", []),
        )
        save_js(result)
        os.makedirs(TRACK_DIR, exist_ok=True)
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        already_saved = False
        if os.path.exists(OUTPUT_FILE):
            with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                existing_content = f.read()
            if f"预测下期: {result['next_qihao']}" in existing_content:
                already_saved = True
        if not already_saved:
            text = f"""
{'='*50}
{now_str}
基于期号: {result['latest_issue']}
开奖时间: {result.get('latest_time', '')}
开奖号码: {result.get('latest_code', '')}
本期特肖: {result['latest_te_sx']}(尾{result['latest_te_wei']})
预测下期: {result['next_qihao']}
{'-'*30}
动态命中率(近50期): 九肖 {rate9:.1f}% | 六肖 {rate6:.1f}%
基准命中率(严格验证): 九肖93.18% | 六肖81.82% | 16码60.18%
{'-'*30}
★九肖: {', '.join(result['nine_pool'])}
★六肖: {', '.join(result['six_pool'])}
★五肖: {', '.join(result['five'])}
★四肖: {', '.join(result['four'])}
★三肖: {', '.join(result['three'])}
★16码: {' '.join(str(n) for n in result['numbers'])}
★最优7尾: {' '.join(str(t) for t in result['opt_tails'])}
{'='*50}
"""
            with open(OUTPUT_FILE, 'a', encoding='utf-8') as f:
                f.write(text)
            print(f"记录已保存至 {OUTPUT_FILE}")
        else:
            print(f"期号 {result['next_qihao']} 已有记录，跳过保存")