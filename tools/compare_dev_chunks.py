"""在已建好的三张表上评估开发集，不读取测试题。"""
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kb.core import ROOT, Retriever, load_config, load_model, read_jsonl
from kb.evaluate import measure

config = load_config()
model = load_model(config)
dev = read_jsonl(ROOT / "data/dev_questions.jsonl")
rows, results = [], {}
for size, overlap in [(180, 30), (300, 50), (420, 70)]:
    table = config["database"]["table"] if size == config["chunking"]["chunk_size"] else f"comparison_{size}_{overlap}"
    variant = copy.deepcopy(config)
    variant["database"]["table"] = table
    result = measure(Retriever(variant, model), dev, "hybrid", 0.5, 1, config["evaluation"]["seed"])
    rows.append({"chunk_size": size, "overlap": overlap, "dev_recall_at_5": result["recall_at_5"],
                 "dev_rejection_rate": result["rejection_rate"]})
    results[str(size)] = result
(ROOT / "results/chunk_development.json").write_text(json.dumps({"rows": rows, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(rows, ensure_ascii=False, indent=2))
