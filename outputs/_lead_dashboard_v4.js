// ===== 线索池看板 v4.0 JS逻辑（独立文件，避免Python f-string冲突）=====

/* 主题 */
const themeBtn=document.getElementById('themeBtn');
function setTheme(t){
  document.documentElement.setAttribute('data-theme',t);
  themeBtn.textContent=t==='dark'?'☀️':'🌙';
  try{localStorage.setItem('lead-theme',t);}catch(e){}
  if(FILTERED.length>0){drawAllCharts();if(typeof drawPageChannel==='function')drawPageChannel();}
}
themeBtn.onclick=()=>{const c=document.documentElement.getAttribute('data-theme')||'light';setTheme(c==='dark'?'light':'dark');};
try{
  if(localStorage.getItem('lead-theme'))setTheme(localStorage.getItem('lead-theme'));
  else if(window.matchMedia&&window.matchMedia('(prefers-color-scheme:dark)').matches)setTheme('dark');
}catch(e){}

/* 工具 */
function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function getCssVar(n){return getComputedStyle(document.documentElement).getPropertyValue(n).trim();}
function gClr(g){return getCssVar('--'+g)||'#ccc';}
function tClr(){return getCssVar('--text');} function t2Clr(){return getCssVar('--text2');} function bdClr(){return getCssVar('--border');}
function acClr(){return getCssVar('--accent');}
function fmtM(v){if(!v)return '¥0';if(v>=10000)return '¥'+(v/10000).toFixed(2)+'万';return '¥'+Math.round(v);}
function tgG(g){if(g==='DEAL')return '<span class="grade-tag DEAL">✅ 已成交</span>';if(g==='S')return '<span class="grade-tag S">S</span>';if(g==='A2')return '<span class="grade-tag A2">A2</span>';if(g==='A3')return '<span class="grade-tag A3">A3</span>';return '<span class="grade-tag '+g+'">'+g+'</span>';}
function tgI(it){if(it==='high')return '<span class="intent-tag hi">高意向</span>';if(it==='medium')return '<span class="intent-tag md">中意向</span>';if(it==='low')return '<span class="intent-tag lo">低</span>';if(it==='rejected')return '<span class="intent-tag rj">拒</span>';return '?';}
function tgAge(a){if(a==null)return'-';if(a<=7)return a+'天';if(a<=21)return a+'天';return '<span style="color:#dc3545;font-weight:600">'+a+'天</span>';}

/* 状态 */
let curGrade='',curItl='',curDept='',curCh='',curDeal='f',curKw='',curDFrom='',curDTo='',
    curCo='',
    PAGE=1,PGSZ=100,SORT_COL='sc',SORT_DIR=-1,FILTERED=[],expandedRow=null;

/* 表格列定义（全局，供详情展开行使用） */
const TCOLS=[{k:'g',l:'分级',w:40,f:c=>tgG(c.g)},
  {k:'sc',l:'评分',w:44},{k:'itl',l:'意向',w:64,f:c=>tgI(c.itl)},
  {k:'ind',l:'行业',w:70},{k:'dept',l:'部门',w:80},{k:'co',l:'顾问',w:60},
  {k:'ch',l:'渠道',w:90},{k:'at',l:'分配',w:60,f:c=>tgAge(c.age)},
  {k:'ph',l:'手机号',w:100,f:c=>'<span class="ph">'+esc(c.ph)+'</span>'}];

/* 导航 */
document.querySelectorAll('.nav-item').forEach(t=>{
  t.onclick=()=>{
    document.querySelectorAll('.nav-item').forEach(x=>x.classList.remove('active'));
    document.querySelectorAll('.page').forEach(x=>x.classList.remove('active'));
    t.classList.add('active');
    document.getElementById('page-'+t.dataset.page).classList.add('active');
    if(t.dataset.page==='overview')drawAllCharts();
    if(t.dataset.page==='channel')drawPageChannel();
    if(t.dataset.page==='list'&&FILTERED.length===0)applyFilter();
  };
});

