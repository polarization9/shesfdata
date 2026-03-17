#!/usr/bin/env python3
import argparse
import csv
import json
from datetime import date, datetime, timedelta
from pathlib import Path


PLATE_GLOB = "fangdi_plate_metrics_*.csv"
DISTRICT_GLOB = "fangdi_district_metrics_*.csv"


def load_csv_rows(path):
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows, fieldnames):
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_date(value):
    return datetime.strptime(value, "%Y-%m-%d").date()


def row_date(rows, fallback_path):
    if rows and rows[0].get("date"):
        return rows[0]["date"]
    name = Path(fallback_path).stem
    parts = name.split("_")
    for part in reversed(parts):
        try:
            parse_date(part)
            return part
        except Exception:
            continue
    raise ValueError(f"cannot infer date from {fallback_path}")


def to_int(value):
    try:
        return int(value)
    except Exception:
        return 0


def to_float(value):
    try:
        return float(value)
    except Exception:
        return 0.0


def pct_delta(current, previous):
    if previous in ("", None):
        return ""
    previous = to_int(previous)
    if previous == 0:
        return ""
    return round((to_int(current) - previous) / previous, 6)


def choose_compare_dates(current_date, available_dates):
    prev_dates = sorted(d for d in available_dates if d < current_date)
    compare_1d = prev_dates[-1] if prev_dates else None

    target_7d = current_date - timedelta(days=7)
    candidates_7d = [d for d in prev_dates if d <= target_7d]
    compare_7d = candidates_7d[-1] if candidates_7d else None
    return compare_1d, compare_7d


def scan_history(directory, glob_pattern, current_path):
    history = {}
    for path in sorted(Path(directory).glob(glob_pattern)):
        if path.resolve() == Path(current_path).resolve():
            continue
        rows = load_csv_rows(path)
        if not rows:
            continue
        file_date = row_date(rows, path)
        history[parse_date(file_date)] = rows
    return history


def index_plate_rows(rows):
    return {(row["district"], row["plate"]): row for row in rows}


def index_district_rows(rows):
    return {row["district"]: row for row in rows}


def enrich_plate_rows(current_rows, compare_1d_rows=None, compare_7d_rows=None, compare_1d_date=None, compare_7d_date=None):
    index_1d = index_plate_rows(compare_1d_rows or [])
    index_7d = index_plate_rows(compare_7d_rows or [])

    enriched = []
    for row in current_rows:
        key = (row["district"], row["plate"])
        prev_1d = index_1d.get(key)
        prev_7d = index_7d.get(key)

        current_total = to_int(row["total_count"])
        current_fresh = to_float(row["fresh_ratio"])
        current_stale = to_float(row["stale_ratio"])

        prev_1d_total = to_int(prev_1d["total_count"]) if prev_1d else ""
        prev_7d_total = to_int(prev_7d["total_count"]) if prev_7d else ""

        item = dict(row)
        item.update(
            {
                "compare_1d_date": compare_1d_date.isoformat() if compare_1d_date and prev_1d else "",
                "prev_total_count_1d": prev_1d_total,
                "delta_1d": current_total - prev_1d_total if prev_1d else "",
                "delta_1d_pct": pct_delta(current_total, prev_1d_total) if prev_1d else "",
                "fresh_ratio_delta_1d": round(current_fresh - to_float(prev_1d["fresh_ratio"]), 6) if prev_1d else "",
                "stale_ratio_delta_1d": round(current_stale - to_float(prev_1d["stale_ratio"]), 6) if prev_1d else "",
                "compare_7d_date": compare_7d_date.isoformat() if compare_7d_date and prev_7d else "",
                "prev_total_count_7d": prev_7d_total,
                "delta_7d": current_total - prev_7d_total if prev_7d else "",
                "delta_7d_pct": pct_delta(current_total, prev_7d_total) if prev_7d else "",
                "fresh_ratio_delta_7d": round(current_fresh - to_float(prev_7d["fresh_ratio"]), 6) if prev_7d else "",
                "stale_ratio_delta_7d": round(current_stale - to_float(prev_7d["stale_ratio"]), 6) if prev_7d else "",
            }
        )
        enriched.append(item)
    return enriched


def enrich_district_rows(current_rows, compare_1d_rows=None, compare_7d_rows=None, compare_1d_date=None, compare_7d_date=None):
    index_1d = index_district_rows(compare_1d_rows or [])
    index_7d = index_district_rows(compare_7d_rows or [])

    enriched = []
    for row in current_rows:
        key = row["district"]
        prev_1d = index_1d.get(key)
        prev_7d = index_7d.get(key)

        current_total = to_int(row["total_count"])
        current_fresh = to_float(row["fresh_ratio"])
        current_stale = to_float(row["stale_ratio"])

        prev_1d_total = to_int(prev_1d["total_count"]) if prev_1d else ""
        prev_7d_total = to_int(prev_7d["total_count"]) if prev_7d else ""

        item = dict(row)
        item.update(
            {
                "compare_1d_date": compare_1d_date.isoformat() if compare_1d_date and prev_1d else "",
                "prev_total_count_1d": prev_1d_total,
                "delta_1d": current_total - prev_1d_total if prev_1d else "",
                "delta_1d_pct": pct_delta(current_total, prev_1d_total) if prev_1d else "",
                "fresh_ratio_delta_1d": round(current_fresh - to_float(prev_1d["fresh_ratio"]), 6) if prev_1d else "",
                "stale_ratio_delta_1d": round(current_stale - to_float(prev_1d["stale_ratio"]), 6) if prev_1d else "",
                "compare_7d_date": compare_7d_date.isoformat() if compare_7d_date and prev_7d else "",
                "prev_total_count_7d": prev_7d_total,
                "delta_7d": current_total - prev_7d_total if prev_7d else "",
                "delta_7d_pct": pct_delta(current_total, prev_7d_total) if prev_7d else "",
                "fresh_ratio_delta_7d": round(current_fresh - to_float(prev_7d["fresh_ratio"]), 6) if prev_7d else "",
                "stale_ratio_delta_7d": round(current_stale - to_float(prev_7d["stale_ratio"]), 6) if prev_7d else "",
            }
        )
        enriched.append(item)
    return enriched


