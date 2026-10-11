// 石墨文档 - 稳健版：从.spreadsheet-view fiber入口 + 等待渲染 + getContent
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
  // 等待sheet标签渲染完成（React树就绪的标志）
  console.log('等待sheet标签渲染...');
  try {
    await page.waitForSelector('.sm-sheet-tab-item', { timeout: 30000 });
    console.log('sheet标签已出现');
  } catch (e) { console.log('等待sheet标签超时，继续'); }
  await page.waitForTimeout(5000);  // 额外等待数据加载

  // 用 .spreadsheet-view 作为fiber入口（稳健）
  const probe = await page.evaluate(() => {
    const out = { found: false };
    // 入口：尝试多个元素
    const entries = [
      document.querySelector('.spreadsheet-view'),
      document.querySelector('.sm-sheet-wrapper'),
      document.querySelector('.sm-sheet-editor-wrap'),
      document.querySelector('.sm-sheet-tab-item'),
      document.querySelector('#root')
    ];
    let entryFiber = null;
    let entryInfo = [];
    for (const el of entries) {
      if (!el) { entryInfo.push({ el: '缺失' }); continue; }
      const fk = Object.keys(el).find(k => k.startsWith('__react'));
      entryInfo.push({ tag: el.tagName, cls: (el.className || '').substring(0, 30), hasFiber: !!fk, fiberKey: fk });
      if (fk && !entryFiber) entryFiber = el[fk];
    }
    out.entryInfo = entryInfo;
    if (!entryFiber) { out.error = '无任何fiber入口'; return out; }

    // 向上return到根
    let rootFiber = entryFiber;
    let upN = 0;
    while (rootFiber && rootFiber.return && upN < 50) { rootFiber = rootFiber.return; upN++; }
    out.upSteps = upN;
    out.rootTag = rootFiber.tag;
    // 如果是FiberRoot(tag=3)，用current
    if (rootFiber.tag === 3 && rootFiber.current) rootFiber = rootFiber.current;
    out.actualRootTag = rootFiber.tag;

    const fiberVisited = new Set();
    const objVisited = new WeakSet();
    let found = null;
    let objScanCount = 0;

    function scanObj(obj, depth, path) {
      if (!obj || typeof obj !== 'object' || depth > 6 || found) return;
      try { if (objVisited.has(obj)) return; objVisited.add(obj); } catch (e) { return; }
      objScanCount++;
      try {
        if (typeof obj.getContent === 'function' && typeof obj.subscribeContentChange === 'function') {
          found = obj; out.path = path; return;
        }
      } catch (e) {}
      let keys; try { keys = Object.keys(obj); } catch (e) { return; }
      for (const k of keys) {
        if (found) return;
        try {
          const v = obj[k];
          if (v && typeof v === 'object' && typeof v !== 'function') scanObj(v, depth + 1, path + '.' + k);
        } catch (e) {}
      }
    }

    function dfs(f, depth) {
      if (!f || fiberVisited.has(f) || depth > 25 || found) return;
      fiberVisited.add(f);
      try { if (f.memoizedProps) scanObj(f.memoizedProps, 0, 'props@f' + depth); } catch (e) {}
      try {
        const sn = f.stateNode;
        if (sn && typeof sn === 'object' && !sn.tagName && !sn.nodeType) {
          scanObj(sn, 0, 'stateNode@f' + depth);
          if (sn.props) scanObj(sn.props, 0, 'sn.props@f' + depth);
          if (sn.state) scanObj(sn.state, 0, 'sn.state@f' + depth);
        }
      } catch (e) {}
      if (found) return;
      dfs(f.child, depth + 1);
      if (found) return;
      dfs(f.sibling, depth + 1);
      if (found) return;
      let eff = f.firstEffect;
      while (eff && !found) {
        if (!fiberVisited.has(eff)) {
          fiberVisited.add(eff);
          try {
            if (eff.memoizedProps) scanObj(eff.memoizedProps, 0, 'eff.props@f' + depth);
            if (eff.stateNode && typeof eff.stateNode === 'object' && !eff.stateNode.tagName) {
              scanObj(eff.stateNode, 0, 'eff.stateNode@f' + depth);
              if (eff.stateNode.props) scanObj(eff.stateNode.props, 0, 'eff.sn.props@f' + depth);
            }
          } catch (e) {}
        }
        eff = eff.nextEffect;
      }
    }
    dfs(rootFiber, 0);
    out.fiberScanned = fiberVisited.size;
    out.objScanned = objScanCount;

    if (!found) return out;
    out.found = true;
    window.__fm = found;

    // dump FM方法
    out.fmMethods = [];
    let p = found;
    while (p && p !== Object.prototype && out.fmMethods.length < 200) {
      try { for (const k of Object.getOwnPropertyNames(p)) { if (typeof found[k] === 'function' && !out.fmMethods.includes(k) && k !== 'constructor') out.fmMethods.push(k); } } catch (e) { break; }
      p = Object.getPrototypeOf(p);
    }
    out.fmKeys = Object.keys(found);
    out.fmConstructor = found.constructor ? found.constructor.name : '?';

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
    }
    return out;
  });

  console.log('入口诊断:', JSON.stringify(probe.entryInfo));
  console.log('向上步数:', probe.upSteps, 'rootTag:', probe.rootTag, 'actualRootTag:', probe.actualRootTag);
  console.log('扫描fiber:', probe.fiberScanned, '扫描对象:', probe.objScanned);
  if (probe.error) { console.log('错误:', probe.error); await context.close(); return; }
  if (!probe.found) { console.log('未找到文件管理器'); fs.writeFileSync(path.join(OUTPUT_DIR, 'probe_v3.json'), JSON.stringify(probe, null, 2), 'utf-8'); await context.close(); return; }

  console.log('\n=== 找到文件管理器！===');
  console.log('path:', probe.path);
  console.log('构造函数:', probe.fmConstructor);
  console.log('FM方法(' + probe.fmMethods.length + '):', probe.fmMethods.join(', '));
  console.log('FM keys:', probe.fmKeys.join(', '));
  if (probe.fdmMethods) {
    console.log('\nfileDataManager(' + probe.fdmConstructor + '):');
    console.log('FDM方法(' + probe.fdmMethods.length + '):', probe.fdmMethods.join(', '));
    console.log('FDM keys:', probe.fdmKeys.join(', '));
  }
  fs.writeFileSync(path.join(OUTPUT_DIR, 'filemanager_probe3.json'), JSON.stringify(probe, null, 2), 'utf-8');

  // ========== 调用 getContent + getRemoteContent ==========
  console.log('\n=== 调用 getContent / getRemoteContent ===');
  const contentResult = await page.evaluate(async () => {
    const fm = window.__fm;
    const out = {};
    // getContent
    try {
      const r = await fm.getContent();
      out.getContent = { type: typeof r, isArray: Array.isArray(r), keys: r && typeof r === 'object' ? Object.keys(r).slice(0, 40) : null, strLen: JSON.stringify(r).length, preview: JSON.stringify(r).substring(0, 3000) };
    } catch (e) { out.getContentError = e.message; }
    // getRemoteContent
    try {
      const r = await fm.getRemoteContent();
      out.getRemoteContent = { type: typeof r, isArray: Array.isArray(r), keys: r && typeof r === 'object' ? Object.keys(r).slice(0, 40) : null, strLen: JSON.stringify(r).length, preview: JSON.stringify(r).substring(0, 3000) };
    } catch (e) { out.getRemoteContentError = e.message; }
    return out;
  });
  if (contentResult.getContent) {
    const c = contentResult.getContent;
    console.log('getContent: type=' + c.type + ' strLen=' + c.strLen + ' keys=' + JSON.stringify(c.keys));
    console.log('  preview:', c.preview.substring(0, 1500));
  } else console.log('getContent错误:', contentResult.getContentError);
  if (contentResult.getRemoteContent) {
    const c = contentResult.getRemoteContent;
    console.log('\ngetRemoteContent: type=' + c.type + ' strLen=' + c.strLen + ' keys=' + JSON.stringify(c.keys));
    console.log('  preview:', c.preview.substring(0, 1500));
  } else console.log('getRemoteContent错误:', contentResult.getRemoteContentError);
  fs.writeFileSync(path.join(OUTPUT_DIR, 'content_result3.json'), JSON.stringify(contentResult, null, 2), 'utf-8');

  // 保存完整数据
  const which = contentResult.getContent ? 'getContent' : (contentResult.getRemoteContent ? 'getRemoteContent' : null);
  if (which) {
    console.log('\n=== 保存完整 ' + which + ' 数据 ===');
    const full = await page.evaluate(async (w) => {
      try { return w === 'getContent' ? await window.__fm.getContent() : await window.__fm.getRemoteContent(); } catch (e) { return { error: e.message }; }
    }, which);
    fs.writeFileSync(path.join(DATA_OUTPUT, which + '_full.json'), JSON.stringify(full, null, 2), 'utf-8');
    console.log('已保存 ' + which + '_full.json, 大小:', JSON.stringify(full).length, '字符');
  }

  console.log('\n完成');
  await page.waitForTimeout(3000);
  await context.close();
})().catch(e => { console.error('脚本错误:', e); process.exit(1); });
