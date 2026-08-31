"""基于金标 CSV 的离线 RAG 评估工具。"""

from .dataset import GoldCase, GoldContext, load_gold_cases

__all__ = ["GoldCase", "GoldContext", "load_gold_cases"]
