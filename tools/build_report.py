"""依据保存的实验结果生成白底黑字黑线的作业报告。"""
import json
import os
from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from pdf2image import convert_from_path
from reportlab.graphics import renderPDF
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ROOT = Path(__file__).resolve().parents[1]
summary = json.loads((ROOT / "results/summary.json").read_text(encoding="utf-8"))
manifest = json.loads((ROOT / "data/manifest.json").read_text(encoding="utf-8"))
calibration = json.loads((ROOT / "results/threshold_calibration.json").read_text(encoding="utf-8"))
baseline = json.loads((ROOT / "results/baseline/summary.json").read_text(encoding="utf-8"))
index_record = json.loads((ROOT / "results/build_python_support.json").read_text(encoding="utf-8"))
official = next(item for item in summary["experiments"] if item["official"])
detail = json.loads((ROOT / f'results/{official["name"]}.json').read_text(encoding="utf-8"))
vector = next(item for item in summary["experiments"] if item["chunk_size"] == official["chunk_size"] and item["mode"] == "vector")
old = next(item for item in baseline["experiments"] if item["official"])
config = summary["config"]
percent = lambda value: f"{value * 100:.1f}%"
work = ROOT / ".work/report_figures"
work.mkdir(parents=True, exist_ok=True)
poppler = os.environ.get("POPPLER_PATH")

# 图表使用全黑线条，以线型和标记区分系列，保留白色背景。
figure = Drawing(540, 215)
plot = LinePlot()
plot.x, plot.y, plot.width, plot.height = 48, 35, 460, 150
plot.data = [[(k, row["recall_curve"][str(k)] * 100) for k in range(1, 6)] for row in (vector, official)]
plot.xValueAxis.valueMin, plot.xValueAxis.valueMax, plot.xValueAxis.valueStep = 1, 5, 1
plot.yValueAxis.valueMin, plot.yValueAxis.valueMax, plot.yValueAxis.valueStep = 0, 100, 20
for axis in (plot.xValueAxis, plot.yValueAxis):
    axis.strokeColor = colors.black
    axis.labels.fillColor = colors.black
    axis.labels.fontName = "Helvetica"
    axis.labels.fontSize = 10
for index in (0, 1):
    plot.lines[index].strokeColor = colors.black
    plot.lines[index].strokeWidth = 1.6
plot.lines[0].strokeDashArray = [5, 3]
figure.add(plot)
for series_index, row in enumerate((vector, official)):
    for k in range(1, 6):
        x = 48 + (k - 1) * 115
        y = 35 + row["recall_curve"][str(k)] * 150
        if series_index == 0:
            figure.add(Rect(x - 2.5, y - 2.5, 5, 5, fillColor=colors.white, strokeColor=colors.black))
        else:
            figure.add(Polygon([x, y + 3, x - 3, y - 3, x + 3, y - 3], fillColor=colors.black, strokeColor=colors.black))
figure.add(String(48, 199, "Document Recall@K (%)", fillColor=colors.black, fontSize=11))
figure.add(String(273, 10, "K", fillColor=colors.black, fontSize=10))
figure.add(Line(304, 202, 330, 202, strokeColor=colors.black, strokeDashArray=[5, 3]))
figure.add(String(337, 198, "Vector", fillColor=colors.black, fontSize=10))
figure.add(Line(408, 202, 434, 202, strokeColor=colors.black))
figure.add(String(441, 198, "Hybrid", fillColor=colors.black, fontSize=10))
renderPDF.drawToFile(figure, str(work / "recall_bw.pdf"))
convert_from_path(work / "recall_bw.pdf", dpi=180, poppler_path=poppler)[0].convert("L").save(work / "recall_bw.png")

