// 石墨文档 - 复制法测试（正确聚焦canvas + copy事件捕获）
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
  await context.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: 'https://shimo.im' });
  const pages = context.pages();
  const page = pages.length > 0 ? pages[0] : await context.newPage();

  // 注入copy事件监听器，捕获石墨复制的clipboardData
  await page.addInitScript(() => {
    window.__copyData = null;
    document.addEventListener('copy', (e) => {
      try {
        const data = {};
        const types = e.clipboardData ? e.clipboardData.types : [];
        data.types = Array.from(types);
        for (const t of data.types) {
          try { data[t] = e.clipboardData.getData(t); } catch (err) { data[t] = 'err:' + err.message; }
        }
        window.__copyData = data;
      } catch (err) { window.__copyData = { error: err.message }; }
    }, true);  // capture阶段
  });

  console.log('打开石墨文档...');
  await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
  try { await page.waitForSelector('.sm-sheet-tab-item', { timeout: 30000 }); } catch (e) {}
  await page.waitForTimeout(6000);

  // 清空copyData
  await page.evaluate(() => { window.__copyData = null; });

  // ========== 测试复制当前sheet ==========
  console.log('\n=== 测试复制当前sheet ===');

  // 1. 找canvas并点击聚焦
  const canvasInfo = await page.evaluate(() => {
    const canvas = document.querySelector('canvas');
    if (!canvas) return { error: '无canvas' };
    const r = canvas.getBoundingClientRect();
    return { found: true, x: r.x, y: r.y, w: r.width, h: r.height, cx: r.x + r.width / 2, cy: r.y + r.height / 2 };
  });
  console.log('Canvas信息:', JSON.stringify(canvasInfo));

  if (canvasInfo.found) {
    // 点击canvas中心
    await page.mouse.click(canvasInfo.cx, canvasInfo.cy);
    await page.waitForTimeout(800);
    const activeInfo = await page.evaluate(() => ({ active: document.activeElement ? document.activeElement.tagName + '.' + (document.activeElement.className || '') : 'null' }));
    console.log('点击后焦点:', activeInfo.active);

    // 2. Ctrl+A 全选
    await page.keyboard.press('Control+A');
    await page.waitForTimeout(1200);

    // 3. Ctrl+C 复制
    await page.keyboard.press('Control+C');
    await page.waitForTimeout(2000);

    // 4. 读取copy事件捕获的数据
    const copyData = await page.evaluate(() => window.__copyData);
    console.log('copy事件数据:');
    if (copyData) {
      console.log('  types:', copyData.types);
      if (copyData['text/plain']) {
        console.log('  text/plain 长度:', copyData['text/plain'].length);
        console.log('  text/plain 预览(前500):', copyData['text/plain'].substring(0, 500));
        console.log('  行数:', copyData['text/plain'].split('\n').length);
      }
      if (copyData['text/html']) {
        console.log('  text/html 长度:', copyData['text/html'].length);
      }
    } else {
      console.log('  无copy事件触发');
    }

    // 5. 也尝试读系统剪贴板
    const clip = await page.evaluate(async () => {
      try { return { text: await navigator.clipboard.readText() }; } catch (e) { return { error: e.message }; }
    });
    console.log('系统剪贴板:', clip.text ? ('长度=' + clip.text.length + ' 预览=' + clip.text.substring(0, 200)) : clip.error);

    // 6. 如果copy事件有数据，保存
    if (copyData && copyData['text/plain'] && copyData['text/plain'].length > 50) {
      fs.writeFileSync(path.join(DATA_OUTPUT, 'sheet_test_copy.tsv'), copyData['text/plain'], 'utf-8');
      console.log('已保存 sheet_test_copy.tsv');
      fs.writeFileSync(path.join(OUTPUT_DIR, 'copy_test_success.json'), JSON.stringify({
        types: copyData.types,
        plainLen: copyData['text/plain'].length,
        htmlLen: copyData['text/html'] ? copyData['text/html'].length : 0,
        rows: copyData['text/plain'].split('\n').length,
        cols: copyData['text/plain'].split('\n')[0] ? copyData['text/plain'].split('\n')[0].split('\t').length : 0
      }, null, 2), 'utf-8');
    }

    // 7. 如果Ctrl+A不行，尝试点击表格左上角"全选"按钮
    if (!copyData || !copyData['text/plain'] || copyData['text/plain'].length < 50) {
      console.log('\nCtrl+A未生效，尝试点击全选按钮...');
      // 石墨表格左上角有全选按钮（行号列交叉处）
      // 尝试找全选按钮
      const selectAllBtn = await page.evaluate(() => {
        // 找左上角的全选区域
        const corners = document.querySelectorAll('[class*="select-all"], [class*="corner"], [class*="header-corner"], [class*="all-select"]');
        const result = [];
        corners.forEach(el => {
          const r = el.getBoundingClientRect();
          result.push({ cls: el.className.substring(0, 60), x: r.x, y: r.y, w: r.width, h: r.height });
        });
        // 也找canvas左上角小区域（行号列表头上方）
        return result;
      });
      console.log('全选按钮候选:', JSON.stringify(selectAllBtn));

      // 尝试点击canvas左上角(0,0)附近（通常是全选）
      await page.mouse.click(canvasInfo.x + 10, canvasInfo.y + 10);
      await page.waitForTimeout(500);
      await page.keyboard.press('Control+A');
      await page.waitForTimeout(1000);
      await page.evaluate(() => { window.__copyData = null; });
      await page.keyboard.press('Control+C');
      await page.waitForTimeout(2000);
      const copyData2 = await page.evaluate(() => window.__copyData);
      console.log('第二次copy事件:', copyData2 ? JSON.stringify({ types: copyData2.types, plainLen: copyData2['text/plain'] ? copyData2['text/plain'].length : 0 }) : 'null');
    }
  }

  console.log('\n测试完成');
  await page.waitForTimeout(3000);
  await context.close();
})().catch(e => { console.error('脚本错误:', e); process.exit(1); });
