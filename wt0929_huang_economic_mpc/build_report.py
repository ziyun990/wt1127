"""Publish absolute results, explicit implementation limits and a local evidence index."""
from pathlib import Path
import csv,json,html,hashlib,shutil
from docx import Document
from docx.shared import Cm,Pt,RGBColor
from docx.oxml.ns import qn
ROOT=Path(__file__).resolve().parent
def read(path):
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
means={r['policy']:r for r in read(ROOT/'summary/means.csv')}
labels={'huang':'Huang 基准','old_model':'旧固定工单模型','model':'经济滚动修订版'}
table=[['指标']+[labels[p] for p in labels]]
for key,label in [('jobs_completed','完成工单数'),('work_hours','有效维修工时'),('material_eur','材料费用 欧元'),('early_started','提前启动工单数'),('early_completed','提前完成工单数'),('lost_mwh','损失电量 MWh'),('sailing_hours','等效航行小时'),('fuel_eur','燃油费用 欧元'),('finish_hour','最后工单完成时刻 小时'),('total_eur','总费用及收入损失 欧元')]:
    table.append([label]+[f'{float(means[p][key]):,.2f}' for p in labels])
early=sum(float(r['early_completed']) for r in read(ROOT/'summary/runs.csv') if r['policy']=='model')
cost_change=float(means['model']['total_eur'])/float(means['huang']['total_eur'])-1
loss_change=float(means['model']['lost_mwh'])/float(means['huang']['lost_mwh'])-1
sections=[('修订结果与结论',[
 '本次实验移除故障任务的 300000 元净完工奖励和 1000 元每天风险暴露奖励，使用发电损失与航行燃油费用决定排程。所有工单最终必须完成，材料费用和有效维修总工时固定，优化目标不再为提前或故障后完成额外设置奖励。旧固定工单实验保留作为对照。',
 f'主实验采用原来冻结的 24 个场景，每组每场景完成同一批 24 张工单。修订版共提前完成 {early:.0f} 张工单。下表为各场景的绝对结果均值，三组按每个场景共同评价终点重新统计，避免固定费用统计时长不同。相对 Huang 基准，总费用及收入损失变化 {cost_change:+.2%}，损失电量变化 {loss_change:+.2%}；改善与否均按实际输出报告。',
 '本次属于修订后的经济滚动排程策略实验。原代码的候选生成模块继续使用，排程部分新增路线模式混合整数规划；两组使用同一个原生 WOMBAT 物理执行层。不能将它表述为未修改原始 wt0929_release 的直接验证。',
 '综合费用改善伴随完成时间的取舍：修订版最后工单平均完成时刻为 2790.35 小时，Huang 基准为 2370.97 小时，相差 419.37 小时。当前经济目标允许推迟部分发电影响较小的任务，尚未纳入合同服务时限或积压任务管理约束。不能仅以成本降低宣称所有运营指标均改善。'
]),('经济目标与多日滚动计算',[
 '目标包含航距除以船速再乘燃油费、维修停机发电损失、未维修故障的降额发电损失，以及未完任务的后续成本估计。实际评价另计完整材料费与共同固定费。两种维修时机使用相同工时和材料费；300000 元完工奖励和 1000 元每天风险暴露项均不出现在新优化目标中。',
 '每日 06:00 更新已释放工单、实际维修进度和船舶状态，规划未来 14 天，只开放当前可执行的船舶任务序列，次日重新求解。未发布工单不进入优化器。工单的确定性故障截止时刻从信息释放后可用；候选生成的 14 天提前期用于覆盖规划窗口，不代表真实 RUL 预测器。',
 '窗口末未完任务使用额外 14 天天气预测生成后续维修路径及故障等待成本估计。若后续记录内仍无可完成路径，使用该段天气下的降额损失、平均发电机会成本和必要航行费估计继续处理成本。该终端值是近似继续成本，不是严格的无限时域最优价值。预测条件采用双方共同可用的实际天气预知情景。',
 '候选路径模式包含单任务和两个邻近任务的连续服务，允许长任务跨班次、跨日完成；有效作业进度在原生执行层持续保存。优化器为三个船舶分配任务序列，对船舶占用和同机单团队维修施加约束。多部件情景按工单分别保留 RUL，避免同机部件状态相互覆盖。',
 '成本接近相等时采用极小的完成时刻项进行确定性破平，量级为每小时百万分之一欧元；它不构成故障任务或提前任务的专属奖励。COPT 单线程、每次最多 3 秒、相对间隙目标 0.5%；时限内可行解和间隙均保存在逐日 decisions.json。'
]),('航行执行与费用核验',[
 '航距使用原生 WOMBAT 的机位距离矩阵，港场距离沿用 53 km，船速 44.448 km/h。连续服务序列只增加机位之间的航程，不对每张任务独立收取一次完整港场往返费用。人员转移、天气等待、实际航行和跨日返航由 WOMBAT 原生过程执行。',
 '接入层按优化结果限制允许接单的船舶、任务序列和序列最早启动时刻。船未到达、维修海况不满足时，不允许将计划工时当作实际完成量。原生程序决定实际到达与施工时刻；后续日滚动重新读取已完成进度。',
 '规划路径采用连续小时天气区间模拟，包含往返和跨日服务的近似处理；它不是 WOMBAT 内部所有秒级动作的逐步复制。32 个修订场景的 768 张工单中，开工时刻预测绝对误差均值约为 2.40 小时，完工时刻误差均值约为 29.97 小时，最大完工误差约为 1342.94 小时。长工单与天气等待的预测仍需校准，尚不能宣称精确逐时计划得到完整执行。报告中的成本仅来自已执行的原生事件和状态。',
 '规划发电输入按公开天气、功率曲线和 Jensen 尾流生成全健康机组功率。路径模式的停机和降额损失采用可加近似，不精确展开多个机组同时停机时的全部尾流交互；实际评价根据各组同时停机状态重算全场尾流。该预测近似仍是模型误差来源，应与策略收益一并说明。',
 '受控测试检验了长预防任务跨日完成且早于故障时刻、两个同址任务连续服务只需 106 km 而不是 212 km，以及新求解目标不含原故障完工奖励。基准组通过与旧基准的 1361 条事件精确回放，证明状态记录接入未改变基准行为。',
 '同机多部件场景揭示了原生日志的自环距离问题：从同机位到同机位的航行时长为零，距离却记为无穷大。统一后处理仅对经核对的同起终点且零时长航段将结算距离设为零，两组处理一致，原始日志保留，修正清单见 summary_supplement/self_distance_corrections.csv。',
 '全部修订场景共有 9 次日优化达到时间上限；其中部分最优间隙为极大数，表示未获得有效有限界，不能解释为已证明接近最优。采用的整数可行解或可行暂缓方案会进入下一次滚动。原始状态和间隙见 summary/solver_statuses.csv。'
]),('数据 公平性与补充情景',[
 '主实验的公开天气、布局、功率曲线、维修参数和三份冻结工单均沿用旧固定工单实验，输入哈希可核对。每份 24 张工单，信息在前 21 天释放，未维修故障时刻为释放后 7 天；预防与故障维修工时、材料费相同。关闭新随机故障和重复故障，保证两组工作量一致。',
 '主实验使用 2016 年与 2017 年 1 月、4 月、7 月、10 月的 8 个窗口，随机种子为 834、835、836。三个策略共享每场景的共同评价终点；先完成且全场恢复健康的策略延续健康发电至该终点。365 天为共同清理上限，不按结果筛除场景。',
 '补充实验将原种子 834 的同一份工单变换为两类几何场景：24 个邻近但不同机位，以及每台机组两个不同部件的 12 机位场景。工单类型、工时、材料费、释放及故障时刻不变，两组使用相同变换。采用 2016 年四季窗口，形成 8 个配对补充场景。主实验与补充结果分别统计，避免混合构造任务类型后改变总体权重。',
 '逐场景审计检查已完成工单编号、每单有效维修工时、材料费和信息释放约束。修订版额外检查派工船舶及序列最早启动时刻。完整实际日志、逐日预测路径、原生运行状态和统一发电后处理数据均可从实验索引打开。',
 '本次仍限定于 CTV 任务和理想信息条件，不代表 Huang 原论文多年浮式风场全范围复现。新增序列最多含两个连续任务，不能宣称已求解任意长度多机位全局航线。重复故障收益与真实 RUL 预测精度需要另行验证。'
])]
doc=Document();sec=doc.sections[0];sec.top_margin=sec.bottom_margin=Cm(1.6);sec.left_margin=sec.right_margin=Cm(1.8)
for name in ('Normal','Title','Heading 1'):
    st=doc.styles[name];st.font.name='Calibri';st._element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'),'宋体');st.font.color.rgb=RGBColor(0,0,0)
    if name=='Normal':st.font.size=Pt(10)
    else:st.font.bold=False
