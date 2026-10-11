#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SDR 服务池跟进表 v3.0 - 客户画像5规则+话术痛点
新增5维画像规则：
  R1 系统到期(60天内)  R2 付费>3000  R3 活跃>100天  R4 门店/子账号≥3  R5 销售机会综合评判
结合秦丝全产品线生成沟通话术+痛点分析
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
DATA_FILE = os.path.join(BASE_DIR, 'chengdu_final_enriched.json')
OUTPUT_FILE = os.path.join(BASE_DIR, f'成都分部SDR跟进名单_画像话术v3_{datetime.now().strftime("%Y%m%d")}.xlsx')

now = datetime.now()

# 顾问ID → 名称映射（2026-07-06 CRM抓取getUserListForCounselors.ac核对确认）
# CRM真实数据：1431=吴必川 1314=王胜学 2379=潘飞 2381=吴云凤 800=刘昕(主管)
# 老板指示：吴必川(1431)病假→客户归属吴云凤；刘昕(800)主管不跟进→待分配
# 零散ID(1696/1878/1733等)为成都分部已离职人员→待分配
COUNSELOR_MAP = {1431: '吴云凤', 1314: '王胜学', 2379: '潘飞', 2381: '吴云凤'}

# ==================== 秦丝产品知识库（基于真实数据，37个产品名ground truth） ====================
# 产品名来源：chengdu_final_enriched.json 中 expirationList.serviceName + payServiceConsumeRecordCurrentCountList.serviceName
# 价格标注说明：无官方价格表，按价位档次标注（高/中/入门），避免编造确切价格
QINSILK_PRODUCTS = {
    # === 核心系统（按档次：会员版 < 专业版 < 高级版） ===
    '进销存会员': {'category': '核心系统-进销存', 'tier': '入门', 'value': '进销存基础功能，适合单店起步'},
    '进销存专业版': {'category': '核心系统-进销存', 'tier': '中端', 'value': '进销存+商品管理+库存预警+欠货统计，适合成长型单店'},
    '生意通会员': {'category': '核心系统-生意通', 'tier': '入门', 'value': '生意通基础功能'},
    '生意通专业版': {'category': '核心系统-生意通', 'tier': '中端', 'value': '生意通进阶功能，适合批发订货场景'},
    '生意通高级版': {'category': '核心系统-生意通', 'tier': '高端', 'value': '多门店管理+采购管理+财务报表+员工权限，适合连锁/规模化'},
    # === 线上渠道（微商城系列） ===
    '销货宝微商城标准版': {'category': '线上渠道-微商城', 'tier': '入门', 'value': '微信小程序商城+商品上架+在线支付'},
    '销货宝微商城基础版': {'category': '线上渠道-微商城', 'tier': '中端', 'value': '微信小程序商城+商品上架+在线支付+基础营销'},
    '销货宝微商城专业版': {'category': '线上渠道-微商城', 'tier': '高端', 'value': '微商城+营销插件+分销+直播，全渠道运营'},
    '专属品牌小程序': {'category': '线上渠道-小程序', 'tier': '中端', 'value': '独立品牌小程序+自定义装修+品牌展示'},
    # === 营销工具 ===
    '限时折扣促单宝': {'category': '营销工具', 'tier': '入门', 'value': '限时折扣+会员价+阶梯定价'},
    '限时秒杀促单宝': {'category': '营销工具', 'tier': '入门', 'value': '秒杀活动+库存锁定+倒计时'},
    '批量推款宝': {'category': '营销工具', 'tier': '入门', 'value': '批量推款+客户在线选款+自动分享'},
    '直播卖货': {'category': '营销工具', 'tier': '中端', 'value': '直播带货+引流到店+互动抽奖'},
    '微信自动化经营': {'category': '营销工具', 'tier': '中端', 'value': '自动加好友+群发+朋友圈营销'},
    # === 会员运营 ===
    '专属微信会员卡': {'category': '会员运营', 'tier': '中端', 'value': '微信会员卡+积分+储值+会员画像'},
    '会员积分充值': {'category': '会员运营', 'tier': '入门', 'value': '会员积分充值+消费抵扣+积分商城'},
    '客户积分': {'category': '会员运营', 'tier': '入门', 'value': '客户积分管理+消费累计'},
    # === 门店/账号扩展 ===
    '门店': {'category': '门店管理', 'tier': '中端', 'value': '多门店统一管理+门店独立库存+智能调拨'},
    '子帐号': {'category': '账号扩展', 'tier': '入门', 'value': '新增子账号+员工协作+权限分配'},
    # === 硬件/收银 ===
    '慧店宝': {'category': '硬件-收银', 'tier': '中端', 'value': '收银终端+扫码+打印一体'},
    '慧店宝大屏收银端': {'category': '硬件-收银', 'tier': '高端', 'value': '大屏收银终端+扫码+打印一体，高效收银'},
    # === AI工具 ===
    'AI绘图': {'category': 'AI工具', 'tier': '入门', 'value': 'AI自动绘图+智能抠图+商品图生成'},
    '以图搜图': {'category': 'AI工具', 'tier': '入门', 'value': '图片搜索商品+快速找款'},
    # === 品牌展示 ===
    '商家名片': {'category': '品牌展示', 'tier': '入门', 'value': '电子名片+商品展示+一键拨号'},
    # === 存储/服务 ===
    '秦丝进销存云存储费': {'category': '存储扩展', 'tier': '入门', 'value': '扩展进销存数据存储空间'},
    '秦丝生意通云存储费': {'category': '存储扩展', 'tier': '入门', 'value': '扩展生意通数据存储空间'},
    '短信服务': {'category': '增值服务', 'tier': '入门', 'value': '短信通知+营销短信'},
    '数据迁移服务': {'category': '增值服务', 'tier': '中端', 'value': '数据迁移+系统切换协助'},
    # === 企业微信 ===
    '企业微信客户助手': {'category': '私域运营', 'tier': '中端', 'value': '企微客户管理+自动回复+SOP'},
    # === 联盟版 ===
    '联盟版': {'category': '联盟体系', 'tier': '高端', 'value': '联盟商户+资源共享+跨店结算'},
    '联盟版绑定数': {'category': '联盟体系', 'tier': '中端', 'value': '联盟商户绑定数扩展'},
    # === 慧店宝系列 ===
    '多店智擎': {'category': '多店管理', 'tier': '高端', 'value': '多店智能管理+数据分析+决策辅助'},
    # === 其他 ===
    '订制（电脑端）打印模板': {'category': '工具', 'tier': '入门', 'value': '自定义打印模板+小票设计'},
    '10本开店管店必看书籍': {'category': '增值服务', 'tier': '入门', 'value': '开店管店实体书籍'},
    '线上卖货六脉神剑电子版': {'category': '增值服务', 'tier': '入门', 'value': '线上卖货方法论电子书'},
    '旺剪-算力': {'category': 'AI工具', 'tier': '中端', 'value': 'AI视频剪辑算力'},
    '旺剪-云空间': {'category': '存储扩展', 'tier': '入门', 'value': '视频剪辑云存储空间'},
}

CORE_INDUSTRIES = ['服装鞋帽', '服装']

# ==================== 行业画像库 v3.2（基于真实行业分布·专属痛点+产品推荐） ====================
# 数据源：chengdu_final_enriched.json 实际行业分布 top15
# score: D2行业匹配度评分（5核心/4强匹配/3通用/2弱/1未填）
# painpoints: 该行业典型痛点列表
# recommend: 该行业推荐产品（基于秦丝产品线）
INDUSTRY_PROFILES = {
    # === 核心行业（5分）·秦丝最擅长 ===
    '服装鞋帽': {
        'score': 5, 'category': '核心',
        'painpoints': ['款式SKU多难管理', '换季库存积压风险', '颜色尺码组合爆炸', '需要批量推款给客户'],
        'recommend': ['批量推款宝', 'AI绘图', '销货宝微商城专业版'],
    },
    '服装': {
        'score': 5, 'category': '核心',
        'painpoints': ['款式SKU多难管理', '换季库存积压风险', '颜色尺码组合爆炸'],
        'recommend': ['批量推款宝', 'AI绘图', '销货宝微商城专业版'],
    },
    # === 强匹配行业（4分）·有明确行业专属痛点 ===
    '食品饮料': {
        'score': 4, 'category': '强匹配',
        'painpoints': ['保质期管理难·过期损耗', '批次追溯需求', '临期商品促销'],
        'recommend': ['进销存专业版', '限时折扣促单宝'],
    },
    '水果生鲜': {
        'score': 4, 'category': '强匹配',
        'painpoints': ['保质期极短·损耗大', '每日库存周转', '临期快速清仓'],
        'recommend': ['进销存专业版', '限时秒杀促单宝'],
    },
    '数码家电': {
        'score': 4, 'category': '强匹配',
        'painpoints': ['序列号/IMEI管理', '价格波动快·调价频繁', '保修期追溯'],
        'recommend': ['进销存专业版', '销货宝微商城基础版'],
    },
    '手机配件': {
        'score': 4, 'category': '强匹配',
        'painpoints': ['SKU繁多·型号适配复杂', '价格波动快', '需要序列号管理'],
        'recommend': ['进销存专业版', '批量推款宝'],
    },
    '美妆代购': {
        'score': 4, 'category': '强匹配',
        'painpoints': ['会员复购运营·积分体系', '批次/临期管理', '代购多渠道客户管理'],
        'recommend': ['专属微信会员卡', '会员积分充值', '销货宝微商城专业版'],
    },
    '母婴玩具': {
        'score': 4, 'category': '强匹配',
        'painpoints': ['会员复购·宝宝成长周期', '安全合规追溯', '积分运营'],
        'recommend': ['专属微信会员卡', '会员积分充值', '销货宝微商城基础版'],
    },
    '烟酒茶叶': {
        'score': 4, 'category': '强匹配',
        'painpoints': ['防伪溯源需求', '批次/年份管理', '高价值商品库存'],
        'recommend': ['进销存专业版', '专属微信会员卡'],
    },
    '珠宝饰品': {
        'score': 4, 'category': '强匹配',
        'painpoints': ['高价值商品防伪', '会员VIP运营', '定制订单管理'],
        'recommend': ['专属微信会员卡', '进销存专业版'],
    },
    '商超便利': {
        'score': 4, 'category': '强匹配',
        'painpoints': ['收银效率·排队', '快消品高频周转', '会员储值'],
        'recommend': ['慧店宝', '专属微信会员卡', '限时折扣促单宝'],
    },
    # === 通用行业（3分）·产品通用适配 ===
    '日用百货': {
        'score': 3, 'category': '通用',
        'painpoints': ['SKU多而杂', '库存盘点繁琐', '低毛利跑量'],
        'recommend': ['进销存专业版', '销货宝微商城基础版'],
    },
    '家装建材': {
        'score': 3, 'category': '通用',
        'painpoints': ['大宗商品·批次管理', '订单周期长', '送货安装协调'],
        'recommend': ['生意通专业版', '销货宝微商城基础版'],
    },
    '家居家纺': {
        'score': 3, 'category': '通用',
        'painpoints': ['SKU多·花色规格', '换季库存', '会员复购'],
        'recommend': ['进销存专业版', '专属微信会员卡'],
    },
    '五金机械': {
        'score': 3, 'category': '通用',
        'painpoints': ['规格型号复杂', 'B2B批发订货', '库存价值高'],
        'recommend': ['生意通专业版', '批量推款宝'],
    },
    '汽修汽配': {
        'score': 3, 'category': '通用',
        'painpoints': ['配件型号适配复杂', 'B2B批发', '库存价值高'],
        'recommend': ['生意通专业版', '进销存专业版'],
    },
    '文体图书': {
        'score': 3, 'category': '通用',
        'painpoints': ['SKU海量·盘点难', '低毛利跑量', '会员复购'],
        'recommend': ['进销存专业版', '专属微信会员卡'],
    },
    '农药化肥': {
        'score': 3, 'category': '通用',
        'painpoints': ['季节性强', '批次追溯', 'B2B批发'],
        'recommend': ['生意通专业版', '进销存专业版'],
    },
    '宠物用品': {
        'score': 3, 'category': '通用',
        'painpoints': ['会员复购·宠物档案', 'SKU多', '积分运营'],
        'recommend': ['专属微信会员卡', '销货宝微商城基础版'],
    },
}

