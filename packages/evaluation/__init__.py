"""SalesCall QA Evaluation Layer.

Contains abstract evaluator contracts, check strategies, and evidence models.
Zero dependency on external infrastructure (FastAPI, Redis, MinIO, or OpenAI).
"""

from packages.evaluation.base import BaseCheckEvaluator, EvaluationFinding

__all__ = [
    "BaseCheckEvaluator",
    "EvaluationFinding",
]
