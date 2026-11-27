"""Mechanism fixtures independent of the formal work orders."""
import sys,io,json
from pathlib import Path
import numpy as np
saved=sys.stdin;sys.stdin=io.StringIO('')
from solver_worker import solve
sys.stdin=saved
base=dict(hour=6,safe=np.ones(672,int).tolist(),power=np.r_[np.zeros(120),np.ones(552)*15].tolist(),coords=np.zeros((67,2)).tolist(),distances=np.zeros((67,67)).tolist(),ships=[dict(node=-1,available_hour=6) for _ in range(3)])
job=dict(job_id='long_PM',turbine=0,component='shaft',remaining=36,required_hours=36,material_eur=1000,failure_hour=126,release_hour=0,reduction=.5)
r=solve(dict(base,jobs=[job]))
assert r['plan'] and r['plan'][0]['predicted_finish']<126,r
print('PASS long preventive job spans days and finishes before failure without reward')
short=dict(job,job_id='a',remaining=2,required_hours=2)
other=dict(short,job_id='b',turbine=1)
r=solve(dict(base,jobs=[short,other]))
assert any(len(route['jobs'])==2 and abs(route['distance_km']-106)<1e-6 for route in r['selected_routes']),r
print('PASS shared sailing is 106 km for a two-job sequence, not 212 km')
assert '300000' not in Path(__file__).with_name('solver_worker.py').read_text()
print('PASS objective contains no corrective completion premium')
Path(__file__).with_name('mechanism_tests.json').write_text(json.dumps(dict(long_preventive=True,shared_route=True,no_completion_reward=True),indent=2))