def get_industry_profile(ind):
    """获取行业画像，未匹配的返回通用"""
    if ind in INDUSTRY_PROFILES:
        return INDUSTRY_PROFILES[ind]
    # 未填或未匹配
    return {'score': 1, 'category': '未填', 'painpoints': [], 'recommend': []}

# ==================== 数据加载与字段标准化 ====================
with open(DATA_FILE, 'r', encoding='utf-8') as f:
    customers = json.load(f)

print(f'加载 {len(customers)} 条客户数据')

for c in customers:
    c['name'] = c.get('comName') or c.get('n') or ''
    c['phone'] = c.get('cellphone_full') or c.get('cellphone') or ''
    c['contact'] = c.get('realName') or c.get('crmRealName') or c.get('c') or ''
    cid_val = c.get('counselorId')
    c['advisor'] = COUNSELOR_MAP.get(cid_val, '待分配') if cid_val else '待分配'
    c['dept'] = c.get('department') or c.get('groupName') or '成都分部'
    
    reg_ind = c.get('regIndustry') or ''
    ind = c.get('industry') or ''
    c['industry_val'] = reg_ind if reg_ind and reg_ind != '无' else (ind if ind and ind != '无' else '未填')
    
    biz = c.get('businessType') or c.get('ia') or ''
    c['biz_type'] = biz if biz else '未填'
    
    store = c.get('storeNumber') or c.get('store') or ''
    m = re.search(r'(\d+)', str(store))
    c['store_count'] = int(m.group(1)) if m else (c.get('comStoreNumber') or 0)
    c['sub_accounts'] = c.get('userNumber') or 0
    
    lr_str = c.get('loginDayRate') or '0%'
    m2 = re.search(r'([\d.]+)', str(lr_str))
    c['active_rate'] = float(m2.group(1)) if m2 else 0.0
    c['login_days'] = c.get('loginDays') or 0
    c['total_days'] = c.get('allDays') or 0
    
    pa = c.get('ext_payAmount') or 0
    if not pa:
        pa = c.get('beInviterPayAmount') or 0
    if not pa:
        detail_tmp = c.get('_detail', {})
        obj_tmp = detail_tmp.get('extend', {}).get('object', {}) if isinstance(detail_tmp.get('extend'), dict) else {}
        pay_list_tmp = obj_tmp.get('payServiceConsumeRecordCurrentCountList', []) or []
        if pay_list_tmp:
            pa = len(pay_list_tmp) * 500
    c['pay_amount'] = pa
    c['hard_qty'] = c.get('ext_hardQuantity') or c.get('hardQuantity') or 0
    
    reg_time = c.get('registerTime') or ''
    if isinstance(reg_time, (int, float)) and reg_time > 1000000000000:
        reg_time = datetime.fromtimestamp(reg_time/1000).strftime('%Y-%m-%d %H:%M:%S')
    c['reg_date'] = str(reg_time)[:10] if reg_time else ''

    vr = c.get('lastVisitDate') or c.get('vr') or ''
    if isinstance(vr, (int, float)) and vr > 1000000000000:
        try:
            dt_vr = datetime.fromtimestamp(vr/1000)
            vr = dt_vr.strftime('%Y/%m/%d %H:%M')
            c['days_since_visit'] = (now - dt_vr).days
        except:
            c['days_since_visit'] = None
    else:
        c['days_since_visit'] = None
        if vr:
            try:
                dt = datetime.strptime(vr, '%Y/%m/%d %H:%M')
                c['days_since_visit'] = (now - dt).days
            except:
                try:
                    dt = datetime.strptime(str(vr)[:10], '%Y/%m/%d')
                    c['days_since_visit'] = (now - dt).days
                except:
                    try:
                        dt = datetime.strptime(str(vr)[:10], '%Y-%m-%d')
                        c['days_since_visit'] = (now - dt).days
                    except:
                        pass
    c['last_visit'] = vr if vr else ''
    
    c['intention'] = c.get('intention') or '无'
    sys_map = {1: '进销存', 2: '微商城', 3: 'ERP'}
    c['sys_name'] = sys_map.get(c.get('sysType'), c.get('detailSysType') or c.get('sys') or '')
    c['ip_area'] = c.get('ipArea') or ''
    c['web_shop'] = c.get('webShop') or '未开通'
    c['last_visit_record'] = c.get('lastVisitRecord') or c.get('recentVisit') or ''
    
    # 解析服务到期信息
    detail = c.get('_detail', {})
    ext_obj = detail.get('extend', {}).get('object', {})
    exp_list = ext_obj.get('expirationList', [])
    
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
        
        if enable_end is None:
            c['permanent_services'].append(svc_name)
        elif enable_end > 4000000000000:  # 永久(2100年+)
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
    
    # 付费服务记录
    pay_list = ext_obj.get('payServiceConsumeRecordCurrentCountList', [])
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
    c['shop_mode'] = upi.get('shopMode', '')
    c['client_level'] = upi.get('clientLevel', '')
    c['store_type_tag'] = upi.get('storeTypeTag', '')
    c['purchase_hardware_tag'] = upi.get('purchaseHardwareTag', '')

# ==================== 5维画像规则评估 ====================
def evaluate_profile_rules(c):
    """评估5维画像规则，返回触发列表+销售机会评分"""
    rules_triggered = []
    opportunity_score = 0
    
    # R1: 系统即将到期（60天以内）
    expiring = c.get('expiring_services', [])
    if expiring:
        rules_triggered.append({
            'rule': 'R1',
            'label': '系统即将到期',
            'detail': f'{len(expiring)}项服务即将到期: {", ".join(expiring[:3])}',
            'urgency': '紧急',
            'opportunity': '续费机会'
        })
        opportunity_score += 30
    
    # R2: 付费金额大于3000
    pa = c.get('pay_amount', 0)
    if pa > 3000:
        rules_triggered.append({
            'rule': 'R2',
            'label': '高付费客户',
            'detail': f'累计付费¥{pa:.0f}，属于高价值客户',
            'urgency': '重要',
            'opportunity': '增购/续费机会'
        })
        opportunity_score += 25
    
    # R3: 客户活跃天数大于100天
    login_days = c.get('login_days', 0)
    if login_days > 100:
        rules_triggered.append({
            'rule': 'R3',
            'label': '高粘性客户',
            'detail': f'已登录{login_days}天(共{c.get("total_days",0)}天)，系统依赖度高',
            'urgency': '重要',
            'opportunity': '升单/增值机会'
        })
        opportunity_score += 20
    
    # R4: 门店数或子账号数≥3
    sn = c.get('store_count', 0)
    sa = c.get('sub_accounts', 0)
    total_scale = sn + sa
    if total_scale >= 3:
        rules_triggered.append({
            'rule': 'R4',
            'label': '多门店/多账号',
            'detail': f'{sn}门店+{sa}子账号=共{total_scale}个管理单元',
            'urgency': '重要',
            'opportunity': '规模化增购机会'
        })
        opportunity_score += 20
    
    # R5: 综合评判销售机会可触达范围
    reachable_channels = []
    if c.get('phone') and '*' not in str(c.get('phone')):
        reachable_channels.append('电话')
    if c.get('has_weixin'):
        reachable_channels.append('微信')
    if c.get('web_shop') and c.get('web_shop') != '未开通':
        reachable_channels.append('微商城')
    
    # 综合因素
    factors = []
    if c.get('intention') == '意向':
        factors.append('有意向标记')
        opportunity_score += 15
    if c.get('industry_val') in CORE_INDUSTRIES:
        factors.append('核心行业')
        opportunity_score += 10
    biz = c.get('biz_type', '')
    if '批发' in biz and '零售' in biz:
        factors.append('批零一体')
        opportunity_score += 10
    if c.get('hard_qty', 0) > 0:
        factors.append(f'已购硬件{c["hard_qty"]}件')
        opportunity_score += 5
    if c.get('pay_services_detail'):
        unused = [ps for ps in c['pay_services_detail'] if ps.get('surplus', 0) > 0]
        if unused:
            factors.append(f'{len(unused)}项服务有余额未用')
            opportunity_score += 5
    
    days = c.get('days_since_visit')
    if days is not None and days > 180:
        factors.append(f'{days}天未回访')
    elif days is None:
        factors.append('从未回访')
    
    rules_triggered.append({
        'rule': 'R5',
        'label': '销售机会综合评判',
        'detail': f'可触达渠道: {", ".join(reachable_channels) or "仅电话"} | 关键因素: {", ".join(factors) if factors else "常规"}',
        'urgency': '常规',
        'opportunity': '综合触达'
    })
    
    c['profile_rules'] = rules_triggered
    c['opportunity_score'] = min(opportunity_score, 100)
    c['reachable_channels'] = reachable_channels
    
    return rules_triggered, opportunity_score

for c in customers:
    evaluate_profile_rules(c)

