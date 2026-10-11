// 石墨文档 - 登录 + 导出xlsx
const { chromium } = require('playwright-core');
const fs = require('fs');
const path = require('path');

const CHROME_PATH = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const USER_DATA_DIR = path.join(__dirname, '.shimo_data');
const OUTPUT_DIR = path.join(__dirname, 'shimo_capture');
const DATA_OUTPUT = path.join(__dirname, 'shimo_raw_data');
const URL = 'https://shimo.im/sheets/473QMXrrL4F7p53w/dJr6p';
const GUID = '473QMXrrL4F7p53w';

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
  const pages = context.pages();
  const page = pages.length > 0 ? pages[0] : await context.newPage();

  console.log('打开石墨文档...');
  await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(4000);

  // ========== 1. 检测登录状态 ==========
  console.log('\n=== 1. 检测登录状态 ===');
  const loginStatus = await page.evaluate(async () => {
    try {
      const r = await fetch('/lizard-api/users/me', { credentials: 'include' });
      if (r.ok) {
        const j = await r.json();
        return { loggedIn: true, name: j.name, email: j.email, id: j.id };
      }
      return { loggedIn: false, status: r.status };
    } catch (e) { return { loggedIn: false, error: e.message }; }
  });
  console.log('登录状态:', JSON.stringify(loginStatus));

  // ========== 2. 如果未登录，等待用户登录 ==========
  if (!loginStatus.loggedIn) {
    console.log('\n========================================');
    console.log('⚠️  当前未登录石墨文档！');
    console.log('请在弹出的浏览器窗口中登录石墨账号。');
    console.log('你可以：');
    console.log('  1. 访问 https://shimo.im 登录');
    console.log('  2. 用公司邮箱（@qinsilk.com）或微信扫码登录');
    console.log('登录成功后，脚本会自动继续。');
    console.log('（最多等待5分钟）');
    console.log('========================================\n');

    // 导航到登录页
    await page.goto('https://shimo.im/login?from=home', { waitUntil: 'domcontentloaded', timeout: 60000 });

    // 等待登录完成（users/me返回200）
    try {
      await page.waitForFunction(async () => {
        try {
          const r = await fetch('/lizard-api/users/me', { credentials: 'include' });
          return r.ok;
        } catch (e) { return false; }
      }, { timeout: 300000 });
      console.log('✓ 登录成功！');
    } catch (e) {
      console.log('登录等待超时，尝试继续...');
    }

    // 登录后重新打开文档
    console.log('重新打开文档...');
    await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForTimeout(5000);

    const loginStatus2 = await page.evaluate(async () => {
      try {
        const r = await fetch('/lizard-api/users/me', { credentials: 'include' });
        if (r.ok) { const j = await r.json(); return { loggedIn: true, name: j.name }; }
        return { loggedIn: false };
      } catch (e) { return { loggedIn: false, error: e.message }; }
    });
    console.log('登录状态:', JSON.stringify(loginStatus2));
    if (!loginStatus2.loggedIn) {
      console.log('仍未登录，无法导出。请确认已登录石墨账号。');
      console.log('浏览器保持打开60秒，你可以手动登录后告诉我。');
      await page.waitForTimeout(60000);
      await context.close();
      return;
    }
  }

  // ========== 3. 获取文件元数据，检查导出权限 ==========
  console.log('\n=== 3. 检查导出权限 ===');
  const meta = await page.evaluate(async (guid) => {
    try {
      const r = await fetch(`/lizard-api/files/${guid}`, { credentials: 'include' });
      const j = await r.json();
      return { status: r.status, permissions: j.permissions, name: j.name, type: j.type, contentUrl: j.contentUrl };
    } catch (e) { return { error: e.message }; }
  }, GUID);
  console.log('文件:', meta.name, '类型:', meta.type);
  console.log('权限:', JSON.stringify(meta.permissions));

  // ========== 4. 尝试多种导出方式 ==========
  console.log('\n=== 4. 尝试导出xlsx ===');
  const exportResult = await page.evaluate(async (guid) => {
    const out = { attempts: [] };
    const apis = [
      { name: 'download_xlsx', method: 'GET', url: `/lizard-api/files/${guid}/download?type=xlsx` },
      { name: 'download_xlsx_post', method: 'POST', url: `/lizard-api/files/${guid}/download`, body: { type: 'xlsx' } },
      { name: 'export_xlsx', method: 'POST', url: `/lizard-api/files/${guid}/export`, body: { type: 'xlsx', file: {} } },
      { name: 'export_xlsx_v2', method: 'POST', url: `/lizard-api/files/${guid}/export`, body: { type: 'xlsx' } },
      { name: 'panda_export', method: 'POST', url: `/panda-api/file/files/${guid}/export`, body: { type: 'xlsx' } },
      { name: 'panda_download', method: 'GET', url: `/panda-api/file/files/${guid}/download?type=xlsx` },
      { name: 'api_download', method: 'GET', url: `/api/files/${guid}/download?type=xlsx` },
    ];
    for (const a of apis) {
      try {
        const opt = { method: a.method, credentials: 'include', headers: { 'Content-Type': 'application/json' } };
        if (a.body) opt.body = JSON.stringify(a.body);
        const r = await fetch(a.url, opt);
        const ct = r.headers.get('content-type') || '';
        const cd = r.headers.get('content-disposition') || '';
        let bodyInfo;
        if (ct.includes('json')) {
          const t = await r.text();
          bodyInfo = { type: 'json', len: t.length, preview: t.substring(0, 300) };
        } else if (ct.includes('octet-stream') || ct.includes('spreadsheet') || ct.includes('application/vnd') || r.status === 200) {
          const blob = await r.blob();
          bodyInfo = { type: 'blob', size: blob.size, contentType: ct, contentDisposition: cd };
          // 如果是文件，转base64
          if (blob.size > 100 && blob.size < 50000000) {
            const buf = await blob.arrayBuffer();
            bodyInfo.base64 = btoa(String.fromCharCode(...new Uint8Array(buf.slice(0, 1000))));  // 前1000字节样本
            bodyInfo.fullSize = buf.byteLength;
          }
        } else {
          const t = await r.text();
          bodyInfo = { type: ct, len: t.length, preview: t.substring(0, 200) };
        }
        out.attempts.push({ name: a.name, status: r.status, contentType: ct, contentDisposition: cd, bodyInfo });
      } catch (e) {
        out.attempts.push({ name: a.name, error: e.message });
      }
    }
    return out;
  }, GUID);

  let successExport = null;
  for (const a of exportResult.attempts) {
    console.log(`\n  [${a.name}] status=${a.status} ct=${a.contentType || ''} cd=${a.contentDisposition || ''}`);
    if (a.bodyInfo) {
      console.log(`    body: type=${a.bodyInfo.type} ${a.bodyInfo.size !== undefined ? 'size=' + a.bodyInfo.size : ''} ${a.bodyInfo.len !== undefined ? 'len=' + a.bodyInfo.len : ''}`);
      if (a.bodyInfo.preview) console.log('    preview:', a.bodyInfo.preview.substring(0, 150));
      if (a.bodyInfo.type === 'blob' && a.bodyInfo.size > 1000) {
        console.log(`    ✓ 可能是文件！size=${a.bodyInfo.size} ct=${a.bodyInfo.contentType}`);
        successExport = a;
      }
    }
    if (a.error) console.log('    error:', a.error);
  }
  fs.writeFileSync(path.join(OUTPUT_DIR, 'export_attempts_logged.json'), JSON.stringify(exportResult, null, 2), 'utf-8');

  // ========== 5. 如果有成功的导出，下载完整文件 ==========
  if (successExport) {
    console.log('\n=== 5. 下载完整导出文件 ===');
    const a = successExport;
    const fullFile = await page.evaluate(async (guid, apiUrl, method, body) => {
      const opt = { method, credentials: 'include' };
      if (body) { opt.headers = { 'Content-Type': 'application/json' }; opt.body = JSON.stringify(body); }
      const r = await fetch(apiUrl, opt);
      const blob = await r.blob();
      const buf = await blob.arrayBuffer();
      // 转base64
      const arr = new Uint8Array(buf);
      let binary = '';
      for (let i = 0; i < arr.length; i++) binary += String.fromCharCode(arr[i]);
      return { base64: btoa(binary), size: arr.length, contentType: blob.type };
    }, GUID,
      a.name.startsWith('panda') ? (a.name.includes('export') ? `/panda-api/file/files/${GUID}/export` : `/panda-api/file/files/${GUID}/download?type=xlsx`) : (a.name.includes('download') ? `/lizard-api/files/${GUID}/download?type=xlsx` : `/lizard-api/files/${GUID}/export`),
      a.name.includes('download') ? 'GET' : 'POST',
      a.name.includes('export') ? { type: 'xlsx' } : null
    );
    // 保存base64为文件
    if (fullFile && fullFile.base64) {
      const buf = Buffer.from(fullFile.base64, 'base64');
      const outPath = path.join(DATA_OUTPUT, `导出_${meta.name || GUID}.xlsx`);
      fs.writeFileSync(outPath, buf);
      console.log(`✓ 已保存: ${outPath} (${buf.length} 字节)`);
    }
  } else {
    console.log('\n所有API导出均失败。将尝试通过页面菜单导出...');
    console.log('浏览器保持打开，可手动操作下载。');
  }

  console.log('\n完成。浏览器保持打开30秒。');
  await page.waitForTimeout(30000);
  await context.close();
})().catch(e => { console.error('脚本错误:', e); process.exit(1); });
