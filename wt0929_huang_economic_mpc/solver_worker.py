"""Fourteen-day set-partition MILP over multi-day vessel service sequences.

No completion reward. Native WOMBAT remains the realization/settlement engine.
Profiles approximate its fractional travel/transfer with continuous-hour weather slots.
"""
from pathlib import Path
import sys,json,itertools,math
from functools import lru_cache
import numpy as np
import coptpy as cp
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'wt0929_release'))
from cl_stochos_mu import generate_candidate_tasks,TriggerConfig
ENV=cp.Envr()

def solve(p):
    jobs=p['jobs'];n=len(jobs);H=min(336,len(p['safe']));now=p['hour']
    if not n:return dict(rank=[],plan=[],status='EMPTY',gap=0,objective_eur=0,candidates=[])
    safe=np.asarray(p['safe'],bool);power=np.asarray(p['power']);coords=np.asarray(p['coords'])
    # Candidate generation remains source-grounded. Exposure reward is disabled.
    rul=np.full((67,n,10),1e6);hours=np.ones((67,n));cost=np.ones((67,n))
    for i,j in enumerate(jobs):
        rul[j['turbine'],i]=max(0,(j['failure_hour']-now)/24)
        hours[j['turbine'],i]=j['remaining'];cost[j['turbine'],i]=j['material_eur']
    generated=generate_candidate_tasks(rul,task_hours=hours,preventive_costs=cost,corrective_costs=cost,config=TriggerConfig(lead_time_days=14,rul_probability_threshold=.6,risk_exposure_cost_per_day=0,benefit_cost_filter=False))
    eligible={(t.turbine,t.component) for t in generated.tasks}
    indices=[i for i,j in enumerate(jobs) if (j['turbine'],i) in eligible]
    def dist(a,b):
        if a==b:return 0.
        if a<0 or b<0:return 53.
        return float(p['distances'][a][b]) if 'distances' in p else float(np.linalg.norm(coords[a]-coords[b])/1000)
    @lru_cache(None)
    def advance(t,duration,work=False):
        left=duration
        while left>1e-8 and t<len(safe):
            h=int(t);step=min(left,math.floor(t+1+1e-8)-t)
            if step<1e-8:step=min(left,1.)
            if safe[h] and 6<=(now+h)%24<22:left-=step;t+=step
            else:t=float(h+1)
        return t if left<1e-8 else float(len(safe)+1)
    @lru_cache(None)
    def profile(seq,start,source):
        t=float(start);distance=0.;node=source;records=[];costs={}
        for i in seq:
            j=jobs[i];departure=t
            d=dist(node,j['turbine']);distance+=d;t=advance(t,d/44.448)
            begin=t;t=advance(t,.25);remaining=j['remaining']
            while remaining>1e-8 and t<len(safe):
                h=int(t);hod=(now+h)%24
                if hod>=21 or hod<6:
                    distance+=106.;t=float((math.floor((now+t)/24)+1)*24+6-now) if hod>=21 else float(h+6-hod)
                    t=advance(t,53/44.448+.5);continue
                step=min(remaining,math.floor(t+1+1e-8)-t,21.5-hod)
                if step<=1e-8:t=float(h+1);continue
                if safe[h]:remaining-=step
                t+=step
            t=advance(t,.25)
            if t>=len(safe):return None
            end=t
            # Lost generation: repair outage plus degradation waiting before repair.
            failure=max(0,j['failure_hour']-now)
            pp=power[:,j['turbine']] if power.ndim==2 else power
            wait=float(pp[max(0,int(failure)):max(0,int(begin))].sum())*j['reduction']*80
            outage=float(pp[max(0,int(begin)):min(len(pp),int(math.ceil(end)))].sum())*80
            costs[i]=wait+outage
            records.append(dict(job_id=j['job_id'],turbine=j['turbine'],dispatch_hour=now+departure,predicted_work_start=now+begin,predicted_finish=now+end))
            node=j['turbine']
        distance+=dist(node,-1)
        end=advance(t,dist(node,-1)/44.448)
        return dict(seq=seq,start=start,end=end,cost=sum(costs.values())+distance/44.448*400,distance=distance,records=records)
    patterns=[]
    for v,ship in enumerate(p['ships']):
        earliest=max(0,float(ship['available_hour'])-now)
        starts=[float(h) for h in range(H) if (now+h)%24 in (6,) and h>=earliest]
        if earliest<H and 6<=(now+earliest)%24<20:starts.append(earliest)
        for start in sorted(set(starts)):
            source=ship['node'] if start<24 and earliest<24 else -1
            for i in indices:
                r=profile((i,),start,source)
                if r and r['end']<=H:patterns.append(dict(r,vessel=v))
                # One nearby continuation; directional pairs preserve route order.
                if not r or r['end']>H:continue
                others=sorted((j for j in indices if j!=i),key=lambda j:dist(jobs[i]['turbine'],jobs[j]['turbine']))[:2]
                for j in others:
                    pair=profile((i,j),start,source)
                    if pair and pair['end']<=H:patterns.append(dict(pair,vessel=v))
    model=ENV.createModel('economic_mpc');model.setParam(cp.COPT.Param.Logging,0);model.setParam(cp.COPT.Param.Threads,1);model.setParam(cp.COPT.Param.TimeLimit,3);model.setParam(cp.COPT.Param.RelGap,.005)
    x=[model.addVar(vtype=cp.COPT.BINARY) for _ in patterns]
    defer=[model.addVar(vtype=cp.COPT.BINARY) for _ in jobs]
    for i in range(n):model.addConstr(cp.quicksum(x[k] for k,r in enumerate(patterns) if i in r['seq'])+defer[i]==1)
    vessel_slots={};asset_slots={};shared={j['turbine'] for j in jobs if sum(q['turbine']==j['turbine'] for q in jobs)>1}
    for k,r in enumerate(patterns):
        for h in range(int(math.ceil(r['start'])),min(H,int(math.ceil(r['end'])))):
            vessel_slots.setdefault((r['vessel'],h),[]).append(k)
        occupied=set()
        for rec in r['records']:
            if rec['turbine'] in shared:
                for h in range(max(0,int(math.ceil(rec['predicted_work_start']-now))),min(H,int(math.ceil(rec['predicted_finish']-now)))):occupied.add((rec['turbine'],h))
        for key in occupied:asset_slots.setdefault(key,[]).append(k)
    for ids_at_slot in vessel_slots.values():model.addConstr(cp.quicksum(x[k] for k in ids_at_slot)<=1)
    for ids_at_slot in asset_slots.values():
        if len(ids_at_slot)>1:model.addConstr(cp.quicksum(x[k] for k in ids_at_slot)<=1)
    terminal=[]
    for i,j in enumerate(jobs):
        tail=profile((i,),H,-1)
        if tail:terminal.append(tail['cost'])
        else:
            # No feasible continuation in the available weather record: use the
            # remaining forecast degradation plus unavoidable repair opportunity cost.
            pp=power[:,j['turbine']] if power.ndim==2 else power
            terminal.append(float(pp[max(0,j['failure_hour']-now):].sum())*j['reduction']*80+float(pp.mean())*j['remaining']*80+106/44.448*400)
    model.setObjective(cp.quicksum((r['cost']+1e-6*r['end'])*x[k] for k,r in enumerate(patterns))+cp.quicksum((terminal[i]+1e-6*len(safe))*defer[i] for i in range(n)),cp.COPT.MINIMIZE)
    # All jobs deferred is explicitly feasible, even when the LP root consumes
    # the time budget. Supply it rather than terminating the physical simulation.
    used_jobs=set();used_vessel=set();used_assets=set();initial=[0.]*len(x)
    for k in sorted(range(len(patterns)),key=lambda k:patterns[k]['cost']-sum(terminal[i] for i in patterns[k]['seq'])):
        r=patterns[k]
        if r['cost']>=sum(terminal[i] for i in r['seq']) or any(i in used_jobs for i in r['seq']):continue
        vs={(r['vessel'],h) for h in range(int(math.ceil(r['start'])),min(H,int(math.ceil(r['end']))))}
        ats={(rec['turbine'],h) for rec in r['records'] if rec['turbine'] in shared for h in range(max(0,int(math.ceil(rec['predicted_work_start']-now))),min(H,int(math.ceil(rec['predicted_finish']-now))))}
        if vs & used_vessel or ats & used_assets:continue
        initial[k]=1.;used_jobs.update(r['seq']);used_vessel|=vs;used_assets|=ats
    model.setMipStart(x+defer,initial+[float(i not in used_jobs) for i in range(n)]);model.loadMipStart()
    model.solve()
    if not model.hasmipsol:
        model.dispose()
        return dict(plan=[],rank=[],status='FEASIBLE_DEFER_FALLBACK',gap=None,objective_eur=sum(terminal),candidates=[j['job_id'] for j in jobs],terminal_eur=terminal,patterns=len(patterns),selected_routes=[])
    selected=[r for k,r in enumerate(patterns) if x[k].x>.5]
    plan=[]
    for r in selected:
        for record in r['records']:plan.append(dict(record,vessel=r['vessel'],sequence_start_hour=now+r['start']))
    result=dict(plan=sorted(plan,key=lambda r:(r['dispatch_hour'],r['vessel'])),rank=[r['job_id'] for r in sorted(plan,key=lambda r:r['dispatch_hour']) if r['dispatch_hour']<now+24],status='OPTIMAL' if model.status==cp.COPT.OPTIMAL else 'TIME_LIMIT',gap=float(model.bestgap),objective_eur=float(model.objval),candidates=[j['job_id'] for j in jobs],terminal_eur=terminal,patterns=len(patterns),selected_routes=[dict(vessel=r['vessel'],start=now+r['start'],distance_km=r['distance'],cost_eur=r['cost'],jobs=[jobs[i]['job_id'] for i in r['seq']]) for r in selected])
    model.dispose()
    return result

for line in sys.stdin:
    try:print('RESULT '+json.dumps(solve(json.loads(line))),flush=True)
    except Exception as e:print('RESULT '+json.dumps(dict(error=repr(e))),flush=True)