# 离线与在线链路的架构图，字体来自 Windows 自带宋体。
pdfmetrics.registerFont(TTFont("ReportSimSun", r"C:\Windows\Fonts\simsun.ttc", subfontIndex=0))
architecture = Drawing(540, 182)
boxes = [(15, 142, 110, "官方 HTML 快照"), (150, 142, 110, "API 清洗与分块"),
         (285, 142, 110, "BGE 向量化"), (420, 142, 110, "LanceDB 索引"),
         (15, 77, 110, "问题与过滤条件"), (150, 77, 110, "查询嵌入"),
         (285, 77, 110, "向量与 BM25 召回"), (420, 77, 110, "文档合并与融合"),
         (420, 12, 110, "余弦阈值过滤"), (150, 12, 245, "返回 Top5 原文与来源 或 未找到")]
for x, y, width, label in boxes:
    architecture.add(Rect(x, y, width, 29, fillColor=colors.white, strokeColor=colors.black, strokeWidth=0.8))
    architecture.add(String(x + width / 2, y + 10, label, fontName="ReportSimSun", fontSize=10, textAnchor="middle", fillColor=colors.black))
for y in (156.5, 91.5):
    for x in (125, 260, 395):
        architecture.add(Line(x, y, x + 25, y, strokeColor=colors.black, strokeWidth=0.8))
        architecture.add(Polygon([x + 25, y, x + 20, y + 2.5, x + 20, y - 2.5], fillColor=colors.black, strokeColor=colors.black))
for x1, y1, x2, y2 in [(475, 142, 475, 124), (475, 124, 340, 124), (340, 124, 340, 106), (475, 77, 475, 41), (420, 26.5, 395, 26.5)]:
    architecture.add(Line(x1, y1, x2, y2, strokeColor=colors.black, strokeWidth=0.8))
architecture.add(Polygon([340, 106, 337.5, 111, 342.5, 111], fillColor=colors.black, strokeColor=colors.black))
architecture.add(Polygon([475, 41, 472.5, 46, 477.5, 46], fillColor=colors.black, strokeColor=colors.black))
architecture.add(Polygon([395, 26.5, 400, 29, 400, 24], fillColor=colors.black, strokeColor=colors.black))
renderPDF.drawToFile(architecture, str(work / "architecture_bw.pdf"))
convert_from_path(work / "architecture_bw.pdf", dpi=180, poppler_path=poppler)[0].convert("L").save(work / "architecture_bw.png")

doc = Document()
doc.core_properties.title = "基于 RAG 架构的智能客服检索系统作业报告"
doc.core_properties.subject = "Python 官方文档客服知识库的设计与评估"
doc.core_properties.author = ""
for style in doc.styles:
    if style.type in (1, 2):
        style.font.color.rgb = RGBColor(0, 0, 0)
for border in doc.styles.element.xpath(".//w:pBdr"):
    border.getparent().remove(border)
for shading in doc.styles.element.xpath(".//w:shd"):
    shading.getparent().remove(shading)
section = doc.sections[0]
section.page_height, section.page_width = Cm(29.7), Cm(21)
section.top_margin, section.bottom_margin = Cm(1.8), Cm(1.8)
section.left_margin, section.right_margin = Cm(2), Cm(2)
for style_name, size, chinese_font in [("Normal", 11.5, "宋体"), ("Title", 20, "黑体"), ("Heading 1", 14, "黑体"), ("Heading 2", 12, "黑体")]:
    style = doc.styles[style_name]
    style.font.name = "Times New Roman"
    style.element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), chinese_font)
    style.font.size = Pt(size)
    style.font.color.rgb = RGBColor(0, 0, 0)
    style.paragraph_format.space_after = Pt(5)
    style.paragraph_format.line_spacing = 1.18
    if style_name in ("Title", "Heading 1", "Heading 2"):
        style.font.bold = True
        style.paragraph_format.space_before = Pt(7)
doc.styles["Title"].paragraph_format.space_after = Pt(9)
doc.styles["Title"].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
footer = section.footer.paragraphs[0]
footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
field = OxmlElement("w:fldSimple")
field.set(qn("w:instr"), "PAGE")
footer._p.append(field)


def p(text, style=None):
    return doc.add_paragraph(text, style)


