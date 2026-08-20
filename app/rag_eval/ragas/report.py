"""逐题结果的原子 CSV 落盘与批次 JSON 汇总。"""

from __future__ import annotations

import csv
import json
import math
import os
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .dataset import GoldCase

RESULT_COLUMNS = (
    "run_id", "case_id", "response", "retrieved_contexts_json",
    "layer_results_json", "faithfulness", "answer_relevancy",
    "context_precision", "context_recall", "answer_correctness",
    "id_metrics_json", "latency_ms", "error_message", "config_snapshot_json",
)
RAGAS_FIELDS = RESULT_COLUMNS[5:10]


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def write_results_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_COLUMNS, lineterminator="\r\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in RESULT_COLUMNS})
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _stats(values: Iterable[float | None]) -> dict[str, Any]:
    valid = [float(value) for value in values if value is not None]
    return {
        "valid_count": len(valid),
        "mean": statistics.fmean(valid) if valid else None,
        "median": statistics.median(valid) if valid else None,
        "p10": _percentile(valid, 0.10),
    }


def _score_value(row: dict[str, Any], field: str) -> float | None:
    value = row.get(field)
    return float(value) if isinstance(value, (int, float)) else None


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ragas = {field: _stats(_score_value(row, field) for row in rows) for field in RAGAS_FIELDS}
    id_metrics: dict[str, dict[str, Any]] = {}
    for layer in ("embedding", "hyde", "rrf", "rerank"):
        id_metrics[layer] = {}
        for field in ("id_precision", "id_recall", "must_hit_rate"):
            id_metrics[layer][field] = _stats(
                (row.get("_id_metrics") or {}).get(layer, {}).get(field) for row in rows
            )
    return {"sample_count": len(rows), "ragas": ragas, "id_metrics": id_metrics}


def build_summary(
    *, run_id: str, cases: list[GoldCase], rows: list[dict[str, Any]],
    started_at: str, finished_at: str, dataset: dict[str, Any], filters: dict[str, Any],
) -> dict[str, Any]:
    case_by_id = {case.case_id: case for case in cases}
    success = [row for row in rows if not row.get("error_message")]
    error_types = Counter(
        str(row.get("_error_type") or "unknown")
        for row in rows if row.get("error_message")
    )
    groups: dict[str, Any] = {}
    for split in ("dev", "test"):
        group = [row for row in rows if case_by_id[row["case_id"]].split == split]
        if group:
            groups[f"split:{split}"] = _aggregate(group)
    for answerable in (True, False):
        group = [row for row in rows if case_by_id[row["case_id"]].answerable == answerable]
        if group:
            groups[f"answerable:{str(answerable).lower()}"] = _aggregate(group)
    multi = [row for row in rows if case_by_id[row["case_id"]].is_multi_document]
    unanswerable = [row for row in rows if not case_by_id[row["case_id"]].answerable]
    abstentions = [row.get("_abstention_correct") for row in unanswerable]
    return {
        "run_id": run_id, "started_at": started_at, "finished_at": finished_at,
        "dataset": dataset, "filters": filters, "sample_count": len(rows),
        "success_count": len(success), "failure_count": len(rows) - len(success),
        "overall": _aggregate(rows), "groups": groups,
        "multi_document": {
            "sample_count": len(multi),
            "success_count": sum(not row.get("error_message") for row in multi),
            "metrics": _aggregate(multi),
        },
        "abstention_accuracy": {
            "valid_count": len(abstentions),
            "value": (sum(bool(value) for value in abstentions) / len(abstentions)) if abstentions else None,
        },
        "error_types": dict(error_types),
        "aggregation_policy": (
            "仅聚合非 null 数值；失败和不适用值不作为 0；P10 使用排序后的线性插值。"
        ),
    }


def write_summary(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
