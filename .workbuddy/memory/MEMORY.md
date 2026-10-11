# 销售SDR项目 · 长期记忆

## ⚡ 指令触发规则（老板约定，2026-07-02）

老板会直接给简短指令启动子任务，无需多问：
- **"抓服务池"** → 启动服务池工作流（见下方第1节）
- **"抓公海"** → 启动公海客户工作流（见下方第2节）

执行时直接按对应工作流操作，不再确认。

---

## 项目概述
SDR客户智能分级系统，针对秦丝CRM做两个维度的客户筛选：
1. **服务池**：已服务老客户，做评分分级+画像分析+话术生成
2. **公海客户**：新注册潜在客户，严格筛选+机会判断+转化话术

服务于成都分部SDR团队（在职5人：王胜学、吴云凤、潘飞、吴必川[病假]、刘昕）。

---

## 1. 服务池工作流（指令：抓服务池）

1. **数据抓取** → MCP Playwright浏览器内fetch调用列表API
   - 列表API参数：`department:7`(成都分部) + `statusPoolType:2`(服务池) + `queryGroupList:[7]`
   - 详情API补全：`userExtendInfo.ac`，参数`{cid, sysType}`，每批100条
   - 输出：`outputs/chengdu_final_enriched.json`
2. **分析+表生成** → 运行 `outputs/generate_chengdu_v3.py`
   - 6维评分+5维画像规则+v3.2话术生成（老客户精准营销·15年销售专家视角）
   - 输出：`outputs/成都分部SDR跟进名单_画像话术v3_YYYYMMDD.xlsx`（6个Sheet）
3. **交付** → present_files 展示Excel

## 2. 公海客户工作流（指令：抓公海）⏸️ 暂缓迭代

> **2026-07-03 老板决策**：公海工作流暂缓迭代，后续再迭代。当前只走服务池路径。
> 已完成的公海脚本和数据保留，但不再投入优化。

1. **数据抓取** → MCP Playwright浏览器内fetch调用列表API
   - 列表API参数：`department:-1`(公司公海) + `queryGroupList:[-1]` + `registerDate`时间范围
   - **硬性筛选**：`minLoginDayRate:50` + `minLoginDays:5`（API层直接过滤）
   - 详情API补全：`userExtendInfo.ac`
   - 输出：`outputs/high_seas_enriched.json`
2. **无效客户剔除**：测试账号 + 回访记录含"不要了"等明确拒绝
3. **分析+表生成** → 运行 `outputs/generate_high_seas_v1.py`
   - 6维评分（适配公海）+ 话术生成（新客户转化视角）
   - 输出：`outputs/成都分部SDR公海客户跟进名单_YYYYMMDD.xlsx`（6个Sheet）
4. **交付** → present_files 展示Excel

## 数据源与抓取技术
- 数据源：秦丝CRM（cloud.qinsilk.com）
- 两个维度：服务池（老客户）+ 公海客户（新注册潜在客户）
- 抓取方式：MCP Playwright浏览器内fetch调用API（替代本地playwright，无需装包）
- API技术细节：POST + JSON body，content-type=`application/json;charset=UTF-8`
- 列表API：`/console/crm/user/v2/userInfoDataJson.ac?page=X&pageSize=100`
- **服务池参数**：`department:7`(成都分部) + `statusPoolType:2`(服务池) + `queryGroupList:[7]` + `temporaryVisit:0`
- **公海参数**：`department:-1`(公司公海) + `queryGroupList:[-1]` + `registerDate`时间范围
- **公海硬性筛选参数**：`minLoginDayRate:50` + `minLoginDays:5`（API层直接过滤）
- **公海数据结构**：`object.userInfoList`（注意：服务池是`list`，公海是`userInfoList`）
- 详情API：`/console/crm/user/v2/userExtendInfo.ac`（参数: `{cid, sysType}`）
- **列表API手机号脱敏**（`189****5261`），详情API返回完整手机号（`object.userExtendInfo.cellphone`）
- **成都分部payAmount字段全null**（详情API不返回）→ 改用付费服务记录数×500+beInviterPayAmount估算
- **counselor字段为null** → 用counselorId映射（**2026-07-06 CRM抓取getUserListForCounselors.ac最终核对**）
- **MCP浏览器抓取分页限制**：单次evaluate最多100条详情API（200条超时），列表API最多3页/次
- **window变量持久化**：MCP浏览器window变量跨evaluate调用保持，可用于分批累积
- **counselorId分布与归属（2026-07-06 CRM核对确认）**：
  - 1431=**吴必川**（1262条·40.7%）→ **病假，老板指示归属吴云凤** → 显示"吴云凤"
  - 1314=**王胜学**（1124条·36.3%）
  - 2379=**潘飞**（574条·18.5%）
  - 2381=**吴云凤**（6条·0.2%）
  - 800=**刘昕**（76条·2.5%）→ **主管不跟进客户** → 显示"待分配"
  - 零散ID(1696/1878/1733/1352/826/1067/2212/205)=成都分部已离职人员→"待分配"（14条）
  - None=未分配→"待分配"（43条）
  - **最终看板分布**：吴云凤1268(40.9%) / 王胜学1124(36.3%) / 潘飞574(18.5%) / 待分配133(4.3%)
