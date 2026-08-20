"""评估批次编排：真实查询、Ragas、ID 指标与增量报告。"""

from __future__ import annotations

import asyncio
import hashlib
import importlib.metadata
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from app.rag.query import config as query_config

from .collector import collect_query
from .dataset import DEFAULT_DATASET_PATH, GoldCase, load_gold_cases
from .metrics import RagasEvaluator, abstention_correct, compute_layer_metrics
from .report import build_summary, json_text, write_results_atomic, write_summary


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_commit() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, capture_output=True,
            text=True, timeout=5,
        ).stdout.strip() or None
    except Exception:
        return None


def _config_snapshot(dataset_path: Path, split: str, statuses: list[str], web: bool) -> dict[str, Any]:
    from dotenv import load_dotenv
    load_dotenv()
    prompt_path = Path(__file__).with_name("prompt_coding")
    return {
        "git_commit": _git_commit(), "dataset_path": str(dataset_path),
        "dataset_sha256": _sha256(dataset_path), "split": split,
        "review_statuses": statuses,
        "ragas_version": importlib.metadata.version("ragas"),
        "answer_model": __import__("os").getenv("LLM_DEFAULT_MODEL", ""),
        "evaluator_model": __import__("os").getenv("RAGAS_EVALUATOR_MODEL", ""),
        "evaluator_max_tokens": __import__("os").getenv("RAGAS_EVALUATOR_MAX_TOKENS", "4096"),
        "embedding_model": __import__("os").getenv("RAGAS_EMBEDDING_MODEL", ""),
        "embedding_provider": __import__("os").getenv("RAGAS_EMBEDDING_PROVIDER", "openai"),
        "prompt_sha256": _sha256(prompt_path) if prompt_path.exists() else None,
        "search_top_k": query_config.SEARCH_TOP_K, "rrf_k": query_config.RRF_K,
        "rrf_top_k": query_config.RRF_TOP_K,
        "rerank_min_top_k": query_config.RERANK_MIN_TOPK,
        "rerank_max_top_k": query_config.RERANK_MAX_TOPK,
        "web_enabled": web, "created_at": _now(),
    }


def run_evaluation(
    *, dataset_path: str | Path = DEFAULT_DATASET_PATH, split: str = "dev",
    review_statuses: Iterable[str] = ("draft", "reviewed"),
    output_root: str | Path | None = None, web_enabled: bool = False,
    evaluator: Any | None = None, graph_app: Any | None = None,
    skip_ragas: bool = False, limit: int | None = None,
) -> Path:
    """运行一个评估批次并返回本次输出目录。"""
    dataset_path = Path(dataset_path).expanduser().resolve()
    statuses = list(review_statuses)
    cases = load_gold_cases(dataset_path, split=split, review_statuses=statuses)
    if limit is not None:
        if limit <= 0:
            raise ValueError("limit 必须大于 0")
        cases = cases[:limit]
    run_id = datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
    root = Path(output_root) if output_root else Path(__file__).with_name("runs")
    run_dir = root.expanduser().resolve() / run_id
    results_path = run_dir / "run_results.csv"
    snapshot = _config_snapshot(dataset_path, split, statuses, web_enabled)
    if evaluator is None and not skip_ragas:
        evaluator = RagasEvaluator.from_env()
    rows: list[dict[str, Any]] = []
    started_at = _now()
    for case in cases:
        started = time.perf_counter()
        row: dict[str, Any] = {
            "run_id": run_id, "case_id": case.case_id, "response": "",
            "retrieved_contexts_json": "[]", "layer_results_json": "{}",
            "faithfulness": None, "answer_relevancy": None,
            "context_precision": None, "context_recall": None,
            "answer_correctness": None, "id_metrics_json": "{}",
            "error_message": "", "config_snapshot_json": json_text(snapshot),
        }
        try:
            trace = collect_query(
                case, run_id=run_id, graph_app=graph_app, web_enabled=web_enabled
            )
            id_metrics = compute_layer_metrics(case, trace.layer_ids)
            row.update(
                response=trace.response,
                retrieved_contexts_json=json_text(list(trace.retrieved_contexts)),
                layer_results_json=json_text(trace.layer_ids),
                id_metrics_json=json_text(id_metrics), _id_metrics=id_metrics,
            )
            metric_errors: list[str] = []
            if evaluator is not None:
                scores, metric_errors = asyncio.run(evaluator.score(
                    user_input=case.user_input, response=trace.response,
                    reference=case.reference,
                    retrieved_contexts=list(trace.retrieved_contexts),
                ))
                row.update(scores)
            if metric_errors:
                row["error_message"] = " | ".join(metric_errors)
                row["_error_type"] = "ragas_metric_error"
            if not case.answerable:
                row["_abstention_correct"] = abstention_correct(trace.response)
        except Exception as exc:
            row["error_message"] = f"{type(exc).__name__}: {exc}"
            row["_error_type"] = type(exc).__name__
        row["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
        rows.append(row)
        write_results_atomic(results_path, rows)
    finished_at = _now()
    summary = build_summary(
        run_id=run_id, cases=cases, rows=rows, started_at=started_at,
        finished_at=finished_at,
        dataset={"path": str(dataset_path), "sha256": snapshot["dataset_sha256"]},
        filters={"split": split, "review_statuses": statuses},
    )
    write_summary(run_dir / "summary.json", summary)
    return run_dir
