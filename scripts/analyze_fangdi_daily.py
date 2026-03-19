#!/usr/bin/env python3
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


AGE_BUCKETS = ["15天", "1个月", "3个月", "3个月以上"]


def load_csv_rows(path):
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def to_int(value):
    try:
        return int(value)
    except Exception:
        return 0


def safe_ratio(numerator, denominator):
    if not denominator:
        return 0.0
    return round(numerator / denominator, 6)


def index_previous(rows):
    plate_index = {}
    district_index = {}

    for row in rows:
        key = (row["district"], row["plate"])
        plate_index[key] = row
    for row in rows:
        key = row["district"]
        district_index[key] = row

    return plate_index, district_index


def build_plate_metrics(rows):
    grouped = defaultdict(lambda: defaultdict(int))
    run_date = rows[0]["date"] if rows else ""

    for row in rows:
        key = (row["district"], row["plate"])
        grouped[key][row["listing_age"]] = to_int(row["count"])

    plate_rows = []
    for (district, plate), counts in sorted(grouped.items()):
        count_15d = counts.get("15天", 0)
        count_1m = counts.get("1个月", 0)
        count_3m = counts.get("3个月", 0)
        count_3m_plus = counts.get("3个月以上", 0)
        total = count_15d + count_1m + count_3m + count_3m_plus
        plate_rows.append(
            {
                "date": run_date,
                "district": district,
                "plate": plate,
                "count_15d": count_15d,
                "count_1m": count_1m,
                "count_3m": count_3m,
                "count_3m_plus": count_3m_plus,
                "total_count": total,
                "fresh_ratio": safe_ratio(count_15d, total),
                "mid_ratio": safe_ratio(count_1m + count_3m, total),
                "stale_ratio": safe_ratio(count_3m_plus, total),
            }
        )
    return plate_rows


def build_district_metrics(plate_rows):
    grouped = defaultdict(lambda: defaultdict(int))
    run_date = plate_rows[0]["date"] if plate_rows else ""

    for row in plate_rows:
        district = row["district"]
        grouped[district]["count_15d"] += row["count_15d"]
        grouped[district]["count_1m"] += row["count_1m"]
        grouped[district]["count_3m"] += row["count_3m"]
        grouped[district]["count_3m_plus"] += row["count_3m_plus"]
        grouped[district]["plate_count"] += 1

    district_rows = []
    for district, counts in sorted(grouped.items()):
        total = counts["count_15d"] + counts["count_1m"] + counts["count_3m"] + counts["count_3m_plus"]
        district_rows.append(
            {
                "date": run_date,
                "district": district,
                "count_15d": counts["count_15d"],
                "count_1m": counts["count_1m"],
                "count_3m": counts["count_3m"],
                "count_3m_plus": counts["count_3m_plus"],
                "total_count": total,
                "fresh_ratio": safe_ratio(counts["count_15d"], total),
                "stale_ratio": safe_ratio(counts["count_3m_plus"], total),
                "plate_count": counts["plate_count"],
            }
        )
    return district_rows


def apply_history(plate_rows, district_rows, previous_plate_rows=None, previous_district_rows=None):
    prev_plate_index = {}
    prev_district_index = {}
    if previous_plate_rows:
        prev_plate_index, _ = index_previous(previous_plate_rows)
    if previous_district_rows:
        _, prev_district_index = index_previous(previous_district_rows)

    for row in plate_rows:
        prev = prev_plate_index.get((row["district"], row["plate"]))
        if prev:
            prev_total = to_int(prev["total_count"])
            prev_fresh_ratio = float(prev["fresh_ratio"])
            prev_stale_ratio = float(prev["stale_ratio"])
            row["delta_1d"] = row["total_count"] - prev_total
            row["fresh_ratio_delta_1d"] = round(row["fresh_ratio"] - prev_fresh_ratio, 6)
            row["stale_ratio_delta_1d"] = round(row["stale_ratio"] - prev_stale_ratio, 6)
        else:
            row["delta_1d"] = ""
            row["fresh_ratio_delta_1d"] = ""
            row["stale_ratio_delta_1d"] = ""

    for row in district_rows:
        prev = prev_district_index.get(row["district"])
        if prev:
            prev_total = to_int(prev["total_count"])
            prev_fresh_ratio = float(prev["fresh_ratio"])
            prev_stale_ratio = float(prev["stale_ratio"])
            row["delta_1d"] = row["total_count"] - prev_total
            row["fresh_ratio_delta_1d"] = round(row["fresh_ratio"] - prev_fresh_ratio, 6)
            row["stale_ratio_delta_1d"] = round(row["stale_ratio"] - prev_stale_ratio, 6)
        else:
            row["delta_1d"] = ""
            row["fresh_ratio_delta_1d"] = ""
            row["stale_ratio_delta_1d"] = ""


