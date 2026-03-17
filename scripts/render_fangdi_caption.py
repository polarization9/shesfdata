#!/usr/bin/env python3
import argparse
import csv
import json
from pathlib import Path


def load_csv_rows(path):
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("insights_json")
    parser.add_argument("plate_metrics_csv")
    parser.add_argument("district_metrics_csv")
    parser.add_argument("headline_md")
    parser.add_argument("caption_md")
    args = parser.parse_args()

    insights = json.loads(Path(args.insights_json).read_text(encoding="utf-8"))
    plate_rows = load_csv_rows(args.plate_metrics_csv)
    district_rows = load_csv_rows(args.district_metrics_csv)

    date = insights.get("summary", {}).get("date", "")
    city_total = to_int(insights.get("summary", {}).get("city_total_count", 0))
    history_mode = insights.get("summary", {}).get("history_mode", "day1_absolute_only")

    top_district = max(district_rows, key=lambda row: to_int(row["total_count"])) if district_rows else None
    top_stale_plate = max(plate_rows, key=lambda row: to_float(row["stale_ratio"])) if plate_rows else None
    top_fresh_plate = max(plate_rows, key=lambda row: to_float(row["fresh_ratio"])) if plate_rows else None

    headlines = [
        f"{date}上海二手房挂牌观察：库存和结构先看这 4 张图",
        f"{date}上海二手房挂牌盘点：哪个区库存最多，哪些板块长挂压力更大？",
        f"{date}上海二手房供给观察：首日先看挂牌总量和库存年龄结构",
    ]

    if history_mode != "day1_absolute_only":
        headlines.insert(0, f"{date}上海二手房挂牌异动：哪些区和板块今天变化最大？")

    caption_lines = [
        f"# {date} 上海二手房挂牌供给观察",
        "",
        f"今天先看挂牌供给和库存年龄结构。当前全市抓到的挂牌总量约为 {city_total:,} 套，这是一套挂牌库存观察口径，不是成交数据口径。",
        "",
    ]

    if top_district:
        caption_lines.append(
            f"- 当前挂牌总量最高的区是 {top_district['district']}，总量约 {to_int(top_district['total_count']):,} 套。"
        )
    if top_stale_plate:
        caption_lines.append(
            f"- 长挂压力最重的板块之一是 {top_stale_plate['district']} / {top_stale_plate['plate']}，3个月以上挂牌占比约 {to_float(top_stale_plate['stale_ratio']) * 100:.1f}%。"
        )
    if top_fresh_plate:
        caption_lines.append(
            f"- 新挂牌相对活跃的板块之一是 {top_fresh_plate['district']} / {top_fresh_plate['plate']}，15天挂牌占比约 {to_float(top_fresh_plate['fresh_ratio']) * 100:.1f}%。"
        )

    caption_lines.extend(
        [
            "",
            "这套数据更适合回答：",
            "- 哪些区当前供给盘子更大",
            "- 哪些板块库存偏老、长挂压力更重",
            "- 哪些板块短期新增挂牌更活跃",
            "",
            "等后面历史数据累积起来后，再继续看日变化、周变化和异常波动。",
            "",
            "说明：",
            "- 数据来自 Fangdi 查询页挂牌供给统计",
            "- 当前只讨论挂牌供给，不直接推导成交价和成交热度",
        ]
    )

    headline_path = Path(args.headline_md)
    headline_path.parent.mkdir(parents=True, exist_ok=True)
    headline_path.write_text("\n".join(f"- {line}" for line in headlines) + "\n", encoding="utf-8")

    caption_path = Path(args.caption_md)
    caption_path.parent.mkdir(parents=True, exist_ok=True)
    caption_path.write_text("\n".join(caption_lines) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "headline_md": str(headline_path),
                "caption_md": str(caption_path),
                "history_mode": history_mode,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
