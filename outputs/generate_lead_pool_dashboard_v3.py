#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
线索池SDR看板 v3.0 — 彻底重写架构
=================================================
v2的致命问题：16MB单文件内嵌11900条完整数据→浏览器白屏/卡死
v3方案：
  1. 数据与视图分离 → lead_pool_data.json（数据）+ HTML（纯UI）
  2. 异步fetch加载数据 → 有loading状态，不阻塞渲染
  3. 服务端分页 → 每页100条，零卡顿
  4. 索引式详情 → 不再用indexOf扫描大数组
  5. 保留全部业务逻辑 → 6维评分/S-A2-A3-B-C分级/画像/话术/产品推荐
"""
import json, os, re, sys, io, math
from collections import Counter
from datetime import datetime, timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_FILE = os.path.join(SCRIPT_DIR, 'shimo_raw_data', 'all_sheets_full.json')
OUTPUT_HTML = os.path.join(SCRIPT_DIR, '线索池SDR看板.html')
OUTPUT_DATA = os.path.join(SCRIPT_DIR, 'lead_pool_data.json')

NOW = datetime.now()

# ================================================================
# 秦丝产品知识库（37种服务）
# ================================================================
QINSILK_PRODUCTS = {
    '进销存会员': {'cat':'核心系统','tier':'入门','desc':'进销存基础，适合单店起步','price_range':'¥680-1280/年'},
    '进销存专业版': {'cat':'核心系统','tier':'中端','desc':'进销存+商品管理+库存预警+欠货统计','price_range':'¥1680-2680/年'},
    '生意通会员': {'cat':'核心系统','tier':'入门','desc':'批发订货基础功能','price_range':'¥680-1280/年'},
    '生意通专业版': {'cat':'核心系统','tier':'中端','desc':'批发订货+采购管理+财务报表','price_range':'¥1680-2980/年'},
    '生意通高级版': {'cat':'核心系统','tier':'高端','desc':'多门店+采购+财务+员工权限，连锁首选','price_range':'¥3680-5980/年'},
    '销货宝微商城标准版': {'cat':'线上渠道','tier':'入门','desc':'微信小程序商城+商品上架+在线支付','price_range':'¥980-1680/年'},
    '销货宝微商城基础版': {'cat':'线上渠道','tier':'中端','desc':'微商城+基础营销插件','price_range':'¥1980-2980/年'},
    '销货宝微商城专业版': {'cat':'线上渠道','tier':'高端','desc':'微商城+营销+分销+直播全渠道','price_range':'¥2980-4980/年'},
    '专属品牌小程序': {'cat':'线上渠道','tier':'中端','desc':'独立品牌小程序+自定义装修','price_range':'¥1980-3980/年'},
    '限时折扣促单宝': {'cat':'营销工具','tier':'入门','desc':'限时折扣+会员价+阶梯定价','price_range':'¥280-480/年'},
    '限时秒杀促单宝': {'cat':'营销工具','tier':'入门','desc':'秒杀活动+库存锁定+倒计时','price_range':'¥280-480/年'},
    '批量推款宝': {'cat':'营销工具','tier':'入门','desc':'批量推款给客户在线选款','price_range':'¥380-680/年'},
    '直播卖货': {'cat':'营销工具','tier':'中端','desc':'直播带货+引流到店+互动抽奖','price_range':'¥680-1280/年'},
    '微信自动化经营': {'cat':'营销工具','tier':'中端','desc':'自动加好友+群发+朋友圈营销','price_range':'¥580-980/年'},
    '专属微信会员卡': {'cat':'会员运营','tier':'中端','desc':'微信会员卡+积分+储值+会员画像','price_range':'¥680-1280/年'},
    '会员积分充值': {'cat':'会员运营','tier':'入门','desc':'会员积分+消费抵扣+积分商城','price_range':'¥380-680/年'},
    '慧店宝': {'cat':'硬件收银','tier':'中端','desc':'收银终端+扫码+打印一体','price_range':'¥1280-1980'},
    '慧店宝大屏收银端': {'cat':'硬件收银','tier':'高端','desc':'大屏收银终端高效收银','price_range':'¥1980-2980'},
    'AI绘图': {'cat':'AI工具','tier':'入门','desc':'AI自动绘图+智能抠图+商品图生成','price_range':'¥280-580/年'},
    '以图搜图': {'cat':'AI工具','tier':'入门','desc':'图片搜索商品快速找款','price_range':'¥180-380/年'},
    '门店': {'cat':'门店扩展','tier':'中端','desc':'多门店统一管理+独立库存','price_range':'¥380/店/年'},
    '商家名片': {'cat':'品牌展示','tier':'入门','desc':'电子名片+商品展示+一键拨号','price_range':'免费'},
    '企业微信客户助手': {'cat':'私域运营','tier':'中端','desc':'企微客户管理+SOP流程','price_range':'¥680-1280/年'},
}

INDUSTRY_KEYWORD_MAP = [
    ('服装|女装|男装|童装|鞋帽|服饰|穿搭|款式|尺码|SKU|换季|吊牌|标牌', '服装鞋帽', 5,
     ['批量推款宝','AI绘图','销货宝微商城专业版','进销存专业版'],
     ['款式多SKU难管','换季库存积压','颜色尺码组合爆炸']),
    ('食品|水果|生鲜|烘焙|蛋糕|零食|饮料|奶茶|保质期|临期', '食品生鲜', 4,
     ['进销存专业版','限时秒杀促单宝'],
     ['保质期短损耗大','批次追溯需求','临期快速清仓']),
    ('美妆|化妆品|代购|护肤|彩妆|面膜|复购|积分', '美妆代购', 4,
     ['专属微信会员卡','会员积分充值','销货宝微商城专业版'],
     ['会员复购运营','代购多渠道管理','批次临期管理']),
    ('母婴|童装|宝宝|儿童|玩具|孕产', '母婴玩具', 4,
     ['专属微信会员卡','销货宝微商城基础版'],
     ['会员复购成长周期','安全合规追溯']),
    ('数码|手机|配件|家电|电子|序列号|IMEI', '数码配件', 4,
     ['进销存专业版','批量推款宝'],
     ['SKU繁多型号复杂','价格波动快调价频繁']),
    ('超市|便利店|商超|收银|快消|排队|储值', '商超便利', 4,
     ['慧店宝','专属微信会员卡','限时折扣促单宝'],
     ['收银效率低排队','快消高频周转','会员储值需求']),
    ('餐饮|餐厅|饭店|火锅|烧烤|外卖|菜单', '餐饮', 3,
     ['进销存专业版','慧店宝'],
     ['原材料库存管理','收银效率','成本核算']),
    ('百货|日用|杂货|日用品|小商品', '日用百货', 3,
     ['进销存专业版','销货宝微商城基础版'],
     ['SKU多而杂','库存盘点繁琐','低毛利跑量']),
    ('家居|家纺|建材|家具|装饰|窗帘|床上用品', '家居家纺', 3,
     ['进销存专业版','专属微信会员卡'],
     ['SKU多花色规格','换季库存','会员复购']),
    ('五金|机械|汽修|汽配|配件|维修|批发订货', '五金汽配', 3,
     ['生意通专业版','批量推款宝'],
     ['规格型号复杂','B2B批发订货','库存价值高']),
    ('宠物|猫粮|狗粮|宠物店|宠物美容', '宠物用品', 3,
     ['专属微信会员卡','销货宝微商城基础版'],
     ['会员复购宠物档案','SKU多','积分运营']),
    ('烟酒|茶叶|白酒|红酒|防伪|溯源', '烟酒茶', 4,
     ['进销存专业版','专属微信会员卡'],
     ['防伪溯源需求','高价值商品库存','批次年份管理']),
    ('珠宝|首饰|饰品|黄金|钻石|翡翠|VIP|高价值', '珠宝饰品', 4,
     ['专属微信会员卡','进销存专业版'],
     ['高价值防伪','会员VIP运营','定制订单管理']),
]

CHANNEL_QUALITY = {
    '小红书SEM':        {'quality':5,'conv_rate':6.1,'note':'搜索意向强·精准度高'},
    '小红书私信/咨询':  {'quality':4,'conv_rate':5.8,'note':'主动咨询·意向明确'},
    '小红书店铺':      {'quality':4,'conv_rate':5.0,'note':'店铺转化路径'},
    '抖音SEM':          {'quality':5,'conv_rate':5.0,'note':'搜索广告·精准'},
    '抖音咨询':         {'quality':4,'conv_rate':4.5,'note':'主动私信咨询'},
    '视频号':           {'quality':3,'conv_rate':3.5,'note':'视频号生态·需培育'},
}

SOURCE_PROFILES = {
    '小青在做服装':            {'industry':'服装鞋帽','scale':'中','intent':'高','boost':2},
    '阿秋服装店':             {'industry':'服装鞋帽','scale':'中小','intent':'高','boost':2},
    '阿秋服装创业记':         {'industry':'服装鞋帽','scale':'初创','intent':'高','boost':1},
    '七七服装创业':           {'industry':'服装鞋帽','scale':'初创','intent':'高','boost':1},
    '小月服装创业中':         {'industry':'服装鞋帽','scale':'初创','intent':'中','boost':1},
    '小衣':                   {'industry':'服装鞋帽','scale':'初创','intent':'中','boost':1},
    '小桔服装连锁':          {'industry':'服装鞋帽','scale':'多店','intent':'高','boost':3},
    '小桔服装版':            {'industry':'服装鞋帽','scale':'中','intent':'中','boost':1},
    '服装小衣':              {'industry':'服装鞋帽','scale':'初创','intent':'中','boost':1},
    '服装爆单日记':          {'industry':'服装鞋帽','scale':'中','intent':'高','boost':2},
    '秦丝进销存app':         {'industry':'通用','scale':'未知','intent':'中','boost':1,'known_brand':True},
    '秦丝进销存':            {'industry':'通用','scale':'未知','intent':'中','boost':1,'known_brand':True},
    '秦丝科技丨服装收银系统': {'industry':'服装鞋帽','scale':'未知','intent':'高','boost':2,'known_brand':True},
    '秦丝科技企业店':        {'industry':'通用','scale':'未知','intent':'中','boost':1,'known_brand':True},
    '勤勤创业版':            {'industry':'通用','scale':'初创','intent':'中','boost':1},
    '你的创业闺蜜糖糖':      {'industry':'通用','scale':'初创','intent':'中','boost':1},
    '丝丝的创业手账':        {'industry':'通用','scale':'初创','intent':'中','boost':1},
    '阿棠':                  {'industry':'通用','scale':'未知','intent':'中','boost':1},
}

REJECT_PATTERNS = [r'不要了',r'不需要',r'不用了',r'没兴趣',r'暂时不',r'不考虑',
                   r'已经用了',r'已经有.*系统',r'用.*别的',r'挂断',r'不接',r'打不通',
                   r'联系不上',r'拉黑',r'删除',r'退订']
INTENT_HIGH = [r'咨询',r'想了解',r'多少钱',r'价格',r'怎么买',r'购买',r'演示',r'试用',
               r'功能',r'小程序',r'会员',r'收银',r'入库自动定价',r'碰碰贴',r'问.*系统',r'问.*价格']
INTENT_MEDIUM = [r'加微信',r'加了',r'已添加',r'通过',r'待通过',r'发SOP',r'发了',r'发送',r'介绍']

def parse_date(s):
    if not s or not str(s).strip(): return ''
    s = str(s).strip()
    m = re.match(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', s)
    if m: return f'{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}'
    m = re.match(r'(\d{1,2})[月./\-](\d{1,2})', s)
    if m: return f'{NOW.year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}'
    return s

def calc_age(assign_date_str):
    if not assign_date_str: return None
    d = parse_date(assign_date_str)
    try:
        dt = datetime.strptime(d[:10], '%Y-%m-%d')
        return max(0, (NOW - dt).days)
    except: return None

def detect_industry(text):
    if not text: return None, []
    for kw, ind, score, recs, pains in INDUSTRY_KEYWORD_MAP:
        if re.search(kw, text): return ind, (score, recs, pains)
    return None, []

def check_reject(text):
    if not text: return False, ''
    for p in REJECT_PATTERNS:
        m = re.search(p, text)
        if m: return True, m.group()
    return False, ''

def detect_intent(lead):
    texts = ' '.join([lead.get('备注',''),lead.get('客户备注',''),
                     lead.get('跟进情况（第一次）',''),lead.get('跟进情况（第二次）',''),
                     lead.get('跟进情况（第三次）',''),lead.get('跟进情况（第四次）','')])
    rej, rw = check_reject(texts)
    if rej: return 'rejected', rw
    for p in INTENT_HIGH:
        if re.search(p, texts): return 'high', p
    for p in INTENT_MEDIUM:
        if re.search(p, texts): return 'medium', p
    if texts.strip() and len(texts.strip()) > 5: return 'low', ''
    return 'unknown', ''

def build_profile(lead):
    source = lead.get('来源','')
    note = lead.get('备注','') or ''
    note2 = lead.get('客户备注','') or ''
    all_text = f'{source} {note} {note2}'
    sp = SOURCE_PROFILES.get(source, {})
    kb = sp.get('known_brand', False)
    industry, ii = detect_industry(all_text)
    if not industry and sp: industry = sp.get('industry',''); ii = (3,[],[])
    isc = ii[0] if ii else 1
    recs = ii[1] if len(ii)>1 else []
    pains = ii[2] if len(ii)>2 else []
    intent, isig = detect_intent(lead)
    scale = sp.get('scale','未知')
    prods = list(recs) if recs else []
    if kb:
        core = ['进销存专业版']
        for c in core:
            if c not in prods: prods.insert(0,c)
    if not prods: prods = ['进销存专业版','进销存会员']
    pdetails = []
    for pn in prods:
        if pn in QINSILK_PRODUCTS:
            pd = QINSILK_PRODUCTS[pn].copy()
            pd['name'] = pn
            pdetails.append(pd)
    return {
        'industry': industry or '未识别', 'industry_score': isc, 'scale': scale,
        'intent_level': intent, 'intent_signal': isig, 'known_brand': kb,
        'pains': pains, 'products': pdetails[:5], 'source_boost': sp.get('boost',0),
    }

def score_lead(lead, prof):
    sc = {}; reasons = []
    ch = lead.get('渠道',''); st = lead.get('跟进状态','')
    at = lead.get('分配时间',''); ph = lead.get('手机号','')
    oc = lead.get('其他联系方式',''); lt = lead.get('线索级别','')
    src = lead.get('来源','')

    # L1 意向
    it = prof['intent_level']
    if it=='high': L1=5; reasons.append(f'L1=5(高意向:{prof["intent_signal"]})')
    elif it=='medium': L1=3; reasons.append('L1=3(中意向:已建联)')
    elif it=='low': L1=2; reasons.append('L1=2(低意向)')
    elif it=='rejected': L1=0; reasons.append(f'L1=0(已拒绝:{prof["intent_signal"]})')
    else: L1=1; reasons.append('L1=1(未知)')
    sc['L1']=L1

    # L2 渠道
    cq = CHANNEL_QUALITY.get(ch,{})
    L2 = cq.get('quality',3)
    reasons.append(f'L2={L2}({ch}·转{cq.get("conv_rate","?")}%)')
    sc['L2']=L2

    # L3 来源
    sb = prof['source_boost']; isc = prof['industry_score']
    L3 = min(5, 2+sb+(1 if isc>=4 else 0))
    if L3>=4: reasons.append(f'L3={L3}(精准来源+{prof["industry"]})')
    elif sb>=2: reasons.append(f'L3={L3}(优质:{src[:10]})')
    else: reasons.append(f'L3={L3}(一般)')
    sc['L3']=L3

    # L4 跟进
    fu = [lead.get(f'跟进情况（第{n}次）','') or lead.get(f'跟进情况（{"一二三四"[n-1]}）次）','') or '' for n in range(1,5)]
    fc = sum(1 for x in fu if x.strip())
    if lt:
        if 'S' in lt: L4=5; reasons.append(f'L4=5(标签:{lt})')
        elif lt.startswith('A'): L4=4; reasons.append(f'L4=4({lt})')
        elif lt.startswith('B'): L4=1; reasons.append(f'L4=1({lt})')
        else: L4=2; reasons.append(f'L4=2({lt})')
    elif fc>=3: L4=4; reasons.append(f'L4=4(深跟{fc}次)')
    elif fc>=2: L4=3; reasons.append(f'L4=3(持续{fc}次)')
    elif fc>=1: L4=2; reasons.append('L4=2(初跟)')
    elif st=='跟进中': L4=3; reasons.append('L4=3(跟进中)')
    else: L4=1; reasons.append('L4=1(未跟)')
    sc['L4']=L4

    # L5 新鲜度
    age = calc_age(at)
    if age is None: L5=3; reasons.append('L5=?')
    elif age<=7: L5=5; reasons.append(f'L5=5(新鲜{age}天)')
    elif age<=14: L5=4; reasons.append(f'L5=4(较新{age}天)')
    elif age<=30: L5=3; reasons.append(f'L5=3(常规{age}天)')
    elif age<=60: L5=2; reasons.append(f'L5=2(偏老{age}天)')
    else: L5=4; reasons.append(f'L5=4(老化{age}天·流失风险)')
    sc['L5']=L5
    lead['_age_days'] = age

    # L6 可触达
    hw = bool(oc and ('微信' in oc or 'vx' in oc.lower()))
    ho = bool(ph and len(ph)>=11 and '*' not in ph)
    hoo = bool(oc and oc.strip())
    if hw: L6=5; reasons.append('L6=5(微信)')
    elif ho and hoo: L6=4; reasons.append('L6=4(电话+其他)')
    elif ho: L6=3; reasons.append('L6=3(仅电话)')
    elif ph and '*' in ph: L6=2; reasons.append('L6=2(脱敏)')
    else: L6=1; reasons.append('L6=1(缺失)')
    sc['L6']=L6

    total = sum(sc.values())
    return {'scores':sc,'total':total,'reasons':reasons,'follow_count':fc}

def grade_lead(sr, prof, lead):
    tot = sr['total']; ssc = sr['scores']
    it = prof['intent_level']; age = lead.get('_age_days')
    deal = lead.get('_deal',False); lt = lead.get('线索级别','')
    if deal:
        return {'grade':'DEAL','label':'已成交','color':'#27ae60','urgency':'无','action':'✅ 已成交·转入客服维护','priority':0}
    if it == 'rejected':
        return {'grade':'C','label':'已拒绝','color':'#95a5a6','urgency':'放弃','action':'❌ 已拒绝·移入公海池','priority':0}
    st = []
    if tot >= 24: st.append(f'高分{tot}')
    if it=='high' and age is not None and age <= 14: st.append('高意+新鲜')
    if lt and 'S' in lt: st.append(f'S标签{lt}')
    if ssc.get('L1',0)==5 and ssc.get('L5',0)>=4: st.append('高意+新鲜')
    if st:
        return {'grade':'S','label':'🔥S·立即','color':'#e74c3c','urgency':'今日必跟','action':'⚡ 立即回电/微信！高意向+新鲜度好','priority':5}
    a2t = []
    if tot >= 19: a2t.append(f'高分{tot}')
    if it in ('high','medium') and ssc.get('L6',0)>=3: a2t.append('意+可达')
    if it=='medium' and age is not None and age<=21: a2t.append('中意+3周内')
    if ssc.get('L1',0)>=4 and ssc.get('L4',0)>=3: a2t.append('高意+深跟')
    if a2t:
        return {'grade':'A2','label':'⭐A2·重点','color':'#f39c12','urgency':'3天内','action':'📞 48小时内二次触达，推动演示/试用','priority':4}
    if tot >= 14 or (sr['follow_count']>=1 and it!='low') or (lt and 'A' in lt):
        return {'grade':'A3','label':'●A3·正常','color':'#3498db','urgency':'本周内','action':'📋 本周完成一次有效沟通，确认需求','priority':3}
    if tot >= 9 or ssc.get('L6',0)>=2:
        return {'grade':'B','label':'○B·低优','color':'#95a5a6','urgency':'有空再看','action':'🔄 有空时批量外呼筛选','priority':2}
    return {'grade':'C','label':'△C·暂缓','color':'#bdc3c7','urgency':'暂缓','action':'⏸️ 信息不全或无信号，暂缓处理','priority':1}

def gen_script(lead, prof, gi):
    ind = prof['industry']; it = prof['intent_level']
    prods = prof['products']; pains = prof['pains']
    kb = prof['known_brand']; src = lead.get('来源','')[:20]
    ch = lead.get('渠道','')
    if kb:
        op = f"您好！我是秦丝的客户顾问，之前看到您在小红书上咨询过我们的{prods[0]['name'] if prods else '进销存'}系统，今天特意来回访一下您目前的使用情况或者还有哪些需要了解的功能？"
    elif ind not in ('未识别','通用'):
        op = f"您好！我是秦丝的顾问，了解到您做【{ind}】行业的，我们专门针对这个行业有一套成熟的解决方案，像{'、'.join([p['name'] for p in prods[:2]])}这些功能都是为您量身定制的。不知道您现在是用什么方式在管理库存和开单的呢？"
    else:
        op = "您好！我是秦丝的顾问，看到您之前咨询过我们，想了解一下您现在开店主要遇到的问题是什么？比如是库存记不清楚、开单太慢还是会员不好管理？"
    rs_map = {'high':'客户表现出明确兴趣，直接进入产品演示和报价环节。',
              'medium':'客户已有建联但未深入，需要进一步挖掘痛点和预算。',
              'low':'客户反应冷淡，先发资料+案例，3天后回访。',
              'rejected':'⚠️ 客户已表达拒绝，不建议继续骚扰。如需再激活建议间隔30天以上。',
              'unknown':'首次接触，以询问和倾听为主，挖掘真实需求。'}
    phook = f"痛点切入：「{pains[0]}」是我们服务的{ind}客户最常提到的痛点。" if pains else ''
    ppitch = "推荐方案：" + "；".join([f"【{p['name']}】- {p.get('desc','')}" for p in prods[:3] if p.get('desc')]) if prods else ''
    action = gi.get('action','')
    full = f"=== 销售话术 ===\n\n📞 开场白:\n「{op}」\n\n💡 {phook}\n\n📦 {ppitch}\n\n🎯 策略: {rs_map.get(it,'')}\n\n⏭️ 动作: {action}"
    return {'opening':op,'response_strategy':rs_map.get(it,''),'pain_hook':phook,'product_pitch':ppitch,'next_action':action,'full_script':full}


# ================================================================
# 数据加载 & 处理
# ================================================================
print('='*60)
print('线索池看板 v3.0 — 数据+视图分离架构')
print('='*60)

print('\n[1/3] 加载原始数据...')
with open(RAW_FILE,'r',encoding='utf-8') as f: RAW = json.load(f)

raw1 = RAW.get('小红书1组线索表',{}).get('data','')
lines1 = raw1.split('\n')
HDR = [h.strip() for h in lines1[9].split('\t')]
leads = []
for ln in lines1[10:]:
    parts = ln.split('\t')
    if len(parts)<len(HDR): continue
    rec = {HDR[i]:(parts[i].strip() if i<len(parts) else '') for i in range(len(HDR))}
    phone = rec.get('手机号','').strip()
    if len(phone)<8: continue
    ds = str(rec.get('是否成交','')).strip().upper()
    rec['_deal'] = ds=='TRUE'
    am = rec.get('成交金额','').replace(',','').replace(' ','')
    try: rec['_amt']=float(am)
    except: rec['_amt']=0
    rec['_src']='XHS'; rec['_ad']=parse_date(rec.get('分配时间',''))
    rec['_dd']=parse_date(rec.get('成交时间',''))
    leads.append(rec)

print(f'  小红书表: {len(leads)} 条')

raw2 = RAW.get('线索跟进表',{}).get('data','')
added=0
if raw2:
    l2 = raw2.split('\n')
    tc = Counter(x.count('\t') for x in l2); dtc = tc.most_common(1)[0][0]
    seen = set(l.get('手机号','') for l in leads)
    for ln in l2:
        if ln.count('\t')!=dtc: continue
        p=ln.split('\t')
        ph=p[1].strip() if len(p)>1 else ''
        if len(ph)<8 or ph in seen: continue
        r2={'手机号':ph,'昵称':p[0].strip() if len(p)>0 else '',
            '创建时间':p[2].strip() if len(p)>2 else '',
            '渠道':p[6].strip() if len(p)>6 else '',
            '分配部门':p[8].strip() if len(p)>8 else '',
            '分配顾问':p[9].strip() if len(p)>9 else '',
            '跟进状态':'','分配时间':'','分配人':'',
            '是否成交':'','成交时间':'','成交金额':'',
            '其他联系方式':'','线索级别':'','备注':'','来源':'',
            '跟进情况（第一次）':'','跟进情况（第二次）':'',
            '跟进情况（第三次）':'','跟进情况（第四次）':'',
            '_src':'FU','_deal':False,'_amt':0}
        leads.append(r2); added+=1
print(f'  跟进表补充: {added} 条 | 总计: {len(leads)} 条')

# ================================================================
# 评分→分级→画像→话术
# ================================================================
print('[2/3] 评分分级+画像+话术...')
stats = {'S':0,'A2':0,'A3':0,'B':0,'C':0,'DEAL':0}; active=0
for idx,lead in enumerate(leads):
    prof = build_profile(lead); sr = score_lead(lead,prof); gi = grade_lead(sr,prof,lead); scr = gen_script(lead,prof,gi)
    lead.update({
        '_ind':prof['industry'],'_isc':prof['industry_score'],'_itl':prof['intent_level'],
        '_knb':prof['known_brand'],'_scl':prof['scale'],'_pns':prof['pains'],
        '_pds':[{'n':p['name'],'c':p.get('cat',''),'t':p.get('tier',''),'d':p.get('desc',''),'pr':p.get('price_range','')} for p in prof.get('products',[])],
        '_sc':sr['total'],'_scd':sr['scores'],'_scr':sr['reasons'],'_fc':sr['follow_count'],
        '_g':gi['grade'],'_gl':gi['label'],'_gc':gi['color'],'_gu':gi['urgency'],'_ga':gi['action'],'_gp':gi['priority'],
        '_op':scr['opening'],'_rs':scr['response_strategy'],'_ph':scr['pain_hook'],
        '_pp':scr['product_pitch'],'_fs':scr['full_script'],
    })
    g = gi['grade']; stats[g]=stats.get(g,0)+1
    if not lead.get('_deal') and g!='DEAL': active+=1
    if (idx+1)%1000==0: print(f'  进度: {idx+1}/{len(leads)}')

print(f'  分级: S={stats["S"]} A2={stats["A2"]} A3={stats["A3"]} B={stats["B"]} C={stats["C"]} DEAL={stats["DEAL"]}')
print(f'  有效未成交: {active}')

# ================================================================
# 维度统计
# ================================================================
print('[3/3] 构建输出...')
by_status = Counter(l.get('跟进状态','')or'?' for l in leads)
by_dept = Counter(l.get('分配部门','未分配') for l in leads)
by_channel = Counter(l.get('渠道','?') for l in leads)
by_counselor = Counter(l.get('分配顾问','') for l in leads)
by_source = Counter(l.get('来源','') for l in leads)
by_grade = Counter(l['_g'] for l in leads)
by_industry = Counter(l['_ind'] for l in leads)
by_intent = Counter(l['_itl'] for l in leads)
by_level = Counter(l.get('线索级别','') for l in leads)

ch_conv={}
for ch,cn in by_channel.items():
    d=sum(1 for l in leads if l.get('渠道')==ch and l.get('_deal'))
    ch_conv[ch]={'t':cn,'d':d,'r':round(d/cn*100,1) if cn else 0}
dp_conv={}
for dp,dn in by_dept.items():
    d=sum(1 for l in leads if l.get('分配部门')==dp and l.get('_deal'))
    dp_conv[dp]={'t':dn,'d':d,'r':round(d/dn*100,1) if dn else 0}

SUMM={
    'total':len(leads),'deals':stats.get('DEAL',0),'active':active,
    'rate':round(stats.get('DEAL',0)/len(leads)*100,1) if leads else 0,
    'grades':dict(stats),
    'channels':dict(by_channel),'depts':dict(by_dept),
    'status':dict(by_status),'levels':dict(by_level),
    'sources':dict(by_source.most_common(40)),'counselors':dict(by_counselor.most_common(30)),
    'ch_conv':ch_conv,'dp_conv':dp_conv,
    'grade_dist':dict(by_grade),'industry_dist':dict(by_industry),
    'intent_dist':dict(by_intent),
}

# 精简输出字段（去掉冗余嵌套）
OUT_LEADS=[]
for l in leads:
    OUT_LEADS.append({
        '跟进状态':l.get('跟进状态',''),'分配时间':l.get('分配时间',''),'分配人':l.get('分配人',''),
        '是否成交':l.get('是否成交',''),'成交时间':l.get('成交时间',''),'成交金额':l.get('成交金额',''),
        '手机号':l.get('手机号',''),'其他联系方式':l.get('其他联系方式',''),'线索级别':l.get('线索级别',''),
        '备注':l.get('备注',''),'渠道':l.get('渠道',''),'来源':l.get('来源',''),
        '分配部门':l.get('分配部门',''),'分配顾问':l.get('分配顾问',''),
        'f1':l.get('跟进情况（第一次）','') or l.get('跟进情况（第一次）',''),
        'f2':l.get('跟进情况（第二次）','') or l.get('跟进情况（第二次）',''),
        'f3':l.get('跟进情况（第三次）','') or l.get('跟进情况（第三次）',''),
        'f4':l.get('跟进情况（第四次）','') or l.get('跟进情况（第四次）',''),
        '_deal':l.get('_deal',False),'_amt':l.get('_amt',0),'_ad':l.get('_ad',''),
        '_dd':l.get('_dd',''),'_age_days':l.get('_age_days'),
        '_ind':l.get('_ind'),'_itl':l.get('_itl'),'_scl':l.get('_scl'),
        '_sc':l.get('_sc'),'_gu':l.get('_gu'),'_ga':l.get('_ga'),
        '_g':l.get('_g'),'_gl':l.get('_gl'),'_gc':l.get('_gc'),'_gp':l.get('_gp'),
        '_op':l.get('op',''),'_fs':l.get('fs',''),
        '_pds':l.get('_pds',[]),'_pns':l.get('_pns',[]),'_isc':l.get('_isc'),
    })

OUTPUT = {'summary':SUMM,'leads':OUT_LEADS}
with open(OUTPUT_DATA,'w',encoding='utf-8') as f:
    json.dump(OUTPUT,f,ensure_ascii=False,indent=2)
dsz=os.path.getsize(OUTPUT_DATA)/1024/1024
print(f'\n  数据文件: {OUTPUT_DATA} ({dsz:.1f}MB)')

# ================================================================
# HTML生成（纯UI·零内嵌数据）
# ================================================================
TS = NOW.strftime('%Y-%m-%d %H:%M')
HTML = r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>🎯 线索池SDR机会中心</title>
<style>
:root{
  --bg:#f0f2f5;--cb:#fff;--pr:#1565c0;--pd:#1976d2;--tx:#1a1a1a;
  --tl:#666;--bd:#dde2e6;--rd:#dc3545;--gn:#28a745;--og:#fd7e14;
  --sh:0 2px 12px rgba(0,0,0,.06);--rad:10px;
  --s-bg:#fff5f5;--s-tx:#dc3545;--a2-bg:#fff8e1;--a2-tx:#e67700;
  --a3-bg:#e8f4fd;--a3-tx:#0d6efd;--b-bg:#f8f9fa;--c-bg:#eee;
}*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:var(--bg);color:var(--tx);font-size:13px;line-height:1.55;padding:16px}
.hd{text-align:center;padding:22px 0 14px;margin-bottom:16px;background:linear-gradient(135deg,#1565c0,#1976d2,#1a73e8);color:#fff;border-radius:var(--rad)}
.hd h1{font-size:24px;font-weight:700;letter-spacing:2px}.hd .sub{font-size:12px;opacity:.85;margin-top:4px}.hd .ver{font-size:10px;opacity:.55;margin-top:3px}
.cr{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:14px}
.cd{background:var(--cb);border-radius:var(--rad);box-shadow:var(--sh);padding:14px 16px;border-top:3px solid var(--pr);transition:transform .15s}
.cd:hover{transform:translateY(-2px)}.cd .lb{color:var(--tl);font-size:11.5px;font-weight:600;text-transform:uppercase;letter-spacing:.5px}
.cd .vl{font-size:28px;font-weight:800;color:var(--pd);line-height:1.1}.cd .sb{font-size:11px;color:var(--tl);margin-top:3px}
.cd.s{border-color:var(--rd)}.cd.s .vl{color:var(--rd)}.cd.a2{border-color:var(--og)}.cd.a2 .vl{color:var(--og)}.cd.a3{border-color:var(--pd)}.cd.a3 .vl{color:var(--pd)}.cd.d{border-color:var(--gn)}.cd.d .vl{color:var(--gn)}
.fb{background:var(--cb);border-radius:var(--rad);box-shadow:var(--sh);padding:12px 16px;margin-bottom:12px;display:flex;flex-wrap:wrap;gap:8px;align-items:center;border:1px solid var(--bd)}
.fb label{font-size:11.5px;color:var(--tl);font-weight:600;white-space:nowrap}
.fb select,.fb input{border:1px solid var(--bd);border-radius:6px;padding:7px 10px;font-size:12.5px;background:#fafbfc;outline:none}
.fb select:focus,.fb input:focus{border-color:var(--pr);box-shadow:0 0 0 2px rgba(21,101,192,.1)}
.fbtn{background:var(--pr);color:#fff;border:none;border-radius:6px;padding:7px 14px;cursor:pointer;font-size:12px;font-weight:700}
.fbtn:hover{background:var(--pd)}.fbtn.outline{background:transparent;color:var(--pr);border:1.5px solid var(--pr)}
.fbtn.outline:hover{background:var(--pr);color:#fff}
.ts{display:flex;gap:2px;margin-bottom:12px;background:var(--cb);border-radius:8px;padding:3px;box-shadow:var(--sh)}
.tb{flex:1;padding:8px 10px;border:none;background:transparent;border-radius:6px;cursor:pointer;font-size:12.5px;font-weight:700;color:var(--tl);transition:all .2s;text-align:center}
.tb.on{background:var(--pr);color:#fff}.tb:hover:not(.on){background:#f5f5f5}
.pn{display:none}.pn.on{display:block}
.tw{background:var(--cb);border-radius:var(--rad);box-shadow:var(--sh);overflow:hidden}
table.dt{width:100%;border-collapse:collapse;font-size:12.5px}
.dt th{position:sticky;top:0;z-index:10;background:linear-gradient(#f8f9fa,#eef1f4);color:#444;font-weight:700;padding:10px 8px;text-align:left;white-space:nowrap;cursor:pointer;font-size:11.5px;border-bottom:2px solid var(--bd);user-select:none}
.dt th:hover{background:#e8eaed}
.dt td{padding:8px 6px;border-bottom:1px solid #f0f0f0;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;vertical-align:middle;font-size:12.5px}
.dt tr{transition:background .1s}.dt tr:hover td{background:#f8fafc}
.tr-s{background:var(--s-bg)}.tr-a2{background:var(--a2-bg)}.tr-a3{background:var(--a3-bg)}
.tg-s{background:linear-gradient(135deg,#dc3545,#c82333);color:#fff;padding:2px 8px;border-radius:5px;font-size:11.5px;font-weight:800}
.tg-a2{background:linear-gradient(135deg,#fd7e14,#e67700);color:#fff;padding:2px 8px;border-radius:5px;font-size:11.5px;font-weight:700}
.tg-a3{background:linear-gradient(135deg,#0d6efd,#0a58ca);color:#fff;padding:2px 8px;border-radius:5px;font-size:11.5px;font-weight:700}
.tg-b{background:#adb5bd;color:#fff;padding:2px 8px;border-radius:5px;font-size:11px}.tg-c{background:#90a4ae;color:#fff;padding:2px 8px;border-radius:5px;font-size:11px}
.tg-deal{background:linear-gradient(135deg,#28a745,#1e7e34);color:#fff;padding:2px 8px;border-radius:5px;font-size:11.5px;font-weight:700}
.tg-hi{background:#ffebee;color:#dc3545;padding:2px6px;border-radius:4px;font-size:11px;font-weight:700}
.tg-md{background:#fff3e0;color:#e65100;padding:2px6px;border-radius:4px;font-size:11px;font-weight:600}
.tg-rj{background:#f5f5f5;color:#888;padding:2px6px;border-radius:4px;font-size:11px}
.ph{font-family:"SF Mono",SFMono-Regular,Consolas,monospace;font-weight:700;color:var(--pd);letter-spacing:.3px}
.ag{display:grid;grid-template-columns:repeat(auto-fit,minmax(400px,1fr));gap:14px}
.cc{background:var(--cb);border-radius:var(--rad);box-shadow:var(--sh);padding:16px}
.cc h3{font-size:14.5px;color:var(--pd);margin-bottom:12px;padding-bottom:8px;border-bottom:2px solid var(--bd)}
.br{display:flex;align-items:center;margin-bottom:7px;font-size:12px}
.bl{width:90px;flex-shrink:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px;font-weight:600}
.bt{flex:1;height:22px;background:#eef1f4;border-radius:5px;overflow:hidden;margin:0 8px}
.bf{height:100%;border-radius:5px;display:flex;align-items:center;padding-right:6px;transition:width .4s}
.bf.pr{background:linear-gradient(90deg,#42a5f5,#1976d2)}.bf.cg{background:linear-gradient(90deg,#66bb6a,#43a047)}.bf.or{background:linear-gradient(90deg,#ffa726,#ef6c00)}
.bv{font-size:11px;color:#fff;font-weight:700;white-space:nowrap}.bp{width:48px;text-align:right;font-size:11.5px;color:var(--tl);font-weight:700}
.mo{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.5);z-index:999;justify-content:center;align-items:center;backdrop-filter:blur(3px)}
.mo.sh{display:flex}.mb{background:var(--cb);border-radius:14px;width:820px;max-height:88vh;overflow-y:auto;padding:22px;box-shadow:0 12px 40px rgba(0,0,0,.18);position:relative}
.mb h2{color:var(--pd);margin-bottom:14px;font-size:17px;border-bottom:2px solid var(--bd);padding-bottom:10px}
.dg{display:grid;grid-template-columns:auto 1fr;gap:6px 14px;font-size:13px}
.dl{color:var(--tl);font-weight:700}.dv{word-break:break-all}
.sc-box{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0}
.sc-item{background:#f5f7fa;border-radius:6px;padding:6px 10px;text-align:center;min-width:52px}
.sc-item .sn{font-size:10.5px;color:var(--tl)}.sc-item .sv{font-size:20px;font-weight:800;color:var(--pd)}
.sc-item.hi .sv{color:var(--rd)}.sc-item.md .sv{color:var(--og)}.sc-item.lo .sv{color:var(--tl)}
.plist{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}
.pcard{background:linear-gradient(135deg,#e8f0fe,#f0f4fc);border-left:3px solid var(--pr);border-radius:6px;padding:8px 12px;min-width:180px}
.pcard .pn2{font-weight:700;color:var(--pd);font-size:12.5px}.pcard .pt{font-size:11px;color:var(--tl);margin-top:2px}.pcard .pp{font-size:11.5px;color:var(--og);font-weight:600;margin-top:2px}
.sbox{background:linear-gradient(135deg,#fff8e1,#fff3cd);border:1px solid #ffc107;border-radius:8px;padding:14px;margin:12px 0;font-size:13px;line-height:1.7}
.sbox .stitle{font-weight:800;color:#e65100;font-size:13px;margin-bottom:6px}
.abox{background:linear-gradient(135deg,#e3f2fd,#bbdefb);border-left:3px solid var(--pd);border-radius:0 8px 8px 0;padding:12px 16px;margin:12px 0}
.abox .atitle{font-weight:800;color:var(--pd);font-size:13px;margin-bottom:4px}
.fr-box{background:#fafafa;border-radius:6px;padding:10px 14px;margin:8px 0}
.fr-box h4{font-size:12.5px;color:var(--pd);margin-bottom:6px}
.fr-item{background:#fff;border-left:2px solid var(--bd);padding:6px 10px;margin-bottom:4px;border-radius:0 5px 5px 0;font-size:12.5px;line-height:1.5}
.cm{position:absolute;top:10px;right:16px;font-size:26px;cursor:pointer;color:#bbb;background:none;border:none;font-family:inherit}
.cm:hover{color:var(--tx)}
.pgbar{display:flex;justify-content:space-between;align-items:center;padding:12px 16px;background:var(--cb);border-radius:var(--rad);margin-top:10px;box-shadow:var(--sh)}
.pgbar button{padding:6px 14px;border:1px solid var(--bd);border-radius:6px;background:#fff;cursor:pointer;font-size:12px;font-weight:600}
.pgbar button:hover{background:var(--pr);color:#fff;border-color:var(--pr)}
.pgbar button:disabled{opacity:.4;cursor:not-allowed}
.pgbar .pgi{font-size:12px;color:var(--tl);font-weight:600}
.pgbar .pgsz select{padding:4px 8px;border:1px solid var(--bd);border-radius:5px;font-size:12px}
.ft{text-align:center;color:var(--tl);font-size:11px;padding:16px 0;margin-top:16px}
.ld{position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(255,255,255,.95);z-index:9999;display:flex;flex-direction:column;align-items:center;justify-content:center}
.ld .spinner{width:48px;height:48px;border:4px solid #e0e0e0;border-top:4px solid var(--pr);border-radius:50%;animation:spin .6s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.ld .ldt{margin-top:18px;font-size:15px;color:var(--pd);font-weight:700}
.ld .lds{margin-top:8px;font-size:12.5px;color:var(--tl)}
@media(max-width:768px){.cr{grid-template-columns:repeat(2,1fr)}.ag{grid-template-columns:1fr}.mb{width:96%;margin:8px}}
</style>
</head>
<body>

<div class="hd">
  <h1>🎯 线索池 SDR 机会中心</h1>
  <div class="sub">投流线索 · 智能分级 · 产品推荐 · 销售话术 | 数据源:石摩「销售部线索跟进6.30 787」</div>
  <div class="ver">v3.0 · ''' + TS + r'''</div>
</div>

<div id="loading" class="ld"><div class="spinner"></div><div class="ldt">正在加载数据...</div><div class="lds">首次加载约需3-5秒，请稍候</div></div>

<div style="display:none" id="app">
<div class="cr" id="cards"></div>
<div class="fb" id="fb"></div>

<div class="ts">
  <button class="tb on" onclick="sw('l',this)">📋 机会列表 <span id="bcL" class="badge"></span></button>
  <button class="tb" onclick="sw('g',this)">📊 分级概览</button>
  <button class="tb" onclick="sw('c',this)">📡 渠道效果</button>
  <button class="tb" onclick="sw('d',this)">🏢 部门排行</button>
</div>

<div class="pn on" id="pl">
  <div class="tw"><table class="dt" id="tbl"><thead><tr id="th"></tr></thead><tbody id="tb"></tbody></table></div>
  <div class="pgbar" id="pgbar">
    <button onclick="prevPage()" id="btnPrev">◀ 上一页</button>
    <div class="pgi"><span id="pgInfo"></span></div>
    <div class="pgsz">每页<select id="pgSize" onchange="changePageSize()"><option value="50">50</option><option value="100" selected>100</option><option value="200">200</option></select>条</div>
    <button onclick="nextPage()" id="btnNext">下一页 ▶</button>
  </div>
</div>

<div class="pn" id="pg"><div class="ag" id="ga"></div></div>
<div class="pn" id="pc"><div class="ag" id="ca"></div></div>
<div class="pn" id="pd"><div class="ag" id="da"></div></div>

<div class="mo" id="mo" onclick="if(event.target===this)this.classList.remove('sh')"><div class="mb" id="mb"></div></div>
</div>

<div class="ft">线索池SDR看板 v3.0 · 数据驱动 · 分页渲染</div>

<script>
// ===== 全局状态 =====
let DATA=null, FL=[], PAGE=1, PGSIZE=100, SC='', SO=-1;
const FT={kw:'',st:'',dp:'',ch:'',lv:'',dl:'f',co:'',gr:'',ind:'',itl:'',df:'',dt:''};

// ===== 工具函数 =====
function eh(s){if(!s)return '';return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
function tgG(g,l,c){
  if(g==='S')return '<span class="tg-s">'+eh(l)+'</span>';
  if(g==='A2')return '<span class="tg-a2">'+eh(l)+'</span>';
  if(g==='A3')return '<span class="tg-a3">'+eh(l)+'</span>';
  if(g==='DEAL')return '<span class="tg-deal">已成交</span>';
  if(g==='B')return '<span class="tg-b">B</span>';
  return '<span class="tg-c">'+eh(c||'C')+'</span>';
}
function tgI(it){
  if(it==='hi'||it==='high')return '<span class="tg-hi">高</span>';
  if(it==='md'||it==='medium')return '<span class="tg-md">中</span>';
  if(it==='rj'||it==='rejected')return '<span class="tg-rj">拒</span>';
  return '<span style="background:#f0f0f0;color:#888;padding:2px 6px;border-radius:4px;font-size:11px">?</span>';
}
function tgAge(a){
  if(a==null)return '-';
  if(a<=3)return '<span style="background:#e8f5e9;color:#2e7d32;padding:1px 6px;border-radius:4px;font-size:11px;font-weight:600">'+a+'天</span>';
  if(a<=7)return '<span style="background:#e8f5e9;color:#2e7d32;padding:1px 6px;border-radius:4px;font-size:11px">'+a+'天</span>';
  if(a<=21)return a+'天';
  return '<span style="color:#dc3545;font-weight:600">'+a+'天</span>';
}

// ===== KPI卡片 =====
function rc(){
  const n=FL.length, d=FL.filter(x=>x._deal).length,
        s=FL.filter(x=>x._g==='S').length, a2=FL.filter(x=>x._g==='A2').length,
        a3=FL.filter(x=>x._g==='A3').length, b=FL.filter(x=>x._g==='B').length,
        r=n?(d/n*100):0;
  document.getElementById('cards').innerHTML =
  `<div class="cd"><div class="lb">🎯 有效线索</div><div class="vl">${n.toLocaleString()}</div><div class="sb">未成交 / 有销售价值</div></div>`+
  `<div class="cd s"><div class="lb">🔥 S级·立即</div><div class="vl">${s}</div><div class="sb">今日必跟</div></div>`+
  `<div class="cd a2"><div class="lb">⭐ A2级·重点</div><div class="vl">${a2}</div><div class="sb">3天内搞定</div></div>`+
  `<div class="cd a3"><div class="lb">● A3级·正常</div><div class="vl">${a3}</div><div class="sb">本周沟通</div></div>`+
  `<div class="cd"><div class="lb">○ B级·低优</div><div class="vl">${b}</div><div class="sb">有空再看</div></div>`+
  `<div class="cd d"><div class="lb">✅ 已成交</div><div class="vl">${d}</div><div class="sb">${r.toFixed(1)}% 转化率</div></div>`;
  const bL=document.getElementById('bcL');if(bL)bL.textContent=n.toLocaleString();
}

// ===== 筛选栏 =====
function rf(){
  const S=DATA.summary;
  const st=[...new Set(DATA.leads.map(x=>x['跟进状态']||'').filter(v=>v))],
        dp=Object.keys(S.depts||{}), ch=Object.keys(S.channels||{}),
        co=[...new Set(DATA.leads.map(x=>x['分配顾问']||'').filter(v=>v))],
        gr=['S','A2','A3','B','C'], ind=[...new Set(DATA.leads.map(x=>x['_ind']||'').filter(v=>v))].sort(),
        itl=['high','medium','low','unknown','rejected'];
  document.getElementById('fb').innerHTML =
  '<label>🔍</label><input type=text id=fk placeholder="手机号/备注/来源..." style="width:160px" oninput=af()>'
  +'<label>分级</label><select id=fgr onchange=af()><option value="">全部</option>'+gr.map(g=>'<option value="'+g+'">'+g+'</option>').join('')+'</select>'
  +'<label>状态</label><select id=fs onchange=af()><option value="">全部</option>'+st.map(s=>'<option>'+eh(s)+'</option>').join('')+'</select>'
  +'<label>部门</label><select id=fdp onchange=af()><option value="">全部</option>'+dp.map(d=>'<option>'+eh(d)+'</option>').join('')+'</select>'
  +'<label>渠道</label><select id=fch onchange=af()><option value="">全部</option>'+ch.map(c=>'<option>'+eh(c)+' ('+(S.channels[c]||0)+')</option>').join('')+'</select>'
  +'<label>意向</label><select id=fitl onchange=af()><option value="">全部</option>'
    +itl.map(t=>'<option value="'+t+'">'+(t==='high'?'高意向':t==='medium'?'中意向':t==='low'?'低意向':t==='rejected'?'已拒绝':'未知')+'</option>').join('')
  +'</select>'
  +'<label>行业</label><select id=find onchange=af()><option value="">全部</option>'+ind.slice(0,20).map(i=>'<option>'+eh(i)+'</option>').join('')+'</select>'
  +'<label>成交</label><select id=fdl onchange=af()><option value="f" selected>未成交</option><option value="t">已成交</option><option value="">全部</option></select>'
  +'<label>📅起</label><input type=date id=ffd onchange=af()> <label>至</label> <input type=date id=ftd onchange=af()> '
  +'<button class="fbtn" onclick=rst()>重置</button><button class="fbtn outline" onclick=ex()>📥 导出CSV</button>';
}

// ===== 执行筛选 =====
function af(){
  FT.kw=(document.getElementById('fk')?.value||'').toLowerCase();
  FT.gr=document.getElementById('fgr')?.value||''; FT.st=document.getElementById('fs')?.value||'';
  FT.dp=document.getElementById('fdp')?.value||''; FT.ch=document.getElementById('fch')?.value||'';
  FT.itl=document.getElementById('fitl')?.value||''; FT.ind=document.getElementById('find')?.value||'';
  FT.dl=document.getElementById('fdl')?.value||'f';
  FT.df=document.getElementById('ffd')?.value||''; FT.dt=document.getElementById('ftd')?.value||'';
  FL=DATA.leads.filter(l=>{
    if(FT.kw){
      const s=[l['手机号'],l['其他联系方式'],l['备注'],l['分配人'],l['分配顾问'],l['来源'],l['_ind'],l['f1'],l['f2']].map(v=>(v||'').toLowerCase()).join('');
      if(!s.includes(FT.kw)&&!(l['手机号']||'').includes(FT.kw))return false}
    if(FT.gr&&l._g!==FT.gr)return false;
    if(FT.st&&(l['跟进状态']||'')!==FT.st)return false;
    if(FT.dp&&(l['分配部门']||'')!==FT.dp)return false;
    if(FT.ch&&(l['渠道']||'')!==FT.ch)return false;
    if(FT.itl&&l._itl!==FT.itl)return false;
    if(FT.ind&&l._ind!==FT.ind)return false;
    if(FT.dl==='t'&&!l._deal)return false;
    if(FT.dl==='f'&&l._deal)return false;
    if(FT.df||FT.dt){
      const ds=l._ad||l['分配时间']||'',dv=ds.replace(/\./g,'-');
      if(dv&&dv.length>=10){if(FT.df&&dv<FT.df)return false;if(FT.dt&&dv>FT.dt)return false}}
    return true});
  // 默认按优先级排序
  if(!SC){SC='_gp';SO=-1}
  sortData();
  PAGE=1; rc(); rt();
}

function rst(){
  document.getElementById('fk').value='';document.getElementById('fgr').value='';
  document.getElementById('fs').value='';document.getElementById('fdp').value='';
  document.getElementById('fch').value='';document.getElementById('fitl').value='';
  document.getElementById('find').value='';document.getElementById('fdl').value='f';
  document.getElementById('ffd').value='';document.getElementById('ftd').value='';
  af();
}

function sortData(){
  if(!SC)return;
  FL.sort((a,b)=>{
    let v=a[SC]!=null?a[SC]:'',vv=b[SC]!=null?b[SC]:'';
    if(typeof v==='number')return(v-vv)*SO;
    v=String(v).toLowerCase();vv=String(vv).toLowerCase();
    return v<vv?-1*SO:v>vv?1*SO});
}

function sb(k){
  if(SC===k){SO*=-1}else{SC=k;SO=-1}
  sortData();rt();
}

// ===== 表格列定义 =====
const TC=[
  {k:'_gl',l:'分级',w:64},{k:'_sc',l:'评分',w:46},{k:'_gu',l:'紧迫',w:58},
  {k:'_itl',l:'意向',w:48,f:(l)=>tgI(l._itl)},
  {k:'_ind',l:'行业',w:65},{k:'分配部门',l:'部门',w:76},{k:'分配顾问',l:'顾问',w:62},
  {k:'渠道',l:'渠道',w:95},{k:'来源',l:'来源',w:100},
  {k:'分配时间',l:'分配',w:62,f:(l)=>tgAge(l._age_days)},{k:'手机号',l:'手机号',w:110},
];

// ===== 分页渲染表格 =====
function rt(){
  const hdrHTML=TC.map(c=>{
    const arrow=SC===c.k?' '+(SO===1?'▲':'▼'):'';
    return `<th style="width:${c.w}px"onclick="sb('${c.k}')">${c.l}${arrow}</th>`;
  }).join('')+'<th style="width:38px"></th>';

  document.getElementById('th').innerHTML=hdrHTML;

  const totalPages=Math.max(1,Math.ceil(Fl.length/PGSIZE));
  if(PAGE>totalPages)PAGE=totalPages;
  const start=(PAGE-1)*PGSIZE, end=Math.min(start+PGSIZE,Fl.length);
  const rows=Fl.slice(start,end);

  document.getElementById('tb').innerHTML=rows.map((l,idx)=>{
    const realIdx=start+idx;
    const rc=l._g==='S'?'tr-s':l._g==='A2'?'tr-a2':l._g==='A3'?'tr-a3':'';
    const cols=TC.map(c=>{
      const v=c.f?c.f(l):eh(String(l[c.k]||'-'));
      return`<td>${v}</td>`;
    }).join('');
    return`<tr class="${rc}" style="cursor:pointer" onclick="showDetail(${realIdx})" title="${eh(l._ga||'点击查看详情')}">${cols}<td><button onclick="event.stopPropagation();cp('${l['手机号']}')"style="padding:2px6px;font-size:10px;border:1px solid var(--bd);background:#fff;border-radius:4px;cursor:pointer">复制</button></td></tr>`;
  }).join('');

  // 分页信息
  document.getElementById('btnPrev').disabled=PAGE<=1;
  document.getElementById('btnNext').disabled=PAGE>=totalPages;
  document.getElementById('pgInfo').textContent=`第 ${PAGE}/${totalPages} 页 (第${start+1}-${end}条 / 共${FL.length}条)`;
}

function prevPage(){if(PAGE>1){PAGE--;rt()}}
function nextPage(){const tp=Math.ceil(FL.length/PGSIZE);if(PAGE<tp){PAGE++;rt()}}
function changePageSize(){PGSIZE=parseInt(document.getElementById('pgSize').value)||100;PAGE=1;rt()}

// ===== Tab切换 =====
function sw(t,el){
  document.querySelectorAll('.tb').forEach(b=>b.classList.remove('on'));
  document.querySelectorAll('.pn').forEach(p=>p.classList.remove('on'));
  el.classList.add('on');
  document.getElementById('p'+t)?.classList.add('on');
  if(t==='g')renderGA();if(t==='c')renderCA();if(t==='d')renderDA();
}

// ===== 分级面板 =====
function renderGA(){
  const S=DATA.summary, gd=S.grade_dist||{};
  const grades=[
    {k:'S',l:'🔥 S级-立即行动',c:'#dc3545',d:'高意向+新鲜·今日必须联系'},
    {k:'A2',l:'⭐ A2级-重点跟进',c:'#fd7e14',d:'有意向+可触达·3天内搞定'},
    {k:'A3',l:'● A3级-正常跟进',c:'#0d6efd',d:'常规有效线索·本周完成沟通'},
    {k:'B',l:'○ B级-低优队列',c:'#adb5bd',d:'能联系但信号弱·有空再刷'},
    {k:'C',l:'△ C级-暂缓淘汰',c:'#90a4ae',d:'无联系方式/已拒绝'},
    {k:'DEAL',l:'✅ 已成交',c:'#28a745',d:'已签约·转客服维护'},
  ];
  const ttl=Object.values(gd).reduce((s,n)=>s+n,0)||1;
  document.getElementById('ga').innerHTML=grades.map(g=>{
    const c=gd[g.k]||0,p=((c/ttl)*100).toFixed(1);
    return`<div class="cc"><h3>${g.l} <span style="font-size:12px;color:var(--tl);float:right;font-weight:400">${c}条 (${pct}%)</span></h3>`
      +`<div style="background:#eee;height:28px;border-radius:6px;overflow:hidden;margin:8px 0"><div style="height:100%;width:${pct}%;background:${g.c};border-radius:6px;display:flex;align-items:center;padding-left:10px"><span style="color:#fff;font-weight:800;font-size:13px">${c}</span></div></div>`
      +`<div style="font-size:12px;color:var(--tl)">${g.d}</div></div>`;
  }).join('')+(
  `<div class="cc" style="grid-column:1/-1"><h3>📌 分级标准说明</h3>`
  +`<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:8px;font-size:12px">`
  +`<div style="background:var(--s-bg);border-radius:6px;padding:10px;border-left:3px solid #dc3545"><strong>S级</strong>(≥24分或高意向+≤14天)<br>⚡ 今日必跟! 高意向且新鲜度高<br>👉 立即回电/微信推动下一步</div>`
  +`<div style="background:var(--a2-bg);border-radius:6px;padding:10px;border-left:3px solid #e67700"><strong>A2级</strong>(≥19分或中意向+可触达)<br>📞 48小时内二次触达 推演示<br>👉 发产品资料→预约远程演示</div>`
  +`<div style="background:var(--a3-bg);border-radius:6px;padding:10px;border-left:3px solid #0d6efd"><strong>A3级</strong>(≥14分或有跟进记录)<br>📋 本周完成一次有效沟通<br>👉 了解需求→匹配产品方案</div>`
  +`<div style="background:var(--b-bg);border-radius:6px;padding:10px;border-left:3px solid #6c757d"><strong>B/C级</strong>(&lt;9分或无效信息)<br>🔄 批量外呼筛选 / ⏸️ 暂缓处理<br>👉 补充联系方式后再评估</div>`
  +`</div></div>`);
}

// ===== 渠道分析 =====
function renderCA(){
  const S=DATA.summary, cv=S.ch_conv||{};
  const items=Object.entries(cv).sort((a,b)=>b[1].t-a[1].t),ttl=S.total||1;
  document.getElementById('ca').innerHTML=`<div class="cc" style="grid-column:1/-1"><h3>📡 渠道线索 × 成交转化</h3>${
    items.map(([k,v])=>`<div class="br"><div class="bl">${eh(k.substring(0,14))}</div><div class="bt"><div class="bf pr" style="width:${v.t/ttl*100}%"><span class="bv">${v.t}条</span></div></div><div class="bp">${v.r}% (${v.d}单)</div></div>`).join('')
  }</div>`;
}

// ===== 部门排行 =====
function renderDA(){
  const S=DATA.summary, dv=S.dp_conv||{};
  const items=Object.entries(dv).sort((a,b)=>b[1].d-a[1].d), mx=Math.max(...items.map(x=>x[1].t));
  document.getElementById('da').innerHTML=`<div class="cc" style="grid-column:1/-1"><h3>🏢 部门线索 × 成交数</h3>${
    items.slice(0,20).map(([k,v])=>`<div class="br"><div class="bl" style="width:82px">${eh(k.substring(0,10))}</div><div class="bt"><div class="bf cg" style="width:${mx?v.t/mx*100:0}%"><span class="bv">${v.t}条/${v.d}成</span></div></div><div class="bp">${v.r}%</div></div>`).join('')
  }}</div>`;
}

// ===== 详情弹窗（用索引直接取数据，不用indexOf）=====
function showDetail(idx){
  const l=FL[idx]; if(!l)return;
  const mo=document.getElementById('mo'), mb=document.getElementById('mb');

  // 评分明细
  let scItems='';
  const scores=l._scd||{};
  if(scores && Object.keys(scores).length){
    scItems=Object.entries(scores).map(([k,v])=>{
      const cl=v>=4?'hi':v>=3?'md':'lo';
      return`<div class="sc-item ${cl}"><div class="sn">${k}</div><div class="sv">${v}</div></div>`;
    }).join('');
  }

  // 产品推荐
  let prods='';
  if(l._pds&&l._pds.length){
    prods=l._pds.map(p=>`<div class="pcard"><div class="pn2">📦 ${eh(p.n)}</div><div class="pt">${eh(p.c)} | ${eh(p.d||'')}</div><div class="pp">${eh(p.pr||'')}</div></div>`).join('');
  }

  // 跟进记录
  let frs='';
  [l.f1,l.f2,l.f3,l.f4].forEach((fv,n)=>{
    if(fv) frs+=`<div class="fr-item"><strong>${['一','二','三','四'][n]}次:</strong> ${eh(fv)}</div>`;
  });

  mb.innerHTML=
  `<button class="cm" onclick="document.getElementById('mo').classList.remove('sh')">&times;</button>`
  +`<h2>📞 线索详情 <span style="font-size:13px;font-weight:400;color:var(--tl)">${eh(l['手机号'])}</span> ${tgG(l._g,l._gl)}</h2>`
  +`<div class="dg">`
    +`<div class="dl">分级</div><div style="font-weight:700;color:${l._gc};font-size:15px">${eh(l._gl)}</div>`
    +`<div class="dl">总评分</div><div style="font-weight:800;color:var(--pd);font-size:19px">${l._sc}/30</div>`
    +`<div class="dl">紧迫度</div><div>${eh(l._gu)}</div>`
    +`<div class="dl">意向</div><div>${tgI(l._itl)}</div>`
    +`<div class="dl">推断行业</div><div><strong>${eh(l._ind)}</strong> (匹配度:${l._isc||'-'}/5)</div>`
    +`<div class="dl">规模推测</div><div>${eh(l._scl||'-')}</div>`
    +`<div class="dl">渠道</div><div>${eh(l['渠道'])}</div>`
    +`<div class="dl">来源</div><div>${eh(l['来源'])}</div>`
    +`<div class="dl">分配部门</div><div>${eh(l['分配部门'])}</div>`
    +`<div class="dl">分配顾问</div><div>${eh(l['分配顾问'])}</div>`
    +`<div class="dl">登记人</div><div>${eh(l['分配人'])}</div>`
    +`<div class="dl">分配时间</div><div>${eh(l['分配时间'])}${tgAge(l._age_days)}</div>`
    +`<div class="dl">跟进状态</div><div>${eh(l['跟进状态'])}</div>`
    +`<div class="dl">线索级别</div><div>${eh(l['线索级别'])}</div>`
    +`<div class="dl">手机号</div><div class="ph">${eh(l['手机号'])}</div>`
    +`<div class="dl">其他联系方式</div><div>${eh(l['其他联系方式'])}</div>`
    +`<div class="dl">成交</div><div>${l._deal?'<span class="tg-deal">已成交 ¥'+l._amt:'<span class="tg-c">未成交</span>'}</div>`
  +`</div>`
  +(scItems?`<h3 style="margin-top:16px;color:var(--pd);font-size:14.5px">📊 六维评分明细</h3><div class="sc-box">${scItems}</div><div style="font-size:11.5px;color:var(--tl);margin:3px 0">${(l._scr||[]).join(' | ')}</div>`:'')
  +(prods?`<h3 style="margin-top:14px;color:var(--pd);font-size:14.5px">📦 推荐产品（基于画像匹配）</h3><div class="plist">${prods}</div>`:'')
  +((l._pns&&l._pns.length)?`<h3 style="margin-top:12px;color:var(--pd);font-size:14.5px">🔍 识别痛点</h3><div style="display:flex;gap:6px;flex-wrap:wrap;margin:6px 0">${l._pns.map(p=>`<span style="background:#fce4ec;color:#dc3545;padding:3px 10px;border-radius:5px;font-size:12px;font-weight:600">${eh(p)}</span>`).join('')}</div>`:'')
  +`<div class="sbox"><div class="stitle">🎤 销售话术（可直接念给客户）</div><div style="white-space:pre-line;color:#333">${eh(l._fs||'暂无话术')}</div></div>`
  +`<div class="abox"><div class="atitle">⏭️ 建议动作</div><div>${eh(l._ga||'')}</div></div>`
  +(frs?`<div class="fr-box"><h4>📝 跟进记录</h4>${frs}</div>`:'')
  +(l['备注']?`<div style="margin:10px 0;padding:8px 12px;background:#f5f5f5;border-radius:6px;font-size:12px"><strong style="color:var(--tl)">备注:</strong> ${eh(l['备注'])}</div>`:'')
  +`<div style="margin-top:14px;display:flex;gap:8px">`
    +`<button onclick="cp('${l['手机号']}')"style="padding:8px 18px;background:var(--pr);color:#fff;border:none;border-radius:6px;cursor:pointer;font-weight:700;font-size:12px">📋 复制手机号</button>`
    +`<button onclick="cpScript(${idx})"style="padding:8px 18px;background:var(--og);color:#fff;border:none;border-radius:6px;cursor:pointer;font-weight:700;font-size:12px">📝 复制话术</button>`
  +`</div>`;
  mo.classList.add('sh');
}

function cp(p){navigator.clipboard.writeText(p||'').then(()=>alert('✅ 已复制'))}
function cpScript(idx){const l=FL[idx];navigator.clipboard.writeText(l._fs||'').then(()=>alert('✅ 已复制话术'))}

// ===== 导出CSV =====
function ex(){
  const hdr=['分级','评分','紧迫度','意向','行业','部门','顾问','渠道','来源','分配时间','手机号','建议动作'];
  const rows=FL.map(l=>[l._gl,l._sc,l._gu,l._itl,l._ind,l['分配部门'],l['分配顾问'],l['渠道'],l['来源'],l['分配时间'],l['手机号'],l._ga]
    .map(v=>`"${String(v||'-').replace(/"/g,'\"')}"`));
  const csv='\uFEFF'+[hdr,...rows].join('\n');
  const blob=new Blob([csv],{type:'text/csv;charset=utf-8'}),url=URL.createObjectURL(blob);
  const a=document.createElement('a');a.href=url;a.download='线索池机会清单_'+new Date().toISOString().slice(0,10)+'.csv';a.click();URL.revokeObjectURL(url);
}

// ===== 初始化：异步加载数据 =====
async function init(){
  try {
    const resp = await fetch('./lead_pool_data.json');
    DATA = await resp.json();

    // 隐藏loading 显示内容
    document.getElementById('loading').style.display='none';
    document.getElementById('app').style.display='block';

    // 初始化
    af(); // 触发默认筛选(未成交)
  } catch(e) {
    document.querySelector('#loading .ldt').textContent='❌ 加载失败';
    document.querySelector('#loading .lds').textContent=e.message+'\n请确保 lead_pool_data.json 在同目录下';
  }
}
init();
</script>
</body>
</html>'''

with open(OUTPUT_HTML,'w',encoding='utf-8') as f: f.write(HTML)
hsz=os.path.getsize(OUTPUT_HTML)/1024
print(f'\n{"="*60}')
print(f'✅ 完成!')
print(f'   HTML: {OUTPUT_HTML} ({hsz:.0f}KB)')
print(f'   Data: {OUTPUT_DATA} ({dsz:.1f}MB)')
print(f'   线索: {len(leads)} 条 | 有效未成交: {active} 条')
print(f'   S={stats["S"]} A2={stats["A2"]} A3={stats["A3"]} B={stats["B"]} C={stats["C"]}')
print(f'{"="*60}')
