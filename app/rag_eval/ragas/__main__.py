"""Ragas 评估入口，支持模块运行和 IDE 直接运行本文件。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    # IDE 的“运行 Python 文件”不会建立包上下文，需要将仓库根目录加入搜索路径。
    repository_root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(repository_root))
    from app.rag_eval.ragas.dataset import DEFAULT_DATASET_PATH
    from app.rag_eval.ragas.runner import run_evaluation
else:
    from .dataset import DEFAULT_DATASET_PATH
    from .runner import run_evaluation


def main() -> None:
    parser = argparse.ArgumentParser(description="运行真实 RAG 离线评估")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET_PATH))
    parser.add_argument("--split", choices=("dev", "test", "all"), default="dev")
    parser.add_argument("--review-status", action="append", dest="statuses")
    parser.add_argument("--output-root")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--web", action="store_true", help="显式启用实时 Web 检索")
    parser.add_argument("--skip-ragas", action="store_true", help="只诊断真实检索和 ID 指标")
    args = parser.parse_args()
    run_dir = run_evaluation(
        dataset_path=args.dataset, split=args.split,
        review_statuses=args.statuses or ("draft", "reviewed"),
        output_root=args.output_root, web_enabled=args.web,
        skip_ragas=args.skip_ragas, limit=args.limit,
    )
    print(run_dir)


if __name__ == "__main__":
    main()
