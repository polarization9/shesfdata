#!/usr/bin/env python3
import json
import sys
from pathlib import Path

import cv2
from fangdi_ocr_lib import ocr_array


def main():
    if len(sys.argv) != 2:
      raise SystemExit("usage: ocr_captcha.py <image_path>")

    image_path = Path(sys.argv[1])
    image = cv2.imread(str(image_path))
    if image is None:
        raise SystemExit(f"failed to read image: {image_path}")

    print(json.dumps(ocr_array(image), ensure_ascii=False))


if __name__ == "__main__":
    main()