def table(headers, records, widths, font=10.5, centered=()):
    tbl = doc.add_table(rows=1, cols=len(headers))
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False
    for column, width in zip(tbl.columns, widths):
        column.width = Cm(width)
    for values in [headers] + list(records):
        row = tbl.rows[0] if values is headers else tbl.add_row()
        for cell, value, width in zip(row.cells, values, widths):
            cell.width = Cm(width)
            cell.text = str(value)
    for index, row in enumerate(tbl.rows):
        trpr = row._tr.get_or_add_trPr()
        no_split = OxmlElement("w:cantSplit")
        trpr.append(no_split)
        if index == 0:
            trpr.append(OxmlElement("w:tblHeader"))
        for column_index, cell in enumerate(row.cells):
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            props = cell._tc.get_or_add_tcPr()
            shade = OxmlElement("w:shd")
            shade.set(qn("w:val"), "clear")
            shade.set(qn("w:fill"), "FFFFFF")
            props.append(shade)
            borders = OxmlElement("w:tcBorders")
            for edge in ("top", "left", "bottom", "right"):
                item = OxmlElement("w:" + edge)
                item.set(qn("w:val"), "single")
                item.set(qn("w:sz"), "5")
                item.set(qn("w:color"), "000000")
                borders.append(item)
            props.append(borders)
            margins = OxmlElement("w:tcMar")
            for edge in ("top", "left", "bottom", "right"):
                item = OxmlElement("w:" + edge)
                item.set(qn("w:w"), "65")
                item.set(qn("w:type"), "dxa")
                margins.append(item)
            props.append(margins)
            for paragraph in cell.paragraphs:
                paragraph.paragraph_format.space_after = Pt(0)
                paragraph.paragraph_format.line_spacing = 1.05
                if column_index in centered:
                    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for run in paragraph.runs:
                    run.font.size = Pt(font)
                    run.font.color.rgb = RGBColor(0, 0, 0)
                    run.bold = index == 0
    space = p("")
    space.paragraph_format.space_after = Pt(0)
    space.paragraph_format.line_spacing = 0.4
    return tbl


p("基于 RAG 架构的智能客服检索系统作业报告", "Title")
metadata = p(f'数据领域 Python 官方中文标准库    实验日期 {summary["created_at"][:10]}')
metadata.alignment = WD_ALIGN_PARAGRAPH.CENTER
p(f'本项目构建了包含 {summary["documents"]:,} 条独立 API 文档的技术客服知识库，完成清洗、分块、嵌入、批量入库、索引和混合检索。正式方案以 {official["chunk_size"]} 字符分块、{official["overlap"]} 字符重叠生成 {official["chunks"]:,} 个文本块，在固定 20 题中命中 17 题，Recall@5 为 {percent(official["recall_at_5"])}，串行稳态 P95 为 {official["p95_ms"]:.2f} ms。系统返回原文证据及官方出处，供客服处理或后续生成模型使用。')

p("1 项目背景与研究意义", "Heading 1")
p("Python 学习平台的技术咨询通常以自然语言提出，而官方文档以模块、接口和参数组织。仅依赖关键词容易遗漏同义表达；只按向量相似度排序，又可能混淆用途接近的接口。版本或模块不同也会改变答案范围，因此检索需要同时考虑语义、关键词和元数据条件。")
p("本项目将官方文档转为可追溯的知识条目，通过向量与 BM25 双路召回寻找候选，再用元数据过滤、文档去重和余弦阈值控制结果范围。研究重点是让检索过程可复现、来源可核验，并在知识库无覆盖时明确返回“未找到”。当前完成 RAG 的检索阶段，可选的大模型答案生成尚未接入。")