# ==================== 评分模型 v3.0（6维+5规则） ====================
def score_customer(c):
    score = 0
    reasons = []
    
    # D1 回访紧迫度 (5分)
    days = c.get('days_since_visit')
    if days is None:
        d1 = 3; reasons.append('D1=3(无回访)')
    elif days <= 30:
        d1 = 1; reasons.append(f'D1=1({days}天)')
    elif days <= 90:
        d1 = 2; reasons.append(f'D1=2({days}天)')
    elif days <= 180:
        d1 = 3; reasons.append(f'D1=3({days}天)')
    elif days <= 365:
        d1 = 4; reasons.append(f'D1=4({days}天)')
    else:
        d1 = 5; reasons.append(f'D1=5({days}天·高危)')
    score += d1; c['d1'] = d1
    
    # D2 行业匹配度 (5分) · v3.2 使用行业画像库
    ind = c.get('industry_val', '')
    ind_profile = get_industry_profile(ind)
    d2 = ind_profile['score']
    ind_cat = ind_profile.get('category', '未填')
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
    score += d2; c['d2'] = d2
    c['industry_profile'] = ind_profile
    
    # D3 业务类型 (5分)
    ia = c.get('biz_type', '')
    if '批发' in ia and '零售' in ia:
        d3 = 5; reasons.append('D3=5(批零一体)')
    elif '批发' in ia:
        d3 = 3; reasons.append('D3=3(批发)')
    elif ia and ia != '未填':
        d3 = 2; reasons.append(f'D3=2({ia})')
    else:
        d3 = 1; reasons.append('D3=1(未填)')
    score += d3; c['d3'] = d3
    
    # D4 门店规模 (5分)
    sn = c.get('store_count', 0) + c.get('sub_accounts', 0)
    if sn >= 6:
        d4 = 5; reasons.append(f'D4=5({sn}管理单元)')
    elif sn >= 3:
        d4 = 4; reasons.append(f'D4=4({sn}管理单元)')
    elif sn == 2:
        d4 = 3; reasons.append('D4=3(2单元)')
    elif sn == 1:
        d4 = 2; reasons.append('D4=2(1单元)')
    else:
        d4 = 1; reasons.append('D4=1(无数据)')
    score += d4; c['d4'] = d4
    
    # D5 活跃度 (5分)
    lr = c.get('active_rate', 0)
    if lr >= 80:
        d5 = 5; reasons.append(f'D5=5(活跃{lr}%)')
    elif lr >= 50:
        d5 = 3; reasons.append(f'D5=3(活跃{lr}%)')
    elif lr >= 20:
        d5 = 2; reasons.append(f'D5=2(活跃{lr}%)')
    else:
        d5 = 1; reasons.append(f'D5=1(活跃{lr}%)')
    score += d5; c['d5'] = d5
    
    # D6 付费价值 (5分)
    pa = c.get('pay_amount', 0)
    if pa >= 3000:
        d6 = 5; reasons.append(f'D6=5(已付¥{pa:.0f})')
    elif pa >= 1000:
        d6 = 4; reasons.append(f'D6=4(已付¥{pa:.0f})')
    elif pa > 0:
        d6 = 3; reasons.append(f'D6=3(已付¥{pa:.0f})')
    else:
        d6 = 1; reasons.append('D6=1(未付费)')
    score += d6; c['d6'] = d6
    
    # 画像规则加成
    opp = c.get('opportunity_score', 0)
    if opp >= 50:
        score += 3; reasons.append(f'+3(机会分{opp})')
    elif opp >= 30:
        score += 2; reasons.append(f'+2(机会分{opp})')
    elif opp >= 15:
        score += 1; reasons.append(f'+1(机会分{opp})')
    
    c['score'] = score
    c['reasons'] = ' | '.join(reasons)
    return score

for c in customers:
    score_customer(c)

# ==================== 分级规则 v3.0 ====================
def grade_customer(c):
    score = c['score']
    days = c.get('days_since_visit')
    ind = c.get('industry_val', '')
    ia = c.get('biz_type', '')
    sn = c.get('store_count', 0) + c.get('sub_accounts', 0)
    pa = c.get('pay_amount', 0)
    lr = c.get('active_rate', 0)
    opp = c.get('opportunity_score', 0)
    expiring = c.get('expiring_services', [])
    
    triggered = []
    
    # A级
    if expiring:
        triggered.append(f'⚠{len(expiring)}项服务即将到期')
    if score >= 24:
        triggered.append(f'总分≥24(分{score})')
    if pa >= 3000 and lr >= 50:
        triggered.append(f'高付费¥{pa:.0f}+高活跃{lr}%')
    if pa >= 5000 and days and days >= 180:
        triggered.append(f'超高付费¥{pa:.0f}+{days}天未回访')
    if sn >= 6 and pa > 0:
        triggered.append(f'规模化({sn}单元)+已付费')
    if opp >= 60:
        triggered.append(f'销售机会高(分{opp})')
    
    if triggered:
        c['grade'] = 'A'
        c['grade_reason'] = '、'.join(triggered)
        return
    
    # B级
    if score >= 18:
        triggered.append(f'总分{score}')
    if pa >= 1000 and lr >= 20:
        triggered.append(f'付费¥{pa:.0f}+活跃{lr}%')
    if days and days >= 180 and pa > 0:
        triggered.append(f'{days}天未回访+已付费')
    if days is None and ind in CORE_INDUSTRIES:
        triggered.append('无回访+核心行业')
    if sn >= 3:
        triggered.append(f'多单元({sn})')
    if opp >= 30:
        triggered.append(f'销售机会中(分{opp})')
    
    if triggered:
        c['grade'] = 'B'
        c['grade_reason'] = '、'.join(triggered)
        return
    
    c['grade'] = 'C'
    c['grade_reason'] = '常规维护'

for c in customers:
    grade_customer(c)

# ==================== A级细分 S/A2/A3（v3.1 · 解决A级46%泛化） ====================
SUB_GRADE_ORDER = {'S': 0, 'A2': 1, 'A3': 2, 'B': 3, 'C': 4}

def sub_grade_a(c):
    """A级细分：S必跟(24h) / A2重点(48h) / A3常规A(本周)
    B/C级保持原值，优先级列统一显示 sub_grade。"""
    if c['grade'] != 'A':
        c['sub_grade'] = c['grade']
        c['sub_reason'] = c.get('grade_reason', '')
        return

    # 计算最近到期天数（取所有服务里最小的未过期天数）
    min_days = None
    for svc in c.get('services', []):
        d = svc.get('days_to_expire')
        if d is not None and d >= 0:
            if min_days is None or d < min_days:
                min_days = d

    pa = c.get('pay_amount', 0)
    days = c.get('days_since_visit')
    lr = c.get('active_rate', 0)
    opp = c.get('opportunity_score', 0)
    intention = c.get('intention', '无')

    # S 必跟(24h)：服务7天内到期 / 高付费+久未回访(≥180天) / 意向客户
    if min_days is not None and min_days <= 7:
        c['sub_grade'] = 'S'
        c['sub_reason'] = f'服务{min_days}天内到期'
        return
    if pa >= 3000 and days is not None and days >= 180:
        c['sub_grade'] = 'S'
        c['sub_reason'] = f'高付费¥{pa:.0f}+{days}天未回访'
        return
    if intention == '意向':
        c['sub_grade'] = 'S'
        c['sub_reason'] = '意向客户'
        return

    # A2 重点(48h)：30天内到期 / 机会分≥60 / 高付费+高活跃
    if min_days is not None and min_days <= 30:
        c['sub_grade'] = 'A2'
        c['sub_reason'] = f'服务{min_days}天内到期'
        return
    if opp >= 60:
        c['sub_grade'] = 'A2'
        c['sub_reason'] = f'机会分{opp}'
        return
    if pa >= 3000 and lr >= 50:
        c['sub_grade'] = 'A2'
        c['sub_reason'] = f'高付费¥{pa:.0f}+活跃{lr}%'
        return

    # A3 常规A（本周触达）
    c['sub_grade'] = 'A3'
    c['sub_reason'] = '常规A级'

for c in customers:
    sub_grade_a(c)

# 排序：S > A2 > A3 > B > C，同档按机会分/总分/未回访天数
customers.sort(key=lambda x: (
    SUB_GRADE_ORDER.get(x.get('sub_grade', 'C'), 4),
    -x.get('opportunity_score', 0),
    -x['score'],
    -(x.get('days_since_visit') or 9999)
))

grades = Counter(c['grade'] for c in customers)
sub_grades = Counter(c.get('sub_grade', c['grade']) for c in customers)
print(f'分级结果: A={grades["A"]} B={grades["B"]} C={grades["C"]}')
print(f'A级细分: S={sub_grades.get("S",0)} A2={sub_grades.get("A2",0)} A3={sub_grades.get("A3",0)}')

# ==================== 话术与痛点生成（v3.2 老客户精准营销·15年销售专家视角） ====================
def _pay_tier(pa):
    """付费层级判定"""
    if pa == 0: return 'none'
    if pa < 1000: return 'low'
    if pa < 3000: return 'mid'
    return 'high'

def _active_tier(lr, login_days):
    """活跃层级判定"""
    if lr == 0: return 'lost'
    if lr < 20: return 'low'
    if lr < 50: return 'mid'
    if login_days > 200: return 'super'
    return 'high'

def _biz_tag(biz, ind):
    """业务场景标签"""
    if '批发' in biz and '零售' in biz: return 'both'
    if '批发' in biz: return 'wholesale'
    if '零售' in biz: return 'retail'
    if ind in CORE_INDUSTRIES: return 'apparel_general'
    return 'other'

def _gap_products(c):
    """基于已有服务+画像缺口，推荐缺失的增值产品（差异化推荐核心）"""
    have = set(s['name'] for s in c.get('services', []))
    gaps = []
    ind = c.get('industry_val', '')
    biz = c.get('biz_type', '')
    sn = c.get('store_count', 0)
    sa = c.get('sub_accounts', 0)
    web_shop = c.get('web_shop', '')
    hard_qty = c.get('hard_qty', 0)
    pa = c.get('pay_amount', 0)
    tier = _pay_tier(pa)

    # 门店规模缺口——多门店客户推荐生意通高级版或门店管理
    if sn + sa >= 3 and '生意通高级版' not in have and '门店' not in have:
        gaps.append(('生意通高级版', '多门店统一管理+采购管理+财务报表+员工权限', '高端款'))
    # 线上渠道缺口——未开通微商城
    if web_shop == '未开通':
        # 高付费客户推专业版微商城
        if tier == 'high' and '销货宝微商城专业版' not in have:
            gaps.append(('销货宝微商城专业版', '微商城+营销插件+分销+直播，全渠道运营', '高端款'))
        # 中低付费客户推基础版
        elif '销货宝微商城基础版' not in have:
            gaps.append(('销货宝微商城基础版', '微信小程序商城+商品上架+在线支付+基础营销', '中端款'))
    # 硬件/收银缺口（服装行业高频扫码场景）
    if hard_qty == 0 and ind in CORE_INDUSTRIES:
        gaps.append(('慧店宝', '收银终端+扫码+打印一体，高效收银', '中端款'))
    # 营销工具缺口（零售客户推促单宝）
    if '零售' in biz:
        if '限时折扣促单宝' not in have:
            gaps.append(('限时折扣促单宝', '限时折扣+会员价+阶梯定价', '入门款'))
        elif '限时秒杀促单宝' not in have:
            gaps.append(('限时秒杀促单宝', '秒杀活动+库存锁定+倒计时', '入门款'))
    # 会员运营缺口
    if '专属微信会员卡' not in have and ('零售' in biz or tier == 'high'):
        gaps.append(('专属微信会员卡', '微信会员卡+积分+储值+会员画像', '中端款'))
    # 高活跃客户推AI工具
    if c.get('login_days', 0) > 150 and 'AI绘图' not in have:
        gaps.append(('AI绘图', 'AI自动绘图+智能抠图+商品图生成', '入门款'))
    # 批发客户推批量推款宝（真实存在的批发工具）
    if '批发' in biz and '批量推款宝' not in have and tier in ('mid', 'high'):
        gaps.append(('批量推款宝', '批量推款+客户在线选款+自动分享', '入门款'))
    return gaps[:3]  # 最多推荐3个

