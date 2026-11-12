"""使用 Word 导出的 PDF，通过文档技能标准 rasterize 流程核对所有页。"""
import importlib.util
import os
from pathlib import Path

root = Path(__file__).resolve().parents[1]
skill = Path(os.environ["DOCUMENTS_SKILL_PATH"])
spec = importlib.util.spec_from_file_location("render_docx", skill / "render_docx.py")
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)
# 本机无捆绑 LibreOffice，由 Microsoft Word 提供 PDF 转换结果。
renderer.convert_to_pdf = lambda *args, **kwargs: (str(root / ".work/report.pdf"), "Exported by Microsoft Word")
os.environ["PATH"] = os.environ["POPPLER_PATH"] + os.pathsep + os.environ["PATH"]
pages = renderer.rasterize(str(root / "作业报告.docx"), str(root / ".work/report_pages"), 130, False, False)
print(f"Rendered {len(pages)} pages using render_docx.py rasterize")
