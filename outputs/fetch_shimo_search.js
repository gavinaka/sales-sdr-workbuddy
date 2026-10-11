// 石墨文档 - 内容搜索定位数据模型（找含表格实际内容的对象）
const { chromium } = require('playwright-core');
const fs = require('fs');
const path = require('path');

const CHROME_PATH = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const USER_DATA_DIR = path.join(__dirname, '.shimo_data');
const OUTPUT_DIR = path.join(__dirname, 'shimo_capture');
const DATA_OUTPUT = path.join(__dirname, 'shimo_raw_data');
const URL = 'https://shimo.im/sheets/473QMXrrL4F7p53w/dJr6p';

if (!fs.existsSync(OUTPUT_DIR)) fs.mkdirSync(OUTPUT_DIR, { recursive: true });
if (!fs.existsSync(DATA_OUTPUT)) fs.mkdirSync(DATA_OUTPUT, { recursive: true });

(async () => {
  console.log('启动浏览器...');
  const context = await chromium.launchPersistentContext(USER_DATA_DIR, {
    executablePath: CHROME_PATH,
    headless: false,
    viewport: null,
    args: ['--start-maximized', '--disable-blink-features=AutomationControlled']
  });
  const pages = context.pages();
  const page = pages.length > 0 ? pages[0] : await context.newPage();

  console.log('打开石墨文档...');
  await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
  try { await page.waitForSelector('.sm-sheet-tab-item', { timeout: 30000 }); } catch (e) {}
  await page.waitForTimeout(6000);

  // 内容搜索：递归遍历所有对象，找含表格关键词的对象
  console.log('\n=== 内容搜索定位数据模型 ===');
  const search = await page.evaluate(() => {
    const out = { matches: [], bigObj: null };
    const KEYWORDS = ['小红书', '线索', '顾问', '转化率', '流转表', '成交数据'];
    const PHONE_RE = /1[3-9]\d{9}/;

    const entries = [document.querySelector('.spreadsheet-view'), document.querySelector('.sm-sheet-wrapper'), document.querySelector('#root')];
    let entryFiber = null;
    for (const el of entries) { if (!el) continue; const fk = Object.keys(el).find(k => k.startsWith('__react')); if (fk) { entryFiber = el[fk]; break; } }
    if (!entryFiber) { out.error = '无fiber入口'; return out; }
    let rootFiber = entryFiber;
    while (rootFiber && rootFiber.return) rootFiber = rootFiber.return;
    if (rootFiber.tag === 3 && rootFiber.current) rootFiber = rootFiber.current;

    const fiberVisited = new Set();
    const objVisited = new WeakSet();
    let totalScanned = 0;
    const MAX_SCAN = 80000;

    function scanObj(obj, depth, path, parentChain) {
      if (!obj || typeof obj !== 'object' || depth > 6 || totalScanned > MAX_SCAN) return;
      try { if (objVisited.has(obj)) return; objVisited.add(obj); } catch (e) { return; }
      totalScanned++;

      // 检查这个对象的字符串值是否含关键词
      let matchCount = 0;
      let matchedKeywords = [];
      let isImmutable = false;
      try {
        // Immutable.js 对象有 get 方法且非数组
        if (typeof obj.get === 'function' && typeof obj.toJS === 'function' && !Array.isArray(obj)) {
          isImmutable = true;
        }
      } catch (e) {}

      try {
        const keys = isImmutable ? (obj.keys ? Array.from(obj.keys()) : Object.keys(obj)) : Object.keys(obj);
        for (const k of keys.slice(0, 200)) {
          let v;
          try { v = isImmutable ? obj.get(k) : obj[k]; } catch (e) { continue; }
          if (typeof v === 'string') {
            for (const kw of KEYWORDS) {
              if (v.includes(kw)) { matchCount++; matchedKeywords.push(kw + ':' + v.substring(0, 40)); break; }
            }
            if (PHONE_RE.test(v)) { matchCount++; matchedKeywords.push('phone:' + v.substring(0, 20)); }
          }
        }
      } catch (e) {}

      // 如果匹配多个关键词，这是潜在数据模型
      if (matchCount >= 2) {
        out.matches.push({
          path, depth, matchCount,
          matched: matchedKeywords.slice(0, 10),
          isImmutable,
          keyCount: (() => { try { return isImmutable ? (obj.size !== undefined ? obj.size : '?') : Object.keys(obj).length; } catch (e) { return '?'; } })(),
          keys: (() => { try { return isImmutable ? Array.from(obj.keys()).slice(0, 20) : Object.keys(obj).slice(0, 20); } catch (e) { return []; } })()
        });
        // 保存最大的匹配对象
        if (!out.bigObj || (typeof out.bigObj.keyCount === 'number' && out.bigObj.keyCount < matchCount)) {
          try {
            window.__dataModel = obj;
            out.bigObj = { path, matchCount, isImmutable };
          } catch (e) {}
        }
      }

      // 递归
      let keys;
      try { keys = isImmutable ? Array.from(obj.keys()) : Object.keys(obj); } catch (e) { return; }
      for (const k of keys.slice(0, 50)) {
        if (totalScanned > MAX_SCAN) return;
        let v;
        try { v = isImmutable ? obj.get(k) : obj[k]; } catch (e) { continue; }
        if (v && typeof v === 'object' && typeof v !== 'function') {
          scanObj(v, depth + 1, path + '.' + k, obj);
        }
      }
    }

    function dfs(f, depth) {
      if (!f || fiberVisited.has(f) || depth > 25 || totalScanned > MAX_SCAN) return;
      fiberVisited.add(f);
      try { if (f.memoizedProps) scanObj(f.memoizedProps, 0, 'props', null); } catch (e) {}
      try {
        const sn = f.stateNode;
        if (sn && typeof sn === 'object' && !sn.tagName && !sn.nodeType) {
          scanObj(sn, 0, 'sn', null);
          if (sn.props) scanObj(sn.props, 0, 'sn.props', null);
          if (sn.state) scanObj(sn.state, 0, 'sn.state', null);
        }
      } catch (e) {}
      dfs(f.child, depth + 1); dfs(f.sibling, depth + 1);
      let eff = f.firstEffect;
      while (eff) {
        if (!fiberVisited.has(eff)) {
          fiberVisited.add(eff);
          try {
            if (eff.memoizedProps) scanObj(eff.memoizedProps, 0, 'eff.props', null);
            if (eff.stateNode && typeof eff.stateNode === 'object' && !eff.stateNode.tagName) {
              scanObj(eff.stateNode, 0, 'eff.sn', null);
              if (eff.stateNode.props) scanObj(eff.stateNode.props, 0, 'eff.sn.props', null);
            }
          } catch (e) {}
        }
        eff = eff.nextEffect;
      }
    }
    dfs(rootFiber, 0);
    out.fiberScanned = fiberVisited.size;
    out.objScanned = totalScanned;
    // 按matchCount排序
    out.matches.sort((a, b) => b.matchCount - a.matchCount);
    out.matches = out.matches.slice(0, 25);
    return out;
  });

  console.log('扫描fiber:', search.fiberScanned, '扫描对象:', search.objScanned);
  console.log('匹配数据模型:', search.matches.length);
  search.matches.slice(0, 15).forEach((m, i) => {
    console.log(`\n  [匹配${i}] path=${m.path} depth=${m.depth} matchCount=${m.matchCount} isImmutable=${m.isImmutable} keyCount=${m.keyCount}`);
    console.log(`    keys: ${m.keys.join(', ')}`);
    console.log(`    matched: ${m.matched.join(' | ')}`);
  });
  fs.writeFileSync(path.join(OUTPUT_DIR, 'content_search.json'), JSON.stringify(search, null, 2), 'utf-8');

  // ========== 如果找到数据模型，提取数据 ==========
  if (search.bigObj) {
    console.log('\n=== 找到数据模型！提取数据 ===');
    console.log('路径:', search.bigObj.path, 'isImmutable:', search.bigObj.isImmutable);
    const extract = await page.evaluate(() => {
      const dm = window.__dataModel;
      if (!dm) return { error: '无dm' };
      const out = {};
      // 如果是Immutable，转JS
      let plain;
      try {
        if (typeof dm.toJS === 'function') {
          plain = dm.toJS();
          out.convertedFromImmutable = true;
        } else {
          plain = JSON.parse(JSON.stringify(dm));
        }
      } catch (e) {
        out.convertError = e.message;
        // 尝试手动提取
        try {
          plain = {};
          const keys = Object.keys(dm);
          for (const k of keys) {
            const v = dm[k];
            if (typeof v !== 'function') {
              try { plain[k] = typeof v === 'object' && v && typeof v.toJS === 'function' ? v.toJS() : JSON.parse(JSON.stringify(v)); } catch (e) { plain[k] = String(v); }
            }
          }
        } catch (e2) { out.manualError = e2.message; }
      }
      if (plain) {
        out.keys = Object.keys(plain);
        out.strLen = JSON.stringify(plain).length;
        out.preview = JSON.stringify(plain).substring(0, 3000);
        out.full = plain;
      }
      return out;
    });
    console.log('转换自Immutable:', extract.convertedFromImmutable);
    console.log('keys:', extract.keys);
    console.log('strLen:', extract.strLen);
    console.log('preview:', (extract.preview || '').substring(0, 2000));
    if (extract.full) {
      fs.writeFileSync(path.join(DATA_OUTPUT, 'datamodel_extracted.json'), JSON.stringify(extract.full, null, 2), 'utf-8');
      console.log('\n已保存 datamodel_extracted.json, 大小:', JSON.stringify(extract.full).length);
    }
    fs.writeFileSync(path.join(OUTPUT_DIR, 'datamodel_extract_info.json'), JSON.stringify(extract, null, 2), 'utf-8');
  }

  console.log('\n完成');
  await page.waitForTimeout(3000);
  await context.close();
})().catch(e => { console.error('脚本错误:', e); process.exit(1); });