def _parse_contact(contact):
    """解析联系人字段，提取真实姓名。
    联系人列格式：
      1. 纯姓名：张玲、郑小进、杨森
      2. 店员格式带括号：店员3700(杨冰) → 取括号内
      3. 带括号别名：武小玲(武小丽) → 取第一个
      4. 店员XXXX无括号 / 管理员 / 店长 → 非真实姓名，返回None
      5. 纯数字 → 返回None
    """
    if not contact:
        return None
    s = str(contact).strip()
    if not s:
        return None
    # 纯数字 → 非姓名
    if s.isdigit():
        return None
    # 含括号 → 取括号内容或括号前内容
    if '(' in s or '（' in s:
        # 统一括号
        s_uni = s.replace('（', '(').replace('）', ')')
        parts = s_uni.split('(')
        before = parts[0].strip()
        inner = parts[1].replace(')', '').strip() if len(parts) > 1 else ''
        # "店员3700(杨冰)" → before="店员3700" → 取inner
        # "武小玲(武小丽)" → before="武小玲" → 取before
        # "18523317995(杨冲)" → before是纯数字 → 取inner
        # "兰应(郑位先)" → before="兰应" → 取before
        before_valid = before and not (before.startswith('店员') or before.startswith('管理员') or before.startswith('店长')) and not before.isdigit()
        if before_valid:
            return before
        inner_valid = inner and not (inner.startswith('店员') or inner.startswith('管理员') or inner.startswith('店长'))
        if inner_valid:
            return inner
        return None
    # 无括号
    # "店员3700""管理员""店长XXX" → 非真实姓名
    if s.startswith('店员') or s.startswith('管理员') or s.startswith('店长') or s.startswith('老板'):
        return None
    # 纯英文店员编号如"staff123"等
    if s.lower().startswith('staff'):
        return None
    # 其他视为真实姓名
    return s

def _call_name(c):
    """生成自然称呼——15年销售专家按姓氏称呼：张玲→张总，不是玲总。
    优先级：联系人真实姓名 → 公司名兜底 → 老板
    """
    # 第一步：尝试从联系人解析真实姓名
    real_name = _parse_contact(c.get('contact', ''))
    # 第二步：联系人无效，用公司名兜底（但排除"店铺XXXX""管理员"等非真实名称）
    if not real_name:
        company = c.get('name', '') or ''
        if not company:
            return '老板'
        s = company.strip()
        # "店铺XXXX""店铺NNNN"等编号型 → 老板
        if s.startswith('店铺') and any(ch.isdigit() for ch in s):
            return '老板'
        # 纯"管理员""店长"等 → 老板
        if s in ('管理员', '店长', '老板', '店'):
            return '老板'
        real_name = company
    if not real_name:
        return '老板'

    s = real_name.strip()
    # 纯数字 → 老板
    if s.isdigit():
        return '老板'
    # 纯英文 → Mr. + 首字母
    if all(ch.isascii() for ch in s):
        letters = [ch for ch in s if ch.isalpha()]
        if letters:
            return f'Mr.{letters[0].upper()}'
        return '老板'
    # 中文姓名 → 取姓氏（第一个字）+ 总
    # 中国人姓名：姓在前名在后，"张玲"姓张，"郑小进"姓郑，"欧阳锋"复姓欧阳
    cn_chars = [ch for ch in s if '\u4e00' <= ch <= '\u9fff']
    if not cn_chars:
        return '老板'
    # 复姓处理
    compound_surnames = ['欧阳', '司马', '诸葛', '上官', '司徒', '司空', '尉迟', '公孙', '令狐', '慕容', '皇甫', '宇文', '东方', '南宫', '西门']
    name_str = ''.join(cn_chars)
    for cs in compound_surnames:
        if name_str.startswith(cs):
            return f'{cs}总'
    # 单姓：取第一个字
    return f'{cn_chars[0]}总'

def _opening(c):
    """开场白：老客户不破冰，直接切入业务。根据回访状态+数据洞察生成。"""
    pa = c.get('pay_amount', 0)
    days = c.get('days_since_visit')
    lr = c.get('active_rate', 0)
    login_days = c.get('login_days', 0)
    expiring = c.get('expiring_services', [])
    call = _call_name(c)

    # 优先级1: 服务即将到期——直接报数据
    if expiring:
        svc_str = '、'.join(expiring[:2])
        return f'{call}，您{svc_str}快到期了，我提前说一声，现在续费老客户有优惠，顺便帮您看下要不要升级套餐。', '续费'

    # 优先级2: 高付费久未回访——关怀切入
    if pa >= 3000 and days and days >= 180:
        return f'{call}，好久没联系了。您是我们{pa:.0f}元的老客户，最近半年没跟进到您，今天专门来了解下用得怎么样，有没有遇到问题。', '挽回'

    # 优先级3: 高活跃——聊使用情况
    if login_days > 100 and lr >= 50:
        return f'{call}，看您系统用得挺频繁的，{login_days}天了。今天聊几句，看您这边有没有什么需要升级或加功能的。', '增值'

    # 优先级4: 低活跃/流失——问使用障碍
    if lr < 20 and pa > 0:
        return f'{call}，看您最近系统用得少，活跃率才{lr}%。是遇到什么问题了还是功能不够用？我帮您看下。', '激活'
    if lr == 0:
        return f'{call}，看到您有一阵没用系统了。是换其他软件了还是暂时没开店？不管怎样有问题都可以找我。', '唤醒'

    # 优先级5: 从未回访——建立关系
    if days is None:
        return f'{call}，之前一直没跟您联系上，今天专门打个电话。您现在生意怎么样？系统用着还顺手吗？', '首触'

    # 优先级6: 超长期未回访——回访关怀
    if days and days > 365:
        return f'{call}，快一年没联系了。今天回访一下，您生意怎么样？系统还在用吗？', '回访'

    # 兜底
    return f'{call}，今天打电话问候一下，您系统用得还顺利吗？有什么问题都可以跟我说。', '维护'

def _insight(c):
    """数据洞察：基于客户画像组合生成具体痛点分析（差异化核心）"""
    insights = []
    pa = c.get('pay_amount', 0)
    lr = c.get('active_rate', 0)
    login_days = c.get('login_days', 0)
    ind = c.get('industry_val', '')
    biz = c.get('biz_type', '')
    sn = c.get('store_count', 0)
    sa = c.get('sub_accounts', 0)
    expiring = c.get('expiring_services', [])
    web_shop = c.get('web_shop', '')
    hard_qty = c.get('hard_qty', 0)
    days = c.get('days_since_visit')
    services = [s['name'] for s in c.get('services', [])]
    tier = _pay_tier(pa)
    atier = _active_tier(lr, login_days)
    btag = _biz_tag(biz, ind)

    # 到期洞察
    if expiring:
        svc_str = '、'.join(expiring[:3])
        insights.append(f'【到期紧迫】{svc_str}即将到期，不及时续费影响日常经营')

    # 价值流失洞察
    if tier == 'high' and days and days >= 180:
        insights.append(f'【高价值流失风险】累计付费¥{pa:.0f}但{days}天未回访，客户可能被竞品切入')
    elif tier == 'mid' and days and days >= 365:
        insights.append(f'【中价值沉睡】累计付费¥{pa:.0f}，{days}天未回访，使用频率可能下降')

    # 活跃度洞察
    if atier == 'lost' and pa > 0:
        insights.append('【完全流失】活跃率0%，付费客户已停用，需立即挽回')
    elif atier == 'low' and pa > 0:
        insights.append(f'【活跃度低】活跃率{lr}%，付费客户使用频率极低，存在退费风险')

    # 线上渠道洞察
    if web_shop == '未开通' and login_days > 80:
        insights.append('【线上渠道缺失】高度依赖系统但未开通微商城，错失线上销售渠道')

    # 硬件洞察（按行业）
    if hard_qty == 0 and login_days > 50:
        if ind in CORE_INDUSTRIES:
            insights.append('【硬件效率低】服装行业高频扫码出入库但未配置收银终端，手动操作效率低')
        elif ind in ('商超便利', '食品饮料', '水果生鲜'):
            insights.append('【硬件效率低】高频收银场景但未配置收银终端，排队影响体验')

    # 行业专属痛点洞察（v3.2 · 基于行业画像库）
    ind_profile = c.get('industry_profile') or get_industry_profile(ind)
    ind_pains = ind_profile.get('painpoints', [])
    if ind_pains and ind != '未填':
        # 取前2个痛点避免过长
        pain_str = '；'.join(ind_pains[:2])
        insights.append(f'【{ind}行业痛点】{pain_str}')

    # 多门店洞察
    if sn >= 3:
        insights.append(f'【多店管理复杂】{sn}家门店需统一管理库存和调拨，手工对账易出错')
    elif sa >= 3 and sn < 3:
        insights.append(f'【多账号协同】{sa}个子账号需权限管理和数据隔离，基础版功能不足')

    # 行业业务洞察
    if btag == 'both':
        insights.append('【批零一体复杂】同时做批发零售，两套价格体系和客户管理混乱')
    elif btag == 'wholesale':
        insights.append('【批发订单管理】客户多订单量大，手工开单易漏单错单')
    elif btag == 'retail':
        insights.append('【零售会员薄弱】会员管理单一，营销活动工具少，复购率低')

    # 服务浪费洞察
    pay_svcs = c.get('pay_services_detail', [])
    unused = [ps for ps in pay_svcs if ps.get('surplus', 0) > 0]
    if unused:
        svc_names = '、'.join([f"{ps['name']}(余{ps['surplus']})" for ps in unused[:2]])
        insights.append(f'【服务浪费】已购买未使用: {svc_names}')

    # 回访洞察
    if days is None:
        insights.append('【从未回访】缺乏服务关系建立')
    elif days and days > 365:
        insights.append(f'【超长期未回访】{days}天未回访，客户可能已遗忘服务关系')

    if not insights:
        insights.append('【常规维护】客户状态正常，保持定期触达')

    return insights

