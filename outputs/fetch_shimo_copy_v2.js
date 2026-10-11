// 石墨文档 - 复制法v2（登录态已保存，copyable:true）
// 聚焦input + 多种全选/复制方式 + 详细诊断
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

  // 注入copy事件监听器（capture + bubble）+ clipboard hook
  await page.addInitScript(() => {
    window.__copyEvents = [];
    window.__clipboardWrite = [];
    // 监听copy事件（capture和bubble）
    document.addEventListener('copy', (e) => {
      const data = { phase: 'capture', types: [], contents: {}, defaultPrevented: false };
      try {
        data.types = Array.from(e.clipboardData ? e.clipboardData.types : []);
        for (const t of data.types) { try { data.contents[t] = (e.clipboardData.getData(t) || '').substring(0, 2000); } catch (err) {} }
      } catch (err) {}
      window.__copyEvents.push(data);
    }, true);
    document.addEventListener('copy', (e) => {
      const data = { phase: 'bubble', types: [], contents: {}, defaultPrevented: false };
      try {
        data.types = Array.from(e.clipboardData ? e.clipboardData.types : []);
        for (const t of data.types) { try { data.contents[t] = (e.clipboardData.getData(t) || '').substring(0, 5000); } catch (err) {} }
        data.defaultPrevented = e.defaultPrevented;
      } catch (err) {}
      window.__copyEvents.push(data);
    }, false);
    // hook navigator.clipboard.writeText
    if (navigator.clipboard && navigator.clipboard.writeText) {
      const orig = navigator.clipboard.writeText.bind(navigator.clipboard);
      navigator.clipboard.writeText = function (text) {
        window.__clipboardWrite.push({ method: 'writeText', len: text.length, preview: text.substring(0, 2000) });
        return orig(text);
      };
    }
    // hook execCommand
    const origExec = document.execCommand.bind(document);
    document.execCommand = function (cmd, ...args) {
      if (cmd === 'copy') { window.__clipboardWrite.push({ method: 'execCommand', cmd }); }
      return origExec(cmd, ...args);
    };
  });

  console.log('打开石墨文档...');
  await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
  try { await page.waitForSelector('.sm-sheet-tab-item', { timeout: 30000 }); } catch (e) {}
  await page.waitForTimeout(6000);

  // 清空记录
  await page.evaluate(() => { window.__copyEvents = []; window.__clipboardWrite = []; });

  // ========== 方式A: 点击canvas → Ctrl+A → Ctrl+C ==========
  console.log('\n=== 方式A: 点击canvas → Ctrl+A → Ctrl+C ===');
  const canvasInfo = await page.evaluate(() => {
    const c = document.querySelector('canvas');
    if (!c) return null;
    const r = c.getBoundingClientRect();
    return { x: r.x, y: r.y, w: r.width, h: r.height };
  });
  console.log('canvas:', JSON.stringify(canvasInfo));
  if (canvasInfo) {
    // 点击canvas内容区（避开行号列和表头行，点击B2附近）
    await page.mouse.click(canvasInfo.x + 200, canvasInfo.y + 80);
    await page.waitForTimeout(800);
    const ae1 = await page.evaluate(() => ({ tag: document.activeElement.tagName, cls: (document.activeElement.className || '').substring(0, 50), id: document.activeElement.id }));
    console.log('点击后焦点:', JSON.stringify(ae1));
    // Ctrl+A
    await page.keyboard.press('Control+A');
    await page.waitForTimeout(1000);
    // Ctrl+C
    await page.keyboard.press('Control+C');
    await page.waitForTimeout(2000);
    const resA = await page.evaluate(async () => ({
      copyEvents: window.__copyEvents,
      clipboardWrites: window.__clipboardWrite,
      systemClipboard: (() => { try { return null; } catch(e){ return null; } })()
    }));
    console.log('copy事件数:', resA.copyEvents.length);
    resA.copyEvents.forEach((e, i) => console.log(`  事件${i}[${e.phase}]: types=${JSON.stringify(e.types)} defaultPrevented=${e.defaultPrevented} plain=${(e.contents['text/plain'] || '').substring(0, 80)}`));
    console.log('clipboard写入:', JSON.stringify(resA.clipboardWrites));
    const sysClipA = await page.evaluate(async () => { try { return await navigator.clipboard.readText(); } catch(e) { return 'ERR:'+e.message; } });
    console.log('系统剪贴板:', sysClipA ? ('len=' + sysClipA.length + ' preview=' + sysClipA.substring(0, 100)) : 'null');
    await page.evaluate(() => { window.__copyEvents = []; window.__clipboardWrite = []; });
  }

  // ========== 方式B: 聚焦.sm-sheet-input → Ctrl+A → Ctrl+C ==========
  console.log('\n=== 方式B: 聚焦.sm-sheet-input → Ctrl+A → Ctrl+C ===');
  const inputInfo = await page.evaluate(() => {
    const inp = document.querySelector('.sm-sheet-input');
    if (!inp) return null;
    const r = inp.getBoundingClientRect();
    return { x: r.x, y: r.y, w: r.width, h: r.height, visible: r.width > 0 && r.height > 0, tag: inp.tagName, type: inp.type };
  });
  console.log('input:', JSON.stringify(inputInfo));
  if (inputInfo) {
    await page.evaluate(() => { const i = document.querySelector('.sm-sheet-input'); if (i) i.focus(); });
    await page.waitForTimeout(500);
    const ae2 = await page.evaluate(() => ({ tag: document.activeElement.tagName, cls: (document.activeElement.className || '').substring(0, 50) }));
    console.log('聚焦后焦点:', JSON.stringify(ae2));
    await page.keyboard.press('Control+A');
    await page.waitForTimeout(1000);
    await page.keyboard.press('Control+C');
    await page.waitForTimeout(2000);
    const resB = await page.evaluate(() => ({ copyEvents: window.__copyEvents, clipboardWrites: window.__clipboardWrite }));
    console.log('copy事件数:', resB.copyEvents.length);
    resB.copyEvents.forEach((e, i) => console.log(`  事件${i}[${e.phase}]: types=${JSON.stringify(e.types)} plain=${(e.contents['text/plain'] || '').substring(0, 80)}`));
    console.log('clipboard写入:', JSON.stringify(resB.clipboardWrites));
    await page.evaluate(() => { window.__copyEvents = []; window.__clipboardWrite = []; });
  }

  // ========== 方式C: 点击canvas左上角全选区 → Ctrl+C ==========
  console.log('\n=== 方式C: 点击canvas左上角(全选区) → Ctrl+C ===');
  if (canvasInfo) {
    // 表格左上角通常是全选按钮（行号列与列头行交叉）
    await page.mouse.click(canvasInfo.x + 15, canvasInfo.y + 15);
    await page.waitForTimeout(1000);
    const ae3 = await page.evaluate(() => ({ tag: document.activeElement.tagName, cls: (document.activeElement.className || '').substring(0, 50) }));
    console.log('全选点击后焦点:', JSON.stringify(ae3));
    await page.keyboard.press('Control+C');
    await page.waitForTimeout(2000);
    const resC = await page.evaluate(() => ({ copyEvents: window.__copyEvents, clipboardWrites: window.__clipboardWrite }));
    console.log('copy事件数:', resC.copyEvents.length);
    resC.copyEvents.forEach((e, i) => console.log(`  事件${i}[${e.phase}]: types=${JSON.stringify(e.types)} plain=${(e.contents['text/plain'] || '').substring(0, 80)}`));
    console.log('clipboard写入:', JSON.stringify(resC.clipboardWrites));
    const sysClipC = await page.evaluate(async () => { try { return await navigator.clipboard.readText(); } catch(e) { return 'ERR:'+e.message; } });
    console.log('系统剪贴板:', sysClipC ? ('len=' + sysClipC.length + ' preview=' + sysClipC.substring(0, 100)) : 'null');
    await page.evaluate(() => { window.__copyEvents = []; window.__clipboardWrite = []; });
  }

  // ========== 方式D: 点击canvas单元格 → Shift+Ctrl+End → Ctrl+C ==========
  console.log('\n=== 方式D: 点击canvas → Shift+Ctrl+End → Ctrl+C ===');
  if (canvasInfo) {
    await page.mouse.click(canvasInfo.x + 200, canvasInfo.y + 80);
    await page.waitForTimeout(500);
    await page.keyboard.press('Shift+Control+End');
    await page.waitForTimeout(1000);
    await page.keyboard.press('Control+C');
    await page.waitForTimeout(2000);
    const resD = await page.evaluate(() => ({ copyEvents: window.__copyEvents, clipboardWrites: window.__clipboardWrite }));
    console.log('copy事件数:', resD.copyEvents.length);
    resD.copyEvents.forEach((e, i) => console.log(`  事件${i}[${e.phase}]: types=${JSON.stringify(e.types)} plain=${(e.contents['text/plain'] || '').substring(0, 80)}`));
    const sysClipD = await page.evaluate(async () => { try { return await navigator.clipboard.readText(); } catch(e) { return 'ERR:'+e.message; } });
    console.log('系统剪贴板:', sysClipD ? ('len=' + sysClipD.length + ' preview=' + sysClipD.substring(0, 100)) : 'null');
    await page.evaluate(() => { window.__copyEvents = []; window.__clipboardWrite = []; });
  }

  console.log('\n诊断完成');
  await page.waitForTimeout(3000);
  await context.close();
})().catch(e => { console.error('脚本错误:', e); process.exit(1); });
