"""Ingestion Service — takes a file, parses it, chunks it, embeds it, stores it."""

import os
import uuid
from .parsers import parse_file
from .chunker import SmartChunker
from ..embeddings.service import EmbeddingService
from ..vectordb.store import VectorStore


class IngestionService:

    def __init__(self, embedding_provider: str = "", embedding_model: str = ""):
        self.chunker = SmartChunker(chunk_size=512, overlap=50)
        self.embedding = EmbeddingService(provider=embedding_provider, model=embedding_model)
        self.vector_store = VectorStore()

    def ingest_file(self, file_path: str, bot_id: str, source_id: str) -> dict:
        """Parse file → chunk → embed → store in vector DB."""

        # Step 1: Parse
        result = parse_file(file_path)
        if result.get("error"):
            return {"success": False, "error": result["error"]}

        content = result.get("content", "")
        if not content.strip():
            return {"success": False, "error": "File is empty"}

        metadata = {
            "source_id": source_id,
            "source_name": result.get("metadata", {}).get("file_name", os.path.basename(file_path)),
            "source_type": "document",
        }

        # Step 2: Chunk (per page if PDF, else semantic)
        pages = result.get("pages", [])
        if pages:
            all_chunks = []
            for i, page_text in enumerate(pages):
                if not page_text.strip():
                    continue
                page_meta = {**metadata, "page_number": i + 1}
                chunks = self.chunker.chunk_text(page_text, page_meta)
                all_chunks.extend(chunks)
        else:
            all_chunks = self.chunker.chunk_text(content, metadata)

        if not all_chunks:
            return {"success": False, "error": "No content after chunking"}

        # Step 3: Embed
        texts = [c.content for c in all_chunks]
        vectors = self.embedding.embed_texts(texts)

        # Step 4: Store in vector DB
        collection = f"bot_{bot_id}"
        self.vector_store.create_collection(collection, self.embedding.dimension)

        ids = [str(uuid.uuid4()) for _ in all_chunks]
        payloads = [
            {
                "content": c.content,
                "source_id": source_id,
                "metadata": c.metadata,
            }
            for c in all_chunks
        ]

        self.vector_store.upsert(collection, ids, vectors, payloads)

        return {
            "success": True,
            "chunks_created": len(all_chunks),
            "strategy": "embedding",
        }

    def ingest_url(self, url: str, bot_id: str, source_id: str) -> dict:
        """Crawl a URL → chunk → embed → store."""
        try:
            import requests
            from bs4 import BeautifulSoup

            resp = requests.get(url, timeout=30, headers={"User-Agent": "RagBase/1.0"})
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "lxml")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()

            text = soup.get_text(separator="\n", strip=True)
            title = soup.title.string if soup.title else url

            if not text.strip():
                return {"success": False, "error": "No content found at URL"}

            metadata = {
                "source_id": source_id,
                "source_name": title,
                "source_type": "url",
                "url": url,
            }

            chunks = self.chunker.chunk_text(text, metadata)
            if not chunks:
                return {"success": False, "error": "No content after chunking"}

            texts = [c.content for c in chunks]
            vectors = self.embedding.embed_texts(texts)

            collection = f"bot_{bot_id}"
            self.vector_store.create_collection(collection, self.embedding.dimension)

            ids = [str(uuid.uuid4()) for _ in chunks]
            payloads = [{"content": c.content, "source_id": source_id, "metadata": c.metadata} for c in chunks]

            self.vector_store.upsert(collection, ids, vectors, payloads)

            return {"success": True, "chunks_created": len(chunks), "strategy": "embedding"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def delete_source(self, bot_id: str, source_id: str):
        """Remove all vectors for a source."""
        collection = f"bot_{bot_id}"
        self.vector_store.delete_by_source(collection, source_id)