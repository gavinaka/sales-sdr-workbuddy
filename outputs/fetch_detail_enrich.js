// 服务池详情API补全 - userExtendInfo.ac
// 从chengdu_final_enriched.json读取3099条的cid/sysType，分批调用详情API补全完整手机号、付费记录等
// 只读操作：仅GET/POST查询API，不修改CRM任何数据
const { chromium } = require('playwright-core');
const fs = require('fs');
const path = require('path');

const CHROME_PATH = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const USER_DATA_DIR = path.join(__dirname, '.browser_data');
const INPUT_FILE = path.join(__dirname, 'chengdu_final_enriched.json');
const OUTPUT_FILE = path.join(__dirname, 'chengdu_detail_enriched.json'); // 新文件，不覆盖原数据
const BATCH_SIZE = 100; // 每批最多100条详情API（避免单次evaluate超时）

(async () => {
  console.log('=== 服务池详情补全 ===');
  console.log(`读取: ${INPUT_FILE}`);
  
  // 读取现有数据
  const rawData = JSON.parse(fs.readFileSync(INPUT_FILE, 'utf-8'));
  console.log(`总记录: ${rawData.length} 条`);
  
  // 提取每条的cid和sysType用于详情查询
  const records = rawData.map((r, idx) => ({
    idx,
    cid: r.cid,
    sysType: r.sysType || 1,
    userId: r.userId
  }));
  console.log(`需补全: ${records.length} 条详情`);

  // 启动浏览器（复用已登录cookie）
  console.log('\n启动浏览器...');
  const context = await chromium.launchPersistentContext(USER_DATA_DIR, {
    executablePath: CHROME_PATH,
    headless: false,
    viewport: null,
    args: ['--start-maximized', '--disable-blink-features=AutomationControlled']
  });
  const pages = context.pages();
  const page = pages.length > 0 ? pages[0] : await context.newPage();

  // 导航到CRM页面确保登录态有效
  console.log('检查登录态...');
  await page.goto('https://cloud.qinsilk.com/sapp/qinsilkReport/#/manager/userInfoList', {
    waitUntil: 'domcontentloaded', timeout: 60000
  });
  await page.waitForTimeout(3000);

  // 检查是否已登录
  if (page.url().includes('login')) {
    console.log('⚠️ 未登录！请在浏览器中完成登录...');
    try {
      await page.waitForURL(url => !url.toString().includes('login.ac'), { timeout: 300000 });
      console.log('✅ 登录成功！');
      await page.goto('https://cloud.qinsilk.com/sapp/qinsilkReport/#/manager/userInfoList', {
        waitUntil: 'domcontentloaded', timeout: 60000
      });
      await page.waitForTimeout(3000);
    } catch (e) {
      console.error('登录超时', e.message);
      await context.close();
      return;
    }
  }
  console.log('✅ 已登录, URL:', page.url());

  // 分批调用详情API
  const allDetails = {}; // idx -> detail data
  const totalBatches = Math.ceil(records.length / BATCH_SIZE);
  let successCount = 0;
  let failCount = 0;

  for (let batchIdx = 0; batchIdx < totalBatches; batchIdx++) {
    const start = batchIdx * BATCH_SIZE;
    const end = Math.min(start + BATCH_SIZE, records.length);
    const batch = records.slice(start, end);
    
    console.log(`\n--- 批次 ${batchIdx + 1}/${totalBatches} (第${start + 1}-${end}条) ---`);
    
    const batchResults = await page.evaluate(async (batchData) => {
      const results = [];
      for (const rec of batchData) {
        try {
          const resp = await fetch('https://cloud.qinsilk.com/console/crm/user/v2/userExtendInfo.ac', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json;charset=UTF-8' },
            body: JSON.stringify({ cid: rec.cid, sysType: rec.sysType })
          });
          const data = await resp.json();
          results.push({
            idx: rec.idx,
            cid: rec.cid,
            status: resp.status,
            data: data
          });
        } catch (e) {
          results.push({ idx: rec.idx, cid: rec.cid, error: e.message });
        }
        // 小间隔避免请求过快
        await new Promise(r => setTimeout(r, 50));
      }
      return results;
    }, batch);

    // 统计本批结果
    for (const r of batchResults) {
      if (r.error) {
        failCount++;
        allDetails[r.idx] = { error: r.error };
      } else {
        successCount++;
        allDetails[r.idx] = r.data;
      }
    }

    const batchSuccess = batchResults.filter(r => !r.error).length;
    console.log(`  本批: ${batchSuccess}/${batch.length} 成功 | 累计: ${successCount}成功 ${failCount}失败`);

    // 批间暂停避免频率限制
    if (batchIdx < totalBatches - 1) {
      await page.waitForTimeout(1500);
    }
  }

  console.log(`\n=== 详情补全完成 ===`);
  console.log(`成功: ${successCount}/${records.length}`);
  console.log(`失败: ${failCount}/${records.length}`);

  // 合并数据：原数据 + 详情
  console.log('\n合并数据...');
  const enriched = rawData.map((rec, idx) => {
    const detail = allDetails[idx];
    const merged = { ...rec };
    if (detail && !detail.error) {
      // 将userExtendInfo数据合并到顶层
      merged.userExtendInfo = detail.userExtendInfo || detail.resultObject || detail;
      
      // 如果详情里有完整手机号，覆盖脱敏的
      if (detail.userExtendInfo && detail.userExtendInfo.cellphone) {
        merged.cellphone = detail.userExtendInfo.cellphone;
      }
      if (detail.resultObject && detail.resultObject.cellphone) {
        merged.cellphone = detail.resultObject.cellphone;
      }
      
      // 保留原始detail响应供排查
      merged._detailRaw = detail;
    } else {
      merged._detailError = detail ? detail.error : 'No detail fetched';
    }
    return merged;
  });

  // 统计补全效果
  const fullPhones = enriched.filter(x => x.cellphone && !x.cellphone.includes('*')).length;
  const hasExtInfo = enriched.filter(x => x.userExtendInfo && !x._detailError).length;
  console.log(`\n补全后统计:`);
  console.log(`  完整手机号: ${fullPhones}/${enriched.length}`);
  console.log(`  有userExtendInfo: ${hasExtInfo}/${enriched.length}`);

  // 保存到新文件
  fs.writeFileSync(OUTPUT_FILE, JSON.stringify(enriched, null, 2), 'utf-8');
  const sizeMB = fs.statSync(OUTPUT_FILE).size / 1024 / 1024;
  console.log(`\n✅ 已保存: ${OUTPUT_FILE} (${sizeMB.toFixed(1)} MB)`);

  console.log('\n10秒后关闭浏览器...');
  await page.waitForTimeout(10000);
  await context.close();
  console.log('Done.');
})();
