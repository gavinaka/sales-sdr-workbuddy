#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
线索池SDR看板 v2.0 - 15年销售专家视角
=================================================
核心改进：
  1. 线索评分分级模型（L1-L6 → S/A2/A3/B/C）
  2. 默认过滤已成交（只看未成交=有销售价值）
  3. 客户画像（来源关键词→行业推断→痛点识别）
  4. 精准产品推荐（秦丝37产品×画像匹配）
  5. 销售话术生成（可直接念的开场白+跟进话术）
  6. 跟进紧迫度+建议动作
  7. 深蓝专业UI（销售总监工作台风格）
  8. 全维度筛选+自定义日期范围

数据源：石摩「销售部线索跟进6.30 787」
       小红书1组线索表 + 线索跟进表
"""
import json, os, re, sys, io, math
from collections import Counter
from datetime import datetime, timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_FILE = os.path.join(SCRIPT_DIR, 'shimo_raw_data', 'all_sheets_full.json')
OUTPUT_HTML = os.path.join(SCRIPT_DIR, '线索池SDR看板v2.html')

NOW = datetime.now()

# ================================================================
# 秦丝产品知识库（37种服务·与generate_chengdu_v3.py同步）
# ================================================================
QINSILK_PRODUCTS = {
    # 核心系统
    '进销存会员': {'cat': '核心系统', 'tier': '入门', 'desc': '进销存基础，适合单店起步', 'price_range': '¥680-1280/年'},
    '进销存专业版': {'cat': '核心系统', 'tier': '中端', 'desc': '进销存+商品管理+库存预警+欠货统计', 'price_range': '¥1680-2680/年'},
    '生意通会员': {'cat': '核心系统', 'tier': '入门', 'desc': '批发订货基础功能', 'price_range': '¥680-1280/年'},
    '生意通专业版': {'cat': '核心系统', 'tier': '中端', 'desc': '批发订货+采购管理+财务报表', 'price_range': '¥1680-2980/年'},
    '生意通高级版': {'cat': '核心系统', 'tier': '高端', 'desc': '多门店+采购+财务+员工权限，连锁首选', 'price_range': '¥3680-5980/年'},
    # 线上渠道
    '销货宝微商城标准版': {'cat': '线上渠道', 'tier': '入门', 'desc': '微信小程序商城+商品上架+在线支付', 'price_range': '¥980-1680/年'},
    '销货宝微商城基础版': {'cat': '线上渠道', 'tier': '中端', 'desc': '微商城+基础营销插件', 'price_range': '¥1980-2980/年'},
    '销货宝微商城专业版': {'cat': '线上渠道', 'tier': '高端', 'desc': '微商城+营销+分销+直播全渠道', 'price_range': '¥2980-4980/年'},
    '专属品牌小程序': {'cat': '线上渠道', 'tier': '中端', 'desc': '独立品牌小程序+自定义装修', 'price_range': '¥1980-3980/年'},
    # 营销工具
    '限时折扣促单宝': {'cat': '营销工具', 'tier': '入门', 'desc': '限时折扣+会员价+阶梯定价', 'price_range': '¥280-480/年'},
    '限时秒杀促单宝': {'cat': '营销工具', 'tier': '入门', 'desc': '秒杀活动+库存锁定+倒计时', 'price_range': '¥280-480/年'},
    '批量推款宝': {'cat': '营销工具', 'tier': '入门', 'desc': '批量推款给客户在线选款', 'price_range': '¥380-680/年'},
    '直播卖货': {'cat': '营销工具', 'tier': '中端', 'desc': '直播带货+引流到店+互动抽奖', 'price_range': '¥680-1280/年'},
    '微信自动化经营': {'cat': '营销工具', 'tier': '中端', 'desc': '自动加好友+群发+朋友圈营销', 'price_range': '¥580-980/年'},
    # 会员运营
    '专属微信会员卡': {'cat': '会员运营', 'tier': '中端', 'desc': '微信会员卡+积分+储值+会员画像', 'price_range': '¥680-1280/年'},
    '会员积分充值': {'cat': '会员运营', 'tier': '入门', 'desc': '会员积分+消费抵扣+积分商城', 'price_range': '¥380-680/年'},
    # 硬件
    '慧店宝': {'cat': '硬件收银', 'tier': '中端', 'desc': '收银终端+扫码+打印一体', 'price_range': '¥1280-1980'},
    '慧店宝大屏收银端': {'cat': '硬件收银', 'tier': '高端', 'desc': '大屏收银终端高效收银', 'price_range': '¥1980-2980'},
    # AI工具
    'AI绘图': {'cat': 'AI工具', 'tier': '入门', 'desc': 'AI自动绘图+智能抠图+商品图生成', 'price_range': '¥280-580/年'},
    '以图搜图': {'cat': 'AI工具', 'tier': '入门', 'desc': '图片搜索商品快速找款', 'price_range': '¥180-380/年'},
    # 其他
    '门店': {'cat': '门店扩展', 'tier': '中端', 'desc': '多门店统一管理+独立库存', 'price_range': '¥380/店/年'},
    '商家名片': {'cat': '品牌展示', 'tier': '入门', 'desc': '电子名片+商品展示+一键拨号', 'price_range': '免费'},
    '企业微信客户助手': {'cat': '私域运营', 'tier': '中端', 'desc': '企微客户管理+SOP流程', 'price_range': '¥680-1280/年'},
}

# ================================================================
# 行业推断库（从来源/备注关键词→行业→推荐产品）
# ================================================================
INDUSTRY_KEYWORD_MAP = [
    # 核心行业（秦丝最擅长·高转化）
    ('服装|女装|男装|童装|鞋帽|服饰|穿搭|款式|尺码|SKU|换季|吊牌|标牌', '服装鞋帽', 5,
     ['批量推款宝','AI绘图','销货宝微商城专业版','进销存专业版'],
     ['款式多SKU难管','换季库存积压','颜色尺码组合爆炸']),
    # 食品
    ('食品|水果|生鲜|烘焙|蛋糕|零食|饮料|奶茶|保质期|临期', '食品生鲜', 4,
     ['进销存专业版','限时秒杀促单宝'],
     ['保质期短损耗大','批次追溯需求','临期快速清仓']),
    # 美妆
    ('美妆|化妆品|代购|护肤|彩妆|面膜|复购|积分', '美妆代购', 4,
     ['专属微信会员卡','会员积分充值','销货宝微商城专业版'],
     ['会员复购运营','代购多渠道管理','批次临期管理']),
    # 母婴
    ('母婴|童装|宝宝|儿童|玩具|孕产', '母婴玩具', 4,
     ['专属微信会员卡','销货宝微商城基础版'],
     ['会员复购成长周期','安全合规追溯']),
    # 数码家电
    ('数码|手机|配件|家电|电子|序列号|IMEI', '数码配件', 4,
     ['进销存专业版','批量推款宝'],
     ['SKU繁多型号复杂','价格波动快调价频繁']),
    # 商超便利
    ('超市|便利店|商超|收银|快消|排队|储值', '商超便利', 4,
     ['慧店宝','专属微信会员卡','限时折扣促单宝'],
     ['收银效率低排队','快消高频周转','会员储值需求']),
    # 餐饮
    ('餐饮|餐厅|饭店|火锅|烧烤|外卖|菜单', '餐饮', 3,
     ['进销存专业版','慧店宝'],
     ['原材料库存管理','收银效率','成本核算']),
    # 日用百货
    ('百货|日用|杂货|日用品|小商品', '日用百货', 3,
     ['进销存专业版','销货宝微商城基础版'],
     ['SKU多而杂','库存盘点繁琐','低毛利跑量']),
    # 家居家装
    ('家居|家纺|建材|家具|装饰|窗帘|床上用品', '家居家纺', 3,
     ['进销存专业版','专属微信会员卡'],
     ['SKU多花色规格','换季库存','会员复购']),
    # 五金汽配
    ('五金|机械|汽修|汽配|配件|维修|批发订货', '五金汽配', 3,
     ['生意通专业版','批量推款宝'],
     ['规格型号复杂','B2B批发订货','库存价值高']),
    # 宠物
    ('宠物|猫粮|狗粮|宠物店|宠物美容', '宠物用品', 3,
     ['专属微信会员卡','销货宝微商城基础版'],
     ['会员复购宠物档案','SKU多','积分运营']),
    # 烟酒茶叶
    ('烟酒|茶叶|白酒|红酒|防伪|溯源', '烟酒茶', 4,
     ['进销存专业版','专属微信会员卡'],
     ['防伪溯源需求','高价值商品库存','批次年份管理']),
    # 珠宝饰品
    ('珠宝|首饰|饰品|黄金|钻石|翡翠|VIP|高价值', '珠宝饰品', 4,
     ['专属微信会员卡','进销存专业版'],
     ['高价值防伪','会员VIP运营','定制订单管理']),
]

# ================================================================
# 渠道质量评分（基于实际转化数据反推）
# ================================================================
CHANNEL_QUALITY = {
    '小红书SEM':        {'quality': 5, 'conv_rate': 6.1, 'note': '搜索意向强·精准度高'},
    '小红书私信/咨询':  {'quality': 4, 'conv_rate': 5.8, 'note': '主动咨询·意向明确'},
    '小红书店铺':      {'quality': 4, 'conv_rate': 5.0, 'note': '店铺转化路径'},
    '抖音SEM':          {'quality': 5, 'conv_rate': 5.0, 'note': '搜索广告·精准'},
    '抖音咨询':         {'quality': 4, 'conv_rate': 4.5, 'note': '主动私信咨询'},
    '视频号':           {'quality': 3, 'conv_rate': 3.5, 'note': '视频号生态·需培育'},
}

# ================================================================
# 来源账号画像（从来源名称推断业务类型/规模）
# ================================================================
SOURCE_PROFILES = {
    # 服装类来源（最高质量）
    '小青在做服装':            {'industry': '服装鞋帽', 'scale': '中', 'intent': '高', 'boost': 2},
    '阿秋服装店':             {'industry': '服装鞋帽', 'scale': '中小', 'intent': '高', 'boost': 2},
    '阿秋服装创业记':         {'industry': '服装鞋帽', 'scale': '初创', 'intent': '高', 'boost': 1},
    '七七服装创业':           {'industry': '服装鞋帽', 'scale': '初创', 'intent': '高', 'boost': 1},
    '小月服装创业中':         {'industry': '服装鞋帽', 'scale': '初创', 'intent': '中', 'boost': 1},
    '小衣':                   {'industry': '服装鞋帽', 'scale': '初创', 'intent': '中', 'boost': 1},
    '小桔服装连锁':          {'industry': '服装鞋帽', 'scale': '多店', 'intent': '高', 'boost': 3},
    '小桔服装版':            {'industry': '服装鞋帽', 'scale': '中', 'intent': '中', 'boost': 1},
    '服装小衣':              {'industry': '服装鞋帽', 'scale': '初创', 'intent': '中', 'boost': 1},
    '服装爆单日记':          {'industry': '服装鞋帽', 'scale': '中', 'intent': '高', 'boost': 2},
    # 秦丝官方（品牌认知·已了解产品）
    '秦丝进销存app':         {'industry': '通用', 'scale': '未知', 'intent': '中', 'boost': 1, 'known_brand': True},
    '秦丝进销存':            {'industry': '通用', 'scale': '未知', 'intent': '中', 'boost': 1, 'known_brand': True},
    '秦丝科技丨服装收银系统': {'industry': '服装鞋帽', 'scale': '未知', 'intent': '高', 'boost': 2, 'known_brand': True},
    '秦丝科技企业店':        {'industry': '通用', 'scale': '未知', 'intent': '中', 'boost': 1, 'known_brand': True},
    # 创业类（通用但有意向）
    '勤勤创业版':            {'industry': '通用', 'scale': '初创', 'intent': '中', 'boost': 1},
    '你的创业闺蜜糖糖':      {'industry': '通用', 'scale': '初创', 'intent': '中', 'boost': 1},
    '丝丝的创业手账':        {'industry': '通用', 'scale': '初创', 'intent': '中', 'boost': 1},
    '阿棠':                  {'industry': '通用', 'scale': '未知', 'intent': '中', 'boost': 1},
    '双':                    {'industry': '通用', 'scale': '未知', 'intent': '低', 'boost': 0},
    '三薪':                  {'industry': '通用', 'scale': '未知', 'intent': '低', 'boost': 0},
    '若若':                  {'industry': '通用', 'scale': '未知', 'intent': '中', 'boost': 1},
}

# ================================================================
# 拒绝词库（明确无需求→降级为C或剔除）
# ================================================================
REJECT_PATTERNS = [
    r'不要了', r'不需要', r'不用了', r'没兴趣', r'暂时不',
    r'不考虑', r'已经用了', r'已经有.*系统', r'用.*别的',
    r'挂断', r'不接', r'打不通', r'联系不上', r'拉黑',
    r'删除', r'退订', r'投诉',
]

# 高意向信号
INTENT_HIGH = [
    r'咨询', r'想了解', r'多少钱', r'价格', r'怎么买', r'购买',
    r'演示', r'试用', r'功能', r'小程序', r'会员', r'收银',
    r'入库自动定价', r'碰碰贴', r'问.*系统', r'问.*价格',
]
INTENT_MEDIUM = [
    r'加微信', r'加了', r'已添加', r'通过', r'待通过',
    r'发SOP', r'发了', r'发送', r'介绍',
]


def parse_date(s):
    """解析各种日期格式→ YYYY-MM-DD"""
    if not s or not str(s).strip(): return ''
    s = str(s).strip()
    m = re.match(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', s)
    if m: return f'{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}'
    m = re.match(r'(\d{1,2})[月./\-](\d{1,2})', s)
    if m: return f'{NOW.year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}'
    return s


def calc_lead_age(assign_date_str):
    """计算线索年龄（天）"""
    if not assign_date_str: return None
    d = parse_date(assign_date_str)
    try:
        dt = datetime.strptime(d[:10], '%Y-%m-%d')
        return max(0, (NOW - dt).days)
    except:
        return None


def detect_industry_from_text(text):
    """从文本推断行业"""
    if not text: return None, []
    text_lower = text.lower()
    for keywords, industry, score, recommends, pains in INDUSTRY_KEYWORD_MAP:
        if re.search(keywords, text):
            return industry, (score, recommends, pains)
    return None, []


def check_reject_signals(text):
    """检测拒绝信号"""
    if not text: return False, ''
    for p in REJECT_PATTERNS:
        m = re.search(p, text)
        if m:
            return True, m.group()
    return False, ''


def detect_intent_level(lead):
    """检测意向等级（从备注+4次跟进记录综合判断）"""
    texts = ' '.join([
        lead.get('备注', ''),
        lead.get('客户备注', ''),
        lead.get('跟进情况（第一次）', ''),
        lead.get('跟进情况（第二次）', ''),
        lead.get('跟进情况（第三次）', ''),
        lead.get('跟进情况（第四次）', '')
    ])
    
    # 检查拒绝信号
    rejected, reject_word = check_reject_signals(texts)
    if rejected:
        return 'rejected', reject_word
    
    # 高意向
    for p in INTENT_HIGH:
        if re.search(p, texts):
            return 'high', p
    
    # 中意向
    for p in INTENT_MEDIUM:
        if re.search(p, texts):
            return 'medium', p
    
    # 低意向/待判断
    if texts.strip() and len(texts.strip()) > 5:
        return 'low', ''
    
    return 'unknown', ''


def generate_profile(lead):
    """
    为每条线索生成完整画像：
      - 推断行业（从来源+备注关键词）
      - 意向等级
      - 规模推测
      - 推荐产品列表
      - 痛点识别
    """
    source = lead.get('来源', '')
    note = lead.get('备注', '') or ''
    note2 = lead.get('客户备注', '') or ''
    all_text = f'{source} {note} {note2}'
    
    # 1. 来源画像
    src_prof = SOURCE_PROFILES.get(source, {})
    known_brand = src_prof.get('known_brand', False)
    
    # 2. 行业推断
    industry, ind_info = detect_industry_from_text(all_text)
    if not industry and src_prof:
        industry = src_prof.get('industry', '')
        ind_info = (3, [], [])
    
    ind_score = ind_info[0] if ind_info else 1
    ind_recommends = ind_info[1] if len(ind_info) > 1 else []
    ind_pains = ind_info[2] if len(ind_info) > 2 else []
    
    # 3. 意向检测
    intent_level, intent_signal = detect_intent_level(lead)
    
    # 4. 规模推测
    scale = src_prof.get('scale', '未知')
    
    # 5. 产品推荐
    products = list(ind_recommends) if ind_recommends else []
    # 如果已知秦丝品牌，加推核心产品
    if known_brand:
        core = ['进销存专业版']
        for c in core:
            if c not in products:
                products.insert(0, c)
    # 如果没有行业匹配，推通用产品
    if not products:
        products = ['进销存专业版', '进销存会员']
    
    # 补充产品详情
    product_details = []
    for pname in products:
        if pname in QINSILK_PRODUCTS:
            product_details.append({
                'name': pname,
                **QINSILK_PRODUCTS[pname]
            })
    
    profile = {
        'industry': industry or '未识别',
        'industry_score': ind_score,
        'scale': scale,
        'intent_level': intent_level,
        'intent_signal': intent_signal,
        'known_brand': known_brand,
        'pains': ind_pains,
        'products': product_details[:5],  # 最多推荐5个
        'source_boost': src_prof.get('boost', 0),
    }
    
    return profile


def score_lead(lead, profile):
    """
    线索评分模型 v2.0（6维度·总分30分→分级）

    L1 意向强度 (5分): high=5 / medium=3 / low=2 / unknown=1 / rejected=0
    L2 渠道质量 (5分): 从CHANNEL_QUALITY取值
    L3 来源精准度 (5分): 来源画像boost映射 + 行业匹配
    L4 跟进阶段 (5分): 基于跟进记录和状态判断
    L5 线索新鲜度 (5分): 分配时间→年龄
    L6 可触达性 (5分): 手机号有效性+联系方式丰富度
    """
    scores = {}
    reasons = []
    
    channel = lead.get('渠道', '')
    status = lead.get('跟进状态', '')
    assign_time = lead.get('分配时间', '')
    phone = lead.get('手机号', '')
    other_contact = lead.get('其他联系方式', '')
    level_tag = lead.get('线索级别', '')
    source = lead.get('来源', '')
    
    # ---- L1 意向强度 (5) ----
    intent = profile['intent_level']
    if intent == 'high':
        l1 = 5; reasons.append(f'L1=5(高意向:{profile["intent_signal"]})')
    elif intent == 'medium':
        l1 = 3; reasons.append(f'L1=3(中意向:已建联)')
    elif intent == 'low':
        l1 = 2; reasons.append('L1=2(低意向:有记录但无明确信号)')
    elif intent == 'rejected':
        l1 = 0; reasons.append(f'L1=0(已拒绝:{profile["intent_signal"]})')
    else:
        l1 = 1; reasons.append('L1=1(未知:无有效跟进记录)')
    scores['L1'] = l1
    
    # ---- L2 渠道质量 (5) ----
    ch_q = CHANNEL_QUALITY.get(channel, {})
    l2 = ch_q.get('quality', 3)
    reasons.append(f'L2={l2}({channel}·转化{ch_q.get("conv_rate","?")}%)')
    scores['L2'] = l2
    
    # ---- L3 来源精准度 (5) ----
    src_boost = profile['source_boost']  # 0~3
    ind_score = profile['industry_score']  # 1~5
    l3 = min(5, 2 + src_boost + (1 if ind_score >= 4 else 0))
    if l3 >= 4:
        reasons.append(f'L3={l3}(精准来源+{profile["industry"]}行业)')
    elif src_boost >= 2:
        reasons.append(f'L3={l3}(优质来源:{source[:10]})')
    else:
        reasons.append(f'L3={l3}(一般来源)')
    scores['L3'] = l3
    
    # ---- L4 跟进阶段 (5) ----
    fu1 = lead.get('跟进情况（第一次）', '') or ''
    fu2 = lead.get('跟进情况（第二次）', '') or ''
    fu3 = lead.get('跟进情况（第三次）', '') or ''
    fu4 = lead.get('跟进情况（第四次）', '') or ''
    
    follow_count = sum(1 for x in [fu1, fu2, fu3, fu4] if x.strip())
    
    # 已有级别标签
    if level_tag:
        if 'S' in level_tag:
            l4 = 5; reasons.append(f'L4=5(已成交/签约级:{level_tag})')
        elif level_tag.startswith('A'):
            l4 = 4; reasons.append(f'L4=4(A级线索:{level_tag})')
        elif level_tag.startswith('B'):
            l4 = 1; reasons.append(f'L4=1(B级:无法建联/{level_tag})')
        else:
            l4 = 2; reasons.append(f'L4=2({level_tag})')
    elif follow_count >= 3:
        l4 = 4; reasons.append(f'L4=4(深度跟进{follow_count}次)')
    elif follow_count >= 2:
        l4 = 3; reasons.append(f'L4=3(持续跟进{follow_count}次)')
    elif follow_count >= 1:
        l4 = 2; reasons.append('L4=2(初次跟进)')
    elif status == '跟进中':
        l4 = 3; reasons.append('L4=3(跟进中状态)')
    else:
        l4 = 1; reasons.append('L4=1(未开始跟进)')
    scores['L4'] = l4
    
    # ---- L5 线索新鲜度 (5) ----
    age = calc_lead_age(assign_time)
    if age is None:
        l5 = 3; reasons.append('L5=3(时间未知)')
    elif age <= 7:
        l5 = 5; reasons.append(f'L5=5(新鲜:{age}天)')
    elif age <= 14:
        l5 = 4; reasons.append(f'L5=4(较新:{age}天)')
    elif age <= 30:
        l5 = 3; reasons.append(f'L5=3(常规:{age}天)')
    elif age <= 60:
        l5 = 2; reasons.append(f'L5=2(偏老:{age}天·需加快)')
    else:
        l5 = 1; reasons.append(f'L5=5(老化:{age}天·紧急)')
        # 超过30天的老线索反而要优先处理——可能流失
        l5 = 4  # 提升权重：老线索不跟就丢了
        reasons[-1] = f'L5=4(偏老:{age}天·有流失风险)'
    scores['L5'] = l5
    lead['_age_days'] = age
    
    # ---- L6 可触达性 (5) ----
    has_phone = bool(phone and len(phone) >= 11 and '*' not in phone)
    has_other = bool(other_contact and other_contact.strip())
    has_wechat = bool(other_contact and ('微信' in other_contact or 'vx' in other_contact.lower()))
    
    if has_wechat:
        l6 = 5; reasons.append('L6=5(有微信·最佳触达)')
    elif has_phone and has_other:
        l6 = 4; reasons.append('L6=4(电话+其他联系方式)')
    elif has_phone:
        l6 = 3; reasons.append('L6=3(仅电话可触达)')
    elif phone and '*' in phone:
        l6 = 2; reasons.append('L6=2(手机号脱敏)')
    else:
        l6 = 1; reasons.append('L6=1(联系方式缺失)')
    scores['L6'] = l6
    
    total = sum(scores.values())
    
    return {
        'scores': scores,
        'total': total,
        'reasons': reasons,
        'follow_count': follow_count,
    }


def grade_lead(score_result, profile, lead):
    """
    分级规则（15年销售经验总结）：

    S级（立即行动）：总≥24 或 (高意向+新鲜≤14天) 或 (已有A/S标签)
    A2级（重点跟进）：总≥19 或 (中意向+有联系方式) 
    A3级（正常跟进）：总≥14 或 (有跟进记录但信号弱)
    B级（低优队列）：总≥9 或 (能联系但意向不明)
    C级（暂缓/淘汰）：总<9 或 明确拒绝 或 无法建联

    返回: {grade, label, color, urgency, action}
    """
    total = score_result['total']
    sc = score_result['scores']
    intent = profile['intent_level']
    age = lead.get('_age_days')
    deal = lead.get('_deal', False)
    level_tag = lead.get('线索级别', '')
    
    # 已成交的直接标记
    if deal:
        return {
            'grade': 'DEAL', 'label': '已成交', 'color': '#27ae60',
            'urgency': '无', 'action': '✅ 已成交·转入客服维护',
            'priority': 0
        }
    
    # 明确拒绝
    if intent == 'rejected':
        return {
            'grade': 'C', 'label': '已拒绝', 'color': '#95a5a6',
            'urgency': '放弃', 'action': '❌ 已明确拒绝·移入公海池',
            'priority': 0
        }
    
    # S级触发条件
    s_triggers = []
    if total >= 24: s_triggers.append(f'高分{total}')
    if intent == 'high' and age is not None and age <= 14: s_triggers.append('高意向+新鲜')
    if level_tag and 'S' in level_tag: s_triggers.append(f'原始标签{level_tag}')
    if sc.get('L1',0) == 5 and sc.get('L5',0) >= 4: s_triggers.append('高意向+新鲜')
    
    if s_triggers:
        return {
            'grade': 'S', 'label': '🔥S-立即', 'color': '#e74c3c',
            'urgency': '今日必跟', 'action': '⚡ 立即回电/微信！高意向+新鲜度好，窗口期短',
            'priority': 5
        }
    
    # A2级
    a2_triggers = []
    if total >= 19: a2_triggers.append(f'高分{total}')
    if intent in ('high','medium') and sc.get('L6',0) >= 3: a2_triggers.append('有意向+可触达')
    if intent == 'medium' and age is not None and age <= 21: a2_triggers.append('中意向+3周内')
    if sc.get('L1',0) >= 4 and sc.get('L4',0) >= 3: a2_triggers.append('高意向+已多次跟进')
    
    if a2_triggers:
        return {
            'grade': 'A2', 'label': '⭐A2-重点', 'color': '#f39c12',
            'urgency': '3天内', 'action': '📞 48小时内二次触达，推动演示/试用',
            'priority': 4
        }
    
    # A3级
    if total >= 14 or (score_result['follow_count'] >= 1 and intent != 'low') or (level_tag and 'A' in level_tag):
        return {
            'grade': 'A3', 'label': '●A3-正常', 'color': '#3498db',
            'urgency': '本周内', 'action': '📋 本周完成一次有效沟通，确认需求',
            'priority': 3
        }
    
    # B级
    if total >= 9 or (sc.get('L6',0) >= 2):
        return {
            'grade': 'B', 'label': '○B-低优', 'color': '#95a5a6',
            'urgency': '有空再看', 'action': '🔄 有空时批量外呼，筛选出有需求的',
            'priority': 2
        }
    
    # C级
    return {
        'grade': 'C', 'label': '△C-暂缓', 'color': '#bdc3c7',
        'urgency': '暂缓', 'action': '⏸️ 联系方式不全或完全无信号，暂缓处理',
        'priority': 1
    }


def generate_script(lead, profile, grade_info):
    """
    生成销售话术（可直接念给客户的）
    基于：行业+意向+来源渠道+推荐产品+跟进记录
    """
    industry = profile['industry']
    intent = profile['intent_level']
    products = profile['products']
    pains = profile['pains']
    known_brand = profile['known_brand']
    source = lead.get('来源', '')[:20]
    channel = lead.get('渠道', '')
    
    fu1 = lead.get('跟进情况（第一次）', '') or ''
    fu2 = lead.get('跟进情况（第二次）', '') or ''
    
    # 开场白模板
    if known_brand:
        opening = (
            "您好！我是秦丝的客户顾问，之前看到您在小红书上"
            f"咨询过我们的{products[0]['name'] if products else '进销存'}系统，"
            "今天特意来回访一下您目前的使用情况或者还有哪些需要了解的功能？"
        )
    elif industry != '未识别' and industry != '通用':
        opening = (
            f"您好！我是秦丝的顾问，了解到您做【{industry}】行业的，"
            "我们专门针对这个行业有一套成熟的解决方案，"
            f"像{'、'.join([p['name'] for p in products[:2]])}这些功能都是为您量身定制的。"
            "不知道您现在是用什么方式在管理库存和开单的呢？"
        )
    else:
        opening = (
            "您好！我是秦丝的顾问，看到您之前咨询过我们，"
            "想了解一下您现在开店主要遇到的问题是什么？"
            "比如是库存记不清楚、开单太慢还是会员不好管理？"
        )
    
    # 意向回应
    if intent == 'high':
        response = "客户表现出明确兴趣（询问价格/功能），直接进入产品演示和报价环节。"
    elif intent == 'medium':
        response = "客户已有建联但未深入，需要进一步挖掘痛点和预算。"
    elif intent == 'low':
        response = "客户反应冷淡，先发资料+案例，3天后回访。"
    elif intent == 'rejected':
        response = "⚠️ 客户已表达拒绝，不建议继续骚扰。如需再激活建议间隔30天以上。"
    else:
        response = "首次接触，以询问和倾听为主，挖掘真实需求。"
    
    # 痛点切入
    pain_hook = ""
    if pains:
        pain_hook = f"痛点切入：「{pains[0]}」是我们服务的{industry}客户最常提到的痛点。"
    
    # 产品推荐语
    product_pitch = ""
    if products:
        top3 = products[:3]
        pitch_parts = [f"【{p['name']}】- {p.get('desc','')}" for p in top3 if p.get('desc')]
        product_pitch = "推荐方案：" + "；".join(pitch_parts)
    
    # 下一步建议动作
    action = grade_info.get('action', '')
    
    # 组合完整话术
    script = {
        'opening': opening,
        'response_strategy': response,
        'pain_hook': pain_hook,
        'product_pitch': product_pitch,
        'next_action': action,
        'full_script': (
            f"=== 可直接使用的话术 ===\n\n"
            f"📞 开场白:\n「{opening}」\n\n"
            f"💡 {pain_hook}\n\n"
            f"📦 {product_pitch}\n\n"
            f"🎯 策略: {response}\n\n"
            f"⏭️ 动作: {action}"
        ),
    }
    
    return script


# ================================================================
# 数据加载
# ================================================================
print('=' * 60)
print('线索池看板 v2.0 - 15年销售专家视角')
print('=' * 60)

print('\n[1/4] 加载原始数据...')
with open(RAW_FILE, 'r', encoding='utf-8') as f:
    RAW = json.load(f)

# 解析小红书1组线索表
print('[2/4] 解析线索表...')
raw1 = RAW.get('小红书1组线索表', {}).get('data', '')
lines1 = raw1.split('\n')
HDR = [h.strip() for h in lines1[9].split('\t')]

leads = []
for ln in lines1[10:]:
    parts = ln.split('\t')
    if len(parts) < len(HDR): continue
    record = {HDR[i]: (parts[i].strip() if i < len(parts) else '') for i in range(len(HDR))}
    
    phone = record.get('手机号', '').strip()
    if len(phone) < 8: continue
    
    # 成交标记
    ds = str(record.get('是否成交', '')).strip().upper()
    record['_deal'] = ds == 'TRUE'
    
    # 成交金额
    am = record.get('成交金额', '').replace(',', '').replace(' ', '')
    try: record['_amt'] = float(am)
    except: record['_amt'] = 0
    
    record['_src'] = 'XHS'
    record['_ad'] = parse_date(record.get('分配时间', ''))
    record['_dd'] = parse_date(record.get('成交时间', ''))
    
    leads.append(record)

print(f'  小红书线索表: {len(leads)} 条')

# 解析线索跟进表（补充）
raw2 = RAW.get('线索跟进表', {}).get('data', '')
added = 0
if raw2:
    lines2 = raw2.split('\n')
    tc = Counter(x.count('\t') for x in lines2)
    dtc = tc.most_common(1)[0][0]
    seen_phones = set(l.get('手机号', '') for l in leads)
    
    for ln in lines2:
        if ln.count('\t') != dtc: continue
        p = ln.split('\t')
        ph = p[1].strip() if len(p) > 1 else ''
        if len(ph) < 8 or ph in seen_phones: continue
        
        r2 = {
            '手机号': ph,
            '昵称': p[0].strip() if len(p) > 0 else '',
            '创建时间': p[2].strip() if len(p) > 2 else '',
            '渠道': p[6].strip() if len(p) > 6 else '',
            '分配部门': p[8].strip() if len(p) > 8 else '',
            '分配顾问': p[9].strip() if len(p) > 9 else '',
            '跟进状态': '',
            '分配时间': '',
            '分配人': '',
            '是否成交': '',
            '成交时间': '',
            '成交金额': '',
            '其他联系方式': '',
            '线索级别': '',
            '备注': '',
            '来源': '',
            '跟进情况（第一次）': '',
            '跟进情况（第二次）': '',
            '跟进情况（第三次）': '',
            '跟进情况（第四次）': '',
            '_src': 'FU', '_deal': False, '_amt': 0,
        }
        leads.append(r2)
        added += 1

print(f'  跟进表补充: {added} 条')
print(f'  总计: {len(leads)} 条')

# ================================================================
# 核心分析：评分→分级→画像→话术
# ================================================================
print('[3/4] 执行评分分级+画像+话术...')

stats = {'S': 0, 'A2': 0, 'A3': 0, 'B': 0, 'C': 0, 'DEAL': 0}
active_count = 0  # 未成交的有效线索
for idx, lead in enumerate(leads):
    # 画像生成
    profile = generate_profile(lead)
    lead['_profile'] = profile
    
    # 评分
    score_result = score_lead(lead, profile)
    lead['_score'] = score_result
    
    # 分级
    grade_info = grade_lead(score_result, profile, lead)
    lead['_grade'] = grade_info
    
    # 话术
    script = generate_script(lead, profile, grade_info)
    lead['_script'] = script
    
    # 统计
    g = grade_info['grade']
    stats[g] = stats.get(g, 0) + 1
    if not lead.get('_deal') and g != 'DEAL':
        active_count += 1
    
    if (idx + 1) % 500 == 0:
        print(f'  处理进度: {idx+1}/{len(leads)}')

print(f'\n  分级分布:')
for g in ['S', 'A2', 'A3', 'B', 'C', 'DEAL']:
    print(f'    {g}: {stats.get(g,0)} 条')

print(f'  有效未成交线索: {active_count} 条')

# ================================================================
# 维度统计（用于前端筛选下拉框）
# ================================================================
print('[4/4] 生成维度统计...')
by_status = Counter(l.get('跟进状态', '') or '?' for l in leads)
by_dept = Counter(l.get('分配部门', '未分配') for l in leads)
by_channel = Counter(l.get('渠道', '?') for l in leads)
by_level = Counter(l.get('线索级别', '') for l in leads)
by_counselor = Counter(l.get('分配顾问', '') for l in leads)
by_source = Counter(l.get('来源', '') for l in leads)
by_grade = Counter(l['_grade']['grade'] for l in leads)
by_industry = Counter(l['_profile']['industry'] for l in leads)
by_intent = Counter(l['_profile']['intent_level'] for l in leads)

ch_conv = {}
for ch, cn in by_channel.items():
    d = sum(1 for l in leads if l.get('渠道', '') == ch and l.get('_deal'))
    ch_conv[ch] = {'t': cn, 'd': d, 'r': round(d/cn*100, 1) if cn else 0}

dp_conv = {}
for dp, dn in by_dept.items():
    d = sum(1 for l in leads if l.get('分配部门', '') == dp and l.get('_deal'))
    dp_conv[dp] = {'t': dn, 'd': d, 'r': round(d/dn*100, 1) if dn else 0}

SUMM = {
    'total': len(leads),
    'deals': stats.get('DEAL', 0),
    'active': active_count,
    'rate': round(stats.get('DEAL', 0)/len(leads)*100, 1) if leads else 0,
    'grades': dict(stats),
    'channels': dict(by_channel),
    'depts': dict(by_dept),
    'status': dict(by_status),
    'levels': dict(by_level),
    'sources': dict(by_source.most_common(30)),
    'counselors': dict(by_counselor.most_common(25)),
    'ch_conv': ch_conv,
    'dp_conv': dp_conv,
    'grade_dist': dict(by_grade),
    'industry_dist': dict(by_industry),
    'intent_dist': dict(by_intent),
}

# 准备精简数据（去掉冗余字段减小体积）
LEADS_LIGHT = []
for l in leads:
    light = {
        # 基本信息
        '跟进状态': l.get('跟进状态', ''),
        '分配时间': l.get('分配时间', ''),
        '分配人': l.get('分配人', ''),
        '是否成交': l.get('是否成交', ''),
        '成交时间': l.get('成交时间', ''),
        '成交金额': l.get('成交金额', ''),
        '手机号': l.get('手机号', ''),
        '其他联系方式': l.get('其他联系方式', ''),
        '线索级别': l.get('线索级别', ''),
        '备注': l.get('备注', ''),
        '渠道': l.get('渠道', ''),
        '来源': l.get('来源', ''),
        '分配部门': l.get('分配部门', ''),
        '分配顾问': l.get('分配顾问', ''),
        '跟进情况（第一次）': l.get('跟进情况（第一次）', ''),
        '跟进情况（第二次）': l.get('跟进情况（第二次）', ''),
        '跟进情况（第三次）': l.get('跟进情况（第三次）', ''),
        '跟进情况（第四次）': l.get('跟进情况（第四次）', ''),
        # 计算字段
        '_deal': l.get('_deal', False),
        '_amt': l.get('_amt', 0),
        '_ad': l.get('_ad', ''),
        '_dd': l.get('_dd', ''),
        '_src': l.get('_src', ''),
        '_age_days': l.get('_age_days'),
        # 画像
        '_ind': l['_profile']['industry'],
        '_isc': l['_profile']['industry_score'],
        '_itl': l['_profile']['intent_level'],
        '_knb': l['_profile']['known_brand'],
        '_scl': l['_profile']['scale'],
        '_pns': l['_profile']['pains'],
        '_pds': [{'n':p['name'],'c':p.get('cat',''),'t':p.get('tier',''),'d':p.get('desc',''),'pr':p.get('price_range','')} for p in l['_profile'].get('products',[])],
        # 评分
        '_sc': l['_score']['total'],
        '_scd': l['_score']['scores'],
        '_scr': l['_score']['reasons'],
        '_fc': l['_score']['follow_count'],
        # 分级
        '_g': l['_grade']['grade'],
        '_gl': l['_grade']['label'],
        '_gc': l['_grade']['color'],
        '_gu': l['_grade']['urgency'],
        '_ga': l['_grade']['action'],
        '_gp': l['_grade']['priority'],
        # 话术
        '_op': l['_script']['opening'],
        '_rs': l['_script']['response_strategy'],
        '_ph': l['_script']['pain_hook'],
        '_pp': l['_script']['product_pitch'],
        '_fs': l['_script']['full_script'],
    }
    LEADS_LIGHT.append(light)

JL = json.dumps(LEADS_LIGHT, ensure_ascii=False)
JS = json.dumps(SUMM, ensure_ascii=False)

TS = NOW.strftime('%Y-%m-%d %H:%M')
print(f'\n数据准备完毕: {len(LEADS_LIGHT)}条, JSON大小约 {len(JL)//1024}KB')

# ================================================================
# HTML 生成 - 专业深蓝销售工作台风格
# ================================================================

HTML = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>🎯 线索池SDR看板 v2 | 销售机会中心</title>
<style>
:root{
  --bg:#f0f2f5;--cb:#fff;--pr:#1a73e8;--pd:#1558d0;--tx:#1a1a1a;
  --tl:#666;--bd:#e0e4e7;--rd:#e53935;--gn:#2e7d32;--og:#ef6c00;
  --bl:#1976d2;--sh:0 2px 16px rgba(0,0,0,.08);--rad:12px;
  --s-bg:#fef2f2;--s-tx:#c62828;--a2-bg:#fff8e1;--a2-tx:#e65100;
  --a3-bg:#e3f2fd;--a3-tx:#1565c0;--b-bg:#f5f5f5;--b-tx:#616161;
  --c-bg:#eceff1;--c-tx:#455a64;--deal-bg:#e8f5e9;--deal-tx:#2e7d32;
}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:var(--bg);color:var(--tx);font-size:14px;line-height:1.55;padding:20px}

/* Header */
.hd{text-align:center;padding:28px 0 18px;margin-bottom:22px;background:linear-gradient(135deg,#1565c0 0%,#1976d2 50%,#1a73e8 100%);color:#fff;border-radius:var(--rad);box-shadow:0 4px 24px rgba(21,101,192,.35)}
.hd h1{font-size:28px;font-weight:700;letter-spacing:2px;text-shadow:0 1px 4px rgba(0,0,0,.15)}
.hd .sub{font-size:13px;opacity:.88;margin-top:6px}
.hd .ver{font-size:11px;opacity:.6;margin-top:4px}

/* KPI Cards */
.cr{display:grid;grid-template-columns:repeat(auto-fit,minmax(175px,1fr));gap:14px;margin-bottom:18px}
.cd{background:var(--cb);border-radius:var(--rad);box-shadow:var(--sh);padding:18px 20px;border-top:4px solid var(--pr);transition:transform .2s,box-shadow .2s;position:relative;overflow:hidden}
.cd:hover{transform:translateY(-3px);box-shadow:0 6px 24px rgba(0,0,0,.12)}
.cd .lb{color:var(--tl);font-size:12.5px;margin-bottom:6px;font-weight:600;text-transform:uppercase;letter-spacing:.5px}
.cd .vl{font-size:32px;font-weight:800;color:var(--pd);line-height:1.1}
.cd .sb{font-size:11.5px;color:var(--tl);margin-top:5px}
.cd.s{border-color:var(--rd)}.cd.s .vl{color:var(--rd)}
.cd.a2{border-color:var(--og)}.cd.a2 .vl{color:var(--og)}
.cd.a3{border-color:var(--bl)}.cd.a3 .vl{color:var(--bl)}
.cd.d{border-color:var(--gn)}.cd.d .vl{color:var(--gn)}

/* Filter Bar */
.fb{background:var(--cb);border-radius:var(--rad);box-shadow:var(--sh);padding:16px 20px;margin-bottom:16px;display:flex;flex-wrap:wrap;gap:10px;align-items:center;border:1px solid var(--bd)}
.fb label{font-size:12.5px;color:var(--tl);font-weight:600;white-space:nowrap}
.fb select,.fb input{border:1px solid var(--bd);border-radius:8px;padding:8px 12px;font-size:13px;background:#fafbfc;outline:none;transition:border .2s}
.fb select:focus,.fb input:focus{border-color:var(--pr);box-shadow:0 0 0 3px rgba(26,115,232,.12)}
.fbtn{background:var(--pr);color:#fff;border:none;border-radius:8px;padding:8px 18px;cursor:pointer;font-size:13px;font-weight:700;transition:background .2s}
.fbtn:hover{background:var(--pd)}
.fbtn.outline{background:transparent;color:var(--pr);border:1.5px solid var(--pr)}
.fbtn.outline:hover{background:var(--pr);color:#fff}

/* Tabs */
.ts{display:flex;gap:2px;margin-bottom:16px;background:var(--cb);border-radius:10px;padding:4px;box-shadow:var(--sh)}
.tb{flex:1;padding:10px 14px;border:none;background:transparent;border-radius:8px;cursor:pointer;font-size:13px;font-weight:700;color:var(--tl);transition:all .25s;text-align:center}
.tb.on{background:var(--pr);color:#fff;box-shadow:0 2px 8px rgba(26,115,232,.3)}
.tb:hover:not(.on){background:#f5f5f5;color:var(--tx)}
.tb .badge{display:inline-block;background:var(--rd);color:#fff;font-size:10.5px;padding:1px 7px;border-radius:10px;margin-left:4px;font-weight:700;vertical-align:middle}

/* Panel */
.pn{display:none}.pn.on{display:block}

/* Table */
.tw{background:var(--cb);border-radius:var(--rad);box-shadow:var(--sh);overflow:hidden}
table.dt{width:100%;border-collapse:collapse;font-size:13px}
.dt th{position:sticky;top:0;z-index:10;background:linear-gradient(#f8f9fa,#eef1f4);color:#444;font-weight:700;padding:12px 10px;text-align:left;white-space:nowrap;cursor:pointer;font-size:12px;border-bottom:2px solid var(--bd);user-select:none}
.dt th:hover{background:#e8eaed}
.dt td{padding:10px;border-bottom:1px solid #f0f0f0;max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;vertical-align:middle;font-size:13px}
.dt tr{transition:background .15s}
.dt tr:hover td{background:#f8faff}
.dt tr.s-row{background:var(--s-bg)}
.dt tr.a2-row{background:var(--a2-bg)}
.dt tr.a3-row{background:var(--a3-bg)}

/* Grade Tags */
.tg-s{background:linear-gradient(135deg,#e53935,#c62828);color:#fff;padding:3px 10px;border-radius:6px;font-size:12px;font-weight:800;letter-spacing:.5px;display:inline-block;min-width:56px;text-align:center}
.tg-a2{background:linear-gradient(135deg,#ef6c00,#e65100);color:#fff;padding:3px 10px;border-radius:6px;font-size:12px;font-weight:700;display:inline-block;min-width:56px;text-align:center}
.tg-a3{background:linear-gradient(135deg,#1976d2,#1565c0);color:#fff;padding:3px 10px;border-radius:6px;font-size:12px;font-weight:700;display:inline-block;min-width:56px;text-align:center}
.tg-b{background:#bdbdbd;color:#fff;padding:3px 10px;border-radius:6px;font-size:12px;font-weight:600;display:inline-block}
.tg-c{background:#90a4ae;color:#fff;padding:3px 10px;border-radius:6px;font-size:12px;display:inline-block}
.tg-deal{background:linear-gradient(135deg,#43a047,#2e7d32);color:#fff;padding:3px 10px;border-radius:6px;font-size:12px;font-weight:700;display:inline-block}
.tg-hot{background:linear-gradient(135deg,#ff5722,#e64a19);color:#fff;padding:1px 7px;border-radius:4px;font-size:10px;font-weight:700}
.tg-new{background:#4caf50;color:#fff;padding:1px 7px;border-radius:4px;font-size:10px;font-weight:700}
.ph{font-family:"SF Mono",SFMono-Regular,Consolas,monospace;font-weight:700;color:var(--pd);letter-spacing:.3px}

/* Charts Area */
.ag{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:16px}
.cc{background:var(--cb);border-radius:var(--rad);box-shadow:var(--sh);padding:20px}
.cc h3{font-size:15.5px;color:var(--pd);margin-bottom:16px;padding-bottom:10px;border-bottom:2px solid var(--bd);display:flex;align-items:center;gap:8px}
.br{display:flex;align-items:center;margin-bottom:9px;font-size:13px}
.bl{width:100px;flex-shrink:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12.5px;font-weight:600}
.bt{flex:1;height:24px;background:#eef1f4;border-radius:6px;overflow:hidden;margin:0 10px}
.bf{height:100%;border-radius:6px;display:flex;align-items:center;padding-right:8px;transition:width .5s ease}
.bf.pr{background:linear-gradient(90deg,#42a5f5,#1976d2)}
.bf.cg{background:linear-gradient(90deg,#66bb6a,#43a047)}
.bf.or{background:linear-gradient(90deg,#ffa726,#ef6c00)}
.bf.rd{background:linear-gradient(90deg,#ef5350,#e53935)}
.bv{font-size:11.5px;color:#fff;font-weight:700;white-space:nowrap;text-shadow:0 1px 2px rgba(0,0,0,.15)}
.bp{width:52px;text-align:right;font-size:12px;color:var(--tl);font-weight:700}

/* Detail Modal */
.mo{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.5);z-index:999;justify-content:center;align-items:center;backdrop-filter:blur(3px)}
.mo.sh{display:flex}
.mb{background:var(--cb);border-radius:16px;width:780px;max-height:85vh;overflow-y:auto;padding:28px;box-shadow:0 12px 48px rgba(0,0,0,.2);position:relative}
.mb h2{color:var(--pd);margin-bottom:18px;font-size:19px;border-bottom:2px solid var(--bd);padding-bottom:12px;display:flex;align-items:center;gap:10px}
.dg{display:grid;grid-template-columns:auto 1fr;gap:8px 18px;font-size:13.5px}
.dl{color:var(--tl);font-weight:700}.dv{word-break:break-all}
/* Score Breakdown */
.sc-box{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}
.sc-item{background:#f5f7fa;border-radius:8px;padding:8px 12px;text-align:center;min-width:58px}
.sc-item .sn{font-size:11px;color:var(--tl)}.sc-item .sv{font-size:22px;font-weight:800;color:var(--pd)}
.sc-item.hi .sv{color:var(--rd)} .sc-item.md .sv{color:var(--og)} .sc-item.lo .sv{color:var(--b-tx)}

/* Product Cards */
.prod-list{display:flex;gap:10px;flex-wrap:wrap;margin:10px 0}
.prod-card{background:linear-gradient(135deg,#e8f0fe,#f0f4fc);border-left:4px solid var(--pr);border-radius:8px;padding:10px 14px;min-width:200px}
.prod-card .pn2{font-weight:700;color:var(--pd);font-size:13.5px}
.prod-card .pt{font-size:11.5px;color:var(--tl);margin-top:3px}
.prod-card .pp{font-size:12px;color:var(--og);font-weight:600;margin-top:3px}

/* Script Box */
.script-box{background:linear-gradient(135deg,#fff8e1,#fff3cd);border:1px solid #ffc107;border-radius:10px;padding:16px;margin:14px 0;font-size:13.5px;line-height:1.75}
.script-box .stitle{font-weight:800;color:#e65100;font-size:14px;margin-bottom:8px;display:flex;align-items:center;gap:6px}
.script-box .scontent{color:#333;white-space:pre-line}

/* Action Box */
.action-box{background:linear-gradient(135deg,#e3f2fd,#bbdefb);border-left:4px solid var(--bl);border-radius:0 10px 10px 0;padding:14px 18px;margin:14px 0}
.action-box .atitle{font-weight:800;color:var(--bl);font-size:14px;margin-bottom:6px}
.action-box .acontent{font-size:13.5px;line-height:1.65}

/* Follow Records */
.fr-box{background:#fafafa;border-radius:8px;padding:12px 16px;margin:10px 0}
.fr-box h4{font-size:13.5px;color:var(--pd);margin-bottom:8px}
.fr-item{background:#fff;border-left:3px solid var(--bd);padding:8px 12px;margin-bottom:6px;border-radius:0 6px 6px 0;font-size:13px;line-height:1.6}

.cm{position:absolute;top:14px;right:18px;font-size:28px;cursor:pointer;color:#bbb;background:none;border:none;font-family:inherit}
.cm:hover{color:var(--tx)}

.ft{text-align:center;color:var(--tl);font-size:11.5px;padding:18px 0;margin-top:20px}

@media(max-width:768px){
  .cr{grid-template-columns:repeat(2,1fr)}
  .ag{grid-template-columns:1fr}
  .mb{width:95%;margin:10px}
}
</style>
</head>
<body>

<div class="hd">
  <h1>🎯 线索池 SDR 机会中心</h1>
  <div class="sub">投流线索 · 智能分级 · 产品推荐 · 销售话术 | 数据源:石摩「销售部线索跟进6.30 787」</div>
  <div class="ver">v2.0 · Professional Edition · '''+TS+'''</div>
</div>

<div class="cr" id="cards"></div>
<div class="fb" id="fb"></div>

<div class="ts">
  <button class="tb on" onclick="sw(\'l\',this)">📋 机会列表 <span id="bcL" class="badge"></span></button>
  <button class="tb" onclick="sw(\'g\',this)">📊 机会分级</button>
  <button class="tb" onclick="sw(\'c\',this)">📡 渠道效果</button>
  <button class="tb" onclick="sw(\'d\',this)">🏢 部门排行</button>
</div>

<!-- List Panel -->
<div class="pn on" id="pl">
  <div class="tw"><table class="dt" id="tbl"><thead><tr id="th"></tr></thead><tbody id="tb"></tbody></table></div>
  <div id="ti" style="padding:14px;text-align:center;color:var(--tl);font-size:13px"></div>
</div>

<!-- Grade Panel -->
<div class="pn" id="pg"><div class="ag" id="ga"></div></div>

<!-- Channel Panel -->
<div class="pn" id="pc"><div class="ag" id="ca"></div></div>

<!-- Dept Panel -->
<div class="pn" id="pd"><div class="ag" id="da"></div></div>

<!-- Modal -->
<div class="mo" id="mo" onclick="if(event.target===this)this.classList.remove(\'sh\')">
  <div class="mb" id="mb"></div>
</div>

<div class="ft">线索池SDR看板 v2.0 · 15年销售专家视角 · '''+str(len(leads))+'''条 | 仅展示未成交有效线索</div>

<script>
const AL='''+JL+''';
const SM='''+JS+''';

let FL=[...AL],sc=\'\',so=1;
const ft={kw:\'\',st:\'\',dp:\'\',ch:\'\',lv:\'\',dl:\'f\',co:\'\',gr:\'\',ind:\'\',itl:\'\',df:\'\',dt:\'\',ag:\'\'};

function eh(s){if(!s)return \'\';return String(s).replace(/&/g,\'&amp;\').replace(/</g,\'&lt;\').replace(/>/g,\'&gt;\')}

// ====== KPI Cards ======
function rc(){
  const n=FL.length,d=FL.filter(x=>x._deal).length,
        s=FL.filter(x=>x._g===\'S\').length,a2=FL.filter(x=>x._g===\'A2\').length,
        a3=FL.filter(x=>x._g===\'A3\').length,b=FL.filter(x=>x._g===\'B\').length,
        r=n?(d/n*100):0;
  document.getElementById(\'cards\').innerHTML=`
  <div class="cd"><div class="lb">🎯 有效线索</div><div class="vl">${n.toLocaleString()}</div><div class="sb">未成交 / 有跟进价值</div></div>
  <div class="cd s"><div class="lb">🔥 S级·立即</div><div class="vl">${s}</div><div class="sb">今日必跟</div></div>
  <div class="cd a2"><div class="lb">⭐ A2级·重点</div><div class="vl">${a2}</div><div class="sb">3天内跟进</div></div>
  <div class="cd a3"><div class="lb">● A3级·正常</div><div class="vl">${a3}</div><div class="sb">本周内跟进</div></div>
  <div class="cd"><div class="lb">○ B级·低优</div><div class="vl">${b}</div><div class="sb">有空再看</div></div>
  <div class="cd d"><div class="lb">✅ 已成交</div><div class="vl">${d}</div><div class="sb">${r.toFixed(1)}% 转化率</div></div>`;
  // Update badges
  const bL=document.getElementById(\'bcL\');if(bL)bL.textContent=n.toLocaleString();
}

// ====== Filter Bar ======
function rf(){
  const el=document.getElementById(\'fb\');
  const st=[...new Set(AL.map(x=>x[\'跟进状态\']||\'\').filter(v=>v))],
        dp=Object.keys(SM.depts||{}),
        ch=Object.keys(SM.channels||{}),
        lv=[...new Set(AL.map(x=>x[\'线索级别\']||\'\').filter(v=>v))],
        co=[...new Set(AL.map(x=>x[\'分配顾问\']||\'\').filter(v=>v))],
        gr=[\'S\',\'A2\',\'A3\',\'B\',\'C\'],
        ind=[...new Set(AL.map(x=>x[\'_ind\']||\'\').filter(v=>v))].sort(),
        itl=[\'high\',\'medium\',\'low\',\'unknown\',\'rejected\'];

  el.innerHTML=`
  <label>🔍</label><input type=text id=fk placeholder="手机号/备注/来源..." style="width:170px" oninput=af()>
  <label>分级</label><select id=fgr onchange=af()><option value="">全部</option>${gr.map(g=>`<option value="${g}">${g}</option>`).join(\'\')}</select>
  <label>状态</label><select id=fs onchange=af()><option value="">全部</option>${st.map(s=>`<option>${eh(s)}</option>`).join(\'\')}</select>
  <label>部门</label><select id=fdp onchange=af()><option value="">全部</option>${dp.map(d=>`<option>${eh(d)}</option>`).join(\'\')}</select>
  <label>渠道</label><select id=fch onchange=af()><option value="">全部</option>${ch.map(c=>`<option>${eh(c)} (${SM.channels[c]||0})</option>`).join(\'\')}</select>
  <label>意向</label><select id=fitl onchange=af()><option value="">全部</option>${itl.map(t=>`<option value="${t}">${t===\'high\'?\'高意向\':t===\'medium\'?\'中意向\':t===\'low\'?\'低意向\':t===\'rejected\'?\'已拒绝\':\'未知\')}</option>`).join(\'\')}</select>
  <label>行业</label><select id=find onchange=af()><option value="">全部</option>${ind.slice(0,20).map(i=>`<option>${eh(i)}</option>`).join(\'\')}</select>
  <label>成交</label><select id=fdl onchange=af()><option value="f" selected>未成交</option><option value="t">已成交</option><option value="">全部</option></select>
  <label>📅起</label><input type=date id=ffd onchange=af()> <label>至</label> <input type=date id=ftd onchange=af()>
  <button class="fbtn" onclick=rst()>重置筛选</button>
  <button class="fbtn outline" onclick=ex()>📥 导出CSV</button>`;
}

// ====== Apply Filter ======
function af(){
  ft.kw=(document.getElementById(\'fk\')?.value||\'\').toLowerCase();
  ft.gr=document.getElementById(\'fgr\')?.value||\'\';
  ft.st=document.getElementById(\'fs\')?.value||\'\';
  ft.dp=document.getElementById(\'fdp\')?.value||\'\';
  ft.ch=document.getElementById(\'fch\')?.value||\'\';
  ft.itl=document.getElementById(\'fitl\')?.value||\'\';
  ft.ind=document.getElementById(\'find\')?.value||\'\';
  ft.dl=document.getElementById(\'fdl\')?.value||\'\';
  ft.co=(window.fcoEl?.value)||\'\'; // optional counselor filter
  ft.df=document.getElementById(\'ffd\')?.value||\'\';
  ft.dt=document.getElementById(\'ftd\')?.value||\'\';

  FL=AL.filter(l=>{
    if(ft.kw){
      const s=[l[\'手机号\'],l[\'其他联系方式\'],l[\'备注\'],l[\'分配人\'],l[\'分配顾问\'],l[\'来源\'],l[\'_ind\'],
        l[\'跟进情况（第一次）\'],l[\'跟进情况（第二次）\']].map(v=>(v||\'\').toLowerCase()).join(\'\');
      if(!s.includes(ft.kw)&&!(l[\'手机号\']||\'\').includes(ft.kw))return false}
    if(ft.gr&&l._gr!==ft.gr)return false;
    if(ft.st&&(l[\'跟进状态\']||\'\')!==ft.st)return false;
    if(ft.dp&&(l[\'分配部门\']||\'\')!==ft.dp)return false;
    if(ft.ch&&(l[\'渠道\']||\'\')!==ft.ch)return false;
    if(ft.itl&&l._itl!==ft.itl)return false;
    if(ft.ind&&l._ind!==ft.ind)return false;
    if(ft.dl===\'t\'&&!l._deal)return false;
    if(ft.dl===\'f\'&&l._deal)return false;
    if(ft.co&&(l[\'分配顾问\']||\'\')!==ft.co)return false;
    if(ft.df||ft.dt){
      const ds=l._ad||l[\'分配时间\']||\'\',dv=ds.replace(/\./g,\'-\');
      if(dv&&dv.length>=10){if(ft.df&&dv<ft.df)return false;if(ft.dt&&dv>ft.dt)return false}}
    return true});
  rc();rt();
}

function rst(){
  document.getElementById(\'fk\').value=\'\';
  document.getElementById(\'fgr\').value=\'\';
  document.getElementById(\'fs\').value=\'\';
  document.getElementById(\'fdp\').value=\'\';
  document.getElementById(\'fch\').value=\'\';
  document.getElementById(\'fitl\').value=\'\';
  document.getElementById(\'find\').value=\'\';
  document.getElementById(\'fdl\').value=\'f\';
  document.getElementById(\'ffd\').value=\'\';
  document.getElementById(\'ftd\').value=\'\';
  af();
}

// ====== Table Columns & Render ======
const TC=[
  {k:\'_gl\',l:\'分级\',w:72,f:(l)=>tgGrade(l)},
  {k:\'_sc\',l:\'评分\',w:50,f:(l)=>`<strong style="color:${l._sc>=24?\'#c62828\':l._sc>=19?\'#e65100\':l._sc>=14?\'#1976d2\':\'#666\'}">${l._sc}</strong>`},
  {k:\'_gu\',l:\'紧迫\',w:62},
  {k:\'_itl\',l:\'意向\',w:55,f:(l)=>tgIntent(l)},
  {k:\'_ind\',l:\'行业\',w:70},
  {k:\'分配部门\',l:\'部门\',w:82},
  {k:\'分配顾问\',l:\'顾问\',w:68},
  {k:\'渠道\',l:\'渠道\',w:105},
  {k:\'来源\',l:\'来源\',w:110},
  {k:\'分配时间\',l:\'分配\',w:68,f:(l)=>tagAge(l)},
  {k:\'手机号\',l:\'手机号\',w:120},
  {k:\'_ga\',l:\'建议动作\',w:0,hide:true},
];

function tgGrade(l){
  const g=l._g,c=l._gc;
  if(g===\'S\')return \'<span class="tg-s">\'+l._gl+\'</span>\';
  if(g===\'A2\')return \'<span class="tg-a2">\'+l._gl+\'</span>\';
  if(g===\'A3\')return \'<span class="tg-a3">\'+l._gl+\'</span>\';
  if(g===\'DEAL\')return \'<span class="tg-deal">已成交</span>\';
  if(g===\'B\')return \'<span class="tg-b">B</span>\';
  return \'<span class="tg-c">C</span>\';
}
function tgIntent(l){
  const it=l._itl;
  if(it===\'high\')return \'<span style="background:#ffebee;color:#c62828;padding:2px8px;border-radius:4px;font-size:11.5px;font-weight:700">高</span>\';
  if(it===\'medium\')return \'<span style="background:#fff3e0;color:#e65100;padding:2px8px;border-radius:4px;font-size:11.5px;font-weight:600">中</span>\';
  if(it===\'rejected\')return \'<span style="background:#eee;color:#888;padding:2px8px;border-radius:4px;font-size:11.5px">拒</span>\';
  return \'<span style="background:#f5f5f5;color:#888;padding:2px8px;border-radius:4px;font-size:11.5px">?</span>\';
}
function tagAge(l){
  const a=l._age_days;
  if(a==null)return \'-\';
  if(a<=3)return \'<span class="tg-new">\'+a+\'天</span>\';
  if(a<=7)return \'<span style="background:#e8f5e9;color:#2e7d32;padding:1px7px;border-radius:4px;font-size:11px;font-weight:600">\'+a+\'天</span>\';
  if(a<=21)return a+\'天\';
  return \'<span style="color:#e53935;font-weight:600">\'+a+\'天</span>\';
}

function rt(){
  // Sort by priority desc by default
  if(!sc){sc=\'_gp\';so=-1}
  const hdrHTML=TC.filter(c=>!c.hide).map(c=>{
    const arrow=sc===c.k?\' \'+(so===1?\'▲\':\'▼\'):\'\';
    return `<th style="width:${c.w}px"onclick="sb(\'${c.k}\')">${c.l}${arrow}</th>`;
  }).join(\'\')+\'<th style="width:46px">操作</th>\';

  document.getElementById(\'th\').innerHTML=hdrHTML;

  let rows=FL.slice(0,600);
  // Highlight S/A2 rows
  document.getElementById(\'tb\').innerHTML=rows.map(l=>{
    const rowClass=l._g===\'S\'?\'s-row\':l._g===\'A2\'?\'a2-row\':l._g===\'A3\'?\'a3-row\':\'\';
    const cols=TC.filter(c=>!c.hide).map(c=>{
      const v=c.f?c.f(l):(eh(String(l[c.k]||\'-\')));
      return `<td>${v}</td>`;
    }).join(\'\');
    return `<tr class="${rowClass}" onclick="sd(${AL.indexOf(l)})"style="cursor:pointer" title="${eh(l._ga||\'点击查看详情+话术\')}">${cols}<td><button onclick="event.stopPropagation();cp(\'${l[\'手机号\']}\\')"style="padding:3px8px;font-size:11px;border:1px solid var(--bd);background:#fff;border-radius:5px;cursor:pointer">复制</button></td></tr>`;
  }).join(\'\');

  document.getElementById(\'ti\').innerHTML=`显示 ${Math.min(rows.length,FL.length)} / ${FL.length} 条${FL.length>600?\' (前600，请缩小筛选范围)\':\'\'}${FL.length===0?\' 💡 提示：默认只显示未成交线索，切换到"全部"查看所有\':\'\'}`;
}

function sb(k){
  if(sc===k){so*=-1}else{sc=k;so=1}
  FL.sort((a,b)=>{
    let v=a[k]!=null?a[k]:\'\',vv=b[k]!=null?b[k]:\'\';
    if(typeof v===\'number\'){return(v-vv)*so}
    v=String(v).toLowerCase();vv=String(vv).toLowerCase();
    return v<vv?-1*so:v>vv?1*so});
  rt();
}

// ====== Tab Switching ======
function sw(t,el){
  document.querySelectorAll(\'.tb\').forEach(b=>b.classList.remove(\'on\'));
  document.querySelectorAll(\'.pn\').forEach(p=>p.classList.remove(\'on\'));
  el.classList.add(\'on\');
  document.getElementById(\'p\'+t)?.classList.add(\'on\');
  if(t===\'g\')renderGA();
  if(t===\'c\')renderCA();
  if(t===\'d\')renderDA();
}

// ====== Grade Distribution Chart ======
function renderGA(){
  const el=document.getElementById(\'ga\'),gd=SM.grade_dist||{};
  const grades=[
    {key:\'S\',label:\'🔥 S级-立即行动\',color:\'#e53935\',desc:\'高意向+新鲜·今日必须联系\'},
    {key:\'A2\',label:\'⭐ A2级-重点跟进\',color:\'#ef6c00\',desc:\'有意向+可触达·3天内搞定\'},
    {key:\'A3\',label:\'● A3级-正常跟进\',color:\'#1976d2\',desc:\'常规有效线索·本周完成沟通\'},
    {key:\'B\',label:\'○ B级-低优队列\',color:\'#9e9e9e\',desc:\'能联系但信号弱·有空再刷\'},
    {key:\'C\',label:\'△ C级-暂缓淘汰\',color:\'#78909c\',desc:\'无联系方式/已拒绝\'},
    {key:\'DEAL\',label:\'✅ 已成交\',color:\'#43a047\',desc:\'已签约·转客服维护\'},
  ];
  const ttl=Object.values(gd).reduce((s,n)=>s+n,0)||1;
  el.innerHTML=grades.map(g=>{
    const c=gd[g.key]||0,pct=((c/ttl)*100).toFixed(1);
    return `<div class="cc">
      <h3>${g.label} <span style="font-size:12px;color:var(--tl);margin-left:auto;font-weight:400">${c}条 (${pct}%)</span></h3>
      <div style="background:#eee;height:32px;border-radius:8px;overflow:hidden;margin:10px 0">
        <div style="height:100%;width:${pct}%;background:${g.color};border-radius:8px;display:flex;align-items:center;padding-left:12px;transition:width .6s">
          <span style="color:#fff;font-weight:800;font-size:14px">${c}</span>
        </div>
      </div>
      <div style="font-size:12.5px;color:var(--tl)">${g.desc}</div>
    </div>`;
  }).join(\'\')+(`
  <div class="cc" style="grid-column:1/-1">
    <h3>📌 分级标准说明</h3>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:10px;font-size:12.5px">
      <div style="background:var(--s-bg);border-radius:8px;padding:12px;border-left:4px solid #c62828">
        <strong>S级</strong> (≥24分 或 高意向+≤14天)<br>⚡ 今日必跟！高意向且新鲜度高<br>👉 立即回电/微信，推动下一步
      </div>
      <div style="background:var(--a2-bg);border-radius:8px;padding:12px;border-left:4px solid #e65100">
        <strong>A2级</strong> (≥19分 或 中意向+可触达)<br>📞 48小时内二次触达，推演示<br>👉 发产品资料→预约远程演示
      </div>
      <div style="background:var(--a3-bg);border-radius:8px;padding:12px;border-left:4px solid #1565c0">
        <strong>A3级</strong> (≥14分 或 有跟进记录)<br>📋 本周完成一次有效沟通<br>👉 了解需求→匹配产品方案
      </div>
      <div style="background:var(--b-bg);border-radius:8px;padding:12px;border-left:4px solid #616161">
        <strong>B/C级</strong> (&lt;9分 或 无有效信息)<br>🔄 批量外呼筛选 / ⏸️ 暂缓<br>👉 补充联系方式后再评估
      </div>
    </div>
  </div>`);
}

// ====== Channel Analysis ======
function renderCA(){
  const el=document.getElementById(\'ca\'),cv=SM.ch_conv||{};
  const items=Object.entries(cv).sort((a,b)=>b[1].t-a[1].t),ttl=SM.total||1;
  el.innerHTML=`<div class="cc" style="grid-column:1/-1">
    <h3>📡 渠道线索量 × 成交转化率</h3>
    ${items.map(([k,v])=>`<div class="br">
      <div class="bl" title="${eh(k)}">${eh(k.substring(0,12))}</div>
      <div class="bt"><div class="bf pr" style="width:${v.t/ttl*100}%"><span class="bv">${v.t}条</span></div></div>
      <div class="bp">${v.r}% (${v.d}单)</div>
    </div>`).join(\'\')}
  </div>`;
}

// ====== Dept Ranking ======
function renderDA(){
  const el=document.getElementById(\'da\'),dv=SM.dp_conv||{};
  const items=Object.entries(dv).sort((a,b)=>b[1].d-a[1].d),mx=Math.max(...items.map(x=>x[1].t));
  el.innerHTML=`<div class="cc" style="grid-column:1/-1">
    <h3>🏢 部门线索量 × 成交数</h3>
    ${items.slice(0,20).map(([k,v])=>`<div class="br">
      <div class="bl" style="width:90px" title="${eh(k)}">${eh(k.substring(0,10))}</div>
      <div class="bt"><div class="bf cg" style="width:${mx?v.t/mx*100:0}%"><span class="bv">${v.t}条 / ${v.d}成</span></div></div>
      <div class="bp">${v.r}%</div>
    </div>`).join(\'\')}
  </div>`;
}

// ====== Detail Modal (with scoring, profiling, scripts) ======
function sd(i){
  const l=AL[i];
  const mo=document.getElementById(\'mo\'),mb=document.getElementById(\'mb\');

  // Score breakdown
  const scd=l._scd||{};
  const scItems=Object.entries(scd).map(([k,v])=>{
    const cl=v>=4?\'hi\':v>=3?\'md\':\'lo\';
    return \`<div class="sc-item \${cl}"><div class="sn">\${k}</div><div class="sv">\${v}</div></div>\`;
  }).join(\'\');

  // Products
  const prods=(l._pds||[]).map(p=>
    \`<div class="prod-card"><div class="pn2">📦 \${eh(p.n)}</div>\
    <div class="pt">\${eh(p.c)} | \${eh(p.d||\'\')}</div>\
    <div class="pp">\${eh(p.pr||\'\')}</div></div>\`
  ).join(\'\');

  // Follow records
  let frs=\'\';
  for(let n=1;n<=4;n++){
    const fk=\`跟进情况（第\${\'一二三四\'[n-1]}次）\`;
    const fv=l[fk];if(fv)frs+=\`<div class="fr-item"><strong>第\${n}次:</strong> \${eh(fv)}</div>\`;
  }

  mb.innerHTML=\`
    <button class="cm" onclick="document.getElementById(\'mo\').classList.remove(\'sh\')">&times;</button>
    <h2>📞 线索详情 <span style="font-size:14px;font-weight:400;color:var(--tl)">${eh(l[\'手机号\'])}</span> ${tgGrade(l)}</h2>

    <!-- Basic Info -->
    <div class="dg">
      <div class="dl">分级</div><div style="font-weight:700;color:${l._gc};font-size:16px">${eh(l._gl)}</div>
      <div class="dl">总评分</div><div style="font-weight:800;color:var(--pd);font-size:20px">${l._sc} / 30</div>
      <div class="dl">紧迫度</div><div>${eh(l._gu)}</div>
      <div class="dl">意向等级</div><div>${tgIntent(l)}</div>
      <div class="dl">推断行业</div><div><strong>${eh(l._ind)}</strong> (匹配度:${l._isc||\'-\'}/5)</div>
      <div class="dl">规模推测</div><div>${eh(l._scl||\'-\')}</div>
      <div class="dl">渠道</div><div>${eh(l[\'渠道\'])}</div>
      <div class="dl">来源</div><div>${eh(l[\'来源\'])}</div>
      <div class="dl">分配部门</div><div>${eh(l[\'分配部门\'])}</div>
      <div class="dl">分配顾问</div><div>${eh(l[\'分配顾问\'])}</div>
      <div class="dl">登记人</div><div>${eh(l[\'分配人\'])}</div>
      <div class="dl">分配时间</div><div>${eh(l[\'分配时间\'])}${tagAge(l)}</div>
      <div class="dl">跟进状态</div><div>${eh(l[\'跟进状态\'])}</div>
      <div class="dl">线索级别</div><div>${eh(l[\'线索级别\'])}</div>
      <div class="dl">手机号</div><div class="ph">${eh(l[\'手机号\'])}</div>
      <div class="dl">其他联系方式</div><div>${eh(l[\'其他联系方式\'])}</div>
      <div class="dl">成交</div><div>${l._deal?\'<span class="tg-deal">已成交 ¥\'+l._amt:\'<span class="tg-c">未成交</span>\'}</div>
    </div>

    <!-- Score Breakdown -->
    <h3 style="margin-top:20px;color:var(--pd);font-size:15px">📊 六维评分明细</h3>
    <div class="sc-box">${scItems}</div>
    <div style="font-size:12px;color:var(--tl);margin:4px 0">${(l._scr||[]).join(\' | \')}</div>

    <!-- Recommended Products -->
    ${prods?`<h3 style="margin-top:18px;color:var(--pd);font-size:15px">📦 推荐产品（基于画像匹配）</h3>
    <div class="prod-list">${prods}</div>`:\'\'}

    <!-- Pains -->
    ${(l._pns||[]).length?`<h3 style="margin-top:14px;color:var(--pd);font-size:15px">🔍 识别到的痛点</h3>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin:8px 0">
    ${(l._pns||[]).map(p=>`<span style="background:#fce4ec;color:#c62828;padding:4px12px;border-radius:6px;font-size:12.5px;font-weight:600">${eh(p)}</span>`).join(\'\')}
    </div>`:\'\'}

    <!-- Sales Script -->
    <div class="script-box">
      <div class="stitle">🎤 销售话术（可直接念给客户）</div>
      <div class="scontent">${eh(l._fs||\'暂无话术\')}</div>
    </div>

    <!-- Action Recommendation -->
    <div class="action-box">
      <div class="atitle">⏭️ 建议动作</div>
      <div class="acontent">${eh(l._ga||\'\')}</div>
    </div>

    <!-- Follow Records -->
    ${frs?`<div class="fr-box"><h4>📝 跟进记录</h4>${frs}</div>`:\'\'}

    <!-- Notes -->
    ${l[\'备注\']?`<div style="margin:12px 0;padding:10px 14px;background:#f5f5f5;border-radius:8px;font-size:13px"><strong style="color:var(--tl)">备注:</strong> ${eh(l[\'备注\'])}</div>`:\'\'}

    <div style="margin-top:18px;display:flex;gap:10px">
      <button onclick="cp(\'${l[\'手机号\']}\')" style="padding:10px20px;background:var(--pr);color:#fff;border:none;border-radius:8px;cursor:pointer;font-weight:700;font-size:13px">📋 复制手机号</button>
      <button onclick="cpScript(${i})" style="padding:10px20px;background:var(--og);color:#fff;border:none;border-radius:8px;cursor:pointer;font-weight:700;font-size:13px">📝 复制话术</button>
    </div>
  \`;
  mo.classList.add(\'sh\');
}

function cp(p){navigator.clipboard.writeText(p||\'\').then(()=>alert(\'✅ 已复制: \'+p))}

function cpScript(i){
  const l=AL[i];
  const txt=l._op||\'\';
  navigator.clipboard.writeText(txt).then(()=>alert(\'✅ 已复制开场白话术\'));
}

// ====== Export CSV ======
function ex(){
  const hdr=[\'分级\',\'评分\',\'紧迫度\',\'意向\',\'行业\',\'部门\',\'顾问\',\'渠道\',\'来源\',\'分配时间\',\'手机号\',\'建议动作\'];
  const rows=FL.map(l=>[
    l._gl,l._sc,l._gu,l._itl,l._ind,l[\'分配部门\'],l[\'分配顾问\'],l[\'渠道\'],l[\'来源\'],l[\'分配时间\'],l[\'手机号\'],l._ga
  ].map(v=>`"${String(v).replace(/"/g,\'"\')}"`));
  const csv=\'\\uFEFF\'+[hdr,...rows].join(\'\\n\');
  const blob=new Blob([csv],{type:\'text/csv;charset=utf-8\'}),url=URL.createObjectURL(blob);
  const a=document.createElement(\'a\');a.href=url;a.download=\'线索池机会清单_\'+new Date().toISOString().slice(0,10)+\'.csv\';a.click();URL.revokeObjectURL(url);
}

// Init
rc();rf();rt();
</script>
</body>
</html>'''

with open(OUTPUT_HTML, 'w', encoding='utf-8') as f:
    f.write(HTML)

sz_kb = os.path.getsize(OUTPUT_HTML) / 1024
print(f'\n{"="*60}')
print(f'✅ 输出: {OUTPUT_HTML}')
print(f'   大小: {sz_kb:.0f} KB')
print(f'   线索: {len(leads)} 条')
print(f'   有效(未成交): {active_count} 条')
print(f'   S级: {stats["S"]} | A2: {stats["A2"]} | A3: {stats["A3"]} | B: {stats["B"]} | C: {stats["C"]}')
print(f'{"="*60}')
