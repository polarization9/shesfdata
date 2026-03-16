#!/usr/bin/env python3
import argparse
import html
import json
import shutil
from pathlib import Path

import cv2
from fangdi_ocr_lib import ocr_array


def ocr_image(image_path: Path):
    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError(f"failed to read {image_path}")
    return {"file": str(image_path), **ocr_array(image)}


def render_html(items, output_path: Path):
    rows = []
    for item in items:
        image_name = Path(item["file"]).name
        grouped = ", ".join(
            f"{candidate['normalized'] or '[blank]'} x{candidate['count']}"
            for candidate in item["grouped_candidates"]
        )
        rows.append(
            f"""
            <tr data-file="{html.escape(image_name)}" data-best="{html.escape(item["best"])}">
              <td><img src="{html.escape(image_name)}" style="height:48px;border:1px solid #ddd;"></td>
              <td>{html.escape(item["best"])}</td>
              <td>{html.escape(", ".join(c["normalized"] for c in item["candidates"]))}</td>
              <td>{html.escape(grouped)}</td>
              <td class="truth" contenteditable="true" style="background:#fffbe6;"></td>
            </tr>
            """
        )

    page = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>fangdi captcha review</title>
  <style>
    body {{ font-family: sans-serif; padding: 24px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    td, th {{ border: 1px solid #ddd; padding: 8px; vertical-align: middle; }}
    th {{ background: #f7f7f7; }}
    .toolbar {{ display:flex; gap:12px; align-items:center; margin-bottom:16px; }}
    button {{ padding:8px 12px; cursor:pointer; }}
  </style>
</head>
<body>
  <h1>fangdi captcha OCR review</h1>
  <div class="toolbar">
    <button id="export">导出标注 JSON</button>
    <span>最后一列填写真实验证码，点按钮即可下载 <code>captcha-labels.json</code>。</span>
  </div>
  <table>
    <thead>
      <tr><th>图片</th><th>最佳识别</th><th>候选</th><th>聚合票数</th><th>人工标注</th></tr>
    </thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>
  <script>
    document.getElementById("export").addEventListener("click", () => {{
      const rows = [...document.querySelectorAll("tbody tr")];
      const items = rows.map((row) => {{
        const truth = row.querySelector(".truth").textContent.trim().toUpperCase();
        return {{
          file: row.dataset.file,
          best: row.dataset.best,
          truth
        }};
      }}).filter((item) => item.truth);

      const blob = new Blob([JSON.stringify(items, null, 2)], {{ type: "application/json" }});
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "captcha-labels.json";
      document.body.appendChild(a);
      a.click();
      a.remove();
    }});
  </script>
</body>
</html>"""
    output_path.write_text(page, encoding="utf-8")


def write_ascii_mirror(folder: Path, json_path: Path, html_path: Path):
    mirror_dir = Path("/tmp/fangdi-ocr-sample")
    if mirror_dir.exists():
        shutil.rmtree(mirror_dir)
    mirror_dir.mkdir(parents=True, exist_ok=True)

    for image_path in sorted(folder.glob("*.png")):
        shutil.copy2(image_path, mirror_dir / image_path.name)

    shutil.copy2(json_path, mirror_dir / json_path.name)
    shutil.copy2(html_path, mirror_dir / html_path.name)
    return mirror_dir


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", help="folder containing captcha png files")
    args = parser.parse_args()

    folder = Path(args.folder)
    images = sorted(folder.glob("*.png"))
    if not images:
      raise SystemExit("no png files found")

    results = [ocr_image(image_path) for image_path in images]
    json_path = folder / "ocr-results.json"
    html_path = folder / "ocr-review.html"
    json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    render_html(results, html_path)
    mirror_dir = write_ascii_mirror(folder, json_path, html_path)

    print(json.dumps({
        "count": len(results),
        "json": str(json_path),
        "html": str(html_path),
        "ascii_mirror": str(mirror_dir),
        "ascii_html": str(mirror_dir / html_path.name),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
