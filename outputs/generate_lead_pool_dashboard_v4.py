#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
线索池SDR看板 v4.0 — 完全对齐服务池看板风格
=================================================
v3问题：fetch CORS导致转圈加载失败 + UI风格不搭 + 功能缺失
v4方案：
  1. 数据内嵌HTML（const DATA=[...]）— 对标服务池的2.9MB单文件方案
  2. 精简字段（去掉话术/产品推荐等大文本，改用JS模板动态生成）
  3. 完全复刻服务池浅黄主题CSS变量+布局+交互模式
  4. Canvas图表(饼图+柱状图) + 顶栏导航 + KPI卡片 + 展开行详情
  5. 分页渲染100条/页 + 暗色主题切换 + 导出CSV
"""
import json, os, sys, io, math, re
from collections import Counter
from datetime import datetime, timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_FILE = os.path.join(SCRIPT_DIR, 'shimo_raw_data', 'all_sheets_full.json')
OUTPUT_HTML = os.path.join(SCRIPT_DIR, '线索池SDR看板.html')

NOW = datetime.now()

# ================================================================
# 秦丝产品知识库（用于话术生成）
# ================================================================
PRODUCTS = [
    {'n':'进销存专业版','c':'核心系统','d':'进销存+商品管理+库存预警','p':'¥1680-2680/年'},
    {'n':'生意通专业版','c':'批发订货','d':'批发订货+采购管理+财务报表','p':'¥1680-2980/年'},
    {'n':'销货宝微商城','c':'线上渠道','d':'微信小程序商城+在线支付+营销','p':'¥980-2980/年'},
    {'n':'专属品牌小程序','c':'线上渠道','d':'独立品牌小程序+自定义装修','p':'¥1980-3980/年'},
    {'n':'限时折扣促单宝','c':'营销工具','d':'限时折扣+会员价+阶梯定价','p':'¥280-480/年'},
    {'n':'批量推款宝','c':'营销工具','d':'批量推款给客户在线选款','p':'¥380-680/年'},
    {'n':'直播卖货','c':'营销工具','d':'直播带货+引流到店+互动抽奖','p':'¥680-1280/年'},
    {'n':'微信自动化经营','c':'营销工具','d':'自动加好友+群发+朋友圈营销','p':'¥580-980/年'},
    {'n':'专属微信会员卡','c':'会员运营','d':'微信会员卡+积分+储值+画像','p':'¥680-1280/年'},
    {'n':'慧店宝收银','c':'硬件收银','d':'收银终端+扫码+打印一体','p':'¥1280-1980'},
    {'n':'AI绘图','c':'AI工具','d':'AI自动绘图+智能抠图+商品图生成','p':'¥280-580/年'},
    {'n':'以图搜图','c':'AI工具','d':'图片搜索商品快速找款','p':'¥180-380/年'},
]

INDUSTRY_MAP = {
    '服装':'服装鞋帽','服饰':'服装鞋帽','女装':'服装鞋帽','男装':'服装鞋帽',
    '母婴':'母婴童玩','玩具':'母婴童玩','童装':'母婴童玩',
    '食品':'食品生鲜','零食':'食品生鲜','水果':'食品生鲜','生鲜':'食品生鲜','餐饮':'食品生鲜',
    '美妆':'美容美发','化妆':'美容美发','护肤':'美容美发','美甲':'美容美发',
    '家居':'家居家纺','家具':'家居家纺','家装':'家居家纺','百货':'家居家纺','日用品':'家居家纺',
    '数码':'3C数码','手机':'3C数码','电子':'3C数码',
    '配件':'汽摩配件','汽车':'汽摩配件','五金':'汽摩配件',
    '户外':'运动户外','体育':'运动户外','健身':'运动户外',
    '珠宝':'饰品珠宝','首饰':'饰品珠宝','手表':'饰品珠宝',
    '农资':'农产品','蔬菜':'农产品','农业':'农产品',
    '医药':'医药保健','保健':'医药健康','养生':'医药健康',
    '宠物':'宠物生活','花':'鲜花绿植','文具':'办公用品',
}

# ================================================================
# 数据解析
# ================================================================
print('[1/5] 解析石摩原始数据...')
with open(RAW_FILE, 'r', encoding='utf-8') as f:
    raw = json.load(f)

# ---- 小红书1组线索表（主表）----
raw1 = raw.get('小红书1组线索表', {}).get('data', '')
lines1 = raw1.split('\n')
header_line_idx = 9
HDR = [h.strip() for h in lines1[header_line_idx].split('\t')]

leads = []
for line in lines1[header_line_idx + 1:]:
    parts = line.split('\t')
    if len(parts) < len(HDR):
        continue
    rec = {}
    for i, h in enumerate(HDR):
        rec[h] = parts[i].strip() if i < len(parts) else ''
    phone = rec.get('手机号', '').strip()
    if not phone or len(phone) < 6:
        continue
    leads.append(rec)

print(f'  小红书1组线索表: {len(leads)} 条有效')

# ---- 线索跟进表（补充）----
raw2 = raw.get('线索跟进表', {}).get('data', '')
if raw2:
    lines2 = raw2.split('\n')
    # 跟进表数据行从tabs最多的区间开始
    tab_dist = Counter(l.count('\t') for l in lines2)
    data_tabs = tab_dist.most_common(1)[0][0]
    # 推断跟进表字段（基于之前分析）
    follow_hdr = ['微信昵称','手机号','创建时间','来源行业','归属运营','线索渠道',
                  '渠道子类','分配部门','顾问','一次跟进记录','二次跟进记录',
                  '三次跟进记录','四次跟进记录','五次跟进记录','线索级别',
                  '成交状态','下单金额','下单日期','换注册手机号','','']
    
    follow_map = {}  # 手机号 -> 跟进数据
    for line in lines2:
        parts = line.split('\t')
        if len(parts) < 10:
            continue
        fphone = (parts[1] or '').strip()
        if not fphone or len(fphone) < 6:
            continue
        follow_map[fphone] = {
            'f1': (parts[9] or '').strip()[:200],
            'f2': (parts[10] or '').strip()[:200],
            'f3': (parts[11] or '').strip()[:200],
            'f4': (parts[12] or '').strip()[:200],
            'f5': (parts[13] or '').strip()[:200],
            'fl': (parts[14] or '').strip(),  # 线索级别
            'fs': (parts[15] or '').strip(),  # 成交状态
            'fa': (parts[16] or '').strip(),  # 下单金额
            'fd': (parts[17] or '').strip(),  # 下单日期
            'fc': (parts[5] or '').strip(),   # 渠道
            'fdpt': (parts[7] or '').strip(), # 部门
            'fco': (parts[8] or '').strip(),  # 顾问
        }
    print(f'  线索跟进表: {len(follow_map)} 条跟进记录')

# 合并数据
merged_count = 0
for l in leads:
    phone = l.get('手机号', '')
    if phone in follow_map:
        fm = follow_map[phone]
        l['_f1'] = fm['f1']; l['_f2'] = fm['f2']; l['_f3'] = fm['f3']; l['_f4'] = fm['f4']
        if not l.get('线索级别'): l['线索级别'] = fm['fl']
        merged_count += 1

print(f'  合并后: {len(leads)} 条 (其中{merged_count}条有跟进补充)')

# ================================================================
# 6维评分 + 分级模型
# ================================================================
def score_lead(l):
    """6维评分返回 {scores:{L1-L6}, total, grade, gl, gc, gu, itl, ind, scl, _deal, _amt}"""
    sc = {}
    
    # L1 意向信号(5): 基于跟进状态/线索级别/是否有跟进记录
    status = str(l.get('跟进状态', '')).strip()
    level = str(l.get('线索级别', '')).strip()
    has_follow = any(l.get(f'_f{i}') for i in range(1, 5))
    
    hi_keywords = ['有意向','高意向','意向强','要购买','考虑','对比','报价','演示','了解产品','想买']
    md_keywords = ['待跟进','跟进中','沟通中','再联系','考虑中','已分配','新线索']
    rj_keywords = ['不要了','不需要','拒绝','无效','空号','关机','拉黑','退订']
    
    note = str(l.get('备注', '')) + ' ' + str(l.get('客户备注', '')) + ' ' + str(l.get('_f1', ''))
    note_lower = note.lower()
    
    if any(kw in status for kw in hi_keywords) or any(kw in level for kw in ['A','S','高']):
        sc['L1'] = 5; itl = 'high'
    elif has_follow or any(kw in status for kw in md_keywords) or any(kw in level for kw in ['B','中']):
        sc['L1'] = 3; itl = 'medium'
    elif any(kw in note_lower for kw in rj_keywords) or any(kw in status for kw in rj_keywords):
        sc['L1'] = 1; itl = 'rejected'
    else:
        sc['L1'] = 2; itl = 'low'
    
    # L2 渠道质量(5): 基于渠道类型
    ch = str(l.get('渠道', '')).strip()
    hi_ch = ['小红书广告','抖音广告','信息流','SEM','搜索广告','朋友圈广告']
    md_ch = ['自然搜索','转介绍','老客户推荐','地推','线下活动','社群']
    if ch in hi_ch or any(kw in ch for kw in ['广告','投放','信息流','付费']):
        sc['L2'] = 5
    elif ch in md_ch or any(kw in ch for kw in ['转介','推荐','自然','搜索','线下','社群']):
        sc['L2'] = 4
    elif ch:
        sc['L2'] = 3
    else:
        sc['L2'] = 2
    
    # L3 来源质量(5)
    src = str(l.get('来源', '')).strip()
    if any(kw in src for kw in ['咨询','留言','电话','表单','预约','体验']):
        sc['L3'] = 5
    elif any(kw in src for kw in ['浏览','访问','点击','查看','首页']):
        sc['L3'] = 3
    elif src:
        sc['L3'] = 2
    else:
        sc['L3'] = 1
    
    # L4 跟进深度(5)
    follow_count = sum(1 for i in range(1, 5) if l.get(f'_f{i}'))
    if follow_count >= 3:
        sc['L4'] = 5
    elif follow_count >= 2:
        sc['L4'] = 4
    elif follow_count >= 1:
        sc['L4'] = 3
    elif has_follow:
        sc['L4'] = 2
    else:
        sc['L4'] = 1
    
    # L5 新鲜度/线索年龄(5): 基于分配时间
    at = str(l.get('分配时间', '')).strip()
    age_days = None
    if at:
        try:
            at_clean = at.replace('.', '-').replace('/', '-')
            # 尝试多种格式解析日期
            dt = None
            for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d']:
                try:
                    dt = datetime.strptime(at_clean[:10], '%Y-%m-%d')
                    break
                except:
                    continue
            if dt:
                age_days = (NOW - dt).days
        except:
            pass
    
    if age_days is not None:
        if age_days <= 3:
            sc['L5'] = 5; gu = '今日新鲜'
        elif age_days <= 7:
            sc['L5'] = 5; gu = '一周内'
        elif age_days <= 14:
            sc['L5'] = 4; gu = '两周内'
        elif age_days <= 30:
            sc['L5'] = 3; gu = '一月内'
        elif age_days <= 90:
            sc['L5'] = 2; gu = f'{age_days}天'
        else:
            sc['L5'] = 1; gu = f'{age_days}天(旧)'
    else:
        sc['L5'] = 2; gu = '-'
    
    # L6 可触达性(5)
    phone = str(l.get('手机号', '')).strip()
    other_contact = str(l.get('其他联系方式', '')).strip() or str(l.get('微信号', '')).strip()
    
    if phone and len(phone) >= 11 and '*' not in phone:
        sc['L6'] = 5
    elif phone and len(phone) >= 6:
        sc['L6'] = 3
    elif other_contact:
        sc['L6'] = 3
    else:
        sc['L6'] = 1
    
    total = sum(sc.values())
    
    # 分级规则（对标服务池 S/A2/A3/B/C）
    opp_score = total  # 综合机会分
    if itl == 'high' and (age_days is None or age_days <= 14):
        grade = 'S'; gl = 'S·立即行动'; gc = '#B71C1C'
    elif total >= 22 or (itl == 'high' and age_days and age_days <= 30):
        grade = 'A2'; gl = 'A2·重点跟进'; gc = '#E65100'
    elif total >= 16 or itl == 'medium':
        grade = 'A3'; gl = 'A3·正常跟进'; gc = '#F57F17'
    elif total >= 10:
        grade = 'B'; gl = 'B·低优队列'; gc = '#558B2F'
    else:
        grade = 'C'; gl = 'C·暂缓淘汰'; gc = '#33691E'
    
    # 成交判断
    deal_val = str(l.get('是否成交', '')).strip().upper()
    amt_str = str(l.get('成交金额', '')).replace(',', '').replace(' ', '')
    _deal = deal_val in ('TRUE', '是', '已成交', 'YES', '1')
    try:
        _amt = float(amt_str) if amt_str else 0
    except:
        _amt = 0
    if _amt > 0 and not _deal:
        _deal = True  # 有金额视为成交
    
    if _deal:
        grade = 'DEAL'; gl = '已成交'; gc = '#2E7D32'
    
    # 行业推断
    src_text = (str(l.get('来源', '')) + ' ' + str(l.get('备注', '')) + ' ' + str(l.get('客户备注', ''))).lower()
    ind = '未知'
    for kw, cat in INDUSTRY_MAP.items():
        if kw in src_text:
            ind = cat
            break
    dept = str(l.get('分配部门', '')).strip() or '未分配'
    counselor = str(l.get('分配顾问', '')).strip() or str(l.get('顾问', '')).strip() or '未分配'
    
    # 规模推测
    scl = '未知'
    if '连锁' in src_text or '多店' in src_text or '分店' in src_text:
        scl = '多店连锁(≥3)'
    elif '公司' in src_text or '企业' in src_text or '工厂' in src_text:
        scl = '企业级'
    elif '店' in src_text or '铺' in src_text:
        scl = '单店'
    
    return {
        '_sc': total,
        '_scd': dict(sc),
        '_g': grade,
        '_gl': gl,
        '_gc': gc,
        '_gu': gu,
        '_itl': itl,
        '_ind': ind,
        '_scl': scl,
        '_ad': at,
        '_age_days': age_days,
        '_deal': _deal,
        '_amt': _amt,
        '_dept': dept,
        '_co': counselor,
        '_ch': ch,
    }

# ================================================================
# 批量评分
# ================================================================
print('[2/5] 6维评分分级...')
for i, l in enumerate(leads):
    s = score_lead(l)
    l.update(s)

grade_counts = Counter(l['_g'] for l in leads)
deal_count = sum(1 for l in leads if l['_deal'])
total_amt = sum(l['_amt'] for l in leads if l['_amt'] > 0)
print(f'  分级分布: S={grade_counts.get("S",0)} A2={grade_counts.get("A2",0)} A3={grade_counts.get("A3",0)} B={grade_counts.get("B",0)} C={grade_counts.get("C",0)} 已成交={deal_count}')

# ================================================================
# 生成HTML — 复刻服务池浅黄主题
# ================================================================
print('[3/5] 生成HTML...')

# 精简数据：只保留展示需要的字段
export_leads = []
for l in leads:
    export_leads.append({
        'g': l['_g'],
        'sc': l['_sc'],
        'gu': l['_gu'],
        'itl': l['_itl'],
        'ind': l['_ind'],
        'dept': l['_dept'],
        'co': l['_co'],
        'ch': l['_ch'],
        'src': (l.get('来源', '') or '')[:50],
        'at': l['_ad'],
        'ph': l.get('手机号', ''),
        'oc': (l.get('其他联系方式', '') or l.get('微信号', '') or '')[:50],
        'st': (l.get('跟进状态', '') or '')[:30],
        'lv': (l.get('线索级别', '') or '')[:20],
        'note': ((l.get('备注', '') or l.get('客户备注', '') or '') or '')[:120],
        'f1': l.get('_f1', ''),
        'f2': l.get('_f2', ''),
        'f3': l.get('_f3', ''),
        'f4': l.get('_f4', ''),
        'ag': l.get('分配人', '') or '',
        'deal': l['_deal'],
        'amt': l['_amt'],
        'age': l['_age_days'],
        'scd': l['_scd'],
        'scl': l['_scl'],
    })

data_json = json.dumps(export_leads, ensure_ascii=False, separators=(',', ':'))
meta_json = json.dumps({
    'total': len(export_leads),
    'deals': deal_count,
    'amount': total_amt,
    'grades': dict(grade_counts),
    'genTime': NOW.strftime('%Y-%m-%d %H:%M:%S'),
}, ensure_ascii=False)

gen_ts = NOW.strftime('%Y-%m-%d %H:%M:%S')

html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>线索池SDR机会中心</title>
<style>
:root{{
  --bg:#FFFBF0;--bg2:#FFF6E0;--card:#FFFFFF;--card2:#FFFEF7;
  --text:#3D2C1E;--text2:#8D6E63;--text3:#BFA08A;
  --border:#F0E2C4;--border2:#E8D5A8;
  --accent:#E65100;--accent2:#F57C00;--accent-soft:#FFF3E0;--accent-bg:#FFF8E1;
  --good:#2E7D32;--warn:#F57F17;--danger:#C62828;
  --S:#FFCDD2;--A2:#FFE0B2;--A3:#FFF3C4;--B:#E6F0C8;--C:#D7E8C5;
  --S-t:#B71C1C;--A2-t:#E65100;--A3-t:#F57F17;--B-t:#558B2F;--C-t:#33691E;
  --shadow:0 1px 3px rgba(141,110,99,.08),0 1px 2px rgba(141,110,99,.04);
  --shadow-h:0 4px 12px rgba(141,110,99,.12),0 2px 4px rgba(141,110,99,.06);
  --radius:12px;--radius-s:8px;
}}
@media(prefers-color-scheme:dark){{:root{{
  --bg:#1E1810;--bg2:#261E14;--card:#2A2118;--card2:#332920;
  --text:#F5E9D6;--text2:#BFA08A;--text3:#8D6E63;
  --border:#3D2E1F;--border2:#4D3A28;
  --accent:#FFB74D;--accent2:#FFA726;--accent-soft:#3D2E1F;--accent-bg:#332920;
  --S:#5D2A2A;--A2:#5D4221;--A3:#5D5021;--B:#3D5021;--C:#2A4A2A;
  --shadow:0 1px 3px rgba(0,0,0,.3);--shadow-h:0 4px 12px rgba(0,0,0,.2);
}}}}
[data-theme="dark"]{{
  --bg:#1E1810;--bg2:#261E14;--card:#2A2118;--card2:#332920;
  --text:#F5E9D6;--text2:#BFA08A;--text3:#8D6E63;
  --border:#3D2E1F;--border2:#4D3A28;--accent:#FFB74D;--accent2:#FFA726;
  --accent-soft:#3D2E1F;--accent-bg:#332920;
  --S:#5D2A2A;--A2:#5D4221;--A3:#5D5021;--B:#3D5021;--C:#2A4A2A;
  --shadow:0 1px 3px rgba(0,0,0,.3);--shadow-h:0 4px 12px rgba(0,0,0,.2);
}}
[data-theme="light"]{{
  --bg:#FFFBF0;--bg2:#FFF6E0;--card:#FFFFFF;--card2:#FFFEF7;
  --text:#3D2C1E;--text2:#8D6E63;--text3:#BFA08A;
  --border:#F0E2C4;--border2:#E8D5A8;
  --accent:#E65100;--accent2:#F57C00;--accent-soft:#FFF3E0;--accent-bg:#FFF8E1;
  --S:#FFCDD2;--A2:#FFE0B2;--A3:#FFF3C4;--B:#E6F0C8;--C:#D7E8C5;
  --S-t:#B71C1C;--A2-t:#E65100;--A3-t:#F57F17;--B-t:#558B2F;--C-t:#33691E;
  --shadow:0 1px 3px rgba(141,110,99,.08);--shadow-h:0 4px 12px rgba(141,110,99,.12);
}}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{height:100%}}
body{{font-family:"PingFang SC","Microsoft YaHei","微软雅黑",-apple-system,sans-serif;background:var(--bg);color:var(--text);line-height:1.5;font-size:14px;-webkit-font-smoothing:antialiased}}
::-webkit-scrollbar{{width:8px;height:8px}}
::-webkit-scrollbar-thumb{{background:var(--border2);border-radius:4px}}

/* ===== 顶栏 ===== */
.topbar{{position:sticky;top:0;z-index:100;background:linear-gradient(135deg,var(--card) 0%,var(--card2) 100%);border-bottom:1px solid var(--border);padding:0 24px;display:flex;align-items:center;gap:20px;box-shadow:var(--shadow);min-height:60px}}
.topbar .brand{{display:flex;align-items:center;gap:10px;padding:10px 0}}
.topbar .logo{{width:32px;height:32px;border-radius:8px;background:linear-gradient(135deg,var(--accent) 0%,var(--accent2) 100%);display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:16px;box-shadow:0 2px 6px rgba(230,81,0,.3)}}
.topbar .title{{font-size:16px;font-weight:600;color:var(--text)}}
.topbar .sub{{font-size:11px;color:var(--text2);margin-top:1px}}
.topbar .nav{{display:flex;gap:2px;margin-left:8px}}
.nav-item{{padding:8px 14px;border-radius:8px;cursor:pointer;color:var(--text2);font-size:13px;font-weight:500;transition:all .15s;border:1px solid transparent}}
.nav-item:hover{{color:var(--accent);background:var(--accent-soft)}}
.nav-item.active{{color:var(--accent);background:var(--accent-soft);border-color:var(--border2);font-weight:600}}
.nav-item .badge{{display:inline-block;margin-left:4px;padding:1px 6px;border-radius:8px;background:var(--accent);color:#fff;font-size:10px;font-weight:600;min-width:16px;text-align:center}}
.topbar .spacer{{flex:1}}
.iconbtn{{width:34px;height:34px;border-radius:8px;border:1px solid var(--border);background:var(--card);color:var(--text2);cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:14px;transition:all .15s}}
.iconbtn:hover{{border-color:var(--accent);color:var(--accent)}}

/* ===== 页面 ===== */
.page{{display:none;padding:22px 24px 48px;max-width:1480px;margin:0 auto}}
.page.active{{display:block;animation:fade .2s ease}}
@keyframes fade{{from{{opacity:0;transform:translateY(4px)}}to{{opacity:1;transform:translateY(0)}}}}

/* ===== KPI ===== */
.kpi-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin-bottom:20px}}
.kpi{{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:16px 18px;box-shadow:var(--shadow);position:relative;overflow:hidden;transition:transform .15s,box-shadow .15s}}
.kpi:hover{{transform:translateY(-1px);box-shadow:var(--shadow-h)}}
.kpi .lbl{{font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:.3px;font-weight:600}}
.kpi .val{{font-size:26px;font-weight:700;margin-top:6px;color:var(--text);line-height:1.1}}
.kpi .val small{{font-size:12px;font-weight:500;color:var(--text2);margin-left:4px}}
.kpi .delta{{font-size:11px;color:var(--text2);margin-top:4px}}
.kpi.grade{{border-left:4px solid var(--border2)}}
.kpi.grade.S{{border-left-color:#E53935;background:linear-gradient(135deg,var(--S) 0%,var(--card) 50%)}}
.kpi.grade.A2{{border-left-color:var(--accent2);background:linear-gradient(135deg,var(--A2) 0%,var(--card) 50%)}}
.kpi.grade.A3{{border-left-color:var(--warn);background:linear-gradient(135deg,var(--A3) 0%,var(--card) 50%)}}
.kpi.grade.B{{border-left-color:#7CB342;background:linear-gradient(135deg,var(--B) 0%,var(--card) 50%)}}
.kpi.grade.C{{border-left-color:#558B2F;background:linear-gradient(135deg,var(--C) 0%,var(--card) 50%)}}
.kpi-mini{{font-size:10px;color:var(--text2);margin-top:6px;display:flex;gap:8px}}
.kpi-mini span b{{color:var(--text);font-weight:600}}

/* ===== 图表 ===== */
.charts-row{{display:grid;grid-template-columns:1.1fr 1fr 1fr;gap:16px;margin-bottom:8px}}
.chart-card{{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:18px;box-shadow:var(--shadow)}}
.chart-card h3{{font-size:13px;font-weight:600;color:var(--text);margin-bottom:4;display:flex;align-items:center;gap:6px}}
.chart-card .sub{{font-size:11px;color:var(--text2);margin-bottom:12px}}
.chart-card canvas{{width:100%;display:block}}
@media(max-width:980px){{.charts-row{{grid-template-columns:1fr}}}}

/* ===== 表格 ===== */
.filters{{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:14px 16px;margin-bottom:14px;display:flex;flex-wrap:wrap;gap:12px;align-items:center;box-shadow:var(--shadow)}}
.filters .fgroup{{display:flex;align-items:center;gap:6px}}
.filters label{{font-size:11px;color:var(--text2);font-weight:600;letter-spacing:.2px;text-transform:uppercase}}
.filters select,.filters input{{padding:7px 12px;border:1px solid var(--border);border-radius:var(--radius-s);background:var(--card2);color:var(--text);font-size:13px;font-family:inherit;transition:border-color .15s}}
.filters select:focus,.filters input:focus{{outline:none;border-color:var(--accent2)}}
.filters input{{flex:1;min-width:180px}}
.filters .stat{{margin-left:auto;font-size:12px;color:var(--text2);font-weight:500}}
.grade-chips{{display:flex;gap:5px;flex-wrap:wrap}}
.chip{{padding:4px 12px;border-radius:14px;font-size:12px;cursor:pointer;border:1px solid var(--border);background:var(--card);color:var(--text2);user-select:none;font-weight:500;transition:all .12s}}
.chip:hover{{border-color:var(--accent2);color:var(--accent)}}
.chip.active{{background:var(--accent);color:#fff;border-color:var(--accent);box-shadow:0 2px 6px rgba(230,81,0,.25)}}

.table-wrap{{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;box-shadow:var(--shadow)}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
thead th{{background:var(--accent-bg);color:var(--text);padding:11px 12px;text-align:left;font-weight:600;position:sticky;top:0;white-space:nowrap;border-bottom:1px solid var(--border2);font-size:12px;letter-spacing:.2px;cursor:pointer}}
thead th.center{{text-align:center}}
thead th:hover{{filter:brightness(0.96)}}
tbody td{{padding:10px 12px;border-bottom:1px solid var(--border);vertical-align:middle}}
tbody tr:last-child td{{border-bottom:none}}
tbody tr{{cursor:pointer;transition:background .1s}}
tbody tr:hover{{background:var(--accent-soft)}}
.grade-tag{{display:inline-block;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:700;white-space:nowrap;letter-spacing:.3px}}
.grade-tag.S{{background:var(--S);color:var(--S-t)}}
.grade-tag.A2{{background:var(--A2);color:var(--A2-t)}}
.grade-tag.A3{{background:var(--A3);color:var(--A3-t)}}
.grade-tag.B{{background:var(--B);color:var(--B-t)}}
.grade-tag.C{{background:var(--C);color:var(--C-t)}}
.grade-tag.DEAL{{background:#C8E6C9;color:#1B5E20}}
.prio{{display:inline-flex;align-items:center;justify-content:center;min-width:28px;height:24px;padding:0 8px;border-radius:6px;font-size:11px;font-weight:700;color:#fff;background:var(--text3);letter-spacing:.3px}}
.prio.p1{{background:var(--danger);box-shadow:0 1px 3px rgba(198,40,40,.3)}}
.prio.p2{{background:var(--accent2);box-shadow:0 1px 3px rgba(245,124,0,.3)}}
.prio.p3{{background:var(--warn);color:#3D2C1E}}
.prio.p4{{background:var(--good)}}
.prio.p5{{background:var(--text3)}}
.muted{{color:var(--text2)}}
.tnum{{font-variant-numeric:tabular-nums;font-feature-settings:"tnum"}}
.ph{{font-family:"SF Mono",SFMono-Regular,Consolas,monospace;font-weight:700;letter-spacing:.3px}}
.reasons{{font-size:11.5px;color:var(--text2);max-width:240px;line-height:1.45}}
.reasons span{{display:inline-block;margin-right:6px;padding:1px 6px;border-radius:4px;background:var(--accent-bg);color:var(--text)}}

.detail-row td{{background:var(--bg2);padding:0;border-bottom:1px solid var(--border)}}
.detail-box{{padding:18px 20px;display:grid;grid-template-columns:1fr 1fr 1fr;gap:18px}}
.detail-box .block h4{{font-size:12px;color:var(--accent);margin-bottom:8px;font-weight:700;letter-spacing:.3px;text-transform:uppercase;display:flex;align-items:center;gap:6px}}
.detail-box .block h4:before{{content:"";width:3px;height:12px;background:var(--accent);border-radius:2px}}
.detail-box .block ul{{list-style:none;padding-left:0}}
.detail-box .block li{{font-size:12px;padding:4px 0;color:var(--text);position:relative;padding-left:14px;line-height:1.5}}
.detail-box .block li:before{{content:"";position:absolute;left:4px;top:11px;width:4px;height:4px;border-radius:50%;background:var(--accent2)}}
.detail-box .block .tt{{font-size:12.5px;color:var(--text);line-height:1.65;padding:8px 12px;background:var(--card);border-radius:8px;border:1px solid var(--border)}}
.score-bar{{display:inline-flex;gap:2px;align-items:center}}
.score-cell{{display:inline-block;width:18px;height:18px;border-radius:4px;background:var(--bg2);text-align:center;line-height:18px;font-size:10px;color:var(--text2);font-weight:700}}
.score-cell.s5{{background:#558B2F;color:#fff}}.score-cell.s4{{background:#9CCC65;color:#fff}}.score-cell.s3{{background:#F0C419;color:#3D2C1E}}.score-cell.s2{{background:#FFB74D;color:#fff}}.score-cell.s1{{background:#E57373;color:#fff}}
@media(max-width:800px){{.detail-box{{grid-template-columns:1fr}}}}
.pager{{display:flex;justify-content:center;align-items:center;gap:6px;padding:16px;flex-wrap:wrap}}
.pager button{{padding:7px 14px;border:1px solid var(--border);border-radius:var(--radius-s);background:var(--card);color:var(--text);cursor:pointer;font-size:13px;font-family:inherit;transition:all .12s}}
.pager button:hover:not(:disabled){{border-color:var(--accent);color:var(--accent)}}
.pager button:disabled{{opacity:.4;cursor:not-allowed}}
.pager button.active{{background:var(--accent);color:#fff;border-color:var(--accent)}}
.pager .info{{font-size:12px;color:var(--text2);margin:0 8px}}
.no-data{{text-align:center;padding:60px 20px;color:var(--text2)}}
.no-data .ico{{font-size:32px;margin-bottom:8px;opacity:.5}}
.counselor-tag{{display:inline-block;padding:2px 9px;border-radius:6px;background:var(--accent-soft);color:var(--accent);font-size:11px;font-weight:600;border:1px solid var(--border2);white-space:nowrap}}
.foot{{text-align:center;color:var(--text3);font-size:11px;padding:18px 0;border-top:1px solid var(--border);margin-top:24px}}
.talk-box{{background:linear-gradient(135deg,#fff8e1,#fff3cd);border:1px solid #ffc107;border-radius:8px;padding:14px;margin:12px 0;font-size:13px;line-height:1.7}}
.talk-box .talk-title{{font-weight:800;color:#e65100;font-size:13px;margin-bottom:6px}}
.action-box{{background:linear-gradient(135deg,#e3f2fd,#bbdefb);border-left:3px solid var(--accent);border-radius:0 8px 8px 0;padding:12px 16px;margin:12px 0}}
.action-box .action-title{{font-weight:800;color:var(--accent);font-size:13px;margin-bottom:4px}}
.prod-list{{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0}}
.prod-card{{background:linear-gradient(135deg,#e8f0fe,#f0f4fc);border-left:3px solid var(--accent);border-radius:6px;padding:6px 10px;min-width:160px}}
.prod-card .pn{{font-weight:700;color:var(--accent);font-size:12px}}
.prod-card .pd{{font-size:11px;color:var(--text2);margin-top:2px}}
.intent-tag{{display:inline-flex;align-items:center;gap:4px;padding:3px 9px;border-radius:6px;font-size:11px;font-weight:600}}
.intent-tag.hi{{background:#ffebee;color:#c62828}}.intent-tag.md{{background:#fff3e0;color:#e65100}}.intent-tag.lo{{background:#f5f5f5;color:#888}}.intent-tag.rj{{background:#efeef0;color:#999}}
</style>
</head>
<body>

<div class="topbar">
  <div class="brand"><div class="logo">SDR</div><div><div class="title">线索池SDR机会中心</div><div class="sub" id="subInfo">投流线索 · 智能分级 · 产品推荐 | 石摩销售部线索跟进</div></div></div>
  <div class="nav">
    <div class="nav-item active" data-page="overview">总览</div>
    <div class="nav-item" data-page="list">机会列表<span class="badge" id="listBadge">0</span></div>
    <div class="nav-item" data-page="channel">渠道效果</div>
  </div>
  <div class="spacer"></div>
  <button class="iconbtn" id="themeBtn" title="切换主题">&#127769;</button>
</div>

<!-- 总览 -->
<div id="page-overview" class="page active">
  <div class="kpi-grid" id="kpiGrid"></div>
  <div class="charts-row">
    <div class="chart-card"><h3>分级分布</h3><div class="sub">S/A2/A3/B/C 五档线索占比</div><canvas id="pieChart" height="260"></canvas></div>
    <div class="chart-card"><h3>渠道分布 TOP10</h3><div class="sub">按线索数量排序</div><canvas id="chChart" height="260"></canvas></div>
    <div class="chart-card"><h3>部门分布</h3><div class="sub">按分配部门统计</div><canvas id="deptChart" height="260"></canvas></div>
  </div>
  <div class="chart-card" style="margin-top:16px"><h3>顾问线索分布</h3><div class="sub">按归属顾问统计 · 点击筛选</div><div id="counselorBars"></div></div>
</div>

<!-- 列表 -->
<div id="page-list" class="page">
  <div class="filters">
    <div class="fgroup"><label>分级</label><div class="grade-chips" id="gradeChips">
      <span class="chip active" data-grade="">全部</span>
      <span class="chip" data-grade="S" style="background:var(--S);color:var(--S-t)">S</span>
      <span class="chip" data-grade="A2" style="background:var(--A2);color:var(--A2-t)">A2</span>
      <span class="chip" data-grade="A3" style="background:var(--A3);color:var(--A3-t)">A3</span>
      <span class="chip" data-grade="B" style="background:var(--B);color:var(--B-t)">B</span>
      <span class="chip" data-grade="C" style="background:var(--C);color:var(--C-t)">C</span>
    </div></div>
    <div class="fgroup"><label>意向</label><select id="fltItl"><option value="">全部</option><option value="high">高意向</option><option value="medium">中意向</option><option value="low">低意向</option><option value="rejected">已拒绝</option></select></div>
    <div class="fgroup"><label>部门</label><select id="fltDept"><option value="">全部部门</option></select></div>
    <div class="fgroup"><label>渠道</label><select id="fltCh"><option value="">全部渠道</option></select></div>
    <div class="fgroup"><label>成交</label><select id="fltDeal"><option value="f" selected>未成交</option><option value="t">已成交</option><option value="">全部</option></select></div>
    <input id="search" type="text" placeholder="&#128269; 手机号/备注/来源..." style="max-width:220px">
    <div class="fgroup"><label>&#128197;</label><input type=date id="fltDateFrom"> <span style="color:var(--text2)">至</span> <input type=date id="fltDateTo"></div>
    <div class="stat" id="filterStat"></div>
  </div>
  <div class="table-wrap"><table><thead><tr id="theadRow"></tr></thead><tbody id="tbody"></tbody></table></div>
  <div class="pager" id="pager"></div>
</div>

<!-- 渠道分析 -->
<div id="page-channel" class="page">
  <div class="chart-card"><h3>渠道效果分析</h3><div class="sub">各渠道线索量 × 成交转化率</div><canvas id="chConvChart" height="360"></canvas></div>
  <div class="charts-row" style="margin-top:16px">
    <div class="chart-card"><h3>来源TOP15</h3><canvas id="srcChart" height="280"></canvas></div>
    <div class="chart-card"><h3>意向分布</h3><canvas id="itlChart" height="280"></canvas></div>
  </div>
</div>

<div class="foot">线索池SDR机会中心 v4.0 · 数据源:石摩「销售部线索跟进6.30 787」 · 生成于 {gen_ts}</div>

<script>
const DATA={data_json};
const META={meta_json};

/* ===== 主题 ===== */
const themeBtn=document.getElementById('themeBtn');
function setTheme(t){{document.documentElement.setAttribute('data-theme',t);themeBtn.textContent=t==='dark'?'\u2600\uFE0F':'\uD83C\uDF19';localStorage.setItem('lead-theme',t);drawAllCharts();if(typeof drawPageChannel==='function')drawPageChannel();}}
themeBtn.onclick=()=>{{const c=document.documentElement.getAttribute('data-theme')||'light';setTheme(c==='dark'?'light':'dark');}};
const savedTheme=localStorage.getItem('lead-theme');
if(savedTheme)setTheme(savedTheme);
else if(window.matchMedia&&window.matchMedia('(prefers-color-scheme:dark)').matches)setTheme('dark');

/* ===== 工具函数 ===== */
function esc(s){{return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}}
function cv(n){{return getComputedStyle(document.documentElement).getPropertyValue(n).trim();}}
function gClr(g){{return cv('--'+g)||'#ccc';}}
function tClr(){{return cv('--text');}} function t2Clr(){{return cv('--text2');}} function bdClr(){{return cv('--border');}}
function acClr(){{return cv('--accent');}} function ac2Clr(){{return cv('--accent2');}}
function fmtM(v){{if(!v)return '\u00A50';if(v>=10000)return '\u005C'+(v/10000).toFixed(2)+'\u4E07';return '\u005C'+Math.round(v);}}
function tgG(g,l,c){{if(g==='DEAL')return '<span class="grade-tag DEAL">\u2705 \u5DF2\u6210\u4EA4</span>';if(g==='S')return '<span class="grade-tag S">'+esc(l)+'</span>';if(g==='A2')return '<span class="grade-tag A2">'+esc(l)+'</span>';if(g==='A3')return '<span class="grade-tag A3">'+esc(l)+'</span>';return '<span class="grade-tag '+g+'">'+esc(c||g)+'</span>';}}
function tgI(it){{if(it==='high')return '<span class="intent-tag hi">\u9AD8\u610F\u5411</span>';if(it==='medium')return '<span class="intent-tag md">\u4E2D\u610F\u5411</span>';if(it==='low')return '<span class="intent-tag lo">\u4F4E</span>';if(it==='rejected')return '<span class="intent-tag rj\">\u62D2</span>';return '<span style="background:#f0f0f0;color:#888;padding:2px 6px;border-radius:4px;font-size:11px">?</span>';}}
function tgAge(a){{if(a==null)return'-';if(a<=3)return '<span style="background:#e8f5e9;color:#2e7d32;padding:1px 6px;border-radius:4px;font-size:11px;font-weight:600">'+a+'\u5929</span>';if(a<=7)return a+'\u5929';if(a<=21)return a+'\u5929';return '<span style="color:#dc3545;font-weight:600">'+a+'\u5929</span>';}}

/* ===== 筛选状态 ===== */
let curGrade='',curItl='',curDept='',curCh='',curDeal='f',curKw='',curDFrom='',curDTo='',PAGE=1,PGSZ=100,SORT_COL='sc',SORT_DIR=-1,FILTERED=[];
let expandedRow=null;

/* ===== 导航 ===== */
document.querySelectorAll('.nav-item').forEach(t=>{{t.onclick=()=>{{document.querySelectorAll('.nav-item').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.page').forEach(x=>x.classList.remove('active'));t.classList.add('active');document.getElementById('page-'+t.dataset.page).classList.add('active');if(t.dataset.page==='overview')drawAllCharts();if(t.dataset.page==='channel')drawPageChannel();if(t.dataset.page==='list'&&FILTERED.length===0)applyFilter();}};}});

/* ===== Canvas工具 ===== */
function setupCanvas(cv){{const dpr=window.devicePixelRatio||1;const w=cv.clientWidth||cv.parentElement.clientWidth-36;const h=parseInt(cv.getAttribute('height'))||260;cv.width=w*dpr;cv.height=h*dpr;cv.style.height=h+'px';const ctx=cv.getContext('2d');ctx.scale(dpr,dpr);ctx.clearRect(0,0,w,h);return {{ctx,w,h}};}}
function drawPie(){{const cv=document.getElementById('pieChart');const {{ctx,w,h}}=setupCanvas(cv);const grades=['S','A2','A3','B','C'];let dealCount=0;const data=grades.map(g=>({{g,n:FILTERED.filter(c=>c.g===g).length}}));dealCount=FILTERED.filter(c=>c.deal).length;const total=data.reduce((s,d)=>s+d.n,0)+dealCount;if(total===0)return;const cx=w*0.34,cy=h/2,R=Math.min(w*0.34,h*0.42);let a=-Math.PI/2;data.forEach(d=>{{if(d.n===0)return;const ang=d.n/total*Math.PI*2;ctx.beginPath();ctx.moveTo(cx,cy);ctx.arc(cx,cy,R,a,a+ang);ctx.closePath();ctx.fillStyle=gClr(d.g);ctx.fill();ctx.strokeStyle=cv('--card');ctx.lineWidth=3;ctx.stroke();a+=ang;}});if(dealCount>0){{const ang=dealCount/total*Math.PI*2;ctx.beginPath();ctx.moveTo(cx,cy);ctx.arc(cx,cy,R,a,a+ang);ctx.closePath();ctx.fillStyle='#2E7D32';ctx.fill();ctx.strokeStyle=cv('--card');ctx.lineWidth=3;ctx.stroke();}}ctx.fillStyle=tClr();ctx.font='bold 26px "PingFang SC","Microsoft YaHei"';ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(total,cx,cy-8);ctx.fillStyle=t2Clr();ctx.font='11px "PingFang SC"';ctx.fillText('\u603B\u7EBF\u7D22',cx,cy+14);const lx=w*0.66;let ly=h/2-(data.length*22)/2+10;ctx.font='12px "PingFang SC"';ctx.textAlign='left';ctx.textBaseline='middle';const allItems=[...data];if(dealCount>0) allItems.push({{g:'DEAL',n:dealCount}});allItems.forEach(d=>{{ctx.fillStyle=gClr(d.g);ctx.fillRect(lx,ly-6,12,12);ctx.fillStyle=tClr();ctx.fillText(d.g+'  '+d.n+' ('+(d.n/total*100).toFixed(1)+'%)',lx+18,ly);ly+=22;}});}}
function drawBar(cv,items,opts){{const {{ctx,w,h}}=setupCanvas(cv);if(!items.length)return;const padL=opts.padL||44,padR=12,padT=16,padB=48;const cw=w-padL-padR,ch=h-padT-padB;const maxV=Math.max.apply(null,items.map(i=>i.v))||1;let niceMax=1;const mag=Math.pow(10,Math.floor(Math.log10(maxV)));niceMax=Math.ceil(maxV/mag)*mag;const gap=cw/items.length,bw=gap*0.62;ctx.strokeStyle=bdClr();ctx.fillStyle=t2Clr();ctx.font='10px "PingFang SC"';ctx.textAlign='right';ctx.textBaseline='middle';const steps=4;for(let i=0;i<=steps;i++){{const v=niceMax*i/steps;const y=padT+ch-ch*i/steps;ctx.beginPath();ctx.moveTo(padL,y);ctx.lineTo(w-padR,y);ctx.strokeStyle=bdClr();ctx.globalAlpha=.5;ctx.stroke();ctx.globalAlpha=1;ctx.fillText(v>=1000?(v/1000)+'k':Math.round(v),padL-6,y);}}const colors=opts.colors||[acClr()];items.forEach((it,i)=>{{const x=padL+i*gap+(gap-bw)/2;const bh=ch*(it.v/niceMax);const y=padT+ch-bh;const col=Array.isArray(colors)?(colors[i%colors.length]):colors;ctx.fillStyle=col;const r=Math.min(4,bw/2);ctx.beginPath();ctx.moveTo(x,y+r);ctx.arcTo(x,y,x+bw,y+r,r);ctx.arcTo(x+bw,y,x+bw,y+bh,r);ctx.lineTo(x+bw,y+bh);ctx.lineTo(x,y+bh);ctx.closePath();ctx.fill();ctx.fillStyle=tClr();ctx.font='bold 11px "PingFang SC"';ctx.textAlign='center';ctx.textBaseline='bottom';ctx.fillText(it.v,x+bw/2,y-3);ctx.fillStyle=t2Clr();ctx.font='11px "PingFang SC"';ctx.textBaseline='top';const lbl=it.l.length>6?it.l.slice(0,6):it.l;ctx.fillText(lbl,x+bw/2,padT+ch+8);}});}}
function drawAllCharts(){{renderKPI();drawPie();drawChChart();drawDeptChart();renderCounselorBars();}}

/* ===== KPI ===== */
function renderKPI(){{const g={{S:0,A2:0,A3:0,B:0,C:0,DEAL:0}};let totalAmt=0;FILTERED.forEach(c=>{{g[c.g]=(g[c.g]||0)+1;if(c.amt>0)totalAmt+=c.amt;}});const total=FILTERED.length;document.getElementById('listBadge').textContent=total;const items=[
{{lbl:'\u6709\u6548\u7EBF\u7D22',val:total,cls:'',mini:'<span>\u672A\u6210\u4EA4 <b>'+total+'</b></span><span>\u5DF2\u6210\u4EA4 <b>'+g.DEAL+'</b></span><span>\u8F6C\u5316 <b>'+(total?(g.DEAL/total*100).toFixed(1):0)+'%</b></span>'}},
{{lbl:'S \u00B7 \u7ACB\u5373',val:g.S,cls:'grade S',mini:'<span>\u5360\u6BD4 <b>'+(g.S/total*100).toFixed(1)+'%</b></span>'}},
{{lbl:'A2 \u00B7 \u91CD\u70B9',val:g.A2,cls:'grade A2',mini:'<span>\u5360\u6BD4 <b>'+(g.A2/total*100).toFixed(1)+'%</b></span>'}},
{{lbl:'A3 \u00B7 \u6B63\u5E38',val:g.A3,cls:'grade A3',mini:'<span>\u5360\u6BD4 <b>'+(g.A3/total*100).toFixed(1)+'%</b></span>'}},
{{lbl:'B \u00B7 \u4F4E\u4F18',val:g.B,cls:'grade B',mini:'<span>\u5360\u6BD4 <b>'+(g.B/total*100).toFixed(1)+'%</b></span>'}},
{{lbl:'C \u00B7 \u6682\u7F13',val:g.C,cls:'grade C',mini:'<span>\u5360\u6BD4 <b>'+(g.C/total*100).toFixed(1)+'%</b></span>'}},
{{lbl:'\u6210\u4EA4\u91D1\u989D',val:fmtM(totalAmt),cls:'',mini:'<span>\u5747\u4EF7 <b>'+fmtM(totalAmt/Math.max(g.DEAL,1))+'</b></span>'}},
];document.getElementById('kpiGrid').innerHTML=items.map(it=>'<div class="kpi '+it.cls+'"><div class="lbl">'+it.lbl+'</div><div class="val">'+it.val+'</div>'+(it.mini?'<div class="kpi-mini">'+it.mini+'</div>':'')+'</div>').join('');
document.getElementById('subInfo').textContent='\u6295\u6D41\u7EBF\u7D22 \u00B7 '+total+' \u6761\u6709\u6548 \u00B7 '+g.DEAL+' \u5DF2\u6210\u4EA4 \u00B7 '+fmtM(totalAmt);}}

/* ===== 渠道图表 ===== */
function drawChChart(){{const cnt={{}};FILTERED.forEach(c=>{{cnt[c.ch]=(cnt[c.ch]||0)+1;}});const items=Object.keys(cnt).map(k=>({{l:k,v:cnt[k]}})).sort((a,b)=>b.v-a.v).slice(0,10);const palette=['#E65100','#F57C00','#FB8C00','#FFA726','#FFB74D','#FFCA28','#FFD54F','#FFE082','#FFECB3','#FFF59D'];drawBar(document.getElementById('chChart'),items,{{padL:48,colors:palette}});}}
function drawDeptChart(){{const cnt={{}};FILTERED.forEach(c=>{{cnt[c.dept]=(cnt[c.dept]||0)+1;}});const items=Object.keys(cnt).map(k=>({{l:k,v:cnt[k]}})).sort((a,b)=>b.v-a.v).slice(0,10);drawBar(document.getElementById('deptChart'),items,{{padL:56,colors:['#E65100','#F57C00','#7CB342','#1976D2','#78909C','#BA68C8']}});}}
function renderCounselorBars(){{const cnt={{}};FILTERED.forEach(c=>{{cnt[c.co]=(cnt[c.co]||0)+1;}});const items=Object.keys(cnt).map(k=>({{name:k,n:cnt[k]}})).sort((a,b)=>b.n-a.n);const maxN=Math.max.apply(null,items.map(i=>i.n))||1;const total=FILTERED.length;const box=document.getElementById('counselorBars');if(!box)return;box.innerHTML=items.slice(0,20).map(it=>{{const pct=(it.n/maxN*100).toFixed(1);const share=(it.n/total*100).toFixed(1);return '<div style="display:flex;align-items:center;gap:10px;cursor:pointer;padding:6px 8px;border-radius:8px;transition:background .12s" onclick="filterByCounselor(\\''+esc(it.name)+'\\')"><div style="min-width:90px;font-size:13px;font-weight:600;color:var(--text)">'+esc(it.name)+'</div><div style="flex:1;height:24px;background:var(--bg2);border-radius:6px;overflow:hidden;border:1px solid var(--border)"><div style="height:100%;width:'+pct+'%;background:linear-gradient(90deg,var(--accent),var(--accent2));border-radius:6px"></div></div><div style="min-width:100px;text-align:right;font-size:13px"><b style="color:var(--text)">'+it.n+'</b> <span style="color:var(--text2);font-size:11px">('+share+'%)</span></div></div>';}}).join('');}}

window.addEventListener('resize',()=>{{if(document.getElementById('page-overview').classList.contains('active'))drawAllCharts();}});

/* ===== 筛选 ===== */
function applyFilter(){{FILTERED=DATA.filter(c=>{{if(curGrade&&c.g!==curGrade)return false;if(curItl&&c.itl!==curItl)return false;if(curDept&&c.dept!==curDept)return false;if(curCh&&c.ch!==curCh)return false;if(curDeal==='t'&&!c.deal)return false;if(curDeal==='f'&&c.deal)return false;if(curKw){{const s=(c.ph+' '+c.oc+' '+c.note+' '+c.src+' '+c.ind+' '+c.st+' '+c.co).toLowerCase();if(!s.includes(curKw)&&!c.ph.includes(curKw))return false;}}if(curDFrom||curDTo){{const ds=c.at||'';if(ds){{const dv=ds.replace(/\\./g,'-');if(curDFrom&&dv<curDFrom)return false;if(curDTo&&dv>curDTo)return false;}}}}return true;}});FILTERED.sort((a,b)=>{{let v=a[SORT_COL]!=null?a[SORT_COL]:'',vv=b[SORT_COL]!=null?b[SORT_COL]:'';if(typeof v==='number')return(v-vv)*SORT_DIR;v=String(v).toLowerCase();vv=String(vv).toLowerCase();return v<vv?-1*SORT_DIR:v>vv?1*SORT_DIR;}});PAGE=1;renderKPI();renderList();renderFilterStat();buildSelects();}}
function buildSelects(){{const depts=[...new Set(FILTERED.map(c=>c.dept))],chs=[...new Set(FILTERED.map(c=>c.ch))];const ds=document.getElementById('fltDept');if(ds.options.length<=1)depts.forEach(d=>ds.innerHTML+='<option value="'+esc(d)+'">'+esc(d)+'</option>');const cs=document.getElementById('fltCh');if(cs.options.length<=1)chs.forEach(c=>cs.innerHTML+='<option value="'+esc(c)+'">'+esc(c)+'</option>');}}
function renderFilterStat(){{document.getElementById('filterStat').textContent=FILTERED.length+' \u6761 / '+DATA.length+' \u603B';}}
function filterByCounselor(name){{document.querySelectorAll('.nav-item').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.page').forEach(x=>x.classList.remove('active'));document.querySelector('.nav-item[data-page="list"]').classList.add('active');document.getElementById('page-list').classList.add('active');curCo=name;const el=document.getElementById('fltDept');for(let i=0;i<el.options.length;i++){{if(el.options[i].value.indexOf(name)>=0){{el.options[i].selected=true;break;}}}}applyFilter();}}

/* 筛选事件绑定 */
document.getElementById('search').addEventListener('input',e=>{{curKw=e.target.value.toLowerCase();applyFilter();}});
document.querySelectorAll('#gradeChips .chip').forEach(c=>{{c.onclick=()=>{{document.querySelectorAll('#gradeChips .chip').forEach(x=>x.classList.remove('active'));c.classList.add('active');curGrade=c.dataset.grade;applyFilter();}};}});
document.getElementById('fltItl').onchange=e=>{{curItl=e.target.value;applyFilter();}};
document.getElementById('fltDeal').onchange=e=>{{curDeal=e.target.value;applyFilter();}};
document.getElementById('fltDateFrom').onchange=e=>{{curDFrom=e.target.value;applyFilter();}};
document.getElementById('fltDateTo').onchange=e=>{{curDTo=e.target.value;applyFilter();}};

/* 排序 */
function sortTable(col){{if(SORT_COL===col){{SORT_DIR*=-1;}}else{{SORT_COL=col;SORT_DIR=-1;}}applyFilter();}}

/* ===== 表格渲染 ===== */
function renderList(){{const thead=document.getElementById('theadRow');const tbody=document.getElementById('tbody');
const cols=[
  {{k:'g',l:'\u5206\u7EA7',w:64,f:(c)=>tgG(c.g,c.g,c.g)}},
  {{k:'sc',l:'\u8BC4\u5206',w:46}},
  {{k:'itl',l:'\u610F\u5411',w:52,f:(c)=>tgI(c.itl)}},
  {{k:'ind',l:'\u884C\u4E1A',w:70}},
  {{k:'dept',l:'\u90E8\u95E8',w:82}},
  {{k:'co',l:'\u987E\u95EE',w:62}},
  {{k:'ch',l:'\u6E20\u9053',w:90}},
  {{k:'at',l:'\u5206\u914D',w:60,f:(c)=>tgAge(c.age)}},
  {{k:'ph',l:'\u624B\u673A\u53F7',w:120,f:(c)=>'<span class="ph">'+esc(c.ph)+'</span>'}},
];
thead.innerHTML=cols.map(c=>{{const arr=SORT_COL===c.k?' '+(SORT_DIR===1?'\u25B2':'\u25BC'):'';return '<th style="width:'+c.w+'px" onclick="sortTable(\\''+c.k+'\\')">'+c.l+arr+'</th>';}}).join('<th style="width:38px"></th>');
const totalPages=Math.max(1,Math.ceil(FILTERED.length/PGSZ));
if(PAGE>totalPages)PAGE=totalPages;
const start=(PAGE-1)*PGSZ,end=Math.min(start+PGSZ,FILTERED.length);
const rows=FILTERED.slice(start,end);
tbody.innerHTML=rows.map((c,idx)=>{{const ri=start+idx;const cls=c.g==='S'?'style="background:var(--S)"':c.g==='A2'?'style="background:var(--A2)"':c.g==='A3'?'style="background:var(--A3)"':'';const tds=cols.map(col=>{{const v=col.f?col.f(c):esc(String(c[col.k]==null?'-':c[col.k]));return'<td>'+v+'</td>';}}).join('');
return'<tr data-idx="'+ri+'" '+cls+' onclick="toggleExpand('+ri+')">'+tds+'<td><button onclick="event.stopPropagation();copyPhone(\\''+esc(c.ph.replace(/'/g,"\\\\'"))+'\\')"style="padding:2px 6px;font-size:10px;border:1px solid var(--border);background:var(--card);border-radius:4px;cursor:pointer;font-family:inherit">\u590D\u5236</button></td></tr>';
}}).join('');
renderPager();
}}
function renderPager(){{const tp=Math.max(1,Math.ceil(FILTERED.length/PGSZ)),pg=document.getElementById('pager');
const start=(PAGE-1)*PGSZ+1,end=Math.min(PAGE*PGSZ,FILTERED.length);
pg.innerHTML='<button onclick="goPage('+(PAGE-1)+')" '+(PAGE<=1?'disabled':'')+'>\u25C0</button>'
+'<span class="info">'+start+'-'+end+' / '+FILTERED.length+' \u6761 (\u7B2C'+PAGE+'/'+tp'\u9875)</span>'
+'<button onclick="goPage('+(PAGE+1)+')" '+(PAGE>=tp?'disabled':'')+'>\u25B6</button>'
+'&nbsp;\u6BCF\u9875<select onchange="changePageSize(this.value)"><option'+(PGSZ===50?' selected':'')+'>50</option><option'+(PGSZ===100?' selected':'')+'>100</option><option'+(PGSZ===200?' selected':'')+'>200</option></select>\u6761';}}
function goPage(p){{const tp=Math.ceil(FILTERED.length/PGSZ);if(p>=1&&p<=tp){{PAGE=p;renderList();window.scrollTo({{top:0,behavior:'smooth'}});}}}}
function changePageSize(n){{PGSZ=parseInt(n)||100;PAGE=1;renderList();}}

/* ===== 详情展开行 ===== */
function toggleExpand(idx){{const row=document.querySelector('tr[data-idx="'+idx+'"]');if(!row)return;const next=row.nextElementSibling;if(next&&next.classList.contains('detail-row')){{row.classList.remove('expanded');next.remove();expandedRow=null;return;}}if(expandedRow){{const prevExp=document.querySelector('tr.expanded');if(prevExp){{prevExp.classList.remove('expanded');const prevDetail=prevExp.nextElementSibling;if(prevDetail&&prevDetail.classList.contains('detail-row'))prevDetail.remove();}}}row.classList.add('expanded');expandedRow=row;const c=FILTERED[idx];if(!c)return;const scd=c.scd||{{}};const scCells=['L1','L2','L3','L4','L5','L6'].map(k=>{{const v=scd[k];const cl=v>=4?'s5':v>=3?'s4':v>=2?'s3':v>=1?'s2':'s1';return '<div class="score-cell '+cl+'">'+v+'</div>';}}).join('');
// 话术生成
const talk=generateTalk(c);
// 产品推荐
const prods=generateProds(c);const prodHtml=prods.map(p=>'<div class="prod-card"><div class="pn">\uD83D\uDCE6 '+esc(p.n)+'</div><div class="pd">'+esc(p.c)+' | '+esc(p.d)+' | '+esc(p.p)+'</div></div>').join('');
// 跟进记录
let frHtml='';[c.f1,c.f2,c.f3,c.f4].forEach((fv,n)=>{{if(fv)frHtml+='<li><strong>'+['\u4E00','\u4E8C','\u4E09','\u56DB'][n]+':</strong> '+esc(fv)+'</li>';}});const detailTr=document.createElement('tr');detailTr.className='detail-row';
detailTr.innerHTML='<td colspan="'+(cols.length+1)+'"><div class="detail-box">'
+'<div class="block"><h4>\u8BC4\u5206\u660E\u7EC6</h4><div class="score-bar">'+scCells+'</div><p style="font-size:11.5px;color:var(--text2);margin-top:6px">L1\u610F\u5411 L2\u6E20\u9053 L3\u6765\u6E90 L4\u8DDF\u8fdb L5\u65B0\u9C9C L6\u89E6\u8FBE | \u603B\u5206:'+c.sc+'/30</p></div>'
+'<div class="block"><h4>\u5BA2\u6237\u753B\u50CF</h4><ul><li>\u884C\u4E1A: <b>'+esc(c.ind)+'</b></li><li>\u89C4\u6A21: <b>'+(esc(c.scl)||'-')+'</b></li><li>\u6E20\u9053: <b>'+esc(c.ch)+'</b></li><li>\u6765\u6E90: <b>'+esc(c.src)+'</b></li><li>\u90E8\u95E8: <b>'+esc(c.dept)+'</b></li><li>\u987E\u95EE: <b>'+esc(c.co)+'</b></li></ul></div>'
+'<div class="block"><h4>\u63A8\u8367\u4EA7\u54C1</h4>'+(prodHtml||'<div class="tt">\u6682\u65E0\u63A8\u8350(\u7531\u4E8E\u884C\u4E1A/\u6E20\u9053\u4FE1\u606F\u4E0D\u8DB3)</div>')+'</div>'
+'</div>'
+(talk?'<div class="talk-box"><div class="talk-title">\uD83C\uDFA4 \u9500\u552E\u8BDD\u672F(\u53EF\u76F4\u63A5\u5FF5\u7ED9\u5BA2\u6237)</div><div style="white-space:pre-line;color:#333">'+talk.talk+'</div></div>':'')
+'<div class="action-box"><div class="action-title">\u2B07\uFE0F \u5EFA\u8BAE\u52A8\u4F5C</div><div>'+(talk.action||'-')+'</div></div>'
+(frHtml?'<div style="padding:10px 14px;margin:8px 0;background:var(--card);border-radius:8px;border:1px solid var(--border)"><h4 style="font-size:12px;color:var(--accent);margin-bottom:6px">\uD83D\uDCDD \u8DDF\u8BBF\u8BB0\u5F55</h4><ul style="list-style:none;padding-left:0">'+frHtml+'</ul></div>':'')
+(c.note?'<div style="margin:8px 0;padding:8px 12px;background:#f5f5f5;border-radius:6px;font-size:12px"><strong style="color:var(--text2)">\u5907\u6CE8:</strong> '+esc(c.note)+'</div>':'')
+'<div style="margin-top:12px;display:flex;gap:8px">'
+'<button onclick="copyPhone(\\''+esc(c.ph.replace(/'/g,"\\\\'"))+'\\')"style="padding:8px 16px;background:var(--accent);color:#fff;border:none;border-radius:6px;cursor:pointer;font-weight:700;font-size:12px;font-family:inherit">\uD83DDCCE \u590D\u5236\u624B\u673A</button>'
+'<button onclick="this.innerText=\u2705\u5DF2\u590D\u5236;navigator.clipboard.writeText(\\''+esc(talk.talk||'').replace(/'/g,"\\\\'")+'\\')"style="padding:8px 16px;background:var(--accent2);color:#fff;border:none;border-radius:6px;cursor:pointer;font-weight:700;font-size:12px;font-family:inherit">\uD83DUDCB \u590D\u5236\u8BDD\u672F</button>'
+'</div></td></tr>';row.after(detailTr);}}

function copyPhone(p){{navigator.clipboard.writeText(p||'').then(()=>alert('\u2705 \u5DF2\u590D\u5236\u624B\u673A\u53F7: '+p));}}
function copyText(t,n){{navigator.clipboard.writeText(t||'').then(()=>alert('\u2705 \u5DF2\u590D\u5236'+n));}}

/* ===== 话术生成引擎 ===== */
function generateTalk(c){{const ind=c.ind,it=c.itl,ch=c.ch,src=c.src,note=(c.note||'').substring(0,200);let talk='',action='';
// 根据行业匹配开场白
const openings={{'服装鞋帽':'您好\uff01\u770B\u5230\u60A8\u5728\u5C0F\u7EA2\u4E66/\u6296\u97F3\u4E0A\u5173\u6CE8\u4E86\u6211\u4EEC\u79D1\u6280\uff0C\u6211\u662F\u79D1\u6280\u54E1\u3002\u60A8\u73B0\u5728\u7528\u7684\u8FDB\u9500\u5B58\u8F6F\u4EF6\u662F\u81EA\u5DF1\u5F00\u53D1\u7684\u8FD8\u662F\u4E70\u7684\uff1f\u5982\u679C\u662F\u81EA\u5DF1\u5F00\u53D1\u7684\uff0c\u592A\u8D39\u65F6\u95F4\u4E86\u3002\u6211\u4EEC\u8FDB\u9500\u5B58\u53EF\u4EE5\u76F4\u63A5\u7EDF\u8BA1\u4F60\u6BCF\u4E2A\u6B3E\u5F0F\u5356\u51FA\u591A\u5C11\u3001\u5E93\u5B58\u8FD8\u6709\u591A\u5C11\u3001\u54EA\u4E9B\u6B3E\u5356\u5F97\u597D\u54EA\u4E9B\u4E0D\u884C\uff0C\u4E00\u76EE\u4E86\u7136\u3002','食品生鲜':'\u60A8\u597D\uff01\u6211\u662F\u79D1\u6280\u54E1\u3002\u770B\u5230\u60A8\u5728\u67E5\u770B\u8FDB\u9500\u5B58\u7CFB\u7EDF\uff0C\u60A8\u662F\u505A\u98DF\u54C1/\u751F\u9C9C\u7684\u5427\uff1f\u6211\u4EEC\u7684\u5BA2\u6237\u5F88\u591A\u90FD\u662F\u5199\u9910\u996E\u7684\uff0C\u6700\u5934\u75BC\u7684\u5C31\u662F\u4FDD\u8D28\u671F\u7BA1\u7406\u548C\u5E94\u8D26\u5E94\u4ED8\u3002\u8FDB\u9500\u5B58\u53EF\u4EE5\u81EA\u52A8\u63D0\u9192\u60A8\u54EA\u4E9B\u8D27\u54C1\u5FEB\u8FC7\u671F\u4E86\uff0C\u964D\u4F4E\u635F\u8017\u3002','美容美发':'\u60A8\u597D\uff01\u6211\u662F\u79D1\u6280\u54E1\u3002\u60A8\u662F\u505A\u7F8E\u5BB9/\u7F8E\u53D1\u7684\u5427\uff1f\u8FD9\u884C\u5BA2\u6237\u590D\u8D2F\u7387\u5F88\u9AD8\uff0C\u5982\u679C\u6709\u4E00\u5957\u7CFB\u7EDF\u80FD\u5E2E\u60A8\u7BA1\u7406\u4F1A\u5458\u4FE1\u606F\u3001\u79EF\u5206\u3001\u50A8\u503C\uFF0C\u90A3\u5BF9\u63D0\u5347\u590D\u8D2D\u771F\u7684\u6709\u5E2E\u52A9\u3002\u6211\u4EEC\u7684\u4F1A\u5458\u7CFB\u7EDF\u53EF\u4EE5\u8BA9\u5BA2\u6237\u5728\u5FAE\u4FE1\u4E0A\u76F4\u63A5\u67E5\u79EF\u5206\u3001\u5151\u6362\u3001\u9884\u7EA6\u3002','家居家纺':'\u60A8\u597D\uff01\u6211\u662F\u79D1\u6280\u54E1\u3002\u60A8\u662F\u505A\u5BB6\u5C45/\u5BB6\u7eba\u7684\u5427\uff1f\u6211\u4EEC\u6709\u5F88\u591A\u5BB6\u5C45\u5BA2\u6237\u90FD\u5728\u7528\u8FDB\u9500\u5B58\uFF0C\u7279\u522B\u662F\u591A\u5E97\u94FA\u7BA1\u7406\u3001\u5E93\u5B54\u8C03\u62E8\u3001\u8D27\u6E90\u5171\u4EAB\u8FD9\u4E9B\u529F\u80FD\u5BF9\u60A8\u7684\u4E1A\u52A1\u5E2E\u52A9\u5F88\u5927\u3002','3C数码':'\u60A8\u597D\uff01\u6211\u662F\u79D1\u6280\u54E1\u3002\u770B\u5230\u60A8\u5173\u6CE8\u4E86\u79D1\u6280\u7C7B\u4EA7\u54C1\u3002\u6211\u4EEC\u7684\u7CFB\u7EDF\u5BF9\u6570\u7801\u7C7B\u5546\u54C1\u7684\u5E8F\u5217\u53F7/\u578B\u53F7\u7BA1\u7406\u3001SN\u7801\u8ffd\u6EAF\u5F88\u65B9\u4FBF\u3002','default':'\u60A8\u597D\uff01\u6211\u662F\u79D1\u6280\u54E1\u3002\u770B\u5230\u60A8\u5728\u5173\u6CE8\u6211\u4EEC\u7684\u4EA7\u54C1\u3002\u60A8\u73B0\u5728\u7528\u7684\u662F\u4EC0\u4E48\u7BA1\u7406\u65B9\u5F0F\u5462\uFF1F\u662F\u8BB0\u5FC3\u8D26/\u672C\u5B50\uFF0C\u8FD8\u662F\u5DF2\u7ECF\u5728\u7528\u8F6F\u4EF6\u4E86\uFF1F'}};
talk=openings[ind]||openings['default'];
// 意向追加
if(it==='high'){{talk+='\\n\\n[\u9AD8\u610F\u5411] \u5BA2\u6237\u5DF2\u8868\u793A\u8FDB\u4E00\u6B65\u4E86\u89E3\u7684\u610F\u5411\uFF0C\u76F4\u63A5\u5F04\u6E05\u9700\u6C42\u70B9\uFF0C\u9488\u5BF9\u6027\u63A8\u8350\u65B9\u6848\uFF0C\u5FEB\u901F\u63A8\u8FDB\u5230\u4EA7\u54C1\u6F14\u793A\u73AF\u8282\u3002';action='\u24D8 24\u5C0F\u65F6\u5185\u5B89\u6392\u4EA7\u54C1\u6F14\u793A\uFF0C\u91CD\u70B9\u63A8\u8FDB\u8FDB\u9500\u5B58\u4E13\u4E1A\u7248+\u5FAE\u5546\u57CE\uFF1B'}}
else if(it==='medium'){{talk+='\\n\\n[\u4E2D\u610F\u5411] \u5BA2\u6237\u6709\u5174\u8DA3\u4F46\u8FD8\u5728\u8003\u8651\u3002\u5148\u4E86\u89E3\u5BA2\u6237\u73B0\u6709\u7684\u75DB\u70B9\u548C\u9700\u6C42\uFF0C\u518D\u505A\u5316\u914D\u63A8\u8350\u3002';action='\uD83D\uDCCB 48\u5C0F\u65F6\u5185\u4E8C\u6B21\u56DE\u8BBF\uFF0C\u53D1\u4EA7\u54C1\u8D44\u6599+\u6210\u529F\u6848\u4F8B\uFF1B'}}
else if(it==='rejected'){{talk+='\\n\\n[\u5DF2\u62D2\u7EDD/\u65E0\u6548] \u8FD9\u4E2A\u7EBF\u7D22\u6682\u65F6\u53EF\u4EE5\u653E\u4F4E\u4F18\u5148\u7EA7\uFF0C\u6216\u7B49\u4E00\u6BB5\u65F6\u95F4\u518D\u91CD\u65B0\u8054\u7CFB\u3002';action='\u263A\u6807\u8BB0\u4E3A\u201C\u5DF2\u62D2\u7EDD\u201D\uFF0C30\u5929\u540E\u518D\u56DE\u8BBF\uFF1B'}}
else{{talk+='\\n\\n[\u672A\u77E5] \u5148\u5F04\u6E05\u5BA2\u6237\u7684\u5177\u4F53\u9700\u6C42\u548C\u73B0\u6709\u75DB\u70B9\uFF0C\u518D\u505A\u5316\u914D\u3002';action='\uD83D\uDCCD 3\u5929\u5185\u5B8C\u6210\u9996\u6B21\u6709\u6548\u8054\u7CFB\uFF0C\u4E86\u89E3\u9700\u6C42\uFF1B'}}
if(c.age!=null&&c.age<=3){{action+='\u26A1 \u7EBF\u7D22\u975E\u5E38\u65B0\u9C9C\uFF0C\u4E09\u5929\u5185\u5FC5\u987B\u5F04\u6E05\u610F\u5411\uFF01';}}
if(ch&&ch.indexOf('\u5E7F\u544A')>=0){{talk+='\\n[\u6295\u6D41\u7EBF\u7D22] \u5BA2\u6237\u662F\u4ED8\u8D39\u5E7F\u544A\u83B7\u5F97\u7684\uFF0C\u610F\u8BC6\u5230\u6211\u4EEC\u54C1\u724C\u4E86\uFF0C\u8F6C\u5316\u73B0\u53EF\u80FD\u6027\u8F83\u9AD8\u3002';}}
return {{talk, action}};}

/* ===== 产品推荐引擎 ===== */
function generateProds(c){{const ind=c.ind,it=c.itl,ch=c.ch;
// 默认推荐前4个通用产品
let prods=PRODUCTS.slice(0,4);
if(ind==='\u670D\u88C5\u978B\u5E3D'||ind.indexOf('\u670D\u88C0')>=0)prods=PRODUCTS.filter(p=>['\u8FDB\u9500\u5B58\u4E13\u4E1A\u7248','\u9500\u8D27\u5B9D\u5FAE\u5546\u57CE','\u4E13\u5C5E\u54C1\u724C\u5C0F\u7A0B\u5E8F','\u6279\u91CF\u63A8\u6B3E\u5B9D','\u76F4\u64AD\u5356\u8D27'].indexOf(p.n)>=0);
if(ind.indexOf('\u7F8E\u5BB9')>=0||ind.indexOf('\u7F8E\u53D1')>=0)prods=PRODUCTS.filter(p=>['\u8FDB\u9500\u5B58\u4E13\u4E1A\u7248','\u4E13\u5C5E\u5FAE\u4FE1\u4F1A\u5458\u5361','\u9500\u8D27\u5B9D\u5FAE\u5546\u57CE','\u5FAE\u4FE1\u81EA\u52A8\u5316\u7ECF\u8425'].indexOf(p.n)>=0);
if(ind.indexOf('\u98DF\u54C1')>=0||ind.indexOf'\u751F\u9C9C'>=0)prods=PRODUCTS.filter(p=>['\u8FDB\u9500\u5B58\u4E13\u4E1A\u7248','\u751F\u610F\u901A\u4E13\u4E1A\u7248','\u4E13\u5C5E\u54C1\u724C\u5C0F\u7A0B\u5E8F','\u9650\u65F6\u6298\u6263\u4FC3\u5355\u5B9D'].indexOf(p.n)>=0);
return prods.slice(0,5);}}

/* ===== 渠道分析页 ===== */
function drawPageChannel(){{const ccnt={{}},conv={{}};DATA.forEach(c=>{{ccnt[c.ch]=(ccnt[c.ch]||0)+1;conv[c.ch]=(conv[c.ch]||{{t:0,d:0,r:0}});conv[c.ch].t++;if(c.deal)conv[c.ch].d++;}});Object.keys(conv).forEach(k=>{{conv[k].r=conv[k].t?((conv[k].d/conv[k].t)*100).toFixed(1):0;}});const cItems=Object.entries(conv).sort((a,b)=>b[1].t-a[1].t);drawBar(document.getElementById('chConvChart'),cItems.map(([k,v])=>({{l:k,t:v.t,d:v.d,r:Number(v.r)}})),{{padL:52,colors:function(i){{return Number(cItems[i][1].r)>3?'#2E7D32':Number(cItems[i][1].r)>1?'#43A047':'#FFA726';}}}});
const scnt={{}};DATA.forEach(c=>{{const s=(c.src||'\u672A\u77E5').substring(0,12);scnt[s]=(scnt[s]||0)+1;}});const sItems=Object.keys(scnt).map(k=>({{l:k,v:scnt[k]}})).sort((a,b)=>b.v-a.v).slice(0,15);drawBar(document.getElementById('srcChart'),sItems,{{padL:52,colors:'#E65100'}});
const icnt={{}};DATA.forEach(c=>{{icnt[c.itl]=(icnt[c.itl]||0)+1;}});const iItems=Object.keys(icnt).map(k=>({{l:k===''?'\u672A\u77E5':k=='high'?'\u9AD8\u610F\u5411':k=='medium'?'\u4E2D\u610F\u5411':k=='low'?'\u4F4E\u610F\u5411':'\u5DF2\u62D2\u7EDD',v:icnt[k]}}));drawBar(document.getElementById('itlChart'),iItems,{{padL:52,colors:['#C62828','#E65100','#F57F17','#9E9E9E']}});}}

/* ===== CSV导出 ===== */
function exportCSV(){{const hdr=['\u5206\u7EA7','\u8BC4\u5206','\u610F\u5411','\u884C\u4E1A','\u90E8\u95E8','\u987E\u95EE','\u6E20\u9053','\u6765\u6E90','\u5206\u914D\u65F6\u95F4','\u624B\u673A\u53F7','\u5efa\u8BAe\u52A8\u4F5C'];const rows=FILTERED.map(c=>[c.g,c.sc,c.itl,c.ind,c.dept,c.co,c.ch,c.src,c.at,c.ph,'']);const csv='\\uFEFF'+[hdr,...rows].map(r=>r.map(v=>'"'+String(v||'-').replace(/"/g,'"')+'"').join(',')).join('\\n');const blob=new Blob([csv],{{type:'text/csv;charset=utf-8'}}),url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='\u7EBF\u7D22\u6C60\u673A\u4F1A\u6E05\u5355_'+new Date().toISOString().slice(0,10)+'.csv';a.click();URL.revokeObjectURL(url);}}

/* ===== 初始化 ===== */
applyFilter();

</script>
</body>
</html>'''

with open(OUTPUT_HTML, 'w', encoding='utf-8') as f:
    f.write(html)

size_kb = os.path.getsize(OUTPUT_HTML) / 1024
size_mb = size_kb / 1024
print(f'[4/5] HTML生成完成: {OUTPUT_HTML}')
print(f'     文件大小: {size_mb:.1f} MB ({size_kb:.0f} KB)')
print(f'     数据条数: {len(export_leads)}')
print(f'     每条约: {(len(data_json)/len(export_leads)):.0f} bytes')

# 同时输出精简版JSON供参考（可选）
import shutil
print(f'[5/5] 完成! 输出文件:')
print(f'     HTML: {OUTPUT_html} ({size_mb:.1f} MB)')
