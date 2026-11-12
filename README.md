# Python 官方文档智能客服检索系统

本项目实现客服知识库的清洗、分块、嵌入、批量写入、索引、过滤、混合检索和真实评估。返回可核验的原文片段与官方来源链接。

## 实测结果

- 数据：20 个 Python 3.13 官方中文文档页面，提取 **1388 条独立 API 文档**；正式方案为 1786 个块。文档数与块数分别统计。
- 正式配置：chunk_size=420 字符，overlap=70 字符，余弦阈值 0.5。
- 固定 20 题：Recall@5 **85.0%**，P95 **19.68 ms**。
- 每题重复 5 次，共 100 个串行稳态计时请求。重复请求用于延迟采样，题目数量仍是 20。
- 6 条额外负例（含不存在的模块、版本）拒答率：100.0%。
- 首轮实测 Recall@5 为 75.0%，完整失败结果保存在 `results/baseline/`，未覆盖或美化。

## 快速运行

需要 Python 3.12。当前机器的 `.venv`、模型缓存和本地库已准备好，可直接运行：

```powershell
cd C:\Prj\AIDBS\期末作业
.\.venv\Scripts\python.exe main.py query "如何递归复制整个目录？" --module shutil
.\.venv\Scripts\python.exe main.py query "我的快递丢失了，赔偿多少钱？"
.\.venv\Scripts\python.exe main.py query "如何读取文本文件？" --module unknown_module
```

后两条预期返回 `"status": "未找到"` 和空的 `results`。正常检索返回最多 5 个不同 doc_id 的证据条目，包含原文、余弦相似度、融合分数、模块、版本和来源。

在新环境安装并重建：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
# 使用仓库内的官方 HTML 快照，离线提取数据
.\.venv\Scripts\python.exe main.py prepare
# 首次执行需要联网下载约 90 MB 的公开模型，之后使用 .cache/models
.\.venv\Scripts\python.exe main.py build
.\.venv\Scripts\python.exe main.py query "如何按容差比较浮点数？" --module math
```

`python` 应指向 Python 3.12。若需更新官方网页，再运行 `main.py prepare --download`；刷新会改变快照及校验值，不能与本次结果混作同一次实验。

## 复现实验

```powershell
.\.venv\Scripts\python.exe tools/tune_retrieval.py
.\.venv\Scripts\python.exe main.py evaluate
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
5. BM25 除以本次候选中的最大 BM25；混合分数 = `vector_weight * cosine + (1-vector_weight) * normalized_BM25`。默认向量权重为 0.3，具体以 config.toml 为准。
6. 融合分数只决定排序，结果还必须通过原始余弦阈值 0.5；最多返回 5 条不同文档。空结果明确返回“未找到”。

不把 BM25、融合分数和余弦阈值混为同一量纲；不为未找到的情况拼接无关答案。系统完成 RAG 的检索与证据供给阶段，未实现可选的生成模型回答。

## 评估口径与真实输出

Recall@5 = 20 道题的 `|Top5文档ID ∩ 标注相关ID| / |标注相关ID|` 的平均值。先按 doc_id 去重，不能用重复的相邻块充当多个命中。每题目前标注一个目标 API，因此该集合上的 Recall@5 等于目标条目的 Top5 命中率；标注尚不是穷尽相关文档的人工金标准。

延迟从 search 入口到输出结果计时，包含查询嵌入、元数据预过滤、召回、融合、阈值及结果组装。模型加载和建库耗时不计入稳态 P95，首条查询耗时另列。每次计时重新向量化问题，无查询结果缓存。请求顺序由固定随机种子打乱，P95 使用 NumPy 线性插值百分位。

| 分块 字符 | 方法 | 块数 | Recall@5 | P50 ms | P95 ms |
|---|---|---|---|---|---|
| 180/30 | vector | 2836 | 70.0% | 12.55 | 14.35 |
| 180/30 | hybrid | 2836 | 85.0% | 17.11 | 21.71 |
| 300/50 | vector | 2084 | 65.0% | 11.24 | 13.14 |
| 300/50 | hybrid | 2084 | 80.0% | 16.72 | 21.96 |
| 420/70 | vector | 1786 | 65.0% | 11.01 | 12.38 |
| 420/70 | hybrid | 1786 | 85.0% | 17.07 | 19.68 |

这些是小规模、串行 CPU 热态测量，不能外推为并发服务 SLA。测试题及分块结果在开发过程中可见，报告属于课程内迭代评估，不宣称独立盲测泛化能力；正式阈值和权重的网格选择读取开发集。

## 实际运行问题记录

- 下载官方网页时出现读取超时，进程明确报错；随后重试并保存完整 HTML 快照。
- 最初按 30 字过滤说明，导致 os.getcwd 等有效短说明缺失；改为只剔除空说明，并核对所有题目的目标 ID。
- LanceDB 的 IndexStatistics 是 dataclass，直接 JSON 序列化报 TypeError；改为 asdict 后保存实际索引状态。
- 首轮按块进行 RRF 排序仅达到 75.0%；文档级去重与得分融合的各轮输出均保留，不能只交最好看的数字。

## 按作业要求由本人完成的部分

请先阅读 `学习与提交核对.md`；`写作思路与参考.md` 提供基于真实数字的写作方法与参考例子。作业明确要求本人理解核心代码、人工审核测试题，并基于实际输出亲自撰写分块理由、策略取舍和踩坑复盘。报告提供客观配置、真实结果与填写位置。此实现包含 AI 辅助代码，提交前应按课程要求说明使用范围。

## 参考与许可

- [Python 官方中文标准库](https://docs.python.org/zh-cn/3.13/library/index.html)，具体来源见 manifest；PSF 许可见 `data/LICENSE-python.txt`。
- [BGE 模型卡](https://huggingface.co/BAAI/bge-small-zh-v1.5)；[FastEmbed 官方模型表](https://qdrant.github.io/fastembed/examples/Supported_Models/)。
- [LanceDB 向量索引](https://docs.lancedb.com/indexing/vector-index)、[标量索引](https://docs.lancedb.com/indexing/scalar-index)、[全文检索](https://docs.lancedb.com/search/full-text-search)。
