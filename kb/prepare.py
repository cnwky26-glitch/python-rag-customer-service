"""保存官方 HTML 快照，并将独立 API 说明提取为可追溯的知识条目。"""
import hashlib
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup


def clean(text):
    text = unicodedata.normalize("NFKC", text).replace("\xa0", " ")
    text = text.replace("¶", "").replace("", "")
    return re.sub(r"\s+", " ", text).strip()


def prepare(root, config, download=False):
    raw_dir = root / "data/raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    documents, sources = [], []
    for module in config["data"]["modules"]:
        url = f'https://docs.python.org/{config["data"]["language"]}/{config["data"]["version"]}/library/{module}.html'
        path = raw_dir / f"{module}.html"
        if download:
            request = Request(url, headers={"User-Agent": "PythonSupportCourseProject/1.0"})
            with urlopen(request, timeout=60) as response:
                path.write_bytes(response.read())
        html = path.read_bytes()
        soup = BeautifulSoup(html, "html.parser")
        count_before = len(documents)
        for definition in soup.select("dl.py"):
            signature = definition.find("dt", recursive=False)
            body = definition.find("dd", recursive=False)
            if signature is None or body is None or not signature.get("id"):
                continue
            anchor = signature["id"]
            # 子方法另立条目，避免整段类说明重复收录所有子方法。
            fragment = BeautifulSoup(str(body), "html.parser")
            for child in fragment.select("dl.py"):
                child.decompose()
            text = clean(fragment.get_text(" ", strip=True))
            if not text:
                continue
            title = clean(signature.get_text(" ", strip=True))
            documents.append({
                "doc_id": f"{module}:{anchor}", "title": title,
                "text": text, "module": module,
                "version": config["data"]["version"], "language": config["data"]["language"],
                "source": url + "#" + anchor,
            })
        sources.append({"module": module, "url": url,
                        "sha256": hashlib.sha256(html).hexdigest(),
                        "documents": len(documents) - count_before})
        print(f"{module}: {len(documents) - count_before} entries", flush=True)
    assert len({d["doc_id"] for d in documents}) == len(documents), "重复文档 ID"
    if len(documents) < config["data"]["min_documents"]:
        raise ValueError(f"仅提取到 {len(documents)} 条，未满足数据量要求")
    output = root / "data/documents.jsonl"
    output.write_text("".join(json.dumps(d, ensure_ascii=False) + "\n" for d in documents), encoding="utf-8")
    manifest = {"created_at": datetime.now().astimezone().isoformat(),
                "document_count": len(documents), "source_page_count": len(sources),
                "unit": "独立 API 说明条目，不将分块计入原始文档数量",
                "documents_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                "license": "Python documentation PSF License; see data/LICENSE-python.txt", "sources": sources}
    (root / "data/manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if download:
        with urlopen("https://docs.python.org/zh-cn/3.13/license.html", timeout=60) as response:
            license_html = response.read()
        license_soup = BeautifulSoup(license_html, "html.parser")
        (root / "data/LICENSE-python.txt").write_text(license_soup.select_one('[role="main"]').get_text("\n", strip=True), encoding="utf-8")
    return manifest
