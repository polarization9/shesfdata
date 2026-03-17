#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


TEMPLATE = r"""
(() => {
  const CONFIG = __CONFIG__;
  const labels = CONFIG.runner.labels || {};
  const selectors = CONFIG.runner.selectors || {};

  function normalizeSpace(text) {
    return (text || "").replace(/\s+/g, " ").trim();
  }

  function visible(el) {
    if (!el) return false;
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden";
  }

  function byCss(selector) {
    return selector ? document.querySelector(selector) : null;
  }

  function xpathFirst(expr) {
    return document.evaluate(expr, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
  }

  function findLabeledControl(labelText) {
    if (!labelText) return null;
    return (
      xpathFirst(`(//*[contains(normalize-space(.), "${labelText}")]/following::select[1])[1]`) ||
      xpathFirst(`(//*[contains(normalize-space(.), "${labelText}")]/following::input[1])[1]`)
    );
  }

  function getCaptchaImage() {
    return byCss(selectors.captcha_image) || xpathFirst(`(//*[contains(normalize-space(.), "${labels.captcha}")]/following::img[1])[1]`);
  }

  function getCaptchaInput() {
    if (selectors.captcha_input) {
      return byCss(selectors.captcha_input);
    }
    const captchaImage = getCaptchaImage();
    if (captchaImage) {
      const imgRect = captchaImage.getBoundingClientRect();
      const inputs = [...document.querySelectorAll("input")].filter((el) => visible(el));
      const nearby = inputs
        .map((el) => {
          const r = el.getBoundingClientRect();
          const dx = Math.abs(r.right - imgRect.left);
          const dy = Math.abs((r.top + r.height / 2) - (imgRect.top + imgRect.height / 2));
          return { el, score: dx + dy * 2, r };
        })
        .filter(({ r }) => r.width >= 40 && r.width <= 160 && r.height >= 20 && r.height <= 60 && r.left < imgRect.left + 20);
      if (nearby.length) {
        nearby.sort((a, b) => a.score - b.score);
        return nearby[0].el;
      }
    }
    return findLabeledControl(labels.captcha);
  }

  function findQueryButton() {
    if (selectors.query_button) {
      return byCss(selectors.query_button);
    }
    return (
      xpathFirst(`(//button[contains(normalize-space(.), "${labels.query_button}")])[1]`) ||
      xpathFirst(`(//input[@type="submit" and contains(@value, "${labels.query_button}")])[1]`) ||
      xpathFirst(`(//a[contains(normalize-space(.), "${labels.query_button}")])[1]`)
    );
  }

  const found = {
    district: byCss(selectors.district_control) || findLabeledControl(labels.district),
    plate: byCss(selectors.plate_control) || findLabeledControl(labels.plate),
    listing_age: byCss(selectors.listing_age_control) || findLabeledControl(labels.listing_age),
    captcha_input: getCaptchaInput(),
    captcha_image: getCaptchaImage(),
    query_button: findQueryButton()
  };

  const serialize = (el) => {
    if (!el) return null;
    return {
      tag: el.tagName,
      id: el.id || "",
      cls: el.className || "",
      name: el.getAttribute("name") || "",
      type: el.getAttribute("type") || "",
      text: normalizeSpace(el.textContent).slice(0, 80),
      value: el.value || "",
      outer: el.outerHTML.slice(0, 240)
    };
  };

  const colors = {
    district: "red",
    plate: "orange",
    listing_age: "green",
    captcha_input: "blue",
    captcha_image: "purple",
    query_button: "deeppink"
  };

  Object.entries(found).forEach(([key, el]) => {
    if (el) {
      el.style.outline = `3px solid ${colors[key]}`;
    }
  });

  const panelId = "__fangdiSelectorProbe";
  let panel = document.getElementById(panelId);
  if (panel) panel.remove();
  panel = document.createElement("pre");
  panel.id = panelId;
  panel.style.cssText = "position:fixed;left:16px;bottom:16px;z-index:999999;background:#fff;border:2px solid #333;padding:12px;max-width:720px;max-height:50vh;overflow:auto;font:12px/1.4 monospace;white-space:pre-wrap;";
  const payload = Object.fromEntries(Object.entries(found).map(([k, v]) => [k, serialize(v)]));
  panel.textContent = JSON.stringify(payload, null, 2);
  document.body.appendChild(panel);
  console.log("fangdi selector probe", payload);
})();
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("config", help="fangdi poc config json")
    parser.add_argument("output", help="where to write the selector probe js")
    args = parser.parse_args()

    config = json.loads(Path(args.config).read_text())
    script = TEMPLATE.replace("__CONFIG__", json.dumps(config, ensure_ascii=False, indent=2))

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(script, encoding="utf-8")
    print(json.dumps({"output": str(output_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