- **成都分部在职5人（2026-07-06 CRM核对确认）**：
  - **跟进客户3人**：王胜学(1314)、吴云凤(2381+吴必川1431代管)、潘飞(2379)
  - **不跟进客户2人**：刘昕(800·主管)、吴必川(1431·病假)
- **销售画像（老板同步）**：
  - **潘飞(2379)**：老黄牛型·非常在意业绩·销售能力中上·小单也看重·大单较少 → 适合中小价值客户高频跟进
  - **吴云凤(2381)**：小绵羊型·销售能力一般·没耐心刚出社会·脾气冲被家里宠惯了 → 适合标准化客户+流程清晰，避免复杂大单和难缠客户
  - **王胜学(1314)**：野狗型·大单较多·骚操作多存在过度承诺·小单看不上·销售能力中上·资源整合能力强（利用团队/公司资源转化为自己业绩）→ 适合大单客户但需防过度承诺风险
  - **刘昕(800)**：主管，不跟进客户
  - **吴必川(1431)**：请半年病假，客户归属吴云凤；画像待补
- **⚠️ 归属确认历程（重要·避免再犯）**：
  - 2026-07-02：仅确认2379=潘飞
  - 2026-07-03：老板口头确认1431=王胜学、1314=吴云凤、800=刘昕（**此确认有误**）
  - 2026-07-06：**CRM抓取getUserListForCounselors.ac API核对**，发现真实对应：1431=吴必川、1314=王胜学、2381=吴云凤——之前1431/1314搞反了，且漏了2381=吴云凤
  - 老板指示：吴必川(1431)病假→归属吴云凤；刘昕(800)主管→待分配
- **CRM顾问列表API（核对用）**：
  - 端点：`/console/crm/user/getUserListForCounselors.ac`（POST + JSON body `{}`）
  - 返回：`resultObject` 数组，每项含 id/realName/userName/groupId/groupName/status/cellphone
  - 成都分部 groupId=7
  - 抓取脚本：`outputs/fetch_counselor_list.js`（playwright-core + persistent context复用cookie）
  - cookie持久化目录：`outputs/.browser_data/`
- Vue row提取法：表格tr元素`__vue__.row`属性含完整客户数据（含userId/cid/sysType），按userId去重

## 5维画像规则
- R1 系统即将到期(60天内)：解析expirationList中enableEnd时间戳 → 续费机会
- R2 付费金额>¥3000：详情API真实payAmount → 高价值增购
- R3 活跃天数>100天：loginDays字段 → 高粘性升单
- R4 门店/子账号≥3：store_count + userNumber → 规模化增购
- R5 销售机会综合评判：意向+行业+业务+硬件+服务余额+可触达渠道 → 机会评分(0-100)

