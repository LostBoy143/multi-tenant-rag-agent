import io
import logging

import docx
import pymupdf

logger = logging.getLogger(__name__)

ALLOWED_CONTENT_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "text/plain": "txt",
}


def extract_text(file_bytes: bytes, content_type: str) -> str:
    file_type = ALLOWED_CONTENT_TYPES.get(content_type)
    if file_type is None:
        raise ValueError(f"Unsupported file type: {content_type}")

    if file_type == "pdf":
        return _extract_pdf(file_bytes)
    elif file_type == "docx":
        return _extract_docx(file_bytes)
    else:
        return _extract_txt(file_bytes)


def _extract_pdf(data: bytes) -> str:
    doc = pymupdf.open(stream=data, filetype="pdf")
    pages = []
    for page in doc:
        text = page.get_text()
        if text.strip():
            pages.append(text)
    doc.close()
    if not pages:
        raise ValueError("PDF contains no extractable text.")
    return "\n\n".join(pages)


def _extract_docx(data: bytes) -> str:
    document = docx.Document(io.BytesIO(data))
    paragraphs = [p.text for p in document.paragraphs if p.text.strip()]
    if not paragraphs:
        raise ValueError("DOCX contains no extractable text.")
    return "\n\n".join(paragraphs)


def _extract_txt(data: bytes) -> str:
    text = data.decode("utf-8", errors="replace")
    if not text.strip():
        raise ValueError("Text file is empty.")
    return text
