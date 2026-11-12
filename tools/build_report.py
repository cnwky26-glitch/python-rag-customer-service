"""从真实评估输出生成 README、可编辑报告与召回曲线。"""
import json
import os
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from pdf2image import convert_from_path
from reportlab.graphics import renderPDF
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors

ROOT = Path(__file__).resolve().parents[1]
summary = json.loads((ROOT / "results/summary.json").read_text(encoding="utf-8"))
manifest = json.loads((ROOT / "data/manifest.json").read_text(encoding="utf-8"))
calibration = json.loads((ROOT / "results/threshold_calibration.json").read_text(encoding="utf-8"))
baseline = json.loads((ROOT / "results/baseline/summary.json").read_text(encoding="utf-8"))
official = next(item for item in summary["experiments"] if item["official"])
detail = json.loads((ROOT / f'results/{official["name"]}.json').read_text(encoding="utf-8"))
vector = next(item for item in summary["experiments"] if item["chunk_size"] == official["chunk_size"] and item["mode"] == "vector")
old = next(item for item in baseline["experiments"] if item["official"])
percent = lambda value: f"{value * 100:.1f}%"
rows = "\n".join(f'| {r["chunk_size"]}/{r["overlap"]} | {r["mode"]} | {r["chunks"]} | {percent(r["recall_at_5"])} | {r["p50_ms"]:.2f} | {r["p95_ms"]:.2f} |' for r in summary["experiments"])
readme = f'''# Python 官方文档智能客服检索系统

本项目实现客服知识库的清洗、分块、嵌入、批量写入、索引、过滤、混合检索和真实评估。返回可核验的原文片段与官方来源链接。

## 实测结果

- 数据：{manifest["source_page_count"]} 个 Python 3.13 官方中文文档页面，提取 **{summary["documents"]} 条独立 API 文档**；正式方案为 {official["chunks"]} 个块。文档数与块数分别统计。
- 正式配置：chunk_size={official["chunk_size"]} 字符，overlap={official["overlap"]} 字符，余弦阈值 {summary["threshold"]}。
- 固定 20 题：Recall@5 **{percent(official["recall_at_5"])}**，P95 **{official["p95_ms"]:.2f} ms**。
- 每题重复 {summary["repeats"]} 次，共 {official["request_count"]} 个串行稳态计时请求。重复请求用于延迟采样，题目数量仍是 20。
- 6 条额外负例（含不存在的模块、版本）拒答率：{percent(summary["no_answer_rejection_after"])}。
- 首轮实测 Recall@5 为 {percent(old["recall_at_5"])}，完整失败结果保存在 `results/baseline/`，未覆盖或美化。

## 快速运行

需要 Python 3.12。当前机器的 `.venv`、模型缓存和本地库已准备好，可直接运行：

```powershell
cd C:\\Prj\\AIDBS\\期末作业
.\\.venv\\Scripts\\python.exe main.py query "如何递归复制整个目录？" --module shutil
.\\.venv\\Scripts\\python.exe main.py query "我的快递丢失了，赔偿多少钱？"
.\\.venv\\Scripts\\python.exe main.py query "如何读取文本文件？" --module unknown_module
```

后两条预期返回 `"status": "未找到"` 和空的 `results`。正常检索返回最多 5 个不同 doc_id 的证据条目，包含原文、余弦相似度、融合分数、模块、版本和来源。

在新环境安装并重建：

```powershell
python -m venv .venv
.\\.venv\\Scripts\\python.exe -m pip install -r requirements-lock.txt
# 使用仓库内的官方 HTML 快照，离线提取数据
.\\.venv\\Scripts\\python.exe main.py prepare
# 首次执行需要联网下载约 90 MB 的公开模型，之后使用 .cache/models
.\\.venv\\Scripts\\python.exe main.py build
.\\.venv\\Scripts\\python.exe main.py query "如何按容差比较浮点数？" --module math
```

`python` 应指向 Python 3.12。若需更新官方网页，再运行 `main.py prepare --download`；刷新会改变快照及校验值，不能与本次结果混作同一次实验。

## 复现实验

```powershell
.\\.venv\\Scripts\\python.exe tools/tune_retrieval.py
.\\.venv\\Scripts\\python.exe main.py evaluate
```

调参脚本需要先建库，只读取 `data/dev_questions.jsonl`。`evaluate` 重建配置指定的正式表及分块对照表，输出 JSON 和 CSV。它不访问付费服务，不需要 API Key。已有表会被重建，实验输出会更新；首轮留档目录保留。

在本次受限执行环境中，LanceDB 创建异步事件循环需要本地套接字权限，沙箱内导入可能阻塞。本次实跑使用了获准的本地执行环境。普通 PowerShell 中按以上命令执行即可；不要用异常吞掉这个环境问题。

## 目录

```text
main.py                       命令行入口
config.toml                   数据、模型、分块、索引、检索及评估参数
kb/prepare.py                 HTML 快照提取与清洗
kb/core.py                    分块、嵌入、批量建库、过滤及混合检索
kb/evaluate.py                阈值校准、20 题评估和原始计时
data/raw/                     20 份官方 HTML 快照
data/documents.jsonl           独立 API 文档与来源
data/manifest.json            文档计数、来源和 SHA256
data/model_manifest.json      模型仓库版本、文件校验值
data/test_questions.jsonl      20 道测试题及相关文档标注
data/dev_questions.jsonl       开发集，8 正例与 8 负例
data/no_answer_questions.jsonl 6 条额外拒答检查
results/summary.json           正式结果、环境和指标定义
results/chunk_*.json           每题证据及逐请求计时
results/comparison.csv         分块及双路召回对比
results/baseline/              首轮配置、核心代码、日志与失败结果
results/rrf_doc_fusion/        文档级 RRF 中间结果
results/evaluation.log         最终真实运行日志
storage/lancedb/               本地向量库，可由 build/evaluate 重建
作业报告.docx                  可编辑报告
学习与提交核对.md              需本人理解、审核、撰写的部分
```

## 数据与清洗

来源为 Python 3.13 官方中文标准库文档，覆盖 json、csv、pathlib、正则、日期、文件操作、数据库等 20 个模块。每个带独立锚点、具有非空说明的 API 定义是一条文档，不把切块充当独立文档。原始网页、文档来源与许可证已保存。

清洗执行 NFKC 规范化、空白合并及导航锚点符号清理；提取 API 的签名和说明；类说明中的嵌套方法另立条目。短说明仍保留，避免删除有效接口。doc_id 使用模块和原始锚点，重复 ID 直接报错。

分块是固定字符窗口，步长为 `chunk_size - overlap`，保持原文 start/end，末块覆盖到文本末尾，不跨文档拼接。正式输入还附加模块和最多 64 字符的签名。字符数与模型 token 数并不等同，配置与报告均明确单位。

## 模型与数据库

模型为 `BAAI/bge-small-zh-v1.5` 的 FastEmbed ONNX 实现，512 维，CPU 4 线程，批量嵌入 32 条。查询加模型卡建议的中文检索前缀，文档不加查询前缀。向量经模型归一化，余弦值由向量点积得到。

数据库使用嵌入式 LanceDB。Schema 包含 vector（float32 固定 512 维）以及 module、version、language、doc_id、title、text、source、start、end 等标量字段。

| 字段 | 索引 | 实际用途 |
|---|---|---|
| vector | IVF_FLAT，cosine，16 个分区 | 向量检索；nprobes=16 |
| module | BITMAP | 模块预过滤 |
| version | BITMAP | 版本预过滤，默认 3.13 |
| language | BITMAP | 语言字段索引，当前数据为 zh-cn |
| doc_id | BTREE | 独立条目标识索引 |
| terms | FTS / BM25 | 英文标识符及中文二元词全文检索 |

批量写入 128 条后建立索引。`results/build_python_support.json` 保存实际 schema 和各索引的 indexed/unindexed 行数。当前小规模数据使用全部 16 个分区探测，不把本次实验包装成大规模 ANN 性能结论。

## 混合检索的计算流程

1. 校验用户问题、阈值及 top_k；版本过滤始终存在，模块过滤由 `--module` 提供。
2. 对问题计算嵌入，两路都先应用相同过滤，再各取候选。
3. 向量路使用余弦检索；关键词路对 `terms` 字段使用 BM25。
4. 按 doc_id 合并候选，余弦取该文档候选块中的最大值，BM25 也取最大值，避免长文档重复占位。
5. BM25 除以本次候选中的最大 BM25；混合分数 = `vector_weight * cosine + (1-vector_weight) * normalized_BM25`。默认向量权重为 {summary["model"].get("vector_weight", 0.3)}，具体以 config.toml 为准。
6. 融合分数只决定排序，结果还必须通过原始余弦阈值 {summary["threshold"]}；最多返回 5 条不同文档。空结果明确返回“未找到”。

不把 BM25、融合分数和余弦阈值混为同一量纲；不为未找到的情况拼接无关答案。系统完成 RAG 的检索与证据供给阶段，未实现可选的生成模型回答。

## 评估口径与真实输出

Recall@5 = 20 道题的 `|Top5文档ID ∩ 标注相关ID| / |标注相关ID|` 的平均值。先按 doc_id 去重，不能用重复的相邻块充当多个命中。每题目前标注一个目标 API，因此该集合上的 Recall@5 等于目标条目的 Top5 命中率；标注尚不是穷尽相关文档的人工金标准。

延迟从 search 入口到输出结果计时，包含查询嵌入、元数据预过滤、召回、融合、阈值及结果组装。模型加载和建库耗时不计入稳态 P95，首条查询耗时另列。每次计时重新向量化问题，无查询结果缓存。请求顺序由固定随机种子打乱，P95 使用 NumPy 线性插值百分位。

| 分块 字符 | 方法 | 块数 | Recall@5 | P50 ms | P95 ms |
|---|---|---|---|---|---|
{rows}

这些是小规模、串行 CPU 热态测量，不能外推为并发服务 SLA。测试题及分块结果在开发过程中可见，报告属于课程内迭代评估，不宣称独立盲测泛化能力；正式阈值和权重的网格选择读取开发集。

## 实际运行问题记录

- 下载官方网页时出现读取超时，进程明确报错；随后重试并保存完整 HTML 快照。
- 最初按 30 字过滤说明，导致 os.getcwd 等有效短说明缺失；改为只剔除空说明，并核对所有题目的目标 ID。
- LanceDB 的 IndexStatistics 是 dataclass，直接 JSON 序列化报 TypeError；改为 asdict 后保存实际索引状态。
- 首轮按块进行 RRF 排序仅达到 {percent(old["recall_at_5"])}；文档级去重与得分融合的各轮输出均保留，不能只交最好看的数字。

## 按作业要求由本人完成的部分

请先阅读 `学习与提交核对.md`；`写作思路与参考.md` 提供基于真实数字的写作方法与参考例子。作业明确要求本人理解核心代码、人工审核测试题，并基于实际输出亲自撰写分块理由、策略取舍和踩坑复盘。报告提供客观配置、真实结果与填写位置。此实现包含 AI 辅助代码，提交前应按课程要求说明使用范围。

## 参考与许可

- [Python 官方中文标准库](https://docs.python.org/zh-cn/3.13/library/index.html)，具体来源见 manifest；PSF 许可见 `data/LICENSE-python.txt`。
- [BGE 模型卡](https://huggingface.co/BAAI/bge-small-zh-v1.5)；[FastEmbed 官方模型表](https://qdrant.github.io/fastembed/examples/Supported_Models/)。
- [LanceDB 向量索引](https://docs.lancedb.com/indexing/vector-index)、[标量索引](https://docs.lancedb.com/indexing/scalar-index)、[全文检索](https://docs.lancedb.com/search/full-text-search)。
'''
(ROOT / "README.md").write_text(readme, encoding="utf-8")