## 评分模型 v3.0（6维度+规则加成）
- D1 回访紧迫度(5): 0-30天=1|31-90=2|91-180=3|181-365=4|365+=5|无=3
- D2 行业匹配度(5): 未填=1|非核心=2|服装鞋帽=5
- D3 业务类型(5): 未填=1|零售=2|批发=3|批零一体=5
- D4 门店规模(5): 无=1|1-2单元=2-3|3-5=4|6+=5
- D5 活跃度(5): 0%=1|1-19%=1|20-49%=2|50-79%=3|≥80%=5
- D6 付费价值(5): 未付费=1|¥1-999=3|¥1000-2999=4|≥¥3000=5
- 规则加成：机会分≥50→+3 | ≥30→+2 | ≥15→+1
- A级触发：服务到期/总分≥24/高付费+高活跃/超高付费+久未回访/规模化+已付费/机会分≥60
- 分级结果v3.0：A=265(46.2%) B=180(31.4%) C=129(22.5%)
- **分级结果v3.1（A级细分·2026-07-03）**：S=566(18.3%) A2=367(11.8%) A3=585(18.9%) B=1124 C=457
- **分级标识：S/A2/A3/B/C**（原A1改为S，BD更好解读·S=最高优先级）
- S级规则（服务池）：服务7天内到期/高付费+久未回访/意向
- S级规则（公海）：服务到期/意向/已下单

## 话术与痛点生成（9种痛点类型）
- 到期紧迫/价值流失/线上渠道缺失/硬件效率低/多店管理复杂/行业特定/活跃度低/未回访/服务浪费
- 每客户生成：痛点分析+沟通话术(可直接念)+建议动作+机会类型
- 话术基于：产品到期+付费金额+活跃度+行业+业务类型+门店规模组合

## 秦丝产品知识库（32种服务）
- 核心系统：进销通高级版/专业版/会员/进销存专业版/进阶版会员
- 线上渠道：基础版微商城/专业版微商城/专属商品小程序
- 营销工具：营销宝/直播引流/限时折扣/限时秒杀/微信自动化运营
- 会员运营：专属微信会员包/会员营销成长值
- 硬件：扫码宝/AI描图
- 增值：开店账号/门店/商家名片/拼图美图/防伪服务/报税宝/订货宝
- 存储扩展：客户公海存储包

## 路径规范（重要）
- 项目根：`C:/Users/杨杨/Desktop/销售SDR`
- 输出目录：`outputs/`
- **脚本必须用相对路径**（`os.path.dirname(os.path.abspath(__file__))`），禁止硬编码绝对路径

## Python环境
- venv：`C:/Users/杨杨/.workbuddy/binaries/python/envs/default`（注意用户名是杨杨不是31702）
- managed python：`C:\Users\杨杨\.workbuddy\binaries\python\versions\3.13.12\python.exe`
- 已装：openpyxl 3.1.5
- 运行：`<venv>/Scripts/python.exe <script>.py`

## 核心脚本清单（2026-07-06清理后，仅保留在用文件）
### 服务池（主线路径）
- `outputs/generate_chengdu_v3.py` — **服务池主力脚本**（成都分部全量3099条·v3.2话术·8个Sheet）
- `outputs/generate_html_dashboard.py` — **HTML交互看板生成器**（浅黄主题·总览/列表/到期预警·含顾问分布）
- `outputs/chengdu_final_enriched.json` — 服务池数据源（3099条·含详情API补全）

### 公海客户（暂缓迭代）
- `outputs/generate_high_seas_v1.py` — **公海主力脚本**（严格筛选+6维评分+话术·6个Sheet）
- `outputs/high_seas_enriched.json` — 公海客户详情数据（硬性筛选后）

### CRM核对工具
- `outputs/fetch_counselor_list.js` — 顾问列表核对脚本（playwright-core + persistent context复用cookie）
- `outputs/counselor_list_final.json` — getUserListForCounselors.ac API返回数据（2301个顾问·参考用）
- `outputs/.browser_data/` — playwright cookie持久化目录（复用登录态）

### 交付物
- `outputs/服务池SDR交互看板.html` — 最新HTML看板（单文件零依赖可离线）
- `outputs/成都分部SDR跟进名单_画像话术v3_20260706.xlsx` — 最新Excel（8 Sheet）
- `outputs/成都分部SDR公海客户跟进名单_20260703.xlsx` — 公海Excel

## 待优化
- 话术模板可进一步细化（按行业/付费档位分模板）— 已部分实现（行业画像库推荐）
- HTML看板与Excel评分细节有差异，后续可统一评分逻辑为独立模块
- 公海工作流暂缓，后续迭代时再优化