/* Canvas工具 */
function setupCanvas(cv){
  const dpr=window.devicePixelRatio||1;
  const w=cv.clientWidth||cv.parentElement.clientWidth-36;
  const h=parseInt(cv.getAttribute('height'))||260;
  cv.width=w*dpr;cv.height=h*dpr;cv.style.height=h+'px';
  const ctx=cv.getContext('2d');ctx.scale(dpr,dpr);ctx.clearRect(0,0,w,h);
  return {ctx,w,h};
}

function drawPie(){
  const cv=document.getElementById('pieChart'),{ctx,w,h}=setupCanvas(cv);
  const grades=['S','A2','A3','B','C'];
  let dealCount=0;
  const data=grades.map(g=>({g,n:FILTERED.filter(c=>c.g===g).length}));
  dealCount=FILTERED.filter(c=>c.deal).length;
  const total=data.reduce((s,d)=>s+d.n,0)+dealCount;
  if(total===0)return;
  const cx=w*0.34,cy=h/2,R=Math.min(w*0.34,h*0.42);
  let a=-Math.PI/2;
  data.forEach(d=>{
    if(d.n===0)return;
    const ang=d.n/total*Math.PI*2;
    ctx.beginPath();ctx.moveTo(cx,cy);ctx.arc(cx,cy,R,a,a+ang);ctx.closePath();
    ctx.fillStyle=gClr(d.g);ctx.fill();ctx.strokeStyle=getCssVar('--card');ctx.lineWidth=3;ctx.stroke();
    a+=ang;
  });
  if(dealCount>0){
    const ang=dealCount/total*Math.PI*2;
    ctx.beginPath();ctx.moveTo(cx,cy);ctx.arc(cx,cy,R,a,a+ang);ctx.closePath();ctx.fillStyle='#2E7D32';ctx.fill();
    a+=ang;
  }
  ctx.fillStyle=tClr();ctx.font='bold 26px "PingFang SC"';ctx.textAlign='center';ctx.textBaseline='middle';
  ctx.fillText(total,cx,cy-8);
  ctx.fillStyle=t2Clr();ctx.font='11px "PingFang SC"';ctx.fillText('总线索',cx,cy+14);
  const lx=w*0.66;let ly=h/2-(data.length*22)/2+10;
  ctx.font='12px "PingFang SC"';ctx.textAlign='left';
  const allItems=[...data];if(dealCount>0)allItems.push({g:'DEAL',n:dealCount});
  allItems.forEach(d=>{
    ctx.fillStyle=gClr(d.g);ctx.fillRect(lx,ly-6,12,12);
    ctx.fillStyle=tClr();ctx.fillText(d.g+'  '+d.n+' ('+(d.n/total*100).toFixed(1)+'%)',lx+18,ly);ly+=22;
  });
}

