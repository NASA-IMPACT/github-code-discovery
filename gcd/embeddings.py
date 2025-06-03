from __future__ import annotations

import numpy as np
from loguru import logger
from sentence_transformers import SentenceTransformer


class Embedder:
    """Base class for embedding models."""

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        debug: bool = False,
    ):
        self.model_name = model_name
        logger.info(f"Loading SentenceTransformer model: {self.model_name}")
        self.model = SentenceTransformer(self.model_name)
        logger.info(f"Loaded SentenceTransformer model: {self.model_name}")
        self.debug = bool(debug)

    def embed_texts(
        self,
        texts: list[str],
    ) -> np.ndarray:
        """Get embeddings using sentence-transformers."""
        if isinstance(texts, str):
            texts = [texts]
        return self.model.encode(texts, convert_to_tensor=False)

    def get_embedding_dimensions(self) -> int:
        """Get the dimensions of the embeddings."""
        assert self.model is not None, "Model is not loaded"
        if not hasattr(self.model, "get_sentence_embedding_dimension"):
            return self.embed_texts(
                ["test"],
            ).shape[1]
        # Use the model's method to get embedding dimensions
        return self.model.get_sentence_embedding_dimension()

    @property
    def embedding_dimensions(self) -> int:
        """Get the dimensions of the embeddings."""
        return self.get_embedding_dimensions()

    def compute_similarity(self, query: str, text: str) -> float:
        """Compute similarity between query and text."""
        raise NotImplementedError("Subclasses must implement this method.")