work = ROOT / ".work"
work.mkdir(exist_ok=True)
figure = Drawing(540, 240)
plot = LinePlot()
plot.x, plot.y, plot.width, plot.height = 52, 42, 450, 165
plot.data = [[(k, row["recall_curve"][str(k)] * 100) for k in range(1, 6)] for row in (vector, official)]
plot.xValueAxis.valueMin, plot.xValueAxis.valueMax, plot.xValueAxis.valueStep = 1, 5, 1
plot.yValueAxis.valueMin, plot.yValueAxis.valueMax, plot.yValueAxis.valueStep = 0, 100, 20
plot.lines[0].strokeColor, plot.lines[1].strokeColor = colors.HexColor("#66788a"), colors.HexColor("#1c5890")
plot.lines[0].strokeWidth, plot.lines[1].strokeWidth = 2, 2
figure.add(plot)
figure.add(String(52, 220, "Document Recall@K (%)", fontName="Helvetica", fontSize=11))
figure.add(String(265, 13, "K", fontName="Helvetica", fontSize=10))
figure.add(String(330, 220, "Vector", fillColor=colors.HexColor("#66788a"), fontSize=10))
figure.add(String(420, 220, "Hybrid", fillColor=colors.HexColor("#1c5890"), fontSize=10))
renderPDF.drawToFile(figure, str(work / "curve.pdf"))
poppler = os.environ.get("POPPLER_PATH")
image = convert_from_path(work / "curve.pdf", dpi=150, poppler_path=poppler)[0]
image.save(ROOT / "results/recall_curve.png")

