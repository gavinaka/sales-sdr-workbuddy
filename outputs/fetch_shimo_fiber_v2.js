// 石墨文档 Fiber 全面遍历 v2 + createSheetSDK 源码分析
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

  // ========== 1. createSheetSDK 源码分析 ==========
  console.log('\n=== 1. createSheetSDK 源码分析 ===');
  const sdkSource = await page.evaluate(() => {
    const sdk = window['@shimo/editor-sdk-sheet'];
    if (!sdk || !sdk.createSheetSDK) return { error: '无SDK' };
    const fnStr = sdk.createSheetSDK.toString();
    return { length: fnStr.length, preview: fnStr.substring(0, 3000), full: fnStr.substring(0, 8000) };
  });
  console.log('createSheetSDK源码长度:', sdkSource.length);
  console.log('源码预览:\n', sdkSource.preview.substring(0, 2000));
  fs.writeFileSync(path.join(OUTPUT_DIR, 'createSheetSDK_source.txt'), sdkSource.full || '', 'utf-8');

  // ========== 2. 全面DFS遍历Fiber，找所有类组件实例 ==========
  console.log('\n=== 2. 全面Fiber DFS遍历 ===');
  const allInstances = await page.evaluate(() => {
    const results = { scanned: 0, classInstances: [], richPropsInstances: [] };

    // 找根fiber
    const container = document.querySelector('#root, #app, [id*="root"]');
    const body = document.body;
    let rootFiber = null;
    // 尝试多个入口
    const entries = [container, body, document.querySelector('.sm-sheet-wrapper')];
    for (const el of entries) {
      if (!el) continue;
      const fk = Object.keys(el).find(k => k.startsWith('__reactContainer$') || k.startsWith('__reactInternalInstance$') || k.startsWith('__reactFiber$'));
      if (fk) { rootFiber = el[fk]; break; }
    }
    if (!rootFiber) { results.error = '找不到root fiber'; return results; }

    const visited = new Set();
    function dfs(f, depth) {
      if (!f || visited.has(f) || depth > 15 || results.scanned > 3000) return;
      visited.add(f);
      results.scanned++;

      // 检查 stateNode 是否类组件实例
      try {
        const sn = f.stateNode;
        if (sn && typeof sn === 'object' && sn !== document.body && !sn.tagName && !sn.nodeType) {
          // 这是类组件实例
          const ownKeys = Object.keys(sn);
          if (ownKeys.length >= 3) {
            // 收集方法（含原型链）
            const methods = [];
            let proto = sn;
            while (proto && proto !== Object.prototype && methods.length < 150) {
              try {
                for (const k of Object.getOwnPropertyNames(proto)) {
                  if (k !== 'constructor' && typeof sn[k] === 'function' && !methods.includes(k)) methods.push(k);
                }
              } catch (e) { break; }
              proto = Object.getPrototypeOf(proto);
            }
            if (methods.length > 5 || ownKeys.length > 5) {
              const dataMethods = methods.filter(m => /get|read|export|sheet|cell|data|value|range|row|column|workbook|all|toJS|toJSON|serialize/i.test(m));
              results.classInstances.push({
                elementType: typeof f.elementType === 'string' ? f.elementType : (f.elementType && (f.elementType.displayName || f.elementType.name)) || '?',
                ownKeysCount: ownKeys.length,
                ownKeys: ownKeys.slice(0, 30),
                methodsCount: methods.length,
                dataMethods: dataMethods.slice(0, 50),
                allMethods: methods.slice(0, 80)
              });
            }
          }
        }
      } catch (e) {}

      // 检查 memoizedProps 里是否有丰富对象（潜在editor实例通过props传入）
      try {
        if (f.memoizedProps && typeof f.memoizedProps === 'object') {
          for (const pk of Object.keys(f.memoizedProps)) {
            if (pk === 'children') continue;
            const v = f.memoizedProps[pk];
            if (v && typeof v === 'object' && !Array.isArray(v)) {
              const vkeys = Object.keys(v);
              const vmethods = vkeys.filter(k => { try { return typeof v[k] === 'function'; } catch (e) { return false; } });
              if (vmethods.length > 8) {
                const dataMethods = vmethods.filter(m => /get|read|export|sheet|cell|data|value|range|row|column|workbook|all|toJS|toJSON|serialize/i.test(m));
                results.richPropsInstances.push({
                  propKey: pk,
                  elementType: typeof f.elementType === 'string' ? f.elementType : (f.elementType && (f.elementType.displayName || f.elementType.name)) || '?',
                  keysCount: vkeys.length,
                  methodsCount: vmethods.length,
                  dataMethods: dataMethods.slice(0, 50),
                  allMethods: vmethods.slice(0, 60)
                });
              }
            }
          }
        }
      } catch (e) {}

      dfs(f.child, depth + 1);
      dfs(f.sibling, depth + 1);
    }
    dfs(rootFiber, 0);
    return results;
  });

  console.log('扫描fiber总数:', allInstances.scanned);
  console.log('\n类组件实例数:', allInstances.classInstances.length);
  allInstances.classInstances.forEach((c, i) => {
    const hasData = c.dataMethods.length > 0;
    if (hasData || c.methodsCount > 15 || c.ownKeysCount > 8) {
      console.log(`\n  [类实例${i}] ${c.elementType} (ownKeys=${c.ownKeysCount}, methods=${c.methodsCount})`);
      console.log(`    ownKeys: ${c.ownKeys.join(', ')}`);
      if (c.dataMethods.length) console.log(`    数据方法: ${c.dataMethods.join(', ')}`);
      if (c.dataMethods.length) console.log(`    全部方法: ${c.allMethods.join(', ')}`);
    }
  });
  console.log('\n富Props实例数:', allInstances.richPropsInstances.length);
  allInstances.richPropsInstances.forEach((c, i) => {
    console.log(`\n  [Props实例${i}] prop=${c.propKey} elementType=${c.elementType} (keys=${c.keysCount}, methods=${c.methodsCount})`);
    if (c.dataMethods.length) console.log(`    数据方法: ${c.dataMethods.join(', ')}`);
    if (c.dataMethods.length) console.log(`    全部方法: ${c.allMethods.join(', ')}`);
  });
  fs.writeFileSync(path.join(OUTPUT_DIR, 'fiber_all_instances.json'), JSON.stringify(allInstances, null, 2), 'utf-8');

  console.log('\n探测完成');
  await page.waitForTimeout(3000);
  await context.close();
})().catch(e => { console.error('脚本错误:', e); process.exit(1); });