p("2 系统整体架构", "Heading 1")
doc.add_picture(str(work / "architecture_bw.png"), width=Cm(17))
caption = p("图 1 离线建库与在线检索流程")
caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
table(["模块", "实现位置", "职责"], [("数据准备", "kb/prepare.py", "提取 API 说明、清洗并保存来源清单"), ("建库与检索", "kb/core.py", "分块、嵌入、索引及过滤后的混合召回"), ("实验评估", "kb/evaluate.py", "开发集阈值校准与正式题计时评估"), ("运行入口", "main.py / config.toml", "命令行操作与参数外置")], [3, 5, 9], font=10)
p("离线处理保留原始 HTML、清洗文档、SHA256 和索引状态；在线检索使用已加载的嵌入模型及本地向量库。查询输出含 status、results、filters、threshold、mode 和 latency_ms，便于检查过滤条件、证据与耗时。")

p("3 核心模块设计与实现", "Heading 1").paragraph_format.page_break_before = True
p("3 1 数据来源与清洗", "Heading 2")
p(f'数据来自 Python 3.13 官方中文标准库的 {manifest["source_page_count"]} 个页面，覆盖 json、csv、pathlib、re、datetime、os、sqlite3 等模块。每个具有独立锚点和非空说明的 API 定义计为一条原始文档，共 {summary["documents"]:,} 条；网页数、文档条目数和文本块数分别统计。')
p("清洗执行 NFKC 规范化、空白合并及锚点符号清理，保留 API 签名和说明。类说明中的嵌套方法分别提取，避免整类重复包含所有子方法；有效短说明仍保留。doc_id 由模块与原始锚点组成，每条文档保留模块、版本、语言和精确到 API 的来源链接。原始快照及校验值写入 data/manifest.json。")
p("3 2 分块策略与参数依据", "Heading 2")
p(f'分块采用固定字符窗口，chunk_size={official["chunk_size"]}、overlap={official["overlap"]}，步长为 350 字符，重叠比例约 16.7%。窗口不跨文档拼接，保留 start/end，末块覆盖到原文末尾。嵌入输入还附加模块名与最多 64 字符的签名；字符数和模型 token 数分别看待。')
p("重叠使边界附近说明可在相邻块中再次出现，代价是重复存储和嵌入。在相同最终检索方式下，420/70 与 180/30 均达到 85% Recall@5，块数分别为 1,786 与 2,836；300/50 为 2,084 块、80% Recall@5。当前默认配置以较少的块数达到本次测试目标。实验同时改变块长和重叠，尚不能证明 70 字符是独立最优的重叠量。")
p("3 3 嵌入模型与存储选型", "Heading 2")
p("嵌入采用 BAAI/bge-small-zh-v1.5 的 FastEmbed ONNX 实现，输出 512 维归一化向量，CPU 4 线程运行，嵌入批次为 32。该方案满足中文检索、本地推理和无需付费 API 的条件。本实验没有比较其他嵌入模型，因此不作模型性能最优的判断。查询附加中文检索前缀，文档不加查询前缀。")
p("向量库采用嵌入式 LanceDB，将向量、元数据和全文索引置于同一张表，无需另启数据库服务。每批写入 128 条，随后建立向量、标量与全文索引。")
table(["字段", "数据类型或索引", "用途"], [("vector", "float32[512] / IVF_FLAT", "按 cosine 进行向量召回"), ("module / version", "string / BITMAP", "模块与版本预过滤"), ("language", "string / BITMAP", "保存并索引语言信息"), ("doc_id", "string / BTREE", "文档标识字段"), ("terms", "string / FTS", "BM25 关键词检索"), ("title / text / source", "string", "签名、证据文本与来源"), ("chunk_id / start / end", "string / int64 / int64", "文本块标识和原文范围")], [4.4, 6.3, 6.3], font=10)
p(f'正式表的 6 个索引均覆盖 {official["chunks"]:,} 行，未索引行数均为 0，实际状态保存在 results/build_python_support.json。向量索引有 16 个分区，查询 nprobes=16，会探测全部分区；本次小规模实验不用于证明大规模 ANN 加速效果。')

