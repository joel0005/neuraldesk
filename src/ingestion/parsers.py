"""File Parsers — extract text from PDF, DOCX, CSV, Excel, JSON, HTML, TXT."""

import os
import json
import logging

logger = logging.getLogger(__name__)


def parse_file(file_path: str) -> dict:
    """
    Parse any supported file. Returns:
    {"content": "...", "metadata": {...}, "tables": [...], "pages": [...]}
    """
    ext = os.path.splitext(file_path)[1].lower()

    parsers = {
        ".pdf": parse_pdf,
        ".docx": parse_docx,
        ".csv": parse_csv,
        ".xlsx": parse_excel,
        ".xls": parse_excel,
        ".json": parse_json,
        ".txt": parse_text,
        ".md": parse_text,
        ".html": parse_html,
        ".htm": parse_html,
    }

    parser = parsers.get(ext)
    if not parser:
        return {"content": "", "metadata": {}, "error": f"Unsupported file type: {ext}"}

    try:
        return parser(file_path)
    except Exception as e:
        logger.error(f"Parse failed for {file_path}: {e}")
        return {"content": "", "metadata": {}, "error": str(e)}


def parse_pdf(path: str) -> dict:
    import fitz
    doc = fitz.open(path)
    pages = []
    for page in doc:
        pages.append(page.get_text("text"))
    doc.close()

    return {
        "content": "\n\n".join(pages),
        "metadata": {"file_type": "pdf", "page_count": len(pages), "file_name": os.path.basename(path)},
        "pages": pages,
    }


def parse_docx(path: str) -> dict:
    from docx import Document
    doc = Document(path)
    paragraphs = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            if para.style.name.startswith("Heading"):
                paragraphs.append(f"## {text}")
            else:
                paragraphs.append(text)

    return {
        "content": "\n\n".join(paragraphs),
        "metadata": {"file_type": "docx", "file_name": os.path.basename(path)},
    }


def parse_csv(path: str) -> dict:
    import pandas as pd
    import chardet

    with open(path, "rb") as f:
        detected = chardet.detect(f.read(10000))
    encoding = detected.get("encoding", "utf-8")

    try:
        df = pd.read_csv(path, encoding=encoding)
    except Exception:
        df = pd.read_csv(path, encoding="latin-1")

    rows_text = []
    for _, row in df.iterrows():
        parts = [f"{col}: {val}" for col, val in row.items() if pd.notna(val)]
        rows_text.append(", ".join(parts))

    return {
        "content": "\n".join(rows_text),
        "metadata": {"file_type": "csv", "row_count": len(df), "columns": list(df.columns), "file_name": os.path.basename(path)},
        "dataframe": df,
    }


def parse_excel(path: str) -> dict:
    import pandas as pd
    xls = pd.ExcelFile(path)
    all_text = []
    all_dfs = {}

    for sheet in xls.sheet_names:
        df = pd.read_excel(path, sheet_name=sheet)
        if df.empty:
            continue
        all_dfs[sheet] = df
        all_text.append(f"## Sheet: {sheet}")
        for _, row in df.iterrows():
            parts = [f"{col}: {val}" for col, val in row.items() if pd.notna(val)]
            if parts:
                all_text.append(", ".join(parts))

    return {
        "content": "\n".join(all_text),
        "metadata": {"file_type": "excel", "sheets": xls.sheet_names, "file_name": os.path.basename(path)},
        "dataframes": all_dfs,
    }


def parse_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    lines = []
    _flatten(data, "", lines)

    return {
        "content": "\n".join(lines),
        "metadata": {"file_type": "json", "file_name": os.path.basename(path)},
    }


def _flatten(obj, path, result, depth=0):
    if depth > 10:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            new_path = f"{path}.{k}" if path else k
            if isinstance(v, (str, int, float, bool)):
                result.append(f"{new_path}: {v}")
            else:
                _flatten(v, new_path, result, depth + 1)
    elif isinstance(obj, list):
        for i, item in enumerate(obj[:500]):
            _flatten(item, f"{path}[{i}]", result, depth + 1)


def parse_text(path: str) -> dict:
    import chardet
    with open(path, "rb") as f:
        raw = f.read()
    detected = chardet.detect(raw)
    content = raw.decode(detected.get("encoding", "utf-8"), errors="replace")

    return {
        "content": content,
        "metadata": {"file_type": "text", "file_name": os.path.basename(path)},
    }


def parse_html(path: str) -> dict:
    from bs4 import BeautifulSoup
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    return {
        "content": soup.get_text(separator="\n", strip=True),
        "metadata": {"file_type": "html", "file_name": os.path.basename(path)},
    }


def supported_types() -> list:
    return [".pdf", ".docx", ".csv", ".xlsx", ".xls", ".json", ".txt", ".md", ".html", ".htm"]