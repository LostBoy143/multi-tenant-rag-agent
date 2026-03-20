SENTENCE_ENDINGS = {".", "!", "?", "\n"}


def recursive_chunk(text: str, chunk_size: int = 500, chunk_overlap: int = 50) -> list[str]:
    """Split text into overlapping chunks, trying to break at sentence boundaries."""
    if not text.strip():
        return []

    text = text.strip()
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        if end >= len(text):
            chunks.append(text[start:].strip())
            break

        split_pos = _find_sentence_boundary(text, start, end)
        chunk = text[start:split_pos].strip()
        if chunk:
            chunks.append(chunk)

        start = split_pos - chunk_overlap
        if start < 0:
            start = 0
        if start >= split_pos:
            start = split_pos

    return [c for c in chunks if c]


def _find_sentence_boundary(text: str, start: int, end: int) -> int:
    """Find the last sentence ending within the window, falling back to the end position."""
    search_start = max(start + (end - start) // 2, start)
    best = -1
    for i in range(end - 1, search_start - 1, -1):
        if text[i] in SENTENCE_ENDINGS:
            best = i + 1
            break
    return best if best > start else end
