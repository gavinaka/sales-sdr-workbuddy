// 石墨文档 - Hook createSheetSDK 捕获编辑器实例 + 方法探测 + 数据读取
const { chromium } = require('playwright-core');
const fs = require('fs');
const path = require('path');

const CHROME_PATH = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const USER_DATA_DIR = path.join(__dirname, '.shimo_data');
const OUTPUT_DIR = path.join(__dirname, 'shimo_capture');
const URL = 'https://shimo.im/sheets/473QMXrrL4F7p53w/dJr6p';

if (!fs.existsSync(OUTPUT_DIR)) fs.mkdirSync(OUTPUT_DIR, { recursive: true });

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

  // 关键：在页面脚本执行前注入hook，拦截 createSheetSDK
  await page.addInitScript(() => {
    window.__capturedSDKInstances = [];
    window.__sdkCallLog = [];
    let _sdk;
    try {
      Object.defineProperty(window, '@shimo/editor-sdk-sheet', {
        configurable: true,
        set(v) {
          _sdk = v;
          if (v && typeof v.createSheetSDK === 'function') {
            const origCreate = v.createSheetSDK;
            v.createSheetSDK = function (...args) {
              window.__sdkCallLog.push({ time: Date.now(), argCount: args.length, argTypes: args.map(a => typeof a) });
              try {
                const ret = origCreate.apply(this, args);
                if (ret && typeof ret.then === 'function') {
                  ret.then(inst => {
                    window.__capturedSDKInstances.push({ time: Date.now(), inst, argCount: args.length });
                  }).catch(e => { window.__sdkCallLog.push({ error: e.message }); });
                } else {
                  window.__capturedSDKInstances.push({ time: Date.now(), inst: ret, argCount: args.length });
                }
              } catch (e) {
                window.__sdkCallLog.push({ error: e.message });
              }
              return ret;
            };
          }
        },
        get() { return _sdk; }
      });
    } catch (e) { window.__hookError = e.message; }
  });

  console.log('打开石墨文档（已注入SDK hook）...');
  await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(10000);  // 等待SDK创建实例

  // ========== 1. 检查捕获的实例 ==========
  console.log('\n=== 1. 检查捕获的SDK实例 ===');
  const captureInfo = await page.evaluate(() => {
    return {
      hookError: window.__hookError,
      sdkCallLog: window.__sdkCallLog,
      capturedCount: window.__capturedSDKInstances.length,
      capturedInfo: window.__capturedSDKInstances.map((c, i) => ({
        idx: i, argCount: c.argCount,
        instType: typeof c.inst,
        instIsObj: c.inst && typeof c.inst === 'object',
        instKeys: c.inst && typeof c.inst === 'object' ? Object.keys(c.inst).slice(0, 50) : null,
        // 收集方法（含原型链）
        instMethods: (() => {
          if (!c.inst || typeof c.inst !== 'object') return null;
          const ms = [];
          let p = c.inst;
          while (p && p !== Object.prototype && ms.length < 200) {
            try { for (const k of Object.getOwnPropertyNames(p)) { if (typeof c.inst[k] === 'function' && !ms.includes(k)) ms.push(k); } } catch (e) { break; }
            p = Object.getPrototypeOf(p);
          }
          return ms;
        })()
      }))
    };
  });
  console.log('hook错误:', captureInfo.hookError);
  console.log('SDK调用日志:', JSON.stringify(captureInfo.sdkCallLog));
  console.log('捕获实例数:', captureInfo.capturedCount);
  captureInfo.capturedInfo.forEach((c, i) => {
    console.log(`\n  [实例${i}] argCount=${c.argCount} type=${c.instType}`);
    console.log(`    keys(${c.instKeys ? c.instKeys.length : 0}): ${(c.instKeys || []).join(', ')}`);
    if (c.instMethods) {
      const dataMethods = c.instMethods.filter(m => /get|read|export|sheet|cell|data|value|range|row|column|workbook|all|toJS|toJSON|serialize|save|fetch|load/i.test(m));
      console.log(`    总方法数: ${c.instMethods.length}`);
      console.log(`    数据相关方法(${dataMethods.length}): ${dataMethods.join(', ')}`);
      console.log(`    全部方法: ${c.instMethods.slice(0, 100).join(', ')}`);
    }
  });
  fs.writeFileSync(path.join(OUTPUT_DIR, 'sdk_captured.json'), JSON.stringify(captureInfo, null, 2), 'utf-8');

  // ========== 2. 如果捕获到实例，dump完整方法列表到文件 ==========
  if (captureInfo.capturedCount > 0) {
    console.log('\n=== 2. dump实例完整结构 ===');
    const fullDump = await page.evaluate(() => {
      const c = window.__capturedSDKInstances[0];
      if (!c || !c.inst) return { error: 'no instance' };
      const inst = c.inst;
      // 收集所有方法（含原型链多层）
      const allMethods = [];
      const seen = new Set();
      let p = inst;
      let depth = 0;
      while (p && p !== Object.prototype && depth < 5) {
        try {
          for (const k of Object.getOwnPropertyNames(p)) {
            if (!seen.has(k)) { seen.add(k); allMethods.push(k); }
          }
        } catch (e) { break; }
        p = Object.getPrototypeOf(p);
        depth++;
      }
      // 对每个方法，尝试获取toString前100字符（了解签名）
      const methodSignatures = {};
      for (const m of allMethods.slice(0, 150)) {
        try {
          if (typeof inst[m] === 'function') {
            methodSignatures[m] = inst[m].toString().substring(0, 150);
          }
        } catch (e) {}
      }
      return {
        ownKeys: Object.keys(inst),
        allMethods,
        methodSignatures
      };
    });
    fs.writeFileSync(path.join(OUTPUT_DIR, 'sdk_instance_full.json'), JSON.stringify(fullDump, null, 2), 'utf-8');
    console.log('完整方法列表已保存。方法数:', fullDump.allMethods ? fullDump.allMethods.length : 0);
    console.log('ownKeys:', fullDump.ownKeys);
    if (fullDump.allMethods) {
      console.log('所有方法:', fullDump.allMethods.join(', '));
    }
  } else {
    console.log('\n未捕获到实例，检查hook是否生效...');
    // 备用：直接探测window上是否有editor相关全局变量
    const backup = await page.evaluate(() => {
      const matches = {};
      for (const k of Object.keys(window)) {
        if (/editor|sheet|workbook|document|model/i.test(k) && typeof window[k] === 'object' && window[k]) {
          matches[k] = { keys: Object.keys(window[k]).slice(0, 20) };
        }
      }
      return matches;
    });
    console.log('备用探测:', JSON.stringify(backup, null, 2));
  }

  console.log('\n探测完成');
  await page.waitForTimeout(3000);
  await context.close();
})().catch(e => { console.error('脚本错误:', e); process.exit(1); });