doc = Document()
for border in doc.styles.element.xpath(".//w:pBdr"):
    border.getparent().remove(border)
section = doc.sections[0]
section.page_height, section.page_width = Cm(29.7), Cm(21)
section.top_margin, section.bottom_margin = Cm(1.8), Cm(1.8)
section.left_margin, section.right_margin = Cm(2), Cm(2)
for style_name, size in [("Normal", 10.5), ("Title", 21), ("Heading 1", 14), ("Heading 2", 11.5)]:
    style = doc.styles[style_name]
    style.font.name = "Microsoft YaHei"
    style.element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "微软雅黑")
    style.font.size = Pt(size)
    style.font.color.rgb = RGBColor(0, 0, 0)
    style.paragraph_format.space_after = Pt(6)
    style.paragraph_format.line_spacing = 1.15
doc.styles["Title"].paragraph_format.space_after = Pt(12)
footer = section.footer.paragraphs[0]
footer.alignment = 2
field = OxmlElement("w:fldSimple")
field.set(qn("w:instr"), "PAGE")
footer._p.append(field)


def p(text, style=None):
    return doc.add_paragraph(text, style)


def table(headers, records, widths, font=9.5):
    tbl = doc.add_table(rows=1, cols=len(headers))
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False
    for cell, value, width in zip(tbl.rows[0].cells, headers, widths):
        cell.text = str(value)
        cell.width = Cm(width)
    for record in records:
        for cell, value, width in zip(tbl.add_row().cells, record, widths):
            cell.text = str(value)
            cell.width = Cm(width)
    for i, row in enumerate(tbl.rows):
        trpr = row._tr.get_or_add_trPr()
        if i == 0:
            repeat = OxmlElement("w:tblHeader")
            trpr.append(repeat)
        no_split = OxmlElement("w:cantSplit")
        trpr.append(no_split)
        for cell in row.cells:
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            props = cell._tc.get_or_add_tcPr()
            shade = OxmlElement("w:shd")
            shade.set(qn("w:fill"), "DDE7F0" if i == 0 else ("F4F6F8" if i % 2 == 0 else "FFFFFF"))
            props.append(shade)
            borders = OxmlElement("w:tcBorders")
            for edge in ("top", "left", "bottom", "right"):
                item = OxmlElement("w:" + edge)
                item.set(qn("w:val"), "single")
                item.set(qn("w:sz"), "4")
                item.set(qn("w:color"), "D9D9D9")
                borders.append(item)
            props.append(borders)
            margins = OxmlElement("w:tcMar")
            for edge in ("top", "left", "bottom", "right"):
                item = OxmlElement("w:" + edge)
                item.set(qn("w:w"), "75")
                item.set(qn("w:type"), "dxa")
                margins.append(item)
            props.append(margins)
            for paragraph in cell.paragraphs:
                paragraph.paragraph_format.space_after = Pt(0)
                paragraph.paragraph_format.line_spacing = 1.05
                for run in paragraph.runs:
                    run.font.size = Pt(font)
                    run.bold = i == 0
    p("").paragraph_format.space_after = Pt(0)
    return tbl


