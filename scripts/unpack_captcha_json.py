#!/usr/bin/env python3
import argparse
import base64
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("json_file", help="captcha json exported from browser")
    parser.add_argument(
        "--out-dir",
        default=None,
        help="directory to write png files into (defaults to sibling folder)",
    )
    args = parser.parse_args()

    json_path = Path(args.json_file)
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    items = payload.get("items", [])
    if not items:
        raise SystemExit("no items found in json")

    out_dir = Path(args.out_dir) if args.out_dir else json_path.with_suffix("")
    out_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for item in items:
        filename = item.get("filename") or f"captcha-{count+1:03d}.png"
        data_url = item.get("dataUrl", "")
        if "," not in data_url:
            continue
        _, b64 = data_url.split(",", 1)
        (out_dir / filename).write_bytes(base64.b64decode(b64))
        count += 1

    print(
        json.dumps(
            {
                "written": count,
                "out_dir": str(out_dir),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
