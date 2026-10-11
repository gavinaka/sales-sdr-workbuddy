#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SDR 公海客户机会筛选 v1.0
硬性门槛：活跃度>50% + 活跃天数>5天
综合判断：行业匹配/业务类型/门店规模/服务到期/回访状态/意向/可触达渠道
模板与服务池一致：6个Sheet（跟进名单+话术痛点/A类重点/服务到期预警/画像分析/可视化看板/筛选方法论）
"""
import json
import os
import re
import sys
import io
from collections import Counter
from datetime import datetime, timedelta

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.chart import PieChart, BarChart, Reference
from openpyxl.chart.label import DataLabelList

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, 'high_seas_enriched.json')
OUTPUT_FILE = os.path.join(BASE_DIR, f'成都分部SDR公海客户跟进名单_{datetime.now().strftime("%Y%m%d")}.xlsx')

now = datetime.now()

# 无效客户黑名单（测试账号+明确拒绝）
INVALID_KEYWORDS = ['内部测试', '测试账号']
INVALID_VISIT_RECORDS = ['不要了', '已放弃', '已退费', '无效客户']

# ==================== 秦丝产品知识库（37个真实产品名，与服务池一致） ====================
QINSILK_PRODUCTS = {
    '进销存会员': {'category': '核心系统-进销存', 'tier': '入门', 'value': '进销存基础功能，适合单店起步'},
    '进销存专业版': {'category': '核心系统-进销存', 'tier': '中端', 'value': '进销存+商品管理+库存预警+欠货统计，适合成长型单店'},
    '生意通会员': {'category': '核心系统-生意通', 'tier': '入门', 'value': '生意通基础功能'},
    '生意通专业版': {'category': '核心系统-生意通', 'tier': '中端', 'value': '生意通进阶功能，适合批发订货场景'},
    '生意通高级版': {'category': '核心系统-生意通', 'tier': '高端', 'value': '多门店管理+采购管理+财务报表+员工权限，适合连锁/规模化'},
    '销货宝微商城标准版': {'category': '线上渠道-微商城', 'tier': '入门', 'value': '微信小程序商城+商品上架+在线支付'},
    '销货宝微商城基础版': {'category': '线上渠道-微商城', 'tier': '中端', 'value': '微信小程序商城+商品上架+在线支付+基础营销'},
    '销货宝微商城专业版': {'category': '线上渠道-微商城', 'tier': '高端', 'value': '微商城+营销插件+分销+直播，全渠道运营'},
    '专属品牌小程序': {'category': '线上渠道-小程序', 'tier': '中端', 'value': '独立品牌小程序+自定义装修+品牌展示'},
    '限时折扣促单宝': {'category': '营销工具', 'tier': '入门', 'value': '限时折扣+会员价+阶梯定价'},
    '限时秒杀促单宝': {'category': '营销工具', 'tier': '入门', 'value': '秒杀活动+库存锁定+倒计时'},
    '批量推款宝': {'category': '营销工具', 'tier': '入门', 'value': '批量推款+客户在线选款+自动分享'},
    '直播卖货': {'category': '营销工具', 'tier': '中端', 'value': '直播带货+引流到店+互动抽奖'},
    '微信自动化经营': {'category': '营销工具', 'tier': '中端', 'value': '自动加好友+群发+朋友圈营销'},
    '专属微信会员卡': {'category': '会员运营', 'tier': '中端', 'value': '微信会员卡+积分+储值+会员画像'},
    '会员积分充值': {'category': '会员运营', 'tier': '入门', 'value': '会员积分充值+消费抵扣+积分商城'},
    '客户积分': {'category': '会员运营', 'tier': '入门', 'value': '客户积分管理+消费累计'},
    '门店': {'category': '门店管理', 'tier': '中端', 'value': '多门店统一管理+门店独立库存+智能调拨'},
    '子帐号': {'category': '账号扩展', 'tier': '入门', 'value': '新增子账号+员工协作+权限分配'},
    '慧店宝': {'category': '硬件-收银', 'tier': '中端', 'value': '收银终端+扫码+打印一体'},
    '慧店宝大屏收银端': {'category': '硬件-收银', 'tier': '高端', 'value': '大屏收银终端+扫码+打印一体，高效收银'},
    'AI绘图': {'category': 'AI工具', 'tier': '入门', 'value': 'AI自动绘图+智能抠图+商品图生成'},
    '以图搜图': {'category': 'AI工具', 'tier': '入门', 'value': '图片搜索商品+快速找款'},
    '商家名片': {'category': '品牌展示', 'tier': '入门', 'value': '电子名片+商品展示+一键拨号'},
    '秦丝进销存云存储费': {'category': '存储扩展', 'tier': '入门', 'value': '扩展进销存数据存储空间'},
    '秦丝生意通云存储费': {'category': '存储扩展', 'tier': '入门', 'value': '扩展生意通数据存储空间'},
    '短信服务': {'category': '增值服务', 'tier': '入门', 'value': '短信通知+营销短信'},
    '数据迁移服务': {'category': '增值服务', 'tier': '中端', 'value': '数据迁移+系统切换协助'},
    '企业微信客户助手': {'category': '私域运营', 'tier': '中端', 'value': '企微客户管理+自动回复+SOP'},
    '联盟版': {'category': '联盟体系', 'tier': '高端', 'value': '联盟商户+资源共享+跨店结算'},
    '联盟版绑定数': {'category': '联盟体系', 'tier': '中端', 'value': '联盟商户绑定数扩展'},
    '多店智擎': {'category': '多店管理', 'tier': '高端', 'value': '多店智能管理+数据分析+决策辅助'},
    '订制（电脑端）打印模板': {'category': '工具', 'tier': '入门', 'value': '自定义打印模板+小票设计'},
    '10本开店管店必看书籍': {'category': '增值服务', 'tier': '入门', 'value': '开店管店实体书籍'},
    '线上卖货六脉神剑电子版': {'category': '增值服务', 'tier': '入门', 'value': '线上卖货方法论电子书'},
    '旺剪-算力': {'category': 'AI工具', 'tier': '中端', 'value': 'AI视频剪辑算力'},
    '旺剪-云空间': {'category': '存储扩展', 'tier': '入门', 'value': '视频剪辑云存储空间'},
}

CORE_INDUSTRIES = ['服装鞋帽', '服装']

# ==================== 数据加载与字段标准化 ====================
with open(DATA_FILE, 'r', encoding='utf-8') as f:
    raw_customers = json.load(f)

print(f'加载 {len(raw_customers)} 条公海客户数据（已过硬性筛选）')

# 第一步：剔除无效客户（测试账号+明确拒绝）
customers = []
removed = []
for c in raw_customers:
    name = c.get('comName', '')
    visit_record = c.get('lastVisitRecord', '') or ''
    is_invalid = False
    # 测试账号
    for kw in INVALID_KEYWORDS:
        if kw in name:
            is_invalid = True
            removed.append((name, '测试账号'))
            break
    if is_invalid:
        continue
    # 明确拒绝
    for kw in INVALID_VISIT_RECORDS:
        if kw in visit_record:
            is_invalid = True
            removed.append((name, f'明确拒绝: {visit_record[:20]}'))
            break
    if is_invalid:
        continue
    customers.append(c)

print(f'剔除无效客户 {len(removed)} 条:')
for name, reason in removed:
    print(f'  - {name}: {reason}')
print(f'有效客户: {len(customers)} 条')

# 字段标准化
for c in customers:
    c['name'] = c.get('comName') or ''
    c['phone'] = c.get('cellphone_full') or c.get('cellphone') or ''
    c['contact'] = c.get('realName') or c.get('crmRealName') or ''
    c['cid_val'] = c.get('cid', '')

    reg_ind = c.get('regIndustry') or ''
    ind = c.get('industry') or ''
    c['industry_val'] = reg_ind if reg_ind and reg_ind != '无' else (ind if ind and ind != '无' else '未填')

    biz = c.get('industryAttribute') or c.get('businessType') or ''
    c['biz_type'] = biz if biz and biz != '无' else '未填'

    store = c.get('storeNumber') or 0
    c['store_count'] = store if store else 0
    c['sub_accounts'] = c.get('userNumber') or 0

    c['active_rate'] = c.get('loginDayRate') or 0
    c['login_days'] = c.get('loginDays') or 0
    c['total_days'] = c.get('allDays') or 0

    pa = c.get('payAmount') or 0
    if not pa:
        pa = c.get('beInviterPayAmount') or 0
    if not pa:
        detail_tmp = c.get('_detail', {})
        obj_tmp = detail_tmp.get('extend', {}).get('object', {}) if isinstance(detail_tmp.get('extend'), dict) else {}
        pay_list_tmp = obj_tmp.get('payServiceConsumeRecordCurrentCountList', []) or []
        if pay_list_tmp:
            pa = len(pay_list_tmp) * 500
    c['pay_amount'] = pa
    c['hard_qty'] = c.get('hardQuantity') or 0

    reg_time = c.get('createTime')
    if isinstance(reg_time, (int, float)) and reg_time > 1000000000000:
        c['reg_date'] = datetime.fromtimestamp(reg_time/1000).strftime('%Y-%m-%d')
    else:
        c['reg_date'] = str(reg_time)[:10] if reg_time else ''

    # 公海客户大多无回访记录，lastVisitRecord可能是文本
    c['last_visit_record'] = c.get('lastVisitRecord') or ''
    c['visit_time'] = c.get('visitTime') or 0
    c['days_since_visit'] = None  # 公海客户回访记录是文本格式，无法精确计算天数

    c['intention'] = c.get('intention') or '无'
    c['status_pool'] = c.get('statusPoolType') or '无'
    sys_map = {1: '进销存', 2: '微商城', 3: 'ERP'}
    c['sys_name'] = sys_map.get(c.get('sysType'), '')
    c['ip_area'] = c.get('ipArea') or ''
    c['web_shop'] = '未开通'  # 公海客户默认未开通微商城，后续通过服务列表确认
    c['advisor'] = '公海客户'  # 公海客户无归属顾问

    # 解析服务到期信息
    detail = c.get('_detail', {})
    ext_obj = detail.get('extend', {}).get('object', {})
    exp_list = ext_obj.get('expirationList', []) or []

    c['services'] = []
    c['expiring_services'] = []
    c['expired_services'] = []
    c['permanent_services'] = []

    for exp in exp_list:
        svc_name = exp.get('serviceName', '')
        enable_end = exp.get('enableEnd')
        buyout = exp.get('buyoutCount', 0)

        if not svc_name:
            continue

        svc_info = {'name': svc_name, 'category': QINSILK_PRODUCTS.get(svc_name, {}).get('category', '其他')}
        c['services'].append(svc_info)

        if enable_end is None or enable_end > 4000000000000:
            c['permanent_services'].append(svc_name)
        else:
            try:
                end_dt = datetime.fromtimestamp(enable_end / 1000)
                days_to_expire = (end_dt - now).days
                svc_info['end_date'] = end_dt.strftime('%Y-%m-%d')
                svc_info['days_to_expire'] = days_to_expire

                if days_to_expire < 0:
                    c['expired_services'].append(svc_name)
                elif days_to_expire <= 60:
                    c['expiring_services'].append(svc_name)
            except:
                pass

    # 如果有微商城服务，更新web_shop状态
    for svc in c['services']:
        if '微商城' in svc['name'] or '商城' in svc['name']:
            c['web_shop'] = '已开通'
            break

    # 付费服务记录
    pay_list = ext_obj.get('payServiceConsumeRecordCurrentCountList', []) or []
    c['pay_services_detail'] = []
    for ps in pay_list:
        c['pay_services_detail'].append({
            'name': ps.get('serviceName', ''),
            'total': ps.get('totalCount', 0),
            'consumed': ps.get('consumedCount', 0),
            'surplus': ps.get('surplusCount', 0)
        })

    # 画像扩展字段
    upi = ext_obj.get('userPromotionInfo', {})
    c['has_weixin'] = upi.get('hasWeixin', 0)
    c['client_level'] = upi.get('clientLevel', '')
    c['shop_mode'] = upi.get('shopMode', '')

# ==================== 6维度评分模型（适配公海客户） ====================
def calc_score(c):
    """公海客户评分：活跃度/行业/业务/规模/回访/机会"""
    score = 0
    reasons = []

    # D1 活跃度（硬性门槛已过>50%，这里细分）
    lr = c.get('active_rate', 0)
    if lr >= 80:
        score += 5; reasons.append('D1活跃度≥80%=5')
    elif lr >= 60:
        score += 4; reasons.append('D1活跃度60-79%=4')
    else:
        score += 3; reasons.append('D1活跃度50-59%=3')

    # D2 行业匹配度
    ind = c.get('industry_val', '')
    if ind in CORE_INDUSTRIES:
        score += 5; reasons.append('D2服装鞋帽=5')
    elif ind == '未填':
        score += 1; reasons.append('D2未填=1')
    else:
        score += 2; reasons.append(f'D2{ind}=2')

    # D3 业务类型
    biz = c.get('biz_type', '')
    if '批发' in biz and '零售' in biz:
        score += 5; reasons.append('D3批零一体=5')
    elif '批发' in biz:
        score += 3; reasons.append('D3批发=3')
    elif '零售' in biz:
        score += 2; reasons.append('D3零售=2')
    else:
        score += 1; reasons.append('D3未填=1')

    # D4 门店规模
    sn = c.get('store_count', 0)
    sa = c.get('sub_accounts', 0)
    total_scale = sn + sa
    if total_scale >= 6:
        score += 5; reasons.append(f'D4规模{total_scale}≥6=5')
    elif total_scale >= 3:
        score += 4; reasons.append(f'D4规模{total_scale}=4')
    elif total_scale >= 1:
        score += 2; reasons.append(f'D4规模{total_scale}=2')
    else:
        score += 1; reasons.append('D4规模0=1')

    # D5 活跃天数（硬性门槛已过>5天，这里细分）
    ld = c.get('login_days', 0)
    if ld >= 20:
        score += 5; reasons.append(f'D5活跃{ld}天≥20=5')
    elif ld >= 10:
        score += 4; reasons.append(f'D5活跃{ld}天=4')
    else:
        score += 3; reasons.append(f'D5活跃{ld}天=3')

    # D6 意向/付费价值（公海客户大多未付费，用意向+服务替代）
    intention = c.get('intention', '无')
    status_pool = c.get('status_pool', '无')
    services_count = len(c.get('services', []))
    has_permanent = len(c.get('permanent_services', []))

    if status_pool == '意向' or intention == '意向':
        score += 5; reasons.append('D6意向客户=5')
    elif status_pool == '下单':
        score += 5; reasons.append('D6已下单=5')
    elif has_permanent > 0:
        score += 4; reasons.append(f'D6永久服务{has_permanent}个=4')
    elif services_count > 0:
        score += 3; reasons.append(f'D6有服务{services_count}个=3')
    else:
        score += 1; reasons.append('D6无服务=1')

    # 机会分加成
    opp_score = 0
    if ind in CORE_INDUSTRIES and '批发' in biz:
        opp_score += 30
    if c.get('login_days', 0) > 15:
        opp_score += 25
    if total_scale >= 3:
        opp_score += 20
    if c.get('expiring_services'):
        opp_score += 15
    if status_pool in ('意向', '下单'):
        opp_score += 20

    if opp_score >= 50:
        score += 3; reasons.append(f'机会分{opp_score}≥50→+3')
    elif opp_score >= 30:
        score += 2; reasons.append(f'机会分{opp_score}≥30→+2')
    elif opp_score >= 15:
        score += 1; reasons.append(f'机会分{opp_score}≥15→+1')

    c['opportunity_score'] = opp_score
    c['score'] = score
    c['score_reasons'] = ' | '.join(reasons)

    # 分级
    if score >= 24 or status_pool in ('意向', '下单') or c.get('expiring_services'):
        c['grade'] = 'A'
    elif score >= 18:
        c['grade'] = 'B'
    else:
        c['grade'] = 'C'

    # 画像规则
    rules = []
    if c.get('expiring_services'):
        rules.append({'rule': 'R1', 'detail': f'到期: {"、".join(c["expiring_services"][:3])}'})
    if c.get('pay_amount', 0) > 3000:
        rules.append({'rule': 'R2', 'detail': f'高付费¥{c["pay_amount"]:.0f}'})
    if c.get('login_days', 0) > 15:
        rules.append({'rule': 'R3', 'detail': f'高活跃{c["login_days"]}天'})
    if sn + sa >= 3:
        rules.append({'rule': 'R4', 'detail': f'规模化{sn+sa}单元'})
    if opp_score >= 50:
        rules.append({'rule': 'R5', 'detail': f'高机会分{opp_score}'})
    c['profile_rules'] = rules
    c['grade_reason'] = ' | '.join([f"{r['rule']}:{r['detail']}" for r in rules]) if rules else f'总分{score}'

for c in customers:
    calc_score(c)

# ==================== A级细分 S/A2/A3（公海版） ====================
SUB_GRADE_ORDER = {'S': 0, 'A2': 1, 'A3': 2, 'B': 3, 'C': 4}

def sub_grade_a(c):
    """公海A级细分：S必跟(24h) / A2重点(48h) / A3常规A(本周)"""
    if c['grade'] != 'A':
        c['sub_grade'] = c['grade']
        c['sub_reason'] = c.get('grade_reason', '')
        return

    status_pool = c.get('status_pool', '无')
    expiring = c.get('expiring_services', [])
    opp = c.get('opportunity_score', 0)
    ld = c.get('login_days', 0)
    sn = c.get('store_count', 0)
    sa = c.get('sub_accounts', 0)

    # S 必跟(24h)：服务即将到期 / 意向客户 / 已下单客户
    if expiring:
        c['sub_grade'] = 'S'
        c['sub_reason'] = f'服务即将到期'
        return
    if status_pool == '意向':
        c['sub_grade'] = 'S'
        c['sub_reason'] = '意向客户'
        return
    if status_pool == '下单':
        c['sub_grade'] = 'S'
        c['sub_reason'] = '已下单客户'
        return

    # A2 重点(48h)：高机会分≥50 / 高活跃(>15天)+规模化(≥3)
    if opp >= 50:
        c['sub_grade'] = 'A2'
        c['sub_reason'] = f'机会分{opp}'
        return
    if ld > 15 and (sn + sa) >= 3:
        c['sub_grade'] = 'A2'
        c['sub_reason'] = f'高活跃{ld}天+规模{sn+sa}单元'
        return

    # A3 常规A
    c['sub_grade'] = 'A3'
    c['sub_reason'] = '常规A级'

for c in customers:
    sub_grade_a(c)

# 排序：S > A2 > A3 > B > C
customers.sort(key=lambda x: (
    SUB_GRADE_ORDER.get(x.get('sub_grade', 'C'), 4),
    -x.get('opportunity_score', 0),
    -x['score'],
    -x.get('login_days', 0)
))

grades = Counter(c['grade'] for c in customers)
sub_grades = Counter(c.get('sub_grade', c['grade']) for c in customers)
print(f'分级结果: A={grades["A"]} B={grades["B"]} C={grades["C"]}')
print(f'A级细分: S={sub_grades.get("S",0)} A2={sub_grades.get("A2",0)} A3={sub_grades.get("A3",0)}')

# ==================== 话术与痛点生成（公海客户·新客户转化视角） ====================
def _parse_contact(contact):
    """解析联系人字段，提取真实姓名"""
    if not contact:
        return None
    s = str(contact).strip()
    if not s:
        return None
    if s.isdigit():
        return None
    if '(' in s or '（' in s:
        s_uni = s.replace('（', '(').replace('）', ')')
        parts = s_uni.split('(')
        before = parts[0].strip()
        inner = parts[1].replace(')', '').strip() if len(parts) > 1 else ''
        before_valid = before and not (before.startswith('店员') or before.startswith('管理员') or before.startswith('店长')) and not before.isdigit()
        if before_valid:
            return before
        inner_valid = inner and not (inner.startswith('店员') or inner.startswith('管理员') or inner.startswith('店长'))
        if inner_valid:
            # "小王""小李"等昵称→取实际姓氏（去掉"小"字）
            if len(inner) == 2 and inner.startswith('小'):
                return inner[1]
            return inner
        return None
    if s.startswith('店员') or s.startswith('管理员') or s.startswith('店长') or s.startswith('老板'):
        return None
    if s.lower().startswith('staff'):
        return None
    return s

def _call_name(c):
    """生成自然称呼——按姓氏"""
    real_name = _parse_contact(c.get('contact', ''))
    if not real_name:
        company = c.get('name', '') or ''
        if not company:
            return '老板'
        s = company.strip()
        if s.startswith('店铺') and any(ch.isdigit() for ch in s):
            return '老板'
        if s in ('管理员', '店长', '老板', '店'):
            return '老板'
        real_name = company
    if not real_name:
        return '老板'
    s = real_name.strip()
    if s.isdigit():
        return '老板'
    if all(ch.isascii() for ch in s):
        letters = [ch for ch in s if ch.isalpha()]
        if letters:
            return f'Mr.{letters[0].upper()}'
        return '老板'
    cn_chars = [ch for ch in s if '\u4e00' <= ch <= '\u9fff']
    if not cn_chars:
        return '老板'
    compound_surnames = ['欧阳', '司马', '诸葛', '上官', '司徒', '司空', '尉迟', '公孙', '令狐', '慕容', '皇甫', '宇文', '东方', '南宫', '西门']
    name_str = ''.join(cn_chars)
    for cs in compound_surnames:
        if name_str.startswith(cs):
            return f'{cs}总'
    return f'{cn_chars[0]}总'

def _opening(c):
    """开场白：公海客户是新注册活跃用户，以了解使用情况切入"""
    lr = c.get('active_rate', 0)
    ld = c.get('login_days', 0)
    ind = c.get('industry_val', '')
    biz = c.get('biz_type', '')
    status_pool = c.get('status_pool', '无')
    expiring = c.get('expiring_services', [])
    call = _call_name(c)

    # 优先级1: 服务即将到期
    if expiring:
        svc_str = '、'.join(expiring[:2])
        return f'{call}，您{svc_str}快到期了，我提前说一声，看您这边是继续用还是想升级一下？', '续费'

    # 优先级2: 意向/已下单客户
    if status_pool == '意向':
        return f'{call}，看到您之前有意向了解我们的系统。您现在用得怎么样？有没有遇到什么问题需要我协助的？', '意向'
    if status_pool == '下单':
        return f'{call}，看到您已经下单了，恭喜。今天回访一下，看您用得还顺手吗？有没有需要指导的地方？', '成交回访'

    # 优先级3: 高活跃客户——了解使用情况
    if ld >= 15:
        return f'{call}，看您注册后用得挺频繁的，{ld}天活跃了。您是做{ind if ind != "未填" else "服装"}{"的"+biz if biz and biz != "未填" else ""}生意对吧？今天聊聊看您有没有什么需要升级或加功能的。', '增值'

    # 优先级4: 中等活跃——了解需求
    if ld >= 8:
        return f'{call}，看您注册后用了{ld}天了。您目前用得怎么样？有没有遇到什么问题？我可以帮您看下怎么更好地用起来。', '培育'

    # 兜底
    return f'{call}，今天打电话问候一下，您系统用得还顺利吗？有什么问题都可以跟我说。', '维护'

def _insight(c):
    """数据洞察：基于公海客户画像生成痛点分析"""
    insights = []
    lr = c.get('active_rate', 0)
    ld = c.get('login_days', 0)
    ind = c.get('industry_val', '')
    biz = c.get('biz_type', '')
    sn = c.get('store_count', 0)
    sa = c.get('sub_accounts', 0)
    expiring = c.get('expiring_services', [])
    services = [s['name'] for s in c.get('services', [])]
    has_permanent = c.get('permanent_services', [])
    status_pool = c.get('status_pool', '无')

    if expiring:
        svc_str = '、'.join(expiring[:3])
        insights.append(f'【到期紧迫】{svc_str}即将到期，需跟进续费')

    if ld >= 15 and lr >= 70:
        insights.append(f'【高活跃潜力】活跃率{lr}%，活跃{ld}天，使用频率高，转化潜力大')
    elif ld >= 8:
        insights.append(f'【中等活跃】活跃率{lr}%，活跃{ld}天，需培育使用习惯')

    if has_permanent:
        insights.append(f'【已购永久服务】{", ".join(has_permanent[:3])}，有付费意愿基础')

    if status_pool == '意向':
        insights.append('【意向客户】已标记意向，转化窗口期，需重点跟进')
    elif status_pool == '下单':
        insights.append('【已成交客户】已下单，需做好使用指导和售后维护')

    # 门店规模洞察
    if sn + sa >= 3:
        if sn >= 2:
            insights.append(f'【多店管理需求】{sn}家门店，有多店统一管理+智能调拨需求')
        elif sa >= 3:
            insights.append(f'【多账号协同】{sa}个子账号，需权限管理和数据隔离')

    # 行业业务洞察
    if '批发' in biz and '零售' in biz:
        insights.append('【批零一体】同时做批发零售，两套价格体系管理需求')
    elif '批发' in biz:
        insights.append('【批发场景】批发客户多订单量大，有批量开单+欠款管理需求')

    # 服务使用洞察
    pay_svcs = c.get('pay_services_detail', [])
    unused = [ps for ps in pay_svcs if ps.get('surplus', 0) > 0]
    if unused:
        svc_names = '、'.join([f"{ps['name']}(余{ps['surplus']})" for ps in unused[:2]])
        insights.append(f'【服务未用完】已购买未使用: {svc_names}')

    if not insights:
        insights.append('【常规跟进】公海新注册客户，需建立联系+需求挖掘')

    return insights

def _gap_products(c):
    """基于画像缺口推荐增值产品"""
    have = set(s['name'] for s in c.get('services', []))
    gaps = []
    ind = c.get('industry_val', '')
    biz = c.get('biz_type', '')
    sn = c.get('store_count', 0)
    sa = c.get('sub_accounts', 0)

    # 门店规模缺口
    if sn + sa >= 3 and '生意通高级版' not in have and '门店' not in have:
        gaps.append(('生意通高级版', '多门店统一管理+采购管理+财务报表+员工权限', '高端款'))
    # 线上渠道缺口
    if c.get('web_shop') == '未开通':
        if '销货宝微商城专业版' not in have:
            gaps.append(('销货宝微商城基础版', '微信小程序商城+商品上架+在线支付+基础营销', '中端款'))
    # 硬件/收银缺口
    if c.get('hard_qty', 0) == 0 and ind in CORE_INDUSTRIES:
        gaps.append(('慧店宝', '收银终端+扫码+打印一体，高效收银', '中端款'))
    # 营销工具缺口
    if '零售' in biz and '限时折扣促单宝' not in have:
        gaps.append(('限时折扣促单宝', '限时折扣+会员价+阶梯定价', '入门款'))
    # 会员运营缺口
    if '专属微信会员卡' not in have and ('零售' in biz or sa >= 3):
        gaps.append(('专属微信会员卡', '微信会员卡+积分+储值+会员画像', '中端款'))
    # 高活跃推AI工具
    if c.get('login_days', 0) > 15 and 'AI绘图' not in have:
        gaps.append(('AI绘图', 'AI自动绘图+智能抠图+商品图生成', '入门款'))
    # 批发客户推批量推款宝
    if '批发' in biz and '批量推款宝' not in have:
        gaps.append(('批量推款宝', '批量推款+客户在线选款+自动分享', '入门款'))
    return gaps[:3]

def _recommend(c):
    """产品推荐：公海客户大多是新客户，推入门/中端款为主"""
    gaps = _gap_products(c)
    if not gaps:
        return '您目前用的功能比较基础，如果想提升效率可以考虑销货宝微商城基础版或专属微信会员卡，把线上渠道和会员体系做起来。'

    # 公海客户以转化为主，推入门/中端款
    if len(gaps) == 1:
        prod, value, tier = gaps[0]
        return f'{prod}（{tier}）——{value}，您可以先了解下，合适的话我帮您开通试用。'
    main_prod, main_val, main_tier = gaps[0]
    others = '、'.join([f'{p[0]}（{p[2]}）' for p in gaps[1:]])
    return f'{main_prod}（{main_tier}）——{main_val}，您可以先了解下。另外{others}也可以看下。'

def _close(c):
    """促单方式"""
    status_pool = c.get('status_pool', '无')
    opp_score = c.get('opportunity_score', 0)

    if status_pool == '意向':
        return '您这边有意向，我今天专门跟您详细聊。您目前最想解决什么问题？我帮您匹配方案。'
    if status_pool == '下单':
        return '您已经下单了，有什么使用问题随时找我，我帮您解决。'
    if opp_score >= 50:
        return '我看您这边需求挺明确的，要不我给您做个方案，明天发您看看？'
    if opp_score >= 30:
        return '您这边可以考虑下，我先把资料发您，有什么问题随时找我。'
    return '您先了解着，有什么问题随时联系我。'

def generate_script_and_painpoints(c):
    """公海客户话术生成——新客户转化视角"""
    opening, opp_tag = _opening(c)
    insights = _insight(c)
    recommend = _recommend(c)
    close = _close(c)

    script = f'{opening} {recommend} {close}'

    c['painpoints'] = '\n'.join(insights)
    c['script'] = script
    c['opportunity_type'] = opp_tag
    action_map = {
        '续费': '24h内致电·确认到期服务+续费方案',
        '意向': '24h内致电·确认真实需求+方案推荐',
        '成交回访': '48h内致电·使用指导+售后维护',
        '增值': '48h内致电·使用情况了解+增值产品推荐',
        '培育': '本周内致电·培育使用习惯+需求挖掘',
        '维护': '月度触达·客情维护+新功能介绍',
    }
    c['action'] = action_map.get(opp_tag, '月度触达·客情维护')

for c in customers:
    generate_script_and_painpoints(c)

# ==================== Excel 生成 ====================
wb = openpyxl.Workbook()

title_font = Font(name='微软雅黑', size=14, bold=True, color='FFFFFF')
title_fill = PatternFill('solid', fgColor='2F5496')
sub_font = Font(name='微软雅黑', size=10, color='FFFFFF')
sub_fill = PatternFill('solid', fgColor='4472C4')
legend_font = Font(name='微软雅黑', size=9, bold=True)
header_font = Font(name='微软雅黑', size=10, bold=True, color='FFFFFF')
header_fill = PatternFill('solid', fgColor='305496')
a_fill = PatternFill('solid', fgColor='FFC7CE')
b_fill = PatternFill('solid', fgColor='FFEB9C')
c_fill = PatternFill('solid', fgColor='C6EFCE')
# A级细分三档颜色（柔和·低饱和·不刺眼）
a1_fill = PatternFill('solid', fgColor='F8D7DA')   # 浅粉·必跟（S级用）
a2_fill = PatternFill('solid', fgColor='FCE4C4')   # 浅橙·重点
a3_fill = PatternFill('solid', fgColor='FFF3E0')  # 米橙·常规A
orange_fill = PatternFill('solid', fgColor='FCE4D6')
red_font = Font(name='微软雅黑', size=11, bold=True, color='9C0006')
border = Border(
    left=Side(style='thin', color='B4C6E7'), right=Side(style='thin', color='B4C6E7'),
    top=Side(style='thin', color='B4C6E7'), bottom=Side(style='thin', color='B4C6E7')
)
center = Alignment(horizontal='center', vertical='center', wrap_text=True)
left_align = Alignment(horizontal='left', vertical='center', wrap_text=True)

# ============ Sheet1: 跟进名单（含画像+话术+痛点）============
ws1 = wb.active
ws1.title = '跟进名单+话术痛点'

ws1.merge_cells('A1:Z1')
ws1['A1'] = f'成都分部 SDR 公海客户跟进名单 v1.0（严格筛选+画像分析+沟通话术）'
ws1['A1'].font = title_font; ws1['A1'].fill = title_fill; ws1['A1'].alignment = center
ws1.row_dimensions[1].height = 30

ws1.merge_cells('A2:Z2')
ws1['A2'] = (f'数据基准：2026-07-02 · 公海客户6月至今注册 · 硬性筛选(活跃度>50%且活跃天数>5天) · '
             f'全量5792条 → 过筛{len(customers)}条 · S级必跟{sub_grades.get("S",0)} / A2重点{sub_grades.get("A2",0)} / A3常规{sub_grades.get("A3",0)} / B类{grades["B"]} / C类{grades["C"]}')
ws1['A2'].font = sub_font; ws1['A2'].fill = sub_fill; ws1['A2'].alignment = center
ws1.row_dimensions[2].height = 22

ws1.merge_cells('A3:B3'); ws1['A3'] = 'S级必跟(24h)'
ws1['A3'].font = legend_font; ws1['A3'].fill = a1_fill; ws1['A3'].alignment = center
ws1.merge_cells('C3:D3'); ws1['C3'] = 'A2重点(48h)'
ws1['C3'].font = legend_font; ws1['C3'].fill = a2_fill; ws1['C3'].alignment = center
ws1.merge_cells('E3:F3'); ws1['E3'] = 'A3常规A(本周)'
ws1['E3'].font = legend_font; ws1['E3'].fill = a3_fill; ws1['E3'].alignment = center
ws1.merge_cells('G3:H3'); ws1['G3'] = 'B级·本周触达'
ws1['G3'].font = legend_font; ws1['G3'].fill = b_fill; ws1['G3'].alignment = center
ws1.merge_cells('I3:J3'); ws1['I3'] = 'C级·常规维护'
ws1['I3'].font = legend_font; ws1['I3'].fill = c_fill; ws1['I3'].alignment = center
ws1.merge_cells('K3:Z3'); ws1['K3'] = '⚠红底=有服务即将到期 | 黄底=意向客户 | 橙底=高活跃潜力'
ws1['K3'].font = legend_font; ws1['K3'].fill = orange_fill; ws1['K3'].alignment = center
ws1.row_dimensions[3].height = 20

headers = [
    '优先级', '公司名称', '联系人', 'CID', '顾问', '行业', '业务类型',
    '门店/子账号', '系统', '活跃率', '活跃/总天数', '付费金额', '硬件',
    '注册日期', '上次回访', '回访次数', '意向',
    'R1到期', 'R2高付费', 'R3高活跃', 'R4多门店', 'R5机会评判',
    '机会分', '总分', '触发规则',
    '痛点分析', '沟通话术', '建议动作', '机会类型'
]
for col, h in enumerate(headers, 1):
    cell = ws1.cell(4, col, h)
    cell.font = header_font; cell.fill = header_fill; cell.alignment = center; cell.border = border
ws1.row_dimensions[4].height = 32

row = 5
for c in customers:
    grade = c['grade']
    sub_grade = c.get('sub_grade', grade)
    sn = c.get('store_count', 0)
    sa = c.get('sub_accounts', 0)
    expiring = c.get('expiring_services', [])
    pa = c.get('pay_amount', 0)
    status_pool = c.get('status_pool', '无')

    ws1.cell(row, 1, sub_grade)
    ws1.cell(row, 2, c.get('name', ''))
    ws1.cell(row, 3, c.get('contact', ''))
    ws1.cell(row, 4, c.get('cid_val', ''))
    ws1.cell(row, 5, c.get('advisor', '公海'))
    ws1.cell(row, 6, c.get('industry_val', ''))
    ws1.cell(row, 7, c.get('biz_type', ''))
    ws1.cell(row, 8, f"{sn}店/{sa}账号")
    ws1.cell(row, 9, c.get('sys_name', ''))
    ws1.cell(row, 10, f"{c.get('active_rate', 0)}%")
    ws1.cell(row, 11, f"{c.get('login_days', 0)}/{c.get('total_days', 0)}")
    ws1.cell(row, 12, f"¥{pa:.0f}" if pa > 0 else '未付费')
    ws1.cell(row, 13, c.get('hard_qty', 0))
    ws1.cell(row, 14, c.get('reg_date', ''))
    ws1.cell(row, 15, c.get('last_visit_record', '无')[:50])
    ws1.cell(row, 16, c.get('visit_time', 0))
    ws1.cell(row, 17, status_pool)

    ws1.cell(row, 18, '⚠是' if expiring else '否')
    ws1.cell(row, 19, f"¥{pa:.0f}" if pa > 3000 else '否')
    ws1.cell(row, 20, f"{c.get('login_days',0)}天" if c.get('login_days', 0) > 15 else '否')
    ws1.cell(row, 21, f"{sn+sa}单元" if (sn + sa) >= 3 else '否')

    opp_detail = c.get('profile_rules', [{}])[-1].get('detail', '') if c.get('profile_rules') else ''
    ws1.cell(row, 22, opp_detail[:60])

    ws1.cell(row, 23, c.get('opportunity_score', 0))
    ws1.cell(row, 24, c['score'])
    ws1.cell(row, 25, c.get('grade_reason', ''))
    ws1.cell(row, 26, c.get('painpoints', ''))
    ws1.cell(row, 27, c.get('script', ''))
    ws1.cell(row, 28, c.get('action', ''))
    ws1.cell(row, 29, c.get('opportunity_type', ''))

    for col in range(1, 30):
        cell = ws1.cell(row, col)
        cell.border = border
        cell.alignment = center if col in [1, 8, 10, 11, 12, 13, 16, 17, 18, 19, 20, 21, 23, 24] else left_align
        if col == 1:
            if sub_grade == 'S':
                cell.fill = a1_fill; cell.font = Font(name='微软雅黑', size=11, bold=True, color='9C0006')
            elif sub_grade == 'A2':
                cell.fill = a2_fill; cell.font = Font(name='微软雅黑', size=11, bold=True, color='8B4500')
            elif sub_grade == 'A3':
                cell.fill = a3_fill; cell.font = red_font
            elif grade == 'B':
                cell.fill = b_fill; cell.font = Font(name='微软雅黑', size=11, bold=True, color='9C6500')
            else:
                cell.fill = c_fill; cell.font = Font(name='微软雅黑', size=11, bold=True, color='006100')
        else:
            cell.font = Font(name='微软雅黑', size=9)

    row += 1

# 列宽
col_widths = [6, 20, 14, 12, 8, 10, 10, 12, 10, 9, 10, 10, 6, 11, 30, 8, 8, 8, 10, 10, 10, 15, 8, 6, 30, 40, 60, 20, 10]
for i, w in enumerate(col_widths, 1):
    ws1.column_dimensions[get_column_letter(i)].width = w

# ============ Sheet2: S类必跟客户话术 ============
ws2 = wb.create_sheet('S类必跟客户话术')
a1_customers = [c for c in customers if c.get('sub_grade') == 'S']

ws2.merge_cells('A1:I1')
ws2['A1'] = f'S类必跟客户话术（{len(a1_customers)}条 · 24小时内必触达）'
ws2['A1'].font = title_font; ws2['A1'].fill = PatternFill('solid', fgColor='C0504D'); ws2['A1'].alignment = center
ws2.row_dimensions[1].height = 30

a_headers = ['公司名称', '联系人', 'CID', '行业/业务', '活跃率', '活跃天数', '细分原因', '痛点分析', '沟通话术', '建议动作']
for col, h in enumerate(a_headers, 1):
    cell = ws2.cell(2, col, h)
    cell.font = header_font; cell.fill = header_fill; cell.alignment = center; cell.border = border
ws2.row_dimensions[2].height = 32

row = 3
for c in a1_customers:
    ws2.cell(row, 1, c.get('name', ''))
    ws2.cell(row, 2, c.get('contact', ''))
    ws2.cell(row, 3, c.get('cid_val', ''))
    ws2.cell(row, 4, f"{c.get('industry_val','')}/{c.get('biz_type','')}")
    ws2.cell(row, 5, f"{c.get('active_rate', 0)}%")
    ws2.cell(row, 6, f"{c.get('login_days', 0)}天")
    ws2.cell(row, 7, c.get('sub_reason', ''))
    ws2.cell(row, 8, c.get('painpoints', ''))
    ws2.cell(row, 9, c.get('script', ''))
    ws2.cell(row, 10, c.get('action', ''))
    for col in range(1, 11):
        ws2.cell(row, col).border = border
        ws2.cell(row, col).alignment = left_align
        ws2.cell(row, col).font = Font(name='微软雅黑', size=9)
        ws2.cell(row, col).fill = a1_fill
    ws2.row_dimensions[row].height = 80
    row += 1

for i, w in enumerate([20, 14, 12, 15, 9, 10, 18, 40, 60, 25], 1):
    ws2.column_dimensions[get_column_letter(i)].width = w

# ============ Sheet3: 服务到期预警 ============
ws3 = wb.create_sheet('服务到期预警')
expiring_items = []
for c in customers:
    for svc in c.get('services', []):
        if 'days_to_expire' in svc and svc['days_to_expire'] <= 60:
            expiring_items.append({
                'name': c.get('name', ''),
                'cid': c.get('cid_val', ''),
                'contact': c.get('contact', ''),
                'service': svc['name'],
                'end_date': svc.get('end_date', ''),
                'days': svc.get('days_to_expire', 0)
            })

ws3.merge_cells('A1:G1')
ws3['A1'] = f'服务到期预警（60天内到期 {len(expiring_items)} 项）'
ws3['A1'].font = title_font; ws3['A1'].fill = PatternFill('solid', fgColor='C0504D'); ws3['A1'].alignment = center
ws3.row_dimensions[1].height = 30

exp_headers = ['公司名称', 'CID', '联系人', '服务名称', '到期日期', '剩余天数', '建议动作']
for col, h in enumerate(exp_headers, 1):
    cell = ws3.cell(2, col, h)
    cell.font = header_font; cell.fill = header_fill; cell.alignment = center; cell.border = border

row = 3
for item in sorted(expiring_items, key=lambda x: x['days']):
    ws3.cell(row, 1, item['name'])
    ws3.cell(row, 2, item['cid'])
    ws3.cell(row, 3, item['contact'])
    ws3.cell(row, 4, item['service'])
    ws3.cell(row, 5, item['end_date'])
    ws3.cell(row, 6, f"{item['days']}天" if item['days'] > 0 else '已过期')
    ws3.cell(row, 7, '24h内致电续费' if item['days'] <= 7 else '本周内致电续费')
    for col in range(1, 8):
        ws3.cell(row, col).border = border
        ws3.cell(row, col).alignment = center
        ws3.cell(row, col).font = Font(name='微软雅黑', size=9)
        if item['days'] <= 7:
            ws3.cell(row, col).fill = a_fill
    row += 1

for i, w in enumerate([20, 12, 14, 18, 12, 10, 20], 1):
    ws3.column_dimensions[get_column_letter(i)].width = w

# ============ Sheet4: 画像分析 ============
ws4 = wb.create_sheet('画像分析')

ws4.merge_cells('A1:D1')
ws4['A1'] = '公海客户画像分析'
ws4['A1'].font = title_font; ws4['A1'].fill = title_fill; ws4['A1'].alignment = center
ws4.row_dimensions[1].height = 30

row = 3
# 分级分布
ws4.cell(row, 1, '【分级分布】').font = legend_font
row += 1
for grade in ['A', 'B', 'C']:
    cnt = grades.get(grade, 0)
    ws4.cell(row, 2, f'{grade}级')
    ws4.cell(row, 3, f'{cnt}条')
    ws4.cell(row, 4, f'{cnt/len(customers)*100:.1f}%')
    row += 1

row += 1
# 行业分布
ws4.cell(row, 1, '【行业分布】').font = legend_font
row += 1
ind_counter = Counter(c.get('industry_val', '未填') for c in customers)
for ind, cnt in ind_counter.most_common():
    ws4.cell(row, 2, ind)
    ws4.cell(row, 3, f'{cnt}条')
    ws4.cell(row, 4, f'{cnt/len(customers)*100:.1f}%')
    row += 1

row += 1
# 业务类型分布
ws4.cell(row, 1, '【业务类型分布】').font = legend_font
row += 1
biz_counter = Counter(c.get('biz_type', '未填') for c in customers)
for biz, cnt in biz_counter.most_common():
    ws4.cell(row, 2, biz)
    ws4.cell(row, 3, f'{cnt}条')
    ws4.cell(row, 4, f'{cnt/len(customers)*100:.1f}%')
    row += 1

row += 1
# 活跃度分布
ws4.cell(row, 1, '【活跃度分布】').font = legend_font
row += 1
for label, cond in [('50-59%', lambda x: 50 <= x < 60), ('60-79%', lambda x: 60 <= x < 80), ('80%+', lambda x: x >= 80)]:
    cnt = sum(1 for c in customers if cond(c.get('active_rate', 0)))
    ws4.cell(row, 2, label)
    ws4.cell(row, 3, f'{cnt}条')
    ws4.cell(row, 4, f'{cnt/len(customers)*100:.1f}%')
    row += 1

for i, w in enumerate([15, 15, 10, 10], 1):
    ws4.column_dimensions[get_column_letter(i)].width = w

# ============ Sheet5: 可视化看板 ============
ws5 = wb.create_sheet('可视化看板')

ws5.merge_cells('A1:H1')
ws5['A1'] = '公海客户可视化看板'
ws5['A1'].font = title_font; ws5['A1'].fill = title_fill; ws5['A1'].alignment = center
ws5.row_dimensions[1].height = 30

ws5.merge_cells('A2:H2')
ws5['A2'] = f'全量5792条 → 硬性筛选过筛{len(customers)}条 · 剔除率{((5792-len(customers))/5792*100):.1f}% · 筛选标准: 活跃度>50% + 活跃天数>5天'
ws5['A2'].font = sub_font; ws5['A2'].fill = sub_fill; ws5['A2'].alignment = center
ws5.row_dimensions[2].height = 22

# KPI指标卡
kpis = [
    ('公海总量', '5792'),
    ('过筛客户', f'{len(customers)}'),
    ('过筛率', f'{len(customers)/5792*100:.2f}%'),
    ('S级必跟', f'{sub_grades.get("S",0)}'),
    ('A2重点', f'{sub_grades.get("A2",0)}'),
    ('A3常规', f'{sub_grades.get("A3",0)}'),
    ('意向客户', f'{sum(1 for c in customers if c.get("status_pool")=="意向")}'),
    ('已成交', f'{sum(1 for c in customers if c.get("status_pool")=="下单")}'),
]
for i, (label, val) in enumerate(kpis):
    col = i * 2 + 1
    ws5.cell(4, col, label).font = Font(name='微软雅黑', size=9, bold=True)
    ws5.cell(4, col).alignment = center
    ws5.cell(4, col).fill = PatternFill('solid', fgColor='D9E1F2')
    ws5.cell(5, col, val).font = Font(name='微软雅黑', size=14, bold=True, color='2F5496')
    ws5.cell(5, col).alignment = center
    ws5.cell(5, col).fill = PatternFill('solid', fgColor='D9E1F2')
ws5.row_dimensions[4].height = 20
ws5.row_dimensions[5].height = 30

# 数据区：分级分布
ws5.cell(7, 1, '分级').font = legend_font
ws5.cell(7, 2, '数量').font = legend_font
grade_data = [('S', sub_grades.get('S', 0)), ('A2', sub_grades.get('A2', 0)), ('A3', sub_grades.get('A3', 0)), ('B', grades['B']), ('C', grades['C'])]
for i, (g, n) in enumerate(grade_data):
    ws5.cell(8+i, 1, g)
    ws5.cell(8+i, 2, n)

# 饼图：分级分布
pie = PieChart()
labels = Reference(ws5, min_col=1, min_row=8, max_row=12)
data = Reference(ws5, min_col=2, min_row=7, max_row=12)
pie.add_data(data, titles_from_data=True)
pie.set_categories(labels)
pie.title = '分级分布'
pie.height = 8
pie.width = 12
ws5.add_chart(pie, 'D7')

# 数据区：行业分布
ws5.cell(13, 1, '行业').font = legend_font
ws5.cell(13, 2, '数量').font = legend_font
for i, (ind, cnt) in enumerate(ind_counter.most_common()):
    ws5.cell(14+i, 1, ind)
    ws5.cell(14+i, 2, cnt)

# 柱状图：行业分布
bar = BarChart()
bar.type = 'bar'
bar.style = 10
labels2 = Reference(ws5, min_col=1, min_row=14, max_row=13+len(ind_counter))
data2 = Reference(ws5, min_col=2, min_row=13, max_row=13+len(ind_counter))
bar.add_data(data2, titles_from_data=True)
bar.set_categories(labels2)
bar.title = '行业分布'
bar.height = 8
bar.width = 12
ws5.add_chart(bar, 'D13')

for i, w in enumerate([12, 10, 10, 10, 10, 10, 10, 10], 1):
    ws5.column_dimensions[get_column_letter(i)].width = w

# ============ Sheet6: 筛选方法论 ============
ws6 = wb.create_sheet('筛选方法论')

ws6.merge_cells('A1:B1')
ws6['A1'] = '公海客户筛选方法论'
ws6['A1'].font = title_font; ws6['A1'].fill = title_fill; ws6['A1'].alignment = center
ws6.row_dimensions[1].height = 30

methodology = [
    ('【数据来源】', ''),
    ('数据源', '秦丝CRM公海客户（department:-1, queryGroupList:[-1]）'),
    ('时间范围', '2026-06-01 至 2026-07-02'),
    ('全量数据', '5792条'),
    ('', ''),
    ('【硬性筛选门槛】', ''),
    ('活跃度', '>50%（loginDayRate > 50）'),
    ('活跃天数', '>5天（loginDays > 5）'),
    ('过筛结果', f'{len(customers)}条（过筛率{len(customers)/5792*100:.2f}%）'),
    ('', ''),
    ('【无效客户剔除】', ''),
    ('测试账号', '公司内部测试账号等'),
    ('明确拒绝', '回访记录含"不要了""已放弃"等'),
    ('剔除数量', f'{len(removed)}条'),
    ('', ''),
    ('【评分模型 6维度】', ''),
    ('D1 活跃度(5)', '80%+=5 | 60-79%=4 | 50-59%=3'),
    ('D2 行业匹配度(5)', '未填=1 | 非核心=2 | 服装鞋帽=5'),
    ('D3 业务类型(5)', '未填=1 | 零售=2 | 批发=3 | 批零一体=5'),
    ('D4 门店规模(5)', '0=1 | 1-2单元=2 | 3-5单元=4 | 6+单元=5'),
    ('D5 活跃天数(5)', '20+天=5 | 10-19天=4 | 5-9天=3'),
    ('D6 意向/付费(5)', '无服务=1 | 有服务=3 | 永久服务=4 | 意向/下单=5'),
    ('规则加成', '机会分≥50→+3 | ≥30→+2 | ≥15→+1'),
    ('', ''),
    ('【分级标准 v1.1 · A级细分】', ''),
    ('S级 必跟(24h)', '服务即将到期 / 意向客户 / 已下单客户'),
    ('A2 重点(48h)', '机会分≥50 / 高活跃(>15天)+规模化(≥3)'),
    ('A3 常规A(本周)', '其余A级(总分≥24)'),
    ('B级', '总分≥18'),
    ('C级', '总分<18'),
    ('', ''),
    ('【话术生成原则】', ''),
    ('称呼', '按联系人姓氏称呼（张玲→张总）'),
    ('开场', '公海新客户以了解使用情况切入，不破冰'),
    ('推荐', '基于画像缺口+客单价分层推荐产品'),
    ('促单', '意向+机会分驱动，分4档促单强度'),
    ('', ''),
    ('【秦丝产品线】', ''),
    ('核心系统-进销存', '进销存会员/进销存专业版'),
    ('核心系统-生意通', '生意通会员/生意通专业版/生意通高级版'),
    ('线上渠道-微商城', '销货宝微商城标准版/基础版/专业版'),
    ('营销工具', '限时折扣促单宝/限时秒杀促单宝/批量推款宝/直播卖货/微信自动化经营'),
    ('会员运营', '专属微信会员卡/会员积分充值/客户积分'),
    ('硬件-收银', '慧店宝/慧店宝大屏收银端'),
    ('AI工具', 'AI绘图/以图搜图'),
    ('门店/账号扩展', '门店/子帐号'),
]

for row_idx, (label, value) in enumerate(methodology, start=2):
    ws6.cell(row_idx, 1, label).font = Font(name='微软雅黑', size=10, bold=True) if label else Font(name='微软雅黑', size=10)
    ws6.cell(row_idx, 2, value).font = Font(name='微软雅黑', size=10)
    ws6.cell(row_idx, 1).alignment = left_align
    ws6.cell(row_idx, 2).alignment = left_align

ws6.column_dimensions['A'].width = 25
ws6.column_dimensions['B'].width = 60

# ==================== 保存 ====================
wb.save(OUTPUT_FILE)
print(f'\nOK saved: {OUTPUT_FILE}')
print(f'  Sheet1: 跟进名单+话术痛点 ({len(customers)}条)')
print(f'  Sheet2: S类必跟客户话术 ({len(a1_customers)}条)')
print(f'  Sheet3: 服务到期预警 ({len(expiring_items)}项)')
print(f'  Sheet4: 画像分析')
print(f'  Sheet5: 可视化看板')
print(f'  Sheet6: 筛选方法论')

print(f'\n分级统计: S={sub_grades.get("S",0)} A2={sub_grades.get("A2",0)} A3={sub_grades.get("A3",0)} B={grades["B"]} C={grades["C"]}')

print(f'\n=== 机会类型分布 ===')
opp_types = Counter(c['opportunity_type'] for c in customers)
for ot, cnt in opp_types.most_common():
    print(f'  {ot}: {cnt}条')

print(f'\n=== 5维规则触发统计 ===')
r1 = sum(1 for c in customers if c.get('expiring_services'))
r2 = sum(1 for c in customers if c.get('pay_amount', 0) > 3000)
r3 = sum(1 for c in customers if c.get('login_days', 0) > 15)
r4 = sum(1 for c in customers if c.get('store_count', 0) + c.get('sub_accounts', 0) >= 3)
r5 = sum(1 for c in customers if c.get('opportunity_score', 0) >= 50)
print(f'  R1 系统即将到期: {r1}条')
print(f'  R2 高付费>3000: {r2}条')
print(f'  R3 高活跃>15天: {r3}条({r3/len(customers)*100:.1f}%)')
print(f'  R4 多门店/账号: {r4}条({r4/len(customers)*100:.1f}%)')
print(f'  R5 高机会分≥50: {r5}条({r5/len(customers)*100:.1f}%)')

print(f'\n=== 服务到期预警 ===')
if expiring_items:
    exp_7 = sum(1 for item in expiring_items if item['days'] <= 7)
    exp_30 = sum(1 for item in expiring_items if item['days'] <= 30)
    print(f'  60天内到期: {len(expiring_items)}项服务')
    print(f'  7天内到期: {exp_7}项')
    print(f'  30天内到期: {exp_30}项')
else:
    print(f'  无服务即将到期')
