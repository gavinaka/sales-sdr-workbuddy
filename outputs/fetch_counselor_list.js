// 直接fetch顾问列表API（getUserListForCounselors.ac）
const { chromium } = require('playwright-core');
const fs = require('fs');
const path = require('path');

const CHROME_PATH = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const USER_DATA_DIR = path.join(__dirname, '.browser_data');
const OUTPUT_FILE = path.join(__dirname, 'counselor_list_final.json');

(async () => {
  console.log('启动浏览器（复用已登录cookie）...');
  const context = await chromium.launchPersistentContext(USER_DATA_DIR, {
    executablePath: CHROME_PATH,
    headless: false,
    viewport: null,
    args: ['--start-maximized', '--disable-blink-features=AutomationControlled']
  });
  const pages = context.pages();
  const page = pages.length > 0 ? pages[0] : await context.newPage();

  // 导航到客户列表页
  console.log('导航到客户列表页...');
  await page.goto('https://cloud.qinsilk.com/sapp/qinsilkReport/#/manager/userInfoList', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(5000);

  // 检查是否已登录
  if (page.url().includes('login')) {
    console.log('未登录！请先在浏览器里登录CRM，然后脚本会重试...');
    // 等待登录
    try {
      await page.waitForURL(url => !url.toString().includes('login.ac'), { timeout: 300000 });
      console.log('登录成功！URL:', page.url());
      await page.goto('https://cloud.qinsilk.com/sapp/qinsilkReport/#/manager/userInfoList', { waitUntil: 'domcontentloaded', timeout: 60000 });
      await page.waitForTimeout(5000);
    } catch (e) {
      console.log('登录超时');
      await context.close();
      return;
    }
  }

  console.log('当前URL:', page.url());

  // 在控制台fetch顾问列表API
  console.log('\n=== fetch getUserListForCounselors.ac ===');
  const result = await page.evaluate(async () => {
    const results = {};
    // 尝试多个可能的顾问列表API
    const apis = [
      '/console/crm/user/getUserListForCounselors.ac',
      '/console/crm/user/v2/getUserListForCounselors.ac',
    ];
    for (const api of apis) {
      try {
        const resp = await fetch('https://cloud.qinsilk.com' + api, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json;charset=UTF-8' },
          body: JSON.stringify({})
        });
        const text = await resp.text();
        results[api] = { status: resp.status, body: text };
      } catch (e) {
        results[api] = { error: e.message };
      }
    }
    return results;
  });

  // 打印结果
  for (const [api, res] of Object.entries(result)) {
    console.log(`\nAPI: ${api}`);
    console.log(`Status: ${res.status}`);
    if (res.body) {
      console.log(`Body (${res.body.length} chars):`);
      console.log(res.body.substring(0, 5000));
    } else {
      console.log('Error:', res.error);
    }
  }

  // 同时从Vue store获取顾问列表（如果有）
  console.log('\n=== 从Vue Store获取顾问列表 ===');
  const storeCounselors = await page.evaluate(() => {
    try {
      const app = document.querySelector('#app');
      if (app && app.__vue__) {
        const store = app.__vue__.$store;
        if (store && store.state) {
          const result = {};
          for (const k of Object.keys(store.state)) {
            const json = JSON.stringify(store.state[k]);
            if (json.includes('counselor') || json.includes('潘飞') || json.includes('realName')) {
              result[k] = json.substring(0, 8000);
            }
          }
          result._allKeys = Object.keys(store.state);
          return result;
        }
      }
    } catch (e) { return { error: e.message }; }
    return null;
  });
  if (storeCounselors) {
    console.log('Store keys:', storeCounselors._allKeys);
    for (const k of Object.keys(storeCounselors)) {
      if (k.startsWith('_')) continue;
      console.log(`\nStore.${k}:`);
      console.log(storeCounselors[k].substring(0, 3000));
    }
  }

  // 从"所属顾问"下拉框获取顾问列表
  console.log('\n=== 从"所属顾问"下拉框获取顾问列表 ===');
  // 先找"所属顾问"的label，然后找它对应的select
  const counselorOptions = await page.evaluate(() => {
    // 找所有el-select-dropdown__item
    const items = [];
    document.querySelectorAll('.el-select-dropdown__item').forEach(el => {
      const text = (el.innerText || '').trim();
      if (text) items.push(text);
    });
    return items;
  });
  console.log('所有下拉选项:', counselorOptions);

  // 尝试点击"所属顾问"展开下拉框
  try {
    // 找"所属顾问"label
    const labels = page.locator('text=所属顾问');
    const labelCount = await labels.count();
    console.log(`\n找到${labelCount}个"所属顾问"元素`);
    if (labelCount > 0) {
      // 找它附近的select
      for (let i = 0; i < labelCount; i++) {
        try {
          await labels.nth(i).click({ timeout: 3000 });
          await page.waitForTimeout(1000);
        } catch (e) {}
      }
    }
  } catch (e) {}

  // 保存完整结果
  fs.writeFileSync(OUTPUT_FILE, JSON.stringify({
    timestamp: new Date().toISOString(),
    apiResults: result,
    storeCounselors: storeCounselors,
    counselorOptions: counselorOptions
  }, null, 2), 'utf-8');
  console.log(`\n结果保存: ${OUTPUT_FILE}`);

  console.log('\n完成。30秒后关闭浏览器。');
  await page.waitForTimeout(30000);
  await context.close();
})();
