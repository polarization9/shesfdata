#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def load_labels(labels_path: Path):
    items = json.loads(labels_path.read_text())
    return {item["file"]: item["truth"].strip().upper() for item in items if item.get("truth")}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("results", help="ocr-results.json path")
    parser.add_argument("labels", help="captcha-labels.json path")
    args = parser.parse_args()

    results = json.loads(Path(args.results).read_text())
    truths = load_labels(Path(args.labels))

    rows = []
    for item in results:
        file_name = Path(item["file"]).name
        truth = truths.get(file_name)
        if not truth:
            continue
        raw_best = item["candidates"][0]["normalized"] if item.get("candidates") else ""
        reranked_best = item.get("best", "")
        grouped = [candidate["normalized"] for candidate in item.get("grouped_candidates", [])]
        candidate_set = {candidate["normalized"] for candidate in item.get("candidates", [])}
        rows.append(
            {
                "file": file_name,
                "truth": truth,
                "raw_best": raw_best,
                "reranked_best": reranked_best,
                "in_candidates": truth in candidate_set,
                "raw_hit": truth == raw_best,
                "reranked_hit": truth == reranked_best,
                "grouped": grouped,
            }
        )

    total = len(rows)
    if not total:
        raise SystemExit("no overlapping labels found")

    raw_hit = sum(row["raw_hit"] for row in rows)
    reranked_hit = sum(row["reranked_hit"] for row in rows)
    recall = sum(row["in_candidates"] for row in rows)
    improved = [row for row in rows if (not row["raw_hit"]) and row["reranked_hit"]]
    still_wrong = [row for row in rows if not row["reranked_hit"]]

    summary = {
        "labeled_samples": total,
        "raw_top1_accuracy": raw_hit / total,
        "reranked_top1_accuracy": reranked_hit / total,
        "candidate_recall": recall / total,
        "improved_by_reranker": len(improved),
        "still_wrong_after_rerank": len(still_wrong),
    }

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("\nImproved samples:")
    for row in improved:
        print(f"- {row['file']}: raw={row['raw_best']} -> reranked={row['reranked_best']} truth={row['truth']}")

    print("\nStill wrong:")
    for row in still_wrong:
        print(f"- {row['file']}: reranked={row['reranked_best']} truth={row['truth']} grouped={row['grouped'][:4]}")


if __name__ == "__main__":
    main()