p("Python 官方文档智能客服检索系统作业报告", "Title")
p(f'评估日期 {summary["created_at"][:10]}    运行环境 Python {summary["environment"]["python"]}    CPU 本地检索')
p(f'系统以 {summary["documents"]} 条独立 API 文档建立客服检索库，完成清洗、向量化、建库、双路召回及评估。固定 20 题的正式 Recall@5 为 {percent(official["recall_at_5"])}，P95 为 {official["p95_ms"]:.2f} ms。所有数字取自随附的真实运行输出。')
p("一 项目背景与研究范围", "Heading 1")
p("面向 Python 学习平台的技术咨询，知识库提供标准库 API 使用说明及官方出处。系统返回检索证据，支持指定模块及版本，供客服或后续生成模型使用。本项目完成必做的检索与评估链路。")
p(f'数据由 20 个官方中文文档页面提取而来，共 {summary["documents"]} 条独立 API 说明；块数为 {official["chunks"]}。数据条目与分块分别计数，来源链接精确到 API 锚点。原始 HTML、许可与 SHA256 清单保留在 data 目录。')
p("二 系统整体架构", "Heading 1")
p("离线链路：官方 HTML → API 提取与清洗 → 字符窗口分块 → BGE 中文嵌入 → LanceDB 批量写入 → 向量 标量 全文索引。")
p("在线链路：问题及过滤参数 → 查询嵌入 → 过滤后的向量召回与 BM25 召回 → 文档级合并与得分融合 → 余弦阈值 → 证据与来源或未找到。")
table(["文件", "职责"], [("kb/prepare.py", "提取独立 API 文档并保存来源清单"), ("kb/core.py", "分块、嵌入、建库与检索"), ("kb/evaluate.py", "开发集阈值校准、逐题指标与延迟"), ("config.toml", "所有主要实验与检索参数"), ("results/summary.json", "最终实测数字及运行环境")], [5.5, 11.5])
p("复现入口", "Heading 2")
p("在项目目录安装 requirements-lock.txt 后运行 main.py prepare、main.py build 和 main.py evaluate。当前机器已保留模型缓存和本地数据库。详细命令、异常行为和重新下载方法见 README。")