def build_summary(current_date, available_dates, compare_1d_date, compare_7d_date, plate_rows, district_rows):
    summary = {
        "current_date": current_date.isoformat(),
        "available_history_dates": [d.isoformat() for d in sorted(available_dates)],
        "compare_1d_date": compare_1d_date.isoformat() if compare_1d_date else "",
        "compare_7d_date": compare_7d_date.isoformat() if compare_7d_date else "",
    }

    if compare_1d_date:
        summary["top_plate_delta_1d"] = sorted(
            [row for row in plate_rows if row.get("delta_1d") != ""],
            key=lambda row: to_int(row["delta_1d"]),
            reverse=True,
        )[:15]
        summary["top_district_delta_1d"] = sorted(
            [row for row in district_rows if row.get("delta_1d") != ""],
            key=lambda row: to_int(row["delta_1d"]),
            reverse=True,
        )[:10]
        summary["top_plate_stale_ratio_delta_1d"] = sorted(
            [row for row in plate_rows if row.get("stale_ratio_delta_1d") != ""],
            key=lambda row: to_float(row["stale_ratio_delta_1d"]),
            reverse=True,
        )[:15]

    if compare_7d_date:
        summary["top_plate_delta_7d"] = sorted(
            [row for row in plate_rows if row.get("delta_7d") != ""],
            key=lambda row: to_int(row["delta_7d"]),
            reverse=True,
        )[:15]
        summary["top_district_delta_7d"] = sorted(
            [row for row in district_rows if row.get("delta_7d") != ""],
            key=lambda row: to_int(row["delta_7d"]),
            reverse=True,
        )[:10]
        summary["top_plate_stale_ratio_delta_7d"] = sorted(
            [row for row in plate_rows if row.get("stale_ratio_delta_7d") != ""],
            key=lambda row: to_float(row["stale_ratio_delta_7d"]),
            reverse=True,
        )[:15]

    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("current_plate_metrics_csv")
    parser.add_argument("current_district_metrics_csv")
    parser.add_argument("output_plate_history_csv")
    parser.add_argument("output_district_history_csv")
    parser.add_argument("output_history_json")
    parser.add_argument("--plate-history-dir", help="directory containing historical plate metrics csv files")
    parser.add_argument("--district-history-dir", help="directory containing historical district metrics csv files")
    args = parser.parse_args()

    current_plate_rows = load_csv_rows(args.current_plate_metrics_csv)
    current_district_rows = load_csv_rows(args.current_district_metrics_csv)
    if not current_plate_rows or not current_district_rows:
        raise SystemExit("当前指标文件为空，无法做历史对比")

    current_date = parse_date(row_date(current_plate_rows, args.current_plate_metrics_csv))

    plate_history_dir = args.plate_history_dir or str(Path(args.current_plate_metrics_csv).parent)
    district_history_dir = args.district_history_dir or str(Path(args.current_district_metrics_csv).parent)

    plate_history = scan_history(plate_history_dir, PLATE_GLOB, args.current_plate_metrics_csv)
    district_history = scan_history(district_history_dir, DISTRICT_GLOB, args.current_district_metrics_csv)

    available_dates = sorted(set(plate_history.keys()) & set(district_history.keys()))
    compare_1d_date, compare_7d_date = choose_compare_dates(current_date, available_dates)

    compare_1d_plate_rows = plate_history.get(compare_1d_date, [])
    compare_1d_district_rows = district_history.get(compare_1d_date, [])
    compare_7d_plate_rows = plate_history.get(compare_7d_date, [])
    compare_7d_district_rows = district_history.get(compare_7d_date, [])

    enriched_plate_rows = enrich_plate_rows(
        current_plate_rows,
        compare_1d_plate_rows,
        compare_7d_plate_rows,
        compare_1d_date,
        compare_7d_date,
    )
    enriched_district_rows = enrich_district_rows(
        current_district_rows,
        compare_1d_district_rows,
        compare_7d_district_rows,
        compare_1d_date,
        compare_7d_date,
    )

    plate_fields = list(enriched_plate_rows[0].keys()) if enriched_plate_rows else []
    district_fields = list(enriched_district_rows[0].keys()) if enriched_district_rows else []
    write_csv(args.output_plate_history_csv, enriched_plate_rows, plate_fields)
    write_csv(args.output_district_history_csv, enriched_district_rows, district_fields)

    summary = build_summary(
        current_date,
        available_dates,
        compare_1d_date,
        compare_7d_date,
        enriched_plate_rows,
        enriched_district_rows,
    )
    summary_path = Path(args.output_history_json)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "output_plate_history_csv": args.output_plate_history_csv,
                "output_district_history_csv": args.output_district_history_csv,
                "output_history_json": args.output_history_json,
                "compare_1d_date": compare_1d_date.isoformat() if compare_1d_date else "",
                "compare_7d_date": compare_7d_date.isoformat() if compare_7d_date else "",
                "history_dates_found": len(available_dates),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
