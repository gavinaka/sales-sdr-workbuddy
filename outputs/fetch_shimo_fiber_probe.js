// 石墨文档 React Fiber 探测 - 找到编辑器SDK实例
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

  // ========== 1. 遍历 React Fiber 树找编辑器实例 ==========
  console.log('\n=== 1. React Fiber 树遍历找编辑器实例 ===');
  const fiberResult = await page.evaluate(() => {
    const out = { scanned: 0, candidates: [], editorFound: null };

    // 找到表格根DOM元素的fiber
    const root = document.querySelector('.sm-sheet-wrapper, .spreadsheet-view, .sm-sheet-editor-wrap');
    if (!root) { out.error = '找不到表格根DOM'; return out; }

    // 获取fiber key（__reactInternalInstance$xxx 或 __reactFiber$xxx）
    const fiberKey = Object.keys(root).find(k => k.startsWith('__reactInternalInstance$') || k.startsWith('__reactFiber$'));
    if (!fiberKey) { out.error = '找不到fiber key'; return out; }
    out.fiberKey = fiberKey;

    let fiber = root[fiberKey];
    const visited = new Set();
    const KEYWORDS = /editor|sdk|sheet|doc|cell|workbook|spreadsheet|model|data/i;

    // 向上遍历到根，再向下遍历
    function getFiberData(f) {
      if (!f || visited.has(f)) return null;
      visited.add(f);
      out.scanned++;
      if (out.scanned > 2000) return null;

      const data = { tag: f.tag, elementType: typeof f.elementType === 'string' ? f.elementType : (f.elementType && f.elementType.name) || (f.elementType && f.elementType.displayName) || '?' };

      // 检查 memoizedProps
      try {
        if (f.memoizedProps && typeof f.memoizedProps === 'object') {
          const propKeys = Object.keys(f.memoizedProps).filter(k => k !== 'children');
          data.propKeys = propKeys.slice(0, 20);
          // 找含关键词的props
          const matchedProps = propKeys.filter(k => KEYWORDS.test(k));
          if (matchedProps.length) {
            data.matchedProps = matchedProps;
            // 探测这些prop的值
            for (const pk of matchedProps.slice(0, 5)) {
              const v = f.memoizedProps[pk];
              if (v && typeof v === 'object') {
                const vkeys = Object.keys(v).slice(0, 30);
                const vmethods = vkeys.filter(k => typeof v[k] === 'function');
                data['prop_' + pk] = { type: 'object', keys: vkeys, methods: vmethods.slice(0, 50) };
                // 如果方法名含get/export/read，标记为editor候选
                if (vmethods.some(m => /get|export|read|sheet|cell|data/i.test(m))) {
                  out.candidates.push({ from: 'prop:' + pk, elementType: data.elementType, methods: vmethods.slice(0, 80), keys: vkeys.slice(0, 30) });
                }
              } else if (typeof v === 'function') {
                data['prop_' + pk] = { type: 'function' };
              }
            }
          }
        }
      } catch (e) { data.propsError = e.message; }

      // 检查 stateNode（类组件实例）
      try {
        const sn = f.stateNode;
        if (sn && typeof sn === 'object' && sn !== root && !sn.tagName) {
          const snKeys = Object.keys(sn).filter(k => KEYWORDS.test(k));
          if (snKeys.length) {
            data.stateNodeMatchedKeys = snKeys.slice(0, 20);
            for (const sk of snKeys.slice(0, 5)) {
              const v = sn[sk];
              if (v && typeof v === 'object') {
                const vkeys = Object.keys(v).slice(0, 40);
                const vmethods = vkeys.filter(k => typeof v[k] === 'function');
                if (vmethods.length > 3) {
                  out.candidates.push({ from: 'stateNode:' + sk, elementType: data.elementType, methods: vmethods.slice(0, 100), keys: vkeys.slice(0, 40) });
                }
              }
            }
          }
        }
      } catch (e) {}

      // 检查 memoizedState（hooks state）
      try {
        let st = f.memoizedState;
        let stateIdx = 0;
        while (st && stateIdx < 8) {
          if (st.memoizedState && typeof st.memoizedState === 'object') {
            const stKeys = Object.keys(st.memoizedState).filter(k => KEYWORDS.test(k));
            if (stKeys.length) {
              for (const sk of stKeys.slice(0, 3)) {
                const v = st.memoizedState[sk];
                if (v && typeof v === 'object') {
                  const vkeys = Object.keys(v).slice(0, 40);
                  const vmethods = vkeys.filter(k => typeof v[k] === 'function');
                  if (vmethods.length > 5) {
                    out.candidates.push({ from: 'state[' + stateIdx + ']:' + sk, elementType: data.elementType, methods: vmethods.slice(0, 100), keys: vkeys.slice(0, 40) });
                  }
                }
              }
            }
          }
          st = st.next;
          stateIdx++;
        }
      } catch (e) {}

      return data;
    }

    // 先向上到根
    let up = fiber;
    let upCount = 0;
    while (up && upCount < 30) { getFiberData(up); up = up.return; upCount++; }

    // 从根向下DFS
    function dfs(f, depth) {
      if (!f || depth > 12 || out.scanned > 2000) return;
      getFiberData(f);
      dfs(f.child, depth + 1);
      dfs(f.sibling, depth + 1);
    }
    // 从最初的fiber向下
    dfs(fiber, 0);

    // 去重candidates
    const seen = new Set();
    out.candidates = out.candidates.filter(c => {
      const key = c.from + '|' + (c.methods || []).slice(0, 5).join(',');
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    }).slice(0, 30);

    return out;
  });

  console.log('扫描fiber数:', fiberResult.scanned);
  console.log('候选编辑器实例:', fiberResult.candidates.length);
  fiberResult.candidates.forEach((c, i) => {
    console.log(`\n  [候选${i}] from=${c.from} elementType=${c.elementType}`);
    console.log(`    methods: ${(c.methods || []).slice(0, 30).join(', ')}`);
    console.log(`    keys: ${(c.keys || []).slice(0, 20).join(', ')}`);
  });
  fs.writeFileSync(path.join(OUTPUT_DIR, 'fiber_probe.json'), JSON.stringify(fiberResult, null, 2), 'utf-8');

  // ========== 2. 如果找到候选，尝试深入探测方法 ==========
  if (fiberResult.candidates.length > 0) {
    console.log('\n=== 2. 深入探测候选实例的方法列表 ===');
    // 重新遍历，找到第一个候选实例，dump完整方法列表
    const methodDump = await page.evaluate(() => {
      const root = document.querySelector('.sm-sheet-wrapper, .spreadsheet-view, .sm-sheet-editor-wrap');
      const fiberKey = Object.keys(root).find(k => k.startsWith('__reactInternalInstance$') || k.startsWith('__reactFiber$'));
      let fiber = root[fiberKey];
      const visited = new Set();
      const KEYWORDS = /editor|sdk|sheet|doc|cell|workbook|spreadsheet|model|data/i;
      let found = null;

      function scan(f) {
        if (!f || visited.has(f) || found) return;
        visited.add(f);
        // 检查 props
        try {
          if (f.memoizedProps && typeof f.memoizedProps === 'object') {
            for (const pk of Object.keys(f.memoizedProps).filter(k => KEYWORDS.test(k))) {
              const v = f.memoizedProps[pk];
              if (v && typeof v === 'object') {
                const methods = Object.keys(v).filter(k => typeof v[k] === 'function');
                if (methods.length > 5 && methods.some(m => /get|export|sheet|cell/i.test(m))) {
                  found = { source: 'prop:' + pk, instance: v };
                  return;
                }
              }
            }
          }
        } catch (e) {}
        // 检查 stateNode
        try {
          const sn = f.stateNode;
          if (sn && typeof sn === 'object' && !sn.tagName) {
            for (const sk of Object.keys(sn).filter(k => KEYWORDS.test(k))) {
              const v = sn[sk];
              if (v && typeof v === 'object') {
                const methods = Object.keys(v).filter(k => typeof v[k] === 'function');
                if (methods.length > 5 && methods.some(m => /get|export|sheet|cell/i.test(m))) {
                  found = { source: 'stateNode:' + sk, instance: v };
                  return;
                }
              }
            }
          }
        } catch (e) {}
        scan(f.child); scan(f.sibling);
      }
      scan(fiber);
      // 向上也扫
      let up = fiber.return;
      let n = 0;
      while (up && !found && n < 30) { scan(up); up = up.return; n++; }

      if (!found) return { error: '未找到实例' };
      const inst = found.instance;
      // 完整方法列表（含原型链）
      const allMethods = [];
      let proto = inst;
      while (proto && proto !== Object.prototype && allMethods.length < 200) {
        for (const k of Object.getOwnPropertyNames(proto)) {
          if (typeof inst[k] === 'function' && !allMethods.includes(k)) allMethods.push(k);
        }
        proto = Object.getPrototypeOf(proto);
      }
      // 找含 get/read/export/sheet/cell/data 的方法
      const dataMethods = allMethods.filter(m => /get|read|export|sheet|cell|data|value|range|row|column|workbook|all/i.test(m));
      return { source: found.source, allMethodsCount: allMethods.length, allMethods: allMethods.slice(0, 100), dataMethods: dataMethods.slice(0, 60), ownKeys: Object.keys(inst).slice(0, 40) };
    });
    console.log('\n编辑器实例方法dump:');
    console.log('  source:', methodDump.source);
    console.log('  总方法数:', methodDump.allMethodsCount);
    console.log('  数据相关方法:', methodDump.dataMethods);
    console.log('  ownKeys:', methodDump.ownKeys);
    fs.writeFileSync(path.join(OUTPUT_DIR, 'editor_methods.json'), JSON.stringify(methodDump, null, 2), 'utf-8');
  }

  console.log('\n探测完成');
  await page.waitForTimeout(3000);
  await context.close();
})().catch(e => { console.error('脚本错误:', e); process.exit(1); });