def write_csv(path, rows, fieldnames):
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_insights(plate_rows, district_rows, has_history=False, market_stats=None):
    sorted_district_total = sorted(district_rows, key=lambda row: row["total_count"], reverse=True)
    sorted_district_stale = sorted(district_rows, key=lambda row: row["stale_ratio"], reverse=True)
    sorted_plate_total = sorted(plate_rows, key=lambda row: row["total_count"], reverse=True)
    sorted_plate_stale = sorted(
        [row for row in plate_rows if row["total_count"] > 0],
        key=lambda row: row["stale_ratio"],
        reverse=True,
    )
    sorted_plate_fresh = sorted(
        [row for row in plate_rows if row["total_count"] > 0],
        key=lambda row: row["fresh_ratio"],
        reverse=True,
    )

    insights = {
        "summary": {
            "date": district_rows[0]["date"] if district_rows else "",
            "district_count": len(district_rows),
            "plate_count": len(plate_rows),
            "city_total_count": sum(row["total_count"] for row in district_rows),
            "history_mode": "with_daily_comparison" if has_history else "day1_absolute_only",
            "market_stats": market_stats or {},
        },
        "top_districts_by_total": sorted_district_total[:10],
        "top_districts_by_stale_ratio": sorted_district_stale[:10],
        "top_plates_by_total": sorted_plate_total[:15],
        "top_plates_by_stale_ratio": sorted_plate_stale[:15],
        "top_plates_by_fresh_ratio": sorted_plate_fresh[:15],
        "notes": [
            "当前数据是挂牌供给数据，不是成交数据。",
            "首日版本重点适合做库存总量和库存年龄结构分析。",
        ],
    }

    if has_history:
        insights["top_districts_by_delta_1d"] = sorted(
            district_rows, key=lambda row: row.get("delta_1d", 0), reverse=True
        )[:10]
        insights["top_plates_by_delta_1d"] = sorted(
            plate_rows, key=lambda row: row.get("delta_1d", 0), reverse=True
        )[:15]
        insights["top_plates_by_stale_ratio_delta_1d"] = sorted(
            plate_rows, key=lambda row: row.get("stale_ratio_delta_1d", 0), reverse=True
        )[:15]
        insights["notes"].append("已加载上一日数据，可同时输出日变化指标。")

    return insights


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("daily_counts_csv", help="normalized daily counts csv")
    parser.add_argument("plate_metrics_csv", help="plate metrics csv output")
    parser.add_argument("district_metrics_csv", help="district metrics csv output")
    parser.add_argument("insights_json", help="insights json output")
    parser.add_argument("--previous-daily-counts", help="optional previous day normalized csv")
    parser.add_argument("--normalized-summary-json", help="optional normalized summary json with market stats")
    args = parser.parse_args()

    current_rows = [row for row in load_csv_rows(args.daily_counts_csv) if row.get("status") == "success"]
    plate_rows = build_plate_metrics(current_rows)
    district_rows = build_district_metrics(plate_rows)

    has_history = False
    if args.previous_daily_counts and Path(args.previous_daily_counts).exists():
        previous_rows = [row for row in load_csv_rows(args.previous_daily_counts) if row.get("status") == "success"]
        previous_plate_rows = build_plate_metrics(previous_rows)
        previous_district_rows = build_district_metrics(previous_plate_rows)
        apply_history(plate_rows, district_rows, previous_plate_rows, previous_district_rows)
        has_history = True
    else:
        apply_history(plate_rows, district_rows)

    plate_fields = [
        "date",
        "district",
        "plate",
        "count_15d",
        "count_1m",
        "count_3m",
        "count_3m_plus",
        "total_count",
        "fresh_ratio",
        "mid_ratio",
        "stale_ratio",
        "delta_1d",
        "fresh_ratio_delta_1d",
        "stale_ratio_delta_1d",
    ]
    district_fields = [
        "date",
        "district",
        "count_15d",
        "count_1m",
        "count_3m",
        "count_3m_plus",
        "total_count",
        "fresh_ratio",
        "stale_ratio",
        "plate_count",
        "delta_1d",
        "fresh_ratio_delta_1d",
        "stale_ratio_delta_1d",
    ]

    write_csv(args.plate_metrics_csv, plate_rows, plate_fields)
    write_csv(args.district_metrics_csv, district_rows, district_fields)

    market_stats = {}
    if args.normalized_summary_json and Path(args.normalized_summary_json).exists():
        market_stats = load_json(args.normalized_summary_json).get("market_stats", {}) or {}

    insights = build_insights(plate_rows, district_rows, has_history=has_history, market_stats=market_stats)
    insights_path = Path(args.insights_json)
    insights_path.parent.mkdir(parents=True, exist_ok=True)
    insights_path.write_text(json.dumps(insights, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "plate_metrics_csv": args.plate_metrics_csv,
                "district_metrics_csv": args.district_metrics_csv,
                "insights_json": args.insights_json,
                "plate_count": len(plate_rows),
                "district_count": len(district_rows),
                "history_mode": has_history,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
