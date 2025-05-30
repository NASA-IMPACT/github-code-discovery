from __future__ import annotations

import numpy as np
from loguru import logger
from sentence_transformers import SentenceTransformer

from gcd.schema import CodeElement


class EmbeddingScorer:
    """Embedding-based scorer for code elements."""

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

    def _get_embeddings_sentence_transformers(
        self,
        texts: list[str],
    ) -> np.ndarray:
        """Get embeddings using sentence-transformers."""
        return self.model.encode(texts, convert_to_tensor=False)

    def _fallback_similarity(self, query: str, text: str) -> float:
        """Fallback similarity using simple text matching."""
        if not text:
            return 0.0

        query_lower = query.lower()
        text_lower = text.lower()

        # Exact match
        if query_lower == text_lower:
            return 1.0

        # Substring match
        if query_lower in text_lower:
            return 0.8

        # Word overlap
        query_words = set(query_lower.split())
        text_words = set(text_lower.split())

        if not query_words:
            return 0.0

        overlap = len(query_words.intersection(text_words))
        return overlap / len(query_words) * 0.6

    def compute_similarity(self, query: str, text: str) -> float:
        """Compute similarity between query and text."""
        if not text.strip():
            return 0.0

        if self.model is None:
            return self._fallback_similarity(query, text)

        try:
            embeddings = self._get_embeddings_sentence_transformers(
                [query, text],
            )

            # Compute cosine similarity
            query_emb = embeddings[0]
            text_emb = embeddings[1]

            # Normalize vectors
            query_norm = np.linalg.norm(query_emb)
            text_norm = np.linalg.norm(text_emb)

            if query_norm == 0 or text_norm == 0:
                return 0.0

            similarity = np.dot(query_emb, text_emb) / (query_norm * text_norm)

            # Convert to 0-1 range (cosine similarity is -1 to 1)
            return max(0.0, (similarity + 1.0) / 2.0)

        except Exception as e:
            logger.error(f"Error computing similarity: {e}")
            return self._fallback_similarity(query, text)

    @staticmethod
    def _weighted_average(components: list[tuple]) -> float:
        if not components:
            return 0.0
        score = sum([score * weight for score, weight in components])
        return min(1.0, max(0.0, score))

    @staticmethod
    def _weighted_rms(components: list[tuple]) -> float:
        score = sum(weight * score**2 for score, weight in components)
        score = np.sqrt(score)
        return min(1.0, max(0.0, score))

    @staticmethod
    def _weighted_average_selective(
        components: list[tuple],
        threshold: float = 0.25,
    ) -> float:
        components = [
            (score, weight) for score, weight in components if score >= threshold
        ]
        if not components:
            return 0.0
        total_valid_weight = sum(weight for _, weight in components)
        score = sum(
            score * (weight / total_valid_weight) for score, weight in components
        )
        return min(1.0, max(0.0, score))

    def score_element(
        self,
        element: CodeElement,
        query: str,
        weights: dict[str, float] | None = None,
    ) -> float:
        """
        Score how well an element matches the query using embeddings.

        Args:
            element: CodeElement to score
            query: Search query
            weights: Weights for different components
                (name, docstring, signature, file_path)

        Returns:
            Score between 0.0 and 1.0
        """
        weights = weights or {
            "name": 0.40,
            "docstring": 0.40,
            "signature": 0.10,
            "file_path": 0.10,
        }
        if self.debug:
            logger.debug(f"Weights = {weights}")

        # Normalize weights to sum to 1.0
        total_weight = sum(weights.values())
        if total_weight > 0:
            weights = {k: v / total_weight for k, v in weights.items()}

        # Compute individual similarity scores
        s1 = round(self.compute_similarity(query, element.name), 3)
        s2 = round(self.compute_similarity(query, element.docstring), 3)
        s3 = round(self.compute_similarity(query, element.signature), 3)
        s4 = round(self.compute_similarity(query, element.file_path), 3)

        if self.debug:
            logger.debug(f"Name score :: {s1}")
            logger.debug(f"Docstring score :: {s2}")
            logger.debug(f"Signature score :: {s3}")
            logger.debug(f"Filepath score :: {s4}")

        components = [
            (s1, weights["name"]),
            (s2, weights["docstring"]),
            (s3, weights["signature"]),
            (s4, weights["file_path"]),
        ]
        score = self._weighted_average_selective(components)
        # score = self._weighted_average(components)
        # score = self._weighted_rms(components)
        return min(1.0, max(0.0, score))

    def score_elements(
        self,
        elements: list[CodeElement],
        query: str,
        weights: dict[str, float] | None = None,
    ) -> list[CodeElement]:
        """Score and sort a list of code elements."""
        for element in elements:
            element.score = self.score_element(element, query, weights)

        # Sort by score (highest first)
        elements.sort(key=lambda x: x.score, reverse=True)
        return elements
