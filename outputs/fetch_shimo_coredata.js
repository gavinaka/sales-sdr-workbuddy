// 石墨文档 - 探测 coreData 数据中心 + FM.file + 尝试initContentStorage
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
  await page.waitForTimeout(5000);

  // 找 coreData 对象 + contentStorageInstance
  const probe = await page.evaluate(() => {
    const out = { found: false };
    const entries = [document.querySelector('.spreadsheet-view'), document.querySelector('.sm-sheet-wrapper'), document.querySelector('#root')];
    let entryFiber = null;
    for (const el of entries) { if (!el) continue; const fk = Object.keys(el).find(k => k.startsWith('__react')); if (fk) { entryFiber = el[fk]; break; } }
    if (!entryFiber) { out.error = '无fiber入口'; return out; }
    let rootFiber = entryFiber;
    while (rootFiber && rootFiber.return) rootFiber = rootFiber.return;
    if (rootFiber.tag === 3 && rootFiber.current) rootFiber = rootFiber.current;

    const fiberVisited = new Set();
    const objVisited = new WeakSet();
    let coreData = null;
    let contentStorage = null;
    let sheetModel = null;

    function scanObj(obj, depth, path) {
      if (!obj || typeof obj !== 'object' || depth > 7) return;
      try { if (objVisited.has(obj)) return; objVisited.add(obj); } catch (e) { return; }
      // 找 coreData 属性
      try {
        if (obj.coreData && typeof obj.coreData === 'object' && !coreData) {
          coreData = obj.coreData;
          out.coreDataPath = path + '.coreData';
        }
      } catch (e) {}
      // 找 contentStorageInstance
      try {
        if (obj.contentStorageInstance && typeof obj.contentStorageInstance === 'object' && !contentStorage) {
          contentStorage = obj.contentStorageInstance;
          out.csiPath = path + '.contentStorageInstance';
        }
      } catch (e) {}
      // 找含 getSheet/getCell/getModel 的对象（表格数据模型）
      try {
        const ks = Object.keys(obj);
        if (!sheetModel && ks.length > 5) {
          const methods = ks.filter(k => typeof obj[k] === 'function');
          if (methods.some(m => /getSheet|getCell|getModel|getAllSheet|getWorkbook|getSheetData|getCellData|exportData|toJSON|serialize/i.test(m))) {
            sheetModel = obj;
            out.sheetModelPath = path;
            out.sheetModelMethods = methods.filter(m => /get|sheet|cell|model|workbook|data|export|json|serialize|all|row|column/i.test(m));
          }
        }
      } catch (e) {}
      if (coreData && contentStorage && sheetModel) return;
      let keys; try { keys = Object.keys(obj); } catch (e) { return; }
      for (const k of keys) {
        if (coreData && contentStorage && sheetModel) return;
        try { const v = obj[k]; if (v && typeof v === 'object' && typeof v !== 'function') scanObj(v, depth + 1, path + '.' + k); } catch (e) {}
      }
    }
    function dfs(f, depth) {
      if (!f || fiberVisited.has(f) || depth > 25) return;
      fiberVisited.add(f);
      try { if (f.memoizedProps) scanObj(f.memoizedProps, 0, 'props'); } catch (e) {}
      try { const sn = f.stateNode; if (sn && typeof sn === 'object' && !sn.tagName) { scanObj(sn, 0, 'sn'); if (sn.props) scanObj(sn.props, 0, 'sn.props'); if (sn.state) scanObj(sn.state, 0, 'sn.state'); } } catch (e) {}
      dfs(f.child, depth + 1); dfs(f.sibling, depth + 1);
      let eff = f.firstEffect;
      while (eff) { if (!fiberVisited.has(eff)) { fiberVisited.add(eff); try { if (eff.memoizedProps) scanObj(eff.memoizedProps, 0, 'eff.props'); if (eff.stateNode && typeof eff.stateNode === 'object' && !eff.stateNode.tagName) { scanObj(eff.stateNode, 0, 'eff.sn'); if (eff.stateNode.props) scanObj(eff.stateNode.props, 0, 'eff.sn.props'); } } catch (e) {} } eff = eff.nextEffect; }
    }
    dfs(rootFiber, 0);
    out.fiberScanned = fiberVisited.size;

    if (coreData) {
      window.__coreData = coreData;
      out.found = true;
      // dump coreData 结构
      out.cdKeys = Object.keys(coreData);
      out.cdConstructor = coreData.constructor ? coreData.constructor.name : '?';
      // coreData 方法（含原型链）
      out.cdMethods = [];
      let p = coreData;
      while (p && p !== Object.prototype && out.cdMethods.length < 300) {
        try { for (const k of Object.getOwnPropertyNames(p)) { if (typeof coreData[k] === 'function' && !out.cdMethods.includes(k) && k !== 'constructor') out.cdMethods.push(k); } } catch (e) { break; }
        p = Object.getPrototypeOf(p);
      }
      // coreData 每个属性的结构
      out.cdProps = {};
      for (const k of out.cdKeys) {
        try {
          const v = coreData[k];
          if (v === null || v === undefined) { out.cdProps[k] = String(v); continue; }
          if (typeof v === 'function') { out.cdProps[k] = 'function'; continue; }
          if (typeof v === 'object') {
            const vkeys = Object.keys(v);
            out.cdProps[k] = { type: Array.isArray(v) ? 'array(' + v.length + ')' : 'obj(' + vkeys.length + ')', keys: vkeys.slice(0, 25) };
          } else { out.cdProps[k] = String(v).substring(0, 100); }
        } catch (e) { out.cdProps[k] = 'err'; }
      }
    }
    if (contentStorage) { window.__cs = contentStorage; out.csKeys = Object.keys(contentStorage); }
    if (sheetModel) { window.__sm = sheetModel; }
    return out;
  });

  console.log('扫描fiber:', probe.fiberScanned);
  if (probe.error) { console.log('错误:', probe.error); await context.close(); return; }
  console.log('coreData路径:', probe.coreDataPath);
  console.log('contentStorage路径:', probe.csiPath);
  console.log('sheetModel路径:', probe.sheetModelPath);
  if (probe.sheetModelMethods) console.log('sheetModel方法:', probe.sheetModelMethods);

  if (probe.found) {
    console.log('\n=== coreData 数据中心 ===');
    console.log('构造函数:', probe.cdConstructor);
    console.log('keys(' + probe.cdKeys.length + '):', probe.cdKeys.join(', '));
    console.log('方法(' + probe.cdMethods.length + '):', probe.cdMethods.join(', '));
    console.log('\n属性结构:');
    for (const [k, v] of Object.entries(probe.cdProps)) {
      console.log('  ' + k + ':', JSON.stringify(v).substring(0, 200));
    }
    fs.writeFileSync(path.join(OUTPUT_DIR, 'coredata_probe.json'), JSON.stringify(probe, null, 2), 'utf-8');

    // 探测 coreData.file（可能含表格数据）
    console.log('\n=== 深入探测 coreData.file ===');
    const fileProbe = await page.evaluate(() => {
      const cd = window.__coreData;
      if (!cd || !cd.file) return { error: '无file' };
      const f = cd.file;
      const out = { keys: Object.keys(f), constructor: f.constructor ? f.constructor.name : '?' };
      out.methods = [];
      let p = f;
      while (p && p !== Object.prototype && out.methods.length < 200) {
        try { for (const k of Object.getOwnPropertyNames(p)) { if (typeof f[k] === 'function' && !out.methods.includes(k) && k !== 'constructor') out.methods.push(k); } } catch (e) { break; }
        p = Object.getPrototypeOf(p);
      }
      // 每个属性
      out.props = {};
      for (const k of out.keys) {
        try {
          const v = f[k];
          if (v === null || v === undefined) { out.props[k] = String(v); continue; }
          if (typeof v === 'function') { out.props[k] = 'function'; continue; }
          if (typeof v === 'object') {
            const vk = Object.keys(v);
            out.props[k] = { type: Array.isArray(v) ? 'array(' + v.length + ')' : 'obj(' + vk.length + ')', keys: vk.slice(0, 20), preview: JSON.stringify(v).substring(0, 200) };
          } else { out.props[k] = String(v).substring(0, 100); }
        } catch (e) {}
      }
      return out;
    });
    console.log('file构造函数:', fileProbe.constructor);
    console.log('file keys:', fileProbe.keys.join(', '));
    console.log('file方法:', (fileProbe.methods || []).join(', '));
    console.log('file属性:');
    for (const [k, v] of Object.entries(fileProbe.props || {})) {
      console.log('  ' + k + ':', JSON.stringify(v).substring(0, 200));
    }
    fs.writeFileSync(path.join(OUTPUT_DIR, 'coredata_file_probe.json'), JSON.stringify(fileProbe, null, 2), 'utf-8');
  }

  console.log('\n完成');
  await page.waitForTimeout(3000);
  await context.close();
})().catch(e => { console.error('脚本错误:', e); process.exit(1); });
