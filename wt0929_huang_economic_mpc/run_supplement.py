from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import json,subprocess,os,sys
from runtime_paths import solver_python, native_python
ROOT=Path(__file__).resolve().parent
cfg=json.loads((ROOT/'supplement_protocol.json').read_text())
def run(job):
    w,s,p=job;out=ROOT/'runs'/w/str(s)/p;out.mkdir(parents=True,exist_ok=True)
    if '--force' not in sys.argv and (out/'status.json').exists() and json.loads((out/'status.json').read_text())['complete']==24:return job
    with (out/'run.log').open('w',encoding='utf-8') as stream:
        r=subprocess.run([native_python(),str(ROOT/'run_case.py'),w,str(s),p],stdout=stream,stderr=subprocess.STDOUT,env=dict(os.environ,PYTHONUTF8='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'))
    assert r.returncode==0,(job,out/'run.log')
    status=json.loads((out/'status.json').read_text());assert status['complete']==24,(job,status)
    return job
with ThreadPoolExecutor(max_workers=2) as pool:
    for f in as_completed([pool.submit(run,(w,v['seed'],p)) for w in cfg['windows'] for v in cfg['variants'] for p in ['huang','model']]):print('DONE',*f.result(),flush=True)
print('SUPPLEMENT COMPLETE',flush=True)