p("3 4 过滤与混合检索", "Heading 2").paragraph_format.page_break_before = True
p("问题先进行非空和长度校验，再计算查询嵌入。版本条件始终存在，默认值为 3.13；模块条件可由用户指定。两路均先应用相同条件再召回，每路最多取 30 个候选块。用户输入中的单引号转义后进入过滤表达式，避免改变条件语义。")
p("向量路使用余弦距离检索，关键词路使用英文标识符与连续汉字二元词构成的 terms 字段进行 BM25 召回。候选按 doc_id 合并，同一文档取候选块的最大余弦值与最大 BM25 值，返回余弦较高的证据块，避免同一长文档占据多个最终名额。")
p("BM25 以本次候选的最大值归一化，融合公式为：")
p("归一化 BM25 = 文档最大 BM25 ÷ 本次候选最大 BM25")
p("混合分数 = 0.3 × 余弦相似度 + 0.7 × 归一化 BM25")
p("关键词路无匹配时，其贡献为 0。融合分数决定排序，最终结果还必须通过原始余弦阈值 0.5，最多返回 5 条不同文档。没有合格结果时，status 为“未找到”，results 为空。原始余弦值、BM25 和融合分数具有不同含义，阈值不作用于融合分数。")
p("3 5 阈值设定依据", "Heading 2")
p("开发集包含 8 道正例和 8 道负例。阈值选择最大化“正例 Recall@5 与负例拒答率的平均值”，平局时优先正例召回，再选择较低阈值。正式配置的校准结果如下。")
table(["余弦阈值", "正例 Recall@5", "负例拒答率", "平均分"], [(f'{r["threshold"]:.2f}', percent(r["dev_recall_at_5"]), percent(r["dev_rejection_rate"]), f'{r["balanced_score"]:.4f}') for r in calibration["rows"]], [3.2, 4.6, 4.6, 4.6], centered=(0, 1, 2, 3))
p("阈值 0.50 在开发集上保持 87.5% 的正例召回，并拒绝全部负例；降为 0.45 没有增加正例召回，拒答率却降为 87.5%；升为 0.55 后正例召回降为 62.5%。因此当前阈值采用 0.50。该结论仅由小规模开发集支持，完整候选及校准输出保存在 results/threshold_calibration.json。")
p("3 6 工程实现与运行入口", "Heading 2")
p("主要参数置于 config.toml，包含模型、线程、分块、批次、索引分区、候选数、阈值与评估次数。命令行提供 prepare、build、query、evaluate 四类操作。prepare 从快照提取文档，build 重建指定表，query 检索，evaluate 重建对照表并更新结果。")
p("输入错误和运行错误明确抛出，不用无关结果替代失败。数据准备检查重复 ID 和文档条数，评估前检查题目指向的条目是否存在。空问题会报错，不存在的模块或版本形成过滤空集并返回“未找到”。本地模型缓存和数据库由运行生成，不作为源码上传。")

