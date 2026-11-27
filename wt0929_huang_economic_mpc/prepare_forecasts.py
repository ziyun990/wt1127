"""Cache the identical public-weather, Jensen-adjusted forecasting basis."""
from pathlib import Path
import sys,json
import pandas as pd
import numpy as np
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'wt0929_release'))
from cl_stochos_mu import WakeConfig,_jensen_deficit_matrix,power_curve_mw
layout=pd.read_csv(ROOT/'inputs/layout.csv')[['floris_x','floris_y']].to_numpy()
curve=np.loadtxt(ROOT/'inputs/curve.csv',delimiter=',')
cfg=WakeConfig(rated_power_mw=15,rotor_diameter_m=240,hub_height_m=145,wake_decay=.05,thrust_coefficient=.8)
for date in json.loads((ROOT/'protocol.json').read_text())['windows']:
    weather=pd.read_csv(ROOT/'inputs'/f'weather_{date}.csv');output=[]
    for row in weather.itertuples():
        deficits=_jensen_deficit_matrix(row.wind_direction_100m,layout,cfg)
        speed=np.maximum(0,row.windspeed_145m*(1-np.sqrt((deficits**2).sum(axis=0))))
        output.append(power_curve_mw(speed,curve,15))
    np.savez_compressed(ROOT/'inputs'/f'forecast_power_{date}.npz',power=np.array(output))
    print('FORECAST',date,flush=True)