doc.add_page_break()
p("三 核心模块设计与实现", "Heading 1")
p("清洗与分块", "Heading 2")
p(f'清洗合并空白、执行 NFKC 规范化并移除锚点符号；嵌套方法分别提取。仅删除空说明。正式分块大小为 {official["chunk_size"]} 字符，重叠 {official["overlap"]} 字符，保留 start/end；不跨文档拼接，块前附加模块和最多 64 字符的签名。')
p("模型与 Schema", "Heading 2")
p("使用 BGE small zh v1.5 的 FastEmbed ONNX 实现，512 维归一化向量，CPU 4 线程；嵌入批次 32，数据库写入批次 128。向量库使用 LanceDB 嵌入式存储。")
table(["字段", "类型及索引", "作用"], [("vector", "float32[512]  IVF_FLAT", "cosine 检索，16 分区与 16 探测"), ("module version language", "string  BITMAP", "元数据过滤字段"), ("doc_id", "string  BTREE", "来源级标识与去重"), ("terms", "string  FTS BM25", "英文标识符及中文二元词"), ("title text source", "string", "返回证据与官方来源"), ("start end", "int64", "原文块范围")], [4, 6.5, 6.5])
p("过滤与融合", "Heading 2")
p(f'版本过滤默认 3.13，模块过滤可指定；两路均在召回前过滤。各取候选后按文档合并，BM25 以本次候选最大值归一化。混合分数为 0.3 × 余弦 + 0.7 × 归一化 BM25，最终结果还须通过 {summary["threshold"]} 的原始余弦阈值。融合分数仅用于排序。无合格结果时 status 为“未找到”，results 为空。')
p("本人策略取舍填写", "Heading 2")
p("分块大小与重叠的选择理由：________________________________________________")
p("请结合下页的块数、召回与延迟，说明上下文完整性、重复数据和资源占用之间的取舍。模型、数据库及全分区探测的选择理由：________________________________________")

doc.add_page_break()
p("四 实验与性能评估", "Heading 1")
p("评估方法", "Heading 2")
p("开发集包含 8 个正例和 8 个负例，用于融合权重、候选数量和阈值校准。正式测试包含固定 20 题，每题一个预标注目标 API；按 doc_id 去重后计算宏平均 Recall@5，因此本集合的 Recall@5 等于目标条目的 Top5 命中率。额外 6 个负例单独计算拒答率，不并入召回率分母。")
p(f'每题重复 {summary["repeats"]} 次，按固定随机种子打乱，共 {official["request_count"]} 次串行稳态计时。每次重新计算问题嵌入，计时含过滤、召回、融合与结果组装。模型加载、建库不计入稳态延迟；P95 为 NumPy 线性插值百分位。')
table(["分块 字符", "方法", "块数", "Recall@5", "P95 ms"], [(f'{r["chunk_size"]}/{r["overlap"]}', r["mode"], r["chunks"], percent(r["recall_at_5"]), f'{r["p95_ms"]:.2f}') for r in summary["experiments"]], [3, 2.5, 2.3, 3.5, 3.7])
doc.add_picture(str(ROOT / "results/recall_curve.png"), width=Cm(15.2))
p("图一 正式分块下纯向量与混合检索的 Recall 曲线")
p(f'首轮配置的 Recall@5 为 {percent(old["recall_at_5"])}，P95 为 {old["p95_ms"]:.2f} ms；最终正式配置为 {percent(official["recall_at_5"])} 与 {official["p95_ms"]:.2f} ms。首轮、文档级 RRF 和最终得分融合均留档。变化涉及融合方式与参数，不能把差异全部归因于单一变量。')
p("分块比较同时改变大小及重叠，属于三组策略对比。测试题在迭代过程中可见，本实验不宣称独立盲测或并发服务性能。本人对结果的解释与取舍：________________________________________________")