p("4 实验与性能评估", "Heading 1").paragraph_format.page_break_before = True
p("4 1 实验环境与指标口径", "Heading 2")
p(f'实验于 {summary["created_at"][:10]} 在 Windows 11、Python {summary["environment"]["python"]}、Intel CPU 和 ONNX Runtime {summary["environment"]["packages"]["onnxruntime"]} 上完成。固定 20 题每题标注一个目标 API，按文档去重后计算单题 Recall@5，再等权平均；在本集合上即为目标 API 的 Top5 命中率。开发题及额外 6 条负例单独统计。')
p(f'每题重复 {summary["repeats"]} 次并按固定种子打乱，共 {official["request_count"]} 次串行稳态请求。计时含每次查询嵌入、过滤、召回、融合及结果组装，不含模型加载、建库或终端打印；P95 使用 NumPy 线性插值百分位。')
p("4 2 分块与双路召回对比", "Heading 2")
table(["分块 / 重叠", "检索方式", "块数", "Recall@5", "P95 ms"], [(f'{r["chunk_size"]} / {r["overlap"]}', "纯向量" if r["mode"] == "vector" else "混合", f'{r["chunks"]:,}', percent(r["recall_at_5"]), f'{r["p95_ms"]:.2f}') for r in summary["experiments"]], [3.4, 3.2, 3, 3.6, 3.8], centered=(0, 1, 2, 3, 4))
doc.add_picture(str(work / "recall_bw.png"), width=Cm(14))
doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
caption = p("图 2 正式分块下纯向量与混合检索的 Recall 曲线")
caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
p(f'同为 420/70 时，混合检索 Recall@5 为 {percent(official["recall_at_5"])}，比纯向量高 20 个百分点；P95 从 {vector["p95_ms"]:.2f} ms 增至 {official["p95_ms"]:.2f} ms，增加约 7.30 ms。额外关键词召回改善了本集合的 Top5 命中，同时带来处理开销。')
p("4 3 首轮与最终实现对比", "Heading 2")
table(["实现", "分块 / 重叠", "Recall@5", "P95 ms"], [("首轮按块 RRF 融合", "300 / 50", percent(old["recall_at_5"]), f'{old["p95_ms"]:.2f}'), ("最终文档级得分融合", "420 / 70", percent(official["recall_at_5"]), f'{official["p95_ms"]:.2f}')], [7.2, 3.4, 3.3, 3.1], centered=(1, 2, 3))
p("首轮到最终召回增加 10 个百分点，P95 增加约 0.37 ms。变化涉及分块与融合方式，不能归因于单一参数；两轮余弦阈值均为 0.5，也不把提升描述为阈值调整收益。首轮和中间结果均留档。")

p("4 4 固定测试题与逐题结果", "Heading 2").paragraph_format.page_break_before = True
p("下表为正式混合检索的 20 题摘要。完整问题、相关 ID、返回证据与逐请求耗时见 data/test_questions.jsonl 和 results/chunk_420_70_hybrid.json。")
short_questions = ["对象转 JSON 字符串", "CSV 行按表头映射成字典", "Path 读取整个文本文件", "正则返回所有不重叠匹配", "按格式解析日期字符串", "统计元素出现次数", "连续同键元素分组", "缓存最近的函数调用结果", "读取环境变量并设默认值", "递归复制整个目录树", "打开 SQLite 或内存数据库", "解压 ZIP 的所有成员", "声明命令行参数及类型", "配置根日志记录器", "执行命令并等待完成", "计算算术平均值", "按容差比较浮点数", "不放回抽样且保留原序列", "按算法名称创建哈希对象", "Decimal 固定小数指数"]
table(["题号", "问题摘要", "目标 API", "命中"], [(q["id"], short_questions[i], q["relevant_doc_ids"][0].split(":", 1)[1], "是" if q["recall_at_5"] == 1 else "否") for i, q in enumerate(detail["questions"])], [1.2, 6, 8.4, 1.4], font=10, centered=(0, 3))
p(f'共 17/20 题命中，Recall@5 为 {percent(official["recall_at_5"])}。额外 6 条负例全部返回“未找到”，包括 4 条域外问题、1 条不存在的模块及 1 条不存在的版本。边界记录还验证了空问题报错、过滤条件与余弦阈值。')
p("4 5 未命中样本与实验限制", "Heading 2")
p("T05 的目标是 datetime.strptime，返回结果包含 strftime 和 isoformat 等接口，反映日期解析与格式化意图的区分仍不足。T12 的目标是 ZipFile.extractall，结果主要涉及压缩类型与 ZipFile 类，说明归档文档内的细粒度操作定位仍有困难。T15 的目标是 subprocess.run，返回 Popen 及等待、通信方法，说明用途接近的接口仍可能互相挤占排名。")
p("以上判断是对返回结果的分析，尚未通过独立消融实验确认各因素贡献。测试题在迭代过程中可见，20 题的样本规模有限；串行稳态时延也不能外推为并发服务 SLA。结果与失败样本一并保留，便于后续人工审核标注和改进排序。")

