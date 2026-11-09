"""One-shot stable-archive wrapper around unchanged frozen model replay."""
import argparse,json,hashlib
from pathlib import Path
import pandas as pd
from stable_archive import merge_archive
from replay import replay
P=Path(__file__).resolve().parent

def run(spx,es,asof):
 spx_archive=P/'SPX_archive.json';es_archive=P/'ES_archive.json';audit={}
 # Each archive mutation atomic; replay runs only after both inputs validate.
 audit['SPX']=merge_archive(spx,spx_archive,asof);audit['ES']=merge_archive(es,es_archive,asof)
 report=replay(spx_archive,es_archive,asof,P/'ARCHIVE_STATE.json',P/'ARCHIVE_RESULT.json');audit['asof_Riyadh']=str(pd.Timestamp(asof).tz_convert('Asia/Riyadh'));audit['input_archive_sha256']={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in [spx_archive,es_archive]};(P/'ARCHIVE_AUDIT.json').write_text(json.dumps(audit,indent=2));return {'archive':audit,'reader':report}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--spx',type=Path,default=P/'SPX_latest_raw.json');p.add_argument('--es',type=Path,default=P/'ES_latest_raw.json');p.add_argument('--asof',default=pd.Timestamp.now(tz='UTC').isoformat());a=p.parse_args();print(json.dumps(run(a.spx,a.es,a.asof),indent=2))
