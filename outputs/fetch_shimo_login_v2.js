// 石墨文档 - 稳健登录 + 导出 v2
// 改进：不导航走，在文档页原地等待登录；登录后多方式导出
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
  await page.waitForTimeout(3000);

  // ========== 1. 检测登录（稳健：检查users/me返回200且有用户名） ==========
  console.log('\n=== 1. 检测登录状态 ===');
  let loginOk = false;
  const checkLogin = async () => {
    const r = await page.evaluate(async () => {
      try {
        const resp = await fetch('/lizard-api/users/me', { credentials: 'include' });
        if (resp.ok) { const j = await resp.json(); return { ok: true, name: j.name, email: j.email }; }
        return { ok: false, status: resp.status };
      } catch (e) { return { ok: false, error: e.message }; }
    });
    return r;
  };
  let ls = await checkLogin();
  console.log('初始登录状态:', JSON.stringify(ls));

  if (!ls.ok) {
    console.log('\n========================================');
    console.log('⚠️  未登录石墨文档！');
    console.log('请在浏览器中登录石墨账号：');
    console.log('  方式1: 点击文档页面右上角的「登录」按钮');
    console.log('  方式2: 在浏览器新标签页访问 https://shimo.im 登录');
    console.log('  方式3: 访问 https://shimo.im/login 直接登录');
    console.log('用公司邮箱(@qinsilk.com)或微信扫码登录均可。');
    console.log('登录成功后脚本会自动检测并继续。');
    console.log('（轮询检测，最多等待5分钟）');
    console.log('========================================\n');

    // 轮询检测登录（每5秒一次，最多5分钟）
    const startTime = Date.now();
    while (Date.now() - startTime < 300000) {
      await page.waitForTimeout(5000);
      ls = await checkLogin();
      if (ls.ok) {
        console.log('✓ 检测到登录！用户:', ls.name, ls.email);
        loginOk = true;
        break;
      }
      // 每30秒打印一次等待状态
      if ((Date.now() - startTime) % 30000 < 5000) {
        console.log('  仍在等待登录... (' + Math.round((Date.now() - startTime) / 1000) + '秒)');
      }
    }
    if (!loginOk) {
      console.log('登录等待超时（5分钟）。如已登录请告诉我。');
      console.log('浏览器保持打开120秒...');
      await page.waitForTimeout(120000);
      await context.close();
      return;
    }
    // 登录后重新加载文档页（确保登录态生效）
    console.log('重新加载文档页...');
    await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForTimeout(3000);
    ls = await checkLogin();
    console.log('重载后登录状态:', JSON.stringify(ls));
  } else {
    loginOk = true;
    console.log('已登录:', ls.name, ls.email);
  }

  // ========== 2. 获取文件元数据，检查导出权限 ==========
  console.log('\n=== 2. 检查导出权限 ===');
  const meta = await page.evaluate(async (guid) => {
    try {
      const r = await fetch(`/lizard-api/files/${guid}?encryptedContentUrl=true`, { credentials: 'include' });
      const j = await r.json();
      return { status: r.status, name: j.name, type: j.type, permissions: j.permissions, contentUrl: j.contentUrl };
    } catch (e) { return { error: e.message }; }
  }, GUID);
  console.log('文件:', meta.name, '类型:', meta.type);
  console.log('权限:', JSON.stringify(meta.permissions));

  // ========== 3. 尝试API导出 ==========
  console.log('\n=== 3. 尝试API导出xlsx ===');
  const exportResult = await page.evaluate(async (guid) => {
    const out = { attempts: [] };
    const apis = [
      { name: 'lizard_download', method: 'GET', url: `/lizard-api/files/${guid}/download?type=xlsx` },
      { name: 'lizard_download_post', method: 'POST', url: `/lizard-api/files/${guid}/download`, body: { type: 'xlsx' } },
      { name: 'lizard_export', method: 'POST', url: `/lizard-api/files/${guid}/export`, body: { type: 'xlsx', file: {} } },
      { name: 'lizard_export_v2', method: 'POST', url: `/lizard-api/files/${guid}/export`, body: { type: 'xlsx' } },
      { name: 'panda_export', method: 'POST', url: `/panda-api/file/files/${guid}/export`, body: { type: 'xlsx' } },
      { name: 'panda_download', method: 'GET', url: `/panda-api/file/files/${guid}/download?type=xlsx` },
      { name: 'api_download', method: 'GET', url: `/api/files/${guid}/download?type=xlsx` },
      { name: 'api_export', method: 'POST', url: `/api/files/${guid}/export`, body: { type: 'xlsx' } },
    ];
    for (const a of apis) {
      try {
        const opt = { method: a.method, credentials: 'include', headers: { 'Content-Type': 'application/json' } };
        if (a.body) opt.body = JSON.stringify(a.body);
        const r = await fetch(a.url, opt);
        const ct = r.headers.get('content-type') || '';
        const cd = r.headers.get('content-disposition') || '';
        let bodyInfo = {};
        if (ct.includes('json')) {
          const t = await r.text();
          bodyInfo = { kind: 'json', len: t.length, preview: t.substring(0, 300) };
        } else if (ct.includes('octet-stream') || ct.includes('spreadsheet') || ct.includes('application/vnd') || ct.includes('zip') || (r.ok && r.status === 200 && !ct.includes('text'))) {
          const blob = await r.blob();
          const buf = await blob.arrayBuffer();
          bodyInfo = { kind: 'file', size: blob.size, contentType: ct, contentDisposition: cd, magicHex: Array.from(new Uint8Array(buf.slice(0, 8))).map(b => b.toString(16).padStart(2, '0')).join(' ') };
          // 如果是合理大小的文件，转base64
          if (blob.size > 500 && blob.size < 60000000) {
            const arr = new Uint8Array(buf);
            let bin = '';
            for (let i = 0; i < arr.length; i++) bin += String.fromCharCode(arr[i]);
            bodyInfo.base64 = btoa(bin);
          }
        } else {
          const t = await r.text();
          bodyInfo = { kind: ct || 'text', len: t.length, preview: t.substring(0, 200) };
        }
        out.attempts.push({ name: a.name, method: a.method, url: a.url, status: r.status, contentType: ct, contentDisposition: cd, bodyInfo });
      } catch (e) {
        out.attempts.push({ name: a.name, error: e.message });
      }
    }
    return out;
  }, GUID);

  let successApi = null;
  for (const a of exportResult.attempts) {
    const isFile = a.bodyInfo && a.bodyInfo.kind === 'file' && a.bodyInfo.size > 500;
    console.log(`\n  [${a.name}] ${a.method} ${a.url}`);
    console.log(`    status=${a.status} ct=${a.contentType || ''} ${a.contentDisposition ? 'cd=' + a.contentDisposition : ''}`);
    if (a.bodyInfo) {
      console.log(`    body: kind=${a.bodyInfo.kind} ${a.bodyInfo.size !== undefined ? 'size=' + a.bodyInfo.size : ''} ${a.bodyInfo.len !== undefined ? 'len=' + a.bodyInfo.len : ''} ${a.bodyInfo.magicHex ? 'magic=' + a.bodyInfo.magicHex : ''}`);
      if (a.bodyInfo.preview) console.log('    preview:', a.bodyInfo.preview.substring(0, 150));
      if (isFile) { console.log(`    ✓✓ 疑似文件！`); successApi = a; }
    }
    if (a.error) console.log('    error:', a.error);
  }
  fs.writeFileSync(path.join(OUTPUT_DIR, 'export_api_attempts.json'), JSON.stringify(exportResult, null, 2), 'utf-8');

  // ========== 4. 如果API导出成功，保存文件 ==========
  if (successApi && successApi.bodyInfo && successApi.bodyInfo.base64) {
    console.log('\n=== 4. 保存导出文件 ===');
    const buf = Buffer.from(successApi.bodyInfo.base64, 'base64');
    // 判断格式（magic bytes）
    let ext = 'bin';
    if (buf[0] === 0x50 && buf[1] === 0x4b) ext = 'xlsx';  // PK zip
    else if (buf[0] === 0xd0 && buf[1] === 0xcf) ext = 'xls';
    const outPath = path.join(DATA_OUTPUT, `石墨导出_${meta.name || GUID}.${ext}`);
    fs.writeFileSync(outPath, buf);
    console.log(`✓ 已保存: ${outPath} (${buf.length} 字节, 格式=${ext})`);
    console.log('magic bytes:', successApi.bodyInfo.magicHex);
  } else {
    console.log('\n=== API导出均未成功，尝试菜单导出 ===');
    // 用页面菜单导出（点击右上角更多操作→下载）
    try {
      // 等待页面完全加载
      await page.waitForTimeout(2000);
      // 找右上角的"更多"按钮（通常是"..."或菜单）
      console.log('尝试查找下载菜单...');
      // 石墨文档右上角通常有"..."按钮
      const moreBtns = await page.evaluate(() => {
        const btns = [];
        document.querySelectorAll('button, [class*="more"], [class*="menu"], [class*="toolbar"]').forEach(el => {
          const t = (el.innerText || el.getAttribute('aria-label') || el.className || '').toString();
          if (/更多|下载|导出|menu|more|download|export/i.test(t)) {
            const r = el.getBoundingClientRect();
            if (r.x > 800 && r.y < 200) btns.push({ text: t.substring(0, 30), cls: el.className.substring(0, 50), x: Math.round(r.x), y: Math.round(r.y) });
          }
        });
        return btns.slice(0, 15);
      });
      console.log('右上角按钮:', JSON.stringify(moreBtns));
      console.log('（菜单导出较复杂，建议你手动在浏览器里点「下载」导出xlsx到outputs目录）');
    } catch (e) { console.log('菜单探测失败:', e.message); }
  }

  console.log('\n完成。浏览器保持打开120秒，可手动操作。');
  await page.waitForTimeout(120000);
  await context.close();
})().catch(e => { console.error('脚本错误:', e); process.exit(1); });
