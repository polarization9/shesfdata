#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


PREFERRED_AGE_BUCKETS = ["15天", "1个月", "3个月", "3个月以上"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("sample_config", help="existing fangdi config json to copy runner/api settings from")
    parser.add_argument("dimensions_export", help="exported dimensions json from browser")
    parser.add_argument("output", help="where to write the merged config json")
    args = parser.parse_args()

    sample = json.loads(Path(args.sample_config).read_text(encoding="utf-8"))
    exported = json.loads(Path(args.dimensions_export).read_text(encoding="utf-8"))

    exported_buckets = exported.get("listing_age_buckets", [])
    age_buckets = [bucket for bucket in PREFERRED_AGE_BUCKETS if bucket in exported_buckets]
    if not age_buckets:
        age_buckets = sample["dimensions"]["listing_age_buckets"]

    districts = []
    for district in exported.get("districts", []):
        plates = [item["name"] for item in district.get("plates", []) if item.get("name")]
        if not plates:
          continue
        districts.append(
            {
                "name": district["name"],
                "plates": plates,
            }
        )

    payload = {
        "api_base": sample["api_base"],
        "results_file": sample["results_file"],
        "runner": sample["runner"],
        "dimensions": {
            "districts": districts,
            "listing_age_buckets": age_buckets,
        },
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output_path),
                "district_count": len(districts),
                "task_count": len(districts) * len(age_buckets),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
