"""Text extraction for uploaded files. Uploads are treated as untrusted data."""

from __future__ import annotations

import csv
import io

MAX_BYTES = 15 * 1024 * 1024
MAX_CHARS = 400_000
TEXT_TYPES = (".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".log", ".xml", ".html", ".tsv", ".sql", ".py", ".ts", ".js")


class UnsupportedFile(Exception):
    pass


def extract_text(name: str, data: bytes) -> tuple[str, str]:
    """Return (media_type, text)."""
    if len(data) > MAX_BYTES:
        raise UnsupportedFile(f"{name} is larger than {MAX_BYTES // (1024 * 1024)} MB")
    low = name.lower()
    if low.endswith(TEXT_TYPES):
        return "text/plain", data.decode("utf-8", errors="replace")[:MAX_CHARS]
    if low.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        pages = [f"[page {i + 1}]\n{(p.extract_text() or '').strip()}" for i, p in enumerate(reader.pages)]
        return "application/pdf", "\n\n".join(pages)[:MAX_CHARS]
    if low.endswith(".docx"):
        import docx

        d = docx.Document(io.BytesIO(data))
        parts = [p.text for p in d.paragraphs if p.text.strip()]
        for t in d.tables:
            for row in t.rows:
                parts.append(" | ".join(c.text.strip() for c in row.cells))
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "\n".join(parts)[:MAX_CHARS]
    if low.endswith(".xlsx"):
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        out = []
        for ws in wb.worksheets:
            buf = io.StringIO()
            w = csv.writer(buf)
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i >= 2000:
                    buf.write("[... rows truncated at 2000]\n")
                    break
                w.writerow(["" if v is None else v for v in row])
            out.append(f"[sheet {ws.title}]\n{buf.getvalue()}")
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "\n\n".join(out)[:MAX_CHARS]
    raise UnsupportedFile(f"{name}: supported types are text, CSV, JSON, YAML, PDF, DOCX and XLSX")
