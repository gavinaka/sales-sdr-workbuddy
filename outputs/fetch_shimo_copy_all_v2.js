// 石墨文档 - 遍历13个sheet复制 v2（playwright locator点击 + 切换验证）
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

  // 获取所有sheet名称
  const sheetNames = await page.evaluate(() => {
    const names = [];
    document.querySelectorAll('.sm-sheet-tab-item').forEach(tab => {
      const nameEl = tab.querySelector('.sm-sheet-tab-name');
      const name = nameEl ? nameEl.innerText.trim() : '';
      if (name) names.push(name);
    });
    return names;
  });
  console.log('\n找到 ' + sheetNames.length + ' 个sheet:');
  sheetNames.forEach((n, i) => console.log('  ' + (i + 1) + '. ' + n));

  const allData = {};
  let lastClipPreview = '';

  for (let i = 0; i < sheetNames.length; i++) {
    const sheetName = sheetNames[i];
    console.log('\n=== [' + (i + 1) + '/' + sheetNames.length + '] ' + sheetName + ' ===');

    // 用playwright locator点击sheet tab（触发真实React事件）
    let switched = false;
    for (let attempt = 0; attempt < 3 && !switched; attempt++) {
      try {
        // 定位目标sheet tab的name元素
        const tabName = page.locator('.sm-sheet-tab-name', { hasText: sheetName }).first();
        await tabName.scrollIntoViewIfNeeded({ timeout: 5000 });
        await tabName.click({ timeout: 5000 });
        await page.waitForTimeout(2000);
        // 验证是否切换成功
        const activeName = await page.evaluate(() => {
          const a = document.querySelector('.sm-sheet-tab-item.active-tab .sm-sheet-tab-name');
          return a ? a.innerText.trim() : '';
        });
        if (activeName === sheetName) {
          switched = true;
          console.log('  切换成功 (尝试' + (attempt + 1) + ')');
        } else {
          console.log('  切换验证失败，active=' + activeName + ' (尝试' + (attempt + 1) + ')');
          await page.waitForTimeout(2000);
        }
      } catch (e) {
        console.log('  点击异常(尝试' + (attempt + 1) + '):', e.message.substring(0, 80));
        await page.waitForTimeout(2000);
      }
    }
    if (!switched) { console.log('  ✗ 切换失败，跳过'); allData[sheetName] = { error: '切换失败' }; continue; }

    // 等待canvas渲染新sheet
    await page.waitForTimeout(4000);

    const canvasInfo = await page.evaluate(() => {
      const c = document.querySelector('canvas');
      if (!c) return null;
      const r = c.getBoundingClientRect();
      return { x: r.x, y: r.y, w: r.width, h: r.height };
    });
    if (!canvasInfo) { allData[sheetName] = { error: '无canvas' }; continue; }

    // 复制：点击canvas左上角全选 → Ctrl+A → Ctrl+C
    let clipText = '';
    let copySuccess = false;
    for (let copyAttempt = 0; copyAttempt < 3 && !copySuccess; copyAttempt++) {
      // 清空剪贴板
      await page.evaluate(async () => { try { await navigator.clipboard.writeText(''); } catch (e) {} });
      await page.waitForTimeout(300);
      // 点击canvas左上角全选区
      await page.mouse.click(canvasInfo.x + 15, canvasInfo.y + 15);
      await page.waitForTimeout(800);
      await page.keyboard.press('Control+A');
      await page.waitForTimeout(1200);
      await page.keyboard.press('Control+C');
      await page.waitForTimeout(2500);
      // 读取剪贴板
      clipText = await page.evaluate(async () => { try { return await navigator.clipboard.readText(); } catch (e) { return 'ERR:' + e.message; } });
      const preview = (clipText || '').substring(0, 100);
      // 验证：数据不为空，且不和已有任何sheet完全相同（避免未切换的重复）
      if (clipText && !clipText.startsWith('ERR:') && clipText.length > 10) {
        const prevDataList = Object.values(allData).map(d => d.data).filter(Boolean);
        const isFullDup = prevDataList.some(d => d === clipText);
        if (!isFullDup) {
          copySuccess = true;
          lastClipPreview = preview;
        } else {
          console.log('  数据与已有sheet完全相同，可能未切换(尝试' + (copyAttempt + 1) + ')');
        }
      } else {
        console.log('  复制验证失败(尝试' + (copyAttempt + 1) + '): len=' + (clipText || '').length);
      }
    }

    if (copySuccess) {
      console.log('  ✓ 复制成功！长度: ' + clipText.length + ' 字符, 行数: ' + clipText.split('\n').length);
      console.log('  预览: ' + clipText.substring(0, 120).replace(/\n/g, '\\n').substring(0, 100));
      allData[sheetName] = { length: clipText.length, rows: clipText.split('\n').length, cols: clipText.split('\n')[0] ? clipText.split('\n')[0].split('\t').length : 0, data: clipText };
      const safeName = sheetName.replace(/[\/\\:*?"<>|]/g, '_');
      fs.writeFileSync(path.join(DATA_OUTPUT, `sheet_${String(i + 1).padStart(2, '0')}_${safeName}.tsv`), clipText, 'utf-8');
    } else {
      console.log('  ✗ 复制失败: ' + (clipText || '').substring(0, 100));
      allData[sheetName] = { error: '复制失败', detail: (clipText || '').substring(0, 200) };
    }
  }

  // 汇总
  const summary = {};
  for (const [name, info] of Object.entries(allData)) {
    summary[name] = { length: info.length, rows: info.rows, cols: info.cols, error: info.error };
  }
  fs.writeFileSync(path.join(DATA_OUTPUT, 'all_sheets_summary.json'), JSON.stringify(summary, null, 2), 'utf-8');
  fs.writeFileSync(path.join(DATA_OUTPUT, 'all_sheets_full.json'), JSON.stringify(allData, null, 2), 'utf-8');
  console.log('\n=== 汇总 ===');
  let totalLen = 0, okCount = 0;
  for (const [name, info] of Object.entries(summary)) {
    if (info.error) { console.log('  ' + name + ': ✗ ' + info.error); }
    else { console.log('  ' + name + ': ✓ ' + info.length + '字符/' + info.rows + '行/' + info.cols + '列'); totalLen += info.length; okCount++; }
  }
  console.log('\n成功: ' + okCount + '/' + sheetNames.length + ', 总数据量: ' + totalLen + ' 字符');
  console.log('数据目录: ' + DATA_OUTPUT);

  console.log('\n完成');
  await page.waitForTimeout(3000);
  await context.close();
})().catch(e => { console.error('脚本错误:', e); process.exit(1); });