for element in doc.styles.element.iter():
    for border in list(element.findall(qn('w:pBdr'))):element.remove(border)
for i,(title,texts) in enumerate(sections):
    if i:doc.add_page_break()
    else:doc.add_paragraph('Huang 固定工单经济滚动排程修订实验',style='Title')
    doc.add_heading(title,1)
    for j,t in enumerate(texts):
        doc.add_paragraph(t)
        if i==0 and j==1:
            tab=doc.add_table(rows=0,cols=4);tab.style='Table Grid'
            for row in table:
                for c,v in zip(tab.add_row().cells,row):c.text=v
if (ROOT/'summary_supplement/means.csv').exists():
    doc.add_heading('补充场景结果',1)
    extra=read(ROOT/'summary_supplement/means.csv');tab=doc.add_table(rows=1,cols=5);tab.style='Table Grid'
    for c,v in zip(tab.rows[0].cells,['策略','提前完成数','损失电量 MWh','航行小时','总费用 欧元']):c.text=v
    for r in extra:
        vals=[labels[r['policy']]]+[f'{float(r[k]):,.2f}' for k in ('early_completed','lost_mwh','sailing_hours','total_eur')]
        for c,v in zip(tab.add_row().cells,vals):c.text=v
    doc.add_paragraph('以上为两类构造情景在四季窗口的平均值，仅作为机制补充证据；逐场景绝对结果见 summary_supplement/runs.csv。')
