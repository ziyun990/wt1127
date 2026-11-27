from pathlib import Path
import json,hashlib,csv
import pandas as pd
ROOT=Path(__file__).resolve().parent
rows=[];statuses=[]
for file in (ROOT/'runs').glob('*/*/model/status.json'):
    if json.loads(file.read_text())['complete']!=24:continue
    f=file.parent;decisions=json.loads((f/'decisions.json').read_text());dispatch=pd.read_csv(f/'dispatch.csv');events=pd.read_csv(f/'events.csv')
    starts=events.loc[events.action.eq('repair')].groupby('reason').env_time.min()
    ends=events.loc[events.action.eq('repair complete')].set_index('reason').env_time
    assert len(dispatch)==24
    for d in dispatch.itertuples():
        prior=[x for x in decisions if x['day']*24+6<=d.hour+1e-6]
        assert prior
        chosen=next(x for x in prior[-1]['plan'] if x['job_id']==d.job_id)
        assert chosen['vessel']==d.vessel and chosen['sequence_start_hour']<=d.hour+1e-6
        assert starts[d.job_id]>=d.hour and ends[d.job_id]>=starts[d.job_id]
        rows.append(dict(window=f.parents[1].name,seed=f.parent.name,job_id=d.job_id,vessel=d.vessel,planned_sequence_start=chosen['sequence_start_hour'],actual_dispatch=d.hour,predicted_work_start=chosen['predicted_work_start'],actual_work_start=starts[d.job_id],predicted_finish=chosen['predicted_finish'],actual_finish=ends[d.job_id],start_error_hours=starts[d.job_id]-chosen['predicted_work_start'],finish_error_hours=ends[d.job_id]-chosen['predicted_finish']))
    for d in decisions:statuses.append(dict(window=f.parents[1].name,seed=f.parent.name,day=d['day'],status=d['status'],gap=d['gap']))
out=ROOT/'summary';out.mkdir(exist_ok=True)
pd.DataFrame(rows).to_csv(out/'plan_execution_trace.csv',index=False)
pd.DataFrame(statuses).to_csv(out/'solver_statuses.csv',index=False)
manifest=json.loads((ROOT/'inputs/frozen_manifest.json').read_text())
for r in manifest:assert hashlib.sha256((ROOT/'inputs'/r['file']).read_bytes()).hexdigest()==r['sha256']
source=ROOT.parent/'wt0929_release';checked=0
for r in csv.DictReader((source/'MANIFEST_SHA256.csv').open(encoding='utf-8-sig')):
    assert hashlib.sha256((source/r['relative_path']).read_bytes()).hexdigest()==r['sha256'];checked+=1
(out/'execution_validation.json').write_text(json.dumps(dict(model_cases=len(rows)//24,dispatched_jobs=len(rows),vessel_and_sequence_admission_passed=True,primary_frozen_hashes_passed=True,original_files_unchanged=checked,status_counts=pd.Series([x['status'] for x in statuses]).value_counts().to_dict()),indent=2))
print((out/'execution_validation.json').read_text())
