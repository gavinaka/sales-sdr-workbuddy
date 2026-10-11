// 石墨文档 综合诊断：Fiber key + IndexedDB + Socket + 完整fiber遍历
const { chromium } = require('playwright-core');
const fs = require('fs');
const path = require('path');

const CHROME_PATH = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const USER_DATA_DIR = path.join(__dirname, '.shimo_data');
const OUTPUT_DIR = path.join(__dirname, 'shimo_capture');
const URL = 'https://shimo.im/sheets/473QMXrrL4F7p53w/dJr6p';

if (!fs.existsSync(OUTPUT_DIR)) fs.mkdirSync(OUTPUT_DIR, { recursive: true });

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
  await page.waitForTimeout(8000);

  // ========== A. Fiber key 诊断 ==========
  console.log('\n=== A. Fiber key 诊断 ===');
  const fiberDiag = await page.evaluate(() => {
    const out = {};
    const els = {
      'body': document.body,
      'sm-sheet-wrapper': document.querySelector('.sm-sheet-wrapper'),
      'spreadsheet-view': document.querySelector('.spreadsheet-view'),
      'sm-sheet-editor-wrap': document.querySelector('.sm-sheet-editor-wrap'),
      'root': document.querySelector('#root'),
      'app': document.querySelector('#app')
    };
    for (const [name, el] of Object.entries(els)) {
      if (!el) { out[name] = '不存在'; continue; }
      const reactKeys = Object.keys(el).filter(k => k.startsWith('__react'));
      out[name] = { reactKeys, tag: el.tagName, id: el.id, cls: (el.className || '').substring(0, 60) };
    }
    // 找第一个有react key的元素的fiber，看结构
    for (const [name, el] of Object.entries(els)) {
      if (!el) continue;
      const fk = Object.keys(el).find(k => k.startsWith('__react'));
      if (fk) {
        const f = el[fk];
        out._firstFiber = {
          fromEl: name, fiberKey: fk,
          tag: f.tag, elementType: typeof f.elementType === 'string' ? f.elementType : (f.elementType && (f.elementType.displayName || f.elementType.name)) || String(f.elementType),
          hasChild: !!f.child, hasSibling: !!f.sibling, hasReturn: !!f.return,
          hasMemoizedProps: !!f.memoizedProps,
          hasMemoizedState: !!f.memoizedState,
          stateNodeType: f.stateNode ? (f.stateNode.tagName ? 'DOM:' + f.stateNode.tagName : typeof f.stateNode) : 'null'
        };
        break;
      }
    }
    return out;
  });
  console.log(JSON.stringify(fiberDiag, null, 2));
  fs.writeFileSync(path.join(OUTPUT_DIR, 'fiber_diag.json'), JSON.stringify(fiberDiag, null, 2), 'utf-8');

  // ========== B. 完整fiber DFS（从body或root） ==========
  console.log('\n=== B. 完整fiber DFS ===');
  const fiberScan = await page.evaluate(() => {
    const out = { scanned: 0, allElements: [], richStates: [] };
    // 找任何带react fiber的元素作为入口
    let entryEl = null, entryKey = null;
    const candidates = [document.querySelector('#root'), document.querySelector('#app'), document.body];
    for (const el of candidates) {
      if (!el) continue;
      // 元素本身
      let k = Object.keys(el).find(kk => kk.startsWith('__react'));
      if (k) { entryEl = el; entryKey = k; break; }
      // 子元素
      const child = el.querySelector ? el.querySelector('*') : null;
      if (child) {
        k = Object.keys(child).find(kk => kk.startsWith('__react'));
        if (k) { entryEl = child; entryKey = k; break; }
      }
    }
    if (!entryEl) { out.error = '找不到任何react fiber入口'; return out; }
    out.entry = { tag: entryEl.tagName, cls: (entryEl.className || '').substring(0, 50), key: entryKey };

    let fiber = entryEl[entryKey];
    // 向上找到真正的root
    let rootFiber = fiber;
    let upN = 0;
    while (rootFiber && rootFiber.return && upN < 50) { rootFiber = rootFiber.return; upN++; }
    out.upSteps = upN;

    const visited = new Set();
    function dfs(f, depth) {
      if (!f || visited.has(f) || depth > 18 || out.scanned > 5000) return;
      visited.add(f);
      out.scanned++;

      const et = typeof f.elementType === 'string' ? f.elementType : (f.elementType && (f.elementType.displayName || f.elementType.name)) || '';
      // 记录所有元素
      if (et) out.allElements.push({ depth, tag: f.tag, et, hasState: !!f.memoizedState, hasProps: !!f.memoizedProps });

      // 检查 memoizedState 链（hooks）
      try {
        let st = f.memoizedState;
        let idx = 0;
        while (st && idx < 10) {
          if (st.memoizedState !== null && st.memoizedState !== undefined) {
            const ms = st.memoizedState;
            if (ms && typeof ms === 'object' && !Array.isArray(ms)) {
              const msKeys = Object.keys(ms);
              if (msKeys.length >= 5) {
                // 潜在数据state
                const msMethods = msKeys.filter(k => { try { return typeof ms[k] === 'function'; } catch (e) { return false; } });
                if (msMethods.length > 3 || msKeys.length > 15) {
                  out.richStates.push({
                    depth, et, stateIdx: idx,
                    keysCount: msKeys.length, methodsCount: msMethods.length,
                    keys: msKeys.slice(0, 40),
                    methods: msMethods.slice(0, 60)
                  });
                }
              } else if (Array.isArray(ms) && ms.length > 50) {
                out.richStates.push({ depth, et, stateIdx: idx, type: 'array', length: ms.length });
              }
            }
          }
          st = st.next; idx++;
        }
      } catch (e) {}

      // 检查 stateNode（类实例）
      try {
        const sn = f.stateNode;
        if (sn && typeof sn === 'object' && !sn.tagName && !sn.nodeType) {
          const snKeys = Object.keys(sn);
          if (snKeys.length >= 5) {
            const snMethods = snKeys.filter(k => { try { return typeof sn[k] === 'function'; } catch (e) { return false; } });
            if (snMethods.length > 3) {
              out.richStates.push({ depth, et, source: 'stateNode', keysCount: snKeys.length, methodsCount: snMethods.length, keys: snKeys.slice(0, 40), methods: snMethods.slice(0, 60) });
            }
          }
        }
      } catch (e) {}

      dfs(f.child, depth + 1);
      dfs(f.sibling, depth + 1);
    }
    dfs(rootFiber, 0);
    return out;
  });
  console.log('扫描fiber数:', fiberScan.scanned);
  console.log('向上步数:', fiberScan.upSteps);
  if (fiberScan.error) console.log('错误:', fiberScan.error);
  console.log('richStates数:', fiberScan.richStates.length);
  fiberScan.richStates.slice(0, 15).forEach((r, i) => {
    console.log(`\n  [rich${i}] depth=${r.depth} et=${r.et} source=${r.source || 'hook'} stateIdx=${r.stateIdx} keys=${r.keysCount} methods=${r.methodsCount}`);
    if (r.keys) console.log(`    keys: ${r.keys.join(', ')}`);
    if (r.methods) console.log(`    methods: ${r.methods.join(', ')}`);
  });
  fs.writeFileSync(path.join(OUTPUT_DIR, 'fiber_scan_full.json'), JSON.stringify(fiberScan, null, 2), 'utf-8');

  // ========== C. IndexedDB 探测 ==========
  console.log('\n=== C. IndexedDB 探测 ===');
  const idbProbe = await page.evaluate(async () => {
    const out = { databases: [] };
    try {
      if (indexedDB.databases) {
        const dbs = await indexedDB.databases();
        out.databases = dbs;
      }
    } catch (e) { out.databasesError = e.message; }
    // 列出所有可能的库名
    try {
      const knownNames = ['shimo', 'shimo-sheet', 'sheet-cache', 'shimo_db'];
      for (const n of knownNames) {
        await new Promise((resolve) => {
          const req = indexedDB.open(n);
          req.onsuccess = () => { out.databases.push({ name: n, exists: true, stores: req.result.objectStoreNames ? Array.from(req.result.objectStoreNames) : [] }); req.result.close(); resolve(); };
          req.onerror = () => { resolve(); };
          req.onupgradeneeded = () => { req.transaction.abort(); resolve(); };
        });
      }
    } catch (e) {}
    return out;
  });
  console.log('IndexedDB:', JSON.stringify(idbProbe, null, 2));

  // ========== D. localStorage/sessionStorage 关键key ==========
  console.log('\n=== D. Storage 探测 ===');
  const storageProbe = await page.evaluate(() => {
    const out = { localStorageKeys: [], sessionStorageKeys: [] };
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      const v = localStorage.getItem(k);
      out.localStorageKeys.push({ key: k, len: v ? v.length : 0, preview: v ? v.substring(0, 100) : '' });
    }
    for (let i = 0; i < sessionStorage.length; i++) {
      const k = sessionStorage.key(i);
      const v = sessionStorage.getItem(k);
      out.sessionStorageKeys.push({ key: k, len: v ? v.length : 0, preview: v ? v.substring(0, 100) : '' });
    }
    return out;
  });
  console.log('localStorage (' + storageProbe.localStorageKeys.length + ' keys):');
  storageProbe.localStorageKeys.forEach(k => console.log(`  ${k.key} [${k.len}] ${k.preview.substring(0, 50)}`));

  console.log('\n探测完成');
  fs.writeFileSync(path.join(OUTPUT_DIR, 'storage_probe.json'), JSON.stringify({ idb: idbProbe, storage: storageProbe }, null, 2), 'utf-8');
  await page.waitForTimeout(3000);
  await context.close();
})().catch(e => { console.error('脚本错误:', e); process.exit(1); });