doc.save(ROOT/'经济滚动修订实验报告.docx')
parts=['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>经济滚动修订实验</title><style>body{font:16px/1.7 system-ui;max-width:1150px;margin:30px auto;padding:20px}td,th{border:1px solid #bbb;padding:7px}table{border-collapse:collapse}a{color:#075a9c}</style><h1>Huang 固定工单经济滚动修订实验</h1><p><a href="经济滚动修订实验报告.docx">打开 Word 报告</a></p>']
for i,(title,texts) in enumerate(sections):
    parts.append('<h2>'+html.escape(title)+'</h2>')
    for t in texts:parts.append('<p>'+html.escape(t)+'</p>')
    if not i:parts.append('<table>'+''.join('<tr>'+''.join('<td>'+html.escape(c)+'</td>' for c in row)+'</tr>' for row in table)+'</table>')
parts.append('<h2>输入 代码与审计</h2><ul>')
files=list(ROOT.glob('*.py'))+list(ROOT.glob('*.json'))+list(ROOT.glob('*.txt'))+list((ROOT/'inputs').glob('jobs*'))+list((ROOT/'summary').glob('*'))+list((ROOT/'summary_supplement').glob('*'))
for f in sorted(files):
    if f.is_file():parts.append(f'<li><a href="{f.relative_to(ROOT).as_posix()}">{html.escape(str(f.relative_to(ROOT)))}</a></li>')
parts.append('</ul><h2>逐次运行的中间结果</h2><ul>')
for folder in sorted((ROOT/'runs').glob('*/*/*')):
    if folder.name not in ('huang','model'):continue
    links=[f'<a href="{f.relative_to(ROOT).as_posix()}">{f.name}</a>' for f in sorted(folder.glob('*')) if f.is_file()]
    parts.append('<li>'+html.escape(str(folder.relative_to(ROOT)))+' '+' | '.join(links)+'</li>')
parts.append('</ul></html>');(ROOT/'实验索引.html').write_text(''.join(parts),encoding='utf-8')
snapshot=ROOT/'source_snapshot';snapshot.mkdir(exist_ok=True)
shutil.copy2(ROOT.parent/'wt0929_release/cl_stochos_mu.py',snapshot/'cl_stochos_mu.py')
with (ROOT/'summary/code_input_sha256.csv').open('w',newline='',encoding='utf-8') as stream:
    w=csv.DictWriter(stream,fieldnames=['path','sha256']);w.writeheader()
    for f in list(ROOT.glob('*.py'))+list((ROOT/'inputs').glob('*')):
        if f.is_file():w.writerow(dict(path=str(f.relative_to(ROOT)),sha256=hashlib.sha256(f.read_bytes()).hexdigest()))
print('Created report and local evidence index')
