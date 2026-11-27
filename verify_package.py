"""Verify all publication hashes and the equal-work numerical results, without COPT."""
from pathlib import Path
import csv,json,math,hashlib
ROOT=Path(__file__).resolve().parent
EXP=ROOT/'wt0929_huang_economic_mpc'

def read(path):
    with path.open(encoding='utf-8-sig',newline='') as stream:return list(csv.DictReader(stream))

def main():
    manifest=ROOT/'MANIFEST_SHA256.csv'
    entries=read(manifest) if manifest.exists() else []
    for row in entries:
        f=ROOT/row['path'];assert f.is_file(),row['path']
        assert hashlib.sha256(f.read_bytes()).hexdigest()==row['sha256'],row['path']
    counts={}
    for name,number,arms in [('summary',72,3),('summary_supplement',16,2)]:
        rows=read(EXP/name/'runs.csv');assert len(rows)==number
        groups={}
        for r in rows:
            assert int(float(r['jobs_completed']))==24
            for key in ('total_eur','lost_mwh','fuel_eur','sailing_hours','material_eur','work_hours'):assert math.isfinite(float(r[key]))
            groups.setdefault((r['window'],r['seed']),[]).append(r)
        for group in groups.values():
            assert len(group)==arms
            for field in ('work_hours','material_eur','common_hours','fixed_eur'):
                values=[float(r[field]) for r in group];assert max(values)-min(values)<1e-6
        counts[name]=number
    cases=0
    for file in (EXP/'runs').glob('*/*/*/status.json'):
        status=json.loads(file.read_text());assert status['complete']==status['required']==24
        assert len(read(file.parent/'job_results.csv'))==24;cases+=1
    assert cases==64,cases
    old=list((ROOT/'wt0929_huang_fixed_workorders/runs').glob('*/*/model/status.json'));assert len(old)==24
    for file in old:assert json.loads(file.read_text())['complete']==24
    for item in json.loads((EXP/'inputs/frozen_manifest.json').read_text()):assert hashlib.sha256((EXP/'inputs'/item['file']).read_bytes()).hexdigest()==item['sha256']
    result=dict(success=True,hashed_files=len(entries),latest_trajectories=cases,old_control_trajectories=len(old),result_rows=counts,frozen_workorders=True,equal_work_and_material=True)
    print(json.dumps(result,indent=2))
    return result

if __name__=='__main__':main()
