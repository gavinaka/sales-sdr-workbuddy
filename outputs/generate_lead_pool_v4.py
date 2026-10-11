#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
线索池SDR看板 v4.0 — 完全对齐服务池看板风格
=================================================
- 数据内嵌HTML (const DATA=[...])
- 浅黄主题 (复刻服务池CSS变量)
- Canvas图表 + 展开行详情 + 分页 + 主题切换
"""
import json, os, sys, io, math, re
from collections import Counter
from datetime import datetime, timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_FILE = os.path.join(SCRIPT_DIR, 'shimo_raw_data', 'all_sheets_full.json')
OUTPUT_HTML = os.path.join(SCRIPT_DIR, '线索池SDR看板.html')

NOW = datetime.now()

INDUSTRY_MAP = {
    '服装':'服装鞋帽','服饰':'服装鞋帽','女装':'服装鞋帽','男装':'服装鞋帽',
    '母婴':'母婴童玩','玩具':'母婴童玩','童装':'母婴童玩',
    '食品':'食品生鲜','零食':'食品生鲜','水果':'食品生鲜','生鲜':'食品生鲜',
    '美妆':'美容美发','化妆':'美容美发','护肤':'美容美发','美甲':'美容美发',
    '家居':'家居家纺','家具':'家居家纺','百货':'家居家纺',
    '数码':'3C数码','手机':'3C数码','电子':'3C数码',
}

print('[1/5] 解析原始数据...')
with open(RAW_FILE, 'r', encoding='utf-8') as f:
    raw = json.load(f)

raw1 = raw.get('小红书1组线索表', {}).get('data', '')
lines1 = raw1.split('\n')
HDR = [h.strip() for h in lines1[9].split('\t')]

leads = []
for line in lines1[10:]:
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

# 合并跟进表
follow_map = {}
raw2 = raw.get('线索跟进表', {}).get('data', '')
if raw2:
    for line in raw2.split('\n'):
        parts = line.split('\t')
        if len(parts) >= 15:
            fphone = (parts[1] or '').strip()
            if fphone and len(fphone) >= 6:
                follow_map[fphone] = {
                    'f1': (parts[9] or '').strip()[:200],
                    'f2': (parts[10] or '').strip()[:200],
                    'f3': (parts[11] or '').strip()[:200],
                    'f4': (parts[12] or '').strip()[:200],
                    'fl': (parts[14] or '').strip(),
                    'fs': (parts[15] or '').strip(),
                    'fa': (parts[16] or '').strip(),
                    'fc': (parts[5] or '').strip(),
                    'fdpt': (parts[7] or '').strip(),
                    'fco': (parts[8] or '').strip(),
                }

for l in leads:
    phone = l.get('手机号', '')
    if phone in follow_map:
        fm = follow_map[phone]
        l['_f1'] = fm['f1']; l['_f2'] = fm['f2']
        l['_f3'] = fm['f3']; l['_f4'] = fm['f4']
        if not l.get('线索级别'): l['线索级别'] = fm['fl']

print(f'  线索数: {len(leads)}')

def score_lead(l):
    sc = {}
    status = str(l.get('跟进状态', '')).strip()
    level = str(l.get('线索级别', '')).strip()
    has_follow = any(l.get('_f{}'.format(i)) for i in range(1, 5))
    
    hi_kw = ['有意向','高意向','意向强','要购买','考虑','对比','报价','演示']
    md_kw = ['待跟进','跟进中','沟通中','再联系','考虑中','已分配']
    rj_kw = ['不要了','不需要','拒绝','无效','空号','拉黑']
    note = (str(l.get('备注', '')) + ' ' + str(l.get('客户备注', ''))).lower()
    
    if any(k in status for k in hi_kw) or any(k in level for k in ['A','S','高']):
        sc['L1'] = 5; itl = 'high'
    elif has_follow or any(k in status for k in md_kw):
        sc['L1'] = 3; itl = 'medium'
    elif any(k in note for k in rj_kw):
        sc['L1'] = 1; itl = 'rejected'
    else:
        sc['L1'] = 2; itl = 'low'
    
    ch = str(l.get('渠道', '')).strip()
    if any(k in ch for k in ['广告','投放','信息流','付费']):
        sc['L2'] = 5
    elif any(k in ch for k in ['转介','推荐','自然','搜索','线下','社群']):
        sc['L2'] = 4
    elif ch:
        sc['L2'] = 3
    else:
        sc['L2'] = 2
    
    src = str(l.get('来源', '')).strip()
    if any(k in src for k in ['咨询','留言','电话','表单']):
        sc['L3'] = 5
    elif src:
        sc['L3'] = 2
    else:
        sc['L3'] = 1
    
    fc = sum(1 for i in range(1, 5) if l.get('_f{}'.format(i)))
    if fc >= 3: sc['L4'] = 5
    elif fc >= 2: sc['L4'] = 4
    elif fc >= 1: sc['L4'] = 3
    else: sc['L4'] = 1
    
    at = str(l.get('分配时间', '')).strip()
    age_days = None
    if at:
        try:
            ac = at.replace('.', '-').replace('/', '-')
            dt = datetime.strptime(ac[:10], '%Y-%m-%d')
            age_days = (NOW - dt).days
        except:
            pass
    
    if age_days is not None:
        if age_days <= 7: sc['L5'] = 5; gu = '一周内'
        elif age_days <= 14: sc['L5'] = 4; gu = '两周内'
        elif age_days <= 30: sc['L5'] = 3; gu = '一月内'
        elif age_days <= 90: sc['L5'] = 2; gu = '{}天'.format(age_days)
        else: sc['L5'] = 1; gu = '{}天(旧)'.format(age_days)
    else:
        sc['L5'] = 2; gu = '-'
    
    phone = str(l.get('手机号', '')).strip()
    oc = str(l.get('其他联系方式', '')).strip() or str(l.get('微信号', '')).strip()
    if phone and '*' not in phone and len(phone) >= 11:
        sc['L6'] = 5
    elif oc or (phone and len(phone) >= 6):
        sc['L6'] = 3
    else:
        sc['L6'] = 1
    
    total = sum(sc.values())
    
    opp_score = total
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
    
    deal_val = str(l.get('是否成交', '')).strip().upper()
    amt_str = str(l.get('成交金额', '')).replace(',', '').replace(' ', '')
    _deal = deal_val in ('TRUE', '是', '已成交', 'YES', '1')
    try: _amt = float(amt_str) if amt_str else 0
    except: _amt = 0
    if _amt > 0 and not _deal: _deal = True
    if _deal: grade = 'DEAL'; gl = '已成交'; gc = '#2E7D32'
    
    src_text = (str(l.get('来源', '')) + ' ' + str(l.get('备注', ''))).lower()
    ind = '未知'
    for kw, cat in INDUSTRY_MAP.items():
        if kw in src_text:
            ind = cat; break
    dept = str(l.get('分配部门', '')).strip() or '未分配'
    co = str(l.get('分配顾问', '')).strip() or str(l.get('顾问', '')).strip() or '未分配'
    scl = '未知'
    if any(k in src_text for k in ['连锁','多店','分店']): scl = '多店连锁'
    elif any(k in src_text for k in ['公司','企业','工厂']): scl = '企业级'
    elif '店' in src_text: scl = '单店'
    
    return dict(_sc=total,_scd=sc,_g=grade,_gl=gl,_gc=gc,_gu=gu,
                _itl=itl,_ind=ind,_scl=scl,_ad=at,_age_days=age_days,
                _deal=_deal,_amt=_amt,_dept=dept,_co=co,_ch=ch)

print('[2/5] 评分分级...')
for l in leads:
    s = score_lead(l)
    l.update(s)

gc = Counter(l['_g'] for l in leads)
dc = sum(1 for l in leads if l['_deal'])
ta = sum(l['_amt'] for l in leads if l['_amt'] > 0)
print('  S={} A2={} A3={} B={} C={} DEAL={}'.format(
    gc.get('S',0),gc.get('A2',0),gc.get('A3',0),gc.get('B',0),gc.get('C',0),dc))

print('[3/5] 导出精简数据...')
export_leads = []
for l in leads:
    export_leads.append(dict(
        g=l['_g'],sc=l['_sc'],gu=l['_gu'],itl=l['_itl'],
        ind=l['_ind'],dept=l['_dept'],co=l['_co'],ch=l['_ch'],
        src=(l.get('来源','') or '')[:50],at=l['_ad'],
        ph=l.get('手机号',''),oc=(l.get('其他联系方式','') or l.get('微信号','') or '')[:50],
        st=(l.get('跟进状态','') or '')[:30],lv=(l.get('线索级别','') or '')[:20],
        note=((l.get('备注','') or l.get('客户备注','') or '') or '')[:120],
        f1=l.get('_f1',''),f2=l.get('_f2',''),f3=l.get('_f3',''),f4=l.get('_f4',''),
        ag=l.get('分配人','') or '', deal=l['_deal'],amt=l['_amt'],
        age=l['_age_days'],scd=l['_scd'],scl=l['_scl']))

data_json = json.dumps(export_leads, ensure_ascii=False, separators=(',', ':'))
meta_json = json.dumps(dict(total=len(export_leads),deals=dc,amount=ta,
                              grades=dict(gc),genTime=NOW.strftime('%Y-%m-%d %H:%M:%S')),
                       ensure_ascii=False)

print('[4/5] 写入HTML文件...')

# 用模板文件方式写入，避免f-string花括号冲突
TEMPLATE_FILE = os.path.join(SCRIPT_DIR, '_lead_dashboard_v4_template.html')

# 先读取模板（如果存在），否则生成
gen_ts = NOW.strftime('%Y-%m-%d %H:%M:%S')

# 构建完整HTML内容（分块拼接）
html_parts = []

# HTML头部（静态CSS）
html_head = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>线索池SDR机会中心</title>
<style>
:root{'''
html_head += """
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
}
@media(prefers-color-scheme:dark){:root{
  --bg:#1E1810;--bg2:#261E14;--card:#2A2118;--card2:#332920;
  --text:#F5E9D6;--text2:#BFA08A;--text3:#8D6E63;
  --border:#3D2E1F;--border2:#4D3A28;
  --accent:#FFB74D;--accent2:#FFA726;--accent-soft:#3D2E1F;--accent-bg:#332920;
  --S:#5D2A2A;--A2:#5D4221;--A3:#5D5021;--B:#3D5021;--C:#2A4A2A;
}}
[data-theme="dark"]{--bg:#1E1810;--bg2:#261E14;--card:#2A2118;--card2:#332920;
  --text:#F5E9D6;--text2:#BFA08A;--border:#3D2E1F;--border2:#4D3A28;
  --accent:#FFB74D;--accent2:#FFA726;--S:#5D2A2A;--A2:#5D4221;--A3:#5D5021;--B:#3D5021;--C:#2A4A2A;}
[data-theme="dark"] .grade-tag.S{background:#E53935;color:#fff}
[data-theme="dark"] .grade-tag.A2{background:#FB8C00;color:#fff}
[data-theme="dark"] .grade-tag.A3{background:#FDD835;color:#3D2C1E}
[data-theme="dark"] .grade-tag.B{background:#7CB342;color:#fff}
[data-theme="dark"] .grade-tag.C{background:#78909C;color:#fff}
[data-theme="dark"] .intent-tag.hi{background:#E53935;color:#fff}
[data-theme="dark"] .intent-tag.md{background:#FB8C00;color:#fff}
[data-theme="dark"] .intent-tag.lo{background:#BFA08A;color:#3D2C1E}
[data-theme="light"]{--bg:#FFFBF0;--bg2:#FFF6E0;--card:#FFFFFF;--card2:#FFFEF7;
  --text:#3D2C1E;--text2:#8D6E63;--border:#F0E2C4;--border2:#E8D5A8;
  --accent:#E65100;--accent2:#F57C00;--S:#FFCDD2;--A2:#FFE0B2;--A3:#FFF3C4;--B:#E6F0C8;--C:#D7E8C5;}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%}
body{font-family:"PingFang SC","Microsoft YaHei","微软雅黑",-apple-system,sans-serif;background:var(--bg);color:var(--text);line-height:1.5;font-size:14px;-webkit-font-smoothing:antialiased}
::-webkit-scrollbar{width:8px;height:8px}::-webkit-scrollbar-thumb{background:var(--border2);border-radius:4px}
.topbar{position:sticky;top:0;z-index:100;background:linear-gradient(135deg,var(--card) 0%,var(--card2) 100%);border-bottom:1px solid var(--border);padding:0 24px;display:flex;align-items:center;gap:20px;box-shadow:var(--shadow);min-height:60px}
.topbar .brand{display:flex;align-items:center;gap:10px;padding:10px 0}
.topbar .logo{width:32px;height:32px;border-radius:8px;background:linear-gradient(135deg,var(--accent) 0%,var(--accent2) 100%);display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:16px}
.topbar .title{font-size:16px;font-weight:600;color:var(--text)}
.topbar .sub{font-size:11px;color:var(--text2);margin-top:1px}
.topbar .nav{display:flex;gap:2px;margin-left:8px}
.nav-item{padding:8px 14px;border-radius:8px;cursor:pointer;color:var(--text2);font-size:13px;font-weight:500;transition:all .15s;border:1px solid transparent}
.nav-item:hover{color:var(--accent);background:var(--accent-soft)}
.nav-item.active{color:var(--accent);background:var(--accent-soft);border-color:var(--border2);font-weight:600}
.nav-item .badge{display:inline-block;margin-left:4px;padding:1px 6px;border-radius:8px;background:var(--accent);color:#fff;font-size:10px;font-weight:600}
.topbar .spacer{flex:1}
.iconbtn{width:34px;height:34px;border-radius:8px;border:1px solid var(--border);background:var(--card);color:var(--text2);cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:14px;transition:all .15s}
.iconbtn:hover{border-color:var(--accent);color:var(--accent)}
.page{display:none;padding:22px 24px 48px;max-width:1480px;margin:0 auto}
.page.active{display:block;animation:fade .2s ease}
@keyframes fade{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:translateY(0)}}
.kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin-bottom:20px}
.kpi{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:16px 18px;box-shadow:var(--shadow);transition:transform .15s}
.kpi:hover{transform:translateY(-1px);box-shadow:var(--shadow-h)}
.kpi .lbl{font-size:11px;color:var(--text2);letter-spacing:.3px;font-weight:600;text-transform:uppercase}
.kpi .val{font-size:26px;font-weight:700;margin-top:6px;line-height:1.1}
.kpi-mini{font-size:10px;color:var(--text2);margin-top:6px;display:flex;gap:8px}
.kpi-mini span b{color:var(--text);font-weight:600}
.kpi.grade.S{border-left-color:#E53935;background:linear-gradient(135deg,var(--S) 0%,var(--card) 50%)}
.kpi.grade.A2{border-left-color:var(--accent2);background:linear-gradient(135deg,var(--A2) 0%,var(--card) 50%)}
.kpi.grade.A3{border-left-color:var(--warn);background:linear-gradient(135deg,var(--A3) 0%,var(--card) 50%)}
.kpi.grade.B{border-left-color:#7CB342;background:linear-gradient(135deg,var(--B) 0%,var(--card) 50%)}
.kpi.grade.C{border-left-color:#558B2F;background:linear-gradient(135deg,var(--C) 0%,var(--card) 50%)}
.charts-row{display:grid;grid-template-columns:1.1fr 1fr 1fr;gap:16px;margin-bottom:8px}
.chart-card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:18px;box-shadow:var(--shadow)}
.chart-card h3{font-size:13px;font-weight:600;color:var(--text);margin-bottom:4}
.chart-card .sub{font-size:11px;color:var(--text2);margin-bottom:12px}
.chart-card canvas{width:100%;display:block}
.filters{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:14px 16px;margin-bottom:14px;display:flex;flex-wrap:wrap;gap:12px;align-items:center;box-shadow:var(--shadow)}
.fgroup{display:flex;align-items:center;gap:6px}
.filters label{font-size:11px;color:var(--text2);font-weight:600;letter-spacing:.2px}
.filters select,.filters input{padding:7px 12px;border:1px solid var(--border);border-radius:8px;background:var(--card2);color:var(--text);font-size:13px;font-family:inherit}
.filters input{flex:1;min-width:180px}
.filters .stat{margin-left:auto;font-size:12px;color:var(--text2);font-weight:500}
.grade-chips{display:flex;gap:5px;flex-wrap:wrap}
.chip{padding:4px 12px;border-radius:14px;font-size:12px;cursor:pointer;border:1px solid var(--border);background:var(--card);color:var(--text2);user-select:none;font-weight:500;transition:all .12s}
.chip:hover{border-color:var(--accent2);color:var(--accent)}
.chip.active{background:var(--accent);color:#fff;border-color:var(--accent)}
.table-wrap{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);overflow-x:auto;box-shadow:var(--shadow)}
table{width:auto;min-width:100%;border-collapse:collapse;font-size:13px;table-layout:fixed}
thead th{background:var(--accent-bg);padding:11px 12px;text-align:left;font-weight:600;position:sticky;top:0;white-space:nowrap;border-bottom:1px solid var(--border2);font-size:12px;cursor:pointer}
thead th:hover{filter:brightness(.96)}
tbody td{padding:10px 12px;border-bottom:1px solid var(--border);vertical-align:middle;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
tbody tr:last-child td{border-bottom:none}
tbody tr{cursor:pointer;transition:background .1s}
tbody tr:hover{background:var(--accent-soft)}
.grade-tag{display:inline-block;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:700;white-space:nowrap}
.grade-tag.S{background:var(--S);color:var(--S-t)}.grade-tag.A2{background:var(--A2);color:var(--A2-t)}
.grade-tag.A3{background:var(--A3);color:var(--A3-t)}.grade-tag.B{background:var(--B);color:var(--B-t)}.grade-tag.C{background:var(--C);color:var(--C-t)}
.grade-tag.DEAL{background:#C8E6C9;color:#1B5E20}
.intent-tag{display:inline-flex;align-items:center;gap:4px;padding:3px 9px;border-radius:6px;font-size:11px;font-weight:600}
.intent-tag.hi{background:#ffebee;color:#c62828}.intent-tag.md{background:#fff3e0;color:#e65100}.intent-tag.lo{background:#f5f5f5;color:#888}.intent-tag.rj{background:#efeef0;color:#999}
.ph{font-family:"SF Mono",SFMono-Regular,Consolas,monospace;font-weight:700;letter-spacing:.3px}
.pager{display:flex;justify-content:center;align-items:center;gap:6px;padding:16px;flex-wrap:wrap}
.pager button{padding:7px 14px;border:1px solid var(--border);border-radius:8px;background:var(--card);color:var(--text);cursor:pointer;font-size:13px;font-family:inherit}
.pager button:hover:not(:disabled){border-color:var(--accent);color:var(--accent)}
.pager button:disabled{opacity:.4}
.pager .info{font-size:12px;color:var(--text2);margin:0 8px}
.detail-row td{background:var(--bg2);padding:0;border-bottom:1px solid var(--border)}
.detail-box{padding:18px 20px;display:grid;grid-template-columns:1fr 1fr 1fr;gap:18px}
.block h4{font-size:12px;color:var(--accent);margin-bottom:8px;font-weight:700;letter-spacing:.3px}
.block ul{list-style:none;padding-left:0}
.block li{font-size:12px;padding:4px 0;color:var(--text);position:relative;padding-left:14px;line-height:1.5}
.block li:before{content:'';position:absolute;left:4px;top:11px;width:4px;height:4px;border-radius:50%;background:var(--accent2)}
.tt{font-size:12.5px;color:var(--text);line-height:1.65;padding:8px 12px;background:var(--card);border-radius:8px;border:1px solid var(--border)}
.score-bar{display:inline-flex;gap:2px}
.sc-cell{display:inline-block;width:18px;height:18px;border-radius:4px;background:var(--bg2);text-align:center;line-height:18px;font-size:10px;font-weight:700;color:var(--text2)}
.s5{background:#558B2F;color:#fff}.s4{background:#9CCC65;color:#fff}.s3{background:#F0C419;color:#3D2C1E}.s2{background:#FFB74D;color:#fff}.s1{background:#E57373;color:#fff}
.talk-box{background:linear-gradient(135deg,#fff8e1,#fff3cd);border:1px solid #ffc107;border-radius:8px;padding:14px;margin:12px 0}
.action-box{background:linear-gradient(135deg,#e3f2fd,#bbdefb);border-left:3px solid var(--accent);border-radius:0 8px 8px 0;padding:12px 16px;margin:12px 0}
.prod-list{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0}
.pcard{background:linear-gradient(135deg,#e8f0fe,#f0f4fc);border-left:3px solid var(--accent);border-radius:6px;padding:6px 10px;min-width:160px}
.pcard .pn{font-weight:700;color:var(--accent);font-size:12px}
.pcard .pd{font-size:11px;color:var(--text2);margin-top:2px}
.foot{text-align:center;color:var(--text3);font-size:11px;padding:18px 0;border-top:1px solid var(--border);margin-top:24px}
.counselor-bar{display:flex;align-items:center;gap:10px;cursor:pointer;padding:6px 8px;border-radius:8px;transition:background .12s}
.counselor-bar:hover{background:var(--accent-soft)}
</style>"""

html_body_start = '''</head><body>
<div class="topbar"><div class="brand"><div class="logo">SDR</div><div><div class="title">线索池SDR机会中心</div><div class="sub" id="subInfo">投流线索 · 智能分级 · 产品推荐</div></div></div>
<div class="nav"><div class="nav-item active" data-page="overview">总览</div><div class="nav-item" data-page="list">机会列表<span class="badge" id="listBadge">0</span></div><div class="nav-item" data-page="channel">渠道效果</div></div><div class="spacer"></div><button class="iconbtn" id="themeBtn" title="切换主题">🌙</button></div>

<div id="page-overview" class="page active"><div class="kpi-grid" id="kpiGrid"></div><div class="charts-row"><div class="chart-card"><h3>分级分布</h3><div class="sub">S/A2/A3/B/C 五档线索占比</div><canvas id="pieChart" height="260"></canvas></div><div class="chart-card"><h3>渠道TOP10</h3><div class="sub">按线索数量排序</div><canvas id="chChart" height="260"></canvas></div><div class="chart-card"><h3>部门分布</h3><div class="sub">按分配部门统计</div><canvas id="deptChart" height="260"></canvas></div></div><div class="chart-card" style="margin-top:16px"><h3>顾问线索分布</h3><div class="sub">点击筛选该顾问的线索</div><div id="counselorBars"></div></div></div>

<div id="page-list" class="page"><div class="filters"><div class="fgroup"><label>分级</label><div class="grade-chips" id="gradeChips"><span class="chip active" data-grade="">全部</span><span class="chip" data-grade="S" style="background:var(--S);color:var(--S-t)">S</span><span class="chip" data-grade="A2" style="background:var(--A2);color:var(--A2-t)">A2</span><span class="chip" data-grade="A3" style="background:var(--A3);color:var(--A3-t)">A3</span><span class="chip" data-grade="B" style="background:var(--B);color:var(--B-t)">B</span><span class="chip" data-grade="C" style="background:var(--C);color:var(--C-t)">C</span></div></div><div class="fgroup"><label>意向</label><select id="fltItl"><option value="">全部</option><option value="high">高意向</option><option value="medium">中意向</option><option value="low">低意向</option><option value="rejected">已拒绝</option></select></div><div class="fgroup"><label>部门</label><select id="fltDept"><option value="">全部</option></select></div><div class="fgroup"><label>渠道</label><select id="fltCh"><option value="">全部</option></select></div><div class="fgroup"><label>顾问</label><select id="fltCo"><option value="">全部</option></select></div><div class="fgroup"><label>成交</label><select id="fltDeal"><option value="f" selected>未成交</option><option value="t">已成交</option><option value="">全部</option></select></div><input id="search" placeholder="🔍 手机号/备注/来源..." style="max-width:220px"><div class="fgroup">📅<input type=date id="fltDateFrom">至<input type=date id="fltDateTo"></div><div class="stat" id="filterStat"></div></div><div class="table-wrap"><table><thead><tr id="theadRow"></tr></thead><tbody id="tbody"></tbody></table></div><div class="pager" id="pager"></div></div>

<div id="page-channel" class="page"><div class="chart-card"><h3>渠道效果分析</h3><div class="sub">各渠道线索量 × 成交转化率</div><canvas id="chConvChart" height="360"></canvas></div><div class="charts-row" style="margin-top:16px"><div class="chart-card"><h3>来源TOP15</h3><canvas id="srcChart" height="280"></canvas></div><div class="chart-card"><h3>意向分布</h3><canvas id="itlChart" height="280"></canvas></div></div></div>

<div class="foot">线索池SDR机会中心 v4.0 · 数据源:石摩「销售部线索跟进6.30 787」 · ''' + gen_ts + '''</div>'''

# JS代码从独立文件读取
js_file = os.path.join(SCRIPT_DIR, '_lead_dashboard_v4.js')
if os.path.exists(js_file):
    with open(js_file, 'r', encoding='utf-8') as f:
        js_content = f.read()
else:
    print('  ERROR: 找不到JS模板文件: {}'.format(js_file))
    sys.exit(1)

html_end = '\n</body>\n</html>'

# 拼接完整HTML并写入
with open(OUTPUT_HTML, 'w', encoding='utf-8') as f:
    f.write(html_head)
    f.write(html_body_start)
    f.write('<script>\nconst DATA=')
    f.write(data_json)
    f.write(';\nconst META=')
    f.write(meta_json)
    f.write(';\n')
    f.write(js_content)
    f.write('</script>')
    f.write(html_end)

size_kb = os.path.getsize(OUTPUT_HTML) / 1024
size_mb = size_kb / 1024
print('[5/5] 完成!'.format(size_mb=size_mb))
print('  文件: {}'.format(OUTPUT_HTML))
print('  大小: {:.1f} MB ({:.0f} KB)'.format(size_mb, size_kb))
print('  数据: {} 条'.format(len(export_leads)))