p("5 难点与踩坑复盘", "Heading 1").paragraph_format.page_break_before = True
p("5 1 数据长度规则误删有效接口", "Heading 2")
p("评估前的目标 ID 检查曾提示 os:os.getcwd 缺失。初版清洗把不足 30 字符的说明删除，而这个接口的说明虽短仍然有效。修复将条件改为仅跳过空说明，并从已保存 HTML 重新提取；最终得到 1,388 条，全部开发题和正式题的目标 ID 均存在。该问题表明，技术文档有效性应结合 API 结构判断，单独以长度过滤会损失有效知识。")
p("5 2 索引状态对象序列化失败", "Heading 2")
p("第一次保存索引统计时出现 TypeError，原因是 LanceDB 返回 IndexStatistics dataclass，不能直接交给 JSON 编码器。修复使用 dataclasses.asdict 转为字典，再保存实际索引状态。最终六个索引覆盖全部 1,786 行，未索引行数均为 0；对应错误日志和最终记录可以互相核对。")
p("5 3 融合结果与运行环境问题", "Heading 2")
p("首轮按块进行 RRF 融合的正式 Recall@5 为 75%，未达目标。同一长文档的多个块会占据候选，按名次融合也会丢失关键词得分强弱差异。后续按文档合并并保留 BM25 得分差异，结合分块对比形成最终方案。因为多处因素同时变化，当前只能说明整体配置在该集合上改善，不能认定其中某一项独立贡献了全部收益。")
p("数据下载阶段曾出现读取超时，重试后保存完整 HTML 与校验值；复现时优先使用这些快照。受限沙箱还曾阻塞 LanceDB 创建本地异步循环，获准的本地执行环境可正常运行。对这类错误应检查网络和权限条件，保留明确报错，避免用静默默认值掩盖未完成的步骤。")
p("6 未来优化与总结", "Heading 1")
p("下一步首先扩大人工审核的问题集，为同一问题标注全部可接受的相关文档，并保留未参与调参的新题。分块实验应固定块长单独改变重叠，或固定重叠单独改变块长，使对参数作用的判断更明确。")
p("针对日期解析、归档解压和进程接口等未命中问题，可比较更细的段落边界、重排模型或查询表述处理，记录召回与 P95 的共同变化。实际部署前还需独立测量模型加载、并发请求和网络开销；接入生成模型时应要求答案引用检索证据，并保持无证据时的拒答行为。")
p(f'本项目已经跑通从数据准备到检索评估的完整链路，保留来源、索引状态、逐题证据及失败记录。在当前 20 题课程评估中，正式方案达到 Recall@5 {percent(official["recall_at_5"])}、P95 {official["p95_ms"]:.2f} ms；结论限定于本次数据、配置和运行环境。')
p("AI 辅助说明：实现、调试与文档整理使用 AI 辅助，实验指标取自真实运行输出。提交者仍需理解核心代码、审核测试标注，并依据课程要求确认策略结论与复盘内容。")
p("参考资料", "Heading 2")
for reference in ["[1] Python 官方中文标准库 https://docs.python.org/zh-cn/3.13/library/index.html", "[2] BGE small zh v1.5 模型卡 https://huggingface.co/BAAI/bge-small-zh-v1.5", "[3] LanceDB 索引与检索文档 https://docs.lancedb.com/", "[4] 项目仓库 https://github.com/cnwky26-glitch/python-rag-customer-service"]:
    paragraph = p(reference)
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.line_spacing = 1.0
    for run in paragraph.runs:
        run.font.size = Pt(9.5)

for border in doc.element.xpath(".//w:pBdr"):
    border.getparent().remove(border)
for color in doc.styles.element.xpath(".//w:color") + doc.element.xpath(".//w:color"):
    for attribute in list(color.attrib):
        del color.attrib[attribute]
    color.set(qn("w:val"), "000000")
doc.save(ROOT / "作业报告.docx")
print(f'Report created; Recall@5={percent(official["recall_at_5"])}; P95={official["p95_ms"]:.2f} ms')
