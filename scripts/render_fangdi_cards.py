#!/usr/bin/env python3
import argparse
import csv
import json
import os
import tempfile
from pathlib import Path


try:
    os.environ.setdefault("MPLCONFIGDIR", tempfile.mkdtemp(prefix="fangdi-mpl-"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except Exception:  # pragma: no cover
    plt = None


FONT_CANDIDATES = [
    "Arial Unicode MS",
    "PingFang SC",
    "Hiragino Sans GB",
    "Noto Sans CJK SC",
    "WenQuanYi Zen Hei",
    "SimHei",
    "Microsoft YaHei",
    "DejaVu Sans",
]


def ensure_matplotlib():
    if plt is None:
        raise SystemExit(
            "matplotlib 未安装。请先执行: pip install matplotlib"
        )
    plt.rcParams["font.sans-serif"] = FONT_CANDIDATES
    plt.rcParams["axes.unicode_minus"] = False


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


def save_text_card(output_path, title, lines):
    fig, ax = plt.subplots(figsize=(10, 6), dpi=150)
    fig.patch.set_facecolor("#f7f4ef")
    ax.set_facecolor("#f7f4ef")
    ax.axis("off")
    ax.text(0.03, 0.92, title, fontsize=24, fontweight="bold", color="#1f2937")
    y = 0.82
    for line in lines:
        ax.text(0.05, y, line, fontsize=16, color="#374151")
        y -= 0.1
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)


def save_barh_card(output_path, title, labels, values, subtitle="", value_fmt=None, color="#d97706"):
    fig, ax = plt.subplots(figsize=(12, 7), dpi=150)
    fig.patch.set_facecolor("#f7f4ef")
    ax.set_facecolor("#f7f4ef")
    y = list(range(len(labels)))
    ax.barh(y, values, color=color)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=12)
    ax.invert_yaxis()
    ax.set_title(title, fontsize=22, fontweight="bold", loc="left", color="#1f2937", pad=18)
    if subtitle:
        ax.text(0.0, 1.02, subtitle, transform=ax.transAxes, fontsize=12, color="#6b7280")
    ax.grid(axis="x", linestyle="--", alpha=0.25)
    for spine in ax.spines.values():
        spine.set_visible(False)
    for idx, value in enumerate(values):
        label = value_fmt(value) if value_fmt else str(value)
        ax.text(value, idx, f"  {label}", va="center", fontsize=11, color="#111827")
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("plate_metrics_csv")
    parser.add_argument("district_metrics_csv")
    parser.add_argument("insights_json")
    parser.add_argument("output_dir")
    args = parser.parse_args()

    ensure_matplotlib()

    plate_rows = load_csv_rows(args.plate_metrics_csv)
    district_rows = load_csv_rows(args.district_metrics_csv)
    insights = json.loads(Path(args.insights_json).read_text(encoding="utf-8"))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    date = insights.get("summary", {}).get("date", "")
    city_total = to_int(insights.get("summary", {}).get("city_total_count", 0))
    district_count = to_int(insights.get("summary", {}).get("district_count", 0))
    plate_count = to_int(insights.get("summary", {}).get("plate_count", 0))

    top_districts = sorted(district_rows, key=lambda row: to_int(row["total_count"]), reverse=True)[:10]
    top_stale = sorted(
        [row for row in plate_rows if to_int(row["total_count"]) > 0],
        key=lambda row: to_float(row["stale_ratio"]),
        reverse=True,
    )[:12]
    top_fresh = sorted(
        [row for row in plate_rows if to_int(row["total_count"]) > 0],
        key=lambda row: to_float(row["fresh_ratio"]),
        reverse=True,
    )[:12]

    save_text_card(
        output_dir / "01-overview.png",
        f"{date} 上海二手房挂牌观察",
        [
            f"全市挂牌总量: {city_total:,}",
            f"覆盖区数: {district_count}",
            f"覆盖板块数: {plate_count}",
            f"说明: 当前口径是挂牌供给与库存年龄结构，不是成交数据。",
        ],
    )

    save_barh_card(
        output_dir / "02-district-ranking.png",
        "各区挂牌总量排名",
        [row["district"] for row in top_districts],
        [to_int(row["total_count"]) for row in top_districts],
        subtitle=f"{date} Fangdi 挂牌供给抓取结果",
        value_fmt=lambda value: f"{int(value):,}",
        color="#2563eb",
    )

    save_barh_card(
        output_dir / "03-stale-pressure.png",
        "长挂压力最高的板块",
        [f"{row['district']} / {row['plate']}" for row in top_stale],
        [to_float(row["stale_ratio"]) * 100 for row in top_stale],
        subtitle="按 3个月以上挂牌占比排序",
        value_fmt=lambda value: f"{value:.1f}%",
        color="#dc2626",
    )

    save_barh_card(
        output_dir / "04-fresh-activity.png",
        "新挂牌最活跃的板块",
        [f"{row['district']} / {row['plate']}" for row in top_fresh],
        [to_float(row["fresh_ratio"]) * 100 for row in top_fresh],
        subtitle="按 15天挂牌占比排序",
        value_fmt=lambda value: f"{value:.1f}%",
        color="#059669",
    )

    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "files": [
                    "01-overview.png",
                    "02-district-ranking.png",
                    "03-stale-pressure.png",
                    "04-fresh-activity.png",
                ],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
