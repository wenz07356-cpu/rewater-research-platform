"""确定性检索指标与 Ragas 0.4 collections 适配。"""

from __future__ import annotations

import asyncio
import os
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from ragas.embeddings import BaseRagasEmbedding

from .dataset import GoldCase


class LocalBgeM3Embeddings(BaseRagasEmbedding):
    """将项目现有 BGE-M3 单例适配为 Ragas 0.4 Embeddings 接口。"""

    def __init__(self) -> None:
        super().__init__()

    def embed_text(self, text: str, **_: Any) -> list[float]:
        from app.shared.model.embedding_utils import generate_embeddings

        return generate_embeddings([text])["dense"][0]

    def embed_texts(self, texts: list[str], **_: Any) -> list[list[float]]:
        from app.shared.model.embedding_utils import generate_embeddings

        return generate_embeddings(texts)["dense"]

    async def aembed_text(self, text: str, **kwargs: Any) -> list[float]:
        return await asyncio.to_thread(self.embed_text, text, **kwargs)

    async def aembed_texts(
        self, texts: list[str], **kwargs: Any,
    ) -> list[list[float]]:
        return await asyncio.to_thread(self.embed_texts, texts, **kwargs)


def ordered_unique(values: Iterable[object]) -> list[str]:
    result: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if item and item not in result:
            result.append(item)
    return result


@dataclass(frozen=True)
class IdMetric:
    retrieved_ids: list[str]
    gold_ids: list[str]
    must_hit_ids: list[str]
    hit_ids: list[str]
    retrieved_count: int
    gold_count: int
    must_hit_count: int
    hit_count: int
    id_precision: float | None
    id_recall: float | None
    must_hit_rate: float | None


def compute_id_metric(
    retrieved_ids: Iterable[object],
    gold_ids: Iterable[object],
    must_hit_ids: Iterable[object],
    *,
    answerable: bool = True,
) -> IdMetric:
    retrieved = ordered_unique(retrieved_ids)
    gold = ordered_unique(gold_ids)
    must = ordered_unique(must_hit_ids)
    hits = [item for item in retrieved if item in set(gold)]
    applicable = answerable and bool(gold)
    precision = len(hits) / len(retrieved) if applicable and retrieved else None
    recall = len(hits) / len(gold) if applicable else None
    must_hits = sum(item in set(retrieved) for item in must)
    must_rate = must_hits / len(must) if applicable and must else None
    return IdMetric(
        retrieved, gold, must, hits, len(retrieved), len(gold), len(must),
        len(hits), precision, recall, must_rate,
    )


def compute_layer_metrics(case: GoldCase, layer_ids: dict[str, list[str]]) -> dict[str, dict[str, Any]]:
    return {
        layer: asdict(compute_id_metric(
            ids, case.gold_chunk_ids, case.must_hit_chunk_ids,
            answerable=case.answerable,
        ))
        for layer, ids in layer_ids.items()
    }


def abstention_correct(response: str) -> bool:
    """用于不可回答题的确定性最低限度拒答检查。"""
    text = response.strip()
    signals = ("无法确定", "资料不足", "未检索到", "无法回答", "需要补充")
    return bool(text) and any(signal in text for signal in signals)