function drawBar(cv,items,opts){
  const {ctx,w,h}=setupCanvas(cv);
  if(!items.length)return;
  const padL=opts.padL||44,padR=12,padT=16,padB=64;
  const cw=w-padL-padR,ch=h-padT-padB;
  const maxV=Math.max.apply(null,items.map(i=>i.v))||1;
  let niceMax=1,mag=Math.pow(10,Math.floor(Math.log10(maxV)));niceMax=Math.ceil(maxV/mag)*mag;
  const gap=cw/items.length,bw=gap*0.62;
  ctx.strokeStyle=bdClr();ctx.fillStyle=t2Clr();ctx.font='10px "PingFang SC"';
  ctx.textAlign='right';ctx.textBaseline='middle';
  for(let i=0;i<=4;i++){
    const v=niceMax*i/4,y=padT+ch-ch*i/4;
    ctx.beginPath();ctx.moveTo(padL,y);ctx.lineTo(w-padR,y);ctx.globalAlpha=.5;ctx.stroke();ctx.globalAlpha=1;
    ctx.fillText(v>=1000?(v/1000)+'k':Math.round(v),padL-6,y);
  }
  const colors=opts.colors||[acClr()];
  items.forEach((it,i)=>{
    const x=padL+i*gap+(gap-bw)/2,bh=ch*(it.v/niceMax),y=padT+ch-bh;
    const col=Array.isArray(colors)?colors[i%colors.length]:colors;
    ctx.fillStyle=col;const r=Math.min(4,bw/2);
    ctx.beginPath();ctx.moveTo(x,y+r);ctx.arcTo(x,y,x+bw,y+r,r);
    ctx.arcTo(x+bw,y,x+bw,y+bh,r);ctx.lineTo(x+bw,y+bh);ctx.lineTo(x,y+bh);ctx.closePath();ctx.fill();
    ctx.fillStyle=tClr();ctx.font='bold 11px "PingFang SC"';ctx.textAlign='center';ctx.textBaseline='bottom';
    ctx.fillText(it.v,x+bw/2,y-3);
  });
  // X-axis labels rotated
  ctx.save();
  ctx.fillStyle=t2Clr();ctx.font='11px "PingFang SC"';ctx.textAlign='right';ctx.textBaseline='middle';
  items.forEach((it,i)=>{
    const x=padL+i*gap+(gap-bw)/2+bw/2;
    const label=it.l.length>10?it.l.slice(0,10)+'...':it.l;
    ctx.save();
    ctx.translate(x,padT+ch+12);
    ctx.rotate(-Math.PI/4);
    ctx.fillText(label,0,0);
    ctx.restore();
  });
  ctx.restore();
}
function drawAllCharts(){renderKPI();drawPie();drawChChart();drawDeptChart();renderCounselorBars();}

/* KPI */
function renderKPI(){
  const g={S:0,A2:0,A3:0,B:0,C:0,DEAL:0};let totalAmt=0;
  FILTERED.forEach(c=>{g[c.g]=(g[c.g]||0)+1;if(c.amt>0)totalAmt+=c.amt;});
  const total=FILTERED.length;
  document.getElementById('listBadge').textContent=total;
  document.getElementById('kpiGrid').innerHTML=[
    {lbl:'有效线索',val:total,cls:'',mini:'<span>未成交 <b>'+total+'</b></span><span>已成交 <b>'+g.DEAL+'</b></span><span>转化 <b>'+(total?(g.DEAL/total*100).toFixed(1):0)+'%</b></span>'},
    {lbl:'S · 立即',val:g.S,cls:'grade S',mini:'<span>占比 <b>'+(g.S/total*100).toFixed(1)+'%</b></span>'},
    {lbl:'A2 · 重点',val:g.A2,cls:'grade A2',mini:'<span>占比 <b>'+(g.A2/total*100).toFixed(1)+'%</b></span>'},
    {lbl:'A3 · 正常',val:g.A3,cls:'grade A3',mini:'<span>占比 <b>'+(g.A3/total*100).toFixed(1)+'%</b></span>'},
    {lbl:'B · 低优',val:g.B,cls:'grade B',mini:'<span>占比 <b>'+(g.B/total*100).toFixed(1)+'%</b></span>'},
    {lbl:'C · 暂缓',val:g.C,cls:'grade C',mini:'<span>占比 <b>'+(g.C/total*100).toFixed(1)+'%</b></span>'},
    {lbl:'成交金额',val:fmtM(totalAmt),cls:'',mini:'<span>均价 <b>'+fmtM(totalAmt/Math.max(g.DEAL,1))+'</b></span>'},
  ].map(it=>'<div class="kpi '+it.cls+'"><div class="lbl">'+it.lbl+'</div><div class="val">'+it.val+'</div>'
    +(it.mini?'<div class="kpi-mini">'+it.mini+'</div>':'')+'</div>').join('');
  document.getElementById('subInfo').textContent='投流线索 · '+total+' 条有效 · '+g.DEAL+' 已成交 · '+fmtM(totalAmt);
}

