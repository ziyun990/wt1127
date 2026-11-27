"""Prespecified geometry variants retain the same workload/materials as seed 834."""
from pathlib import Path
import pandas as pd
import numpy as np
import json,hashlib
ROOT=Path(__file__).resolve().parent
layout=pd.read_csv(ROOT/'inputs/layout.csv');coords=layout[['floris_x','floris_y']].to_numpy()
original=pd.read_csv(ROOT/'inputs/jobs_834.csv');variants=[]
rng=np.random.default_rng(834);anchor=int(rng.integers(len(layout)))
near=np.argsort(np.linalg.norm(coords-coords[anchor],axis=1))[:24]
cluster=original.copy();cluster.turbine=near;cluster.asset=layout.id.iloc[near].to_numpy();cluster.job_id='CL_'+cluster.job_id
groups=[[] for _ in range(12)];assigned=[]
for row in original.itertuples():
    choice=next(i for i,g in enumerate(groups) if len(g)<2 and row.component not in g)
    groups[choice].append(row.component);assigned.append(int(original.turbine.iloc[choice]))
multi=original.copy();multi.turbine=assigned;multi.asset=layout.id.iloc[assigned].to_numpy();multi.job_id='MC_'+multi.job_id
for seed,frame,label in [(1834,cluster,'nearby distinct turbines'),(2834,multi,'two different components per turbine')]:
    assert len(frame)==24 and frame.required_hours.sum()==original.required_hours.sum() and frame.material_eur.sum()==original.material_eur.sum()
    assert not frame.duplicated(['asset','component']).any()
    file=ROOT/'inputs'/f'jobs_{seed}.csv';frame.to_csv(file,index=False)
    variants.append(dict(seed=seed,scope=label,sha256=hashlib.sha256(file.read_bytes()).hexdigest(),jobs=24,work_hours=int(frame.required_hours.sum()),materials_eur=float(frame.material_eur.sum())))
(ROOT/'supplement_protocol.json').write_text(json.dumps(dict(windows=['2016-01-01','2016-04-01','2016-07-01','2016-10-01'],variants=variants,decision='fixed geometry variants; no outcome selection; secondary evidence only'),indent=2))
print(json.dumps(variants,indent=2))