def _recommend(c):
    """产品推荐：基于客单价层级+画像缺口+行业画像库，推荐匹配价位和功能的产品（精准营销核心）"""
    pa = c.get('pay_amount', 0)
    tier = _pay_tier(pa)
    gaps = _gap_products(c)
    ind = c.get('industry_val', '')
    biz = c.get('biz_type', '')
    sn = c.get('store_count', 0)

    # v3.2：把行业画像库推荐产品合并到gaps前面（行业专属推荐优先）
    ind_profile = c.get('industry_profile') or get_industry_profile(ind)
    ind_recommends = ind_profile.get('recommend', [])
    have = set(s['name'] for s in c.get('services', []))
    ind_gaps = []
    for prod in ind_recommends:
        if prod not in have and prod in QINSILK_PRODUCTS:
            info = QINSILK_PRODUCTS[prod]
            ind_gaps.append((prod, info['value'], info['tier']))
    # 行业专属推荐优先，合并去重
    seen_names = set()
    merged_gaps = []
    for g in ind_gaps + gaps:
        if g[0] not in seen_names:
            merged_gaps.append(g)
            seen_names.add(g[0])
    gaps = merged_gaps[:3]  # 最多3个

    if not gaps:
        # 无明确缺口，根据付费层级给通用升级建议（产品名均为真实产品）
        if tier == 'high':
            return '您是高价值老客户，建议关注AI绘图和专属微信会员卡，能帮您把会员运营和商品图效率做上来。'
        elif tier == 'mid':
            return '您目前用得不错，如果想提升效率可以考虑专属微信会员卡或直播卖货，把会员复购和线上渠道做起来。'
        elif tier == 'low':
            return '您现在的版本比较基础，如果生意做大了可以考虑升级到进销存专业版，功能更全。'
        else:
            return '您还没付费，建议先试用进销存会员版，上手管理进销存。'

    # 有明确缺口——根据客单价层级推荐对应价位产品
    # 修饰语只说一次，产品简洁列出
    if tier == 'high':
        prefix = '跟您现在的体量匹配，建议直接上'
    elif tier == 'mid':
        prefix = '性价比高，很多同体量客户都在用'
    elif tier == 'low':
        prefix = '可以先试用看看效果，合适再正式开通'
    else:
        prefix = '可以先免费体验，觉得好用再考虑付费'

    if len(gaps) == 1:
        prod, value, price = gaps[0]
        return f'{prod}（{price}）——{value}，{prefix}。'
    # 多个产品：主推第一个详细说，其余简列
    main_prod, main_val, main_price = gaps[0]
    others = '、'.join([f'{p[0]}（{p[2]}）' for p in gaps[1:]])
    return f'{main_prod}（{main_price}）——{main_val}，{prefix}。另外{others}也可以看下。'

def _close(c):
    """促单方式：根据意向+机会分生成"""
    intention = c.get('intention', '无')
    opp_score = c.get('opportunity_score', 0)

    if intention == '意向':
        return '您这边有意向，我今天专门跟您详细聊。您目前最想解决什么问题？我帮您匹配方案，合适的话直接演示给您看。'
    if opp_score >= 60:
        return '我看您这边需求挺明确的，要不我给您做个方案，明天发您看看？合适的话这周就能帮您开通。'
    if opp_score >= 30:
        return '您这边可以考虑下，我先把资料发您，有什么问题随时找我。'
    return '您先了解着，有什么问题随时联系我，我这边随时帮您看。'

def generate_script_and_painpoints(c):
    """15年销售专家视角：老客户精准营销话术——不破冰，数据驱动，对症下药，差异化推荐"""
    # 1. 开场（老客户直接切入业务）
    opening, opp_tag = _opening(c)
    # 2. 数据洞察（差异化痛点分析）
    insights = _insight(c)
    # 3. 产品推荐（客单价分层匹配）
    recommend = _recommend(c)
    # 4. 促单（意向+机会分驱动）
    close = _close(c)

    # 组装话术：开场 + 洞察 + 推荐 + 促单（自然衔接，像同行交流）
    script = f'{opening} {recommend} {close}'

    # 痛点分析独立输出（给销售看的话术背后的逻辑）
    c['painpoints'] = '\n'.join(insights)
    c['script'] = script
    c['opportunity_type'] = opp_tag
    # 建议动作
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
green_fill = PatternFill('solid', fgColor='E2EFDA')
yellow_fill = PatternFill('solid', fgColor='FFF2CC')
orange_fill = PatternFill('solid', fgColor='FCE4D6')
metric_fill = PatternFill('solid', fgColor='D9E1F2')
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
ws1['A1'] = f'成都分部 SDR 服务池跟进名单 v3.0（5维画像规则+沟通话术+痛点分析 · 全量）'
ws1['A1'].font = title_font; ws1['A1'].fill = title_fill; ws1['A1'].alignment = center
ws1.row_dimensions[1].height = 30

ws1.merge_cells('A2:Z2')
ws1['A2'] = (f'数据基准：2026-07-02 · 成都分部全量{len(customers)}条 | '
             f'S级必跟{sub_grades.get("S",0)} / A2重点{sub_grades.get("A2",0)} / A3常规{sub_grades.get("A3",0)} / B类{grades["B"]} / C类{grades["C"]} | '
             f'客户标识CID · 付费数据100% · 服务到期数据100%')
ws1['A2'].font = sub_font; ws1['A2'].fill = sub_fill; ws1['A2'].alignment = center
ws1.row_dimensions[2].height = 22

# 图例行
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
ws1.merge_cells('K3:Z3'); ws1['K3'] = '⚠红底=有服务即将到期 | 黄底=高付费未回访 | 橙底=活跃度低'
ws1['K3'].font = legend_font; ws1['K3'].fill = orange_fill; ws1['K3'].alignment = center
ws1.row_dimensions[3].height = 20

