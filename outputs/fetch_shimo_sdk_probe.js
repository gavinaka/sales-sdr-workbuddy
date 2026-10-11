// 石墨文档SDK深度探测 + 数据读取脚本
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
  // 授予剪贴板权限
  await context.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: 'https://shimo.im' });

  const pages = context.pages();
  const page = pages.length > 0 ? pages[0] : await context.newPage();

  console.log('打开石墨文档...');
  await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(8000);

  // ========== 1. 深度探测SDK结构 ==========
  console.log('\n=== 1. 探测 @shimo/editor-sdk-sheet SDK ===');
  const sdkProbe = await page.evaluate(() => {
    const out = {};
    // 探测 window 上的关键对象
    const keys = ['@shimo/editor-sdk-sheet', 'shimo', 'SHIMO_APM', '_SHIMO_BRAODCAST_', '__LIZARD_CONFIG_HOST__'];
    for (const k of keys) {
      try {
        const v = window[k];
        if (v === undefined) { out[k] = 'undefined'; continue; }
        if (v === null) { out[k] = 'null'; continue; }
        out[k] = {
          type: typeof v,
          keys: v && typeof v === 'object' ? Object.keys(v).slice(0, 100) : null,
          methods: v && typeof v === 'object' ? Object.keys(v).filter(kk => typeof v[kk] === 'function').slice(0, 100) : null
        };
      } catch (e) { out[k] = 'error: ' + e.message; }
    }
    // 探测DOM上的__vue__
    try {
      const app = document.querySelector('#app') || document.querySelector('[id*="app"]');
      if (app && app.__vue__) {
        const store = app.__vue__.$store;
        out._vueStore = store ? { keys: Object.keys(store.state || {}).slice(0, 100) } : null;
      }
    } catch (e) { out._vueError = e.message; }
    // 找所有带 __vue__ 的元素中含 sheet/data 的
    try {
      const vueEls = [];
      document.querySelectorAll('*').forEach(el => {
        if (el.__vue__) {
          const v = el.__vue__;
          const ks = Object.keys(v).filter(k => /sheet|cell|data|editor|doc|file/i.test(k));
          if (ks.length) vueEls.push({ tag: el.tagName, class: el.className.substring(0, 60), keys: ks.slice(0, 20) });
        }
      });
      out._vueElsWithData = vueEls.slice(0, 20);
    } catch (e) { out._vueElsError = e.message; }
    return out;
  });
  console.log(JSON.stringify(sdkProbe, null, 2).substring(0, 6000));
  fs.writeFileSync(path.join(OUTPUT_DIR, 'sdk_probe.json'), JSON.stringify(sdkProbe, null, 2), 'utf-8');

  // ========== 2. 探测editor实例（石墨表格通常挂在某处） ==========
  console.log('\n=== 2. 查找editor实例 ===');
  const editorProbe = await page.evaluate(() => {
    const out = {};
    // 常见挂载点
    const candidates = [
      'window.shimo.sheet', 'window.shimo.editor', 'window.shimo.document',
      'window.sheetEditor', 'window.editor', 'window.sheet', 'window.doc',
      'window.__SHIMO_EDITOR__', 'window.__editor__', 'window.__sheet__'
    ];
    for (const path of candidates) {
      try {
        const v = eval(path);
        if (v) {
          out[path] = {
            type: typeof v,
            keys: v && typeof v === 'object' ? Object.keys(v).slice(0, 80) : null,
            methods: v && typeof v === 'object' ? Object.getOwnPropertyNames(v).filter(k => typeof v[k] === 'function').slice(0, 80) : null
          };
        }
      } catch (e) {}
    }
    // 在shimo对象上递归找editor
    try {
      const shimo = window.shimo;
      if (shimo) {
        out._shimoAllKeys = Object.keys(shimo);
        for (const k of Object.keys(shimo)) {
          const v = shimo[k];
          if (v && typeof v === 'object') {
            out['shimo.' + k + '.keys'] = Object.keys(v).slice(0, 50);
          }
        }
      }
    } catch (e) { out._shimoError = e.message; }
    return out;
  });
  console.log(JSON.stringify(editorProbe, null, 2).substring(0, 6000));
  fs.writeFileSync(path.join(OUTPUT_DIR, 'editor_probe.json'), JSON.stringify(editorProbe, null, 2), 'utf-8');

  // ========== 3. 尝试复制法：读取当前sheet ==========
  console.log('\n=== 3. 尝试复制法（当前sheet）===');
  // 点击表格区域，Ctrl+A全选，Ctrl+C复制
  try {
    await page.click('canvas', { timeout: 5000 }).catch(() => {});
    await page.waitForTimeout(500);
    // Ctrl+A 选中当前sheet全部
    await page.keyboard.press('Control+A');
    await page.waitForTimeout(1000);
    // Ctrl+C 复制
    await page.keyboard.press('Control+C');
    await page.waitForTimeout(1500);
    // 读取剪贴板
    const clipboard = await page.evaluate(async () => {
      try {
        const text = await navigator.clipboard.readText();
        return { len: text.length, sample: text.substring(0, 2000), rows: text.split('\n').length };
      } catch (e) { return { error: e.message }; }
    });
    console.log('剪贴板结果:', JSON.stringify(clipboard).substring(0, 500));
    fs.writeFileSync(path.join(OUTPUT_DIR, 'clipboard_test.json'), JSON.stringify(clipboard, null, 2), 'utf-8');
    // 如果成功，保存完整内容
    if (clipboard.sample && !clipboard.error) {
      const full = await page.evaluate(async () => {
        try { return await navigator.clipboard.readText(); } catch (e) { return 'ERR:' + e.message; }
      });
      fs.writeFileSync(path.join(OUTPUT_DIR, 'sheet_clipboard_test.tsv'), full, 'utf-8');
      console.log('已保存sheet_clipboard_test.tsv, 行数:', full.split('\n').length);
    }
  } catch (e) {
    console.log('复制法失败:', e.message);
  }

  // ========== 4. 探测所有sheet标签的DOM结构（为遍历做准备） ==========
  console.log('\n=== 4. 探测sheet标签DOM（为遍历做准备）===');
  const sheetTabsDom = await page.evaluate(() => {
    // 石墨sheet标签通常在底部
    const out = {};
    // 尝试多种选择器
    const selectors = [
      '.sheet-tab', '.sheet-name', '[class*="sheet"][class*="tab"]',
      '[class*="SheetTab"]', '[class*="sheet-tab"]', '.sheet-bar [class*="tab"]',
      'span[class*="tab"]'
    ];
    for (const s of selectors) {
      const els = document.querySelectorAll(s);
      if (els.length) {
        out[s] = Array.from(els).map(e => ({
          text: (e.innerText || e.textContent || '').trim().substring(0, 30),
          cls: e.className.substring(0, 80)
        })).slice(0, 20);
      }
    }
    // 底部栏的所有可点击文本
    const bottomTexts = [];
    document.querySelectorAll('div, span').forEach(el => {
      const t = (el.innerText || '').trim();
      if (t && t.length < 20 && /线索表|流转表|转化率|透视表|成交|文案|工作表/.test(t) && el.children.length === 0) {
        bottomTexts.push({ text: t, tag: el.tagName, cls: el.className.substring(0, 60), rect: (() => { const r = el.getBoundingClientRect(); return { x: Math.round(r.x), y: Math.round(r.y) }; })() });
      }
    });
    out._bottomSheetTexts = bottomTexts.slice(0, 40);
    return out;
  });
  console.log('Sheet标签DOM结构:');
  console.log(JSON.stringify(sheetTabsDom, null, 2).substring(0, 4000));
  fs.writeFileSync(path.join(OUTPUT_DIR, 'sheet_tabs_dom.json'), JSON.stringify(sheetTabsDom, null, 2), 'utf-8');

  console.log('\n探测完成，结果保存到 shimo_capture/');
  console.log('浏览器保持打开25秒...');
  await page.waitForTimeout(25000);
  await context.close();
})().catch(e => { console.error('脚本错误:', e); process.exit(1); });
