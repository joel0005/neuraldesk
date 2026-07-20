"""Smart Chunker — splits text into optimal chunks for embedding."""

import re
import hashlib
from dataclasses import dataclass, field


@dataclass
class Chunk:
    content: str
    index: int
    metadata: dict = field(default_factory=dict)
    content_hash: str = ""

    def __post_init__(self):
        self.content_hash = hashlib.sha256(self.content.encode()).hexdigest()[:16]


class SmartChunker:

    def __init__(self, chunk_size: int = 512, overlap: int = 50):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_text(self, text: str, metadata: dict = None) -> list:
        if not text or not text.strip():
            return []
        metadata = metadata or {}

        # Try semantic chunking first (by headings/paragraphs)
        chunks = self._semantic_chunk(text, metadata)
        if chunks:
            return self._deduplicate(chunks)

        # Fallback to fixed-size
        return self._deduplicate(self._fixed_chunk(text, metadata))

    def chunk_rows(self, rows: list, table_name: str = "data", metadata: dict = None) -> list:
        """Each database/CSV row becomes a text chunk."""
        metadata = metadata or {}
        chunks = []
        for i, row in enumerate(rows):
            parts = [f"{k}: {v}" for k, v in row.items() if v is not None and str(v).strip()]
            if parts:
                chunks.append(Chunk(
                    content=", ".join(parts),
                    index=i,
                    metadata={**metadata, "table_name": table_name, "row_index": i},
                ))
        return chunks

    def _semantic_chunk(self, text: str, metadata: dict) -> list:
        # Split by double newlines or headings
        sections = re.split(r'\n\n+', text)
        chunks = []
        current = ""

        for section in sections:
            section = section.strip()
            if not section:
                continue

            if len(current) + len(section) > self.chunk_size and current:
                chunks.append(Chunk(content=current.strip(), index=len(chunks), metadata=metadata))
                current = section
            else:
                current = current + "\n\n" + section if current else section

        if current.strip():
            chunks.append(Chunk(content=current.strip(), index=len(chunks), metadata=metadata))

        return chunks

    def _fixed_chunk(self, text: str, metadata: dict) -> list:
        chunks = []
        start = 0

        while start < len(text):
            end = start + self.chunk_size

            # Try to break at sentence boundary
            if end < len(text):
                for sep in [". ", ".\n", "\n\n", "\n", " "]:
                    pos = text.rfind(sep, start + int(self.chunk_size * 0.7), end)
                    if pos > start:
                        end = pos + len(sep)
                        break

            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append(Chunk(content=chunk_text, index=len(chunks), metadata=metadata))

            start = end - self.overlap

        return chunks

    def _deduplicate(self, chunks: list) -> list:
        seen = set()
        unique = []
        for c in chunks:
            if c.content_hash not in seen:
                seen.add(c.content_hash)
                unique.append(c)
        return unique