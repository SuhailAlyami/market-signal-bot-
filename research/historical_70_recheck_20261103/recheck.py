"""Rerun all fixed walkforward policies in separate outputs; preserve live model."""
import sys,json,hashlib,importlib.util
from pathlib import Path
P=Path(__file__).resolve().parent
source=P.parent/'multiframe_walkforward/walkforward.py'
sys.path.insert(0,str(source.parent))
spec=importlib.util.spec_from_file_location('original_walkforward',source)
w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
frozen=P.parent/'multiframe_walkforward/models/FIVE_MINS_price_900.json'
before=hashlib.sha256(frozen.read_bytes()).hexdigest()
out=P/'outputs';out.mkdir(exist_ok=True);w.P=out;w.main()
after=hashlib.sha256(frozen.read_bytes()).hexdigest();assert before==after
report=json.loads((out/'RESULT.json').read_text());rows=report['rows']
qualified=[r for r in rows if r['rate'] is not None and r['rate']>=.70]
decision={'status':'NOT_READY','original_frozen_sha256':after,'original_unchanged':True,
 'threshold_requested':.70,'policies_tested':len(rows),'policies_observed_ge70':qualified,
 'adoption':'Retain only as research candidates; observed rate alone does not establish stable70percent, sample sufficiency, or options profitability.',
 'limitations':['Previously consumed data; not a pristine independent test.','Each walkforward row combines different fold models, not one frozen weight set.','Multiple policies compared; do not select best without multiplicity and future evaluation.'],
 'no_optimization_needed_to_cross_observed_threshold':bool(qualified),
 'no_new_parameters_searched':True,'no_live_alert_changes':True}
(P/'DECISION.json').write_text(json.dumps(decision,indent=2));print(json.dumps(decision,indent=2))
