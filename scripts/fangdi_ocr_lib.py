#!/usr/bin/env python3
import re

import cv2
import ddddocr
import numpy as np


OCR = ddddocr.DdddOcr(show_ad=False)
EXPECTED_LEN = 4
SLIM_CHARS = set("ILJ1T")


def normalize(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", text or "").upper()


def variants(image: np.ndarray):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    up2 = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    blur = cv2.GaussianBlur(up2, (3, 3), 0)
    _, binary = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    invert = cv2.bitwise_not(binary)
    morph = cv2.morphologyEx(binary, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    return {
        "original": image,
        "gray_up2": up2,
        "binary": binary,
        "invert": invert,
        "morph": morph,
    }


def to_png_bytes(image: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError("failed to encode image")
    return encoded.tobytes()


def score(text: str) -> tuple[int, int]:
    normalized = normalize(text)
    alnum = len(normalized)
    exact_bonus = 10 if alnum == EXPECTED_LEN else 0
    near_bonus = max(0, 3 - abs(alnum - EXPECTED_LEN))
    return (exact_bonus + near_bonus + alnum, sum(ch.isalpha() for ch in normalized))


def max_run(text: str) -> int:
    best = 0
    current = 0
    last = None
    for ch in text:
        if ch == last:
            current += 1
        else:
            current = 1
            last = ch
        best = max(best, current)
    return best


def diversity(text: str) -> int:
    return len(set(text))


def rank_candidates(candidates):
    groups = {}
    for candidate in candidates:
        normalized = candidate["normalized"]
        groups.setdefault(
            normalized,
            {
                "normalized": normalized,
                "count": 0,
                "weight": 0.0,
                "derived": 0,
                "variants": [],
                "best_score": (0, 0),
            },
        )
        groups[normalized]["count"] += 1
        groups[normalized]["weight"] += 1.0
        groups[normalized]["variants"].append(candidate["variant"])
        groups[normalized]["best_score"] = max(groups[normalized]["best_score"], tuple(candidate["score"]))

    for candidate in candidates:
        normalized = candidate["normalized"]
        if len(normalized) != EXPECTED_LEN + 1:
            continue
        seen = set()
        for idx, ch in enumerate(normalized):
            if ch not in SLIM_CHARS:
                continue
            derived = normalized[:idx] + normalized[idx + 1 :]
            if derived in seen or len(derived) != EXPECTED_LEN:
                continue
            seen.add(derived)
            groups.setdefault(
                derived,
                {
                    "normalized": derived,
                    "count": 0,
                    "weight": 0.0,
                    "derived": 0,
                    "variants": [],
                    "best_score": score(derived),
                },
            )
            groups[derived]["weight"] += 0.8
            groups[derived]["derived"] += 1
            groups[derived]["variants"].append(f"derived_drop_{ch}")
            groups[derived]["best_score"] = max(groups[derived]["best_score"], score(derived))

    return sorted(
        groups.values(),
        key=lambda item: (
            1 if item["normalized"] else 0,
            1 if len(item["normalized"]) == EXPECTED_LEN else 0,
            item["weight"],
            item["count"],
            -max_run(item["normalized"]),
            diversity(item["normalized"]),
            item["best_score"],
        ),
        reverse=True,
    )


def ocr_array(image: np.ndarray):
    candidates = []
    for name, variant in variants(image).items():
        raw = OCR.classification(to_png_bytes(variant))
        candidates.append(
            {
                "variant": name,
                "raw": raw,
                "normalized": normalize(raw),
                "score": score(raw),
            }
        )
    candidates.sort(key=lambda item: item["score"], reverse=True)
    grouped = rank_candidates(candidates)
    return {
        "best": grouped[0]["normalized"] if grouped else "",
        "candidates": candidates,
        "grouped_candidates": grouped,
    }


def ocr_png_bytes(png_bytes: bytes):
    image = cv2.imdecode(np.frombuffer(png_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError("failed to decode image bytes")
    return ocr_array(image)
