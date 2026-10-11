// 石墨文档抓取探测脚本
// 打开石墨文档，监听所有网络请求，尝试导出xlsx，记录API结构
const { chromium } = require('playwright-core');
const fs = require('fs');
const path = require('path');

const CHROME_PATH = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const USER_DATA_DIR = path.join(__dirname, '.shimo_data');
const OUTPUT_DIR = path.join(__dirname, 'shimo_capture');
const URL = 'https://shimo.im/sheets/473QMXrrL4F7p53w/dJr6p';

if (!fs.existsSync(OUTPUT_DIR)) fs.mkdirSync(OUTPUT_DIR, { recursive: true });

const captured = [];          // 所有请求/响应记录
const responsesBody = {};     // 重要响应body

(async () => {
  console.log('启动浏览器（石墨专用持久化目录）...');
  const context = await chromium.launchPersistentContext(USER_DATA_DIR, {
    executablePath: CHROME_PATH,
    headless: false,
    viewport: null,
    args: ['--start-maximized', '--disable-blink-features=AutomationControlled']
  });

  const pages = context.pages();
  const page = pages.length > 0 ? pages[0] : await context.newPage();

  // 监听所有响应
  page.on('response', async (resp) => {
    try {
      const url = resp.url();
      const status = resp.status();
      const ct = resp.headers()['content-type'] || '';
      const entry = { url, status, contentType: ct };
      // 只记录API类请求（排除静态资源）
      if (url.includes('lizard-api') || url.includes('/api/') || url.includes('shimo.im/api') || url.includes('/files/') || url.includes('/sheets/') || url.includes('export') || url.includes('download')) {
        entry.isApi = true;
        try {
          if (ct.includes('json') || ct.includes('text')) {
            const body = await resp.text();
            entry.body = body.length > 20000 ? body.substring(0, 20000) + '...[truncated]' : body;
            entry.bodyLen = body.length;
          }
        } catch (e) { entry.bodyError = e.message; }
      }
      captured.push(entry);
    } catch (e) {}
  });

  console.log('打开石墨文档:', URL);
  await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 60000 });

  // 检测是否需要登录
  await page.waitForTimeout(4000);
  let curUrl = page.url();
  console.log('当前URL:', curUrl);

  const needsLogin = await page.evaluate(() => {
    const t = document.body ? document.body.innerText : '';
    return t.includes('登录') && (t.includes('立即登录') || t.includes('扫码登录') || t.includes('密码登录')) && !t.includes('销售部线索');
  });

  if (needsLogin || curUrl.includes('login') || curUrl.includes('welcome')) {
    console.log('\n========================================');
    console.log('⚠️  需要登录石墨文档！');
    console.log('请在弹出的浏览器窗口中完成登录（扫码或账号密码）。');
    console.log('登录后会自动跳转回表格，脚本将继续抓取。');
    console.log('等待登录中...（最多5分钟）');
    console.log('========================================\n');
    try {
      // 等待URL回到sheets或文档内容出现
      await page.waitForFunction(() => {
        const t = document.body ? document.body.innerText : '';
        return t.includes('销售部线索') || (location.href.includes('shimo.im/sheets') && !t.includes('立即登录'));
      }, { timeout: 300000 });
      console.log('登录成功！当前URL:', page.url());
    } catch (e) {
      console.log('登录等待超时，尝试继续...');
    }
  } else {
    console.log('已有登录态，直接读取');
  }

  // 重新加载以确保捕获所有API请求
  console.log('\n重新加载页面以捕获所有API请求...');
  captured.length = 0;
  await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(8000);  // 等待数据加载

  // 检测sheet数量和表头
  console.log('\n=== 页面探测 ===');
  const probe = await page.evaluate(() => {
    const info = {};
    info.title = document.title;
    info.url = location.href;
    info.bodyTextSample = document.body ? document.body.innerText.substring(0, 1000) : '';
    // sheet标签
    const sheetTabs = Array.from(document.querySelectorAll('[class*="sheet"][class*="tab"], [class*="SheetTab"], .sheet-name, [data-sheet-name]')).map(e => e.innerText || e.textContent).filter(Boolean);
    info.sheetTabs = sheetTabs.slice(0, 30);
    // 查找所有可能的sheet标签（石墨用canvas，可能没有DOM）
    info.allCanvas = document.querySelectorAll('canvas').length;
    // window对象探测
    try {
      info.windowKeys = Object.keys(window).filter(k => /shimo|lizard|sheet|doc|file/i.test(k)).slice(0, 50);
    } catch(e) { info.windowKeysError = e.message; }
    return info;
  });
  console.log('Title:', probe.title);
  console.log('Sheet标签:', JSON.stringify(probe.sheetTabs));
  console.log('Canvas数量:', probe.allCanvas);
  console.log('Window相关变量:', JSON.stringify(probe.windowKeys));
  console.log('页面文本样本:', probe.bodyTextSample.substring(0, 300));

  // 尝试从guid提取fileId
  const guid = URL.split('/sheets/')[1].split('/')[0];
  console.log('\n文档GUID:', guid);

  // 尝试调用石墨导出API
  console.log('\n=== 尝试导出API ===');
  const exportAttempts = await page.evaluate(async (guid) => {
    const results = {};
    const apis = [
      { name: 'export_xlsx_post', url: `/lizard-api/files/${guid}/export`, method: 'POST', body: { type: 'xlsx', file: {} } },
      { name: 'export_xlsx_post2', url: `/lizard-api/files/${guid}/export`, method: 'POST', body: { type: 'xlsx' } },
      { name: 'download_xlsx', url: `/lizard-api/files/${guid}/download?type=xlsx`, method: 'GET', body: null },
      { name: 'files_meta', url: `/lizard-api/files/${guid}`, method: 'GET', body: null },
      { name: 'sheets_list', url: `/lizard-api/files/${guid}/sheets`, method: 'GET', body: null },
      { name: 'api_files', url: `/api/files/${guid}`, method: 'GET', body: null },
    ];
    for (const a of apis) {
      try {
        const opt = { method: a.method, headers: { 'Content-Type': 'application/json' } };
        if (a.body) opt.body = JSON.stringify(a.body);
        const resp = await fetch('https://shimo.im' + a.url, opt);
        const text = await resp.text();
        results[a.name] = { status: resp.status, ct: resp.headers.get('content-type'), body: text.substring(0, 3000), bodyLen: text.length };
      } catch (e) {
        results[a.name] = { error: e.message };
      }
    }
    return results;
  }, guid);

  for (const [name, res] of Object.entries(exportAttempts)) {
    console.log(`\n[${name}]`);
    if (res.status) {
      console.log(`  status=${res.status} ct=${res.ct} len=${res.bodyLen}`);
      console.log(`  body: ${res.body.substring(0, 500)}`);
    } else {
      console.log(`  error: ${res.error}`);
    }
  }

  // 保存所有捕获的请求
  const apiCalls = captured.filter(c => c.isApi);
  console.log(`\n=== 捕获到 ${captured.length} 个请求，其中 ${apiCalls.length} 个API请求 ===`);
  console.log('API请求列表:');
  apiCalls.forEach((c, i) => {
    console.log(`  [${i}] ${c.status} ${c.url.substring(0, 120)}`);
  });

  fs.writeFileSync(path.join(OUTPUT_DIR, 'captured_requests.json'), JSON.stringify(captured, null, 2), 'utf-8');
  fs.writeFileSync(path.join(OUTPUT_DIR, 'export_attempts.json'), JSON.stringify(exportAttempts, null, 2), 'utf-8');
  fs.writeFileSync(path.join(OUTPUT_DIR, 'page_probe.json'), JSON.stringify(probe, null, 2), 'utf-8');
  console.log(`\n捕获结果保存到: ${OUTPUT_DIR}/`);

  console.log('\n探测完成。浏览器保持打开20秒供观察...');
  await page.waitForTimeout(20000);
  await context.close();
})().catch(e => { console.error('脚本错误:', e); process.exit(1); });
