"""金标题库的 RFC 4180 读取、严格校验与过滤。"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

CSV_COLUMNS = (
    "case_id", "user_input", "reference", "gold_contexts_json",
    "must_hit_chunk_ids_json", "answerable", "split", "review_status", "notes",
)
GOLD_CONTEXT_FIELDS = {"chunk_id", "file_title", "section_title", "content"}
VALID_SPLITS = {"dev", "test"}
VALID_REVIEW_STATUSES = {"draft", "reviewed", "rejected"}
DEFAULT_DATASET_PATH = Path(__file__).with_name("rag_gold_questions.csv")


class DatasetValidationError(ValueError):
    """金标题库不满足固定数据契约。"""


@dataclass(frozen=True)
class GoldContext:
    chunk_id: str
    file_title: str
    section_title: str
    content: str


@dataclass(frozen=True)
class GoldCase:
    case_id: str
    user_input: str
    reference: str
    gold_contexts: tuple[GoldContext, ...]
    must_hit_chunk_ids: tuple[str, ...]
    answerable: bool
    split: str
    review_status: str
    notes: str
    row_number: int

    @property
    def gold_chunk_ids(self) -> tuple[str, ...]:
        return tuple(context.chunk_id for context in self.gold_contexts)

    @property
    def is_multi_document(self) -> bool:
        return self.notes == "多文档题"


def _error(row_number: int, case_id: str, field: str, reason: str) -> DatasetValidationError:
    return DatasetValidationError(
        f"row={row_number}, case_id={case_id or '<unknown>'}, field={field}: {reason}"
    )


def _non_empty(value: object, row: int, case_id: str, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise _error(row, case_id, field, "必须为非空字符串")
    return text


def _unique_ids(values: Iterable[object], row: int, case_id: str, field: str) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        item = _non_empty(value, row, case_id, field)
        if item not in result:
            result.append(item)
    return tuple(result)


def _json_array(raw: str, row: int, case_id: str, field: str) -> list:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise _error(row, case_id, field, f"非法 JSON: {exc.msg}") from exc
    if not isinstance(value, list):
        raise _error(row, case_id, field, "必须是 JSON 数组")
    return value


def _parse_bool(raw: str, row: int, case_id: str) -> bool:
    value = str(raw or "").strip().lower()
    if value not in {"true", "false"}:
        raise _error(row, case_id, "answerable", "只接受 true 或 false")
    return value == "true"


def _parse_row(raw: dict[str, str], row: int) -> GoldCase:
    case_id = _non_empty(raw.get("case_id"), row, "", "case_id")
    user_input = _non_empty(raw.get("user_input"), row, case_id, "user_input")
    reference = str(raw.get("reference") or "").strip()
    answerable = _parse_bool(raw.get("answerable", ""), row, case_id)
    split = _non_empty(raw.get("split"), row, case_id, "split")
    if split not in VALID_SPLITS:
        raise _error(row, case_id, "split", "只能是 dev 或 test")
    status = _non_empty(raw.get("review_status"), row, case_id, "review_status")
    if status not in VALID_REVIEW_STATUSES:
        raise _error(row, case_id, "review_status", "只能是 draft、reviewed 或 rejected")

    context_values = _json_array(raw["gold_contexts_json"], row, case_id, "gold_contexts_json")
    contexts: list[GoldContext] = []
    seen_context_ids: set[str] = set()
    for index, value in enumerate(context_values):
        field = f"gold_contexts_json[{index}]"
        if not isinstance(value, dict) or set(value) != GOLD_CONTEXT_FIELDS:
            raise _error(row, case_id, field, f"字段必须恰好为 {sorted(GOLD_CONTEXT_FIELDS)}")
        context = GoldContext(**{
            name: _non_empty(value[name], row, case_id, f"{field}.{name}")
            for name in GOLD_CONTEXT_FIELDS
        })
        if context.chunk_id not in seen_context_ids:
            contexts.append(context)
            seen_context_ids.add(context.chunk_id)

    must_values = _json_array(
        raw["must_hit_chunk_ids_json"], row, case_id, "must_hit_chunk_ids_json"
    )
    must_ids = _unique_ids(must_values, row, case_id, "must_hit_chunk_ids_json")
    gold_ids = {context.chunk_id for context in contexts}
    if not set(must_ids).issubset(gold_ids):
        raise _error(row, case_id, "must_hit_chunk_ids_json", "必须是 gold chunk ID 的子集")
    if answerable and (not reference or not contexts):
        raise _error(row, case_id, "reference/gold_contexts_json", "可回答题必须有答案和证据")
    if not answerable and (contexts or must_ids):
        raise _error(row, case_id, "gold_contexts_json/must_hit_chunk_ids_json", "不可回答题必须为空数组")
    if not answerable and not reference:
        raise _error(row, case_id, "reference", "不可回答题必须说明资料不足或需补充信息")
    return GoldCase(
        case_id=case_id, user_input=user_input, reference=reference,
        gold_contexts=tuple(contexts), must_hit_chunk_ids=must_ids,
        answerable=answerable, split=split, review_status=status,
        notes=str(raw.get("notes") or "").strip(), row_number=row,
    )


def load_gold_cases(
    path: str | Path = DEFAULT_DATASET_PATH,
    *,
    split: str = "dev",
    review_statuses: Iterable[str] = ("draft", "reviewed"),
) -> list[GoldCase]:
    """校验整个文件后，按 split 和审核状态返回有序样本。"""
    dataset_path = Path(path).expanduser().resolve()
    if split not in {"dev", "test", "all"}:
        raise ValueError("split 只能是 dev、test 或 all")
    statuses = set(review_statuses)
    if "all" in statuses:
        statuses = set(VALID_REVIEW_STATUSES)
    invalid = statuses - VALID_REVIEW_STATUSES
    if invalid:
        raise ValueError(f"非法 review_status: {sorted(invalid)}")
    with dataset_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != CSV_COLUMNS:
            raise DatasetValidationError(
                f"row=1, case_id=<unknown>, field=header: 应为 {CSV_COLUMNS}，实际为 {tuple(reader.fieldnames or ())}"
            )
        cases: list[GoldCase] = []
        for index, row in enumerate(reader, start=2):
            if None in row:
                raise _error(index, str(row.get("case_id") or ""), "row", "字段数量超过固定 9 列")
            missing = [name for name in CSV_COLUMNS if row.get(name) is None]
            if missing:
                raise _error(index, str(row.get("case_id") or ""), "row", f"缺少字段值: {missing}")
            cases.append(_parse_row(row, index))
    seen: set[str] = set()
    for case in cases:
        if case.case_id in seen:
            raise _error(case.row_number, case.case_id, "case_id", "全局重复")
        seen.add(case.case_id)
    selected = [
        case for case in cases
        if (split == "all" or case.split == split) and case.review_status in statuses
    ]
    if not selected:
        raise DatasetValidationError(
            f"row=0, case_id=<unknown>, field=filters: split={split}, review_statuses={sorted(statuses)} 过滤后无样本"
        )
    return selected
