from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import json,subprocess,os,sys
from runtime_paths import solver_python, native_python
ROOT=Path(__file__).resolve().parent
def execute(job):
    stamp,seed,policy=job
    out=ROOT/'runs'/stamp/str(seed)/policy;out.mkdir(parents=True,exist_ok=True)
    if '--force' not in sys.argv and (out/'status.json').exists() and json.loads((out/'status.json').read_text())['complete']==24:return job
    cmd=[native_python(),str(ROOT/'run_case.py'),stamp,str(seed),policy]
    with (out/'run.log').open('w',encoding='utf-8') as stream:
        r=subprocess.run(cmd,stdout=stream,stderr=subprocess.STDOUT,env=dict(os.environ,PYTHONUTF8='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'))
    assert r.returncode==0,(job,out/'run.log')
    status=json.loads((out/'status.json').read_text());assert status['complete']==status['required'],(job,status)
    return job
cfg=json.loads((ROOT/'protocol.json').read_text())
jobs=[(w,s,p) for w in cfg['windows'] for s in cfg['seeds'] for p in ('huang','model')]
with ThreadPoolExecutor(max_workers=4) as pool:
    for f in as_completed([pool.submit(execute,j) for j in jobs]):print('DONE',*f.result(),flush=True)
print('ALL 48 COMPLETE',flush=True)
