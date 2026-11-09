"""Exploratory veto of existing frozen-policy events; no refit, no alert changes."""
import sys,json,hashlib
from pathlib import Path
import numpy as np,pandas as pd
P=Path(__file__).resolve().parent
sys.path.insert(0,str(P.parent/'multiframe_unified'))
import run as base

def conditions(d,f,side):
    ema=d.close-f.distance_ema20*d.atr
    # Trend of the LEVEL over 25 minutes, not the decision candle colour.
    trend=(side*f.slope_ema20>0)&(side*(f.channel_position20-.5)>0)
    touched=((d.low<=ema)&(d.high>=ema)).groupby(d.seg).transform(lambda x:x.rolling(3,min_periods=3).max()).fillna(0)>0
    retest=touched&(side*(d.close-ema)>0)
    return trend,trend&retest

def main():
    protocol={'status':'EXPLORATORY_NOT_READY','hypothesis':'Veto existing event if level trend disagrees; stricter variant also requires EMA20 touch in last3 closed bars and recovery on signal side.',
      'rules_attempted':2,'parameters':'EMA20, slope5 bars, prior20 channel midpoint, touch window3 bars; fixed before computation, no grid search',
      'selection_data':'Previously consumed archival 5m data only; Nov3 forward checkpoint excluded.',
      'comparison':'Same 12 scored price-selective walkforward events, from5 DIFFERENT models. Veto-only; original cooldown still applies even to rejected events. Not a full rerun with regenerated events.',
      'outcome':'signed SPX close change after30min; no options PnL or 70percent adoption claim',
      'future':'No automatic replacement of frozen candidate. Fresh prospective comparison required.'}
    (P/'PROTOCOL.json').write_text(json.dumps(protocol,indent=2));(P/'PROTOCOL.sha256').write_text(hashlib.sha256((P/'PROTOCOL.json').read_bytes()).hexdigest())
    d,e=base.prepare(base.raw(base.P/'raw/SPX_FIVE_MINS.json'),base.raw(base.P/'raw/ES_FIVE_MINS.json'),5)
    f=base.ft.technical(d,e)
    log=pd.read_csv(P.parent/'multiframe_walkforward/signals_derived.csv');log=log[(log.frame=='FIVE_MINS')&(log.variant=='price')&(log.policy=='selective')&log.scorable].copy()
    ix={t:i for i,t in enumerate(d.available)};records=[]
    for row in log.itertuples():
        i=ix[pd.Timestamp(row.decision_Riyadh).tz_convert('UTC')];side=np.full(len(d),row.side);trend,retest=conditions(d,f,side)
        records.append({'decision_Riyadh':row.decision_Riyadh,'side':int(row.side),'signed_points':float(row.signed_points),'trend':bool(trend.iloc[i]),'trend_retest':bool(retest.iloc[i])})
    out=pd.DataFrame(records);out.to_csv(P/'events.csv',index=False);summary=[]
    for label,mask in [('original',np.ones(len(out),bool)),('trend',out.trend),('trend_retest',out.trend_retest)]:
        x=out.loc[mask];summary.append({'policy':label,'signals':len(x),'hits':int((x.signed_points>0).sum()),'direction_rate':float((x.signed_points>0).mean()) if len(x) else None,'retained_fraction':len(x)/len(out),'mean_signed_points':float(x.signed_points.mean()) if len(x) else None,'discarded_correct':int(((out.signed_points>0)&~np.array(mask)).sum()),'discarded_incorrect':int(((out.signed_points<=0)&~np.array(mask)).sum())})
    # Verify no future bars affect the contextual veto on each sampled event.
    for row in records:
        i=ix[pd.Timestamp(row['decision_Riyadh']).tz_convert('UTC')];short=d.iloc[:i+1];ff=base.ft.technical(short,e);a,b=conditions(short,ff,np.full(len(short),row['side']));assert bool(a.iloc[-1])==row['trend'] and bool(b.iloc[-1])==row['trend_retest']
    report={'status':'EXPLORATORY_NOT_READY','rows':summary,'prefix_checks':len(records),'frozen_candidate_changed':False,'forward_data_used':False}
    (P/'RESULT.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

if __name__=='__main__':main()
