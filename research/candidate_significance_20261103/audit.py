"""Exact conditional direction permutations, all14 reported walkforward cells."""
import json,math
from pathlib import Path
import pandas as pd
P=Path(__file__).resolve().parent

def distribution(delta,nlong):
 pos=sum(x>0 for x in delta);neg=sum(x<0 for x in delta);zero=len(delta)-pos-neg;total=math.comb(len(delta),nlong);out={}
 for a in range(max(0,nlong-neg-zero),min(pos,nlong)+1):
  for b in range(max(0,nlong-a-zero),min(neg,nlong-a)+1):
   c=nlong-a-b
   if 0<=c<=zero:
    hits=a+neg-b;prob=math.comb(pos,a)*math.comb(neg,b)*math.comb(zero,c)/total;out[hits]=out.get(hits,0)+prob
 assert math.isclose(sum(out.values()),1,abs_tol=1e-10)
 return out

def convolve(a,b):
 out={}
 for i,p in a.items():
  for j,q in b.items():out[i+j]=out.get(i+j,0)+p*q
 return out

def tail(dist,hits):return min(1.,sum(p for k,p in dist.items() if k>=hits))
def holm(values):
 order=sorted(range(len(values)),key=lambda i:values[i]);out=[0.]*len(values);running=0
 for rank,i in enumerate(order):running=max(running,min(1.,(len(values)-rank)*values[i]));out[i]=running
 return out

def main():
 cfg={'input':'unchanged walkforward signals,14variant/policy/frame cells','primary':'shuffle directions within Riyadh decision-date, preserving each date long count; convolve exact conditional distributions','secondary':'shuffle directions across same-time sample preserving overall long count; exact','multiplicity':'Holm14 primary; Holm14 secondary; additional Holm28 combined; prior project attempts not included, so no definitive adoption claim','limits':'Direction exchangeability is assumption, same-day clustering constrained but serial dependence not proven eliminated; dates reused. Degenerate date groups cannot identify direction skill. No refit or filter changes.'};(P/'PROTOCOL.json').write_text(json.dumps(cfg,indent=2));df=pd.read_csv(P.parent/'multiframe_walkforward/signals_derived.csv');df=df[df.scorable];rows=[]
 for key,g in df.groupby(['frame','variant','policy'],sort=False):
  delta=(g.signed_points*g.side).to_numpy();hits=int((g.signed_points>0).sum());nlong=int((g.side>0).sum());globaldist=distribution(delta,nlong);daily={0:1.};movable=0
  for day,q in g.groupby(g.decision_Riyadh.str[:10]):
   dist=distribution((q.signed_points*q.side).to_numpy(),int((q.side>0).sum()));daily=convolve(daily,dist);movable+=len(dist)>1
  rows.append({'frame':key[0],'variant':key[1],'policy':key[2],'n':len(g),'hits':hits,'primary_within_date_p':tail(daily,hits),'secondary_global_p':tail(globaldist,hits),'dates_with_nonconstant_permuted_hit_count':movable,'primary_expected_hits':sum(k*p for k,p in daily.items()),'global_expected_hits':sum(k*p for k,p in globaldist.items())})
 for field,label in [('primary_within_date_p','primary_Holm14'),('secondary_global_p','secondary_Holm14')]:
  vals=holm([x[field] for x in rows])
  for x,v in zip(rows,vals):x[label]=v
 combined=holm([x['primary_within_date_p'] for x in rows]+[x['secondary_global_p'] for x in rows])
 for i,x in enumerate(rows):x['primary_Holm28']=combined[i];x['secondary_Holm28']=combined[i+len(rows)]
 result={'rows':rows,'tests':len(rows)*2,'status':'NOT_READY','interpretation':'Conditional permutation evidence only; no probability of strategy success or independence proof. Model unchanged.'};(P/'RESULT.json').write_text(json.dumps(result,indent=2));print(json.dumps([x for x in rows if x['frame']=='FIVE_MINS' and x['policy']=='selective'],indent=2))
if __name__=='__main__':main()
