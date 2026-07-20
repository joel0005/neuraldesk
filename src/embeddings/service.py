"""Embedding Service — converts text to vectors. Local = free, no API key."""

from ..config import config


class EmbeddingService:

    def __init__(self, provider: str = "", model: str = ""):
        self.provider = provider or config.DEFAULT_EMBEDDING_PROVIDER
        self.model = model or config.DEFAULT_EMBEDDING_MODEL
        self._model = None

        if self.provider == "local":
            self.dimension = {"all-MiniLM-L6-v2": 384, "all-mpnet-base-v2": 768}.get(self.model, 384)
        else:
            self.dimension = 1536

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