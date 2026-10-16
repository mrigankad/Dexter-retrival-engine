"""
Run the offline evaluation harness against the configured knowledge backend.

    python scripts/run_eval.py --dataset ../evals/datasets/sample.json --top-k 8 [--judge] [--backend local]

Writes a JSON report to evals/reports/<timestamp>.json and prints a summary.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--judge", action="store_true", help="LLM-judged faithfulness/relevancy (needs NVIDIA_API_KEY)")
    parser.add_argument("--answer", action="store_true", help="Generate answers (needs NVIDIA_API_KEY)")
    parser.add_argument("--backend", default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    from src.evaluation import EvalHarness, load_dataset
    from src.infrastructure.database import init_db

    await init_db(seed_admin=False)
    dataset = load_dataset(args.dataset)
    report = await EvalHarness(backend=args.backend).run(dataset, top_k=args.top_k, judge=args.judge, answer=args.answer or args.judge)

    out = args.out or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(args.dataset))), "reports",
                                   datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report.model_dump(), f, indent=2, default=str)

    print(f"backend={report.backend} cases={report.cases} top_k={report.top_k}")
    print(f"hit_rate={report.hit_rate} mrr={report.mrr} context_recall={report.context_recall}")
    print(f"answer_substring_recall={report.answer_substring_recall} citation_rate={report.citation_rate} "
          f"faithfulness={report.faithfulness} relevancy={report.relevancy}")
    print(f"p50_retrieval_ms={report.p50_retrieval_ms} p95_retrieval_ms={report.p95_retrieval_ms}")
    for t, m in report.by_type.items():
        print(f"  {t:12s} cases={m['cases']} hit_rate={m['hit_rate']} mrr={m['mrr']}")
    for r in report.results:
        if r.error or not r.hit_at_k:
            print(f"  MISS {r.question[:70]!r} top={r.top_sources[:3]} err={r.error}")
    print(f"report: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