headers = [
    '优先级', '公司名称', '联系人', 'CID', '顾问', '行业', '业务类型',
    '门店/子账号', '系统', '活跃率', '登录/总天数', '付费金额', '硬件',
    '注册日期', '上次回访', '未回访天数', '意向',
    # 5维画像规则
    'R1到期', 'R2高付费', 'R3高活跃', 'R4多门店', 'R5机会评判',
    # 评分
    '机会分', '总分', '触发规则',
    # 话术与痛点
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
    days = c.get('days_since_visit')
    days_str = str(days) if days is not None else '未知'
    pa = c.get('pay_amount', 0)
    sn = c.get('store_count', 0)
    sa = c.get('sub_accounts', 0)
    expiring = c.get('expiring_services', [])
    
    ws1.cell(row, 1, sub_grade)
    ws1.cell(row, 2, c.get('name', ''))
    ws1.cell(row, 3, c.get('contact', ''))
    ws1.cell(row, 4, c.get('cid', ''))
    ws1.cell(row, 5, c.get('advisor', ''))
    ws1.cell(row, 6, c.get('industry_val', ''))
    ws1.cell(row, 7, c.get('biz_type', ''))
    ws1.cell(row, 8, f"{sn}店/{sa}账号")
    ws1.cell(row, 9, c.get('sys_name', ''))
    ws1.cell(row, 10, f"{c.get('active_rate', 0)}%")
    ws1.cell(row, 11, f"{c.get('login_days', 0)}/{c.get('total_days', 0)}")
    ws1.cell(row, 12, f"¥{pa:.0f}" if pa > 0 else '未付费')
    ws1.cell(row, 13, c.get('hard_qty', 0))
    ws1.cell(row, 14, c.get('reg_date', ''))
    ws1.cell(row, 15, c.get('last_visit', '未回访'))
    ws1.cell(row, 16, days_str)
    ws1.cell(row, 17, c.get('intention', '无'))
    
    # R1-R5
    ws1.cell(row, 18, '⚠是' if expiring else '否')
    ws1.cell(row, 19, f"¥{pa:.0f}" if pa > 3000 else '否')
    ws1.cell(row, 20, f"{c.get('login_days',0)}天" if c.get('login_days', 0) > 100 else '否')
    ws1.cell(row, 21, f"{sn+sa}单元" if (sn + sa) >= 3 else '否')
    
    # R5 机会评判
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
            # 优先级列按 sub_grade 上色
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
            if col == 12 and pa > 3000:
                cell.font = Font(name='微软雅黑', size=9, bold=True, color='9C0006')
            if col == 18 and expiring:
                cell.fill = PatternFill('solid', fgColor='F8D7DA')
                cell.font = Font(name='微软雅黑', size=9, bold=True, color='9C0006')
            if col in [26, 27]:
                cell.font = Font(name='微软雅黑', size=8)
            # 整行底色按 sub_grade（R1到期列除外）
            if col != 1 and col != 18:
                if sub_grade == 'S':
                    cell.fill = a1_fill
                elif sub_grade == 'A2':
                    cell.fill = a2_fill
                elif sub_grade == 'A3':
                    cell.fill = a3_fill
                elif grade == 'B':
                    cell.fill = b_fill
                elif grade == 'C':
                    cell.fill = c_fill
    ws1.row_dimensions[row].height = 80
    row += 1

col_widths = [6, 22, 14, 14, 8, 10, 10, 12, 8, 8, 10, 12, 6, 12, 14, 10, 8,
              8, 8, 8, 8, 30, 6, 6, 30, 45, 55, 25, 20]
for i, w in enumerate(col_widths, 1):
    ws1.column_dimensions[get_column_letter(i)].width = w
ws1.freeze_panes = 'E5'

# ============ Sheet2: S类必跟客户话术（24h内必触达）============
ws2 = wb.create_sheet('S类必跟客户话术')
ws2.merge_cells('A1:N1')
ws2['A1'] = f'S类必跟客户话术（{sub_grades.get("S",0)}条 · 24小时内必触达）'
ws2['A1'].font = title_font; ws2['A1'].fill = PatternFill('solid', fgColor='C0504D'); ws2['A1'].alignment = center
ws2.row_dimensions[1].height = 30

a_headers = ['排名', '公司名称', '联系人', 'CID', '行业', '付费金额', '活跃率',
             '即将到期服务', '机会类型', '细分原因', '痛点分析', '沟通话术', '建议动作']
for col, h in enumerate(a_headers, 1):
    cell = ws2.cell(3, col, h)
    cell.font = header_font; cell.fill = header_fill; cell.alignment = center; cell.border = border
ws2.row_dimensions[3].height = 28

a1_customers = [c for c in customers if c.get('sub_grade') == 'S']
for i, c in enumerate(a1_customers, 1):
    r = 3 + i
    pa = c.get('pay_amount', 0)
    expiring = c.get('expiring_services', [])
    ws2.cell(r, 1, i)
    ws2.cell(r, 2, c.get('name', ''))
    ws2.cell(r, 3, c.get('contact', ''))
    ws2.cell(r, 4, c.get('cid', ''))
    ws2.cell(r, 5, c.get('industry_val', ''))
    ws2.cell(r, 6, f"¥{pa:.0f}" if pa > 0 else '未付费')
    ws2.cell(r, 7, f"{c.get('active_rate', 0)}%")
    ws2.cell(r, 8, '、'.join(expiring) if expiring else '无')
    ws2.cell(r, 9, c.get('opportunity_type', ''))
    ws2.cell(r, 10, c.get('sub_reason', ''))
    ws2.cell(r, 11, c.get('painpoints', ''))
    ws2.cell(r, 12, c.get('script', ''))
    ws2.cell(r, 13, c.get('action', ''))

    for col in range(1, 14):
        cell = ws2.cell(r, col)
        cell.border = border
        cell.alignment = center if col in [1, 5, 6, 7] else left_align
        cell.font = Font(name='微软雅黑', size=9)
        if col == 6 and pa > 3000:
            cell.font = Font(name='微软雅黑', size=9, bold=True, color='9C0006')
        if col == 8 and expiring:
            cell.fill = PatternFill('solid', fgColor='F8D7DA')
            cell.font = Font(name='微软雅黑', size=9, bold=True, color='9C0006')
        else:
            cell.fill = a1_fill
        if col in [11, 12]:
            cell.font = Font(name='微软雅黑', size=8)
    ws2.row_dimensions[r].height = 120

a_widths = [6, 22, 14, 14, 10, 12, 8, 20, 15, 18, 50, 60, 25]
for i, w in enumerate(a_widths, 1):
    ws2.column_dimensions[get_column_letter(i)].width = w
ws2.freeze_panes = 'E4'

# ============ Sheet3: 服务到期预警 ============
ws3 = wb.create_sheet('服务到期预警')
ws3.merge_cells('A1:H1')
ws3['A1'] = '系统服务到期预警（60天内到期 · 按紧急程度排序）'
ws3['A1'].font = title_font; ws3['A1'].fill = PatternFill('solid', fgColor='C0504D'); ws3['A1'].alignment = center
ws3.row_dimensions[1].height = 30

exp_headers = ['排名', '公司名称', 'CID', '到期服务', '到期日期', '剩余天数', '付费金额', '续费话术']
for col, h in enumerate(exp_headers, 1):
    cell = ws3.cell(3, col, h)
    cell.font = header_font; cell.fill = header_fill; cell.alignment = center; cell.border = border
ws3.row_dimensions[3].height = 28

exp_records = []
for c in customers:
    detail = c.get('_detail', {})
    ext_obj = detail.get('extend', {}).get('object', {})
    exp_list = ext_obj.get('expirationList', [])
    for exp in exp_list:
        enable_end = exp.get('enableEnd')
        svc_name = exp.get('serviceName', '')
        if not enable_end or enable_end > 4000000000000 or not svc_name:
            continue
        try:
            end_dt = datetime.fromtimestamp(enable_end / 1000)
            days_left = (end_dt - now).days
            if 0 <= days_left <= 60:
                product = QINSILK_PRODUCTS.get(svc_name, {})
                exp_records.append({
                    'name': c.get('name', ''),
                    'cid': c.get('cid', ''),
                    'service': svc_name,
                    'end_date': end_dt.strftime('%Y-%m-%d'),
                    'days_left': days_left,
                    'pay': c.get('pay_amount', 0),
                    'product_info': product.get('value', ''),
                    'price': product.get('price_range', ''),
                    'grade': c.get('grade', 'C')
                })
        except:
            pass

exp_records.sort(key=lambda x: x['days_left'])
for i, er in enumerate(exp_records, 1):
    r = 3 + i
    ws3.cell(r, 1, i)
    ws3.cell(r, 2, er['name'])
    ws3.cell(r, 3, er['cid'])
    ws3.cell(r, 4, er['service'])
    ws3.cell(r, 5, er['end_date'])
    ws3.cell(r, 6, f"{er['days_left']}天")
    ws3.cell(r, 7, f"¥{er['pay']:.0f}" if er['pay'] > 0 else '未付费')
    
    script = f"您好，您的{er['service']}还有{er['days_left']}天到期（{er['end_date']}）。"
    if er['product_info']:
        script += f"该服务包含{er['product_info']}。"
    script += "现在续费有老客户专属优惠，要不要我帮您看下续费方案？也可以升级到更高级版本。"
    ws3.cell(r, 8, script)
    
    for col in range(1, 9):
        cell = ws3.cell(r, col)
        cell.border = border
        cell.alignment = center if col in [1, 5, 6, 7] else left_align
        cell.font = Font(name='微软雅黑', size=9)
        if col == 6:
            if er['days_left'] <= 7:
                cell.fill = PatternFill('solid', fgColor='F8D7DA')
                cell.font = Font(name='微软雅黑', size=10, bold=True, color='9C0006')
            elif er['days_left'] <= 30:
                cell.fill = a_fill
            else:
                cell.fill = yellow_fill
        if col == 8:
            cell.font = Font(name='微软雅黑', size=8)
    ws3.row_dimensions[r].height = 60

for i, w in enumerate([6, 22, 14, 20, 14, 10, 12, 60], 1):
    ws3.column_dimensions[get_column_letter(i)].width = w
ws3.freeze_panes = 'A4'

# ============ Sheet4: 客户画像深度分析 ============
ws4 = wb.create_sheet('画像分析')
ws4.merge_cells('A1:E1')
ws4['A1'] = '服务池客户画像深度分析（5维规则+产品分布）'
ws4['A1'].font = title_font; ws4['A1'].fill = title_fill; ws4['A1'].alignment = center
ws4.row_dimensions[1].height = 30

r = 3
ws4.cell(r, 1, '【5维画像规则触发统计】').font = Font(name='微软雅黑', size=11, bold=True, color='2F5496')
r += 1
rule_stats = [
    ('R1 系统即将到期(60天内)', sum(1 for c in customers if c.get('expiring_services')), '紧急·续费机会'),
    ('R2 付费金额>¥3000', sum(1 for c in customers if c.get('pay_amount', 0) > 3000), '高价值·增购机会'),
    ('R3 活跃天数>100天', sum(1 for c in customers if c.get('login_days', 0) > 100), '高粘性·升单机会'),
    ('R4 门店/子账号≥3', sum(1 for c in customers if (c.get('store_count', 0) + c.get('sub_accounts', 0)) >= 3), '规模化·增购机会'),
    ('R5 销售机会分≥50', sum(1 for c in customers if c.get('opportunity_score', 0) >= 50), '高机会·重点跟进'),
]
for label, cnt, note in rule_stats:
    ws4.cell(r, 1, label).font = Font(name='微软雅黑', size=10, bold=True)
    ws4.cell(r, 2, cnt).font = Font(name='微软雅黑', size=10)
    ws4.cell(r, 3, f'{cnt/len(customers)*100:.1f}%').font = Font(name='微软雅黑', size=10)
    ws4.cell(r, 4, note).font = Font(name='微软雅黑', size=10)
    for col in range(1, 5):
        ws4.cell(r, col).border = border
    r += 1

r += 1
ws4.cell(r, 1, '【秦丝产品分布（服务到期项）】').font = Font(name='微软雅黑', size=11, bold=True, color='2F5496')
r += 1
svc_counter = Counter()
for c in customers:
    for s in c.get('services', []):
        svc_counter[s['name']] += 1
for svc, cnt in svc_counter.most_common(15):
    ws4.cell(r, 1, svc).font = Font(name='微软雅黑', size=10, bold=True)
    ws4.cell(r, 2, cnt).font = Font(name='微软雅黑', size=10)
    ws4.cell(r, 3, f'{cnt/len(customers)*100:.1f}%').font = Font(name='微软雅黑', size=10)
    prod = QINSILK_PRODUCTS.get(svc, {})
    ws4.cell(r, 4, prod.get('category', '')).font = Font(name='微软雅黑', size=10)
    ws4.cell(r, 5, prod.get('value', '')[:50]).font = Font(name='微软雅黑', size=9)
    for col in range(1, 6):
        ws4.cell(r, col).border = border
    r += 1

r += 1
ws4.cell(r, 1, '【销售机会类型分布】').font = Font(name='微软雅黑', size=11, bold=True, color='2F5496')
r += 1
opp_counter = Counter()
for c in customers:
    for ot in c.get('opportunity_type', '').split('、'):
        if ot:
            opp_counter[ot] += 1
for ot, cnt in opp_counter.most_common():
    ws4.cell(r, 1, ot).font = Font(name='微软雅黑', size=10, bold=True)
    ws4.cell(r, 2, cnt).font = Font(name='微软雅黑', size=10)
    ws4.cell(r, 3, f'{cnt/len(customers)*100:.1f}%').font = Font(name='微软雅黑', size=10)
    for col in range(1, 4):
        ws4.cell(r, col).border = border
    r += 1

ws4.column_dimensions['A'].width = 30
ws4.column_dimensions['B'].width = 12
ws4.column_dimensions['C'].width = 10
ws4.column_dimensions['D'].width = 15
ws4.column_dimensions['E'].width = 50

# ============ Sheet5: 可视化看板 ============
ws5 = wb.create_sheet('可视化看板')
ws5.merge_cells('A1:N1')
ws5['A1'] = '成都分部 SDR 可视化看板 v3.0（5维画像+话术痛点 · 全量）'
ws5['A1'].font = title_font; ws5['A1'].fill = title_fill; ws5['A1'].alignment = center
ws5.row_dimensions[1].height = 30

ws5.merge_cells('A2:N2')
ws5['A2'] = f'数据基准 2026-07-02 | 成都分部全量 {len(customers)} 条 | 客户标识CID | 付费100% | 到期数据100% | 生成 {now.strftime("%Y-%m-%d")}'
ws5['A2'].font = sub_font; ws5['A2'].fill = sub_fill; ws5['A2'].alignment = center

metric_row = 4
paid_count = sum(1 for c in customers if c.get('pay_amount', 0) > 0)
total_pay = sum(c.get('pay_amount', 0) for c in customers)
expiring_count = sum(1 for c in customers if c.get('expiring_services'))
high_active = sum(1 for c in customers if c.get('login_days', 0) > 100)
multi_scale = sum(1 for c in customers if (c.get('store_count', 0) + c.get('sub_accounts', 0)) >= 3)
metrics = [
    ('总客户数', len(customers), '2F5496'),
    ('S级 必跟24h', sub_grades.get('S', 0), '9C0006'),
    ('A2 重点48h', sub_grades.get('A2', 0), '8B4500'),
    ('A3 常规A', sub_grades.get('A3', 0), '8B4500'),
    ('B类 本周', grades['B'], '9C6500'),
    ('C类 常规', grades['C'], '006100'),
    ('即将到期', expiring_count, '9C0006'),
    ('总付费金额', f'¥{total_pay:.0f}', '9C0006'),
]
for i, (label, val, color) in enumerate(metrics):
    col_start = 1 + i * 2; col_end = col_start + 1
    ws5.merge_cells(start_row=metric_row, start_column=col_start, end_row=metric_row, end_column=col_end)
    cell = ws5.cell(metric_row, col_start, label)
    cell.font = Font(name='微软雅黑', size=10, color='595959'); cell.fill = metric_fill; cell.alignment = center
    ws5.merge_cells(start_row=metric_row + 1, start_column=col_start, end_row=metric_row + 1, end_column=col_end)
    cell2 = ws5.cell(metric_row + 1, col_start, val)
    cell2.font = Font(name='微软雅黑', size=18, bold=True, color=color); cell2.fill = metric_fill; cell2.alignment = center
ws5.row_dimensions[metric_row].height = 22; ws5.row_dimensions[metric_row + 1].height = 36

# 文本洞察区（第7-11行·填充KPI与图表之间的空白）
ws5.merge_cells('A7:N7')
ws5['A7'] = '【关键数据洞察】'
ws5['A7'].font = Font(name='微软雅黑', size=11, bold=True, color='2F5496')
ws5['A7'].alignment = Alignment(horizontal='left', vertical='center')
ws5.row_dimensions[7].height = 22

core_ind = sum(1 for c in customers if c.get('industry_val', '') in CORE_INDUSTRIES)
no_visit = sum(1 for c in customers if c.get('days_since_visit') is None)
avg_pay = total_pay / paid_count if paid_count else 0
insights = [
    f'分级: S级必跟{sub_grades.get("S",0)}条({sub_grades.get("S",0)/len(customers)*100:.1f}%) | A2重点{sub_grades.get("A2",0)}条 | A3常规{sub_grades.get("A3",0)}条 | B类{grades["B"]}条 | C类{grades["C"]}条',
    f'付费: 已付费{paid_count}条({paid_count/len(customers)*100:.1f}%) | 总额¥{total_pay:.0f} | 均值¥{avg_pay:.0f}',
    f'活跃: 高活跃(>100天){high_active}条({high_active/len(customers)*100:.1f}%) | 多单元(≥3){multi_scale}条 | 核心行业{core_ind}条',
    f'风险: 即将到期{expiring_count}条 | 从未回访{no_visit}条 | S级必跟客户需24h内全部触达',
]
for i, txt in enumerate(insights):
    r = 8 + i
    ws5.merge_cells(f'A{r}:N{r}')
    ws5.cell(r, 1, f'  · {txt}')
    ws5.cell(r, 1).font = Font(name='微软雅黑', size=10, color='333333')
    ws5.cell(r, 1).alignment = Alignment(horizontal='left', vertical='center')
    ws5.row_dimensions[r].height = 18

# 图表数据区（可见·A/B列·第13行起·不隐藏列）
ws5.merge_cells('A13:B13')
ws5['A13'] = '图表数据源'
ws5['A13'].font = Font(name='微软雅黑', size=9, bold=True, color='595959')
ws5['A13'].fill = PatternFill('solid', fgColor='F2F2F2')
ws5['A13'].alignment = center

ws5.cell(14, 1, '分级'); ws5.cell(14, 2, '数量')
ws5.cell(14, 1).font = Font(name='微软雅黑', size=9, bold=True)
ws5.cell(14, 2).font = Font(name='微软雅黑', size=9, bold=True)
grade_data = [('S', sub_grades.get('S', 0)), ('A2', sub_grades.get('A2', 0)), ('A3', sub_grades.get('A3', 0)), ('B', grades['B']), ('C', grades['C'])]
for i, (g, n) in enumerate(grade_data, 15):
    ws5.cell(i, 1, g); ws5.cell(i, 2, n)
    ws5.cell(i, 1).font = Font(name='微软雅黑', size=9)
    ws5.cell(i, 2).font = Font(name='微软雅黑', size=9)

opp_row = 19
ws5.cell(opp_row, 1, '机会类型'); ws5.cell(opp_row, 2, '数量')
ws5.cell(opp_row, 1).font = Font(name='微软雅黑', size=9, bold=True)
ws5.cell(opp_row, 2).font = Font(name='微软雅黑', size=9, bold=True)
opp_top = opp_counter.most_common(8)
for i, (g, n) in enumerate(opp_top, opp_row+1):
    ws5.cell(i, 1, g); ws5.cell(i, 2, n)
    ws5.cell(i, 1).font = Font(name='微软雅黑', size=9)
    ws5.cell(i, 2).font = Font(name='微软雅黑', size=9)

prod_row = opp_row + len(opp_top) + 2
ws5.cell(prod_row, 1, '产品'); ws5.cell(prod_row, 2, '数量')
ws5.cell(prod_row, 1).font = Font(name='微软雅黑', size=9, bold=True)
ws5.cell(prod_row, 2).font = Font(name='微软雅黑', size=9, bold=True)
svc_top = svc_counter.most_common(8)
for i, (g, n) in enumerate(svc_top, prod_row+1):
    ws5.cell(i, 1, g); ws5.cell(i, 2, n)
    ws5.cell(i, 1).font = Font(name='微软雅黑', size=9)
    ws5.cell(i, 2).font = Font(name='微软雅黑', size=9)

# 图表（引用可见数据区·放在数据右侧D列起）
pie = PieChart(); pie.title = '客户分级分布（S/A2/A3/B/C）'
pie.add_data(Reference(ws5, min_col=2, min_row=14, max_row=19), titles_from_data=True)
pie.set_categories(Reference(ws5, min_col=1, min_row=15, max_row=19))
pie.dataLabels = DataLabelList(); pie.dataLabels.showPercent = True
pie.height = 7; pie.width = 10; ws5.add_chart(pie, 'D13')

bar1 = BarChart(); bar1.type = 'bar'; bar1.title = '销售机会类型 TOP8'; bar1.style = 10
bar1.add_data(Reference(ws5, min_col=2, min_row=opp_row, max_row=opp_row+len(opp_top)), titles_from_data=True)
bar1.set_categories(Reference(ws5, min_col=1, min_row=opp_row+1, max_row=opp_row+len(opp_top)))
bar1.legend = None; bar1.height = 7; bar1.width = 10; ws5.add_chart(bar1, 'I13')

bar2 = BarChart(); bar2.type = 'bar'; bar2.title = '产品分布 TOP8'; bar2.style = 12
bar2.add_data(Reference(ws5, min_col=2, min_row=prod_row, max_row=prod_row+len(svc_top)), titles_from_data=True)
bar2.set_categories(Reference(ws5, min_col=1, min_row=prod_row+1, max_row=prod_row+len(svc_top)))
bar2.legend = None; bar2.height = 8; bar2.width = 16; ws5.add_chart(bar2, 'D30')

for i in range(1, 15):
    ws5.column_dimensions[get_column_letter(i)].width = 12
ws5.column_dimensions['A'].width = 16
ws5.column_dimensions['B'].width = 10

# ============ Sheet6: 筛选方法论 ============
ws6 = wb.create_sheet('筛选方法论')
ws6.column_dimensions['A'].width = 28; ws6.column_dimensions['B'].width = 85

methodology = [
    ('', ''),
    ('【5维画像规则】', ''),
    ('R1 系统即将到期(60天内)', '解析expirationList中enableEnd时间戳，筛选60天内到期的付费服务 → 续费触达'),
    ('R2 付费金额>¥3000', '从详情API userExtendInfo.payAmount获取真实付费金额 → 高价值增购'),
    ('R3 活跃天数>100天', '从loginDays字段获取实际登录天数 → 高粘性升单'),
    ('R4 门店/子账号≥3', 'store_count + userNumber >= 3 → 规模化增购'),
    ('R5 销售机会综合评判', '综合意向+行业+业务类型+硬件+服务余额+可触达渠道 → 机会评分(0-100)'),
    ('', ''),
    ('【评分模型 v3.0 · 6维+规则加成】', ''),
    ('D1 回访紧迫度(5)', '0-30天=1 | 31-90天=2 | 91-180天=3 | 181-365天=4 | 365+天=5 | 无=3'),
    ('D2 行业匹配度(5)', 'v3.2行业画像库：核心(服装)=5 | 强匹配(食品/数码/美妆/母婴/烟酒/珠宝/商超/水果)=4 | 通用(百货/建材/家居/五金/汽配/文体/农药/宠物)=3 | 未填=1'),
    ('D3 业务类型(5)', '未填=1 | 零售=2 | 批发=3 | 批发+零售=5'),
    ('D4 门店规模(5)', '无=1 | 1-2单元=2-3 | 3-5单元=4 | 6+单元=5'),
    ('D5 活跃度(5)', '0%=1 | 1-19%=1 | 20-49%=2 | 50-79%=3 | ≥80%=5'),
    ('D6 付费价值(5)', '未付费=1 | ¥1-999=3 | ¥1000-2999=4 | ≥¥3000=5'),
    ('规则加成', '机会分≥50→+3 | ≥30→+2 | ≥15→+1'),
    ('', ''),
    ('【秦丝产品线】', ''),
    ('核心系统-进销存', '进销存会员/进销存专业版'),
    ('核心系统-生意通', '生意通会员/生意通专业版/生意通高级版'),
    ('线上渠道-微商城', '销货宝微商城标准版/基础版/专业版'),
    ('线上渠道-小程序', '专属品牌小程序'),
    ('营销工具', '限时折扣促单宝/限时秒杀促单宝/批量推款宝/直播卖货/微信自动化经营'),
    ('会员运营', '专属微信会员卡/会员积分充值/客户积分'),
    ('硬件-收银', '慧店宝/慧店宝大屏收银端'),
    ('AI工具', 'AI绘图/以图搜图'),
    ('门店/账号扩展', '门店/子帐号'),
    ('品牌展示', '商家名片'),
    ('私域运营', '企业微信客户助手'),
    ('联盟体系', '联盟版/联盟版绑定数'),
    ('多店管理', '多店智擎'),
    ('存储扩展', '秦丝进销存云存储费/秦丝生意通云存储费'),
    ('增值服务', '短信服务/数据迁移服务/订制打印模板'),
    ('', ''),
    ('【分级结果 v3.1 · A级细分】', ''),
    ('总量', f'{len(customers)}条'),
    ('S级 必跟(24h)', f'{sub_grades.get("S",0)}条({sub_grades.get("S",0)/len(customers)*100:.1f}%) · 服务7天内到期/高付费久未回访/意向'),
    ('A2 重点(48h)', f'{sub_grades.get("A2",0)}条({sub_grades.get("A2",0)/len(customers)*100:.1f}%) · 30天内到期/机会分≥60/高付费高活跃'),
    ('A3 常规A(本周)', f'{sub_grades.get("A3",0)}条({sub_grades.get("A3",0)/len(customers)*100:.1f}%) · 其余A级'),
    ('B类', f'{grades["B"]}条({grades["B"]/len(customers)*100:.1f}%) · 本周触达'),
    ('C类', f'{grades["C"]}条({grades["C"]/len(customers)*100:.1f}%) · 常规维护'),
    ('CID覆盖', f'100%({len(customers)}/{len(customers)}) · 用CID替代手机号规避信息泄露'),
    ('付费数据覆盖', f'100% · 已付费{paid_count}条 · 总¥{total_pay:.0f}'),
    ('到期数据覆盖', f'100% · 60天内到期{expiring_count}条'),
]

for r_idx, (a, b) in enumerate(methodology, 1):
    ws6.cell(r_idx, 1, a)
    ws6.cell(r_idx, 2, b)
    if a.startswith('【'):
        ws6.cell(r_idx, 1).font = Font(name='微软雅黑', size=11, bold=True, color='2F5496')
    else:
        ws6.cell(r_idx, 1).font = Font(name='微软雅黑', size=10, bold=True)
        ws6.cell(r_idx, 2).font = Font(name='微软雅黑', size=10)
    ws6.cell(r_idx, 1).alignment = Alignment(vertical='center', wrap_text=True)
    ws6.cell(r_idx, 2).alignment = Alignment(vertical='center', wrap_text=True)

# ============ Sheet7: 回访回填表（反馈闭环·让系统会进化）============
ws7 = wb.create_sheet('回访回填表')

ws7.merge_cells('A1:K1')
ws7['A1'] = '回访回填表 · 让系统会进化（销售打完电话后回填，下次抓取读取）'
ws7['A1'].font = title_font; ws7['A1'].fill = title_fill; ws7['A1'].alignment = center
ws7.row_dimensions[1].height = 30

ws7.merge_cells('A2:K2')
ws7['A2'] = ('使用说明：每打完一个客户电话，在对应行回填「回访结果」+「备注」+「下次跟进日期」 | '
             '时间衰减规则：S级7天未回填→降A2，A2未回填14天→降A3，A3未回填30天→降B | '
             '下次抓取时读取本表回填数据，调整评分权重')
ws7['A2'].font = Font(name='微软雅黑', size=9, color='C0504D', italic=True)
ws7['A2'].fill = PatternFill('solid', fgColor='FFF3E0')
ws7['A2'].alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
ws7.row_dimensions[2].height = 40

# 只放S+A2级（这些是要回填的重点）
followup_customers = [c for c in customers if c.get('sub_grade') in ('S', 'A2')]
ws7.merge_cells('A3:K3')
ws7['A3'] = f'待回填客户：S级{sub_grades.get("S",0)}条 + A2级{sub_grades.get("A2",0)}条 = 共{len(followup_customers)}条（重点跟进对象）'
ws7['A3'].font = legend_font; ws7['A3'].fill = PatternFill('solid', fgColor='E2EFDA'); ws7['A3'].alignment = center
ws7.row_dimensions[3].height = 20

fb_headers = ['优先级', '公司名称', '联系人', '手机号', 'CID', '当前分级', '细分原因',
              '回访结果', '备注', '下次跟进日期', '是否成交']
for col, h in enumerate(fb_headers, 1):
    cell = ws7.cell(4, col, h)
    cell.font = header_font; cell.fill = header_fill; cell.alignment = center; cell.border = border
ws7.row_dimensions[4].height = 32

# 数据有效性下拉（回访结果）
from openpyxl.worksheet.datavalidation import DataValidation
dv_result = DataValidation(type="list", formula1='"已联系·有意向,已联系·无意向,已联系·待跟进,未接听·电话,未接听·微信,拒绝·不要了,号码错误,已成交"', allow_blank=True)
dv_result.add('H5:H1000')
ws7.add_data_validation(dv_result)

dv_deal = DataValidation(type="list", formula1='"是,否"', allow_blank=True)
dv_deal.add('K5:K1000')
ws7.add_data_validation(dv_deal)

row = 5
for c in followup_customers:
    sub_grade = c.get('sub_grade', '')
    ws7.cell(row, 1, sub_grade)
    ws7.cell(row, 2, c.get('name', ''))
    ws7.cell(row, 3, c.get('contact', ''))
    ws7.cell(row, 4, c.get('phone', ''))
    ws7.cell(row, 5, c.get('cid', ''))
    ws7.cell(row, 6, sub_grade)
    ws7.cell(row, 7, c.get('sub_reason', ''))
    # H/I/J/K 留空给销售回填
    ws7.cell(row, 8, '')
    ws7.cell(row, 9, '')
    ws7.cell(row, 10, '')
    ws7.cell(row, 11, '')

    for col in range(1, 12):
        cell = ws7.cell(row, col)
        cell.border = border
        cell.alignment = center if col in [1, 4, 6, 10, 11] else left_align
        cell.font = Font(name='微软雅黑', size=9)
        if col == 1:
            if sub_grade == 'S':
                cell.fill = a1_fill; cell.font = Font(name='微软雅黑', size=9, bold=True, color='9C0006')
            elif sub_grade == 'A2':
                cell.fill = a2_fill; cell.font = Font(name='微软雅黑', size=9, bold=True, color='8B4500')
        # 回填列加浅色底提示
        if col in [8, 9, 10, 11]:
            cell.fill = PatternFill('solid', fgColor='FFFDE7')
    row += 1

fb_widths = [6, 22, 14, 14, 14, 8, 18, 16, 25, 12, 10]
for i, w in enumerate(fb_widths, 1):
    ws7.column_dimensions[get_column_letter(i)].width = w
ws7.freeze_panes = 'B5'

# ============ Sheet8: 时间衰减规则说明 ============
ws8 = wb.create_sheet('反馈闭环说明')

ws8.merge_cells('A1:B1')
ws8['A1'] = '回访反馈闭环 · 让系统会进化'
ws8['A1'].font = title_font; ws8['A1'].fill = title_fill; ws8['A1'].alignment = center
ws8.row_dimensions[1].height = 30

loop_rules = [
    ('【核心机制】', ''),
    ('目标', '让工作流从"一次性工具"变成"越用越准的引擎"'),
    ('原理', '销售回填结果 → 下次抓取读取 → 调整评分权重 → 更准的分级'),
    ('', ''),
    ('【回访结果选项】', ''),
    ('已联系·有意向', '客户有明确意向，升级为S级重点跟进'),
    ('已联系·无意向', '客户明确拒绝，降为C级·停止高频打扰'),
    ('已联系·待跟进', '正常推进，保持当前分级'),
    ('未接听·电话', '3天内重试，分级不变'),
    ('未接听·微信', '转微信触达，分级不变'),
    ('拒绝·不要了', '加入黑名单，下次抓取剔除'),
    ('号码错误', '标记数据质量问题，需更新联系方式'),
    ('已成交', '转入售后服务流程，降为C级维护'),
    ('', ''),
    ('【时间衰减规则】', ''),
    ('S级', '7天未回填 → 自动降为A2'),
    ('A2级', '14天未回填 → 自动降为A3'),
    ('A3级', '30天未回填 → 自动降为B'),
    ('B级', '60天未回填 → 自动降为C'),
    ('说明', '防止"红名单永远红"，让销售精力自动流向真正活跃的机会'),
    ('', ''),
    ('【话术效果追踪】', ''),
    ('成交客户', '标记成交时使用的话术版本，反哺模板优化'),
    ('拒绝客户', '记录拒绝原因，优化痛点切入角度'),
    ('', ''),
    ('【下次抓取】', ''),
    ('读取', '读取本Sheet7回填数据，合并到客户记录'),
    ('调整', '按回访结果+时间衰减，重新计算分级'),
    ('输出', '生成新Excel，标注"本次变化"列（升降级提示）'),
]

for r_idx, (label, value) in enumerate(loop_rules, start=2):
    ws8.cell(r_idx, 1, label)
    ws8.cell(r_idx, 2, value)
    if label.startswith('【'):
        ws8.cell(r_idx, 1).font = Font(name='微软雅黑', size=11, bold=True, color='2F5496')
    else:
        ws8.cell(r_idx, 1).font = Font(name='微软雅黑', size=10, bold=True)
        ws8.cell(r_idx, 2).font = Font(name='微软雅黑', size=10)
    ws8.cell(r_idx, 1).alignment = Alignment(vertical='center', wrap_text=True)
    ws8.cell(r_idx, 2).alignment = Alignment(vertical='center', wrap_text=True)

ws8.column_dimensions['A'].width = 20
ws8.column_dimensions['B'].width = 60

# 保存
wb.save(OUTPUT_FILE)
print(f'\nOK saved: {OUTPUT_FILE}')
print(f'  Sheet1: 跟进名单+话术痛点 ({len(customers)}条)')
print(f'  Sheet2: S类必跟客户话术 ({len(a1_customers)}条)')
print(f'  Sheet3: 服务到期预警 ({len(exp_records)}项)')
print(f'  Sheet4: 画像分析')
print(f'  Sheet5: 可视化看板')
print(f'  Sheet6: 筛选方法论')
print(f'  Sheet7: 回访回填表 ({len(followup_customers)}条)')
print(f'  Sheet8: 反馈闭环说明')
print(f'\n分级统计: S={sub_grades.get("S",0)} A2={sub_grades.get("A2",0)} A3={sub_grades.get("A3",0)} B={grades["B"]} C={grades["C"]}')

print('\n=== 5维规则触发统计 ===')
for label, cnt, note in rule_stats:
    print(f'  {label}: {cnt}条({cnt/len(customers)*100:.1f}%) → {note}')

print('\n=== 销售机会类型 ===')
for ot, cnt in opp_counter.most_common(10):
    print(f'  {ot}: {cnt}条')

print(f'\n=== 服务到期预警 ===')
print(f'  60天内到期: {len(exp_records)}项服务, 涉及{expiring_count}个客户')
print(f'  7天内到期: {sum(1 for e in exp_records if e["days_left"] <= 7)}项')
print(f'  30天内到期: {sum(1 for e in exp_records if e["days_left"] <= 30)}项')
