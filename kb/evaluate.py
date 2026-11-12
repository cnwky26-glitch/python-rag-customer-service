"""分离开发集阈值校准与固定 20 题评估，保存逐请求结果。"""
import copy
import csv
import hashlib
import importlib.metadata
import json
import platform
import random
import re
import time
from datetime import datetime

import numpy as np

from kb.core import ROOT, Retriever, build, read_jsonl


def save_json(name, value):
    (ROOT / "results" / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def measure(retriever, questions, mode, threshold, repeats, seed):
    # 冷启动单列，不混入稳态 P95；每个计时请求均重新计算查询嵌入。
    first = questions[0]
    cold = retriever.search(first["question"], first.get("module"), mode=mode, threshold=threshold)
    schedule = [(question, repeat) for repeat in range(repeats) for question in questions]
    random.Random(seed).shuffle(schedule)
    requests, first_results = [], {}
    for question, repeat in schedule:
        response = retriever.search(question["question"], question.get("module"), question.get("version"), mode, threshold)
        retrieved = [hit["doc_id"] for hit in response["results"]]
        gold = set(question["relevant_doc_ids"])
        recall = len(gold.intersection(retrieved)) / len(gold) if gold else None
        requests.append({"id": question["id"], "repeat": repeat, "latency_ms": response["latency_ms"],
                         "recall_at_5": recall, "status": response["status"], "retrieved_doc_ids": retrieved})
        first_results.setdefault(question["id"], {**question, "recall_at_5": recall, "response": response})
    latencies = [request["latency_ms"] for request in requests]
    # 每道题等权；重复请求用于延迟抽样，不能把 20 题说成 100 道测试题。
    per_question = [first_results[question["id"]] for question in questions]
    recalls = [question["recall_at_5"] for question in per_question if question["recall_at_5"] is not None]
    no_answers = [question for question in per_question if not question["relevant_doc_ids"]]
    return {"recall_at_5": float(np.mean(recalls)) if recalls else None,
            "recall_curve": {str(k): float(np.mean([
                len(set(q["relevant_doc_ids"]) & {h["doc_id"] for h in q["response"]["results"][:k]}) / len(q["relevant_doc_ids"])
                for q in per_question if q["relevant_doc_ids"]])) for k in range(1, 6)} if recalls else {},
            "p50_ms": float(np.percentile(latencies, 50)), "p95_ms": float(np.percentile(latencies, 95)),
            "p99_ms": float(np.percentile(latencies, 99)), "mean_ms": float(np.mean(latencies)),
            "cold_first_query_ms": cold["latency_ms"], "request_count": len(requests),
            "rejection_rate": sum(q["response"]["status"] == "未找到" for q in no_answers) / len(no_answers) if no_answers else None,
            "questions": per_question, "requests": requests}


def calibrate(retriever, dev, thresholds):
    raw = []
    for question in dev:
        response = retriever.search(question["question"], question.get("module"), mode="hybrid", threshold=0.0,
                                    top_k=retriever.config["retrieval"]["candidate_k"])
        raw.append((question, response))
    rows = []
    for threshold in thresholds:
        recalls, rejections = [], []
        for question, response in raw:
            kept = [hit for hit in response["results"] if hit["similarity"] >= threshold][:5]
            gold = set(question["relevant_doc_ids"])
            if gold:
                recalls.append(len(gold & {hit["doc_id"] for hit in kept}) / len(gold))
            else:
                rejections.append(not kept)
        recall, rejection = float(np.mean(recalls)), float(np.mean(rejections))
        rows.append({"threshold": threshold, "dev_recall_at_5": recall, "dev_rejection_rate": rejection,
                     "balanced_score": (recall + rejection) / 2})
    selected = max(rows, key=lambda row: (row["balanced_score"], row["dev_recall_at_5"], -row["threshold"]))
    save_json("threshold_calibration.json", {"rows": rows, "selected": selected,
              "selection_rule": "仅开发集，最大化 (正例 Recall@5 + 负例拒答率)/2；平局优先正例召回，再选较低阈值以保留召回余量",
              "evidence": [{"question": q, "response": response} for q, response in raw]})
    return selected["threshold"]


def evaluate(config, model):
    started = time.perf_counter()
    (ROOT / "results").mkdir(exist_ok=True)
    tests = read_jsonl(ROOT / "data/test_questions.jsonl")
    dev = read_jsonl(ROOT / "data/dev_questions.jsonl")
    negatives = read_jsonl(ROOT / "data/no_answer_questions.jsonl")
    assert len(tests) == 20, "作业要求固定 20 道测试题"
    documents = {doc["doc_id"]: doc for doc in read_jsonl(ROOT / "data/documents.jsonl")}
    for question in tests + dev + negatives:
        for doc_id in question["relevant_doc_ids"]:
            assert doc_id in documents, f"标注指向不存在的条目: {doc_id}"
            assert documents[doc_id]["module"] == question["module"]
    # 正式方案由 config 指定，保留所有分块对比，不将课程内迭代称为盲测。
    main_build = build(config, model)
    retriever = Retriever(config, model)
    threshold = calibrate(retriever, dev, config["evaluation"]["thresholds"])
    config = copy.deepcopy(config)
    config["retrieval"]["similarity_threshold"] = threshold
    retriever.config = config
    settings = config["evaluation"]
    experiments = []
    for size, overlap in zip(settings["chunk_sizes"], settings["overlaps"], strict=True):
        variant = copy.deepcopy(config)
        variant["chunking"].update(chunk_size=size, overlap=overlap)
        is_main = (size, overlap) == (config["chunking"]["chunk_size"], config["chunking"]["overlap"])
        if is_main:
            built, searcher = main_build, retriever
        else:
            variant["database"]["table"] = f'comparison_{size}_{overlap}'
            built = build(variant, model)
            searcher = Retriever(variant, model)
        for mode in ("vector", "hybrid"):
            print(f"Evaluate chunk={size}/{overlap} mode={mode} threshold={threshold}", flush=True)
            measured = measure(searcher, tests, mode, threshold, settings["repeats"], settings["seed"])
            name = f"chunk_{size}_{overlap}_{mode}"
            save_json(f"{name}.json", measured)
            experiments.append({"name": name, "chunk_size": size, "overlap": overlap, "mode": mode,
                                "threshold": threshold, "chunks": built["chunks"],
                                "build_seconds": built["build_seconds"],
                                "official": is_main and mode == "hybrid",
                                **{key: measured[key] for key in ("recall_at_5", "p50_ms", "p95_ms", "p99_ms", "mean_ms", "cold_first_query_ms", "request_count", "recall_curve")}})
    # 调参前后只改变拒答阈值，其余配置完全一致。
    before = measure(retriever, tests, "hybrid", 0.50, settings["repeats"], settings["seed"])
    before_negatives = measure(retriever, negatives, "hybrid", 0.50, 1, settings["seed"])
    after_negatives = measure(retriever, negatives, "hybrid", threshold, 1, settings["seed"])
    save_json("before_threshold_tuning.json", before)
    save_json("no_answer_before.json", before_negatives)
    save_json("no_answer_after.json", after_negatives)
    # 边界检查针对必做行为，不展开额外的低价值测试。
    empty_query_rejected = False
    try:
        retriever.search(" ")
    except ValueError:
        empty_query_rejected = True
    assert empty_query_rejected
    for question in tests:
        result = retriever.search(question["question"], question["module"])
        assert all(hit["module"] == question["module"] and hit["version"] == config["data"]["version"]
                   and hit["similarity"] >= threshold for hit in result["results"])
    assert all(question["response"]["status"] == "未找到" for question in after_negatives["questions"][-2:])
    save_json("acceptance.json", {"empty_query_rejected": True, "filter_and_threshold_checked": 20,
                                 "empty_module_and_version_return_not_found": True})
    summary = {"created_at": datetime.now().astimezone().isoformat(),
               "environment": {"python": platform.python_version(), "platform": platform.platform(),
                               "processor": platform.processor(),
                               "packages": {name: importlib.metadata.version(name) for name in ("lancedb", "fastembed", "onnxruntime", "numpy", "pyarrow")}},
               "model": config["embedding"], "config": config, "documents": len(documents), "test_questions": len(tests),
               "test_sha256": hashlib.sha256((ROOT / "data/test_questions.jsonl").read_bytes()).hexdigest(),
               "repeats": settings["repeats"], "threshold": threshold, "experiments": experiments,
               "before_threshold_tuning": {key: before[key] for key in ("recall_at_5", "p95_ms")},
               "no_answer_rejection_before": before_negatives["rejection_rate"],
               "no_answer_rejection_after": after_negatives["rejection_rate"],
               "elapsed_seconds": time.perf_counter() - started,
               "metric_definition": "doc-level macro Recall@5; unique doc_id; one pre-labelled target per test question; latency includes embedding, filters, both retrieval routes, fusion and thresholding; excludes model loading and build; serial warm CPU requests; numpy linear percentile"}
    save_json("summary.json", summary)
    columns = [key for key in experiments[0] if key != "recall_curve"]
    with (ROOT / "results/comparison.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(experiments)
    # 写回开发集确定的阈值，保证 README 演示和正式检索一致。
    path = ROOT / "config.toml"
    path.write_text(re.sub(r"similarity_threshold = [0-9.]+", f"similarity_threshold = {threshold}", path.read_text(encoding="utf-8")), encoding="utf-8")
    return summary
