#!/usr/bin/env python3
import argparse
import json
from collections import defaultdict
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("results_file", help="jsonl file produced by ocr_http_service append-result")
    parser.add_argument("output", help="where to write aggregated json")
    args = parser.parse_args()

    totals = defaultdict(dict)
    successes = 0
    failures = 0

    for line in Path(args.results_file).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if item.get("status") == "success":
            successes += 1
            key = f"{item['district']}|{item['plate']}"
            totals[key][item["listing_age"]] = item.get("count")
        else:
            failures += 1

    payload = {
        "successes": successes,
        "failures": failures,
        "items": [
            {
                "district": key.split("|", 1)[0],
                "plate": key.split("|", 1)[1],
                "counts": counts,
            }
            for key, counts in sorted(totals.items())
        ],
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output_path), "successes": successes, "failures": failures}, ensure_ascii=False))


if __name__ == "__main__":
    main()