/* 渠道图表 */
function drawChChart(){
  const cnt={};FILTERED.forEach(c=>{cnt[c.ch]=(cnt[c.ch]||0)+1;});
  const items=Object.keys(cnt).map(k=>({l:k,v:cnt[k]})).sort((a,b)=>b.v-a.v).slice(0,10);
  drawBar(document.getElementById('chChart'),items,{padL:48,colors:['#E65100','#F57C00','#FB8C00','#FFA726','#FFB74D','#FFCA28']});
}
function drawDeptChart(){
  const cnt={};FILTERED.forEach(c=>{cnt[c.dept]=(cnt[c.dept]||0)+1;});
  const items=Object.keys(cnt).map(k=>({l:k,v:cnt[k]})).sort((a,b)=>b.v-a.v).slice(0,10);
  drawBar(document.getElementById('deptChart'),items,{padL:56,colors:'#E65100 #F57C00 #7CB342 #1976D2 #78909C'.split(' ')});
}
function renderCounselorBars(){
  const cnt={};
  FILTERED.forEach(c=>{cnt[c.co]=(cnt[c.co]||0)+1;});
  const items=Object.keys(cnt).map(k=>({name:k,n:cnt[k]})).sort((a,b)=>b.n-a.n);
  const maxN=Math.max.apply(null,items.map(i=>i.n))||1,total=FILTERED.length,
        box=document.getElementById('counselorBars');
  if(!box)return;
  box.innerHTML=items.slice(0,20).map(it=>{
    const pct=(it.n/maxN*100).toFixed(1),share=(it.n/total*100).toFixed(1);
    return '<div class="counselor-bar" onclick="filterByCo(\''+esc(it.name)+'\')">'
      +'<div style="min-width:90px;font-size:13px;font-weight:600;color:var(--text)">'+esc(it.name)+'</div>'
      +'<div style="flex:1;height:24px;background:var(--bg2);border-radius:6px;border:1px solid var(--border)">'
      +'<div style="height:100%;width:'+pct+'%;background:linear-gradient(90deg,var(--accent),var(--accent2));border-radius:6px"></div></div>'
      +'<div style="min-width:100px;text-align:right;font-size:13px"><b style="color:var(--text)">'+it.n
      +'</b> <span style="color:var(--text2);font-size:11px">('+share+'%)</span></div></div>';
  }).join('');
}
window.addEventListener('resize',()=>{if(document.getElementById('page-overview').classList.contains('active'))drawAllCharts();});

