from __future__ import annotations

from gcd.embeddings import Embedder
from gcd.scorer import (
    CodeElementScorer,
    WeightedAverageScorer,
    WeightedAverageSelectiveScorer,
    WeightedRMSScorer,
)


# Factory function for easy scorer creation
def create_scorer(
    scorer_type: str = "weighted_average",
    embedder: Embedder | None = None,
    weights: dict[str, float] | None = None,
    debug: bool = False,
    **kwargs,
) -> CodeElementScorer:
    """
    Factory function to create different types of scorers.

    Args:
        scorer_type: Type of scorer
            ("weighted_average", "weighted_rms", "weighted_average_selective")
        embedder: Embedder instance
        weights: Component weights
        debug: Debug mode
        **kwargs: Additional scorer-specific parameters

    Returns:
        CodeElementScorer instance
    """
    scorer_classes = {
        "weighted_average": WeightedAverageScorer,
        "weighted_rms": WeightedRMSScorer,
        "weighted_average_selective": WeightedAverageSelectiveScorer,
    }

    if scorer_type not in scorer_classes:
        raise ValueError(
            f"Unknown scorer type: {scorer_type}. "
            f"Available: {list(scorer_classes.keys())}",
        )

    scorer_class = scorer_classes[scorer_type]
    return scorer_class(
        embedder=embedder,
        weights=weights,
        debug=debug,
        **kwargs,
    )
