#!/usr/bin/env python3
import argparse
import json
from datetime import datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("config", help="fangdi poc config json")
    parser.add_argument("output", help="where to write the query plan json")
    args = parser.parse_args()

    config = json.loads(Path(args.config).read_text())
    age_buckets = config["dimensions"]["listing_age_buckets"]

    items = []
    for district in config["dimensions"]["districts"]:
        district_name = district["name"]
        for plate in district["plates"]:
            for listing_age in age_buckets:
                items.append(
                    {
                        "task_id": f"{district_name}__{plate}__{listing_age}",
                        "district": district_name,
                        "plate": plate,
                        "listing_age": listing_age,
                    }
                )

    payload = {
        "generated_at": datetime.now().isoformat(),
        "count": len(items),
        "items": items,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"count": len(items), "output": str(output_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
