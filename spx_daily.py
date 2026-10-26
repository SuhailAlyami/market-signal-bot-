"""Offline daily SPX research forecasts. No broker, notification or order access."""
import argparse
from contextlib import closing
import hashlib
import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import pandas_market_calendars as mcal
from flask import Flask, jsonify, Response

VERSION = 'spx-daily-structure-v2'
BASELINE_VERSION = 'spx-daily-analog-v1'

def schedule(start, end):
    return mcal.get_calendar('NYSE').schedule(start_date=start, end_date=end)

def direction(change, atr):
    return 'Bullish' if change > .1*atr else 'Bearish' if change < -.1*atr else 'Sideways'

def features(rows, structure=True):
    f = pd.DataFrame(rows).copy()
    prev = f.close.shift(1)
    tr = pd.concat([f.high-f.low, (f.high-prev).abs(), (f.low-prev).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    resistance = f.high.rolling(20).max()
    support = f.low.rolling(20).min()
    x = pd.DataFrame({'body':(f.close-f.open)/atr, 'range':(f.high-f.low)/atr,
        'trend':(f.close-f.close.shift(5))/atr,
        'volatility':f.close.pct_change().rolling(20).std()*f.close/atr,
        'support':(f.close-support)/atr,'resistance':(resistance-f.close)/atr})
    if structure:
        prior_hi=f.high.shift(1).rolling(20).max()
        prior_lo=f.low.shift(1).rolling(20).min()
        x['close_location']=(f.close-f.low)/(f.high-f.low).replace(0,np.nan)
        x['upper_rejection']=(f.high-f[['open','close']].max(axis=1))/atr
        x['lower_rejection']=(f[['open','close']].min(axis=1)-f.low)/atr
        x['structure_up']=((f.high>f.high.shift(1)) & (f.low>f.low.shift(1))).astype(float)
        x['structure_down']=((f.high<f.high.shift(1)) & (f.low<f.low.shift(1))).astype(float)
        x['failed_high']=((f.high>prior_hi) & (f.close<prior_hi)).astype(float)
        x['failed_low']=((f.low<prior_lo) & (f.close>prior_lo)).astype(float)
    # SPX is an index: volume is optional, never invented or proxied silently.
    return f, x, atr

def forecast(rows, structure=True):
    if len(rows) < 81:
        raise ValueError('need at least 81 complete native SPX daily sessions')
    f,x,atr = features(rows, structure)
    valid = np.flatnonzero(np.isfinite(x.to_numpy()).all(axis=1) & (atr.to_numpy()>0))
    if len(f)-1 not in valid: raise ValueError('invalid latest features')
    train = valid[valid < len(f)-1]  # labels only for already completed next sessions
    if len(train)<40:
        raise ValueError('insufficient training examples')
    scale = x.iloc[train].std().replace(0,1).fillna(1)
    distance = (((x.iloc[train]-x.iloc[-1])/scale)**2).sum(axis=1)
    neighbors = distance.sort_values(kind='stable').index[:min(40,len(train))].to_numpy()
    labels=[direction(f.close.iloc[i+1]-f.close.iloc[i],atr.iloc[i]) for i in neighbors]
    counts={k:labels.count(k) for k in ('Bullish','Bearish','Sideways')}
    predicted=max(counts,key=counts.get)
    hi=np.array([(f.high.iloc[i+1]-f.close.iloc[i])/atr.iloc[i] for i in neighbors])
    lo=np.array([(f.low.iloc[i+1]-f.close.iloc[i])/atr.iloc[i] for i in neighbors])
    c=float(f.close.iloc[-1]); a=float(atr.iloc[-1])
    return {'direction':predicted,'confidence':None,
        'analog_agreement':round(100*counts[predicted]/len(labels),2),
        'predicted_high':round(c+a*float(np.median(hi)),2),
        'predicted_low':round(c+a*float(np.median(lo)),2),
        'high_interval':[round(c+a*float(v),2) for v in np.quantile(hi,[.1,.9])],
        'low_interval':[round(c+a*float(v),2) for v in np.quantile(lo,[.1,.9])],
        'high_confidence':None,'low_confidence':None,'atr':a,
        'volume_used':False,'status':'RESEARCH_NOT_VALIDATED','model_version':VERSION if structure else BASELINE_VERSION,
        'reference_high':float(f.high.iloc[-20:].max()),
        'reference_low':float(f.low.iloc[-20:].min())}

def connect(path):
    db=sqlite3.connect(path)
    db.execute('CREATE TABLE IF NOT EXISTS bars (date TEXT PRIMARY KEY, payload TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS predictions (date TEXT PRIMARY KEY, issued_at TEXT NOT NULL, as_of TEXT NOT NULL, payload TEXT NOT NULL, actual_high REAL, actual_low REAL, direction_accuracy INTEGER, high_error REAL, low_error REAL)')
    return db

def ingest(db, document, now=None):
    now=pd.Timestamp(now or datetime.now(timezone.utc))
    if now.tzinfo is None: raise ValueError('timezone required')
    if document.get('symbol')!='SPX' or document.get('security_type')!='IND' or document.get('source')!='IBKR':
        raise ValueError('require native IBKR SPX IND provenance')
    rows=document['bars']
    dates=[r['date'] for r in rows]
    if dates != sorted(set(dates)): raise ValueError('dates must be unique and ascending')
    if not rows: raise ValueError('empty bars')
    cal=schedule(dates[0], dates[-1])
    session_dates={str(d.date()):v.market_close for d,v in cal.iterrows()}
    for row in rows:
        d=row['date']; values=[float(row[k]) for k in ('open','high','low','close')]
        o,h,l,c=values
        if not all(np.isfinite(values)) or min(values)<=0 or not l<=min(o,c)<=max(o,c)<=h:
            raise ValueError('invalid OHLC')
        if d not in session_dates or session_dates[d]>now: raise ValueError('session incomplete or invalid')
        previous=db.execute('SELECT payload FROM bars WHERE date=?',(d,)).fetchone()
        encoded=json.dumps(row,sort_keys=True)
        if previous and previous[0]!=encoded: raise ValueError('revision requires explicit new dataset; original preserved')
    known={r[0] for r in db.execute('SELECT date FROM bars')}
    all_dates=sorted(known|set(dates))
    expected=[str(d.date()) for d in schedule(all_dates[0],all_dates[-1]).index]
    if all_dates!=expected: raise ValueError('missing trading session')
    with db:
        for row in rows: db.execute('INSERT OR IGNORE INTO bars VALUES (?,?)',(row['date'],json.dumps(row,sort_keys=True)))
    # Score ONLY forecasts issued before the target session opened.
    all_rows=[json.loads(r[0]) for r in db.execute('SELECT payload FROM bars ORDER BY date')]
    for i,row in enumerate(all_rows):
        p=db.execute('SELECT issued_at,payload FROM predictions WHERE date=? AND actual_high IS NULL',(row['date'],)).fetchone()
        if not p or not i: continue
        opening=schedule(row['date'],row['date']).iloc[0].market_open
        if pd.Timestamp(p[0])>=opening: continue
        pred=json.loads(p[1]); actual=direction(row['close']-all_rows[i-1]['close'],pred['atr'])
        with db: db.execute('UPDATE predictions SET actual_high=?,actual_low=?,direction_accuracy=?,high_error=?,low_error=? WHERE date=?',
            (row['high'],row['low'],int(actual==pred['direction']),pred['predicted_high']-row['high'],pred['predicted_low']-row['low'],row['date']))
    return all_rows

def issue(db, now=None):
    now=pd.Timestamp(now or datetime.now(timezone.utc))
    if now.tzinfo is None: raise ValueError('timezone required')
    rows=[json.loads(r[0]) for r in db.execute('SELECT payload FROM bars ORDER BY date')]
    if not rows: raise ValueError('WAIT_DATA')
    last=rows[-1]['date']
    if schedule(last,last).iloc[0].market_close>now: raise ValueError('incomplete source session')
    future=schedule(pd.Timestamp(last)+pd.Timedelta(days=1),pd.Timestamp(last)+pd.Timedelta(days=15))
    target=str(future.index[0].date())
    if now>=future.iloc[0].market_open: raise ValueError('latest completed session missing or forecast deadline passed')
    prior=db.execute('SELECT payload FROM predictions WHERE date=?',(target,)).fetchone()
    if prior: return json.loads(prior[0])
    p=forecast(rows); p.update(date=target,as_of=last,issued_at=now.isoformat(),
        input_sha256=hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest())
    # Expanding-window learner: each newly completed session adds one labeled analog.
    # Confidence is empirical prior prospective accuracy, not neighbor agreement.
    outcomes=[r[0] for r in db.execute("SELECT direction_accuracy FROM predictions WHERE direction_accuracy IS NOT NULL AND json_extract(payload,'$.direction')=? AND json_extract(payload,'$.model_version')=?",(p['direction'],VERSION))]
    if len(outcomes)>=30: p['confidence']=round(100*sum(outcomes)/len(outcomes),2)
    p['confidence_samples']=len(outcomes)
    evaluated=db.execute("SELECT payload,actual_high,actual_low FROM predictions WHERE actual_high IS NOT NULL AND json_extract(payload,'$.model_version')=?",(VERSION,)).fetchall()
    if len(evaluated)>=30:
        for key,column in (('high',1),('low',2)):
            hits=[json.loads(r[0])[key+'_interval'][0]<=r[column]<=json.loads(r[0])[key+'_interval'][1] for r in evaluated]
            p[key+'_confidence']=round(100*sum(hits)/len(hits),2)
    with db: db.execute('INSERT INTO predictions(date,issued_at,as_of,payload) VALUES (?,?,?,?)',(target,p['issued_at'],last,json.dumps(p)))
    return p

def walk_forward(rows):
    """Fixed v1 chronological diagnostic; never used as prospective calibration."""
    results=[]
    for n in range(81,len(rows)):
        p=forecast(rows[:n]); actual=rows[n]
        p.update(date=actual['date'], actual_high=actual['high'],actual_low=actual['low'],
            direction_accuracy=int(p['direction']==direction(actual['close']-rows[n-1]['close'],p['atr'])),
            high_error=p['predicted_high']-actual['high'],low_error=p['predicted_low']-actual['low'])
        results.append(p)
    return {'model':VERSION,'status':'DEVELOPMENT_ONLY','results':results,
        'count':len(results),'direction_accuracy':float(np.mean([r['direction_accuracy'] for r in results])) if results else None,
        'high_mae':float(np.mean([abs(r['high_error']) for r in results])) if results else None,
        'low_mae':float(np.mean([abs(r['low_error']) for r in results])) if results else None}

def records(db):
    db.row_factory=sqlite3.Row
    return [dict(r) for r in db.execute('SELECT * FROM predictions ORDER BY date')]

def create_app(db_path):
    app=Flask(__name__)
    @app.get('/prediction/tomorrow')
    def tomorrow():
        with closing(connect(db_path)) as db:
            row=db.execute('SELECT payload FROM predictions ORDER BY date DESC LIMIT 1').fetchone()
        if not row: return jsonify(error='WAIT_DATA'),503
        p=json.loads(row[0]); close=schedule(p['date'],p['date']).iloc[0].market_close
        if pd.Timestamp.now(tz='UTC')>=close: return jsonify(error='STALE_PREDICTION'),503
        return jsonify(p)
    @app.get('/performance')
    def performance():
        with closing(connect(db_path)) as db: data=records(db)
        return jsonify(data)
    @app.get('/')
    def dashboard():
        return Response(DASHBOARD,mimetype='text/html')
    return app

DASHBOARD='''<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8"><title>سهيل — توقع الجلسة</title><style>body{font:18px system-ui;background:#101827;color:#edf3ff;max-width:1000px;margin:40px auto;padding:20px}pre{white-space:pre-wrap}table{width:100%;border-collapse:collapse}td,th{padding:10px;border-bottom:1px solid #456}svg{width:100%;height:180px}</style><h1>توقع جلسة SPX القادمة</h1><p>بحث تجريبي — لم تثبت الدقة. نسب الثقة غير المتاحة تظهر null.</p><pre id="latest"></pre><h2>الأداء الشهري</h2><table id="stats"></table><h2>متوسط خطأ الحدود المطلق التراكمي بالنقاط</h2><svg id="chart" viewBox="0 0 900 180"></svg><p id="empty"></p><script>Promise.all([fetch('/prediction/tomorrow').then(r=>r.json()),fetch('/performance').then(r=>r.json())]).then(([p,rows])=>{latest.textContent=JSON.stringify(p,null,2);let months={},points=[],total=0;rows.filter(r=>r.actual_high!==null).forEach((r,i)=>{let m=r.date.slice(0,7);(months[m]??=[]).push(r);total+=(Math.abs(r.high_error)+Math.abs(r.low_error))/2;points.push(total/(i+1))});stats.innerHTML='<tr><th>الشهر</th><th>العدد</th><th>صحة الاتجاه</th><th>خطأ القمة المطلق</th><th>خطأ القاع المطلق</th></tr>'+Object.entries(months).map(([m,a])=>'<tr><td>'+m+'</td><td>'+a.length+'</td><td>'+(100*a.reduce((s,r)=>s+r.direction_accuracy,0)/a.length).toFixed(1)+'%</td><td>'+(a.reduce((s,r)=>s+Math.abs(r.high_error),0)/a.length).toFixed(2)+'</td><td>'+(a.reduce((s,r)=>s+Math.abs(r.low_error),0)/a.length).toFixed(2)+'</td></tr>').join('');if(!points.length){empty.textContent='لا توجد نتائج فعلية مقيمة بعد';return}let max=Math.max(...points,1);chart.innerHTML='<polyline fill="none" stroke="#65d5ff" stroke-width="3" points="'+points.map((v,i)=>(20+i*860/Math.max(points.length-1,1))+','+(160-v/max*140)).join(' ')+'"/>';}).catch(()=>{empty.textContent='تعذر تحميل البيانات'});</script></html>'''

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--db',default='.hunter-state/spx-daily.sqlite')
    parser.add_argument('--watch-seconds',type=int,default=0)
    parser.add_argument('--import-json'); parser.add_argument('--serve',action='store_true')
    args=parser.parse_args(); Path(args.db).parent.mkdir(parents=True,exist_ok=True)
    if args.import_json:
        while True:
            with closing(connect(args.db)) as db:
                ingest(db,json.loads(Path(args.import_json).read_text(encoding='utf-8')))
                try: print(json.dumps(issue(db)))
                except ValueError as exc: print(json.dumps({'status':'WAIT_DATA','reason':str(exc)}))
            if not args.watch_seconds: break
            time.sleep(max(60,args.watch_seconds))
    if args.serve: create_app(args.db).run(host='127.0.0.1',port=5050)
