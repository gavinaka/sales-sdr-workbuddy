// 石墨文档 - 增强查找文件管理器（遍历effect链+递归对象）+ getContent
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
  await page.waitForTimeout(12000);

  // 递归扫描对象属性找含 getContent 的对象（遍历effect链+对象属性）
  const probe = await page.evaluate(() => {
    const out = { found: false };
    const root = document.querySelector('#root');
    const fk = Object.keys(root).find(k => k.startsWith('__react'));
    const hostRoot = root[fk].current;
    const fiberVisited = new Set();
    const objVisited = new WeakSet();
    let found = null;

    // 递归扫描对象，找含getContent的
    function scanObj(obj, depth, path) {
      if (!obj || typeof obj !== 'object' || depth > 5 || found) return;
      if (objVisited.has(obj)) return;
      try { objVisited.add(obj); } catch (e) { return; }
      // 检查是否是目标
      try {
        if (typeof obj.getContent === 'function' && typeof obj.subscribeContentChange === 'function') {
          found = obj;
          out.path = path;
          return;
        }
      } catch (e) {}
      // 遍历属性
      let keys;
      try { keys = Object.keys(obj); } catch (e) { return; }
      for (const k of keys) {
        if (found) return;
        try {
          const v = obj[k];
          if (v && typeof v === 'object' && typeof v !== 'function') {
            scanObj(v, depth + 1, path + '.' + k);
          }
        } catch (e) {}
      }
    }

    // DFS遍历fiber（child/sibling + effect链）
    function dfs(f, depth) {
      if (!f || fiberVisited.has(f) || depth > 25 || found) return;
      fiberVisited.add(f);
      // 扫描 memoizedProps
      try {
        if (f.memoizedProps && typeof f.memoizedProps === 'object') {
          scanObj(f.memoizedProps, 0, 'props@fiber' + depth);
        }
      } catch (e) {}
      // 扫描 stateNode（类实例）
      try {
        const sn = f.stateNode;
        if (sn && typeof sn === 'object' && !sn.tagName && !sn.nodeType) {
          scanObj(sn, 0, 'stateNode@fiber' + depth);
          // 类实例的props也可能持有
          if (sn.props && typeof sn.props === 'object') scanObj(sn.props, 0, 'stateNode.props@fiber' + depth);
        }
      } catch (e) {}

      if (found) return;
      dfs(f.child, depth + 1);
      if (found) return;
      dfs(f.sibling, depth + 1);
      if (found) return;
      // 遍历 effect 链
      let eff = f.firstEffect;
      while (eff && !found) {
        if (!fiberVisited.has(eff)) {
          fiberVisited.add(eff);
          try {
            if (eff.memoizedProps && typeof eff.memoizedProps === 'object') scanObj(eff.memoizedProps, 0, 'effect.props@fiber' + depth);
            if (eff.stateNode && typeof eff.stateNode === 'object' && !eff.stateNode.tagName) {
              scanObj(eff.stateNode, 0, 'effect.stateNode@fiber' + depth);
              if (eff.stateNode.props) scanObj(eff.stateNode.props, 0, 'effect.stateNode.props@fiber' + depth);
            }
          } catch (e) {}
        }
        eff = eff.nextEffect;
      }
    }
    dfs(hostRoot, 0);
    out.fiberScanned = fiberVisited.size;

    if (!found) return out;

    out.found = true;
    window.__fm = found;

    // dump方法
    out.fmMethods = [];
    let p = found;
    while (p && p !== Object.prototype && out.fmMethods.length < 200) {
      try { for (const k of Object.getOwnPropertyNames(p)) { if (typeof found[k] === 'function' && !out.fmMethods.includes(k) && k !== 'constructor') out.fmMethods.push(k); } } catch (e) { break; }
      p = Object.getPrototypeOf(p);
    }
    out.fmKeys = Object.keys(found);
    out.fmConstructor = found.constructor ? found.constructor.name : '?';

    // 关键属性
    for (const k of ['guid', 'sheetId', 'file', 'checkpoint', 'config', 'fileDataManager', 'sos2File']) {
      try {
        const v = found[k];
        if (v === undefined || v === null) continue;
        if (typeof v === 'object') {
          out['fm.' + k] = { keyCount: Object.keys(v).length, keys: Object.keys(v).slice(0, 20), preview: JSON.stringify(v).substring(0, 300) };
        } else { out['fm.' + k] = String(v).substring(0, 150); }
      } catch (e) {}
    }

    // fileDataManager
    if (found.fileDataManager) {
      window.__fdm = found.fileDataManager;
      const fdm = found.fileDataManager;
      out.fdmMethods = [];
      let pp = fdm;
      while (pp && pp !== Object.prototype && out.fdmMethods.length < 250) {
        try { for (const k of Object.getOwnPropertyNames(pp)) { if (typeof fdm[k] === 'function' && !out.fdmMethods.includes(k) && k !== 'constructor') out.fdmMethods.push(k); } } catch (e) { break; }
        pp = Object.getPrototypeOf(pp);
      }
      out.fdmKeys = Object.keys(fdm);
      out.fdmConstructor = fdm.constructor ? fdm.constructor.name : '?';
      for (const k of out.fdmKeys.slice(0, 40)) {
        try {
          const v = fdm[k];
          if (v === null || v === undefined) { out['fdm.' + k] = String(v); continue; }
          if (typeof v === 'function') continue;
          if (typeof v === 'object') {
            out['fdm.' + k] = { type: Array.isArray(v) ? 'array(' + v.length + ')' : 'obj', keyCount: Object.keys(v).length, keys: Object.keys(v).slice(0, 15) };
          } else { out['fdm.' + k] = String(v).substring(0, 100); }
        } catch (e) {}
      }
    }
    return out;
  });

  console.log('扫描fiber数:', probe.fiberScanned);
  if (!probe.found) {
    console.log('未找到！path:', probe.path);
    // 重试：再等5秒
    console.log('等待5秒后重试...');
    await page.waitForTimeout(5000);
    const probe2 = await page.evaluate(() => {
      const root = document.querySelector('#root');
      const fk = Object.keys(root).find(k => k.startsWith('__react'));
      const hostRoot = root[fk].current;
      const fiberVisited = new Set();
      const objVisited = new WeakSet();
      let found = null;
      function scanObj(obj, depth) {
        if (!obj || typeof obj !== 'object' || depth > 6 || found) return;
        try { if (objVisited.has(obj)) return; objVisited.add(obj); } catch (e) { return; }
        try { if (typeof obj.getContent === 'function' && typeof obj.subscribeContentChange === 'function') { found = obj; return; } } catch (e) {}
        let keys; try { keys = Object.keys(obj); } catch (e) { return; }
        for (const k of keys) { if (found) return; try { const v = obj[k]; if (v && typeof v === 'object') scanObj(v, depth + 1); } catch (e) {} }
      }
      function dfs(f, depth) {
        if (!f || fiberVisited.has(f) || depth > 25 || found) return;
        fiberVisited.add(f);
        try { if (f.memoizedProps) scanObj(f.memoizedProps, 0); } catch (e) {}
        try { if (f.stateNode && typeof f.stateNode === 'object' && !f.stateNode.tagName) { scanObj(f.stateNode, 0); if (f.stateNode.props) scanObj(f.stateNode.props, 0); } } catch (e) {}
        if (found) return;
        dfs(f.child, depth + 1); if (found) return; dfs(f.sibling, depth + 1); if (found) return;
        let eff = f.firstEffect;
        while (eff && !found) { if (!fiberVisited.has(eff)) { fiberVisited.add(eff); try { if (eff.memoizedProps) scanObj(eff.memoizedProps, 0); if (eff.stateNode && !eff.stateNode.tagName) { scanObj(eff.stateNode, 0); if (eff.stateNode.props) scanObj(eff.stateNode.props, 0); } } catch (e) {} } eff = eff.nextEffect; }
      }
      dfs(hostRoot, 0);
      if (!found) return { found: false, fiberScanned: fiberVisited.size };
      window.__fm = found;
      return { found: true, path: 'retry' };
    });
    console.log('重试结果:', JSON.stringify(probe2));
    if (!probe2.found) { await context.close(); return; }
    // 重新探测结构
    const reprobe = await page.evaluate(() => {
      const found = window.__fm;
      const out = { fmMethods: [], fmKeys: Object.keys(found), fmConstructor: found.constructor ? found.constructor.name : '?' };
      let p = found;
      while (p && p !== Object.prototype && out.fmMethods.length < 200) { try { for (const k of Object.getOwnPropertyNames(p)) { if (typeof found[k] === 'function' && !out.fmMethods.includes(k) && k !== 'constructor') out.fmMethods.push(k); } } catch (e) { break; } p = Object.getPrototypeOf(p); }
      if (found.fileDataManager) { window.__fdm = found.fileDataManager; const fdm = found.fileDataManager; out.fdmMethods = []; let pp = fdm; while (pp && pp !== Object.prototype && out.fdmMethods.length < 250) { try { for (const k of Object.getOwnPropertyNames(pp)) { if (typeof fdm[k] === 'function' && !out.fdmMethods.includes(k) && k !== 'constructor') out.fdmMethods.push(k); } } catch (e) { break; } pp = Object.getPrototypeOf(pp); } out.fdmKeys = Object.keys(fdm); out.fdmConstructor = fdm.constructor ? fdm.constructor.name : '?'; }
      return out;
    });
    Object.assign(probe, reprobe);
  }

  if (probe.found || probe.fmMethods) {
    console.log('\n找到文件管理器！path:', probe.path);
    console.log('构造函数:', probe.fmConstructor);
    console.log('FM方法(' + (probe.fmMethods ? probe.fmMethods.length : 0) + '):', (probe.fmMethods || []).join(', '));
    console.log('FM keys:', probe.fmKeys.join(', '));
    if (probe.fdmMethods) {
      console.log('\n=== fileDataManager ===');
      console.log('构造函数:', probe.fdmConstructor);
      console.log('FDM方法(' + probe.fdmMethods.length + '):', probe.fdmMethods.join(', '));
      console.log('FDM keys:', probe.fdmKeys.join(', '));
    }
    fs.writeFileSync(path.join(OUTPUT_DIR, 'filemanager_probe2.json'), JSON.stringify(probe, null, 2), 'utf-8');

    // ========== 调用 getContent ==========
    console.log('\n=== 调用 getContent() ===');
    const contentResult = await page.evaluate(async () => {
      const fm = window.__fm;
      if (!fm) return { error: '无fm' };
      const out = {};
      try {
        const r = await fm.getContent();
        out.getContent = {
          type: typeof r, isArray: Array.isArray(r),
          keys: r && typeof r === 'object' ? Object.keys(r).slice(0, 30) : null,
          strLen: JSON.stringify(r).length,
          preview: JSON.stringify(r).substring(0, 2000)
        };
      } catch (e) { out.getContentError = e.message; }
      return out;
    });
    if (contentResult.getContent) {
      const c = contentResult.getContent;
      console.log('getContent: type=' + c.type + ' strLen=' + c.strLen + ' keys=' + JSON.stringify(c.keys));
      console.log('preview:', c.preview.substring(0, 1000));
    } else console.log('getContent错误:', contentResult.getContentError);
    fs.writeFileSync(path.join(OUTPUT_DIR, 'content_result2.json'), JSON.stringify(contentResult, null, 2), 'utf-8');

    // 保存完整数据
    if (contentResult.getContent && contentResult.getContent.strLen > 0) {
      console.log('\n保存完整 getContent 数据...');
      const full = await page.evaluate(async () => { try { return await window.__fm.getContent(); } catch (e) { return { error: e.message }; } });
      fs.writeFileSync(path.join(DATA_OUTPUT, 'getContent_full.json'), JSON.stringify(full, null, 2), 'utf-8');
      console.log('已保存 getContent_full.json, 大小:', JSON.stringify(full).length);
    }
  }

  console.log('\n完成');
  await page.waitForTimeout(3000);
  await context.close();
})().catch(e => { console.error('脚本错误:', e); process.exit(1); });
