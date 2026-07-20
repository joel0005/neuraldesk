"""Simple file-based vector store. No Qdrant needed. Just works."""

import os
import json
import numpy as np
from dataclasses import dataclass

STORE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "db_data", "vectors")


@dataclass
class SearchResult:
    id: str
    score: float
    content: str
    metadata: dict


class VectorStore:

    def __init__(self):
        os.makedirs(STORE_DIR, exist_ok=True)

    def _collection_path(self, name: str) -> str:
        path = os.path.join(STORE_DIR, name)
        os.makedirs(path, exist_ok=True)
        return path

    def _load(self, collection: str) -> tuple:
        path = self._collection_path(collection)
        vectors_file = os.path.join(path, "vectors.npy")
        data_file = os.path.join(path, "data.json")

        if not os.path.exists(vectors_file) or not os.path.exists(data_file):
            return np.array([]), []

        vectors = np.load(vectors_file)
        with open(data_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        return vectors, data

    def _save(self, collection: str, vectors: np.ndarray, data: list):
        path = self._collection_path(collection)
        np.save(os.path.join(path, "vectors.npy"), vectors)
        with open(os.path.join(path, "data.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    def create_collection(self, name: str, dimension: int = 384):
        self._collection_path(name)

    def delete_collection(self, name: str):
        import shutil
        path = os.path.join(STORE_DIR, name)
        if os.path.exists(path):
            shutil.rmtree(path)

    def upsert(self, collection: str, ids: list, vectors: list, payloads: list):
        existing_vecs, existing_data = self._load(collection)

        new_vecs = np.array(vectors, dtype=np.float32)
        new_data = [{"id": uid, "payload": payload} for uid, payload in zip(ids, payloads)]

        if len(existing_vecs) > 0:
            all_vecs = np.vstack([existing_vecs, new_vecs])
            all_data = existing_data + new_data
        else:
            all_vecs = new_vecs
            all_data = new_data

        self._save(collection, all_vecs, all_data)
        print(f"  [VectorStore] Saved {len(new_data)} vectors to {collection} (total: {len(all_data)})")

    def search(self, collection: str, query_vector: list, top_k: int = 5) -> list:
        vectors, data = self._load(collection)

        if len(vectors) == 0 or len(data) == 0:
            print(f"  [VectorStore] Collection {collection} is empty")
            return []

        # Cosine similarity
        query = np.array(query_vector, dtype=np.float32)
        query_norm = query / (np.linalg.norm(query) + 1e-10)

        norms = np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-10
        normalized = vectors / norms

        scores = np.dot(normalized, query_norm)

        # Get top K
        top_indices = np.argsort(scores)[::-1][:top_k]

        results = []
        for idx in top_indices:
            idx = int(idx)
            score = float(scores[idx])
            entry = data[idx]
            payload = entry.get("payload", {})

            results.append(SearchResult(
                id=entry.get("id", ""),
                score=score,
                content=payload.get("content", ""),
                metadata=payload.get("metadata", {}),
            ))

        print(f"  [VectorStore] Search found {len(results)} results, top score: {results[0].score:.3f}" if results else "  [VectorStore] No results")
        return results

    def delete_by_source(self, collection: str, source_id: str):
        vectors, data = self._load(collection)
        if len(vectors) == 0:
            return

        keep = []
        for i, entry in enumerate(data):
            if entry.get("payload", {}).get("source_id") != source_id:
                keep.append(i)

        if len(keep) < len(data):
            new_vecs = vectors[keep] if keep else np.array([])
            new_data = [data[i] for i in keep]
            self._save(collection, new_vecs, new_data)

    def count(self, collection: str) -> int:
        _, data = self._load(collection)
        return len(data)