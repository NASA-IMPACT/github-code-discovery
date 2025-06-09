from __future__ import annotations

from abc import ABC, abstractmethod
import numpy as np
from loguru import logger
from gcd.embeddings import Embedder
from gcd.schema import CodeElement

class CodeElementScorer(ABC):
    """Base abstract class for embedding-based code element scorers."""

    def __init__(
        self,
        embedder: Embedder | None = None,
        weights: dict[str, float] | None = None,
        debug: bool = False,
    ):
        self.embedder = embedder or Embedder()
        self.weights = weights or {
            "name": 0.40,
            "docstring": 0.40,
            "signature": 0.10,
            "file_path": 0.10,
        }
        self.debug = bool(debug)

    def _get_embeddings(self, texts: list[str]) -> np.ndarray:
        """Get embeddings for a list of texts."""
        if not self.embedder:
            raise ValueError("Embedder is not initialized")
        return self.embedder.embed_texts(texts)

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

        if self.embedder is None:
            return self._fallback_similarity(query, text)

        try:
            embeddings = self._get_embeddings([query, text])

            # Compute cosine similarity
            query_emb = embeddings[0]
            text_emb = embeddings[1]

            # Normalize vectors
            query_norm = np.linalg.norm(query_emb)
            text_norm = np.linalg.norm(text_emb)

            if query_norm == 0 or text_norm == 0:
                return 0.0

            similarity = float(np.dot(query_emb, text_emb) / (query_norm * text_norm))  # noqa

            # Convert to 0-1 range (cosine similarity is -1 to 1)
            return max(0.0, (similarity + 1.0) / 2.0)

        except Exception as e:
            logger.error(f"Error computing similarity: {e}")
            return self._fallback_similarity(query, text)

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
        weights = weights or self.weights
        if self.debug:
            logger.debug(f"Weights = {weights}")

        # Normalize weights to sum to 1.0
        total_weight = sum(weights.values())
        if total_weight > 0:
            weights = {k: v / total_weight for k, v in weights.items()}

        components = []
        for key in weights:
            val = getattr(element, key, "")
            if not val:
                continue
            score = round(self.compute_similarity(query, val), 3)
            if self.debug:
                logger.debug(f"{key}: {score}")
            components.append((score, weights[key]))

        score = float(self._score_element(components))
        return min(1.0, max(0.0, score))

    @abstractmethod
    def _score_element(self, components: list[tuple]) -> float:
        """
        Compute the final score for an element based on its components.

        Args:
            components: List of tuples (score, weight) for each component

        Returns:
            Final score between 0.0 and 1.0
        """
        raise NotImplementedError()

    def score_elements(
        self,
        elements: list[CodeElement],
        query: str,
        weights: dict[str, float] | None = None,
    ) -> list[CodeElement]:
        """Score and sort a list of code elements."""
        res = []
        for element in elements:
            scored_element = element.model_copy()
            scored_element.score = self.score_element(element, query, weights)
            res.append(scored_element)
        res.sort(key=lambda x: x.score, reverse=True)
        return res


class WeightedAverageScorer(CodeElementScorer):
    """Code element scorer using weighted average of component scores."""

    def _score_element(self, components: list[tuple]) -> float:
        """Compute final score using weighted average."""
        if not components:
            return 0.0
        score = sum([score * weight for score, weight in components])
        return min(1.0, max(0.0, score))


class WeightedRMSScorer(CodeElementScorer):
    """Code element scorer using weighted root mean square of component scores."""  # noqa

    def _score_element(self, components: list[tuple]) -> float:
        """Compute final score using weighted RMS."""
        if not components:
            return 0.0
        score = sum(weight * score**2 for score, weight in components)
        score = np.sqrt(score)
        return min(1.0, max(0.0, score))


class WeightedAverageSelectiveScorer(CodeElementScorer):
    """Code element scorer using weighted average of only high-scoring components."""  # noqa

    def __init__(
        self,
        embedder: Embedder | None = None,
        weights: dict[str, float] | None = None,
        debug: bool = False,
        threshold: float = 0.25,
    ):
        super().__init__(embedder, weights, debug)
        self.threshold = threshold

    def _score_element(self, components: list[tuple]) -> float:
        """Compute final score using weighted average of components above threshold."""  # noqa
        # Filter components above threshold
        filtered_components = [
            (score, weight)
            for score, weight in components
            if score >= self.threshold  # noqa
        ]

        if not filtered_components:
            return 0.0

        # Renormalize weights for remaining components
        total_valid_weight = sum(weight for _, weight in filtered_components)
        if total_valid_weight == 0:
            return 0.0

        score = sum(
            score * (weight / total_valid_weight)
            for score, weight in filtered_components
        )
        return min(1.0, max(0.0, score))