class RagasEvaluator:
    """Ragas 0.4.3 collections 五指标逐项容错评审器。"""

    def __init__(self, llm: Any, embeddings: Any) -> None:
        from ragas.metrics.collections import (
            AnswerCorrectness, AnswerRelevancy, ContextPrecision,
            ContextRecall, Faithfulness,
        )
        self.metrics = {
            "faithfulness": Faithfulness(llm=llm),
            "answer_relevancy": AnswerRelevancy(llm=llm, embeddings=embeddings),
            "context_precision": ContextPrecision(llm=llm),
            "context_recall": ContextRecall(llm=llm),
            "answer_correctness": AnswerCorrectness(llm=llm, embeddings=embeddings),
        }

    @classmethod
    def from_env(cls) -> "RagasEvaluator":
        from dotenv import load_dotenv
        from openai import AsyncOpenAI
        from ragas.embeddings import OpenAIEmbeddings
        from ragas.llms import llm_factory

        load_dotenv()
        model = os.getenv("RAGAS_EVALUATOR_MODEL", "").strip()
        try:
            max_tokens = int(os.getenv("RAGAS_EVALUATOR_MAX_TOKENS", "4096"))
        except ValueError as exc:
            raise RuntimeError("RAGAS_EVALUATOR_MAX_TOKENS 必须是正整数") from exc
        if max_tokens <= 0:
            raise RuntimeError("RAGAS_EVALUATOR_MAX_TOKENS 必须是正整数")
        embedding_model = os.getenv("RAGAS_EMBEDDING_MODEL", "").strip()
        embedding_provider = os.getenv("RAGAS_EMBEDDING_PROVIDER", "openai").strip().lower()
        base_url = os.getenv("RAGAS_EVALUATOR_BASE_URL") or os.getenv("OPENAI_BASE_URL")
        api_key = os.getenv("RAGAS_EVALUATOR_API_KEY") or os.getenv("OPENAI_API_KEY")
        embedding_url = os.getenv("RAGAS_EMBEDDING_BASE_URL") or base_url
        embedding_key = os.getenv("RAGAS_EMBEDDING_API_KEY") or api_key
        required = {
            "RAGAS_EVALUATOR_MODEL": model,
            "RAGAS_EMBEDDING_MODEL": embedding_model,
            "OPENAI_BASE_URL/RAGAS_EVALUATOR_BASE_URL": base_url,
            "OPENAI_API_KEY/RAGAS_EVALUATOR_API_KEY": api_key,
        }
        if embedding_provider == "openai":
            required.update({
                "OPENAI_BASE_URL/RAGAS_EMBEDDING_BASE_URL": embedding_url,
                "OPENAI_API_KEY/RAGAS_EMBEDDING_API_KEY": embedding_key,
            })
        elif embedding_provider != "local_bge_m3":
            raise RuntimeError(
                "RAGAS_EMBEDDING_PROVIDER 只能是 openai 或 local_bge_m3"
            )
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuntimeError(f"Ragas 评审配置缺失: {', '.join(missing)}")
        llm_client = AsyncOpenAI(
            api_key=api_key, base_url=base_url, timeout=60, max_retries=2
        )
        if embedding_provider == "local_bge_m3":
            embeddings: Any = LocalBgeM3Embeddings()
        else:
            embedding_client = AsyncOpenAI(
                api_key=embedding_key, base_url=embedding_url, timeout=60, max_retries=2
            )
            embeddings = OpenAIEmbeddings(client=embedding_client, model=embedding_model)
        return cls(
            llm_factory(
                model, client=llm_client, temperature=0, max_tokens=max_tokens
            ),
            embeddings,
        )

    async def score(
        self, *, user_input: str, response: str, reference: str,
        retrieved_contexts: list[str],
    ) -> tuple[dict[str, float | None], list[str]]:
        kwargs = {
            "faithfulness": dict(user_input=user_input, response=response, retrieved_contexts=retrieved_contexts),
            "answer_relevancy": dict(user_input=user_input, response=response),
            "context_precision": dict(user_input=user_input, reference=reference, retrieved_contexts=retrieved_contexts),
            "context_recall": dict(user_input=user_input, reference=reference, retrieved_contexts=retrieved_contexts),
            "answer_correctness": dict(user_input=user_input, response=response, reference=reference),
        }
        scores: dict[str, float | None] = {}
        errors: list[str] = []
        for name, metric in self.metrics.items():
            try:
                result = await metric.ascore(**kwargs[name])
                scores[name] = float(result.value)
            except Exception as exc:  # 单指标失败不能伪造 0 或丢弃整题
                scores[name] = None
                errors.append(f"{name}: {type(exc).__name__}: {exc}")
        return scores, errors
