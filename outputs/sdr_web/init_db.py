#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SDR Web 数据库初始化脚本
从 chengdu_final_enriched.json 导入客户数据到 SQLite，
并在导入时计算6维评分、机会分、分级(S/A2/A3/B/C)、痛点、话术、动作。
"""
import json
import os
import re
import sys
import io
import sqlite3
from datetime import datetime, timedelta
from collections import Counter

# Windows终端默认GBK，强制stdout为UTF-8
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
except:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'sdr.db')
DATA_FILE = os.path.join(BASE_DIR, '..', 'chengdu_final_enriched.json')

now = datetime.now()

# ==================== 行业画像库 ====================
CORE_INDUSTRIES = ['服装鞋帽', '服装']

INDUSTRY_SCORE = {
    '服装鞋帽': 5, '服装': 5,
    '食品饮料': 4, '数码家电': 4, '美妆代购': 4, '母婴玩具': 4,
    '烟酒茶叶': 4, '珠宝饰品': 4, '商超便利': 4, '水果生鲜': 4,
    '手机配件': 4,
    '日用百货': 3, '家装建材': 3, '家居家纺': 3, '五金机械': 3,
    '汽修汽配': 3, '文体图书': 3, '农药化肥': 3, '宠物用品': 3,
}

INDUSTRY_PAINPOINTS = {
    '服装鞋帽': ['款式SKU多难管理', '换季库存积压风险', '颜色尺码组合爆炸', '需要批量推款给客户'],
    '服装': ['款式SKU多难管理', '换季库存积压风险', '颜色尺码组合爆炸'],
    '食品饮料': ['保质期管理难·过期损耗', '批次追溯需求', '临期商品促销'],
    '水果生鲜': ['保质期极短·损耗大', '每日库存周转', '临期快速清仓'],
    '数码家电': ['序列号/IMEI管理', '价格波动快·调价频繁', '保修期追溯'],
    '手机配件': ['SKU繁多·型号适配复杂', '价格波动快', '需要序列号管理'],
    '美妆代购': ['会员复购运营·积分体系', '批次/临期管理', '代购多渠道客户管理'],
    '母婴玩具': ['会员复购·宝宝成长周期', '安全合规追溯', '积分运营'],
    '烟酒茶叶': ['防伪溯源需求', '批次/年份管理', '高价值商品库存'],
    '珠宝饰品': ['高价值商品防伪', '会员VIP运营', '定制订单管理'],
    '商超便利': ['收银效率·排队', '快消品高频周转', '会员储值'],
    '日用百货': ['SKU多而杂', '库存盘点繁琐', '低毛利跑量'],
    '家装建材': ['大宗商品·批次管理', '订单周期长', '送货安装协调'],
    '家居家纺': ['SKU多·花色规格', '换季库存', '会员复购'],
    '五金机械': ['规格型号复杂', 'B2B批发订货', '库存价值高'],
    '汽修汽配': ['配件型号适配复杂', 'B2B批发', '库存价值高'],
    '文体图书': ['SKU海量·盘点难', '低毛利跑量', '会员复购'],
    '农药化肥': ['季节性强', '批次追溯', 'B2B批发'],
    '宠物用品': ['会员复购·宠物档案', 'SKU多', '积分运营'],
}

INDUSTRY_RECOMMEND = {
    '服装鞋帽': ['批量推款宝', 'AI绘图', '销货宝微商城专业版'],
    '服装': ['批量推款宝', 'AI绘图', '销货宝微商城专业版'],
    '食品饮料': ['进销存专业版', '限时折扣促单宝'],
    '水果生鲜': ['进销存专业版', '限时秒杀促单宝'],
    '数码家电': ['进销存专业版', '销货宝微商城基础版'],
    '手机配件': ['进销存专业版', '批量推款宝'],
    '美妆代购': ['专属微信会员卡', '会员积分充值', '销货宝微商城专业版'],
    '母婴玩具': ['专属微信会员卡', '会员积分充值', '销货宝微商城基础版'],
    '烟酒茶叶': ['进销存专业版', '专属微信会员卡'],
    '珠宝饰品': ['专属微信会员卡', '进销存专业版'],
    '商超便利': ['慧店宝', '专属微信会员卡', '限时折扣促单宝'],
    '日用百货': ['进销存专业版', '销货宝微商城基础版'],
    '家装建材': ['生意通专业版', '销货宝微商城基础版'],
    '家居家纺': ['进销存专业版', '专属微信会员卡'],
    '五金机械': ['生意通专业版', '批量推款宝'],
    '汽修汽配': ['生意通专业版', '进销存专业版'],
    '文体图书': ['进销存专业版', '专属微信会员卡'],
    '农药化肥': ['生意通专业版', '进销存专业版'],
    '宠物用品': ['专属微信会员卡', '销货宝微商城基础版'],
}

QINSILK_PRODUCTS = {
    '进销存会员': '进销存基础功能，适合单店起步',
    '进销存专业版': '进销存+商品管理+库存预警+欠货统计，适合成长型单店',
    '生意通会员': '生意通基础功能',
    '生意通专业版': '生意通进阶功能，适合批发订货场景',
    '生意通高级版': '多门店管理+采购管理+财务报表+员工权限，适合连锁/规模化',
    '销货宝微商城标准版': '微信小程序商城+商品上架+在线支付',
    '销货宝微商城基础版': '微信小程序商城+商品上架+在线支付+基础营销',
    '销货宝微商城专业版': '微商城+营销插件+分销+直播，全渠道运营',
    '专属品牌小程序': '独立品牌小程序+自定义装修+品牌展示',
    '限时折扣促单宝': '限时折扣+会员价+阶梯定价',
    '限时秒杀促单宝': '秒杀活动+库存锁定+倒计时',
    '批量推款宝': '批量推款+客户在线选款+自动分享',
    '直播卖货': '直播带货+引流到店+互动抽奖',
    '微信自动化经营': '自动加好友+群发+朋友圈营销',
    '专属微信会员卡': '微信会员卡+积分+储值+会员画像',
    '会员积分充值': '会员积分充值+消费抵扣+积分商城',
    '客户积分': '客户积分管理+消费累计',
    '门店': '多门店统一管理+门店独立库存+智能调拨',
    '子帐号': '新增子账号+员工协作+权限分配',
    '慧店宝': '收银终端+扫码+打印一体',
    '慧店宝大屏收银端': '大屏收银终端+扫码+打印一体，高效收银',
    'AI绘图': 'AI自动绘图+智能抠图+商品图生成',
    '以图搜图': '图片搜索商品+快速找款',
    '商家名片': '电子名片+商品展示+一键拨号',
    '企业微信客户助手': '企微客户管理+自动回复+SOP',
    '联盟版': '联盟商户+资源共享+跨店结算',
    '多店智擎': '多店智能管理+数据分析+决策辅助',
}


def get_industry_score(ind):
    if not ind or ind == '未填':
        return 1
    return INDUSTRY_SCORE.get(ind, 2)


def parse_int(val, default=0):
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return int(val)
    m = re.search(r'(\d+)', str(val))
    return int(m.group(1)) if m else default


def parse_float(val, default=0.0):
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val)
    m = re.search(r'([\d.]+)', str(val))
    return float(m.group(1)) if m else default


# ==================== 数据加载与字段标准化 ====================
def load_customers():
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    customers = []
    for c in raw:
        rec = {}
        rec['cid'] = str(c.get('cid') or '')
        rec['name'] = c.get('comName') or ''
        rec['contact'] = c.get('realName') or c.get('crmRealName') or ''
        rec['phone'] = c.get('cellphone_full') or c.get('cellphone') or ''

        reg_ind = c.get('regIndustry') or ''
        ind = c.get('industry') or ''
        rec['industry'] = reg_ind if reg_ind and reg_ind != '无' else (ind if ind and ind != '无' else '未填')

        biz = c.get('businessType') or c.get('industryAttribute') or ''
        rec['biz_type'] = biz if biz else '未填'

        rec['store_count'] = parse_int(c.get('storeNumber'))
        rec['sub_accounts'] = parse_int(c.get('userNumber'))

        rec['active_rate'] = parse_float(c.get('loginDayRate'))
        rec['login_days'] = parse_int(c.get('loginDays'))
        rec['total_days'] = parse_int(c.get('allDays'))

        # 付费金额：payAmount(成都全null) → beInviterPayAmount → payServiceConsumeRecordCurrentCountList × 500
        pa = c.get('payAmount') or 0
        if not pa:
            pa = c.get('beInviterPayAmount') or 0
        if not pa:
            detail_tmp = c.get('_detail', {})
            obj_tmp = detail_tmp.get('extend', {}).get('object', {}) if isinstance(detail_tmp.get('extend'), dict) else {}
            pay_list_tmp = obj_tmp.get('payServiceConsumeRecordCurrentCountList', []) or []
            if pay_list_tmp:
                pa = len(pay_list_tmp) * 500
        rec['pay_amount'] = float(pa or 0)

        rec['hard_qty'] = parse_int(c.get('hardQuantity'))

        rec['last_visit_record'] = c.get('lastVisitRecord') or ''

        # 回访时间解析
        vr = c.get('visitTime')
        days_since = None
        visit_time_ts = None
        if vr:
            if isinstance(vr, (int, float)) and vr > 1000000000000:
                visit_time_ts = int(vr)
                try:
                    dt_vr = datetime.fromtimestamp(vr / 1000)
                    days_since = (now - dt_vr).days
                except:
                    pass
            elif isinstance(vr, str) and vr:
                for fmt in ('%Y/%m/%d %H:%M', '%Y-%m-%d %H:%M:%S', '%Y/%m/%d', '%Y-%m-%d'):
                    try:
                        dt_vr = datetime.strptime(vr[:19] if '%H' in fmt else vr[:10], fmt)
                        days_since = (now - dt_vr).days
                        visit_time_ts = int(dt_vr.timestamp() * 1000)
                        break
                    except:
                        pass
        rec['visit_time'] = visit_time_ts if visit_time_ts else 0
        rec['days_since_visit'] = days_since

        rec['intention'] = c.get('intention') or '无'
        rec['sys_type'] = parse_int(c.get('sysType'))

        reg_time = c.get('registerTime') or ''
        if isinstance(reg_time, (int, float)) and reg_time > 1000000000000:
            try:
                reg_time = datetime.fromtimestamp(reg_time / 1000).strftime('%Y-%m-%d')
            except:
                reg_time = ''
        rec['reg_date'] = str(reg_time)[:10] if reg_time else ''

        # 服务到期解析
        detail = c.get('_detail', {})
        ext_obj = detail.get('extend', {}).get('object', {}) if isinstance(detail.get('extend'), dict) else {}
        exp_list = ext_obj.get('expirationList', []) or []

        services = []
        expiring_services = []
        for exp in exp_list:
            svc_name = exp.get('serviceName', '')
            if not svc_name:
                continue
            enable_end = exp.get('enableEnd')
            svc_info = {'name': svc_name}
            if enable_end is None or enable_end > 4000000000000:
                svc_info['end_date'] = '永久'
                svc_info['days_to_expire'] = None
            else:
                try:
                    end_dt = datetime.fromtimestamp(enable_end / 1000)
                    d = (end_dt - now).days
                    svc_info['end_date'] = end_dt.strftime('%Y-%m-%d')
                    svc_info['days_to_expire'] = d
                    if 0 <= d <= 60:
                        expiring_services.append(svc_name)
                except:
                    svc_info['end_date'] = ''
                    svc_info['days_to_expire'] = None
            services.append(svc_info)

        rec['services'] = services
        rec['expiring_services'] = expiring_services

        customers.append(rec)

    # 按cid去重，保留第一条
    seen = set()
    unique = []
    dup_count = 0
    for c in customers:
        if c['cid'] in seen:
            dup_count += 1
            continue
        seen.add(c['cid'])
        unique.append(c)
    if dup_count:
        print(f'发现 {dup_count} 条重复cid，已去重，保留 {len(unique)} 条')
    return unique


# ==================== 机会分计算 ====================
def calc_opportunity(c):
    opp = 0
    ind = c['industry']
    biz = c['biz_type']
    sn = c['store_count'] + c['sub_accounts']
    pa = c['pay_amount']
    login_days = c['login_days']
    intention = c['intention']
    expiring = c['expiring_services']

    # 行业核心+批发
    if ind in CORE_INDUSTRIES and '批发' in biz:
        opp += 30
    # 活跃天数>100
    if login_days > 100:
        opp += 25
    # 规模>=3
    if sn >= 3:
        opp += 20
    # 服务即将到期(60天内)
    if expiring:
        opp += 15
    # 意向客户
    if intention == '意向':
        opp += 20

    return min(opp, 100)


# ==================== 6维评分 ====================
def score_customer(c):
    reasons = []
    days = c['days_since_visit']

    # D1 回访紧迫度
    if days is None:
        d1 = 3; reasons.append('D1=3(无回访)')
    elif days > 365:
        d1 = 5; reasons.append(f'D1=5({days}天·高危)')
    elif days > 180:
        d1 = 4; reasons.append(f'D1=4({days}天)')
    elif days > 90:
        d1 = 3; reasons.append(f'D1=3({days}天)')
    elif days > 30:
        d1 = 2; reasons.append(f'D1=2({days}天)')
    else:
        d1 = 1; reasons.append(f'D1=1({days}天)')

    # D2 行业
    ind = c['industry']
    d2 = get_industry_score(ind)
    if d2 == 5:
        reasons.append(f'D2=5(核心:{ind})')
    elif d2 == 4:
        reasons.append(f'D2=4(强匹配:{ind})')
    elif d2 == 3:
        reasons.append(f'D2=3(通用:{ind})')
    elif d2 == 1:
        reasons.append('D2=1(未填)')
    else:
        reasons.append(f'D2=2({ind})')

    # D3 业务
    ia = c['biz_type']
    if '批发' in ia and '零售' in ia:
        d3 = 5; reasons.append('D3=5(批零一体)')
    elif '批发' in ia:
        d3 = 3; reasons.append('D3=3(批发)')
    elif ia and ia != '未填':
        d3 = 2; reasons.append(f'D3=2({ia})')
    else:
        d3 = 1; reasons.append('D3=1(未填)')

    # D4 规模
    sn = c['store_count'] + c['sub_accounts']
    if sn >= 6:
        d4 = 5; reasons.append(f'D4=5({sn}单元)')
    elif sn >= 3:
        d4 = 4; reasons.append(f'D4=4({sn}单元)')
    elif sn >= 1:
        d4 = 2; reasons.append(f'D4=2({sn}单元)')
    else:
        d4 = 1; reasons.append('D4=1(无数据)')

    # D5 活跃度
    lr = c['active_rate']
    if lr >= 80:
        d5 = 5; reasons.append(f'D5=5(活跃{lr}%)')
    elif lr >= 50:
        d5 = 3; reasons.append(f'D5=3(活跃{lr}%)')
    elif lr >= 20:
        d5 = 2; reasons.append(f'D5=2(活跃{lr}%)')
    else:
        d5 = 1; reasons.append(f'D5=1(活跃{lr}%)')

    # D6 付费
    pa = c['pay_amount']
    if pa >= 3000:
        d6 = 5; reasons.append(f'D6=5(已付¥{pa:.0f})')
    elif pa >= 1000:
        d6 = 4; reasons.append(f'D6=4(已付¥{pa:.0f})')
    elif pa >= 1:
        d6 = 3; reasons.append(f'D6=3(已付¥{pa:.0f})')
    else:
        d6 = 1; reasons.append('D6=1(未付费)')

    score = d1 + d2 + d3 + d4 + d5 + d6

    # 机会分加成
    opp = c['opportunity_score']
    if opp >= 50:
        score += 3; reasons.append(f'+3(机会分{opp})')
    elif opp >= 30:
        score += 2; reasons.append(f'+2(机会分{opp})')
    elif opp >= 15:
        score += 1; reasons.append(f'+1(机会分{opp})')

    c['score'] = score
    c['d1'], c['d2'], c['d3'], c['d4'], c['d5'], c['d6'] = d1, d2, d3, d4, d5, d6
    c['sub_reason_raw'] = ' | '.join(reasons)
    return score


# ==================== 分级 ====================
def grade_customer(c):
    score = c['score']
    days = c['days_since_visit']
    ind = c['industry']
    ia = c['biz_type']
    sn = c['store_count'] + c['sub_accounts']
    pa = c['pay_amount']
    lr = c['active_rate']
    opp = c['opportunity_score']
    expiring = c['expiring_services']
    intention = c['intention']

    # 计算最近到期天数
    min_days = None
    for svc in c['services']:
        d = svc.get('days_to_expire')
        if d is not None and d >= 0:
            if min_days is None or d < min_days:
                min_days = d

    triggered_a = []
    if expiring:
        triggered_a.append(f'{len(expiring)}项服务即将到期')
    if score >= 24:
        triggered_a.append(f'总分≥24(分{score})')
    if pa >= 3000 and lr >= 50:
        triggered_a.append(f'高付费¥{pa:.0f}+高活跃{lr}%')
    if sn >= 6 and pa > 0:
        triggered_a.append(f'规模≥6({sn}单元)+已付费')
    if opp >= 60:
        triggered_a.append(f'机会分≥60(分{opp})')

    is_a = bool(triggered_a)

    if is_a:
        # A级细分
        if min_days is not None and min_days <= 7:
            c['sub_grade'] = 'S'
            c['sub_reason'] = f'服务{min_days}天内到期'
        elif pa >= 3000 and days is not None and days >= 180:
            c['sub_grade'] = 'S'
            c['sub_reason'] = f'高付费¥{pa:.0f}+{days}天未回访'
        elif intention == '意向':
            c['sub_grade'] = 'S'
            c['sub_reason'] = '意向客户'
        elif min_days is not None and min_days <= 30:
            c['sub_grade'] = 'A2'
            c['sub_reason'] = f'服务{min_days}天内到期'
        elif opp >= 60:
            c['sub_grade'] = 'A2'
            c['sub_reason'] = f'机会分{opp}'
        elif pa >= 3000 and lr >= 50:
            c['sub_grade'] = 'A2'
            c['sub_reason'] = f'高付费¥{pa:.0f}+活跃{lr}%'
        else:
            c['sub_grade'] = 'A3'
            c['sub_reason'] = '常规A级'
        return

    # B级
    triggered_b = []
    if score >= 18:
        triggered_b.append(f'总分{score}')
    if pa >= 1000 and lr >= 20:
        triggered_b.append(f'中付费¥{pa:.0f}+活跃{lr}%')
    if sn >= 3:
        triggered_b.append(f'多单元({sn})')
    if opp >= 30:
        triggered_b.append(f'机会分{opp}')

    if triggered_b:
        c['sub_grade'] = 'B'
        c['sub_reason'] = '、'.join(triggered_b)
    else:
        c['sub_grade'] = 'C'
        c['sub_reason'] = '常规维护'


# ==================== 话术与痛点生成 ====================
def _parse_contact(contact):
    if not contact:
        return None
    s = str(contact).strip()
    if not s or s.isdigit():
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
            return inner
        return None
    if s.startswith('店员') or s.startswith('管理员') or s.startswith('店长') or s.startswith('老板'):
        return None
    if s.lower().startswith('staff'):
        return None
    return s


def _call_name(c):
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


def generate_painpoints(c):
    insights = []
    pa = c['pay_amount']
    lr = c['active_rate']
    login_days = c['login_days']
    ind = c['industry']
    biz = c['biz_type']
    sn = c['store_count'] + c['sub_accounts']
    expiring = c['expiring_services']
    days = c['days_since_visit']

    if expiring:
        insights.append(f'【到期紧迫】{"、".join(expiring[:3])}即将到期，不及时续费影响日常经营')
    if pa >= 3000 and days is not None and days >= 180:
        insights.append(f'【高价值流失风险】累计付费¥{pa:.0f}但{days}天未回访，客户可能被竞品切入')
    if lr < 20 and pa > 0:
        insights.append(f'【活跃度低】活跃率{lr}%，付费客户使用频率低，存在退费风险')
    if lr == 0 and pa > 0:
        insights.append('【完全流失】活跃率0%，付费客户已停用，需立即挽回')

    ind_pains = INDUSTRY_PAINPOINTS.get(ind, [])
    if ind_pains and ind != '未填':
        insights.append(f'【{ind}行业痛点】{"；".join(ind_pains[:2])}')

    if sn >= 3:
        insights.append(f'【多店管理复杂】{sn}个管理单元需统一管理库存和调拨，手工对账易出错')

    if '批发' in biz and '零售' in biz:
        insights.append('【批零一体复杂】同时做批发零售，两套价格体系和客户管理混乱')
    elif '批发' in biz:
        insights.append('【批发订单管理】客户多订单量大，手工开单易漏单错单')
    elif '零售' in biz:
        insights.append('【零售会员薄弱】会员管理单一，营销活动工具少，复购率低')

    if days is None:
        insights.append('【从未回访】缺乏服务关系建立')
    elif days > 365:
        insights.append(f'【超长期未回访】{days}天未回访，客户可能已遗忘服务关系')

    if not insights:
        insights.append('【常规维护】客户状态正常，保持定期触达')

    return '\n'.join(insights)


def generate_script(c):
    pa = c['pay_amount']
    days = c['days_since_visit']
    lr = c['active_rate']
    login_days = c['login_days']
    expiring = c['expiring_services']
    intention = c['intention']
    ind = c['industry']
    biz = c['biz_type']
    call = _call_name(c)

    # 开场白
    if expiring:
        svc_str = '、'.join(expiring[:2])
        opening = f'{call}，您{svc_str}快到期了，我提前说一声，现在续费老客户有优惠，顺便帮您看下要不要升级套餐。'
        opp_tag = '续费'
    elif pa >= 3000 and days is not None and days >= 180:
        opening = f'{call}，好久没联系了。您是我们{pa:.0f}元的老客户，最近半年没跟进到您，今天专门来了解下用得怎么样，有没有遇到问题。'
        opp_tag = '挽回'
    elif login_days > 100 and lr >= 50:
        opening = f'{call}，看您系统用得挺频繁的，{login_days}天了。今天聊几句，看您这边有没有什么需要升级或加功能的。'
        opp_tag = '增值'
    elif lr < 20 and pa > 0:
        opening = f'{call}，看您最近系统用得少，活跃率才{lr}%。是遇到什么问题了还是功能不够用？我帮您看下。'
        opp_tag = '激活'
    elif lr == 0:
        opening = f'{call}，看到您有一阵没用系统了。是换其他软件了还是暂时没开店？不管怎样有问题都可以找我。'
        opp_tag = '唤醒'
    elif days is None:
        opening = f'{call}，之前一直没跟您联系上，今天专门打个电话。您现在生意怎么样？系统用着还顺手吗？'
        opp_tag = '首触'
    elif days > 365:
        opening = f'{call}，快一年没联系了。今天回访一下，您生意怎么样？系统还在用吗？'
        opp_tag = '回访'
    else:
        opening = f'{call}，今天打电话问候一下，您系统用得还顺利吗？有什么问题都可以跟我说。'
        opp_tag = '维护'

    # 产品推荐
    have = set(s['name'] for s in c['services'])
    ind_recs = INDUSTRY_RECOMMEND.get(ind, [])
    gaps = []
    for prod in ind_recs:
        if prod not in have and prod in QINSILK_PRODUCTS:
            gaps.append((prod, QINSILK_PRODUCTS[prod]))

    if not gaps:
        if pa >= 3000:
            recommend = '您是高价值老客户，建议关注AI绘图和专属微信会员卡，能帮您把会员运营和商品图效率做上来。'
        elif pa >= 1000:
            recommend = '您目前用得不错，如果想提升效率可以考虑专属微信会员卡或直播卖货，把会员复购和线上渠道做起来。'
        elif pa > 0:
            recommend = '您现在的版本比较基础，如果生意做大了可以考虑升级到进销存专业版，功能更全。'
        else:
            recommend = '您还没付费，建议先试用进销存会员版，上手管理进销存。'
    else:
        main_prod, main_val = gaps[0]
        recommend = f'{main_prod}——{main_val}。'

    # 促单
    if intention == '意向':
        close = '您这边有意向，我今天专门跟您详细聊。您目前最想解决什么问题？我帮您匹配方案，合适的话直接演示给您看。'
    elif c['opportunity_score'] >= 60:
        close = '我看您这边需求挺明确的，要不我给您做个方案，明天发您看看？合适的话这周就能帮您开通。'
    elif c['opportunity_score'] >= 30:
        close = '您这边可以考虑下，我先把资料发您，有什么问题随时找我。'
    else:
        close = '您先了解着，有什么问题随时联系我，我这边随时帮您看。'

    script = f'{opening} {recommend} {close}'

    action_map = {
        '续费': '24h内致电·确认到期服务+续费方案+升级建议',
        '挽回': '24h内致电·高价值客户关怀+流失原因排查',
        '唤醒': '24h内致电·停用原因排查+重新激活引导',
        '增值': '48h内致电·使用情况了解+增值产品推荐',
        '激活': '48h内致电·使用障碍排查+功能指导',
        '首触': '本周内致电·建立服务关系+需求挖掘',
        '回访': '本周内致电·长期未回访关怀+需求更新',
        '维护': '月度触达·客情维护+新功能介绍',
    }
    action = action_map.get(opp_tag, '月度触达·客情维护')

    return script, opp_tag, action


# ==================== 建库 ====================
def init_db():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f'已删除旧数据库: {DB_PATH}')

    conn = sqlite3.connect(DB_PATH)
    conn.execute('''CREATE TABLE customers (
        cid TEXT PRIMARY KEY,
        name TEXT, contact TEXT, phone TEXT,
        industry TEXT, biz_type TEXT,
        store_count INTEGER, sub_accounts INTEGER,
        active_rate REAL, login_days INTEGER, total_days INTEGER,
        pay_amount REAL, hard_qty INTEGER,
        last_visit_record TEXT, visit_time INTEGER,
        intention TEXT, sys_type INTEGER, reg_date TEXT,
        expiring_services TEXT,
        services TEXT,
        score INTEGER, sub_grade TEXT, sub_reason TEXT,
        opportunity_score INTEGER, opportunity_type TEXT,
        d1 INTEGER, d2 INTEGER, d3 INTEGER, d4 INTEGER, d5 INTEGER, d6 INTEGER,
        painpoints TEXT, script TEXT, action TEXT,
        days_since_visit INTEGER,
        updated_at TIMESTAMP
    )''')

    conn.execute('''CREATE TABLE visit_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cid TEXT,
        bd_name TEXT,
        result TEXT,
        note TEXT,
        next_date DATE,
        deal TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (cid) REFERENCES customers(cid)
    )''')

    conn.execute('CREATE INDEX idx_customers_sub_grade ON customers(sub_grade)')
    conn.execute('CREATE INDEX idx_customers_industry ON customers(industry)')
    conn.execute('CREATE INDEX idx_visits_cid ON visit_records(cid)')

    print('表结构已创建')

    customers = load_customers()
    print(f'加载 {len(customers)} 条客户数据')

    for c in customers:
        c['opportunity_score'] = calc_opportunity(c)
        score_customer(c)
        grade_customer(c)
        c['painpoints'] = generate_painpoints(c)
        c['script'], c['opportunity_type'], c['action'] = generate_script(c)

    # 写入
    rows = []
    for c in customers:
        rows.append((
            c['cid'], c['name'], c['contact'], c['phone'],
            c['industry'], c['biz_type'],
            c['store_count'], c['sub_accounts'],
            c['active_rate'], c['login_days'], c['total_days'],
            c['pay_amount'], c['hard_qty'],
            c['last_visit_record'], c['visit_time'],
            c['intention'], c['sys_type'], c['reg_date'],
            json.dumps(c['expiring_services'], ensure_ascii=False),
            json.dumps(c['services'], ensure_ascii=False),
            c['score'], c['sub_grade'], c['sub_reason'],
            c['opportunity_score'], c['opportunity_type'],
            c['d1'], c['d2'], c['d3'], c['d4'], c['d5'], c['d6'],
            c['painpoints'], c['script'], c['action'],
            c['days_since_visit'],
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        ))

    conn.executemany('''INSERT INTO customers (
        cid,name,contact,phone,industry,biz_type,store_count,sub_accounts,
        active_rate,login_days,total_days,pay_amount,hard_qty,
        last_visit_record,visit_time,intention,sys_type,reg_date,
        expiring_services,services,score,sub_grade,sub_reason,
        opportunity_score,opportunity_type,d1,d2,d3,d4,d5,d6,
        painpoints,script,action,days_since_visit,updated_at
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', rows)
    conn.commit()

    # 统计
    sub_counter = Counter(c['sub_grade'] for c in customers)
    print('\n=== 分级统计 ===')
    for g in ['S', 'A2', 'A3', 'B', 'C']:
        cnt = sub_counter.get(g, 0)
        print(f'  {g}: {cnt}条 ({cnt/len(customers)*100:.1f}%)')

    total_pay = sum(c['pay_amount'] for c in customers)
    paid_count = sum(1 for c in customers if c['pay_amount'] > 0)
    expiring_count = sum(1 for c in customers if c['expiring_services'])
    print(f'\n总付费金额: ¥{total_pay:.0f}')
    print(f'已付费客户: {paid_count}条 ({paid_count/len(customers)*100:.1f}%)')
    print(f'60天内到期: {expiring_count}条')

    # 行业TOP10
    ind_counter = Counter(c['industry'] for c in customers)
    print('\n=== 行业TOP10 ===')
    for ind, cnt in ind_counter.most_common(10):
        print(f'  {ind}: {cnt}条')

    # 业务类型分布
    biz_counter = Counter(c['biz_type'] for c in customers)
    print('\n=== 业务类型分布 ===')
    for biz, cnt in biz_counter.most_common(10):
        print(f'  {biz}: {cnt}条')

    conn.close()
    print(f'\n数据库初始化完成: {DB_PATH}')


if __name__ == '__main__':
    init_db()
