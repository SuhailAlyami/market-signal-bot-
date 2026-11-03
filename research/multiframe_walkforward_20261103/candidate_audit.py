import json,math
from pathlib import Path
import pandas as pd
P=Path(__file__).resolve().parent
def main():
 df=pd.read_csv(P/'signals_derived.csv');rows=[]
 for variant in ['price','price_volume']:
  g=df[(df.frame=='FIVE_MINS')&(df.variant==variant)&(df.policy=='selective')];s=g[g.scorable];pts=s.signed_points.to_numpy();side=s.side.to_numpy();delta=pts*side;n=len(s);k=int((pts>0).sum());z=1.959963984540054;den=1+z*z/n;center=(k/n+z*z/(2*n))/den;rad=z*math.sqrt(k/n*(1-k/n)/n+z*z/(4*n*n))/den;p=float((side>0).mean());days=[]
  for day,q in s.groupby(s.decision_Riyadh.str[:10]):days.append({'Riyadh_date':day,'n':len(q),'hits':int((q.signed_points>0).sum())})
  rows.append({'variant':variant,'signals':len(g),'scored':n,'hits':k,'wilson95_independence_descriptive':[center-rad,center+rad],'same_time_preserved_long_share_random_expected':float((p*(delta>0)+(1-p)*(delta<0)).mean()),'long_count':int((side>0).sum()),'daily':days,'incomplete_horizon':len(g)-n})
 (P/'CANDIDATE_AUDIT.json').write_text(json.dumps({'rows':rows,'warning':'Posthoc focus on best cell among14 compared policies; intervals assume independence and are optimistic. Dates consumed, no deployment.'},indent=2))
if __name__=='__main__':main()
