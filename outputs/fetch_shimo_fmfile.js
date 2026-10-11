// 石墨文档 - 探测FM.file结构 + 尝试initContentStorage/getContent + 找数据模型
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

function dumpMethods(obj) {
  const methods = [];
  let p = obj;
  while (p && p !== Object.prototype && methods.length < 300) {
    try { for (const k of Object.getOwnPropertyNames(p)) { if (typeof obj[k] === 'function' && !methods.includes(k) && k !== 'constructor') methods.push(k); } } catch (e) { break; }
    p = Object.getPrototypeOf(p);
  }
  return methods;
}

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

  // 找 FM (contentStorageInstance)
  const probe = await page.evaluate(() => {
    const out = {};
    const entries = [document.querySelector('.spreadsheet-view'), document.querySelector('.sm-sheet-wrapper'), document.querySelector('#root')];
    let entryFiber = null;
    for (const el of entries) { if (!el) continue; const fk = Object.keys(el).find(k => k.startsWith('__react')); if (fk) { entryFiber = el[fk]; break; } }
    if (!entryFiber) { out.error = '无fiber入口'; return out; }
    let rootFiber = entryFiber;
    while (rootFiber && rootFiber.return) rootFiber = rootFiber.return;
    if (rootFiber.tag === 3 && rootFiber.current) rootFiber = rootFiber.current;

    const fiberVisited = new Set();
    const objVisited = new WeakSet();
    let fm = null;
    let dataModel = null;  // 含 getSheet/getCell 的对象
    let bigDataObj = null;  // 含大量数据的对象

    function scanObj(obj, depth, path) {
      if (!obj || typeof obj !== 'object' || depth > 7 || (fm && dataModel)) return;
      try { if (objVisited.has(obj)) return; objVisited.add(obj); } catch (e) { return; }
      // 找 FM
      try {
        if (!fm && typeof obj.getContent === 'function' && typeof obj.subscribeContentChange === 'function') {
          fm = obj; out.fmPath = path;
        }
      } catch (e) {}
      // 找数据模型（含getSheet/getCell/getModel/getAllSheet等）
      try {
        if (!dataModel) {
          const ks = Object.keys(obj);
          if (ks.length > 3) {
            const ms = ks.filter(k => typeof obj[k] === 'function');
            const dataMs = ms.filter(m => /getSheet|getCell|getModel|getAllSheet|getWorkbook|getSheetData|getCellData|getSheetList|getRows|getColumns|getCellRange|getAllCells|exportData|toJSON|serialize|getSheetById|getSheetNames/i.test(m));
            if (dataMs.length >= 2) { dataModel = obj; out.dataModelPath = path; out.dataModelMethods = dataMs; }
          }
        }
      } catch (e) {}
      let keys; try { keys = Object.keys(obj); } catch (e) { return; }
      for (const k of keys) {
        if (fm && dataModel) return;
        try { const v = obj[k]; if (v && typeof v === 'object' && typeof v !== 'function') scanObj(v, depth + 1, path + '.' + k); } catch (e) {}
      }
    }
    function dfs(f, depth) {
      if (!f || fiberVisited.has(f) || depth > 25 || (fm && dataModel)) return;
      fiberVisited.add(f);
      try { if (f.memoizedProps) scanObj(f.memoizedProps, 0, 'props'); } catch (e) {}
      try { const sn = f.stateNode; if (sn && typeof sn === 'object' && !sn.tagName) { scanObj(sn, 0, 'sn'); if (sn.props) scanObj(sn.props, 0, 'sn.props'); if (sn.state) scanObj(sn.state, 0, 'sn.state'); } } catch (e) {}
      dfs(f.child, depth + 1); dfs(f.sibling, depth + 1);
      let eff = f.firstEffect;
      while (eff) { if (!fiberVisited.has(eff)) { fiberVisited.add(eff); try { if (eff.memoizedProps) scanObj(eff.memoizedProps, 0, 'eff.props'); if (eff.stateNode && typeof eff.stateNode === 'object' && !eff.stateNode.tagName) { scanObj(eff.stateNode, 0, 'eff.sn'); if (eff.stateNode.props) scanObj(eff.stateNode.props, 0, 'eff.sn.props'); } } catch (e) {} } eff = eff.nextEffect; }
    }
    dfs(rootFiber, 0);
    out.fiberScanned = fiberVisited.size;
    if (fm) window.__fm = fm;
    if (dataModel) window.__dm = dataModel;
    return out;
  });

  console.log('扫描fiber:', probe.fiberScanned);
  if (probe.error) { console.log('错误:', probe.error); await context.close(); return; }
  console.log('FM路径:', probe.fmPath);
  console.log('数据模型路径:', probe.dataModelPath);
  if (probe.dataModelMethods) console.log('数据模型方法:', probe.dataModelMethods);

  // ========== 探测 FM.file 深度结构 ==========
  if (probe.fmPath) {
    console.log('\n=== FM.file 深度探测 ===');
    const fileDeep = await page.evaluate(() => {
      const fm = window.__fm;
      if (!fm) return { error: '无fm' };
      const out = { fmKeys: Object.keys(fm) };
      // 探测 fm.file
      if (fm.file) {
        const f = fm.file;
        out.fileKeys = Object.keys(f);
        out.fileConstructor = f.constructor ? f.constructor.name : '?';
        out.fileMethods = dumpMethods(f);
        // 每个属性
        out.fileProps = {};
        for (const k of out.fileKeys) {
          try {
            const v = f[k];
            if (v === null || v === undefined) { out.fileProps[k] = String(v); continue; }
            if (typeof v === 'function') { out.fileProps[k] = 'function'; continue; }
            if (typeof v === 'object') {
              const vk = Object.keys(v);
              out.fileProps[k] = { type: Array.isArray(v) ? 'array(' + v.length + ')' : 'obj(' + vk.length + ')', keys: vk.slice(0, 25), preview: JSON.stringify(v).substring(0, 300) };
            } else { out.fileProps[k] = String(v).substring(0, 150); }
          } catch (e) { out.fileProps[k] = 'err'; }
        }
        // 如果 file 有 dataModel/model/sheets/cells 属性，深入
        for (const dk of ['dataModel', 'model', 'sheets', 'cells', 'content', 'workbook', 'spreadsheet', 'snapshot', 'data']) {
          if (f[dk] && typeof f[dk] === 'object') {
            const dm = f[dk];
            out['file.' + dk] = { keys: Object.keys(dm).slice(0, 30), methods: dumpMethods(dm).slice(0, 50), constructor: dm.constructor ? dm.constructor.name : '?', keyCount: Object.keys(dm).length };
          }
        }
      }
      // 探测 fm.config
      if (fm.config) {
        out.configKeys = Object.keys(fm.config);
        out.configPreview = JSON.stringify(fm.config).substring(0, 500);
      }
      // 探测 fm.checkpoint
      if (fm.checkpoint) {
        out.checkpointKeys = Object.keys(fm.checkpoint);
        out.checkpointPreview = JSON.stringify(fm.checkpoint).substring(0, 300);
      }
      function dumpMethods(obj) {
        const m = []; let p = obj;
        while (p && p !== Object.prototype && m.length < 200) { try { for (const k of Object.getOwnPropertyNames(p)) { if (typeof obj[k] === 'function' && !m.includes(k) && k !== 'constructor') m.push(k); } } catch (e) { break; } p = Object.getPrototypeOf(p); }
        return m;
      }
      return out;
    });
    console.log('FM keys:', fileDeep.fmKeys.join(', '));
    console.log('\nfile构造函数:', fileDeep.fileConstructor);
    console.log('file keys:', (fileDeep.fileKeys || []).join(', '));
    console.log('file方法:', (fileDeep.fileMethods || []).join(', '));
    console.log('\nfile属性:');
    for (const [k, v] of Object.entries(fileDeep.fileProps || {})) {
      console.log('  ' + k + ':', JSON.stringify(v).substring(0, 200));
    }
    for (const k of Object.keys(fileDeep).filter(k => k.startsWith('file.'))) {
      console.log('  ' + k + ':', JSON.stringify(fileDeep[k]).substring(0, 250));
    }
    if (fileDeep.configKeys) { console.log('\nconfig:', fileDeep.configKeys.join(','), fileDeep.configPreview); }
    if (fileDeep.checkpointKeys) { console.log('checkpoint:', fileDeep.checkpointKeys.join(','), fileDeep.checkpointPreview); }
    fs.writeFileSync(path.join(OUTPUT_DIR, 'fm_file_deep.json'), JSON.stringify(fileDeep, null, 2), 'utf-8');
  }

  // ========== 尝试 initContentStorage + getContent ==========
  console.log('\n=== 尝试 initContentStorage + getContent ===');
  const initResult = await page.evaluate(async () => {
    const fm = window.__fm;
    if (!fm) return { error: '无fm' };
    const out = {};
    // 尝试无参 initContentStorage
    try {
      const r = await fm.initContentStorage();
      out.initNoArg = { type: typeof r, value: r ? JSON.stringify(r).substring(0, 200) : String(r) };
    } catch (e) { out.initNoArgError = e.message; }
    // 尝试 getContent
    try {
      const r = await fm.getContent();
      out.getContent = { type: typeof r, keys: r && typeof r === 'object' ? Object.keys(r).slice(0, 30) : null, strLen: JSON.stringify(r).length, preview: JSON.stringify(r).substring(0, 2000) };
    } catch (e) { out.getContentError = e.message; }
    // 现在 fileDataManager 应该存在了，探测它
    if (fm.fileDataManager) {
      window.__fdm = fm.fileDataManager;
      const fdm = fm.fileDataManager;
      out.fdmKeys = Object.keys(fdm);
      out.fdmMethods = [];
      let p = fdm;
      while (p && p !== Object.prototype && out.fdmMethods.length < 250) { try { for (const k of Object.getOwnPropertyNames(p)) { if (typeof fdm[k] === 'function' && !out.fdmMethods.includes(k) && k !== 'constructor') out.fdmMethods.push(k); } } catch (e) { break; } p = Object.getPrototypeOf(p); }
      out.fdmConstructor = fdm.constructor ? fdm.constructor.name : '?';
    }
    return out;
  });
  console.log('initContentStorage:', JSON.stringify(initResult.initNoArg || initResult.initNoArgError));
  console.log('getContent:', initResult.getContent ? ('type=' + initResult.getContent.type + ' strLen=' + initResult.getContent.strLen + ' keys=' + JSON.stringify(initResult.getContent.keys)) : initResult.getContentError);
  if (initResult.getContent) console.log('  preview:', initResult.getContent.preview.substring(0, 1000));
  if (initResult.fdmMethods) {
    console.log('\nfileDataManager(' + initResult.fdmConstructor + ')方法(' + initResult.fdmMethods.length + '):', initResult.fdmMethods.join(', '));
    console.log('fdm keys:', initResult.fdmKeys.join(', '));
  }
  fs.writeFileSync(path.join(OUTPUT_DIR, 'init_result.json'), JSON.stringify(initResult, null, 2), 'utf-8');

  // 如果getContent成功，保存完整数据
  if (initResult.getContent && initResult.getContent.strLen > 0) {
    console.log('\n=== 保存完整 getContent 数据 ===');
    const full = await page.evaluate(async () => { try { return await window.__fm.getContent(); } catch (e) { return { error: e.message }; } });
    fs.writeFileSync(path.join(DATA_OUTPUT, 'getContent_full.json'), JSON.stringify(full, null, 2), 'utf-8');
    console.log('已保存 getContent_full.json, 大小:', JSON.stringify(full).length);
  }

  console.log('\n完成');
  await page.waitForTimeout(3000);
  await context.close();
})().catch(e => { console.error('脚本错误:', e); process.exit(1); });
