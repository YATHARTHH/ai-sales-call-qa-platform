"""SalesCall QA Evaluation Layer.

Contains evaluator contracts, strategies, evidence models, registry, and policy engine.
Zero dependency on external infrastructure.
"""

from packages.evaluation.base import BaseCheckEvaluator, EvaluatorContext
from packages.evaluation.evaluators.behavior import BehaviorEvaluator
from packages.evaluation.evaluators.factual import FactualMatchEvaluator
from packages.evaluation.evaluators.verbatim import VerbatimRequirementEvaluator
from packages.evaluation.registry import EvaluatorRegistry

__all__ = [
    "BaseCheckEvaluator",
    "EvaluatorContext",
    "EvaluatorRegistry",
    "VerbatimRequirementEvaluator",
    "FactualMatchEvaluator",
    "BehaviorEvaluator",
]
