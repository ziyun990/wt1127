# Huang 等（2026）WOMBAT 基准复现

复现 IEA Wind Task 49 Humboldt 风场的 `base` 算例。67 台风机各 15 MW，仿真覆盖 1999–2018 年，起始随机数生成器为 `numpy.random.default_rng(834)`。作者的 20 次仿真沿用同一个随机数流。

## 来源

- [论文第 3.1 节](https://wes.copernicus.org/articles/11/3031/2026/#section3)与[图 4](https://wes.copernicus.org/articles/11/3031/2026/wes-11-3031-2026-f04.png)、[图 9](https://wes.copernicus.org/articles/11/3031/2026/wes-11-3031-2026-f09.png)。
- `source/` 为作者 [WAVES 仓库](https://github.com/NatLabRockies/WAVES/tree/cc843037e5f1d2a2513ecfbef9e6cd93a17fcc30)的固定提交。`reference/iea49_sha256.json` 记录该算例公开文件的 SHA-256。
- `reference/wombat_base.xlsx` 为原始[参考结果表](https://github.com/NatLabRockies/WAVES/blob/cc843037e5f1d2a2513ecfbef9e6cd93a17fcc30/library/IEA_49/results/wombat_base.xlsx)。文件内部记录的生成时间为 2025-10-20 UTC。
- `reference/iea49_analysis_workbook_era.py` 来自[参考表生成前最近一次修改分析脚本的提交](https://github.com/NatLabRockies/WAVES/commit/51771205d6e8932470e24354199b12200252cc2c)。作者在[后续提交](https://github.com/NatLabRockies/WAVES/commit/c5508b449b074adcea860cd3c105ff1b0bef51bc)中改用 WOMBAT 的潜在、实际发电量之差计算停机损失。复现脚本在同一次仿真上输出两种算法的数值。

## 运行

使用 Python 3.11。`requirements-reproduction.txt` 固定数值和仿真依赖的候选版本。作者备注中的 WAVES 0.5.3 正式标签要求 Python <3.11，故优先选用脚本声明支持、且在参考表生成时已发布的 WAVES 0.6.1 和 WOMBAT 0.12.2。成功安装的完整依赖清单保存于 `logs/installed-packages.txt`。

```powershell
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements-reproduction.txt
& .\.venv\Scripts\python.exe run_baseline.py --runs 20 results/reproduction
& .\.venv\Scripts\python.exe compare_baseline.py results/reproduction
& .\.venv\Scripts\python.exe compare_baseline.py results/reproduction --workbook-era
```

运行目录应为尚未创建的目录。脚本复制必要输入，在每次仿真完成后写入当时已有的 `Project.csv`、`Project_workbook_era.csv`、`MonthYear.csv`。`run.json` 记录代码提交、依赖版本、年份和随机数初始化值。

逐列核对表按运行编号及年月匹配，数值判同容差为绝对误差 `1e-10` 与相对误差 `1e-9`。期间累计任务完成率取该次运行期末累计完成数除以累计提交数，随后对各次运行的完成率取算术平均。`published_figures.csv` 保留论文图中所标示的数值，并列出与参考表和重跑结果的差异。

## 首轮核对

用相同输入及随机数初始化分别测试了 WOMBAT 0.12.1、0.12.2 和 0.12.3。三版的 `Project.csv` 和 `MonthYear.csv` 的 SHA-256 均一致。相对作者的第 0 次运行，1999 年 1 月至 2004 年 7 月的月度时间可利用率一致，2004 年 8 月首次相差约 1 个机组小时。20 年总体时间可利用率为 75.0022%，参考表为 74.4816%。发电量可利用率为 73.5185%，参考表为 72.7939%。维护总成本为 96.7398，参考表为 95.0107，单位为千欧元/(MW·年)。原因仍待进一步区分。

图 4 的停机损失可按公开代码后期采用的口径回算。首轮模拟的全可利用发电收入为 398.4482 千欧元/(MW·年)，乘以参考表 20 次平均发电量不可利用率 22.3310%，得到 88.9773 千欧元/(MW·年)，与图 4 标示的 89.0 一致到其公布精度。这里使用了参考表的可利用率，属于统计口径核对。计算记录为 `results/pilot/figure4_loss_reconciliation.csv`。

## 原版批次异常与修正批次

`results/reproduction/` 保存未修改 WOMBAT 0.12.2 的批次输出。第 8 次运行（编号 7）在仿真时间 2017-02-26 19:28:21 中断。根据 `run08_derating_events.csv`，机组 `g` 的变桨系统先在小修期间发生大修故障并降至 0.5，随后小修结束时被恢复至旧状态 1.0。大修完成时，WOMBAT 反算撤销 50% 降额，将运行水平从 1.0 抬至 2.0。下次故障创建修理请求时，运行水平超出 `[0, 1]` 校验范围。

前 7 次共保存 1,680 条月度记录。其平均维护成本为 96.3266 千欧元/(MW·年)，同编号参考值为 96.6981。平均时间可利用率为 82.8756%，参考值为 80.6776%。平均发电量可利用率为 80.9628%，参考值为 78.7183%。按参考表生成时的收入损失公式计算，平均损失为 121.1322 千欧元/(MW·年)，参考值为 129.6953。逐列差异和均值区间保存于 `results/reproduction/workbook_era_comparison/`。

`results/derating_correction/` 使用同一随机数初始化及公开输入，增加 `--preserve-concurrent-derating`。该选项在不带降额的小修结束时保留任务期间新增的降额，并把命中的时间、工单及运行水平写入 `logs/derating_correction.log`。这是本地修正，结果应按修正后的 WOMBAT 基准引用。未修改引擎的前 7 次结果、原始异常日志和修正批次输出分别保存。

```powershell
& .\.venv\Scripts\python.exe run_baseline.py --runs 20 --preserve-concurrent-derating results/derating_correction
& .\.venv\Scripts\python.exe compare_baseline.py results/derating_correction
& .\.venv\Scripts\python.exe compare_baseline.py results/derating_correction --workbook-era
```
