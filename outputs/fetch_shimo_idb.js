// 石墨文档 IndexedDB 完整数据读取
// 读取 sm-sheet-snapshot 和 sm-sheet-storage 的所有数据
const { chromium } = require('playwright-core');
const fs = require('fs');
const path = require('path');

const CHROME_PATH = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const USER_DATA_DIR = path.join(__dirname, '.shimo_data');
const OUTPUT_DIR = path.join(__dirname, 'shimo_capture');
const URL = 'https://shimo.im/sheets/473QMXrrL4F7p53w/dJr6p';
const DATA_OUTPUT = path.join(__dirname, 'shimo_raw_data');

if (!fs.existsSync(OUTPUT_DIR)) fs.mkdirSync(OUTPUT_DIR, { recursive: true });
if (!fs.existsSync(DATA_OUTPUT)) fs.mkdirSync(DATA_OUTPUT, { recursive: true });

function idbRequest(req) {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

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

  console.log('打开石墨文档（让数据加载到IndexedDB）...');
  await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(8000);

  // ========== 读取 IndexedDB: sm-sheet-snapshot 和 sm-sheet-storage ==========
  // 在页面上下文中执行（可访问IndexedDB）
  console.log('\n=== 读取 IndexedDB ===');

  // 先探测两个库的object store结构
  const structure = await page.evaluate(async () => {
    const out = {};
    for (const dbName of ['sm-sheet-snapshot', 'sm-sheet-storage', 'desktop2', 'drive_task_v2']) {
      try {
        const db = await new Promise((resolve, reject) => {
          const req = indexedDB.open(dbName);
          req.onsuccess = () => resolve(req.result);
          req.onerror = () => reject(req.error);
          req.onblocked = () => reject(new Error('blocked'));
        });
        const stores = Array.from(db.objectStoreNames);
        out[dbName] = { stores, version: db.version };
        // 探测每个store的记录数和key样本
        const storeInfo = {};
        for (const storeName of stores) {
          try {
            const tx = db.transaction(storeName, 'readonly');
            const store = tx.objectStore(storeName);
            const count = await new Promise((res, rej) => { const r = store.count(); r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error); });
            // 获取一个key样本
            const keysReq = store.getAllKeys();
            const allKeys = await new Promise((res, rej) => { keysReq.onsuccess = () => res(keysReq.result); keysReq.onerror = () => rej(keysReq.error); });
            storeInfo[storeName] = { count, keySamples: allKeys.slice(0, 10).map(k => typeof k === 'object' ? JSON.stringify(k).substring(0, 100) : String(k).substring(0, 100)) };
          } catch (e) { storeInfo[storeName] = { error: e.message }; }
        }
        out[dbName].storeInfo = storeInfo;
        db.close();
      } catch (e) { out[dbName] = { error: e.message }; }
    }
    return out;
  });
  console.log('IndexedDB 结构:');
  console.log(JSON.stringify(structure, null, 2));
  fs.writeFileSync(path.join(OUTPUT_DIR, 'idb_structure.json'), JSON.stringify(structure, null, 2), 'utf-8');

  // 读取 sm-sheet-snapshot 的所有数据
  console.log('\n=== 读取 sm-sheet-snapshot 全部数据 ===');
  const snapshotData = await page.evaluate(async () => {
    const out = { stores: {} };
    try {
      const db = await new Promise((resolve, reject) => {
        const req = indexedDB.open('sm-sheet-snapshot');
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
      });
      for (const storeName of Array.from(db.objectStoreNames)) {
        const tx = db.transaction(storeName, 'readonly');
        const store = tx.objectStore(storeName);
        const allReq = store.getAll();
        const allKeysReq = store.getAllKeys();
        const [values, keys] = await Promise.all([
          new Promise((res, rej) => { allReq.onsuccess = () => res(allReq.result); allReq.onerror = () => rej(allReq.error); }),
          new Promise((res, rej) => { allKeysReq.onsuccess = () => res(allKeysReq.result); allKeysReq.onerror = () => rej(allKeysReq.error); })
        ]);
        out.stores[storeName] = { count: values.length, keys, values };
      }
      db.close();
    } catch (e) { out.error = e.message; }
    return out;
  });
  console.log('snapshot 读取结果:');
  for (const [storeName, info] of Object.entries(snapshotData.stores || {})) {
    console.log(`  store="${storeName}" count=${info.count}`);
    // 显示第一个值的结构
    if (info.values && info.values.length > 0) {
      const v = info.values[0];
      const vStr = typeof v === 'string' ? v : JSON.stringify(v);
      console.log(`    第一个值类型: ${typeof v}, 长度: ${vStr.length}, 预览: ${vStr.substring(0, 200)}`);
    }
  }
  if (snapshotData.error) console.log('错误:', snapshotData.error);
  fs.writeFileSync(path.join(DATA_OUTPUT, 'sm-sheet-snapshot.json'), JSON.stringify(snapshotData, null, 2), 'utf-8');
  console.log('已保存 sm-sheet-snapshot.json');

  // 读取 sm-sheet-storage 的所有数据
  console.log('\n=== 读取 sm-sheet-storage 全部数据 ===');
  const storageData = await page.evaluate(async () => {
    const out = { stores: {} };
    try {
      const db = await new Promise((resolve, reject) => {
        const req = indexedDB.open('sm-sheet-storage');
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
      });
      for (const storeName of Array.from(db.objectStoreNames)) {
        const tx = db.transaction(storeName, 'readonly');
        const store = tx.objectStore(storeName);
        const allReq = store.getAll();
        const allKeysReq = store.getAllKeys();
        const [values, keys] = await Promise.all([
          new Promise((res, rej) => { allReq.onsuccess = () => res(allReq.result); allReq.onerror = () => rej(allReq.error); }),
          new Promise((res, rej) => { allKeysReq.onsuccess = () => res(allKeysReq.result); allKeysReq.onerror = () => rej(allKeysReq.error); })
        ]);
        out.stores[storeName] = { count: values.length, keys, values };
      }
      db.close();
    } catch (e) { out.error = e.message; }
    return out;
  });
  console.log('storage 读取结果:');
  for (const [storeName, info] of Object.entries(storageData.stores || {})) {
    console.log(`  store="${storeName}" count=${info.count}`);
    if (info.values && info.values.length > 0) {
      const v = info.values[0];
      const vStr = typeof v === 'string' ? v : JSON.stringify(v);
      console.log(`    第一个值类型: ${typeof v}, 长度: ${vStr.length}, 预览: ${vStr.substring(0, 200)}`);
    }
  }
  if (storageData.error) console.log('错误:', storageData.error);
  fs.writeFileSync(path.join(DATA_OUTPUT, 'sm-sheet-storage.json'), JSON.stringify(storageData, null, 2), 'utf-8');
  console.log('已保存 sm-sheet-storage.json');

  console.log('\n数据读取完成！');
  console.log('数据目录:', DATA_OUTPUT);
  await page.waitForTimeout(3000);
  await context.close();
})().catch(e => { console.error('脚本错误:', e); process.exit(1); });
