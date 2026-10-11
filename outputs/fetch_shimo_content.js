// 石墨文档 - 定位文件管理器 + 探测fileDataManager + 调用getContent获取数据
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
  await page.waitForTimeout(10000);

  // ========== 1. 定位文件管理器 + 探测结构 ==========
  console.log('\n=== 1. 定位文件管理器并探测结构 ===');
  const probe = await page.evaluate(() => {
    const root = document.querySelector('#root');
    const fk = Object.keys(root).find(k => k.startsWith('__react'));
    const hostRoot = root[fk].current;
    let found = null;
    const visited = new Set();
    function dfs(f, depth) {
      if (!f || visited.has(f) || depth > 20 || found) return;
      visited.add(f);
      try {
        if (f.memoizedProps && typeof f.memoizedProps === 'object') {
          for (const k of Object.keys(f.memoizedProps)) {
            const v = f.memoizedProps[k];
            if (v && typeof v === 'object' && typeof v.getContent === 'function' && typeof v.initContentStorage === 'function') {
              found = v; return;
            }
          }
        }
      } catch (e) {}
      try {
        if (f.stateNode && typeof f.stateNode === 'object' && !f.stateNode.tagName && !f.stateNode.nodeType) {
          for (const k of Object.keys(f.stateNode)) {
            const v = f.stateNode[k];
            if (v && typeof v === 'object' && typeof v.getContent === 'function' && typeof v.initContentStorage === 'function') {
              found = v; return;
            }
          }
        }
      } catch (e) {}
      dfs(f.child, depth + 1); dfs(f.sibling, depth + 1);
    }
    dfs(hostRoot, 0);
    if (!found) return { error: '未找到文件管理器' };
    window.__fm = found;  // 存全局，后续用

    const out = { found: true };
    // 文件管理器的所有方法（含原型链）
    out.fmMethods = [];
    let p = found;
    while (p && p !== Object.prototype && out.fmMethods.length < 200) {
      try { for (const k of Object.getOwnPropertyNames(p)) { if (typeof found[k] === 'function' && !out.fmMethods.includes(k) && k !== 'constructor') out.fmMethods.push(k); } } catch (e) { break; }
      p = Object.getPrototypeOf(p);
    }
    out.fmKeys = Object.keys(found);

    // 探测关键属性
    for (const k of ['guid', 'sheetId', 'file', 'checkpoint', 'config', 'me', 'allowedStorage', 'sos2File', 'sos2User', 'team']) {
      try {
        const v = found[k];
        if (v === undefined || v === null) continue;
        if (typeof v === 'object') {
          const vkeys = Object.keys(v);
          out['fm.' + k] = { type: Array.isArray(v) ? 'array' : 'object', keyCount: vkeys.length, keys: vkeys.slice(0, 25), preview: JSON.stringify(v).substring(0, 400) };
        } else {
          out['fm.' + k] = String(v).substring(0, 200);
        }
      } catch (e) { out['fm.' + k] = 'error: ' + e.message; }
    }

    // 深入探测 fileDataManager（真正的数据持有者）
    if (found.fileDataManager) {
      const fdm = found.fileDataManager;
      window.__fdm = fdm;
      out.fdmMethods = [];
      let pp = fdm;
      while (pp && pp !== Object.prototype && out.fdmMethods.length < 250) {
        try { for (const k of Object.getOwnPropertyNames(pp)) { if (typeof fdm[k] === 'function' && !out.fdmMethods.includes(k) && k !== 'constructor') out.fdmMethods.push(k); } } catch (e) { break; }
        pp = Object.getPrototypeOf(pp);
      }
      out.fdmKeys = Object.keys(fdm);
      out.fdmConstructorName = fdm.constructor ? fdm.constructor.name : '?';
      // 探测fdm的属性
      for (const k of out.fdmKeys.slice(0, 30)) {
        try {
          const v = fdm[k];
          if (v === null || v === undefined) { out['fdm.' + k] = String(v); continue; }
          if (typeof v === 'function') continue;
          if (typeof v === 'object') {
            const vkeys = Object.keys(v);
            out['fdm.' + k] = { type: Array.isArray(v) ? 'array(len=' + v.length + ')' : 'object', keyCount: vkeys.length, keys: vkeys.slice(0, 20) };
          } else {
            out['fdm.' + k] = String(v).substring(0, 150);
          }
        } catch (e) {}
      }
    }
    return out;
  });

  if (probe.error) { console.log('错误:', probe.error); await context.close(); return; }
  console.log('找到文件管理器！');
  console.log('FM方法(' + probe.fmMethods.length + '):', probe.fmMethods.join(', '));
  console.log('FM keys:', probe.fmKeys.join(', '));
  console.log('\nFM关键属性:');
  for (const k of Object.keys(probe).filter(k => k.startsWith('fm.') && k !== 'fmMethods' && k !== 'fmKeys')) {
    console.log('  ' + k + ':', JSON.stringify(probe[k]).substring(0, 200));
  }
  if (probe.fdmMethods) {
    console.log('\n=== fileDataManager（数据持有者）===');
    console.log('构造函数:', probe.fdmConstructorName);
    console.log('FDM方法(' + probe.fdmMethods.length + '):', probe.fdmMethods.join(', '));
    console.log('FDM keys:', probe.fdmKeys.join(', '));
    console.log('FDM属性:');
    for (const k of Object.keys(probe).filter(k => k.startsWith('fdm.'))) {
      console.log('  ' + k + ':', JSON.stringify(probe[k]).substring(0, 200));
    }
  }
  fs.writeFileSync(path.join(OUTPUT_DIR, 'filemanager_probe.json'), JSON.stringify(probe, null, 2), 'utf-8');

  // ========== 2. 调用 getContent 获取内容 ==========
  console.log('\n=== 2. 调用 getContent() 获取内容 ===');
  const contentResult = await page.evaluate(async () => {
    const fm = window.__fm;
    if (!fm) return { error: '无fm' };
    const out = {};
    // 尝试 getContent（无参）
    try {
      const r = await fm.getContent();
      out.getContent = {
        type: typeof r,
        isArray: Array.isArray(r),
        keys: r && typeof r === 'object' ? Object.keys(r).slice(0, 30) : null,
        length: r && typeof r === 'object' ? Object.keys(r).length : null,
        strLen: JSON.stringify(r).length,
        preview: JSON.stringify(r).substring(0, 1500)
      };
    } catch (e) { out.getContentError = e.message; }

    // 尝试 getRemoteContent
    try {
      const r = await fm.getRemoteContent();
      out.getRemoteContent = {
        type: typeof r,
        isArray: Array.isArray(r),
        keys: r && typeof r === 'object' ? Object.keys(r).slice(0, 30) : null,
        strLen: JSON.stringify(r).length,
        preview: JSON.stringify(r).substring(0, 1500)
      };
    } catch (e) { out.getRemoteContentError = e.message; }

    return out;
  });
  console.log('getContent结果:');
  if (contentResult.getContent) {
    const c = contentResult.getContent;
    console.log('  type:', c.type, 'isArray:', c.isArray, 'keys:', c.keys, 'strLen:', c.strLen);
    console.log('  preview:', c.preview.substring(0, 800));
  } else console.log('  错误:', contentResult.getContentError);
  console.log('\ngetRemoteContent结果:');
  if (contentResult.getRemoteContent) {
    const c = contentResult.getRemoteContent;
    console.log('  type:', c.type, 'isArray:', c.isArray, 'keys:', c.keys, 'strLen:', c.strLen);
    console.log('  preview:', c.preview.substring(0, 800));
  } else console.log('  错误:', contentResult.getRemoteContentError);
  fs.writeFileSync(path.join(OUTPUT_DIR, 'content_result.json'), JSON.stringify(contentResult, null, 2), 'utf-8');

  // ========== 3. 如果 getContent 返回数据，保存完整内容 ==========
  if (contentResult.getContent && contentResult.getContent.strLen > 0) {
    console.log('\n=== 3. 保存完整 getContent 数据 ===');
    const fullContent = await page.evaluate(async () => {
      try { return await window.__fm.getContent(); } catch (e) { return { error: e.message }; }
    });
    fs.writeFileSync(path.join(DATA_OUTPUT, 'getContent_full.json'), JSON.stringify(fullContent, null, 2), 'utf-8');
    console.log('已保存 getContent_full.json, 大小:', JSON.stringify(fullContent).length, '字符');
  }

  console.log('\n探测完成');
  await page.waitForTimeout(3000);
  await context.close();
})().catch(e => { console.error('脚本错误:', e); process.exit(1); });
