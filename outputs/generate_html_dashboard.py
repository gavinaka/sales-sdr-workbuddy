#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
服务池SDR交互看板生成器
读取 chengdu_final_enriched.json，对客户进行6维评分+分级，输出单文件HTML交互看板。
"""
import os
import sys
import io
import json
import re
import time
import math
from collections import Counter

# 解决 Windows 控制台编码问题
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, 'chengdu_final_enriched.json')
OUT_FILE = os.path.join(BASE_DIR, '服务池SDR交互看板.html')

NOW_MS = time.time() * 1000
DAY_MS = 86400000.0

# 顾问ID → 名称映射（2026-07-06 CRM抓取getUserListForCounselors.ac核对确认）
# CRM真实数据：1431=吴必川 1314=王胜学 2379=潘飞 2381=吴云凤 800=刘昕(主管)
# 老板指示：吴必川(1431)病假→客户归属吴云凤；刘昕(800)主管不跟进→待分配
# 零散ID(1696/1878/1733等)为成都分部已离职人员→待分配
COUNSELOR_MAP = {
    1431: '吴云凤',   # CRM=吴必川，病假，老板指示归属吴云凤
    1314: '王胜学',
    2379: '潘飞',
    2381: '吴云凤',
}


def counselor_name(cid):
    if not cid:
        return '待分配'
    return COUNSELOR_MAP.get(cid, '待分配')

# ---------------- 评分常量 ----------------
INDUSTRY_5 = {'服装鞋帽'}
INDUSTRY_4 = {'食品饮料', '数码家电', '美妆代购', '母婴玩具', '烟酒茶叶',
              '珠宝饰品', '商超便利', '水果生鲜'}
INDUSTRY_3 = {'日用百货', '家装建材', '家居家纺', '五金机械', '汽修汽配',
              '文体图书', '农药化肥', '宠物用品'}

GRADE_COLORS = {
    'S': '#F8D7DA',
    'A2': '#FCE4C4',
    'A3': '#FFF3E0',
    'B': '#FFEB9C',
    'C': '#C6EFCE',
}
GRADE_TEXT = {
    'S': 'S 紧急',
    'A2': 'A2 高优',
    'A3': 'A3 培养',
    'B': 'B 维护',
    'C': 'C 池养',
}


# ---------------- 评分函数 ----------------
def days_since_visit(last_visit_ms):
    if not last_visit_ms:
        return None
    try:
        return (NOW_MS - float(last_visit_ms)) / DAY_MS
    except (TypeError, ValueError):
        return None


def score_visit(last_visit_ms):
    """D1 回访紧迫度"""
    d = days_since_visit(last_visit_ms)
    if d is None:
        return 3  # 无回访
    if d > 365:
        return 5
    if d > 180:
        return 4
    if d > 90:
        return 3
    if d > 30:
        return 2
    return 1


def score_industry(ind):
    """D2 行业匹配"""
    if not ind or ind == '未填':
        return 1
    if ind in INDUSTRY_5:
        return 5
    if ind in INDUSTRY_4:
        return 4
    if ind in INDUSTRY_3:
        return 3
    return 2  # 其他


def score_business(bt, ia):
    """D3 业务类型"""
    text = (bt or '') + ' ' + (ia or '').replace('＋', '+')
    has_p = '批' in text
    has_l = '零' in text
    if has_p and has_l:
        return 5  # 批零一体/兼营
    if has_p:
        return 3  # 批发
    if has_l:
        return 2  # 零售
    return 1  # 未填/无


def score_scale(store, user):
    """D4 规模"""
    s = (store or 0) + (user or 0)
    if s >= 6:
        return 5
    if s >= 3:
        return 4
    if s >= 1:
        return 2
    return 1


def score_activity(rate):
    """D5 活跃度"""
    r = rate or 0
    if r >= 80:
        return 5
    if r >= 50:
        return 3
    if r >= 20:
        return 2
    return 1


def score_pay(pay):
    """D6 付费"""
    p = pay or 0
    if p >= 3000:
        return 5
    if p >= 1000:
        return 4
    if p >= 1:
        return 3
    return 1


def opp_score(d):
    """机会分 (0-100)"""
    store = d.get('storeNumber') or 0
    user = d.get('userNumber') or 0
    scale = min(30.0, (store + user) * 4)
    act = min(25.0, (d.get('loginDayRate') or 0) * 0.25)
    p = d.get('ext_payAmount') or 0
    if p >= 3000:
        pay_s = 25.0
    elif p >= 1000:
        pay_s = 18.0
    elif p >= 1:
        pay_s = 10.0
    else:
        pay_s = 0.0
    hard = d.get('ext_hardQuantity') or d.get('hardQuantity') or 0
    exps = (d.get('_detail') or {}).get('extend', {}).get('object', {}).get('expirationList') or []
    breadth = (10 if hard and hard > 0 else 0) + (10 if len(exps) >= 3 else (5 if exps else 0))
    return round(scale + act + pay_s + breadth, 1)


def opp_bonus(o):
    if o >= 50:
        return 3
    if o >= 30:
        return 2
    if o >= 15:
        return 1
    return 0


def min_expiry_days(d):
    """最近一次服务到期剩余天数（负值=已过期），None=无到期数据"""
    exps = (d.get('_detail') or {}).get('extend', {}).get('object', {}).get('expirationList') or []
    ends = [e.get('enableEnd') for e in exps if e.get('enableEnd')]
    if not ends:
        return None
    try:
        return (min(float(e) for e in ends) - NOW_MS) / DAY_MS
    except (TypeError, ValueError):
        return None


def get_expirations(d):
    """提取到期服务列表"""
    exps = (d.get('_detail') or {}).get('extend', {}).get('object', {}).get('expirationList') or []
    out = []
    for e in exps:
        end = e.get('enableEnd')
        name = e.get('serviceName') or '未命名服务'
        if end:
            try:
                days = (float(end) - NOW_MS) / DAY_MS
                out.append({'serviceName': name, 'enableEnd': end, 'days': round(days)})
            except (TypeError, ValueError):
                out.append({'serviceName': name, 'enableEnd': end, 'days': None})
        else:
            out.append({'serviceName': name, 'enableEnd': None, 'days': None})
    out.sort(key=lambda x: (x['days'] is None, x['days'] if x['days'] is not None else 0))
    return out


def grade_customer(d, scores, o, total):
    """分级 + 细分原因"""
    pay = d.get('ext_payAmount') or 0
    dv = days_since_visit(d.get('lastVisitTime'))
    it = (d.get('intention') or '').strip()
    ed = min_expiry_days(d)
    reasons = []

    # S 级
    if ed is not None and 0 <= ed <= 7:
        reasons.append(f'服务{ed:.0f}天内到期，紧急承接')
    if pay >= 3000 and dv is not None and dv > 365:
        reasons.append(f'高付费¥{pay:.0f}+{dv:.0f}天未回访')
    if it == '高':
        reasons.append('高意向客户')
    if reasons:
        return 'S', reasons

    # A2 级
    if ed is not None and 7 < ed <= 30:
        reasons.append(f'服务{ed:.0f}天内到期')
    if o >= 60:
        reasons.append(f'机会分{o:.0f}（高价值潜力）')
    if pay >= 3000 and dv is not None and dv > 180:
        reasons.append(f'高付费¥{pay:.0f}+{dv:.0f}天未回访')
    if ed is not None and ed < 0 and pay >= 3000:
        reasons.append(f'服务已过期{-ed:.0f}天，高付费¥{pay:.0f}待续费')
    if reasons:
        return 'A2', reasons

    # A3 级
    if o >= 40:
        reasons.append(f'机会分{o:.0f}')
    if total >= 22:
        reasons.append(f'综合评分{total}（较高）')
    if ed is not None and 30 < ed <= 90:
        reasons.append(f'服务{ed:.0f}天内到期')
    if ed is not None and ed < 0 and pay >= 1000 and dv is not None and dv > 90:
        reasons.append(f'已过期{-ed:.0f}天+{dv:.0f}天未回访，付费¥{pay:.0f}')
    if reasons:
        return 'A3', reasons

    # B 级
    if total >= 15:
        if dv is not None and dv > 90:
            reasons.append(f'{dv:.0f}天未回访')
        if (d.get('loginDayRate') or 0) < 20:
            reasons.append(f'活跃率{d.get("loginDayRate") or 0:.0f}%偏低')
        if not reasons:
            reasons.append(f'综合评分{total}（中等）')
        return 'B', reasons

    # C 级
    reasons.append(f'综合评分{total}（较低）')
    if (d.get('loginDayRate') or 0) < 20:
        reasons.append('活跃率低')
    if not pay:
        reasons.append('无付费记录')
    return 'C', reasons


# ---------------- 痛点/话术/动作生成 ----------------
INDUSTRY_TALK = {
    '服装鞋帽': '服装行业SKU多、季节性强，可围绕爆款备货、断码清仓、多店调拨场景切入，突出进销存与微商城联动。',
    '食品饮料': '食品保质期管理与批次追溯是刚需，可强调临期预警、批次召回、批次核算，结合商超便利渠道铺货。',
    '数码家电': '数码家电客单价高、序列号管理需求强，可切入串码追踪、保修期管理与以旧换新流程。',
    '美妆代购': '美妆代购多渠道分销，可围绕会员复购、套装组合、多仓发货与代理层级分账展开。',
    '母婴玩具': '母婴客群重视复购与会员运营，可切入会员积分、宝宝档案、周期复购提醒。',
    '烟酒茶叶': '烟酒茶叶批零兼营多，可强调批零差价、礼品盒装、客户赊账与业务员访销管理。',
    '珠宝饰品': '珠宝饰品高价值低频次，可围绕门店盘点、定制订单、会员储值与保养提醒。',
    '商超便利': '商超便利SKU海量、周转快，可突出快速收银、库存上下限预警、临期管理与自动补货。',
    '水果生鲜': '生鲜损耗大、保质期短，可切入损耗管理、每日盘点、预售拼团与配送路线。',
}
DEFAULT_TALK = '围绕您的进销存与多店管理痛点，可结合行业方案演示如何提升库存周转与对账效率。'


def gen_pain_points(d, scores):
    pts = []
    rate = d.get('loginDayRate') or 0
    pay = d.get('ext_payAmount') or 0
    dv = days_since_visit(d.get('lastVisitTime'))
    store = d.get('storeNumber') or 0
    user = d.get('userNumber') or 0
    hard = d.get('ext_hardQuantity') or d.get('hardQuantity') or 0
    ed = min_expiry_days(d)

    if rate < 20:
        pts.append(f'活跃度偏低（{rate:.0f}%），存在流失风险')
    if dv is not None and dv > 180:
        pts.append(f'已{dv:.0f}天未回访，客户关系疏离')
    if dv is None:
        pts.append('无回访记录，客户触达断层')
    if ed is not None and ed < 0:
        pts.append(f'服务已过期{-ed:.0f}天，亟待续费唤醒')
    elif ed is not None and 0 <= ed <= 30:
        pts.append(f'服务{ed:.0f}天内到期，续费窗口期')
    if pay < 1000 and rate >= 50:
        pts.append(f'付费深度不足（¥{pay:.0f}），活跃却未深度转化，可向上营销')
    if store >= 2 and user <= 1:
        pts.append(f'{store}家门店仅{user}个子账号，协同效率低')
    if not hard or hard == 0:
        pts.append('未配置硬件，盘点/收银场景未覆盖')
    if scores[4] <= 2 and rate >= 50:
        pts.append('活跃度有基础但未被有效运营激活')
    if not pts:
        pts.append('客户状态平稳，可常规维护并探索增购机会')
    return pts


def gen_talk_track(d):
    ind = d.get('regIndustry') or ''
    grade = d.get('_grade', '')
    base = INDUSTRY_TALK.get(ind, DEFAULT_TALK)
    grade_hook = {
        'S': '【紧急】',
        'A2': '【高优】',
        'A3': '【培养】',
        'B': '【维护】',
        'C': '【池养】',
    }.get(grade, '')
    return f'{grade_hook}{base}'


def gen_action(d, grade):
    pay = d.get('ext_payAmount') or 0
    ed = min_expiry_days(d)
    actions = {
        'S': '48小时内电话回访，推动服务续费/到期承接；同步确认客户当前经营状况与续费意向。',
        'A2': '本周内回访，结合到期节点促成续费或增购；准备行业方案与同类标杆案例。',
        'A3': '两周内触达，推送行业方案激活；通过微信/社群培育意向，挖掘增购点。',
        'B': '月度触达，保持客户关系；推送功能 tips 与活动，择机升级。',
        'C': '低成本批量触达（短信/社群），长期池养，关注活跃度回升信号。',
    }
    a = actions.get(grade, actions['C'])
    extras = []
    if ed is not None and ed < 0 and pay >= 1000:
        extras.append('优先推动到期服务续费（已过期高付费客户）。')
    if pay >= 3000:
        extras.append('高付费客户，关注续约与增购交叉销售。')
    if (d.get('storeNumber') or 0) >= 3:
        extras.append('多门店客户，可推荐多店协同方案与硬件套装。')
    return a + ('' if not extras else ' ' + ' '.join(extras))


# ---------------- 数据处理 ----------------
def mask_phone(s):
    """脱敏手机号：137****2267。同时处理纯数字串和包含手机号的文本。"""
    if not s:
        return s
    return re.sub(r'(\d{3})\d{4}(\d{4})', r'\1****\2', str(s))


def process_customer(d):
    D1 = score_visit(d.get('lastVisitTime'))
    D2 = score_industry(d.get('regIndustry'))
    D3 = score_business(d.get('businessType'), d.get('industryAttribute'))
    D4 = score_scale(d.get('storeNumber'), d.get('userNumber'))
    D5 = score_activity(d.get('loginDayRate'))
    D6 = score_pay(d.get('ext_payAmount'))
    o = opp_score(d)
    bonus = opp_bonus(o)
    total = D1 + D2 + D3 + D4 + D5 + D6 + bonus
    grade, reasons = grade_customer(d, (D1, D2, D3, D4, D5, D6), o, total)

    d['_grade'] = grade  # 供话术生成使用

    sys_type_map = {1: '进销存', 2: '微商城', 3: 'ERP'}
    sys_name = sys_type_map.get(d.get('sysType'), '未知')

    pay = d.get('ext_payAmount') or 0
    be_pay = d.get('beInviterPayAmount') or 0
    dv = days_since_visit(d.get('lastVisitTime'))

    rec = {
        'comName': mask_phone(d.get('comName') or '未命名'),
        'realName': mask_phone(d.get('realName') or d.get('crmRealName') or ''),
        'cellphone': mask_phone(d.get('cellphone_full') or d.get('cellphone') or ''),
        'cid': d.get('cid'),
        'counselor': counselor_name(d.get('counselorId')),
        'counselorId': d.get('counselorId'),
        'regIndustry': d.get('regIndustry') or '未填',
        'businessType': d.get('businessType') or '未填',
        'industryAttribute': d.get('industryAttribute') or '未填',
        'sysType': sys_name,
        'storeNumber': d.get('storeNumber') or 0,
        'userNumber': d.get('userNumber') or 0,
        'loginDayRate': round(d.get('loginDayRate') or 0, 1),
        'loginDays': d.get('loginDays') or 0,
        'allDays': d.get('allDays') or 0,
        'payAmount': round(pay, 2),
        'beInviterPayAmount': round(be_pay, 2),
        'hardQuantity': d.get('ext_hardQuantity') or d.get('hardQuantity') or 0,
        'lastVisitRecord': mask_phone((d.get('lastVisitRecord') or '').strip()),
        'lastVisitDays': (round(dv) if dv is not None else None),
        'visitTime': d.get('visitTime') or 0,
        'intention': (d.get('intention') or '').strip() or '未标注',
        'expirations': get_expirations(d),
        'scores': {'D1': D1, 'D2': D2, 'D3': D3, 'D4': D4, 'D5': D5, 'D6': D6,
                   'opp': o, 'bonus': bonus, 'total': total},
        'grade': grade,
        'reasons': reasons,
        'painPoints': gen_pain_points(d, (D1, D2, D3, D4, D5, D6)),
        'talkTrack': gen_talk_track(d),
        'action': gen_action(d, grade),
    }
    return rec


def fmt_money(v):
    if not v:
        return '¥0'
    if v >= 10000:
        return f'¥{v/10000:.2f}万'
    return f'¥{v:.0f}'


def fmt_date(ms):
    if not ms:
        return '-'
    try:
        t = time.localtime(float(ms) / 1000)
        return time.strftime('%Y-%m-%d', t)
    except (TypeError, ValueError, OverflowError):
        return '-'


# ---------------- HTML 生成 ----------------
HTML_TEMPLATE = r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>服务池SDR智能看板 · 成都分部</title>
<style>
:root{
  /* 浅黄主题 - 温暖专业 */
  --bg:#FFFBF0; --bg2:#FFF6E0; --card:#FFFFFF; --card2:#FFFEF7;
  --text:#3D2C1E; --text2:#8D6E63; --text3:#BFA08A;
  --border:#F0E2C4; --border2:#E8D5A8;
  --accent:#E65100; --accent2:#F57C00; --accent-soft:#FFF3E0; --accent-bg:#FFF8E1;
  --good:#2E7D32; --warn:#F57F17; --danger:#C62828;
  /* 分级色（柔和、与浅黄底协调） */
  --S:#FFCDD2; --A2:#FFE0B2; --A3:#FFF3C4; --B:#E6F0C8; --C:#D7E8C5;
  --S-t:#B71C1C; --A2-t:#E65100; --A3-t:#F57F17; --B-t:#558B2F; --C-t:#33691E;
  --shadow:0 1px 3px rgba(141,110,99,.08),0 1px 2px rgba(141,110,99,.04);
  --shadow-h:0 4px 12px rgba(141,110,99,.12),0 2px 4px rgba(141,110,99,.06);
  --radius:12px; --radius-s:8px;
}
@media (prefers-color-scheme: dark){
  :root{
    --bg:#1E1810; --bg2:#261E14; --card:#2A2118; --card2:#332920;
    --text:#F5E9D6; --text2:#BFA08A; --text3:#8D6E63;
    --border:#3D2E1F; --border2:#4D3A28;
    --accent:#FFB74D; --accent2:#FFA726; --accent-soft:#3D2E1F; --accent-bg:#332920;
    --S:#5D2A2A; --A2:#5D4221; --A3:#5D5021; --B:#3D5021; --C:#2A4A2A;
    --S-t:#FFCDD2; --A2-t:#FFE0B2; --A3-t:#FFF3C4; --B-t:#E6F0C8; --C-t:#D7E8C5;
    --shadow:0 1px 3px rgba(0,0,0,.3);
  }
}
[data-theme="dark"]{
  --bg:#1E1810; --bg2:#261E14; --card:#2A2118; --card2:#332920;
  --text:#F5E9D6; --text2:#BFA08A; --text3:#8D6E63;
  --border:#3D2E1F; --border2:#4D3A28;
  --accent:#FFB74D; --accent2:#FFA726; --accent-soft:#3D2E1F; --accent-bg:#332920;
  --S:#5D2A2A; --A2:#5D4221; --A3:#5D5021; --B:#3D5021; --C:#2A4A2A;
  --S-t:#FFCDD2; --A2-t:#FFE0B2; --A3-t:#FFF3C4; --B-t:#E6F0C8; --C-t:#D7E8C5;
  --shadow:0 1px 3px rgba(0,0,0,.3);
}
[data-theme="light"]{
  --bg:#FFFBF0; --bg2:#FFF6E0; --card:#FFFFFF; --card2:#FFFEF7;
  --text:#3D2C1E; --text2:#8D6E63; --text3:#BFA08A;
  --border:#F0E2C4; --border2:#E8D5A8;
  --accent:#E65100; --accent2:#F57C00; --accent-soft:#FFF3E0; --accent-bg:#FFF8E1;
  --S:#FFCDD2; --A2:#FFE0B2; --A3:#FFF3C4; --B:#E6F0C8; --C:#D7E8C5;
  --S-t:#B71C1C; --A2-t:#E65100; --A3-t:#F57F17; --B-t:#558B2F; --C-t:#33691E;
  --shadow:0 1px 3px rgba(141,110,99,.08),0 1px 2px rgba(141,110,99,.04);
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%}
body{font-family:"PingFang SC","Microsoft YaHei","微软雅黑",-apple-system,sans-serif;background:var(--bg);color:var(--text);line-height:1.5;font-size:14px;-webkit-font-smoothing:antialiased}
::-webkit-scrollbar{width:8px;height:8px}
::-webkit-scrollbar-thumb{background:var(--border2);border-radius:4px}
::-webkit-scrollbar-track{background:transparent}

/* ===== 顶栏 ===== */
.topbar{position:sticky;top:0;z-index:100;background:linear-gradient(135deg,var(--card) 0%,var(--card2) 100%);border-bottom:1px solid var(--border);padding:0 24px;display:flex;align-items:center;gap:20px;box-shadow:var(--shadow);min-height:60px}
.topbar .brand{display:flex;align-items:center;gap:10px;padding:10px 0}
.topbar .logo{width:32px;height:32px;border-radius:8px;background:linear-gradient(135deg,var(--accent) 0%,var(--accent2) 100%);display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:16px;box-shadow:0 2px 6px rgba(230,81,0,.3)}
.topbar .title{font-size:16px;font-weight:600;color:var(--text)}
.topbar .sub{font-size:11px;color:var(--text2);margin-top:1px}
.topbar .nav{display:flex;gap:2px;margin-left:8px}
.nav-item{padding:8px 14px;border-radius:8px;cursor:pointer;color:var(--text2);font-size:13px;font-weight:500;transition:all .15s;border:1px solid transparent}
.nav-item:hover{color:var(--accent);background:var(--accent-soft)}
.nav-item.active{color:var(--accent);background:var(--accent-soft);border-color:var(--border2);font-weight:600}
.nav-item .badge{display:inline-block;margin-left:4px;padding:1px 6px;border-radius:8px;background:var(--accent);color:#fff;font-size:10px;font-weight:600;min-width:16px;text-align:center}
.topbar .spacer{flex:1}
.iconbtn{width:34px;height:34px;border-radius:8px;border:1px solid var(--border);background:var(--card);color:var(--text2);cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:14px;transition:all .15s}
.iconbtn:hover{border-color:var(--accent);color:var(--accent)}

/* ===== 布局 ===== */
.page{display:none;padding:22px 24px 48px;max-width:1480px;margin:0 auto}
.page.active{display:block;animation:fade .2s ease}
@keyframes fade{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:translateY(0)}}

/* ===== KPI ===== */
.kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin-bottom:20px}
.kpi{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:16px 18px;box-shadow:var(--shadow);position:relative;overflow:hidden;transition:transform .15s,box-shadow .15s}
.kpi:hover{transform:translateY(-1px);box-shadow:var(--shadow-h)}
.kpi .lbl{font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:.3px;font-weight:600}
.kpi .val{font-size:26px;font-weight:700;margin-top:6px;color:var(--text);line-height:1.1}
.kpi .val small{font-size:12px;font-weight:500;color:var(--text2);margin-left:4px}
.kpi .delta{font-size:11px;color:var(--text2);margin-top:4px}
.kpi.grade{border-left:4px solid var(--border2)}
.kpi.grade.S{border-left-color:#E53935;background:linear-gradient(135deg,var(--S) 0%,var(--card) 50%)}
.kpi.grade.A2{border-left-color:var(--accent2);background:linear-gradient(135deg,var(--A2) 0%,var(--card) 50%)}
.kpi.grade.A3{border-left-color:var(--warn);background:linear-gradient(135deg,var(--A3) 0%,var(--card) 50%)}
.kpi.grade.B{border-left-color:#7CB342;background:linear-gradient(135deg,var(--B) 0%,var(--card) 50%)}
.kpi.grade.C{border-left-color:#558B2F;background:linear-gradient(135deg,var(--C) 0%,var(--card) 50%)}

/* ===== 图表 ===== */
.charts-row{display:grid;grid-template-columns:1.1fr 1fr 1fr;gap:16px;margin-bottom:8px}
.chart-card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:18px;box-shadow:var(--shadow)}
.chart-card h3{font-size:13px;font-weight:600;color:var(--text);margin-bottom:4px;display:flex;align-items:center;gap:6px}
.chart-card .sub{font-size:11px;color:var(--text2);margin-bottom:12px}
.chart-card canvas{width:100%;display:block}
@media(max-width:980px){.charts-row{grid-template-columns:1fr}}

/* ===== 到期预警专用 ===== */
.exp-summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:18px}
.exp-bucket{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:14px 16px;cursor:pointer;transition:all .15s;position:relative;overflow:hidden}
.exp-bucket:hover{transform:translateY(-2px);box-shadow:var(--shadow-h);border-color:var(--accent2)}
.exp-bucket.active{border-color:var(--accent);background:var(--accent-bg);box-shadow:0 0 0 2px var(--accent-soft)}
.exp-bucket .b-lbl{font-size:11px;color:var(--text2);font-weight:600;letter-spacing:.3px}
.exp-bucket .b-val{font-size:24px;font-weight:700;margin-top:4px;color:var(--text)}
.exp-bucket .b-bar{height:3px;border-radius:2px;margin-top:10px;background:var(--border)}
.exp-bucket .b-bar > i{display:block;height:100%;border-radius:2px;background:var(--accent2);transition:width .3s}
.exp-bucket.danger .b-val{color:var(--danger)}
.exp-bucket.danger .b-bar > i{background:var(--danger)}
.exp-bucket.warn .b-val{color:var(--warn)}
.exp-bucket.warn .b-bar > i{background:var(--warn)}
.exp-bucket.good .b-val{color:var(--good)}
.exp-bucket.good .b-bar > i{background:var(--good)}

/* 时间轴 */
.timeline{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:16px 20px;margin-bottom:18px;box-shadow:var(--shadow)}
.timeline h3{font-size:13px;font-weight:600;margin-bottom:12px;color:var(--text)}
.tl-bar{display:flex;height:38px;border-radius:8px;overflow:hidden;border:1px solid var(--border);background:var(--bg2)}
.tl-seg{position:relative;transition:filter .15s;cursor:pointer}
.tl-seg:hover{filter:brightness(1.08)}
.tl-seg .tl-tip{position:absolute;bottom:calc(100% + 6px);left:50%;transform:translateX(-50%);background:var(--text);color:var(--bg);padding:4px 8px;border-radius:6px;font-size:11px;white-space:nowrap;opacity:0;pointer-events:none;transition:opacity .15s;z-index:5}
.tl-seg:hover .tl-tip{opacity:1}
.tl-legend{display:flex;flex-wrap:wrap;gap:14px;margin-top:10px;font-size:11px;color:var(--text2)}
.tl-legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px;vertical-align:middle}

/* 表格 */
.filters{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:14px 16px;margin-bottom:14px;display:flex;flex-wrap:wrap;gap:12px;align-items:center;box-shadow:var(--shadow)}
.filters .fgroup{display:flex;align-items:center;gap:6px}
.filters label{font-size:11px;color:var(--text2);font-weight:600;letter-spacing:.2px;text-transform:uppercase}
.filters select,.filters input{padding:7px 12px;border:1px solid var(--border);border-radius:var(--radius-s);background:var(--card2);color:var(--text);font-size:13px;font-family:inherit;transition:border-color .15s}
.filters select:focus,.filters input:focus{outline:none;border-color:var(--accent2)}
.filters input{flex:1;min-width:200px}
.filters .stat{margin-left:auto;font-size:12px;color:var(--text2);font-weight:500}
.grade-chips{display:flex;gap:5px;flex-wrap:wrap}
.chip{padding:4px 12px;border-radius:14px;font-size:12px;cursor:pointer;border:1px solid var(--border);background:var(--card);color:var(--text2);user-select:none;font-weight:500;transition:all .12s}
.chip:hover{border-color:var(--accent2);color:var(--accent)}
.chip.active{background:var(--accent);color:#fff;border-color:var(--accent);box-shadow:0 2px 6px rgba(230,81,0,.25)}

.table-wrap{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;box-shadow:var(--shadow)}
table{width:100%;border-collapse:collapse;font-size:13px}
thead th{background:var(--accent-bg);color:var(--text);padding:11px 12px;text-align:left;font-weight:600;position:sticky;top:0;white-space:nowrap;border-bottom:1px solid var(--border2);font-size:12px;letter-spacing:.2px}
thead th.center{text-align:center}
tbody td{padding:10px 12px;border-bottom:1px solid var(--border);vertical-align:middle}
tbody tr:last-child td{border-bottom:none}
tbody tr{cursor:pointer;transition:background .1s}
tbody tr:hover{background:var(--accent-soft)}
tbody tr.expanded{background:var(--accent-soft)}
.grade-tag{display:inline-block;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:700;white-space:nowrap;letter-spacing:.3px}
.grade-tag.S{background:var(--S);color:var(--S-t)}
.grade-tag.A2{background:var(--A2);color:var(--A2-t)}
.grade-tag.A3{background:var(--A3);color:var(--A3-t)}
.grade-tag.B{background:var(--B);color:var(--B-t)}
.grade-tag.C{background:var(--C);color:var(--C-t)}
.prio{display:inline-flex;align-items:center;justify-content:center;min-width:28px;height:24px;padding:0 8px;border-radius:6px;font-size:11px;font-weight:700;color:#fff;background:var(--text3);letter-spacing:.3px}
.prio.p1{background:var(--danger);box-shadow:0 1px 3px rgba(198,40,40,.3)}
.prio.p2{background:var(--accent2);box-shadow:0 1px 3px rgba(245,124,0,.3)}
.prio.p3{background:var(--warn);color:#3D2C1E}
.prio.p4{background:var(--good)}
.prio.p5{background:var(--text3)}
.muted{color:var(--text2)}
.tnum{font-variant-numeric:tabular-nums;font-feature-settings:"tnum"}
.reasons{font-size:11.5px;color:var(--text2);max-width:240px;line-height:1.45}
.reasons span{display:inline-block;margin-right:6px;padding:1px 6px;border-radius:4px;background:var(--accent-bg);color:var(--text)}
.detail-row td{background:var(--bg2);padding:0;border-bottom:1px solid var(--border)}
.detail-box{padding:18px 20px;display:grid;grid-template-columns:1fr 1fr 1fr;gap:18px}
.detail-box .block h4{font-size:12px;color:var(--accent);margin-bottom:8px;font-weight:700;letter-spacing:.3px;text-transform:uppercase;display:flex;align-items:center;gap:6px}
.detail-box .block h4:before{content:"";width:3px;height:12px;background:var(--accent);border-radius:2px}
.detail-box .block ul{list-style:none;padding-left:0}
.detail-box .block li{font-size:12px;padding:4px 0;color:var(--text);position:relative;padding-left:14px;line-height:1.5}
.detail-box .block li:before{content:"";position:absolute;left:4px;top:11px;width:4px;height:4px;border-radius:50%;background:var(--accent2)}
.detail-box .block .tt{font-size:12.5px;color:var(--text);line-height:1.65;padding:8px 12px;background:var(--card);border-radius:8px;border:1px solid var(--border)}
.score-bar{display:inline-flex;gap:2px;align-items:center}
.score-cell{display:inline-block;width:18px;height:18px;border-radius:4px;background:var(--bg2);text-align:center;line-height:18px;font-size:10px;color:var(--text2);font-weight:700}
.score-cell.s5{background:#558B2F;color:#fff}
.score-cell.s4{background:#9CCC65;color:#fff}
.score-cell.s3{background:#F0C419;color:#3D2C1E}
.score-cell.s2{background:#FFB74D;color:#fff}
.score-cell.s1{background:#E57373;color:#fff}
@media(max-width:800px){.detail-box{grid-template-columns:1fr}}
.pager{display:flex;justify-content:center;align-items:center;gap:6px;padding:16px;flex-wrap:wrap}
.pager button{padding:7px 14px;border:1px solid var(--border);border-radius:var(--radius-s);background:var(--card);color:var(--text);cursor:pointer;font-size:13px;font-family:inherit;transition:all .12s}
.pager button:hover:not(:disabled){border-color:var(--accent);color:var(--accent)}
.pager button:disabled{opacity:.4;cursor:not-allowed}
.pager button.active{background:var(--accent);color:#fff;border-color:var(--accent)}
.pager .info{font-size:12px;color:var(--text2);margin:0 8px}
.no-data{text-align:center;padding:60px 20px;color:var(--text2)}
.no-data .ico{font-size:32px;margin-bottom:8px;opacity:.5}
.exp-tag{display:inline-flex;align-items:center;gap:4px;padding:3px 9px;border-radius:6px;font-size:11px;font-weight:600}
.exp-tag.danger{background:#FFEBEE;color:#C62828}
.exp-tag.warn{background:#FFF8E1;color:#F57F17}
.exp-tag.info{background:#E3F2FD;color:#1565C0}
.exp-tag.muted{background:var(--bg2);color:var(--text2)}
.svc-pill{display:inline-block;padding:2px 8px;margin:2px 2px 2px 0;border-radius:4px;background:var(--accent-bg);color:var(--accent-t,var(--accent));font-size:11px;border:1px solid var(--border)}
.counselor-tag{display:inline-block;padding:2px 9px;border-radius:6px;background:var(--accent-soft);color:var(--accent);font-size:11px;font-weight:600;border:1px solid var(--border2);white-space:nowrap}
.kpi-mini{font-size:10px;color:var(--text2);margin-top:6px;display:flex;gap:8px}
.kpi-mini span b{color:var(--text);font-weight:600}
.foot{text-align:center;color:var(--text3);font-size:11px;padding:18px 0;border-top:1px solid var(--border);margin-top:24px}
</style>
</head>
<body>
<div class="topbar">
  <div class="brand">
    <div class="logo">SDR</div>
    <div>
      <div class="title">服务池智能分级看板</div>
      <div class="sub" id="subInfo">成都分部 · 服务池客户智能分级系统</div>
    </div>
  </div>
  <div class="nav">
    <div class="nav-item active" data-page="overview">总览</div>
    <div class="nav-item" data-page="expiring">到期预警<span class="badge" id="expBadge">0</span></div>
    <div class="nav-item" data-page="list">客户列表</div>
  </div>
  <div class="spacer"></div>
  <button class="iconbtn" id="themeBtn" title="切换主题">🌙</button>
</div>

<!-- ====== 总览 ====== -->
<div id="page-overview" class="page active">
  <div class="kpi-grid" id="kpiGrid"></div>
  <div class="charts-row">
    <div class="chart-card">
      <h3>分级分布</h3>
      <div class="sub">S/A2/A3/B/C 五档客户占比</div>
      <canvas id="pieChart" height="260"></canvas>
    </div>
    <div class="chart-card">
      <h3>行业分布 TOP10</h3>
      <div class="sub">按客户数量排序</div>
      <canvas id="indChart" height="260"></canvas>
    </div>
    <div class="chart-card">
      <h3>业务类型分布</h3>
      <div class="sub">零售/批发/批零一体占比</div>
      <canvas id="bizChart" height="260"></canvas>
    </div>
  </div>
  <div class="chart-card" style="margin-top:16px">
    <h3>顾问客户分布</h3>
    <div class="sub">按服务池归属顾问统计 · 点击切换客户列表筛选</div>
    <div id="counselorBars" style="display:flex;flex-direction:column;gap:10px;margin-top:8px"></div>
  </div>
</div>

<!-- ====== 到期预警 ====== -->
<div id="page-expiring" class="page">
  <div class="exp-summary" id="expSummary"></div>
  <div class="timeline">
    <h3>到期时间分布</h3>
    <div class="tl-bar" id="tlBar"></div>
    <div class="tl-legend" id="tlLegend"></div>
  </div>
  <div class="filters">
    <div class="grade-chips" id="expChips">
      <span class="chip active" data-exp="60">60天内</span>
      <span class="chip" data-exp="30">30天内</span>
      <span class="chip" data-exp="7">7天内</span>
      <span class="chip" data-exp="0">已过期</span>
      <span class="chip" data-exp="none">未设置到期</span>
      <span class="chip" data-exp="all">全部</span>
    </div>
    <div class="fgroup">
      <label>归属顾问</label>
      <select id="expCounselorFilter"><option value="">全部顾问</option></select>
    </div>
    <div class="fgroup">
      <label>到期产品</label>
      <select id="expProdFilter"><option value="">全部产品</option></select>
    </div>
    <input id="expSearch" type="text" placeholder="搜索公司名/CID/行业..." style="max-width:240px">
    <div class="stat" id="expStat"></div>
  </div>
  <div class="table-wrap">
    <table>
      <thead><tr>
        <th class="center">紧急度</th><th class="center">分级</th><th>公司名称</th><th>CID</th><th>归属顾问</th><th>行业</th>
        <th>到期服务</th><th>到期时间</th><th class="center">剩余天数</th><th>付费金额</th><th>建议动作</th>
      </tr></thead>
      <tbody id="expTbody"></tbody>
    </table>
  </div>
</div>

<!-- ====== 客户列表 ====== -->
<div id="page-list" class="page">
  <div class="filters">
    <div class="fgroup">
      <label>分级</label>
      <div class="grade-chips" id="gradeChips">
        <span class="chip active" data-grade="">全部</span>
        <span class="chip" data-grade="S" style="background:var(--S);color:var(--S-t)">S</span>
        <span class="chip" data-grade="A2" style="background:var(--A2);color:var(--A2-t)">A2</span>
        <span class="chip" data-grade="A3" style="background:var(--A3);color:var(--A3-t)">A3</span>
        <span class="chip" data-grade="B" style="background:var(--B);color:var(--B-t)">B</span>
        <span class="chip" data-grade="C" style="background:var(--C);color:var(--C-t)">C</span>
      </div>
    </div>
    <div class="fgroup">
      <label>行业</label>
      <select id="indFilter"><option value="">全部行业</option></select>
    </div>
    <div class="fgroup">
      <label>业务</label>
      <select id="bizFilter"><option value="">全部业务</option></select>
    </div>
    <div class="fgroup">
      <label>顾问</label>
      <select id="counselorFilter"><option value="">全部顾问</option></select>
    </div>
    <input id="search" type="text" placeholder="搜索公司名/联系人/CID...">
    <div class="stat" id="filterStat"></div>
  </div>
  <div class="table-wrap">
    <table>
      <thead><tr>
        <th class="center">优先级</th><th class="center">分级</th><th>公司名称</th><th>联系人</th><th>CID</th><th>归属顾问</th>
        <th>行业</th><th>业务</th><th class="center">活跃率</th><th>付费金额</th><th class="center">评分</th><th>细分原因</th>
      </tr></thead>
      <tbody id="tbody"></tbody>
    </table>
    <div class="pager" id="pager"></div>
  </div>
</div>

<div class="foot">服务池SDR智能分级系统 · 数据源:秦丝CRM成都分部服务池 · 手机号已脱敏，客户唯一标识为CID · 生成于 __GEN_TIME__</div>

<script>
const DATA=__DATA_JSON__;
const META=__META_JSON__;

/* ===== 主题 ===== */
const themeBtn=document.getElementById('themeBtn');
function setTheme(t){document.documentElement.setAttribute('data-theme',t);themeBtn.textContent=t==='dark'?'☀️':'🌙';localStorage.setItem('sdr-theme',t);drawAllCharts();}
themeBtn.onclick=()=>{const c=document.documentElement.getAttribute('data-theme')||'light';setTheme(c==='dark'?'light':'dark');};
const savedTheme=localStorage.getItem('sdr-theme');
if(savedTheme)setTheme(savedTheme);
else if(window.matchMedia&&window.matchMedia('(prefers-color-scheme:dark)').matches)setTheme('dark');

/* ===== 导航 ===== */
document.querySelectorAll('.nav-item').forEach(t=>{
  t.onclick=()=>{
    document.querySelectorAll('.nav-item').forEach(x=>x.classList.remove('active'));
    document.querySelectorAll('.page').forEach(x=>x.classList.remove('active'));
    t.classList.add('active');
    document.getElementById('page-'+t.dataset.page).classList.add('active');
    if(t.dataset.page==='overview')drawAllCharts();
    if(t.dataset.page==='expiring')renderExpiring();
  };
});

/* ===== 工具 ===== */
function cssVar(n){return getComputedStyle(document.documentElement).getPropertyValue(n).trim();}
function gradeColor(g){return cssVar('--'+g)||'#ccc';}
function textColor(){return cssVar('--text');}
function text2Color(){return cssVar('--text2');}
function borderColor(){return cssVar('--border');}
function accentColor(){return cssVar('--accent');}
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));}
function fmtMoney(v){if(!v)return '¥0';if(v>=10000)return '¥'+(v/10000).toFixed(2)+'万';return '¥'+Math.round(v);}
function fmtDate(ms){if(!ms)return '-';const d=new Date(ms);return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');}

/* ===== KPI ===== */
function renderKPI(){
  const g={S:0,A2:0,A3:0,B:0,C:0};
  let totalPay=0,exp60=0,exp7=0,overdue=0;
  DATA.forEach(c=>{
    g[c.grade]=(g[c.grade]||0)+1;
    totalPay+=c.payAmount;
    (c.expirations||[]).forEach(e=>{
      if(e.days===null||e.days===undefined)return;
      if(e.days<0)overdue++;
      else if(e.days<=7)exp7++;
      else if(e.days<=60)exp60++;
    });
  });
  const total=DATA.length;
  const expSoon=exp60+exp7;
  document.getElementById('expBadge').textContent=expSoon;
  const items=[
    {lbl:'总客户数',val:total,cls:'',mini:'<span>付费客户 <b>'+DATA.filter(c=>c.payAmount>0).length+'</b></span><span>有到期服务 <b>'+DATA.filter(c=>(c.expirations||[]).length).length+'</b></span>'},
    {lbl:'S · 紧急',val:g.S,cls:'grade S',mini:'<span>占比 <b>'+(g.S/total*100).toFixed(1)+'%</b></span>'},
    {lbl:'A2 · 高优',val:g.A2,cls:'grade A2',mini:'<span>占比 <b>'+(g.A2/total*100).toFixed(1)+'%</b></span>'},
    {lbl:'A3 · 培养',val:g.A3,cls:'grade A3',mini:'<span>占比 <b>'+(g.A3/total*100).toFixed(1)+'%</b></span>'},
    {lbl:'B · 维护',val:g.B,cls:'grade B',mini:'<span>占比 <b>'+(g.B/total*100).toFixed(1)+'%</b></span>'},
    {lbl:'C · 池养',val:g.C,cls:'grade C',mini:'<span>占比 <b>'+(g.C/total*100).toFixed(1)+'%</b></span>'},
    {lbl:'总付费金额',val:fmtMoney(totalPay),cls:'',mini:'<span>人均 <b>'+fmtMoney(totalPay/total)+'</b></span>'},
    {lbl:'60天内到期',val:expSoon,cls:'',mini:'<span>7天内 <b style="color:var(--danger)">'+exp7+'</b></span><span>已过期 <b>'+overdue+'</b></span>'},
  ];
  document.getElementById('kpiGrid').innerHTML=items.map(it=>
    '<div class="kpi '+it.cls+'"><div class="lbl">'+it.lbl+'</div><div class="val">'+it.val+'</div>'+
    (it.mini?'<div class="kpi-mini">'+it.mini+'</div>':'')+'</div>'
  ).join('');
  document.getElementById('subInfo').textContent='成都分部 · 服务池 '+total+' 客户 · 总付费 '+fmtMoney(totalPay)+' · 60天内到期 '+expSoon+' 条';
}

/* ===== Canvas ===== */
function setupCanvas(cv){
  const dpr=window.devicePixelRatio||1;
  const w=cv.clientWidth||cv.parentElement.clientWidth-36;
  const h=parseInt(cv.getAttribute('height'))||260;
  cv.width=w*dpr;cv.height=h*dpr;cv.style.height=h+'px';
  const ctx=cv.getContext('2d');ctx.scale(dpr,dpr);
  ctx.clearRect(0,0,w,h);
  return {ctx,w,h};
}
function drawPie(){
  const cv=document.getElementById('pieChart');
  const {ctx,w,h}=setupCanvas(cv);
  const grades=['S','A2','A3','B','C'];
  const data=grades.map(g=>({g,n:DATA.filter(c=>c.grade===g).length}));
  const total=data.reduce((s,d)=>s+d.n,0);
  if(total===0)return;
  const cx=w*0.34,cy=h/2,R=Math.min(w*0.34,h*0.42);
  let a=-Math.PI/2;
  data.forEach(d=>{
    if(d.n===0)return;
    const ang=d.n/total*Math.PI*2;
    ctx.beginPath();ctx.moveTo(cx,cy);ctx.arc(cx,cy,R,a,a+ang);ctx.closePath();
    ctx.fillStyle=gradeColor(d.g);ctx.fill();
    ctx.strokeStyle=cssVar('--card');ctx.lineWidth=3;ctx.stroke();
    a+=ang;
  });
  ctx.fillStyle=textColor();ctx.font='bold 26px "PingFang SC","Microsoft YaHei"';
  ctx.textAlign='center';ctx.textBaseline='middle';
  ctx.fillText(total,cx,cy-8);
  ctx.fillStyle=text2Color();ctx.font='11px "PingFang SC"';
  ctx.fillText('总客户',cx,cy+14);
  const lx=w*0.66;
  let ly=h/2-(data.length*22)/2+10;
  ctx.font='12px "PingFang SC"';ctx.textAlign='left';ctx.textBaseline='middle';
  data.forEach(d=>{
    ctx.fillStyle=gradeColor(d.g);
    ctx.fillRect(lx,ly-6,12,12);
    ctx.fillStyle=textColor();
    ctx.fillText(d.g+'  '+d.n+' ('+(d.n/total*100).toFixed(1)+'%)',lx+18,ly);
    ly+=22;
  });
}
function drawBar(cv,items,opts){
  const {ctx,w,h}=setupCanvas(cv);
  if(!items.length)return;
  const padL=opts.padL||44,padR=12,padT=16,padB=48;
  const cw=w-padL-padR,ch=h-padT-padB;
  const maxV=Math.max.apply(null,items.map(i=>i.v))||1;
  const niceMax=Math.ceil(maxV/Math.pow(10,Math.floor(Math.log10(maxV))))*Math.pow(10,Math.floor(Math.log10(maxV)))||1;
  const gap=cw/items.length,bw=gap*0.62;
  ctx.strokeStyle=borderColor();ctx.fillStyle=text2Color();ctx.font='10px "PingFang SC"';ctx.textAlign='right';ctx.textBaseline='middle';
  const steps=4;
  for(let i=0;i<=steps;i++){
    const v=niceMax*i/steps;
    const y=padT+ch-ch*i/steps;
    ctx.beginPath();ctx.moveTo(padL,y);ctx.lineTo(w-padR,y);ctx.strokeStyle=borderColor();ctx.globalAlpha=.5;ctx.stroke();ctx.globalAlpha=1;
    ctx.fillText(fmtTick(v),padL-6,y);
  }
  const colors=opts.colors||[accentColor()];
  items.forEach((it,i)=>{
    const x=padL+i*gap+(gap-bw)/2;
    const bh=ch*(it.v/niceMax);
    const y=padT+ch-bh;
    const col=Array.isArray(colors)?(colors[i%colors.length]):colors;
    ctx.fillStyle=col;
    const r=Math.min(4,bw/2);
    ctx.beginPath();
    ctx.moveTo(x,y+r);ctx.arcTo(x,y,x+bw,y+r,r);ctx.arcTo(x+bw,y,x+bw,y+bh,r);ctx.lineTo(x+bw,y+bh);ctx.lineTo(x,y+bh);ctx.closePath();ctx.fill();
    ctx.fillStyle=textColor();ctx.font='bold 11px "PingFang SC"';ctx.textAlign='center';ctx.textBaseline='bottom';
    ctx.fillText(it.v,x+bw/2,y-3);
    ctx.fillStyle=text2Color();ctx.font='11px "PingFang SC"';ctx.textBaseline='top';
    const lbl=it.l.length>6?it.l.slice(0,6):it.l;
    ctx.fillText(lbl,x+bw/2,padT+ch+8);
  });
}
function fmtTick(v){if(v>=1000)return (v/1000)+'k';return Math.round(v);}
function drawIndChart(){
  const cv=document.getElementById('indChart');
  const cnt={};
  DATA.forEach(c=>{cnt[c.regIndustry]=(cnt[c.regIndustry]||0)+1;});
  const items=Object.keys(cnt).map(k=>({l:k,v:cnt[k]})).sort((a,b)=>b.v-a.v).slice(0,10);
  const palette=['#E65100','#F57C00','#FB8C00','#FFA726','#FFB74D','#FFCA28','#FFD54F','#FFE082','#FFECB3','#FFF59D'];
  drawBar(cv,items,{padL:48,colors:palette});
}
function drawBizChart(){
  const cv=document.getElementById('bizChart');
  const cnt={};
  DATA.forEach(c=>{const k=c.businessType||'未填';cnt[k]=(cnt[k]||0)+1;});
  const items=Object.keys(cnt).map(k=>({l:k,v:cnt[k]})).sort((a,b)=>b.v-a.v);
  const palette=['#E65100','#F57C00','#FFA726','#FFCA28','#9CCC65','#558B2F','#BFA08A'];
  drawBar(cv,items,{padL:48,colors:palette});
}
function drawAllCharts(){renderKPI();drawPie();drawIndChart();drawBizChart();renderCounselorBars();}
function renderCounselorBars(){
  const cnt={};
  DATA.forEach(c=>{cnt[c.counselor]=(cnt[c.counselor]||0)+1;});
  const items=Object.keys(cnt).map(k=>({name:k,n:cnt[k]})).sort((a,b)=>b.n-a.n);
  const maxN=Math.max.apply(null,items.map(i=>i.n))||1;
  const total=DATA.length;
  const box=document.getElementById('counselorBars');
  if(!box)return;
  box.innerHTML=items.map(it=>{
    const pct=(it.n/maxN*100).toFixed(1);
    const share=(it.n/total*100).toFixed(1);
    return '<div class="cou-bar" data-name="'+esc(it.name)+'" style="display:flex;align-items:center;gap:10px;cursor:pointer;padding:6px 8px;border-radius:8px;transition:background .12s">'+
      '<div style="min-width:90px;font-size:13px;font-weight:600;color:var(--text)">'+esc(it.name)+'</div>'+
      '<div style="flex:1;height:24px;background:var(--bg2);border-radius:6px;overflow:hidden;border:1px solid var(--border)">'+
        '<div style="height:100%;width:'+pct+'%;background:linear-gradient(90deg,var(--accent) 0%,var(--accent2) 100%);border-radius:6px;transition:width .3s"></div>'+
      '</div>'+
      '<div style="min-width:100px;text-align:right;font-size:13px"><b style="color:var(--text)">'+it.n+'</b> <span style="color:var(--text2);font-size:11px">('+share+'%)</span></div>'+
    '</div>';
  }).join('');
  box.querySelectorAll('.cou-bar').forEach(b=>{
    b.onmouseenter=()=>b.style.background='var(--accent-soft)';
    b.onmouseleave=()=>b.style.background='';
    b.onclick=()=>{
      /* 跳转客户列表并筛选该顾问 */
      document.querySelectorAll('.nav-item').forEach(x=>x.classList.remove('active'));
      document.querySelectorAll('.page').forEach(x=>x.classList.remove('active'));
      document.querySelector('.nav-item[data-page="list"]').classList.add('active');
      document.getElementById('page-list').classList.add('active');
      curCounselor=b.dataset.name;
      const cs=document.getElementById('counselorFilter');
      cs.value=b.dataset.name;
      applyFilter();
    };
  });
}
window.addEventListener('resize',()=>{if(document.getElementById('page-overview').classList.contains('active'))drawAllCharts();});

/* ===== 到期预警 ===== */
let expRange=60,expSearch='',expProd='',expCounselor='';
let expList=[];
let expBuckets={};

function buildExpBuckets(){
  expBuckets={exp7:0,exp30:0,exp60:0,overdue:0,none:0};
  DATA.forEach(c=>{
    const exps=c.expirations||[];
    if(!exps.length)return;
    let hasNone=false,earliest=null;
    exps.forEach(e=>{
      if(e.days===null||e.days===undefined){hasNone=true;return;}
      if(earliest===null||e.days<earliest)earliest=e.days;
    });
    if(hasNone&&earliest===null){expBuckets.none++;return;}
    if(earliest!==null){
      if(earliest<0)expBuckets.overdue++;
      else if(earliest<=7)expBuckets.exp7++;
      else if(earliest<=30)expBuckets.exp30++;
      else if(earliest<=60)expBuckets.exp60++;
    }
    if(hasNone&&earliest!==null)expBuckets.none++;
  });
}
function renderExpSummary(){
  const sum=document.getElementById('expSummary');
  const items=[
    {key:'exp7',lbl:'7天内到期',cls:'danger',range:7},
    {key:'exp30',lbl:'30天内到期',cls:'warn',range:30},
    {key:'exp60',lbl:'60天内到期',cls:'warn',range:60},
    {key:'overdue',lbl:'已过期',cls:'danger',range:0},
    {key:'none',lbl:'未设置到期',cls:'',range:'none'},
  ];
  const maxV=Math.max(1,expBuckets.exp7+expBuckets.exp30+expBuckets.exp60+expBuckets.overdue+expBuckets.none);
  sum.innerHTML=items.map(it=>{
    const v=expBuckets[it.key]||0;
    const pct=(v/maxV*100).toFixed(0);
    return '<div class="exp-bucket '+it.cls+'" data-range="'+it.range+'">'+
      '<div class="b-lbl">'+it.lbl+'</div>'+
      '<div class="b-val">'+v+'</div>'+
      '<div class="b-bar"><i style="width:'+pct+'%"></i></div>'+
    '</div>';
  }).join('');
  sum.querySelectorAll('.exp-bucket').forEach(b=>{
    b.onclick=()=>{
      const r=b.dataset.range;
      document.querySelectorAll('#expChips .chip').forEach(c=>c.classList.remove('active'));
      const chip=document.querySelector('#expChips .chip[data-exp="'+r+'"]');
      if(chip){chip.classList.add('active');expRange=(r==='none'||r==='all')?r:parseInt(r);}
      else{expRange=60;document.querySelector('#expChips .chip[data-exp="60"]').classList.add('active');}
      renderExpiring();
    };
  });
}
function renderTimeline(){
  const bar=document.getElementById('tlBar');
  const segs=[
    {lbl:'7天内',n:expBuckets.exp7,color:'var(--danger)'},
    {lbl:'8-30天',n:expBuckets.exp30,color:'var(--accent2)'},
    {lbl:'31-60天',n:expBuckets.exp60,color:'var(--warn)'},
    {lbl:'已过期',n:expBuckets.overdue,color:'#9E9E9E'},
    {lbl:'未设置',n:expBuckets.none,color:'var(--border2)'},
  ];
  const total=segs.reduce((s,d)=>s+d.n,0)||1;
  bar.innerHTML=segs.map(s=>{
    const pct=(s.n/total*100).toFixed(2);
    if(parseFloat(pct)===0)return '';
    return '<div class="tl-seg" style="flex:'+pct+';background:'+s.color+'">'+
      '<div class="tl-tip">'+s.lbl+' · '+s.n+' 条 ('+(s.n/total*100).toFixed(1)+'%)</div></div>';
  }).join('');
  document.getElementById('tlLegend').innerHTML=segs.map(s=>
    '<span><i style="background:'+s.color+'"></i>'+s.lbl+' <b>'+s.n+'</b> ('+(s.n/total*100).toFixed(1)+'%)</span>'
  ).join('');
}
function renderExpiring(){
  expList=[];
  DATA.forEach(c=>{
    const exps=c.expirations||[];
    if(!exps.length)return;
    /* 产品筛选：如果选了产品，客户必须含该到期服务才显示 */
    let workingExps=exps;
    if(expProd){
      workingExps=exps.filter(e=>e.serviceName===expProd);
      if(!workingExps.length)return;
    }
    /* 按客户聚合：取最早到期服务作为主条目，其余作为附加 */
    const valid=workingExps.filter(e=>e.days!==null&&e.days!==undefined);
    const noDate=workingExps.filter(e=>e.days===null||e.days===undefined);
    let show=false;
    if(expRange==='all')show=true;
    else if(expRange==='none'){
      if(noDate.length>0)show=true;
    }else if(expRange===0){
      if(valid.some(e=>e.days<0))show=true;
    }else{
      if(valid.some(e=>e.days>=0&&e.days<=expRange))show=true;
    }
    if(!show)return;
    if(expSearch){
      const s=expSearch.toLowerCase();
      if(!(c.comName||'').toLowerCase().includes(s)&&!(String(c.cid||'')).toLowerCase().includes(s)&&!(c.regIndustry||'').toLowerCase().includes(s))return;
    }
    if(expCounselor && c.counselor!==expCounselor)return;
    /* 主到期服务：未过期且最早；若无未过期则取已过期最久 */
    let main=null;
    const future=valid.filter(e=>e.days>=0).sort((a,b)=>a.days-b.days);
    const past=valid.filter(e=>e.days<0).sort((a,b)=>b.days-a.days);
    if(expRange===0&&past.length)main=past[0];
    else if(future.length)main=future[0];
    else if(past.length)main=past[0];
    else main=noDate[0];
    const otherExps=workingExps.filter(e=>e!==main);
    expList.push({
      comName:c.comName,cid:c.cid,counselor:c.counselor,regIndustry:c.regIndustry,grade:c.grade,payAmount:c.payAmount,
      mainService:main?main.serviceName:'-',mainEnd:main?main.enableEnd:null,mainDays:main?main.days:null,
      otherExps:otherExps,talkTrack:c.talkTrack,action:c.action,painPoints:c.painPoints,
      allExps:workingExps
    });
  });
  expList.sort((a,b)=>{
    const da=a.mainDays,db=b.mainDays;
    if(da===null&&db===null)return 0;
    if(da===null)return 1;
    if(db===null)return -1;
    if(da>=0&&db>=0)return da-db;
    if(da<0&&db<0)return db-da;
    return da>=0?-1:1;
  });
  document.getElementById('expStat').textContent='共 '+expList.length+' 个客户';
  const tb=document.getElementById('expTbody');
  if(!expList.length){tb.innerHTML='<tr><td colspan="11" class="no-data"><div class="ico">📭</div>无符合条件的到期客户</td></tr>';return;}
  tb.innerHTML=expList.map((c,i)=>{
    let urgent,cls,tag;
    const d=c.mainDays;
    if(d===null){urgent='未设置';cls='p5';tag='<span class="exp-tag muted">未设置到期</span>';}
    else if(d<0){urgent='已过期';cls='p1';tag='<span class="exp-tag danger">过期 '+(-d)+' 天</span>';}
    else if(d<=7){urgent='紧急';cls='p1';tag='<span class="exp-tag danger">'+d+' 天</span>';}
    else if(d<=30){urgent='高';cls='p2';tag='<span class="exp-tag warn">'+d+' 天</span>';}
    else{urgent='中';cls='p3';tag='<span class="exp-tag info">'+d+' 天</span>';}
    let dateText=c.mainEnd?fmtDate(c.mainEnd):'<span class="muted">未设置</span>';
    let svcText=esc(c.mainService);
    if(c.otherExps.length>0)svcText+='<div style="margin-top:4px"><span class="muted" style="font-size:11px">+'+c.otherExps.length+' 项:</span> '+c.otherExps.slice(0,3).map(e=>'<span class="svc-pill">'+esc(e.serviceName)+'</span>').join('')+(c.otherExps.length>3?'<span class="muted" style="font-size:11px">等'+c.otherExps.length+'项</span>':'')+'</div>';
    const act=(c.action||'');
    const actShort=act.length>50?act.slice(0,50)+'…':act;
    return '<tr data-exp-idx="'+i+'">'+
      '<td class="center"><span class="prio '+cls+'">'+urgent+'</span></td>'+
      '<td class="center"><span class="grade-tag '+c.grade+'">'+c.grade+'</span></td>'+
      '<td>'+esc(c.comName)+'</td>'+
      '<td class="muted tnum">'+(esc(c.cid)||'-')+'</td>'+
      '<td><span class="counselor-tag">'+esc(c.counselor)+'</span></td>'+
      '<td>'+esc(c.regIndustry)+'</td>'+
      '<td>'+svcText+'</td>'+
      '<td class="muted tnum">'+dateText+'</td>'+
      '<td class="center">'+tag+'</td>'+
      '<td class="tnum">'+fmtMoney(c.payAmount)+'</td>'+
      '<td class="reasons"><span style="display:block;max-width:200px;white-space:normal">'+esc(actShort)+'</span></td>'+
    '</tr>';
  }).join('');
  tb.querySelectorAll('tr').forEach(tr=>{tr.onclick=()=>toggleExpRow(tr);});
}
function toggleExpRow(tr){
  if(tr.classList.contains('expanded')){
    const n=tr.nextElementSibling;if(n&&n.classList.contains('detail-row'))n.remove();
    tr.classList.remove('expanded');return;
  }
  const tb=document.getElementById('expTbody');
  tb.querySelectorAll('tr.expanded').forEach(e=>{const n=e.nextElementSibling;if(n&&n.classList.contains('detail-row'))n.remove();e.classList.remove('expanded');});
  tr.classList.add('expanded');
  const idx=parseInt(tr.dataset.expIdx);
  const c=expList[idx];
  if(!c)return;
  const expHtml=c.allExps.map(e=>{
    const d=e.days;
    let badge;
    if(d===null||d===undefined)badge='<span class="exp-tag muted">未设置</span>';
    else if(d<0)badge='<span class="exp-tag danger">已过期 '+(-d)+' 天</span>';
    else if(d<=7)badge='<span class="exp-tag danger">'+d+' 天后到期</span>';
    else if(d<=30)badge='<span class="exp-tag warn">'+d+' 天后到期</span>';
    else badge='<span class="exp-tag info">'+d+' 天后到期</span>';
    return '<li>'+esc(e.serviceName)+' — '+(e.enableEnd?fmtDate(e.enableEnd):'<span class="muted">未设置</span>')+' '+badge+'</li>';
  }).join('');
  const detail=document.createElement('tr');
  detail.className='detail-row';
  detail.innerHTML='<td colspan="11"><div class="detail-box">'+
    '<div class="block"><h4>沟通话术</h4><div class="tt">'+esc(c.talkTrack)+'</div></div>'+
    '<div class="block"><h4>建议动作</h4><div class="tt">'+esc(c.action)+'</div></div>'+
    '<div class="block"><h4>服务到期详情</h4><ul>'+expHtml+'</ul></div>'+
    '<div class="block"><h4>痛点分析</h4><ul>'+c.painPoints.map(p=>'<li>'+esc(p)+'</li>').join('')+'</ul></div>'+
    '<div class="block"><h4>客户信息</h4><ul><li>归属顾问：<b style="color:var(--accent)">'+esc(c.counselor)+'</b></li><li>行业：'+esc(c.regIndustry)+'</li><li>付费金额：'+fmtMoney(c.payAmount)+'</li></ul></div>'+
  '</div></td>';
  tr.parentNode.insertBefore(detail,tr.nextSibling);
}

/* ===== 客户列表 ===== */
let curGrade='',curInd='',curBiz='',curSearch='',curCounselor='';
let curPage=1,pageSize=50;
let filtered=DATA.slice();
function prioClass(g){return {S:'p1',A2:'p2',A3:'p3',B:'p4',C:'p5'}[g]||'p5';}
function applyFilter(){
  filtered=DATA.filter(c=>{
    if(curGrade&&c.grade!==curGrade)return false;
    if(curInd&&c.regIndustry!==curInd)return false;
    if(curBiz&&c.businessType!==curBiz)return false;
    if(curCounselor&&c.counselor!==curCounselor)return false;
    if(curSearch){
      const s=curSearch.toLowerCase();
      if(!(c.comName||'').toLowerCase().includes(s)&&!(c.realName||'').toLowerCase().includes(s)&&!(String(c.cid||'')).toLowerCase().includes(s))return false;
    }
    return true;
  });
  const gOrd={S:0,A2:1,A3:2,B:3,C:4};
  filtered.sort((a,b)=>{if(gOrd[a.grade]!==gOrd[b.grade])return gOrd[a.grade]-gOrd[b.grade];return b.scores.total-a.scores.total;});
  curPage=1;renderTable();
}
function renderTable(){
  const tbody=document.getElementById('tbody');
  const total=filtered.length;
  const pages=Math.max(1,Math.ceil(total/pageSize));
  if(curPage>pages)curPage=pages;
  const start=(curPage-1)*pageSize;
  const rows=filtered.slice(start,start+pageSize);
  document.getElementById('filterStat').textContent='共 '+total+' 条 · 第 '+curPage+'/'+pages+' 页';
  if(!rows.length){tbody.innerHTML='<tr><td colspan="12" class="no-data"><div class="ico">🔍</div>无匹配客户</td></tr>';renderPager(pages);return;}
  tbody.innerHTML=rows.map((c,i)=>{
    const sc=c.scores;
    const scoreCells=['D1','D2','D3','D4','D5','D6'].map(k=>'<span class="score-cell s'+sc[k]+'" title="'+k+'='+sc[k]+'">'+sc[k]+'</span>').join('');
    const prioIdx={S:1,A2:2,A3:3,B:4,C:5}[c.grade];
    return '<tr data-idx="'+(start+i)+'">'+
      '<td class="center"><span class="prio p'+prioIdx+'">'+prioIdx+'</span></td>'+
      '<td class="center"><span class="grade-tag '+c.grade+'">'+c.grade+'</span></td>'+
      '<td>'+esc(c.comName)+'</td>'+
      '<td>'+(esc(c.realName)||'<span class="muted">-</span>')+'</td>'+
      '<td class="muted tnum">'+(esc(c.cid)||'-')+'</td>'+
      '<td><span class="counselor-tag">'+esc(c.counselor)+'</span></td>'+
      '<td>'+esc(c.regIndustry)+'</td>'+
      '<td>'+esc(c.businessType)+'</td>'+
      '<td class="center tnum">'+c.loginDayRate+'%</td>'+
      '<td class="tnum">'+fmtMoney(c.payAmount)+'</td>'+
      '<td class="center"><span class="score-bar">'+scoreCells+'<span class="muted tnum" title="总分" style="margin-left:3px;font-weight:600">'+sc.total+'</span></span></td>'+
      '<td class="reasons">'+c.reasons.map(r=>'<span>'+esc(r)+'</span>').join('')+'</td>'+
    '</tr>';
  }).join('');
  tbody.querySelectorAll('tr').forEach(tr=>{tr.onclick=()=>toggleRow(tr);});
  renderPager(pages);
}
function toggleRow(tr){
  if(tr.classList.contains('expanded')){
    const n=tr.nextElementSibling;if(n&&n.classList.contains('detail-row'))n.remove();
    tr.classList.remove('expanded');return;
  }
  const tbody=document.getElementById('tbody');
  tbody.querySelectorAll('tr.expanded').forEach(e=>{const n=e.nextElementSibling;if(n&&n.classList.contains('detail-row'))n.remove();e.classList.remove('expanded');});
  tr.classList.add('expanded');
  const idx=parseInt(tr.dataset.idx);
  const c=filtered[idx];
  const sc=c.scores;
  const expHtml=(c.expirations&&c.expirations.length)?c.expirations.map(e=>{
    const d=e.days;
    let badge='';
    if(d!==null&&d!==undefined){
      if(d<0)badge='<span class="exp-tag danger">已过期 '+(-d)+' 天</span>';
      else if(d<=7)badge='<span class="exp-tag danger">'+d+' 天后到期</span>';
      else if(d<=30)badge='<span class="exp-tag warn">'+d+' 天后到期</span>';
      else badge='<span class="exp-tag info">'+d+' 天后到期</span>';
    }else badge='<span class="exp-tag muted">未设置</span>';
    return '<li>'+esc(e.serviceName)+' — '+(e.enableEnd?fmtDate(e.enableEnd):'<span class="muted">未设置</span>')+' '+badge+'</li>';
  }).join(''):'<li class="muted">无到期服务数据</li>';
  const detail=document.createElement('tr');
  detail.className='detail-row';
  detail.innerHTML='<td colspan="12"><div class="detail-box">'+
    '<div class="block"><h4>痛点分析</h4><ul>'+c.painPoints.map(p=>'<li>'+esc(p)+'</li>').join('')+'</ul></div>'+
    '<div class="block"><h4>沟通话术</h4><div class="tt">'+esc(c.talkTrack)+'</div></div>'+
    '<div class="block"><h4>建议动作</h4><div class="tt">'+esc(c.action)+'</div></div>'+
    '<div class="block"><h4>服务到期</h4><ul>'+expHtml+'</ul>'+
      '<div style="margin-top:10px;font-size:12px;color:var(--text2)">评分明细：D1回访'+sc.D1+' / D2行业'+sc.D2+' / D3业务'+sc.D3+' / D4规模'+sc.D4+' / D5活跃'+sc.D5+' / D6付费'+sc.D6+' · 机会分'+sc.opp+' · 加成+'+sc.bonus+' · 总分'+sc.total+'</div>'+
      '<div style="margin-top:6px;font-size:12px;color:var(--text2)">归属顾问：<b style="color:var(--accent)">'+esc(c.counselor)+'</b> · 门店'+c.storeNumber+'家 · 子账号'+c.userNumber+' · 硬件'+c.hardQuantity+'套 · 系统'+c.sysType+' · 活跃'+c.loginDays+'/'+c.allDays+'天 · 意向：'+esc(c.intention)+'</div>'+
      (c.lastVisitRecord?'<div style="margin-top:6px;font-size:12px;color:var(--text2)">上次回访：'+esc(c.lastVisitRecord)+'</div>':'')+
    '</div>'+
  '</div></td>';
  tr.parentNode.insertBefore(detail,tr.nextSibling);
}
function renderPager(pages){
  const p=document.getElementById('pager');
  if(pages<=1){p.innerHTML='<span class="info">共 '+filtered.length+' 条</span>';return;}
  let html='<button onclick="goPage(1)">«</button>';
  let from=Math.max(1,curPage-3),to=Math.min(pages,curPage+3);
  if(from>1)html+='<span class="info">…</span>';
  for(let i=from;i<=to;i++)html+='<button class="'+(i===curPage?'active':'')+'" onclick="goPage('+i+')">'+i+'</button>';
  if(to<pages)html+='<span class="info">…</span>';
  html+='<button onclick="goPage('+pages+')">»</button>';
  html+='<span class="info">共 '+filtered.length+' 条 / '+pages+' 页 · 每页 '+pageSize+' 条</span>';
  p.innerHTML=html;
}
window.goPage=function(p){curPage=p;renderTable();window.scrollTo({top:0,behavior:'smooth'});};

/* ===== 筛选器初始化 ===== */
function initFilters(){
  const indSet={};DATA.forEach(c=>indSet[c.regIndustry]=1);
  const indSel=document.getElementById('indFilter');
  Object.keys(indSet).sort().forEach(k=>{const o=document.createElement('option');o.value=k;o.textContent=k;indSel.appendChild(o);});
  indSel.onchange=e=>{curInd=e.target.value;applyFilter();};
  const bizSet={};DATA.forEach(c=>bizSet[c.businessType]=1);
  const bizSel=document.getElementById('bizFilter');
  Object.keys(bizSet).sort().forEach(k=>{const o=document.createElement('option');o.value=k;o.textContent=k;bizSel.appendChild(o);});
  bizSel.onchange=e=>{curBiz=e.target.value;applyFilter();};
  /* 顾问下拉框（客户列表页） */
  const couSet={};DATA.forEach(c=>{couSet[c.counselor]=1;});
  const couSel=document.getElementById('counselorFilter');
  Object.keys(couSet).sort().forEach(k=>{const o=document.createElement('option');o.value=k;o.textContent=k;couSel.appendChild(o);});
  couSel.onchange=e=>{curCounselor=e.target.value;applyFilter();};
  /* 顾问下拉框（到期预警页） */
  const expCouSel=document.getElementById('expCounselorFilter');
  Object.keys(couSet).sort().forEach(k=>{const o=document.createElement('option');o.value=k;o.textContent=k;expCouSel.appendChild(o);});
  expCouSel.onchange=e=>{expCounselor=e.target.value;renderExpiring();};
  document.querySelectorAll('#gradeChips .chip').forEach(chip=>{
    chip.onclick=()=>{
      document.querySelectorAll('#gradeChips .chip').forEach(c=>c.classList.remove('active'));
      chip.classList.add('active');
      curGrade=chip.dataset.grade;applyFilter();
    };
  });
  const search=document.getElementById('search');
  let timer;
  search.oninput=e=>{clearTimeout(timer);timer=setTimeout(()=>{curSearch=e.target.value.trim();applyFilter();},200);};
  document.querySelectorAll('#expChips .chip').forEach(chip=>{
    chip.onclick=()=>{
      const v=chip.dataset.exp;
      document.querySelectorAll('#expChips .chip').forEach(c=>c.classList.remove('active'));
      chip.classList.add('active');
      expRange=(v==='all'||v==='none')?v:parseInt(v);
      renderExpiring();
    };
  });
  const es=document.getElementById('expSearch');
  let et;
  es.oninput=e=>{clearTimeout(et);et=setTimeout(()=>{expSearch=e.target.value.trim();renderExpiring();},200);};
  /* 到期产品下拉框 */
  const prodSet={};
  DATA.forEach(c=>{(c.expirations||[]).forEach(e=>{prodSet[e.serviceName]=1;});});
  const prodSel=document.getElementById('expProdFilter');
  Object.keys(prodSet).sort().forEach(k=>{const o=document.createElement('option');o.value=k;o.textContent=k;prodSel.appendChild(o);});
  prodSel.onchange=e=>{expProd=e.target.value;renderExpiring();};
}

/* ===== 启动 ===== */
buildExpBuckets();
initFilters();
applyFilter();
renderExpSummary();
renderTimeline();
renderExpiring();
drawAllCharts();
</script>
</body>
</html>
'''


def build_html(customers, meta):
    data_json = json.dumps(customers, ensure_ascii=False, separators=(',', ':'))
    meta_json = json.dumps(meta, ensure_ascii=False, separators=(',', ':'))
    html = HTML_TEMPLATE.replace('__DATA_JSON__', data_json).replace('__META_JSON__', meta_json).replace('__GEN_TIME__', meta.get('genTime', ''))
    return html


def main():
    print('读取数据:', DATA_FILE)
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    print('原始客户数:', len(raw))

    customers = [process_customer(d) for d in raw]

    # 按分级优先级 + 总分排序
    g_ord = {'S': 0, 'A2': 1, 'A3': 2, 'B': 3, 'C': 4}
    customers.sort(key=lambda c: (g_ord.get(c['grade'], 9), -c['scores']['total']))

    # 统计 meta
    grade_cnt = Counter(c['grade'] for c in customers)
    total_pay = sum(c['payAmount'] for c in customers)
    expiring_soon = sum(
        1 for c in customers
        if any(e['days'] is not None and 0 <= e['days'] <= 30 for e in c['expirations'])
    )
    meta = {
        'total': len(customers),
        'grades': dict(grade_cnt),
        'totalPay': round(total_pay, 2),
        'expiringSoon': expiring_soon,
        'genTime': time.strftime('%Y-%m-%d %H:%M:%S'),
    }

    print('分级分布:', dict(grade_cnt))
    print('总付费金额: %.2f' % total_pay)
    print('30天内到期数:', expiring_soon)

    html = build_html(customers, meta)
    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        f.write(html)

    size_kb = os.path.getsize(OUT_FILE) / 1024
    print('已生成:', OUT_FILE)
    print('文件大小: %.1f KB (%.2f MB)' % (size_kb, size_kb / 1024))


if __name__ == '__main__':
    main()
