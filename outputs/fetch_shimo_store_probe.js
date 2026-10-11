// 石墨文档 Redux Store 深度探测 + 数据提取脚本
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

  // ========== 1. dump state顶层结构 ==========
  console.log('\n=== 1. Redux Store 顶层结构 ===');
  const topStructure = await page.evaluate(() => {
    try {
      const state = window.shimo.store.getState();
      const out = { _topKeys: Object.keys(state) };
      for (const k of Object.keys(state)) {
        const v = state[k];
        try {
          if (v === null || v === undefined) { out[k] = { type: String(v) }; continue; }
          const t = typeof v;
          if (t !== 'object') { out[k] = { type: t, value: String(v).substring(0, 200) }; continue; }
          if (Array.isArray(v)) { out[k] = { type: 'array', length: v.length, sample0: v[0] ? JSON.stringify(v[0]).substring(0, 300) : null }; continue; }
          const subKeys = Object.keys(v);
          out[k] = { type: 'object', keys: subKeys.slice(0, 50), keyCount: subKeys.length };
        } catch (e) { out[k] = { error: e.message }; }
      }
      return out;
    } catch (e) { return { error: e.message }; }
  });
  console.log(JSON.stringify(topStructure, null, 2));
  fs.writeFileSync(path.join(OUTPUT_DIR, 'state_top_structure.json'), JSON.stringify(topStructure, null, 2), 'utf-8');

  // ========== 2. 深度遍历找数据路径（含cell/sheet/data关键词） ==========
  console.log('\n=== 2. 深度遍历定位数据路径 ===');
  const dataPaths = await page.evaluate(() => {
    const state = window.shimo.store.getState();
    const results = [];
    const KEYWORDS = /cell|sheet|data|doc|content|value|row|column|grid|matrix/i;
    const MAX_DEPTH = 4;
    const MAX_PER_PATH = 5;

    function walk(obj, path, depth) {
      if (depth > MAX_DEPTH || obj === null || obj === undefined) return;
      const t = typeof obj;
      if (t !== 'object') {
        // 叶子节点，如果路径含关键词，记录
        if (KEYWORDS.test(path)) {
          results.push({ path, type: t, value: String(obj).substring(0, 100) });
        }
        return;
      }
      let keys;
      try { keys = Object.keys(obj); } catch (e) { return; }
      // 如果路径含关键词且是数组/对象，记录结构
      if (KEYWORDS.test(path) && depth >= 2) {
        const isArr = Array.isArray(obj);
        results.push({ path, type: isArr ? 'array' : 'object', length: isArr ? obj.length : keys.length, keys: keys.slice(0, 10) });
        if (results.length > 200) return; // 限制
      }
      // 递归
      for (const k of keys.slice(0, 30)) {
        walk(obj[k], path ? path + '.' + k : k, depth + 1);
      }
    }
    walk(state, '', 0);
    return results.slice(0, 150);
  });
  console.log(`找到 ${dataPaths.length} 个数据路径，前30个：`);
  dataPaths.slice(0, 30).forEach(d => console.log(`  ${d.path} [${d.type}${d.length !== undefined ? ' len=' + d.length : ''}]${d.keys ? ' keys=' + JSON.stringify(d.keys) : ''}${d.value ? ' = ' + d.value.substring(0, 60) : ''}`));
  fs.writeFileSync(path.join(OUTPUT_DIR, 'state_data_paths.json'), JSON.stringify(dataPaths, null, 2), 'utf-8');

  // ========== 3. 尝试探测 createSheetSDK 是否有已创建的实例 ==========
  console.log('\n=== 3. 探测 SDK 实例与全局变量 ===');
  const sdkInstance = await page.evaluate(() => {
    const out = {};
    // 找所有可能的editor实例挂载点
    const gkeys = Object.keys(window).filter(k => /editor|sheet|doc|sm-|shimo/i.test(k));
    out._matchedGlobalKeys = gkeys;
    for (const k of gkeys) {
      try {
        const v = window[k];
        if (v && typeof v === 'object') {
          const methods = Object.getOwnPropertyNames(v).filter(kk => typeof v[kk] === 'function').slice(0, 50);
          if (methods.length) out['window.' + k] = { type: typeof v, methods };
        }
      } catch (e) {}
    }
    // 找DOM上挂载的实例（sm-开头的容器）
    const containers = document.querySelectorAll('[class*="sm-sheet"], [class*="shimo"], [id*="shimo"], [id*="sheet"]');
    const domInstances = [];
    containers.forEach(el => {
      const vueKeys = el.__vue__ ? Object.keys(el.__vue__).filter(k => /sheet|cell|data|doc|editor|sdk/i.test(k)) : [];
      const otherKeys = Object.keys(el).filter(k => /sheet|editor|sdk|instance|__/i.test(k));
      if (vueKeys.length || otherKeys.length) {
        domInstances.push({ tag: el.tagName, cls: (el.className || '').substring(0, 50), vueKeys: vueKeys.slice(0, 15), otherKeys: otherKeys.slice(0, 15) });
      }
    });
    out._domInstances = domInstances.slice(0, 20);
    return out;
  });
  console.log(JSON.stringify(sdkInstance, null, 2).substring(0, 4000));
  fs.writeFileSync(path.join(OUTPUT_DIR, 'sdk_instance_probe.json'), JSON.stringify(sdkInstance, null, 2), 'utf-8');

  console.log('\n探测完成，结果保存到 shimo_capture/');
  await page.waitForTimeout(5000);
  await context.close();
})().catch(e => { console.error('脚本错误:', e); process.exit(1); });
