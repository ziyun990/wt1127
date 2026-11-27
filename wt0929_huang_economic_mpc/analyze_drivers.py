"""Post hoc decomposition; no scheduling or input changes.

Energy allocation order: healthy -> fault waiting only -> actual execution.
The second difference includes repair outage interactions with fault waiting.
"""
from pathlib import Path
import sys,json
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'wt0929_release'))
from cl_stochos_mu import WakeConfig,_jensen_deficit_matrix,power_curve_mw

def main():
    cfg=json.loads((ROOT/'protocol.json').read_text());layout=pd.read_csv(ROOT/'inputs/layout.csv')
    curve=np.loadtxt(ROOT/'inputs/curve.csv',delimiter=',');runs=pd.read_csv(ROOT/'summary/runs.csv')
    wake=WakeConfig(rated_power_mw=15,rotor_diameter_m=240,hub_height_m=145,wake_decay=.05,thrust_coefficient=.8)
    rows=[];details=[]
    for stamp in cfg['windows']:
        w=pd.read_csv(ROOT/'inputs'/f'weather_{stamp}.csv')
        healthy=np.load(ROOT/'inputs'/f'forecast_power_{stamp}.npz')['power'].sum(axis=1)
        cases=[]
        for seed in cfg['seeds']:
            expected=pd.read_csv(ROOT/'inputs'/f'jobs_{seed}.csv').set_index('job_id')
            for policy in ('huang','model'):
                f=ROOT/'runs'/stamp/str(seed)/policy
                e=pd.read_csv(f/'events.csv');j=pd.read_csv(f/'job_results.csv').set_index('job_id')
                # Native in_situ_repair interrupts the turbine immediately after
                # arriving at its target, before transfer/weather waits. Use that
                # boundary rather than the first effective repair hour.
                start={}
                for key,job in expected.iterrows():
                    arrivals=e.loc[e.reason.eq(key)&e.action.eq('complete travel')&e.additional.eq('arrived at '+job.asset)]
                    assert len(arrivals),(stamp,seed,policy,key)
                    start[key]=float(arrivals.env_time.min())
                r=runs.loc[runs.window.eq(stamp)&runs.seed.eq(seed)&runs.policy.eq(policy)].iloc[0]
                horizon=int(r.common_hours);state=np.ones((horizon,67));wait=span=weighted=0.
                for key,job in expected.iterrows():
                    begin=float(start[key]);end=float(j.loc[key,'completion_hour']);deadline=float(job.failure_hour)
                    wait+=max(0,begin-deadline);weighted+=max(0,begin-deadline)*job.reduction;span+=end-begin
                    mask=(np.arange(horizon)>=deadline)&(np.arange(horizon)<begin)
                    state[mask,int(job.turbine)]=1-job.reduction
                    details.append(dict(window=stamp,seed=seed,policy=policy,job_id=key,reduction=job.reduction,service_start=begin,finish_hour=end,failure_hour=deadline,waiting_hours=max(0,begin-deadline),repair_outage_span_hours=end-begin,required_work_hours=job.required_hours))
                travel=e.loc[e.action.eq('traveling')]
                out=travel.additional.eq('traveling from port to site');back=travel.additional.eq('traveling from site to port')
                row=dict(window=stamp,seed=seed,policy=policy,lost_mwh=r.lost_mwh,fault_wait_mwh=0.,waiting_hours=wait,reduction_weighted_wait_hours=weighted,repair_outage_span_hours=span,port_to_site_legs=int(out.sum()),site_to_port_legs=int(back.sum()),intra_site_legs=int((~out&~back).sum()),port_to_site_km=travel.loc[out,'distance_km'].sum(),site_to_port_km=travel.loc[back,'distance_km'].sum(),intra_site_km=travel.loc[~out&~back,'distance_km'].sum(),total_km=travel.distance_km.sum(),fuel_eur=r.fuel_eur,total_eur=r.total_eur)
                empty=0;productive=0
                for agent,part in e.groupby('agent'):
                    departures=part.loc[part.action.eq('traveling')&part.additional.eq('traveling from port to site')]
                    returns=part.loc[part.action.eq('traveling')&part.additional.eq('traveling from site to port')]
                    repairs=part.loc[part.action.eq('repair')]
                    for d in departures.itertuples():
                        later=returns.loc[returns.env_time>d.env_time]
                        stop=later.env_time.min() if len(later) else float(r.common_hours)
                        amount=repairs.loc[repairs.env_time.between(d.env_time,stop,inclusive='left'),'duration'].sum()
                        if amount>1e-6:productive+=1
                        else:empty+=1
                row.update(no_work_outbound_trips=empty,productive_outbound_trips=productive)
                cases.append((row,state,horizon));rows.append(row)
        maximum=max(h for _,_,h in cases)
        for first in range(0,maximum,128):
            end=min(maximum,first+128)
            squares=np.array([_jensen_deficit_matrix(x,layout[['floris_x','floris_y']].to_numpy(),wake)**2 for x in w.wind_direction_100m.iloc[first:end]])
            speed=w.windspeed_145m.to_numpy()[first:end]
            for row,state,horizon in cases:
                last=min(end,horizon);n=last-first
                if n<=0:continue
                fractions=state[first:last]
                deficits=np.sqrt(np.einsum('hij,hi->hj',squares[:n],fractions>0))
                power=(power_curve_mw(np.maximum(0,speed[:n,None]*(1-deficits)),curve,15)*fractions).sum(axis=1)
                row['fault_wait_mwh']+=float((healthy[first:last]-power).sum())
        for row,_,_ in cases:row['repair_increment_mwh']=row['lost_mwh']-row['fault_wait_mwh']
        print('ANALYZED',stamp,flush=True)
    out=ROOT/'driver_analysis';out.mkdir(exist_ok=True)
    frame=pd.DataFrame(rows);frame.to_csv(out/'scenario_drivers.csv',index=False)
    frame.groupby('policy').mean(numeric_only=True).to_csv(out/'means.csv')
    pd.DataFrame(details).to_csv(out/'job_waiting_and_outage.csv',index=False)
    print(frame.groupby('policy').mean(numeric_only=True).to_string())

if __name__=='__main__':main()