/* 筛选 */
function applyFilter(){
  FILTERED=DATA.filter(c=>{
    if(curGrade&&c.g!==curGrade)return false;
    if(curItl&&c.itl!==curItl)return false;
    if(curDept&&c.dept!==curDept)return false;
    if(curCh&&c.ch!==curCh)return false;
    if(curCo&&c.co!==curCo)return false;
    if(curDeal==='t'&&!c.deal)return false;if(curDeal==='f'&&c.deal)return false;
    if(curKw){
      const s=(c.ph+' '+c.oc+' '+c.note+' '+c.src+' '+c.ind+' '+c.st).toLowerCase();
      if(!s.includes(curKw)&&!c.ph.includes(curKw))return false;
    }
    if(curDFrom||curDTo){const ds=c.at||'';if(ds){const dv=ds.replace(/\./g,'-');
      if(curDFrom&&dv<curDFrom)return false;if(curDTo&&dv>curDTo)return false;}}
    return true;
  });
  FILTERED.sort((a,b)=>{
    let v=a[SORT_COL]!=null?a[SORT_COL]:'',vv=b[SORT_COL]!=null?b[SORT_COL]:'';
    if(typeof v==='number')return(v-vv)*SORT_DIR;
    v=String(v).toLowerCase();vv=String(vv).toLowerCase();return v<vv?-1*SORT_DIR:v>vv?1*SORT_DIR:0;
  });
  PAGE=1;renderKPI();renderList();renderFilterStat();buildSelects();
  if(document.getElementById('page-overview').classList.contains('active'))drawAllCharts();
}
function renderFilterStat(){document.getElementById('filterStat').textContent=FILTERED.length+' 条 / '+DATA.length+' 总';}
function buildSelects(){
  // 从当前 FILTERED 动态重建下拉选项，保留当前选中
  const depts=[...new Set(FILTERED.map(c=>c.dept))].sort();
  const chs=[...new Set(FILTERED.map(c=>c.ch))].sort();
  const cos=[...new Set(FILTERED.map(c=>c.co))].sort();
  rebuildSelect('fltDept', depts, curDept);
  rebuildSelect('fltCh', chs, curCh);
  rebuildSelect('fltCo', cos, curCo);
}
function rebuildSelect(id, values, current){
  const sel=document.getElementById(id); if(!sel)return;
  const oldVal=current;
  sel.innerHTML='<option value="">全部</option>';
  values.forEach(v=>{const o=document.createElement('option');o.value=v;o.textContent=v;sel.appendChild(o);});
  sel.value=(values.includes(oldVal)?oldVal:'');
}
function filterByCo(name){
  document.querySelectorAll('.nav-item').forEach(x=>x.classList.remove('active'));
  document.querySelectorAll('.page').forEach(x=>x.classList.remove('active'));
  document.querySelector('.nav-item[data-page="list"]').classList.add('active');
  document.getElementById('page-list').classList.add('active');
  curCo=name;
  applyFilter();
}
document.getElementById('search').addEventListener('input',e=>{curKw=e.target.value.toLowerCase();applyFilter();});
document.querySelectorAll('#gradeChips .chip').forEach(c=>{
  c.onclick=()=>{document.querySelectorAll('#gradeChips .chip').forEach(x=>x.classList.remove('active'));
    c.classList.add('active');curGrade=c.dataset.grade;applyFilter();};
});
document.getElementById('fltItl').onchange=e=>{curItl=e.target.value;applyFilter();};
document.getElementById('fltDeal').onchange=e=>{curDeal=e.target.value;applyFilter();};
document.getElementById('fltCo').onchange=e=>{curCo=e.target.value;applyFilter();};
document.getElementById('fltDateFrom').onchange=e=>{curDFrom=e.target.value;applyFilter();};
document.getElementById('fltDateTo').onchange=e=>{curDTo=e.target.value;applyFilter();};

/* 排序 */
function sortTable(col){if(SORT_COL===col){SORT_DIR*=-1;}else{SORT_COL=col;SORT_DIR=-1;}applyFilter();}

