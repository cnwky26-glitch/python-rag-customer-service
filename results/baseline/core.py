"""分块、嵌入、批量建库及带过滤和余弦阈值的双路召回。"""
import json
import re
import time
import tomllib
from dataclasses import asdict
from pathlib import Path

import lancedb
import numpy as np
import pyarrow as pa
from fastembed import TextEmbedding
from lancedb.index import FTS

ROOT = Path(__file__).resolve().parents[1]


def load_config(path=None):
    config = tomllib.loads(Path(path or ROOT / "config.toml").read_text(encoding="utf-8"))
    size, overlap = config["chunking"]["chunk_size"], config["chunking"]["overlap"]
    if not 0 <= overlap < size:
        raise ValueError("分块参数必须满足 0 <= overlap < chunk_size")
    if not 0 <= config["retrieval"]["similarity_threshold"] <= 1:
        raise ValueError("相似度阈值必须在 [0, 1] 范围内")
    return config


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def lexical_text(text):
    # 中英混排：英文标识符 + 连续汉字二元词；不依赖在线分词服务。
    terms = []
    for word in re.findall(r"[a-zA-Z_][a-zA-Z_0-9]*|[\u4e00-\u9fff]+", text.lower()):
        if "\u4e00" <= word[0] <= "\u9fff":
            terms.extend(word[i:i + 2] for i in range(len(word) - 1))
        else:
            terms.append(word)
    return " ".join(terms)


def chunk_documents(documents, config):
    size = config["chunking"]["chunk_size"]
    overlap = config["chunking"]["overlap"]
    chunks = []
    for doc in documents:
        for start in range(0, len(doc["text"]), size - overlap):
            text = doc["text"][start:start + size]
            chunks.append({**doc, "chunk_id": f'{doc["doc_id"]}@{start}',
                           "text": text, "start": start, "end": start + len(text),
                           "terms": lexical_text(doc["title"] + " " + text)})
            if start + size >= len(doc["text"]):
                break
    return chunks


def load_model(config):
    # FastEmbed 的本地缓存命中后不需要网络。
    return TextEmbedding(config["embedding"]["model"], cache_dir=str(ROOT / ".cache/models"),
                         threads=config["embedding"]["threads"])


def build(config, model):
    started = time.perf_counter()
    documents = read_jsonl(ROOT / "data/documents.jsonl")
    chunks = chunk_documents(documents, config)
    db_config = config["database"]
    db = lancedb.connect(str(ROOT / db_config["path"]))
    schema = pa.schema([
        pa.field("chunk_id", pa.string()), pa.field("doc_id", pa.string()),
        pa.field("title", pa.string()), pa.field("text", pa.string()),
        pa.field("module", pa.string()), pa.field("version", pa.string()),
        pa.field("language", pa.string()), pa.field("source", pa.string()),
        pa.field("start", pa.int64()), pa.field("end", pa.int64()),
        pa.field("terms", pa.string()),
        pa.field("vector", pa.list_(pa.float32(), config["embedding"]["dimension"])),
    ])
    table = db.create_table(db_config["table"], schema=schema, mode="overwrite")
    batch_size = db_config["batch_size"]
    for offset in range(0, len(chunks), batch_size):
        batch = chunks[offset:offset + batch_size]
        texts = [f'{c["module"]} {c["title"][:config["chunking"]["title_limit"]]}\n{c["text"]}' for c in batch]
        vectors = model.embed(texts, batch_size=config["embedding"]["batch_size"])
        table.add([{**chunk, "vector": vector.tolist()} for chunk, vector in zip(batch, vectors, strict=True)])
        print(f"embedded {min(offset + batch_size, len(chunks))}/{len(chunks)}", flush=True)
    table.create_index(metric="cosine", index_type="IVF_FLAT", num_partitions=db_config["num_partitions"])
    for field in ("module", "version", "language"):
        table.create_scalar_index(field, index_type="BITMAP")
    table.create_scalar_index("doc_id", index_type="BTREE")
    table.create_index("terms", config=FTS(base_tokenizer="whitespace", stem=False, remove_stop_words=False))
    summary = {
        "documents": len(documents), "chunks": len(chunks),
        "chunk_size": config["chunking"]["chunk_size"], "overlap": config["chunking"]["overlap"],
        "build_seconds": time.perf_counter() - started, "schema": str(schema),
        "indexes": [{"name": i.name, "type": i.index_type, "columns": i.columns,
                     "stats": asdict(table.index_stats(i.name))} for i in table.list_indices()],
    }
    output = ROOT / "results"
    output.mkdir(exist_ok=True)
    (output / f'build_{db_config["table"]}.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


class Retriever:
    def __init__(self, config, model):
        self.config = config
        self.model = model
        self.db = lancedb.connect(str(ROOT / config["database"]["path"]))
        self.table = self.db.open_table(config["database"]["table"])

    def search(self, question, module=None, version=None, mode="hybrid", threshold=None, top_k=None):
        started = time.perf_counter()
        if not question.strip() or len(question) > 500:
            raise ValueError("问题不能为空，且长度不能超过 500 字符")
        if mode not in ("vector", "hybrid"):
            raise ValueError("mode 必须是 vector 或 hybrid")
        cfg = self.config
        settings = cfg["retrieval"]
        threshold = settings["similarity_threshold"] if threshold is None else threshold
        top_k = settings["top_k"] if top_k is None else top_k
        if not 0 <= threshold <= 1 or not 1 <= top_k <= settings["candidate_k"]:
            raise ValueError("阈值或 top_k 超出范围")
        # 两路都在召回前过滤；字符串值转义，避免用户输入改变过滤表达式。
        filters = {"version": version if version is not None else cfg["data"]["version"]}
        if module is not None:
            filters["module"] = module
        where = " AND ".join(f"{key} = '{value.replace(chr(39), chr(39) * 2)}'" for key, value in filters.items())
        query = next(self.model.embed([cfg["embedding"]["query_prefix"] + question]))
        dense = (self.table.search(query).distance_type("cosine")
                 .where(where, prefilter=True).nprobes(cfg["database"]["nprobes"])
                 .limit(settings["candidate_k"]).to_list())
        lists = [(dense, 1.0 if mode == "vector" else settings["vector_weight"])]
        terms = lexical_text(question)
        if mode == "hybrid" and terms:
            sparse = (self.table.search(terms, query_type="fts", fts_columns="terms")
                      .where(where, prefilter=True).limit(settings["candidate_k"]).to_list())
            lists.append((sparse, 1 - settings["vector_weight"]))
        candidates, scores = {}, {}
        for hits, weight in lists:
            for rank, hit in enumerate(hits, 1):
                key = hit["chunk_id"]
                candidates[key] = hit
                scores[key] = scores.get(key, 0.0) + weight / (settings["rrf_k"] + rank)
        results, seen = [], set()
        for key in sorted(scores, key=lambda key: (-scores[key], key)):
            hit = candidates[key]
            cosine = float(np.dot(query, np.asarray(hit["vector"], dtype=np.float32)))
            # RRF 分数只排序；拒答使用有明确量纲的原始余弦相似度。
            if cosine < threshold or hit["doc_id"] in seen:
                continue
            seen.add(hit["doc_id"])
            results.append({name: hit[name] for name in ("doc_id", "chunk_id", "title", "text", "source", "module", "version")}
                           | {"similarity": cosine, "rrf_score": scores[key]})
            if len(results) == top_k:
                break
        return {"status": "找到" if results else "未找到", "results": results,
                "filters": filters, "threshold": threshold, "mode": mode,
                "latency_ms": (time.perf_counter() - started) * 1000}
