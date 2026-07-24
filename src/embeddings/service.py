"""Embedding Service — converts text to vectors. Local = free, no API key."""

import os
from ..config import config


class EmbeddingService:

    def __init__(self, provider: str = "", model: str = ""):
        self.provider = provider or config.DEFAULT_EMBEDDING_PROVIDER
        self.model = model or config.DEFAULT_EMBEDDING_MODEL
        self._model = None

        if self.provider == "local":
            local_dims = {
                "all-MiniLM-L6-v2": 384,
                "all-mpnet-base-v2": 768,
                "bge-base-en-v1.5": 768,
                "bge-large-en-v1.5": 1024,
                "all-MiniLM-L12-v2": 384,
                "multi-qa-mpnet-base-dot-v1": 768,
            }
            self.dimension = local_dims.get(self.model, 384)
        elif self.provider == "ollama":
            ollama_dims = {
                "nomic-embed-text": 768,
                "mxbai-embed-large": 1024,
                "all-minilm": 384,
                "snowflake-arctic-embed": 1024,
                "bge-m3": 1024,
            }
            self.dimension = ollama_dims.get(self.model, 768)
        elif self.provider == "openai":
            self.dimension = 1536
        else:
            self.dimension = 384

    def _load_local_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            print(f"Loading embedding model: {self.model} (first time is slow)...")
            self._model = SentenceTransformer(self.model)
        return self._model

    def embed_texts(self, texts: list) -> list:
        if not texts:
            return []

        if self.provider == "local":
            model = self._load_local_model()
            embeddings = model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
            return embeddings.tolist()

        elif self.provider == "ollama":
            import requests
            base_url = config.OLLAMA_BASE_URL.rstrip("/")
            all_embeddings = []
            for text in texts:
                response = requests.post(
                    f"{base_url}/api/embed",
                    json={"model": self.model, "input": text},
                    timeout=120,
                )
                response.raise_for_status()
                data = response.json()
                embedding = data.get("embeddings", [[]])[0]
                if embedding and self.dimension != len(embedding):
                    self.dimension = len(embedding)
                all_embeddings.append(embedding)
            return all_embeddings

        elif self.provider == "openai":
            from openai import OpenAI
            if not config.OPENAI_API_KEY:
                print("No OpenAI key. Falling back to local embeddings.")
                self.provider = "local"
                self.dimension = 384
                self.model = "all-MiniLM-L6-v2"
                return self.embed_texts(texts)

            client = OpenAI(api_key=config.OPENAI_API_KEY)
            all_embeddings = []
            for i in range(0, len(texts), 500):
                batch = texts[i:i + 500]
                response = client.embeddings.create(model=self.model, input=batch)
                all_embeddings.extend([d.embedding for d in response.data])
            return all_embeddings

        else:
            raise ValueError(f"Unknown embedding provider: {self.provider}")

    def embed_query(self, text: str) -> list:
        results = self.embed_texts([text])
        return results[0] if results else []

    @staticmethod
    def list_ollama_models():
        """Fetch embedding models available in local Ollama."""
        try:
            import requests
            resp = requests.get(f"{config.OLLAMA_BASE_URL.rstrip('/')}/api/tags", timeout=5)
            data = resp.json()
            embed_keywords = ["embed", "bge", "minilm", "snowflake", "mxbai"]
            models = []
            for m in data.get("models", []):
                name = m["name"]
                if any(k in name.lower() for k in embed_keywords):
                    models.append(name)
            return models
        except Exception:
            return []

    @staticmethod
    def list_local_models():
        """Find sentence-transformer models already downloaded on this PC."""
        known = ["all-MiniLM-L6-v2", "all-mpnet-base-v2", "bge-base-en-v1.5", "bge-large-en-v1.5", "all-MiniLM-L12-v2", "multi-qa-mpnet-base-dot-v1"]
        cache_dir = os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub")
        downloaded = set()
        if os.path.exists(cache_dir):
            for folder in os.listdir(cache_dir):
                for model in known:
                    if model.lower().replace("-", "--") in folder.lower() or model.lower() in folder.lower():
                        downloaded.add(model)

        ids = []
        labels = []
        for m in known:
            ids.append(m)
            if m in downloaded:
                labels.append(m + " (downloaded)")
            else:
                labels.append(m + " (will download on first use)")
        return ids, labels