doc.add_page_break()
p("固定测试题及逐题结果", "Heading 1")
p("完整题目、相关 ID、返回证据及每次延迟见 data/test_questions.jsonl 与 results 中对应明细。下表是正式混合检索的 20 题摘要。相关条目仍需本人对照官方说明人工审核。")
short_questions = ["对象转 JSON 字符串", "CSV 行按表头映射成字典", "Path 读取整个文本文件", "正则返回所有不重叠匹配", "按格式解析日期字符串", "统计元素出现次数", "连续同键元素分组", "缓存最近的函数调用结果", "读取环境变量并设默认值", "递归复制整个目录树", "打开 SQLite 或内存数据库", "解压 ZIP 的所有成员", "声明命令行参数及类型", "配置根日志记录器", "执行命令并等待完成", "计算算术平均值", "按容差比较浮点数", "不放回抽样且保留原序列", "按算法名称创建哈希对象", "Decimal 固定小数指数"]
table(["题号", "问题摘要", "目标 API", "命中"], [(q["id"], short_questions[i], q["relevant_doc_ids"][0].split(":", 1)[1], "是" if q["recall_at_5"] == 1 else "否") for i, q in enumerate(detail["questions"])], [1.3, 6.1, 8.1, 1.5], font=9)
p(f'正式结果：{int(round(official["recall_at_5"] * 20))}/20 题命中。额外负例拒答率为 {percent(summary["no_answer_rejection_after"])}。未命中题的返回原文已保留，便于定位召回、排序及标注问题。')

doc.add_page_break()
p("五 难点与运行记录", "Heading 1")
p("以下为可从运行日志和代码变更核验的事件记录。个人复盘应由本人基于代码理解补充。")
table(["实际问题", "处理及证据"], [("下载官方网页读取超时", "明确报错后重试，HTML 与 SHA256 已保存"), ("短说明被清洗长度规则误删", "只剔除空说明，全部标注目标 ID 校验通过"), ("索引统计对象不能直接 JSON 序列化", "使用 dataclasses.asdict；实际索引状态保存为 JSON"), ("按块融合挤占候选及弱匹配排序", f'首轮 {percent(old["recall_at_5"])}，中间结果及最终得分融合均有留档'), ("沙箱套接字限制阻塞异步循环", "在获准本地环境实跑；不改库代码掩盖环境错误")], [6, 11])
p("本人踩坑复盘", "Heading 2")
p("我能解释的失败原因及修复依据：________________________________________________")
p("复现某个未命中问题后，我观察到的现象及改进方向：________________________________")
p("六 未来优化与总结", "Heading 1")
p("本次输出覆盖离线数据处理到检索评估的链路。索引统计、逐请求时延和失败样本均可追溯。当前题目较少，每题仅标注一个目标条目，且请求串行运行；这些条件限制了对完整相关性、泛化能力与并发性能的判断。")
p("本人提出的下一步优化及验证方法：________________________________________________")
p("AI 使用与提交核对", "Heading 2")
p("本实现含 AI 辅助代码及文档整理。作业要求本人理解核心逻辑、人工审核测试题，并独立撰写策略取舍与复盘。本报告的个人填写区应完成后再提交；不可把辅助实现直接当作本人独立完成的证明。")
p("参考资料", "Heading 2")
p("Python 官方文档 https://docs.python.org/zh-cn/3.13/library/index.html\nBGE 模型卡 https://huggingface.co/BAAI/bge-small-zh-v1.5\nLanceDB 索引与检索 https://docs.lancedb.com/\n具体 20 个来源、许可证与校验值见 data/manifest.json 和 LICENSE-python.txt。")
for border in doc.element.xpath(".//w:pBdr"):
    border.getparent().remove(border)
doc.save(ROOT / "作业报告.docx")
print(f'Report and README created; Recall@5={percent(official["recall_at_5"])}; P95={official["p95_ms"]:.2f} ms')
