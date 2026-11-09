"""Retrospective reference only, never used by detector."""
def legs(closes,threshold=10):
 if len(closes)<2:return []
 lo=hi=0;side=0;start=ext=0;out=[]
 for i in range(1,len(closes)):
  v=closes[i]
  if side==0:
   if v<closes[lo]:lo=i
   if v>closes[hi]:hi=i
   if v-closes[lo]>=threshold:side=1;start=lo;ext=i
   elif closes[hi]-v>=threshold:side=-1;start=hi;ext=i
   continue
  if side*(v-closes[ext])>0:ext=i
  elif side*(closes[ext]-v)>=threshold:
   out.append({'start':start,'end':ext,'direction':side,'confirmed_at':i,'complete':True});start=ext;ext=i;side=-side
 if side and side*(closes[ext]-closes[start])>=threshold:out.append({'start':start,'end':ext,'direction':side,'confirmed_at':None,'complete':False})
 return out
