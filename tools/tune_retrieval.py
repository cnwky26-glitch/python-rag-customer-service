"""仅使用开发集选择候选数与融合权重；需要先 build。"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kb.core import ROOT, Retriever, load_config, load_model, read_jsonl

config = load_config()
searcher = Retriever(config, load_model(config))
dev = read_jsonl(ROOT / "data/dev_questions.jsonl")
rows = []
for candidate_k in config["evaluation"]["candidate_grid"]:
    for vector_weight in config["evaluation"]["vector_weight_grid"]:
        config["retrieval"].update(candidate_k=candidate_k, vector_weight=vector_weight)
        raw = [(q, searcher.search(q["question"], q.get("module"), threshold=0, top_k=candidate_k)) for q in dev]
        for threshold in config["evaluation"]["thresholds"]:
            recalls, rejects = [], []
            for q, response in raw:
                hits = [hit for hit in response["results"] if hit["similarity"] >= threshold][:5]
                if q["relevant_doc_ids"]:
                    gold = set(q["relevant_doc_ids"])
                    recalls.append(len(gold & {hit["doc_id"] for hit in hits}) / len(gold))
                else:
                    rejects.append(not hits)
            recall, rejection = sum(recalls) / len(recalls), sum(rejects) / len(rejects)
            rows.append({"candidate_k": candidate_k, "vector_weight": vector_weight, "threshold": threshold,
                         "dev_recall_at_5": recall, "dev_rejection_rate": rejection, "balanced_score": (recall + rejection) / 2})
selected = max(rows, key=lambda row: (row["balanced_score"], row["dev_recall_at_5"], -row["candidate_k"], -row["threshold"]))
(ROOT / "results/retrieval_tuning.json").write_text(json.dumps({"rows": rows, "selected": selected}, ensure_ascii=False, indent=2), encoding="utf-8")
config_path = ROOT / "config.toml"
text = config_path.read_text(encoding="utf-8")
for key, value in (("candidate_k", selected["candidate_k"]), ("vector_weight", selected["vector_weight"]),
                   ("similarity_threshold", selected["threshold"])):
    text = re.sub(rf"^{key} = [0-9.]+", f"{key} = {value}", text, flags=re.MULTILINE)
config_path.write_text(text, encoding="utf-8")
print(json.dumps(selected, ensure_ascii=False, indent=2))
