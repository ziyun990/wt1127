"""Both dispatch policies execute through the same unmodified WOMBAT vessel processes."""
from pathlib import Path
import argparse,json,shutil,subprocess,sys,types
import numpy as np
import pandas as pd
import yaml
from wombat.core.simulation_api import Simulation
from wombat.core.data_classes import Failure
from wombat.core.service_equipment import ServiceEquipment
ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parent/'wt0929_huang_native_vs_release/inputs/IEA_49'

def run(stamp,seed,policy):
    out=ROOT/'runs'/stamp/str(seed)/policy;out.mkdir(parents=True,exist_ok=True)
    lib=out/'library'
    for directory in ['project','turbines','cables','substations','vessels']:
        shutil.copytree(SOURCE/directory,lib/directory,dirs_exist_ok=True)
    (lib/'results').mkdir(exist_ok=True);(lib/'weather').mkdir(exist_ok=True)
    for directory in ['turbines','cables','substations']:
        for f in (lib/directory).glob('*.yaml'):
            data=yaml.safe_load(f.read_text())
            def remove(x):
                if isinstance(x,dict):
                    for k,v in list(x.items()):
                        if k in ('maintenance','failures'):x[k]=[]
                        else:remove(v)
            remove(data);f.write_text(yaml.safe_dump(data))
    shutil.copy2(ROOT/'inputs'/f'weather_{stamp}.csv',lib/'weather/fixed.csv')
    cfg=yaml.safe_load((lib/'project/config/base_floating_deep_operations.yaml').read_text())
    cfg.update(weather='fixed.csv',port=None,start_year=int(stamp[:4]),end_year=int(stamp[:4])+1,random_seed=seed,service_equipment=[['ctv.yaml',3]])
    sim=Simulation(lib,cfg);env=sim.env;manager=sim.repair_manager
    jobs=pd.read_csv(ROOT/'inputs'/f'jobs_{seed}.csv').to_dict('records')
    byid={j['job_id']:j for j in jobs};requests={};complete={};worked={};dispatch=[];decisions=[]
    rank=[];worker=None
    if policy=='model':
        worker=subprocess.Popen(['C:/conda/envs/stochos/python.exe',str(ROOT/'solver_worker.py')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=(out/'solver_stderr.log').open('w'),text=True,encoding='utf-8',bufsize=1)
    original_check=manager._is_request_processing
    def eligible_check(self,request):
        key=request.details.description
        if key not in byid:return original_check(request)
        job=byid[key]
        permitted=env.now>=job['failure_hour'] if policy in ('huang','replay') else key in rank
        return not permitted or original_check(request)
    manager._is_request_processing=types.MethodType(eligible_check,manager)
    # The baseline retains the configured native request method. Model selection
    # restricts and orders the pending queue, then delegates to the same method.
    for method in ['get_request_by_system','get_request_by_severity']:
        original=getattr(manager,method)
        def select(self,*args,_original=original,**kw):
            if policy=='model':
                positions={key:i for i,key in enumerate(rank)}
                self.items.sort(key=lambda r:positions.get(r.details.description,100000))
                # Native severity sorting otherwise overrides the optimization order.
                # Only the first optimization-selected, physically available job is
                # exposed at this request event; native validity checks still apply.
                available=[r for r in self.items if r.details.description in positions and not original_check(r) and r.system_id not in self.invalid_systems]
                allowed=available[0].details.description if available else None
                saved=self._is_request_processing
                self._is_request_processing=lambda r: r.details.description!=allowed or saved(r)
                try:result=_original(*args,**kw)
                finally:self._is_request_processing=saved
            elif policy=='replay':
                reference=pd.read_csv(ROOT/'runs'/stamp/str(seed)/'huang/dispatch.csv')
                key=reference.job_id.iloc[len(dispatch)] if len(dispatch)<len(reference) else None
                saved=self._is_request_processing
                self._is_request_processing=lambda r:r.details.description!=key or saved(r)
                try:result=_original(*args,**kw)
                finally:self._is_request_processing=saved
            else:result=_original(*args,**kw)
            if result is not None:
                key=result.value.details.description
                dispatch.append(dict(hour=float(env.now),job_id=key,policy=policy))
            return result
        setattr(manager,method,types.MethodType(select,manager))
    original_register=manager.register_repair
    def registered(self,request):
        complete[request.details.description]=float(env.now)
        yield from original_register(request)
    manager.register_repair=types.MethodType(registered,manager)
    native_restore=ServiceEquipment.register_repair_with_subassembly
    def restore(vessel,subassembly,request,starting):
        # Exactly one fixed demand per turbine. Complete restoration is identical
        # before/after its fixed deadline, including a deadline crossed in repair.
        if request.details.description in byid:
            subassembly.operating_level=1.
            if not subassembly.broken.triggered:subassembly.broken.succeed()
            vessel.manager.enable_requests_for_system(subassembly.system)
            vessel.env.process(vessel.manager.register_repair(request))
        else:native_restore(vessel,subassembly,request,starting)
    ServiceEquipment.register_repair_with_subassembly=restore
    log=env.log_action
    def observed(*args,**kw):
        if kw.get('action')=='repair':
            key=kw.get('reason');worked[key]=worked.get(key,0)+float(kw.get('duration',0))
        return log(*args,**kw)
    env.log_action=observed
    def release(job):
        yield env.timeout(job['release_hour'])
        system=sim.windfarm.system(job['asset']);sub=getattr(system,job['component'])
        action=Failure(scale=0,shape=0,time=job['required_hours'],materials=job['material_eur'],operation_reduction=0,level=job['severity'],service_equipment='CTV',system_value=1,rng=np.random.default_rng(seed),replacement=False,description=job['job_id'])
        sub.trigger_request(action)
        request=next(r for r in manager.items if r.details.description==job['job_id'])
        requests[job['job_id']]=request
        yield env.timeout(job['failure_hour']-job['release_hour'])
        if job['job_id'] not in complete:
            sub.operating_level=1-job['reduction']
            env.log_action(agent='fixed demand',action='fixed deadline',reason=job['job_id'],system_id=job['asset'],part_id=job['component'],system_ol=system.operating_level,part_ol=sub.operating_level)
    weather=pd.read_csv(ROOT/'inputs'/f'weather_{stamp}.csv')
    curve=pd.read_csv(ROOT/'inputs/curve.csv',header=None).to_numpy()
    def optimize():
        nonlocal rank
        for day in range(365):
            if day:yield env.timeout(24)
            # At a release boundary, allow release processes to submit requests first.
            yield env.timeout(.000001)
            pending=[]
            for key,r in requests.items():
                if key in complete or original_check(r):continue
                j=dict(byid[key]);j['remaining']=max(.01,j['required_hours']-worked.get(key,0));pending.append(j)
            w=weather.iloc[day*24:(day+1)*24]
            access=((w.windspeed.to_numpy()<=12)&(w.waveheight.to_numpy()<=1.5));access[:6]=False;access[22:]=False
            power=np.interp(w.windspeed_145m.to_numpy(),curve[:,0],curve[:,1])*15
            payload=dict(hour=day*24,jobs=pending,access=access.astype(int).tolist(),power=power.tolist())
            worker.stdin.write(json.dumps(payload)+'\n');worker.stdin.flush()
            while True:
                line=worker.stdout.readline()
                if not line:raise RuntimeError('solver exited')
                if line.startswith('RESULT '):result=json.loads(line[7:]);break
            if 'error' in result:raise RuntimeError(result['error'])
            rank=result['rank'];decisions.append(dict(day=day,**result))
    for job in jobs:env.process(release(job))
    if worker:env.process(optimize())
    finish=None
    try:
        for day in range(1,366):
            env.run(until=day*24)
            if len(complete)==len(jobs):finish=max(complete.values());break
        env.load_events_log_dataframe().to_csv(out/'events.csv',index=False)
        env.load_operations_log_dataframe().to_csv(out/'operations.csv',index=False)
        pd.DataFrame(dispatch).to_csv(out/'dispatch.csv',index=False)
        pd.DataFrame([dict(j,completion_hour=complete.get(j['job_id']),early_complete=complete.get(j['job_id'],1e9)<j['failure_hour']) for j in jobs]).to_csv(out/'job_results.csv',index=False)
        (out/'decisions.json').write_text(json.dumps(decisions),encoding='utf-8')
        (out/'status.json').write_text(json.dumps(dict(policy=policy,complete=len(complete),required=len(jobs),finish_hour=finish,simulated_hours=day*24)),encoding='utf-8')
        print('COMPLETED',stamp,seed,policy,len(complete),finish,flush=True)
    finally:
        ServiceEquipment.register_repair_with_subassembly=native_restore
        if worker:worker.stdin.close();worker.wait(timeout=30)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stamp');p.add_argument('seed',type=int);p.add_argument('policy',choices=['huang','model','replay']);a=p.parse_args();run(a.stamp,a.seed,a.policy)
