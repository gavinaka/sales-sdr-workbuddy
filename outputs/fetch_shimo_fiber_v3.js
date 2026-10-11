// 石墨文档 Fiber 修复版（用 .current）+ Socket hook + 数据模型定位
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
  console.log('启动浏览器...');
  const context = await chromium.launchPersistentContext(USER_DATA_DIR, {
    executablePath: CHROME_PATH,
    headless: false,
    viewport: null,
    args: ['--start-maximized', '--disable-blink-features=AutomationControlled']
  });
  const pages = context.pages();
  const page = pages.length > 0 ? pages[0] : await context.newPage();

  // 注入 socket hook（在页面脚本前）
  await page.addInitScript(() => {
    window.__socketMessages = [];
    window.__socketRawPackets = [];
    // hook socket.io：当 window.shimo.socket 被设置时，包装它的方法
    let _shimo;
    try {
      Object.defineProperty(window, 'shimo', {
        configurable: true,
        set(v) {
          _shimo = v;
          if (v && v.socket) {
            const sock = v.socket;
            // hook onevent
            const origOnevent = sock.onevent;
            sock.onevent = function (packet) {
              try {
                if (packet && packet.data) {
                  window.__socketMessages.push({ t: Date.now(), data: JSON.stringify(packet.data).substring(0, 500), dataLen: JSON.stringify(packet.data).length });
                }
              } catch (e) {}
              return origOnevent ? origOnevent.apply(this, arguments) : null;
            };
            // hook on
            const origOn = sock.on;
            sock.on = function (ev, cb) {
              const wrapped = function () {
                try {
                  const args = Array.from(arguments);
                  window.__socketMessages.push({ t: Date.now(), event: ev, argTypes: args.map(a => typeof a), preview: JSON.stringify(args).substring(0, 800) });
                } catch (e) {}
                return cb.apply(this, arguments);
              };
              return origOn.call(this, ev, wrapped);
            };
            // hook engine transport
            if (sock.io && sock.io.engine) {
              sock.io.engine.on('packet', (p) => {
                try {
                  if (p && p.data && p.type === 2) {
                    window.__socketRawPackets.push({ t: Date.now(), preview: JSON.stringify(p.data).substring(0, 500) });
                  }
                } catch (e) {}
              });
            }
          }
        },
        get() { return _shimo; }
      });
    } catch (e) { window.__socketHookError = e.message; }
  });

  console.log('打开石墨文档（已注入socket hook）...');
  await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(10000);

  // ========== 1. 检查socket消息 ==========
  console.log('\n=== 1. Socket 消息捕获情况 ===');
  const socketInfo = await page.evaluate(() => {
    return {
      hookError: window.__socketHookError,
      messageCount: window.__socketMessages.length,
      rawPacketCount: window.__socketRawPackets.length,
      messages: window.__socketMessages.slice(0, 30),
      rawPackets: window.__socketRawPackets.slice(0, 30)
    };
  });
  console.log('hook错误:', socketInfo.hookError);
  console.log('消息数:', socketInfo.messageCount, '原始包数:', socketInfo.rawPacketCount);
  socketInfo.messages.slice(0, 15).forEach((m, i) => {
    console.log(`  [msg${i}] event=${m.event || '?'} types=${m.argTypes} preview=${m.preview.substring(0, 150)}`);
  });
  fs.writeFileSync(path.join(OUTPUT_DIR, 'socket_messages.json'), JSON.stringify(socketInfo, null, 2), 'utf-8');

  // ========== 2. 修复版 Fiber 遍历（用 .current）==========
  console.log('\n=== 2. 修复版 Fiber 遍历 ===');
  const fiberScan = await page.evaluate(() => {
    const out = { scanned: 0, dataModels: [], bigStates: [] };
    const root = document.querySelector('#root');
    if (!root) { out.error = '无#root'; return out; }
    const fk = Object.keys(root).find(k => k.startsWith('__react'));
    if (!fk) { out.error = '无fiber key'; return out; }
    let fiberRoot = root[fk];
    // fiberRoot.tag === 3 是 FiberRoot，用 .current 拿到 HostRoot
    let hostRoot = fiberRoot.current ? fiberRoot.current : fiberRoot;
    out.hostRootTag = hostRoot.tag;

    const visited = new Set();
    const DATA_KEYS = /cells|sheets|rows|columns|cellData|sheetList|workbook|spreadsheet|model|content|blocks/i;

    function sizeEstimate(obj, depth) {
      // 粗略估算对象大小（键数量）
      if (depth > 3 || !obj || typeof obj !== 'object') return 0;
      try {
        let n = 0;
        for (const k of Object.keys(obj)) { n++; if (typeof obj[k] === 'object' && obj[k]) n += sizeEstimate(obj[k], depth + 1); }
        return n;
      } catch (e) { return 0; }
    }

    function scanObj(obj, path, depth) {
      // 递归查找含数据键的对象，限制深度
      if (!obj || typeof obj !== 'object' || depth > 4) return;
      try {
        const keys = Object.keys(obj);
        const matched = keys.filter(k => DATA_KEYS.test(k));
        if (matched.length >= 2) {
          // 潜在数据模型
          const size = sizeEstimate(obj, 0);
          out.dataModels.push({
            path, matchedKeys: matched, allKeys: keys.slice(0, 30),
            sizeEstimate: size,
            // 探测matchedKeys对应值的结构
            samples: matched.slice(0, 3).map(k => {
              const v = obj[k];
              if (v === null) return { k, type: 'null' };
              if (Array.isArray(v)) return { k, type: 'array', len: v.length, sample: v[0] ? JSON.stringify(v[0]).substring(0, 150) : null };
              if (typeof v === 'object') return { k, type: 'object', keys: Object.keys(v).slice(0, 15), keyCount: Object.keys(v).length };
              return { k, type: typeof v, value: String(v).substring(0, 80) };
            })
          });
        }
        // 继续递归（只递归对象/数组，不递归DOM/函数）
        for (const k of keys.slice(0, 40)) {
          const v = obj[k];
          if (v && typeof v === 'object' && !v.tagName && !v.nodeType && typeof v !== 'function') {
            scanObj(v, path + '.' + k, depth + 1);
          }
        }
      } catch (e) {}
    }

    function dfs(f, depth) {
      if (!f || visited.has(f) || depth > 20 || out.scanned > 4000) return;
      visited.add(f);
      out.scanned++;
      const et = typeof f.elementType === 'string' ? f.elementType : (f.elementType && (f.elementType.displayName || f.elementType.name)) || '';

      // 扫描 memoizedProps
      try {
        if (f.memoizedProps && typeof f.memoizedProps === 'object') {
          scanObj(f.memoizedProps, 'props@' + et + '(d' + depth + ')', 0);
        }
      } catch (e) {}

      // 扫描 memoizedState 链
      try {
        let st = f.memoizedState;
        let idx = 0;
        while (st && idx < 12) {
          if (st.memoizedState && typeof st.memoizedState === 'object') {
            scanObj(st.memoizedState, 'state[' + idx + ']@' + et + '(d' + depth + ')', 0);
            // 记录大state
            const msKeys = Object.keys(st.memoizedState);
            if (msKeys.length > 10) {
              out.bigStates.push({ path: 'state[' + idx + ']@' + et, keyCount: msKeys.length, keys: msKeys.slice(0, 25) });
            }
          }
          st = st.next; idx++;
        }
      } catch (e) {}

      // 扫描 stateNode（类实例）
      try {
        const sn = f.stateNode;
        if (sn && typeof sn === 'object' && !sn.tagName && !sn.nodeType) {
          scanObj(sn, 'stateNode@' + et + '(d' + depth + ')', 0);
        }
      } catch (e) {}

      dfs(f.child, depth + 1);
      dfs(f.sibling, depth + 1);
    }
    dfs(hostRoot, 0);

    // 去重dataModels
    const seen = new Set();
    out.dataModels = out.dataModels.filter(d => {
      const key = d.path + '|' + d.matchedKeys.join(',');
      if (seen.has(key)) return false;
      seen.add(key); return true;
    }).sort((a, b) => b.sizeEstimate - a.sizeEstimate).slice(0, 20);

    return out;
  });
  console.log('扫描fiber数:', fiberScan.scanned);
  console.log('hostRoot tag:', fiberScan.hostRootTag);
  console.log('数据模型候选:', fiberScan.dataModels.length);
  fiberScan.dataModels.slice(0, 10).forEach((d, i) => {
    console.log(`\n  [模型${i}] path=${d.path} size≈${d.sizeEstimate} matchedKeys=${d.matchedKeys.join(',')}`);
    console.log(`    allKeys: ${d.allKeys.join(', ')}`);
    d.samples.forEach(s => {
      console.log(`    ${s.k}: ${s.type}${s.len !== undefined ? ' len=' + s.len : ''}${s.keyCount !== undefined ? ' keys=' + s.keyCount : ''}${s.keys ? '(' + s.keys.join(',') + ')' : ''}${s.sample ? ' sample=' + s.sample.substring(0, 100) : ''}${s.value ? ' = ' + s.value : ''}`);
    });
  });
  console.log('\n大state对象:', fiberScan.bigStates.length);
  fiberScan.bigStates.slice(0, 10).forEach((s, i) => console.log(`  [big${i}] ${s.path} keys=${s.keyCount} (${s.keys.join(',')})`));
  fs.writeFileSync(path.join(OUTPUT_DIR, 'fiber_datamodels.json'), JSON.stringify(fiberScan, null, 2), 'utf-8');

  console.log('\n探测完成');
  await page.waitForTimeout(3000);
  await context.close();
})().catch(e => { console.error('脚本错误:', e); process.exit(1); });
