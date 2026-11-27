# 安装与复现

下载完整仓库后，首先运行 `python verify_package.py` 校验发布文件与结果完整性。查看已有数据不需要 COPT 许可证。打开 `wt0929_huang_economic_mpc/实验索引.html` 可查看本地结果。

## 环境

实验原生仿真环境采用 Python 3.11；COPT 环境采用 Python 3.7.12。两个环境分离，通过标准输入输出交换 JSON。为尽量贴近原运行，请使用锁定依赖；Python 3.7 已停止维护，此处只用于复现实验历史求解环境。

```powershell
py -3.11 -m venv .venv-native
.\.venv-native\Scripts\python.exe -m pip install -r requirements-native.txt

# 在已安装的 Python 3.7.12 或相应 conda 环境中安装求解依赖
python -m pip install -r requirements-solver.txt
```

重新求解需要合法可用的 COPT 许可证。仓库不包含许可证、Python 安装或虚拟环境。

在 PowerShell 中设置本机解释器路径：

```powershell
$env:WT_NATIVE_PYTHON = (Resolve-Path '.\.venv-native\Scripts\python.exe').Path
$env:WT_SOLVER_PYTHON = '本机COPT环境的python.exe绝对路径'
```

若安装环境允许同时运行 WOMBAT 与 COPT，也可以把两个变量指向同一个兼容环境；这不保证与历史依赖组合逐位一致。未设置变量时默认为当前 Python。原实验电脑上的硬编码路径已由这两个变量替代，差异见 `provenance/portability_changes.diff`。

## 验证和重新运行

```powershell
& $env:WT_SOLVER_PYTHON wt0929_huang_economic_mpc/test_economic.py
& $env:WT_NATIVE_PYTHON wt0929_huang_economic_mpc/run_batch.py
& $env:WT_NATIVE_PYTHON wt0929_huang_economic_mpc/run_supplement.py
& $env:WT_SOLVER_PYTHON wt0929_huang_economic_mpc/evaluate.py
& $env:WT_SOLVER_PYTHON wt0929_huang_economic_mpc/evaluate.py --supplement
& $env:WT_SOLVER_PYTHON wt0929_huang_economic_mpc/audit_execution.py
& $env:WT_SOLVER_PYTHON wt0929_huang_economic_mpc/analyze_drivers.py
```

批量脚本默认跳过已有且已全部完成的场景。需要重算时，先复制仓库另作运行目录并备份结果，再在新副本中增加 `--force` 参数。单场景调用始终重新运行并覆盖该场景文件，例如：

```powershell
& $env:WT_NATIVE_PYTHON wt0929_huang_economic_mpc/run_case.py 2016-07-01 834 model
```

`run_case.py` 自动从仓库内公共配置重建逐次运行库，不需要原工作区其他目录。旧模型对照的24份轨迹已打包，用于三组同终点后处理。

预测功率与补充工单已冻结随仓库提供。如需核查生成过程：

```powershell
& $env:WT_SOLVER_PYTHON wt0929_huang_economic_mpc/prepare_forecasts.py
& $env:WT_SOLVER_PYTHON wt0929_huang_economic_mpc/prepare_supplement.py
```

原始天气的 gzip 文件仅为来源存档，正式执行使用 `inputs/weather_*.csv`；可用 Python gzip 解压原始天气，无需解压即可运行正式场景。

## 报告和完整性记录

生成 Word 报告需要另一个装有 `python-docx` 的现代 Python 环境，执行 `build_report.py`。该步骤不参与优化求解。发布版 Word 已经渲染检查。

`wt0929_release/MANIFEST_SHA256.csv` 验证本仓库所收录的原模型文件；完整原项目355个文件的历史验证记录在 `provenance/`。重新执行审计时，原版文件计数以本仓库收录范围为准。

3秒限时求解可能随设备速度和软件版本选择不同可行解。请保留实际求解状态、最优间隙和执行日志，不要求重新运行逐位匹配历史输出；固定工单、物理条件和计费口径应保持一致。