/* 表格渲染 */
function renderList(){
  const thead=document.getElementById('theadRow'),tbody=document.getElementById('tbody');
  const cg=TCOLS.map(col=>'<col style="width:'+col.w+'px">').join('')+'<col style="width:50px">';
  thead.innerHTML=TCOLS.map(col=>{
    const arr=SORT_COL===col.k?' '+(SORT_DIR===1?'▲':'▼'):'';
    return '<th onclick="sortTable(\''+col.k+'\')">'+col.l+arr+'</th>';
  }).join('<th></th>');
  const tp=Math.max(1,Math.ceil(FILTERED.length/PGSZ));if(PAGE>tp)PAGE=tp;
  const start=(PAGE-1)*PGSZ,end=Math.min(start+PGSZ,FILTERED.length),
        rows=FILTERED.slice(start,end);
  tbody.innerHTML=rows.map((rec,idx)=>{
    const ri=start+idx,cls=rec.g==='S'?'style="background:var(--S)"':rec.g==='A2'?'style="background:var(--A2)"':rec.g==='A3'?'style="background:var(--A3)"':'';
    return '<tr data-idx="'+ri+'" '+cls+' onclick="toggleExpand('+ri+')">'
      +TCOLS.map(col=>'<td>'+(col.f?col.f(rec):esc(String(rec[col.k]==null?'-':rec[col.k])))+'</td>').join('')
      +'<td><button onclick="event.stopPropagation();copyPhone(\''+esc(rec.ph).replace(/'/g,"\\'")+'\')"style="padding:2px 6px;font-size:10px;border:1px solid var(--border);background:transparent;color:var(--text2);border-radius:4px;cursor:pointer;font-family:inherit">复制</button></td></tr>';
  }).join('');
  // Insert colgroup before header
  const table=document.querySelector('#page-list table');
  if(table){
    const oldCg=table.querySelector('colgroup');
    if(oldCg)oldCg.remove();
    table.insertAdjacentHTML('afterbegin','<colgroup>'+cg+'</colgroup>');
  }
  renderPager();
}
function renderPager(){
  const tp=Math.max(1,Math.ceil(FILTERED.length/PGSZ)),pg=document.getElementById('pager'),
        start=(PAGE-1)*PGSZ+1,end=Math.min(PAGE*PGSZ,FILTERED.length);
  pg.innerHTML='<button onclick="goPage('+(PAGE-1)+')" '+(PAGE<=1?'disabled':'')+'>◀</button>'
    +'<span class="info">'+start+'-'+end+'/'+FILTERED.length+' (第'+PAGE+'/'+tp+')</span>'
    +'<button onclick="goPage('+(PAGE+1)+')" '+(PAGE>=tp?'disabled':'')+'>▶</button>'
    +'每页<select onchange="changePageSize(this.value)"><option'+(PGSZ===50?' selected':'')+'>50</option><option'+(PGSZ===100?' selected':'')+'>100</option><option'+(PGSZ===200?' selected':'')+'>200</option></select>条';
}
function goPage(p){const tp=Math.ceil(FILTERED.length/PGSZ);if(p>=1&&p<=tp){PAGE=p;renderList();window.scrollTo({top:0,behavior:'smooth'});}}
function changePageSize(n){PGSZ=parseInt(n)||100;PAGE=1;renderList();}

/* 详情展开行 */
function toggleExpand(idx){
  const row=document.querySelector('tr[data-idx="'+idx+'"]');if(!row)return;
  const next=row.nextElementSibling;
  if(next&&next.classList.contains('detail-row')){
    row.classList.remove('expanded');next.remove();expandedRow=null;return;
  }
  if(expandedRow){
    const prevExp=document.querySelector('tr.expanded');
    if(prevExp){prevExp.classList.remove('expanded');const pd=prevExp.nextElementSibling;if(pd&&pd.classList.contains('detail-row'))pd.remove();}
  }
  row.classList.add('expanded');expandedRow=row;
  const c=FILTERED[idx];if(!c)return;
  // 评分明细
  let scHtml='';
  if(c.scd){
    ['L1','L2','L3','L4','L5','L6'].forEach(k=>{
      const v=c.scd[k],cl=v>=4?'s5':v>=3?'s4':v>=2?'s3':v>=1?'s2':'s1';
      scHtml+='<div class="sc-cell '+cl+'">'+v+'</div>';
    });
  }
  // 话术 & 产品推荐
  const talk=genTalk(c),prods=genProds(c);
  const prodHtml=prods.map(p=>'<div class="pcard"><div class="pn">📦 '+esc(p.n)
    +'</div><div class="pd">'+esc(p.c)+' | '+esc(p.d)+' | '+esc(p.p)+'</div></div>').join('');
  let frHtml='';
  [c.f1,c.f2,c.f3,c.f4].forEach((fv,n)=>{if(fv)frHtml+='<li><strong>'+['一','二','三','四'][n]+'次:</strong> '+esc(fv)+'</li>';});
  
  const tr=document.createElement('tr');
  tr.className='detail-row';
  tr.innerHTML='<td colspan="'+(TCOLS.length+1)+'">'
    +'<div class="detail-box">'
    +'<div class="block"><h4>📊 评分明细</h4><div class="score-bar">'+scHtml+'</div><p style="font-size:11.5px;color:var(--text2);margin-top:6px">L1意向 L2渠道 L3来源 L4跟进 L5新鲜 L6触达 | 总分:'+c.sc+'/30</p></div>'
    +'<div class="block"><h4>👤 客户画像</h4><ul><li>行业: <b>'+esc(c.ind)+'</b></li><li>规模: <b>'+(esc(c.scl)||'-')+'</b></li><li>渠道: <b>'+esc(c.ch)+'</b></li><li>来源: <b>'+esc(c.src)+'</b></li><li>部门: <b>'+esc(c.dept)+'</b></li><li>顾问: <b>'+esc(c.co)+'</b></li></ul></div>'
    +'<div class="block"><h4>📦 推荐产品</h4>'+(prodHtml||'<div class="tt">暂无推荐(行业/渠道信息不足)</div>')+'</div>'
    +'</div>'
    +(talk?'<div class="talk-box"><div class="talk-title">🎤 销售话术(可直接念给客户)</div><div style="white-space:pre-line;color:#333">'+talk.talk+'</div></div>':'')
    +'<div class="action-box"><div class="action-title">⏭️ 建议动作</div><div>'+(talk.action||'-')+'</div></div>'
    +(frHtml?'<div style="padding:10px 14px;margin:8px 0;background:var(--card);border-radius:8px;border:1px solid var(--border)"><h4 style="font-size:12px;color:var(--accent);margin-bottom:6px">📝 跟进记录</h4><ul style="list-style:none;padding-left:0">'+frHtml+'</ul></div>':'')
    +(c.note?'<div style="margin:8px 0;padding:8px 12px;background:#f5f5f5;border-radius:6px;font-size:12px"><strong style="color:var(--text2)">备注:</strong> '+esc(c.note)+'</div>':'')
    +'<div style="margin-top:12px;display:flex;gap:8px">'
    +'<button onclick="copyPhone(\''+esc(c.ph).replace(/'/g,"\\'")+'\')"style="padding:8px 16px;background:var(--accent);color:#fff;border:none;border-radius:6px;cursor:pointer;font-weight:700;font-size:12px;font-family:inherit">📋 复制手机号</button>'
    +'<button onclick="this.innerText=\'✅已复制\';navigator.clipboard.writeText(\''+esc(talk.talk||'').replace(/'/g,"\\'")+'\')"style="padding:8px 16px;background:var(--accent2);color:#fff;border:none;border-radius:6px;cursor:pointer;font-weight:700;font-size:12px;font-family:inherit">📝 复制话术</button>'
    +'</div></td>';
  row.after(tr);
}

function copyPhone(p){navigator.clipboard.writeText(p||'').then(()=>alert('✅ 已复制: '+p));}

/* 话术引擎 */
function genTalk(c){
  const ind=c.ind,it=c.itl,ch=c.ch;
  let talk='您好！我是科技顾问。看到您在关注我们的产品。请问您现在是用什么方式管理库存和销售的呢？是手工记账还是已经在用软件了？',
      action='📞 3天内完成首次有效联系，了解需求；';
  if(ind.indexOf('服装')>=0)talk='您好！看到您在小红书/抖音关注了我们。您是做服装的对吧？我们很多服装客户都在用进销存系统，可以帮您统计每个款卖多少、库存还剩多少、哪些好卖哪些不行，一目了然。';
  else if(ind.indexOf('美')>=0)talk='您好！我是科技顾问。您是做美容/美发的吧？这行客户复购率很高，如果有一套系统能帮您管理会员信息、积分、储值，对提升复购真的很有帮助。我们的会员卡系统可以让客户在微信上查积分、兑换、预约。';
  else if(ind.indexOf('食品')>=0||ind.indexOf('生鲜')>=0)talk='您好！我是科技顾问。您是做食品/生鲜的吧？这行业最头疼的就是保质期管理和应收应付。进销存可以自动提醒哪些货快过期了，降低损耗。';
  
  if(it==='high'){talk+='\n\n[高意向] 已表达进一步了解意向 → 直接弄清需求点，针对性推荐方案，快速推到演示环节。';action+='⚡ 24小时内安排产品演示，重点推专业版+微商城；'}
  else if(it==='medium'){talk+='\n\n[中意向] 有兴趣但在考虑 → 先了解痛点和需求，再做匹配推荐。';action='📞 48小时内二次回访，发产品资料+成功案例；'}
  else if(it==='rejected'){talk='\n[已拒绝/无效] 暂时放低优先级或等一段时间再联系。';action='😐 标记为已拒绝，30天后再回访；'}
  
  if(c.age!=null&&c.age<=3){talk+='\n⚡ 线索非常新鲜，三天内必须弄清意向！';}
  if(ch&&ch.indexOf('广告')>=0){talk+='\n[投流线索] 付费广告获取，已认知品牌，转化概率较高。';}
  return {talk, action};
}

/* 产品推荐引擎 */
function genProds(c){
  const baseProds=[
    {n:'进销存专业版',c:'核心系统',d:'进销存+商品管理+库存预警',p:'¥1680-2680/年'},
    {n:'销货宝微商城',c:'线上渠道',d:'微信小程序商城+在线支付',p:'¥980-2980/年'},
    {n:'专属品牌小程序',c:'线上渠道',d:'独立品牌小程序+自定义装修',p:'¥1980-3980/年'},
    {n:'专属微信会员卡',c:'会员运营',d:'微信会员卡+积分+储值+画像',p:'¥680-1280/年'},
    {n:'批量推款宝',c:'营销工具',d:'批量推款给客户在线选款',p:'¥380-680/年'},
  ];
  if(c.ind.indexOf('服装')>=0)return baseProds.filter(p=>['进销存专业版','销货宝微商城','专属品牌小程序','批量推款宝'].includes(p.n));
  if(c.ind.indexOf('美')>=0)return baseProds.filter(p=>['进销存专业版','专属微信会员卡','销货宝微商城','微信自动化经营'].includes(p.n));
  return baseProds.slice(0,5);
}

/* 渠道分析页 */
function drawPageChannel(){
  const ccnt={},conv={};DATA.forEach(c=>{
    ccnt[c.ch]=(ccnt[c.ch]||0)+1;conv[c.ch]=(conv[c.ch]||{t:0,d:0,r:0});conv[c.ch].t++;if(c.deal)conv[c.ch].d++;
  });Object.keys(conv).forEach(k=>{conv[k].r=conv[k].t?((conv[k].d/conv[k].t)*100).toFixed(1):0;});
  const cItems=Object.entries(conv).sort((a,b)=>b[1].t-a[1].t);
  drawBar(document.getElementById('chConvChart'),cItems.map(([k,v])=>({l:k,v:v.t,d:v.d,r:Number(v.r)})),
    {padL:52,colors:cItems.map(([k,v])=>Number(v.r)>3?'#2E7D32':Number(v.r)>1?'#43A047':'#FFA726')});
  const scnt={};DATA.forEach(c=>{const s=(c.src||'未知').substring(0,12);scnt[s]=(scnt[s]||0)+1;});
  const sItems=Object.keys(scnt).map(k=>({l:k,v:scnt[k]})).sort((a,b)=>b.v-a.v).slice(0,15);
  drawBar(document.getElementById('srcChart'),sItems,{padL:52,colors:'#E65100'});
  const icnt={};DATA.forEach(c=>{icnt[c.itl]=(icnt[c.itl]||0)+1;});
  const iItems=Object.keys(icnt).map(k=>({
    l:(k===''?'未知':k=='high'?'高意向':k=='medium'?'中意向':k=='low'?'低意向':'已拒绝'),v:icnt[k]
  }));
  drawBar(document.getElementById('itlChart'),iItems,{padL:52,colors:['#C62828','#E65100','#F57F17','#9E9E9E']});
}

/* 导出CSV */
function exportCSV(){
  const hdr=['分级','评分','意向','行业','部门','顾问','渠道','来源','分配时间','手机号'],
  rows=FILTERED.map(c=>[c.g,c.sc,c.itl,c.ind,c.dept,c.co,c.ch,c.src,c.at,c.ph]),
  csv='\uFEFF'+[hdr,...rows].map(r=>r.map(v=>'"'+String(v||'-').replace(/"/g,'"')+'"').join(',')).join('\n');
  const blob=new Blob([csv],{type:'text/csv;charset=utf-8'}),url=URL.createObjectURL(blob);
  const a=document.createElement('a');a.href=url;a.download='线索池机会清单_'+new Date().toISOString().slice(0,10)+'.csv';a.click();URL.revokeObjectURL(url);
}

/* 初始化 */
applyFilter();
if(document.getElementById('page-overview').classList.contains('active'))drawAllCharts();
