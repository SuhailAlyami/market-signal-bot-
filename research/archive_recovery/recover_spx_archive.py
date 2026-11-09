"""Read-only search in an explicit project root; package exact published hashes only.
No Gateway connection, acquisition, training, credentials, tasks, or notifications.
"""
import argparse,hashlib,json,os,re,sys,zipfile
from pathlib import Path
P=Path(__file__).resolve().parent

def recover(root,manifest,output):
 root=Path(root).resolve(strict=True);output=Path(output).resolve();m=json.loads(Path(manifest).read_text(encoding='utf-8'))
 expected={r['date']:r['raw_sha256'] for r in m['sessions']};matches={};wrong=[]
 for parent,dirs,files in os.walk(root,followlinks=False):
  dirs[:]=[n for n in dirs if n not in {'.git','.venv','venv','node_modules','__pycache__'} and not (Path(parent)/n).is_symlink()]
  for name in files:
   if not re.fullmatch(r'\d{4}-\d{2}-\d{2}\.raw\.json',name):continue
   date=name[:10]
   if date not in expected:continue
   p=Path(parent)/name
   if p.is_symlink():continue
   digest=hashlib.sha256(p.read_bytes()).hexdigest()
   if digest==expected[date]:matches.setdefault(date,p)
   else:wrong.append({'date':date,'path':str(p),'sha256':digest})
 missing=sorted(set(expected)-set(matches));report={'root':str(root),'matched':len(matches),'expected':len(expected),'missing_dates':missing,'nonmatching_files':wrong,'packaged':False,'recollection_performed':False}
 if not missing:
  if output.exists():raise FileExistsError('Refusing to overwrite existing archive: '+str(output))
  output.parent.mkdir(parents=True,exist_ok=True)
  # Recheck bytes at write time, and remove incomplete archive on any failure.
  try:
   with zipfile.ZipFile(output,'x',zipfile.ZIP_DEFLATED) as z:
    for date,p in sorted(matches.items()):
     data=p.read_bytes()
     if hashlib.sha256(data).hexdigest()!=expected[date]:raise ValueError('Source changed during packaging: '+date)
     z.writestr(date+'.raw.json',data)
    z.writestr('expected_sessions.json',json.dumps(m,indent=2))
   report['packaged']=True;report['archive']=str(output)
  except Exception:
   output.unlink(missing_ok=True);raise
 return report

if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--root',required=True,type=Path,help='Explicit project/worktree root; never search whole drive');a.add_argument('--manifest',type=Path,default=P/'expected_sessions.json');a.add_argument('--output',type=Path,default=Path.cwd()/'Suhail_SPX_20sessions_verified.zip');x=a.parse_args()
 result=recover(x.root,x.manifest,x.output);print(json.dumps(result,indent=2));sys.exit(0 if result['packaged'] else 2)
