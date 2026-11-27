"""Persistent COPT bridge: original candidate generation and pattern scheduler."""
import sys,json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT.parent/'wt0929_release'),str(ROOT.parent/'wt0929_release/model')]
from cl_stochos_mu import generate_candidate_tasks,TriggerConfig
from hourly_component_task import HourlyTask
from hourly_component_scheduler_copt import solve_hourly_component_schedule

def solve(p):
    jobs=p['jobs'];n=len(jobs)
    if not n:return dict(rank=[],status='EMPTY',gap=0,candidates=[])
    # Distinct turbines make one job per component column sufficient.
    rul=np.full((67,1,10),1e6)
    hours=np.ones((67,1));cost=np.ones((67,1))
    for j in jobs:
        rul[j['turbine'],0]=max(0,(j['failure_hour']-p['hour'])/24)
        hours[j['turbine'],0]=j['remaining'];cost[j['turbine'],0]=j['material_eur']*7.7248
    generated=generate_candidate_tasks(rul,task_hours=hours,preventive_costs=cost,corrective_costs=cost,config=TriggerConfig(lead_time_days=5,rul_probability_threshold=.6,risk_exposure_cost_per_day=1000,benefit_cost_filter=False))
    mapping={t.turbine:t for t in generated.tasks};tasks=[];ids=[]
    for j in jobs:
        if j['turbine'] not in mapping:continue
        t=mapping[j['turbine']];cm=p['hour']>=j['failure_hour']
        direct=j['material_eur']*7.7248
        benefit=direct+300000 if cm else t.risk_reduction_benefit
        tasks.append(HourlyTask(j['job_id'],j['turbine'],0,j['component'],j['component'],int(np.ceil(j['remaining'])),direct,benefit,benefit-direct,tuple(t.reasons),mandatory=True,corrective=cm,partial_progress_weight_yuan_per_hour=300000/max(j['remaining'],1) if cm else 0))
        ids.append(j['job_id'])
    if not tasks:return dict(rank=[],status='EMPTY',gap=0,candidates=[])
    access=np.repeat(np.asarray(p['access'])[:,None],67,axis=1)
    loss=np.repeat(np.asarray(p['power'])[:,None]*80*7.7248,67,axis=1)
    r=solve_hourly_component_schedule(tasks,access,loss,max_parallel_turbines=3,standard_work_hours=48,crew_cost_yuan_per_hour=0,overtime_cost_yuan_per_hour=0,vessel_cost_yuan_per_day=0,solver_threads=1,solver_time_limit=10,vessel_technician_capacity=3,visit_cost_yuan_per_turbine=np.full(67,2*53/44.448*400*7.7248))
    order=[]
    for i,key in enumerate(ids):
        h=np.flatnonzero(r['work_plan'][:,i])
        if len(h):order.append((int(h[0]),key))
    return dict(rank=[k for h,k in sorted(order)],status=r['status'],gap=r.get('mip_gap'),candidates=ids,work_plan=r['work_plan'].tolist(),task_ids=ids)

for line in sys.stdin:
    try:result=solve(json.loads(line));print('RESULT '+json.dumps(result),flush=True)
    except Exception as e:print('RESULT '+json.dumps(dict(error=repr(e))),flush=True)
