"""当前金标题库驱动的离线评估单元测试。"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from app.rag_eval.ragas.collector import collect_query
from app.rag_eval.ragas.dataset import (
    CSV_COLUMNS, DEFAULT_DATASET_PATH, DatasetValidationError, load_gold_cases,
)
from app.rag_eval.ragas.metrics import LocalBgeM3Embeddings, compute_id_metric
from app.rag_eval.ragas.runner import run_evaluation


def _read_rows(path: Path = DEFAULT_DATASET_PATH) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_rows(path: Path, rows: list[dict[str, str]], columns=CSV_COLUMNS) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(rows)


class _FakeGraph:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.initial_states: list[dict] = []

    def invoke(self, state: dict) -> dict:
        self.initial_states.append(state)
        if self.fail:
            raise RuntimeError("query failed")
        docs = [
            {"chunk_id": "gold", "content": "第一段"},
            {"chunk_id": "other", "content": "第二段"},
        ]
        return {
            **state, "answer": "真实回答", "embedding_chunks": docs,
            "hyde_embedding_chunks": docs[:1], "rrf_chunks": docs,
            "reranked_docs": list(reversed(docs)),
        }


class RagasEvalTests(unittest.TestCase):
    def test_current_dataset_baseline_and_filters(self) -> None:
        all_cases = load_gold_cases(DEFAULT_DATASET_PATH, split="all")
        self.assertEqual(len(all_cases), 20)
        self.assertEqual(Counter(case.split for case in all_cases), {"dev": 16, "test": 4})
        self.assertEqual(sum(case.is_multi_document for case in all_cases), 2)
        self.assertEqual(len(load_gold_cases(DEFAULT_DATASET_PATH, split="dev")), 16)
        with self.assertRaisesRegex(DatasetValidationError, "过滤后无样本"):
            load_gold_cases(DEFAULT_DATASET_PATH, review_statuses=("reviewed",))

    def test_nested_json_and_chinese_round_trip(self) -> None:
        case = load_gold_cases(DEFAULT_DATASET_PATH, split="dev")[0]
        self.assertIn("1453", case.user_input)
        self.assertIn("深圳", case.gold_contexts[0].content)
        self.assertEqual(case.must_hit_chunk_ids, case.gold_chunk_ids)

    def test_invalid_rows_are_rejected(self) -> None:
        mutations = (
            (lambda rows: rows.__setitem__(1, {**rows[1], "case_id": rows[0]["case_id"]}), "case_id"),
            (lambda rows: rows[0].__setitem__("gold_contexts_json", "{"), "gold_contexts_json"),
            (lambda rows: rows[0].__setitem__("answerable", "yes"), "answerable"),
            (lambda rows: rows[0].__setitem__("split", "train"), "split"),
            (lambda rows: rows[0].__setitem__("review_status", "done"), "review_status"),
            (lambda rows: rows[0].__setitem__("must_hit_chunk_ids_json", '["missing"]'), "must_hit_chunk_ids_json"),
        )
        for mutation, field in mutations:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                rows = _read_rows()[:2]
                mutation(rows)
                path = Path(directory) / "bad.csv"
                _write_rows(path, rows)
                with self.assertRaisesRegex(DatasetValidationError, field):
                    load_gold_cases(path, split="all")

    def test_header_must_match_name_and_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad-header.csv"
            _write_rows(path, _read_rows()[:1], tuple(reversed(CSV_COLUMNS)))
            with self.assertRaisesRegex(DatasetValidationError, "field=header"):
                load_gold_cases(path, split="all")

    def test_extra_row_value_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "extra.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                handle.write(",".join(CSV_COLUMNS) + "\r\n")
                writer = csv.writer(handle, lineterminator="\r\n")
                row = _read_rows()[0]
                writer.writerow([row[name] for name in CSV_COLUMNS] + ["extra"])
            with self.assertRaisesRegex(DatasetValidationError, "超过固定 9 列"):
                load_gold_cases(path, split="all")

    def test_answerability_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            rows = _read_rows()[:1]
            rows[0]["answerable"] = "false"
            path = Path(directory) / "bad-answerability.csv"
            _write_rows(path, rows)
            with self.assertRaisesRegex(DatasetValidationError, "不可回答题必须为空数组"):
                load_gold_cases(path, split="all")

    def test_id_metrics_deduplicate_and_empty_semantics(self) -> None:
        metric = compute_id_metric(["a", "a", "x"], ["a", "b"], ["b"])
        self.assertEqual(metric.retrieved_ids, ["a", "x"])
        self.assertEqual(metric.hit_ids, ["a"])
        self.assertEqual(metric.id_precision, 0.5)
        self.assertEqual(metric.id_recall, 0.5)
        self.assertEqual(metric.must_hit_rate, 0.0)
        empty = compute_id_metric([], ["a"], [])
        self.assertIsNone(empty.id_precision)
        self.assertEqual(empty.id_recall, 0.0)
        self.assertIsNone(empty.must_hit_rate)

    def test_collector_preserves_order_and_eval_flags(self) -> None:
        case = load_gold_cases(DEFAULT_DATASET_PATH, split="dev")[0]
        graph = _FakeGraph()
        trace = collect_query(case, run_id="run", graph_app=graph)
        self.assertEqual(trace.retrieved_contexts, ("第二段", "第一段"))
        self.assertEqual(trace.layer_ids["rerank"], ["other", "gold"])
        self.assertTrue(graph.initial_states[0]["eval_disable_history"])
        self.assertTrue(graph.initial_states[0]["eval_disable_web"])

    def test_failed_query_still_writes_row_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = run_evaluation(
                dataset_path=DEFAULT_DATASET_PATH, split="dev", output_root=directory,
                graph_app=_FakeGraph(fail=True), skip_ragas=True, limit=1,
            )
            with (run_dir / "run_results.csv").open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(len(rows), 1)
            self.assertIn("query failed", rows[0]["error_message"])
            self.assertEqual(summary["sample_count"], 1)
            self.assertEqual(summary["failure_count"], 1)
            self.assertEqual(summary["overall"]["ragas"]["faithfulness"]["valid_count"], 0)

    def test_production_state_defaults_keep_side_effects_enabled(self) -> None:
        from app.process.query.agent.state import create_query_default_state
        state = create_query_default_state()
        self.assertFalse(state["eval_disable_history"])
        self.assertFalse(state["eval_disable_web"])

    def test_local_bge_m3_ragas_adapter(self) -> None:
        from unittest.mock import patch

        adapter = LocalBgeM3Embeddings()
        with patch(
            "app.shared.model.embedding_utils.generate_embeddings",
            return_value={"dense": [[1.0, 2.0], [3.0, 4.0]], "sparse": []},
        ) as generate:
            self.assertEqual(adapter.embed_texts(["甲", "乙"]), [[1.0, 2.0], [3.0, 4.0]])
            generate.assert_called_once_with(["甲", "乙"])

    def test_cli_supports_direct_script_execution(self) -> None:
        main_path = Path(__file__).parents[1] / "app" / "rag_eval" / "ragas" / "__main__.py"
        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.run(
                [sys.executable, str(main_path), "--help"],
                cwd=directory, capture_output=True, text=True, timeout=30,
                check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--split", completed.stdout)


if __name__ == "__main__":
    unittest.main()
