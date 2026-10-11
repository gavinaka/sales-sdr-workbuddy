#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""线索池交互看板生成器 v1.0 - 数据源:石摩销售部线索跟进6.30 787"""
import json, os, re, sys, io
from collections import Counter
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_FILE = os.path.join(SCRIPT_DIR, 'shimo_raw_data', 'all_sheets_full.json')
OUTPUT_HTML = os.path.join(SCRIPT_DIR, '线索池SDR交互看板.html')

print('Loading data...')
with open(RAW_FILE, 'r', encoding='utf-8') as f:
    RAW = json.load(f)

def pd(s):
    if not s or not str(s).strip(): return ''
    s = str(s).strip()
    m = re.match(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', s)
    if m: return f'{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}'
    m = re.match(r'(\d{1,2})[月./\-](\d{1,2})', s)
    if m: return f'{datetime.now().year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}'
    return s

# ===== Parse 小红书1组线索表 =====
print('Parsing xiaohongshu table...')
raw1 = RAW.get('小红书1组线索表',{}).get('data','')
lines1 = raw1.split('\n')
HDR = [h.strip() for h in lines1[9].split('\t')]
LMAP = {}
for ln in lines1[10:]:
    p = ln.split('\t')
    if len(p) < len(HDR): continue
    r = {HDR[i]: (p[i].strip() if i<len(p) else '') for i in range(len(HDR))}
    ph = r.get('手机号','').strip()
    if len(ph) < 8: continue
    ds = str(r.get('是否成交','')).strip().upper()
    r['_deal'] = ds == 'TRUE'
    am = r.get('成交金额','').replace(',',' ').replace(' ','')
    try: r['_amt'] = float(am)
    except: r['_amt'] = 0
    r['_src'] = 'XHS'
    r['_ad'] = pd(r.get('分配时间',''))
    r['_dd'] = pd(r.get('成交时间',''))
    LMAP[ph] = r
print(f'  XHS: {len(LMAP)} leads')

# ===== Parse 线索跟进表 =====
print('Parsing follow-up table...')
raw2 = RAW.get('线索跟进表',{}).get('data','')
added = 0
if raw2:
    l2 = raw2.split('\n')
    tc = Counter(x.count('\t') for x in l2)
    dtc = tc.most_common(1)[0][0]
    for ln in l2:
        if ln.count('\t') != dtc: continue
        p = ln.split('\t')
        ph = p[1].strip() if len(p)>1 else ''
        if len(ph)<8 or ph in LMAP: continue
        r2 = {'手机号':ph,'昵称':p[0].strip() if p else'',
              '创建时间':p[2].strip() if len(p)>2 else '',
              '渠道':p[6].strip() if len(p)>6 else '',
              '分部':p[8].strip() if len(p)>8 else '',
              '顾问':p[9].strip() if len(p)>9 else '',
              '_src':'FU','_deal':False,'_amt':0}
        LMAP[ph] = r2; added += 1
print(f'  FU added: {added}')

LEADS = list(LMAP.values())
TOTAL = len(LEADS)
DCNT = sum(1 for l in LEADS if l.get('_deal'))
DRATE = round(DCNT/TOTAL*100,1) if TOTAL else 0
AMTS = [l['_amt'] for l in LEADS if l.get('_amt',0)>0]
TAMT = sum(AMTS)
AAMT = round(TAMT/len(AMTS)) if AMTS else 0

by_s = Counter(l.get('跟进状态','?') or '?' for l in LEADS)
by_d = Counter(l.get('分配部门','未分配') for l in LEADS)
by_c = Counter(l.get('渠道','?') for l in LEADS)
by_l = Counter(l.get('线索级别','') for l in LEADS)
by_co = Counter(l.get('分配顾问','') for l in LEADS)
by_sr = Counter(l.get('来源','') for l in LEADS)

ch_conv = {}
for ch,cn in by_c.items():
    d=sum(1 for l in LEADS if l.get('渠道','')==ch and l.get('_deal'))
    ch_conv[ch]={'t':cn,'d':d,'r':round(d/cn*100,1) if cn else 0}

dp_conv = {}
for dp,dn in by_d.items():
    d=sum(1 for l in LEADS if l.get('分配部门','')==dp and l.get('_deal'))
    dp_conv[dp]={'t':dn,'d':d,'r':round(d/dn*100,1) if dn else 0}

SUMM = {'total':TOTAL,'deals':DCNT,'rate':DRATE,'amount':TAMT,'avg_amt':AAMT,
        'channels':dict(by_c),'depts':dict(by_d),'status':dict(by_s),
        'levels':dict(by_l), 'sources':dict(by_sr.most_common(30)),
        'counselors':dict(by_co.most_common(25)), 'ch_conv':ch_conv, 'dp_conv':dp_conv}

JL = json.dumps(LEADS, ensure_ascii=False, default=str)
JS = json.dumps(SUMM, ensure_ascii=False)

NOW = datetime.now().strftime('%Y-%m-%d %H:%M')

print(f'Total:{TOTAL} Deals:{DCNT}({DRATE}%) Amount:{TAMT:,}')

HTML = '''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>线索池SDR看板</title>
<style>
:root{--bg:#faf8f3;--cb:#fff;--pr:#c8a96e;--pd:#a88b55;--tx:#333;--tl:#777;--bd:#e8e0d0;--rd:#d45d5d;--gn:#5da86e;--bl:#5b8fd4;--sh:0 2px 12px rgba(0,0,0,.06);--rad:10px}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"Microsoft YaHei","PingFang SC",sans-serif;background:var(--bg);color:var(--tx);font-size:14px;line-height:1.6;padding:20px}
.hd{text-align:center;padding:24px 0 16px;border-bottom:2px solid var(--bd);margin-bottom:20px}
.hd h1{font-size:26px;color:var(--pd);letter-spacing:2px;font-weight:700}
.hd .sub{color:var(--tl);font-size:13px;margin-top:4px}
.cr{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin-bottom:20px}
.cd{background:var(--cb);border-radius:var(--rad);box-shadow:var(--sh);padding:18px 20px;border-left:4px solid var(--pr);transition:transform .2s}
.cd:hover{transform:translateY(-2px)}
.cd .lb{color:var(--tl);font-size:13px;margin-bottom:6px}
.cd .vl{font-size:28px;font-weight:700;color:var(--pd)}
.cd .sb{font-size:12px;color:var(--tl);margin-top:4px}
.cd.d .vl{color:var(--gn)}.cd.r .vl{color:var(--bl)}.cd.a .vl{color:var(--rd)}
.fb{background:var(--cb);border-radius:var(--rad);box-shadow:var(--sh);padding:14px 20px;margin-bottom:16px;display:flex;flex-wrap:wrap;gap:10px;align-items:center}
.fb label{font-size:13px;color:var(--tl);white-space:nowrap}
.fb select,.fb input{border:1px solid var(--bd);border-radius:6px;padding:7px 10px;font-size:13px;background:#fff;outline:none;font-family:inherit}
.fb button{background:var(--pr);color:#fff;border:none;border-radius:6px;padding:7px 18px;cursor:pointer;font-size:13px;font-weight:600}.fb button:hover{background:var(--pd)}
.ts{display:flex;gap:4px;margin-bottom:16px;flex-wrap:wrap}
.tb{padding:8px 18px;border:1px solid var(--bd);background:var(--cb);border-radius:8px 8px 0 0;cursor:pointer;font-size:13px;font-weight:600;color:var(--tl);transition:.2s}
.tb.on{background:var(--pr);color:#fff;border-color:var(--pr)}
.tb:hover:not(.on){background:#f5f0e0;color:var(--tx)}.pn{display:none}.pn.on{display:block}
.tw{background:var(--cb);border-radius:var(--rad);box-shadow:var(--sh);overflow:hidden}
table.dt{width:100%;border-collapse:collapse;font-size:13px}
.dt th{position:sticky;top:0;z-index:10;background:#f5f0e0;color:var(--pd);font-weight:700;padding:11px 10px;text-align:left;white-space:nowrap;cursor:pointer;font-size:12px;border-bottom:2px solid var(--bd)}
.dt th:hover{background:#ede5cc}
.dt td{padding:9px 10px;border-bottom:1px solid #f0ece0;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;vertical-align:middle}
.dt tr:hover td{background:#fdfaf3}
.tg-d{background:#e8f5e9;color:#2e7d32;padding:2px 8px;border-radius:4px;font-size:12px;font-weight:600}
.tg-n{background:#fce4ec;color:#c62828;padding:2px 8px;border-radius:4px;font-size:12px}
.tg-s{background:#e3f2fd;color:#1565c0;padding:2px 8px;border-radius:4px;font-size:12px;font-weight:700}
.tg-a{background:#fff3e0;color:#e65100;padding:2px 8px;border-radius:4px;font-size:12px;font-weight:600}
.ph{font-family:monospace;font-weight:600;color:var(--pd)}
.ag{display:grid;grid-template-columns:repeat(auto-fit,minmax(380px,1fr));gap:16px}
.cc{background:var(--cb);border-radius:var(--rad);box-shadow:var(--sh);padding:18px}
.cc h3{font-size:15px;color:var(--pd);margin-bottom:14px;padding-bottom:8px;border-bottom:1px solid var(--bd)}
.br{display:flex;align-items:center;margin-bottom:8px;font-size:13px}
.bl{width:90px;flex-shrink:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px}
.bt{flex:1;height:22px;background:#f0ebe0;border-radius:4px;overflow:hidden;margin:0 8px}
.bf{height:100%;background:linear-gradient(90deg,var(--pr),var(--pd));border-radius:4px;display:flex;align-items:center;justify-content:flex-end;padding-right:6px}
.bf.g{background:linear-gradient(90deg,#81c784,#43a047)}
.bf.b{background:linear-gradient(90deg,#64b5f6,#1976d2)}
.bv{font-size:12px;color:#fff;font-weight:600;white-space:nowrap}
.bp{width:42px;text-align:right;font-size:12px;color:var(--tl);font-weight:600}
.mo{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.4);z-index:999;justify-content:center;align-items:center}
.mo.sh{display:flex}
.mb{background:#fff;border-radius:12px;width:640px;max-height:80vh;overflow-y:auto;padding:24px;box-shadow:0 8px 40px rgba(0,0,0,.15);position:relative}
.mb h2{color:var(--pd);margin-bottom:16px;font-size:18px;border-bottom:2px solid var(--bd);padding-bottom:10px}
.dg{display:grid;grid-template-columns:auto 1fr;gap:8px 16px;font-size:13px}
.dl{color:var(--tl);font-weight:600}.dv{word-break:break-all}
.fr{background:#faf8f3;border-left:3px solid var(--pr);padding:10px 14px;margin-top:8px;border-radius:0 6px 6px 0;font-size:13px;line-height:1.7}
.cm{position:absolute;top:12px;right:16px;font-size:28px;cursor:pointer;color:#bbb;background:none;border:none;font-family:inherit}.cm:hover{color:var(--tx)}
.ft{text-align:center;color:var(--tl);font-size:12px;padding:16px 0;margin-top:20px}
@media(max-width:768px){.cr{grid-template-columns:repeat(2,1fr)}.ag{grid-template-columns:1fr}}
</style></head><body>
<div class="hd"><h1>🎯 线索池 SDR 跟进看板</h1><div class="sub">投流线索·回访记录·成交追踪 | 数据源:石摩「销售部线索跟进6.30 787」</div></div>
<div class="cr" id="cards"></div>
<div class="fb" id="fb"></div>
<div class="ts">
<button class="tb on" onclick="sw(\'t\',this)">📋 列表</button>
<button class="tb" onclick="sw(\'c\',this)">📊 渠道</button>
<button class="tb" onclick="sw(\'d\',this)">🏢 部门</button>
</div>
<div class="pn on" id="pt"><div class="tw"><table class="dt" id="tbl"><thead><tr id="th"></tr></thead><tbody id="tb"></tbody></table></div><div id="ti" style="padding:12px;text-align:center;color:var(--tl);font-size:13px"></div></div>
<div class="pn" id="pc"><div class="ag" id="ca"></div></div>
<div class="pn" id="pd"><div class="ag" id="da"></div></div>
<div class="mo" id="mo" onclick="if(event.target===this)this.classList.remove('sh')"><div class="mb" id="mb"></div></div>
<div class="ft">线索池SDR看板 v1.0 · '''+NOW+''' · 共'''+str(TOTAL)+'''条</div>
<script>
const AL='''+JL+''';const SM='''+JS+''';
let FL=[...AL],sc='',so=1;
const ft={kw:'',st:'',dp:'',ch:'',lv:'',dl:'',df:'',dt:'',co:''};

function eh(s){if(!s)return '';return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
function rc(){
const n=FL.length,d=FL.filter(x=>x._deal).length,r=n?(d/n*100).toFixed(1):0,a=FL.reduce((s,x)=>s+(x._amt||0),0);
document.getElementById('cards').innerHTML=`
<div class="cd"><div class="lb">筛选后线索</div><div class="vl">${n.toLocaleString()}</div><div class="sb">共${AL.length.toLocaleString()}条</div></div>
<div class="cd d"><div class="lb">已成交</div><div class="vl">${d}</div><div class="sb">${r}%转化</div></div>
<div class="cd r"><div class="lb">成交率</div><div class="vl">${r}%</div><div class="sb">目标5%+</div></div>
<div class="cd a"><div class="lb">成交金额</div><div class="vl">¥${a.toLocaleString()}</div><div class="sb">均价¥${d?Math.round(a/d):0}</div></div>`;}
function rf(){
const el=document.getElementById('fb');
const st=[...new Set(AL.map(x=>x['跟进状态']||'').filter(v=>v))],
dp=Object.keys(SM.depts||{}),
ch=Object.keys(SM.channels||{}),
lv=Object.keys(SM.levels||{}).filter(v=>v),
co=Object.keys(SM.counselors||{}).filter(v=>v);
el.innerHTML=`<label>🔍关键词</label><input type=text id=fk placeholder="手机号/备注..." style="width:160px;padding:7px10px;border:1px solid var(--bd);border-radius:6px;font-size:13px"oninput=af()>
<label>状态</label><select id=fs onchange=af()><option value="">全部</option>${st.map(s=>`<option>${eh(s)}</option>`).join('')}</select>
<label>部门</label><select id=fdp onchange=af()><option value="">全部</option>${dp.map(d=>`<option>${eh(d)}</option>`).join('')}</select>
<label>渠道</label><select id=fch onchange=af()><option value="">全部</option>${ch.map(c=>`<option>${eh(c)} (${SM.channels[c]||0})</option>`).join('')}</select>
<label>级别</label><select id=flv onchange=af()><option value="">全部</option>${lv.map(l=>`<option>${eh(l)}</option>`).join('')}</select>
<label>成交</label><select id=fdl onchange=af()><option value="">全部</option><option value=t>已成交</option><option value=f>未成交</option></select>
<label>顾问</label><select id=fco onchange=af()><option value="">全部</option>${co.map(c=>`<option>${eh(c)}</option>`).join('')}</select>
<label>📅起始</label><input type=date id=ffd onchange=af()><label>至</label><input type=date id=ftd onchange=af()>
<button onclick=rst()>重置</button><button onclick=ex()>导出CSV</button>`;}
function af(){
ft.kw=(document.getElementById('fk')?.value||'').toLowerCase();
ft.st=document.getElementById('fs')?.value||'';
ft.dp=document.getElementById('fdp')?.value||'';
ft.ch=document.getElementById('fch')?.value||'';
ft.lv=document.getElementById('flv')?.value||'';
ft.dl=document.getElementById('fdl')?.value||'';
ft.co=document.getElementById('fco')?.value||'';
ft.df=document.getElementById('ffd')?.value||'';
ft.dt=document.getElementById('ftd')?.value||'';
FL=AL.filter(l=>{
if(ft.kw){
const s=[l['手机号'],l['其他联系方式'],l['备注'],l['分配人'],l['分配顾问'],l['来源'],
l['跟进情况（第一次）'],l['跟进情况（第二次）']].map(v=>(v||'').toLowerCase()).join('');
if(!s.includes(ft.kw)&&!(l['手机号']||'').includes(ft.kw))return false}
if(ft.st&&(l['跟进状态']||'')!==ft.st)return false;
if(ft.dp&&(l['分配部门']||'')!==ft.dp)return false;
if(ft.ch&&(l['渠道']||'')!==ft.ch)return false;
if(ft.lv&&(l['线索级别']||'')!==ft.lv)return false;
if(ft.dl==='t'&&l._deal!==true)return false;
if(ft.dl==='f'&&l._deal!==false)return false;
if(ft.co&&(l['分配顾问']||'')!==ft.co)return false;
if(ft.df||ft.dt){
const ds=l._ad||l['分配时间']||'',dv=ds.replace(/\./g,'-');
if(dv&&dv.length>=10){if(ft.df&&dv<ft.df)return false;if(ft.dt&&dv>ft.dt)return false}}
return true});
rc();rt();}
function rst(){document.getElementById('fk').value='';document.getElementById('fs').value='';
document.getElementById('fdp').value='';document.getElementById('fch').value='';
document.getElementById('flv').value='';document.getElementById('fdl').value='';
document.getElementById('fco').value='';document.getElementById('ffd').value='';
document.getElementById('ftd').value='';af();}
const TC=[{k:'跟进状态',l:'状态',w:70},{k:'分配部门',l:'部门',w:80},{k:'分配顾问',l:'顾问',w:65},{k:'渠道',l:'渠道',w:95},
{k:'来源',l:'来源',w:110},{k:'分配时间',l:'时间',w:70},{k:'手机号',l:'手机号',w:115},{k:'是否成交',l:'成交',w:50},
{k:'成交金额',l:'金额',w:65},{k:'线索级别',l:'级别',w:55},{k:'分配人',l:'登记人',w:58}];
function rt(){
document.getElementById('th').innerHTML=TC.map(c=>`<th style="width:${c.w}px"onclick="sb('${c.k}')">${c.l}${sc===c.k?' '+(so===1?'▲':'▼'):''}</th>`).join('')+'<th>操作</th>';
document.getElementById('tb').innerHTML=FL.slice(0,500).map(l=>{
const dt=l._deal===true?'<span class="tg-d">已成交</span>':l._deal===false?'<span class="tg-n">未成交</span>':'';
const lv=l['线索级别']||'';
const lt=lv.includes('S')?'<span class="tg-s">S</span>':lv.includes('A')?'<span class="tg-a">A</span>':lv.includes('B')?'<span style="background:#f5f5f5;color:#757575;padding:2px8px;border-radius:4px;font-size:12px">B</span>':'';
return`<tr onclick="sd(${AL.indexOf(l)})"style="cursor:pointer"title="点击查看详情">
<td>${eh(l['跟进状态']||'-')}</td><td>${eh(l['分配部门']||'-')}</td><td>${eh(l['分配顾问']||'-')}</td>
<td>${eh(l['渠道']||'-')}</td><td title="${eh(l['来源']||'')}">${eh((l['来源']||'').substring(0,12)||'-')}</td>
<td>${eh(l['分配时间']||'-')}</td><td class="ph">${eh(l['手机号']||'-')}</td><td>${dt}</td>
<td>${l._deal===true?('¥'+(l._amt||0)):'-'}</td><td>${lt}</td><td>${eh(l['分配人']||'-')}</td>
<td><button onclick="event.stopPropagation();cp('${l['手机号']}')"style="padding:2px8px;font-size:11px;border:1px solid var(--bd);background:#fff;border-radius:4px;cursor:pointer">复制</button></td></tr>`}).join('');
document.getElementById('ti').textContent=`显示 ${Math.min(FL.length,500)} / ${FL.length} 条${FL.length>500?' (前500)':''}`;}
function sb(k){
if(sc===k){so*=-1}else{sc=k;so=1}
FL.sort((a,b)=>{
let v=a[k]||'',vv=b[k]|| '';
if(k==='成交金额'){v=parseFloat(v.replace(/[¥,]/g,''))||0;vv=parseFloat(vv.replace(/[¥,]/g,''))||0;return(v-vv)*so}
v=String(v).toLowerCase();vv=String(vv).toLowerCase();
return v<vv?-1*so:v>vv?1*so});rt()}
function sw(t,el){document.querySelectorAll('.tb').forEach(b=>b.classList.remove('on'));
document.querySelectorAll('.pn').forEach(p=>p.classList.remove('on'));
el.classList.add('on');document.getElementById('p'+t)?.classList.add('on');
if(t==='c')renderCA();if(t==='d')renderDA()}
function renderCA(){const el=document.getElementById('ca'),cv=SM.ch_conv||{};
const items=Object.entries(cv).sort((a,b)=>b[1].t-a[1].t),ttl=SM.total||1;
el.innerHTML=`<div class="cc"style="grid-column:1/-1"><h3>📡 渠道分布 & 成交转化</h3>
${items.map(([k,v])=>`<div class="br"><div class="bl"title="${eh(k)}">${eh(k.substring(0,10))}</div>
<div class="bt"><div class="bf b"style="width:${v.t/ttl*100}%"><span class="bv">${v.t}</span></div></div><div class="bp">${v.r}%(${v.d}单)</div></div>`).join('')}</div>`}
function renderDA(){const el=document.getElementById('da'),dv=SM.dp_conv||{};
const items=Object.entries(dv).sort((a,b)=>b[1].d-a[1].d),mx=Math.max(...items.map(x=>x[1].t));
el.innerHTML=`<div class="cc"style="grid-column:1/-1"><h3>🏢 部门线索 & 成交排行</h3>
${items.slice(0,25).map(([k,v])=>`<div class="br"><div class="bl"style="width:85px"title="${eh(k)}">${eh(k.substring(0,8))}</div>
<div class="bt"><div class="bf g"style="width:${v.t/mx*100}%"><span class="bv">${v.t}条/${v.d}成</span></div></div><div class="bp">${v.r}%</div></div>`).join('')}</div>`}
function sd(i){const l=AL[i];
const mo=document.getElementById('mo'),mb=document.getElementById('mb');
const flds=[['跟进状态',l['跟进状态']],['分配时间',l['分配时间']],['分配人',l['分配人']],
['是否成交',l['是否成交']],['成交时间',l['成交时间']],['成交金额',l['成交金额']],
['手机号',l['手机号']],['其他联系方式',l['其他联系方式']],['线索级别',l['线索级别']],
['备注',l['备注']],['渠道',l['渠道']],['来源',l['来源']],
['分配部门',l['分配部门']],['分配顾问',l['分配顾问']],['数据源',l['_src]]];
let frs='';
for(let n=1;n<=4;n++){const fk=`跟进情况（第${'一二三四'[n-1]}次）`;if(l[fk])frs+=`<div class="fr"><strong>第${n}次:</strong>${eh(l[fk])}</div>`}
for(let n=1;n<=5&&!frs;n++)if(l[`跟${n}`])frs+=`<div class="fr"><strong>第${n}次:</strong>${eh(l[`跟${n}`])}</div>`;
mb.innerHTML=`<button class="cm" onclick="document.getElementById('mo').classList.remove('sh')">&times;</button>
<h2>📞 线索详情 - ${eh(l['手机号'])}</h2><div class="dg">${flds.map(([k,v])=>`<div class="dl">${k}</div><div class="dv">${v||'-'}</div>`).join('')}</div>
${frs?`<h3 style="margin-top:18px;color:var(--pd);font-size:15px">📝 跟进记录</h3>${frs}`:''}
<div style="margin-top:16px;display:flex;gap:8px"><button onclick="cp('${l['手机号']}')"style="padding:8px16px;background:var(--pr);color:#fff;border:none;border-radius:6px;cursor:pointer">复制手机号</button></div>`;
mo.classList.add('sh')}
function cp(p){navigator.clipboard.writeText(p||'').then(()=>alert('已复制:'+p))}
function ex(){
const hdr=TC.map(c=>c.label);
const rows=FL.map(l=>TC.map(c=>{let v=l[c.k]||'';if(c.k==='是否成交')v=l._deal?'已成交':'未成交';return'"'+String(v).replace(/"/g,'""')+'"'}));
const csv='\uFEFF'+[hdr,...rows].map(r=>r.join(',')).join('\\n');
const blob=new Blob([csv],{type:'text/csv;charset=utf-8'}),url=URL.createObjectURL(blob);
const a=document.createElement('a');a.href=url;a.download='线索池筛选.csv';a.click();URL.revokeObjectURL(url)}
rc();rf();rt();
</script></body></html>'''

with open(OUTPUT_HTML,'w',encoding='utf-8') as f:
    f.write(HTML)
sz=os.path.getsize(OUTPUT_HTML)/1024
print(f'Done: {OUTPUT_HTML} ({sz:.0f}KB)')
