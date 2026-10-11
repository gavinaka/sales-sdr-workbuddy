#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SDR Web Flask 主程序
让BD在线查看客户分级、实时填写回访记录、自动迭代分级。
"""
import json
import os
import sqlite3
from datetime import datetime, timedelta
from collections import Counter

from flask import Flask, render_template, request, jsonify, g

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'sdr.db')

app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['JSON_AS_ASCII'] = False

BD_NAMES = ['潘飞', '吴云凤', '王胜学', '吴必川']
VISIT_RESULTS = [
    '已联系·有意向', '已联系·无意向', '已联系·待跟进',
    '未接听·电话', '未接听·微信', '拒绝·不要了', '号码错误', '已成交'
]
SUB_GRADE_ORDER = {'S': 0, 'A2': 1, 'A3': 2, 'B': 3, 'C': 4}


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop('db', None)
    if db is not None:
        db.close()


# ==================== 路由 ====================
@app.route('/')
def dashboard():
    db = get_db()
    today = datetime.now().strftime('%Y-%m-%d')

    total = db.execute('SELECT COUNT(*) c FROM customers').fetchone()['c']
    s_cnt = db.execute("SELECT COUNT(*) c FROM customers WHERE sub_grade='S'").fetchone()['c']
    a2_cnt = db.execute("SELECT COUNT(*) c FROM customers WHERE sub_grade='A2'").fetchone()['c']
    a3_cnt = db.execute("SELECT COUNT(*) c FROM customers WHERE sub_grade='A3'").fetchone()['c']
    b_cnt = db.execute("SELECT COUNT(*) c FROM customers WHERE sub_grade='B'").fetchone()['c']
    c_cnt = db.execute("SELECT COUNT(*) c FROM customers WHERE sub_grade='C'").fetchone()['c']
    total_pay = db.execute('SELECT COALESCE(SUM(pay_amount),0) s FROM customers').fetchone()['s']

    # 7天内到期数
    seven_days_later = (datetime.now() + timedelta(days=7)).timestamp() * 1000
    expiring_7 = 0
    for row in db.execute('SELECT services FROM customers'):
        try:
            svcs = json.loads(row['services']) if row['services'] else []
            for s in svcs:
                d = s.get('days_to_expire')
                if d is not None and 0 <= d <= 7:
                    expiring_7 += 1
                    break
        except:
            pass

    today_visited = db.execute(
        "SELECT COUNT(DISTINCT cid) c FROM visit_records WHERE date(created_at)=date('now','localtime')"
    ).fetchone()['c']

    # 行业TOP10
    ind_rows = db.execute(
        'SELECT industry, COUNT(*) c FROM customers GROUP BY industry ORDER BY c DESC LIMIT 10'
    ).fetchall()
    industry_top = [{'name': r['industry'], 'count': r['c']} for r in ind_rows]

    # 业务类型分布
    biz_rows = db.execute(
        'SELECT biz_type, COUNT(*) c FROM customers GROUP BY biz_type ORDER BY c DESC'
    ).fetchall()
    biz_dist = [{'name': r['biz_type'], 'count': r['c']} for r in biz_rows]

    kpi = {
        'total': total, 's': s_cnt, 'a2': a2_cnt, 'a3': a3_cnt,
        'b': b_cnt, 'c': c_cnt,
        'total_pay': round(total_pay, 0),
        'expiring_7': expiring_7,
        'today_visited': today_visited,
    }

    grade_dist = [
        {'name': 'S级必跟', 'count': s_cnt, 'color': '#F8D7DA'},
        {'name': 'A2重点', 'count': a2_cnt, 'color': '#FCE4C4'},
        {'name': 'A3常规A', 'count': a3_cnt, 'color': '#FFF3E0'},
        {'name': 'B级', 'count': b_cnt, 'color': '#FFEB9C'},
        {'name': 'C级', 'count': c_cnt, 'color': '#C6EFCE'},
    ]

    return render_template('dashboard.html', kpi=kpi, grade_dist=grade_dist,
                           industry_top=industry_top, biz_dist=biz_dist,
                           bd_names=BD_NAMES)


@app.route('/customers')
def customers():
    db = get_db()
    page = request.args.get('page', 1, type=int)
    grade = request.args.get('grade', '全部')
    industry = request.args.get('industry', '')
    keyword = request.args.get('q', '').strip()

    where = []
    params = []
    if grade and grade != '全部':
        where.append('sub_grade = ?')
        params.append(grade)
    if industry:
        where.append('industry = ?')
        params.append(industry)
    if keyword:
        where.append('(name LIKE ? OR contact LIKE ? OR cid LIKE ?)')
        kw = f'%{keyword}%'
        params.extend([kw, kw, kw])

    where_sql = (' WHERE ' + ' AND '.join(where)) if where else ''

    # 排序：按sub_grade(S>A2>A3>B>C) + 机会分
    order_sql = " ORDER BY CASE sub_grade WHEN 'S' THEN 0 WHEN 'A2' THEN 1 WHEN 'A3' THEN 2 WHEN 'B' THEN 3 ELSE 4 END, opportunity_score DESC, score DESC"

    per_page = 50
    offset = (page - 1) * per_page

    total = db.execute(f'SELECT COUNT(*) c FROM customers{where_sql}', params).fetchone()['c']
    rows = db.execute(
        f'SELECT * FROM customers{where_sql}{order_sql} LIMIT ? OFFSET ?',
        params + [per_page, offset]
    ).fetchall()

    # 手机号脱敏：name/contact字段如本身含手机号也脱敏
    import re as _re
    def _mask_phone(text):
        if not text:
            return text
        return _re.sub(r'1[3-9]\d{9}', lambda m: m.group()[:3] + '****' + m.group()[-4:], str(text))

    masked_rows = []
    for r in rows:
        rd = dict(r)
        rd['name'] = _mask_phone(rd.get('name', ''))
        rd['contact'] = _mask_phone(rd.get('contact', ''))
        rd['phone'] = ''  # 完整号码不传前端
        masked_rows.append(rd)
    rows = masked_rows

    # 行业列表（去重）
    ind_rows = db.execute(
        'SELECT DISTINCT industry FROM customers ORDER BY industry'
    ).fetchall()
    industries = [r['industry'] for r in ind_rows]

    total_pages = max(1, (total + per_page - 1) // per_page)

    return render_template('customers.html',
                           customers=rows, total=total, page=page,
                           total_pages=total_pages,
                           grades=['全部', 'S', 'A2', 'A3', 'B', 'C'],
                           current_grade=grade,
                           industries=industries,
                           current_industry=industry,
                           keyword=keyword,
                           bd_names=BD_NAMES)


@app.route('/customer/<cid>')
def customer_detail(cid):
    db = get_db()
    c = db.execute('SELECT * FROM customers WHERE cid=?', (cid,)).fetchone()
    if not c:
        return '客户不存在', 404

    services = json.loads(c['services']) if c['services'] else []
    expiring = json.loads(c['expiring_services']) if c['expiring_services'] else []

    visits = db.execute(
        'SELECT * FROM visit_records WHERE cid=? ORDER BY created_at DESC',
        (cid,)
    ).fetchall()

    # 手机号脱敏：中间4位星号（189****5261）·看板不暴露完整号码
    import re as _re
    def _mask_phone(text):
        if not text:
            return text
        return _re.sub(r'1[3-9]\d{9}', lambda m: m.group()[:3] + '****' + m.group()[-4:], str(text))

    c_dict = dict(c)
    c_dict['name'] = _mask_phone(c_dict.get('name', ''))
    c_dict['contact'] = _mask_phone(c_dict.get('contact', ''))
    phone = c_dict.get('phone', '') or ''
    if len(phone) >= 11:
        c_dict['phone_masked'] = phone[:3] + '****' + phone[-4:]
    else:
        c_dict['phone_masked'] = '****'
    c_dict['phone'] = ''  # 完整号码不传给前端

    return render_template('customer_detail.html', c=c_dict, services=services,
                           expiring=expiring, visits=visits,
                           visit_results=VISIT_RESULTS,
                           bd_names=BD_NAMES)


# ==================== API ====================
@app.route('/api/visit', methods=['POST'])
def api_visit():
    db = get_db()
    data = request.get_json(silent=True, force=True) or request.form
    cid = (data.get('cid') or '').strip()
    bd_name = (data.get('bd_name') or '').strip()
    result = (data.get('result') or '').strip()
    note = (data.get('note') or '').strip()
    next_date = (data.get('next_date') or '').strip()
    deal = (data.get('deal') or '否').strip()

    if not cid or not bd_name or not result:
        return jsonify({'ok': False, 'msg': '缺少必填字段(cid/bd_name/result)'}), 400

    cust = db.execute('SELECT cid, sub_grade FROM customers WHERE cid=?', (cid,)).fetchone()
    if not cust:
        return jsonify({'ok': False, 'msg': '客户不存在'}), 404

    db.execute(
        'INSERT INTO visit_records (cid, bd_name, result, note, next_date, deal) VALUES (?,?,?,?,?,?)',
        (cid, bd_name, result, note, next_date or None, deal)
    )

    # 自动迭代分级
    new_grade = cust['sub_grade']
    grade_changed = False
    if result == '已联系·有意向':
        new_grade = 'S'
        grade_changed = new_grade != cust['sub_grade']
    elif result in ('已联系·无意向', '拒绝·不要了', '已成交'):
        new_grade = 'C'
        grade_changed = new_grade != cust['sub_grade']

    if grade_changed:
        db.execute(
            'UPDATE customers SET sub_grade=?, updated_at=? WHERE cid=?',
            (new_grade, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), cid)
        )

    db.commit()
    return jsonify({
        'ok': True,
        'msg': '回访记录已提交',
        'grade_changed': grade_changed,
        'new_grade': new_grade,
        'old_grade': cust['sub_grade']
    })


@app.route('/api/visits/<cid>')
def api_visits(cid):
    db = get_db()
    rows = db.execute(
        'SELECT * FROM visit_records WHERE cid=? ORDER BY created_at DESC',
        (cid,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])


if __name__ == '__main__':
    if not os.path.exists(DB_PATH):
        print('数据库不存在，请先运行 init_db.py')
    else:
        print(f'数据库: {DB_PATH}')
        # 云端部署：host='0.0.0.0' 监听所有网卡，BD可通过公网IP访问
        host = os.environ.get('HOST', '0.0.0.0')
        port = int(os.environ.get('PORT', 5000))
        print(f'启动: http://{host}:{port}/')
        app.run(host=host, port=port, debug=False)
