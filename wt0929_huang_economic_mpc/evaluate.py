"""Audit equal work and evaluate at each pair's common finishing horizon."""
from pathlib import Path
import json,sys,hashlib
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'wt0929_release'))
from cl_stochos_mu import WakeConfig,_jensen_deficit_matrix,power_curve_mw

def main():
    cfg=json.loads((ROOT/'protocol.json').read_text())
    supplemental='--supplement' in sys.argv
    if supplemental:
        extra=json.loads((ROOT/'supplement_protocol.json').read_text());cfg['windows']=extra['windows'];cfg['seeds']=[v['seed'] for v in extra['variants']]
    policies=('huang','model') if supplemental else ('huang','old_model','model')
    def arm_folder(folder,policy):
        return ROOT.parent/'wt0929_huang_fixed_workorders/runs'/folder.relative_to(ROOT/'runs')/'model' if policy=='old_model' else folder/policy
    layout=pd.read_csv(ROOT/'inputs/layout.csv')
    curve=np.loadtxt(ROOT/'inputs/curve.csv',delimiter=',');rows=[];audits=[];hourly=[];jobs=[];distance_corrections=[]
    wake=WakeConfig(rated_power_mw=15,rotor_diameter_m=240,hub_height_m=145,wake_decay=.05,thrust_coefficient=.8)
    for stamp in cfg['windows']:
        weather=pd.read_csv(ROOT/'inputs'/f'weather_{stamp}.csv')
        for seed in cfg['seeds']:
            folder=ROOT/'runs'/stamp/str(seed)
            statuses={p:json.loads((arm_folder(folder,p)/'status.json').read_text()) for p in policies}
            horizon=max(s['simulated_hours'] for s in statuses.values())
            squares=np.array([_jensen_deficit_matrix(w,layout[['floris_x','floris_y']].to_numpy(),wake)**2 for w in weather.wind_direction_100m.iloc[:horizon]])
            speed=weather.windspeed_145m.to_numpy()[:horizon]
            healthy=power_curve_mw(np.maximum(0,speed[:,None]*(1-np.sqrt(squares.sum(axis=1)))),curve,15).sum(axis=1)
            expected=pd.read_csv(ROOT/'inputs'/f'jobs_{seed}.csv').set_index('job_id')
            for policy in policies:
                f=arm_folder(folder,policy);result=pd.read_csv(f/'job_results.csv').set_index('job_id');events=pd.read_csv(f/'events.csv')
                assert set(result.index)==set(expected.index) and result.completion_hour.notna().all()
                work=events.loc[events.action.eq('repair')].groupby('reason').duration.sum()
                assert set(work.index)==set(expected.index)
                assert np.allclose(work.reindex(expected.index),expected.required_hours,atol=1e-6),(stamp,seed,policy)
                assert abs(events.materials_cost.sum()-expected.material_eur.sum())<1e-6
                dispatch=pd.read_csv(f/'dispatch.csv')
                for r in dispatch.itertuples():
                    assert r.hour+1e-6>=expected.loc[r.job_id,'release_hour']
                    if policy=='model':assert r.hour+1e-6>=r.sequence_start_hour and 0<=r.vessel<3
                if policy=='huang':
                    for r in dispatch.itertuples():assert r.hour+1e-6>=expected.loc[r.job_id,'failure_hour']
                op=pd.read_csv(f/'operations.csv').sort_values('env_time')
                states=np.ones((horizon,67))
                states[:len(op)]=op[layout.id.tolist()].to_numpy()
                assert np.all((states>=0)&(states<=1))
                power=[]
                for h,fraction in enumerate(states):
                    ws=np.maximum(0,speed[h]*(1-np.sqrt(squares[h][fraction>0].sum(axis=0))))
                    power.append(float((power_curve_mw(ws,curve,15)*fraction).sum()))
                loss=healthy-np.asarray(power)
                travel=events.loc[events.action.eq('traveling')].copy()
                for idx,r in travel.loc[~np.isfinite(travel.distance_km)].iterrows():
                    text=str(r.additional);a,b=text.replace('traveling from ','',1).split(' to ')
                    assert a==b and r.duration==0,(stamp,seed,policy,text)
                    travel.loc[idx,'distance_km']=0.
                    distance_corrections.append(dict(window=stamp,seed=seed,policy=policy,event_index=int(idx),hour=r.env_time,additional=text,raw_distance='inf',correct_distance_km=0,duration_hours=0))
                sailing=travel.distance_km.sum()/44.448
                fixed=horizon/24*(3*4380+5999850/365.25)
                material=events.materials_cost.sum();fuel=sailing*400;revenue=loss.sum()*80
                assert np.isfinite([material,fuel,revenue,fixed,sailing]).all()
                repair_start=events.loc[events.action.eq('repair')].groupby('reason').env_time.min()
                early=(repair_start.reindex(expected.index)<expected.failure_hour).sum()
                decisions=json.loads((f/'decisions.json').read_text())
                limits=sum(x['status']=='TIME_LIMIT' for x in decisions)
                rows.append(dict(window=stamp,seed=seed,policy=policy,jobs_completed=len(result),work_hours=work.sum(),material_eur=material,common_hours=horizon,finish_hour=statuses[policy]['finish_hour'],early_started=int(early),early_completed=int(result.early_complete.sum()),lost_mwh=loss.sum(),fixed_eur=fixed,fuel_eur=fuel,sailing_hours=sailing,travel_legs=len(travel),total_eur=fixed+material+fuel+revenue,time_limit_days=limits))
                audits.append(dict(window=stamp,seed=seed,policy=policy,same_job_ids=True,all_complete=True,exact_work=True,exact_material=True,no_information_leak=True,common_hours=horizon))
                hourly.extend(dict(window=stamp,seed=seed,policy=policy,hour=h,potential_mwh=healthy[h],actual_mwh=power[h],lost_mwh=loss[h]) for h in range(horizon))
                for key,r in result.iterrows():jobs.append(dict(window=stamp,seed=seed,policy=policy,job_id=key,start_hour=repair_start[key],finish_hour=r.completion_hour,failure_hour=r.failure_hour,early_complete=r.early_complete))
    out=ROOT/('summary_supplement' if supplemental else 'summary');out.mkdir(exist_ok=True)
    frame=pd.DataFrame(rows)
    frame.groupby('policy').mean(numeric_only=True).to_csv(out/'means.csv');frame.to_csv(out/'runs.csv',index=False)
    frame.groupby('policy').mean(numeric_only=True).to_csv(out/'means.csv')
    pd.DataFrame(distance_corrections).to_csv(out/'self_distance_corrections.csv',index=False)
    pd.DataFrame(audits).to_csv(out/'equal_work_audit.csv',index=False)
    pd.DataFrame(hourly).to_csv(out/'hourly_energy.csv',index=False)
    pd.DataFrame(jobs).to_csv(out/'job_comparison.csv',index=False)
    paired=[]
    a=frame[frame.policy.eq('model')].set_index(['window','seed']);b=frame[frame.policy.eq('huang')].set_index(['window','seed'])
    for metric in ('total_eur','lost_mwh','sailing_hours','finish_hour'):
        delta=(a[metric]-b[metric]).groupby('window').mean();rng=np.random.default_rng(20261127)
        means=delta.to_numpy()[rng.integers(0,len(delta),size=(10000,len(delta)))].mean(axis=1)
        paired.append(dict(metric=metric,model_minus_huang=float(delta.mean()),lower=float(np.quantile(means,.025)),upper=float(np.quantile(means,.975))))
    pd.DataFrame(paired).to_csv(out/'paired_intervals.csv',index=False)
    print(frame.groupby('policy')[['jobs_completed','work_hours','material_eur','early_started','early_completed','total_eur','lost_mwh','sailing_hours','finish_hour']].mean().to_string())
    print('ALL EQUAL-WORK AND EXECUTION-ADMISSION AUDITS PASSED',len(frame))

if __name__=='__main__':main()
