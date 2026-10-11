// 石墨文档 - 遍历13个sheet逐个复制完整数据
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
  console.log('启动浏览器（登录态已保存）...');
  const context = await chromium.launchPersistentContext(USER_DATA_DIR, {
    executablePath: CHROME_PATH,
    headless: false,
    viewport: null,
    args: ['--start-maximized', '--disable-blink-features=AutomationControlled']
  });
  await context.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: 'https://shimo.im' });
  const pages = context.pages();
  const page = pages.length > 0 ? pages[0] : await context.newPage();

  console.log('打开石墨文档...');
  await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
  try { await page.waitForSelector('.sm-sheet-tab-item', { timeout: 30000 }); } catch (e) {}
  await page.waitForTimeout(6000);

  // 获取所有sheet名称（13个）
  const sheetNames = await page.evaluate(() => {
    const tabs = document.querySelectorAll('.sm-sheet-tab-item');
    const names = [];
    tabs.forEach(tab => {
      const nameEl = tab.querySelector('.sm-sheet-tab-name');
      const name = nameEl ? nameEl.innerText.trim() : '';
      if (name) names.push(name);
    });
    return names;
  });
  console.log('\n找到 ' + sheetNames.length + ' 个sheet:');
  sheetNames.forEach((n, i) => console.log('  ' + (i + 1) + '. ' + n));

  const allData = {};

  // 遍历每个sheet
  for (let i = 0; i < sheetNames.length; i++) {
    const sheetName = sheetNames[i];
    console.log('\n=== [' + (i + 1) + '/' + sheetNames.length + '] 复制sheet: ' + sheetName + ' ===');

    // 切换到该sheet：点击对应的tab
    try {
      // 用文本定位sheet tab并点击
      const clicked = await page.evaluate((name) => {
        const tabs = document.querySelectorAll('.sm-sheet-tab-item');
        for (const tab of tabs) {
          const nameEl = tab.querySelector('.sm-sheet-tab-name');
          if (nameEl && nameEl.innerText.trim() === name) {
            tab.scrollIntoView({ block: 'nearest', inline: 'nearest' });
            (nameEl).click();
            return true;
          }
        }
        return false;
      }, sheetName);
      console.log('  切换' + (clicked ? '成功' : '失败'));
    } catch (e) { console.log('  切换异常:', e.message); }

    // 等待sheet渲染
    await page.waitForTimeout(3500);

    // 获取canvas位置
    const canvasInfo = await page.evaluate(() => {
      const c = document.querySelector('canvas');
      if (!c) return null;
      const r = c.getBoundingClientRect();
      return { x: r.x, y: r.y, w: r.width, h: r.height };
    });
    if (!canvasInfo) { console.log('  无canvas，跳过'); allData[sheetName] = { error: '无canvas' }; continue; }

    // 清空剪贴板（写入空）
    await page.evaluate(async () => { try { await navigator.clipboard.writeText(''); } catch (e) {} });
    await page.waitForTimeout(300);

    // 方式C：点击canvas左上角全选区 → Ctrl+C
    await page.mouse.click(canvasInfo.x + 15, canvasInfo.y + 15);
    await page.waitForTimeout(800);
    // 加Ctrl+A双保险
    await page.keyboard.press('Control+A');
    await page.waitForTimeout(1200);
    await page.keyboard.press('Control+C');
    await page.waitForTimeout(2500);

    // 读取系统剪贴板
    let clipText = '';
    try {
      clipText = await page.evaluate(async () => { try { return await navigator.clipboard.readText(); } catch (e) { return 'ERR:' + e.message; } });
    } catch (e) { clipText = 'ERR:' + e.message; }

    if (clipText && !clipText.startsWith('ERR:') && clipText.length > 10) {
      console.log('  ✓ 复制成功！长度: ' + clipText.length + ' 字符, 行数: ' + clipText.split('\n').length);
      console.log('  预览(前120): ' + clipText.substring(0, 120).replace(/\n/g, '\\n'));
      allData[sheetName] = { length: clipText.length, rows: clipText.split('\n').length, cols: clipText.split('\n')[0] ? clipText.split('\n')[0].split('\t').length : 0, data: clipText };
      // 保存单独TSV文件
      const safeName = sheetName.replace(/[\/\\:*?"<>|]/g, '_');
      fs.writeFileSync(path.join(DATA_OUTPUT, `sheet_${String(i + 1).padStart(2, '0')}_${safeName}.tsv`), clipText, 'utf-8');
    } else {
      console.log('  ✗ 复制失败: ' + (clipText || '').substring(0, 100));
      // 重试：方式A
      console.log('  重试方式A...');
      await page.mouse.click(canvasInfo.x + 200, canvasInfo.y + 80);
      await page.waitForTimeout(800);
      await page.keyboard.press('Control+A');
      await page.waitForTimeout(1200);
      await page.keyboard.press('Control+C');
      await page.waitForTimeout(2500);
      clipText = await page.evaluate(async () => { try { return await navigator.clipboard.readText(); } catch (e) { return 'ERR:' + e.message; } });
      if (clipText && !clipText.startsWith('ERR:') && clipText.length > 10) {
        console.log('  ✓ 重试成功！长度: ' + clipText.length);
        allData[sheetName] = { length: clipText.length, rows: clipText.split('\n').length, cols: clipText.split('\n')[0] ? clipText.split('\n')[0].split('\t').length : 0, data: clipText };
        const safeName = sheetName.replace(/[\/\\:*?"<>|]/g, '_');
        fs.writeFileSync(path.join(DATA_OUTPUT, `sheet_${String(i + 1).padStart(2, '0')}_${safeName}.tsv`), clipText, 'utf-8');
      } else {
        console.log('  ✗ 重试仍失败');
        allData[sheetName] = { error: '复制失败', detail: (clipText || '').substring(0, 200) };
      }
    }
  }

  // 保存汇总JSON（不含data，只含元信息）
  const summary = {};
  for (const [name, info] of Object.entries(allData)) {
    summary[name] = { length: info.length, rows: info.rows, cols: info.cols, error: info.error };
  }
  fs.writeFileSync(path.join(DATA_OUTPUT, 'all_sheets_summary.json'), JSON.stringify(summary, null, 2), 'utf-8');
  console.log('\n=== 汇总 ===');
  for (const [name, info] of Object.entries(summary)) {
    console.log('  ' + name + ': ' + (info.error ? '失败(' + info.error + ')' : info.length + '字符/' + info.rows + '行'));
  }
  // 保存完整数据（含data）的大JSON
  fs.writeFileSync(path.join(DATA_OUTPUT, 'all_sheets_full.json'), JSON.stringify(allData, null, 2), 'utf-8');
  console.log('\n完整数据已保存到: ' + DATA_OUTPUT);
  console.log('  - all_sheets_summary.json (汇总)');
  console.log('  - all_sheets_full.json (完整数据)');
  console.log('  - sheet_XX_名称.tsv (每个sheet单独)');

  console.log('\n完成');
  await page.waitForTimeout(3000);
  await context.close();
})().catch(e => { console.error('脚本错误:', e); process.exit(1); });
