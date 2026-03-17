#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


TEMPLATE = r"""
(() => {
  const CONFIG = __CONFIG__;
  const PLAN = __PLAN__;

  if (window.__fangdiRunnerActive) {
    console.warn("fangdi runner already active");
    return;
  }
  window.__fangdiRunnerActive = true;

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const rand = ([minMs, maxMs]) => minMs + Math.floor(Math.random() * (maxMs - minMs + 1));
  const now = () => new Date().toISOString();

  const labels = CONFIG.runner.labels || {};
  const selectors = CONFIG.runner.selectors || {};
  const successRe = new RegExp(CONFIG.runner.success_pattern);
  const captchaErrorRe = new RegExp(CONFIG.runner.captcha_error_pattern);

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

  function getCaptchaInput() {
    if (selectors.captcha_input) {
      return byCss(selectors.captcha_input);
    }

    const captchaImage = getCaptchaImage();
    if (captchaImage) {
      const inputs = [...document.querySelectorAll("input")].filter((el) => visible(el) && el !== captchaImage);
      const imgRect = captchaImage.getBoundingClientRect();
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

  function getCaptchaImage() {
    return (
      byCss(selectors.captcha_image) ||
      xpathFirst(`(//*[contains(normalize-space(.), "${labels.captcha}")]/following::img[1])[1]`)
    );
  }

  function getDistrictControl() {
    return byCss(selectors.district_control) || findLabeledControl(labels.district);
  }

  function getPlateControl() {
    return byCss(selectors.plate_control) || findLabeledControl(labels.plate);
  }

  function getListingAgeControl() {
    return byCss(selectors.listing_age_control) || findLabeledControl(labels.listing_age);
  }

  function fireInputEvents(el) {
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  async function pickVisibleOption(text) {
    const target = normalizeSpace(text);
    const candidates = [...document.querySelectorAll("li, option, div, span, a")]
      .filter((el) => visible(el) && normalizeSpace(el.textContent) === target)
      .sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top);
    if (!candidates.length) {
      throw new Error(`visible option not found: ${text}`);
    }
    candidates[0].click();
  }

  async function setControlValue(control, text) {
    if (!control) {
      throw new Error(`control missing for value ${text}`);
    }

    const tag = control.tagName.toLowerCase();
    if (tag === "select") {
      const option = [...control.options].find((item) => normalizeSpace(item.textContent) === text);
      if (!option) {
        throw new Error(`select option not found: ${text}`);
      }
      control.value = option.value;
      fireInputEvents(control);
      return;
    }

    control.click();
    await sleep(rand(CONFIG.runner.after_filter_ms));

    if (tag === "input" && !control.readOnly) {
      control.focus();
      control.value = "";
      fireInputEvents(control);
      control.value = text;
      fireInputEvents(control);
      try {
        await pickVisibleOption(text);
        return;
      } catch {}
      control.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
      control.dispatchEvent(new KeyboardEvent("keyup", { key: "Enter", bubbles: true }));
      return;
    }

    await pickVisibleOption(text);
  }

  function captureCaptchaDataUrl() {
    const img = getCaptchaImage();
    if (!img) {
      throw new Error("captcha image not found");
    }
    const canvas = document.createElement("canvas");
    canvas.width = img.naturalWidth || img.width;
    canvas.height = img.naturalHeight || img.height;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(img, 0, 0);
    return canvas.toDataURL("image/png");
  }

  async function ocrCaptcha() {
    const response = await fetch(`${CONFIG.api_base}/ocr`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image_data_url: captureCaptchaDataUrl() })
    });
    if (!response.ok) {
      throw new Error(`ocr http ${response.status}`);
    }
    return response.json();
  }

  async function appendResult(payload) {
    await fetch(`${CONFIG.api_base}/append-result`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
  }

  function readCount() {
    const text = document.body ? document.body.innerText : "";
    const match = text.match(successRe);
    return {
      count: match ? Number(match[1]) : null,
      text,
    };
  }

  function refreshCaptcha() {
    const img = getCaptchaImage();
    if (!img) {
      throw new Error("captcha image not found");
    }
    img.click();
  }

  function getOverlay() {
    let box = document.getElementById("__fangdiRunnerBox");
    if (box) return box;
    box = document.createElement("div");
    box.id = "__fangdiRunnerBox";
    box.style.cssText = "position:fixed;right:16px;bottom:16px;z-index:999999;background:#fff;border:2px solid #0a84ff;padding:12px;width:320px;font:14px/1.4 sans-serif;color:#111;";
    box.innerHTML = `
      <div style="font-weight:700;margin-bottom:8px;">Fangdi Runner</div>
      <div id="__fangdiRunnerStatus">初始化中...</div>
      <div id="__fangdiRunnerMeta" style="margin-top:6px;color:#555;"></div>
    `;
    document.body.appendChild(box);
    return box;
  }

  function updateOverlay(status, meta = "") {
    const box = getOverlay();
    box.querySelector("#__fangdiRunnerStatus").textContent = status;
    box.querySelector("#__fangdiRunnerMeta").textContent = meta;
  }

  async function runTask(task, index) {
    updateOverlay(`执行中 ${index + 1}/${PLAN.items.length}`, `${task.district} / ${task.plate} / ${task.listing_age}`);

    await setControlValue(getDistrictControl(), task.district);
    await sleep(rand(CONFIG.runner.after_filter_ms));
    await setControlValue(getPlateControl(), task.plate);
    await sleep(rand(CONFIG.runner.after_filter_ms));
    await setControlValue(getListingAgeControl(), task.listing_age);
    await sleep(rand(CONFIG.runner.after_filter_ms));

    const captchaInput = getCaptchaInput();
    const queryButton = findQueryButton();
    if (!captchaInput || !queryButton) {
      throw new Error("captcha input or query button not found");
    }

    for (let attempt = 1; attempt <= CONFIG.runner.max_captcha_refresh; attempt += 1) {
      const ocr = await ocrCaptcha();
      const guess = ocr.best || "";

      if (guess.length !== 4) {
        refreshCaptcha();
        await sleep(rand(CONFIG.runner.after_filter_ms));
        continue;
      }

      captchaInput.focus();
      captchaInput.value = "";
      fireInputEvents(captchaInput);
      captchaInput.value = guess;
      fireInputEvents(captchaInput);
      queryButton.click();
      await sleep(rand(CONFIG.runner.after_submit_ms));

      const summary = readCount();
      const payload = {
        task_id: task.task_id,
        district: task.district,
        plate: task.plate,
        listing_age: task.listing_age,
        captcha_guess: guess,
        captcha_attempt: attempt,
        recorded_at: now(),
        count: summary.count,
        status: summary.count !== null ? "success" : (captchaErrorRe.test(summary.text) ? "captcha_error" : "unknown"),
        page_url: location.href
      };

      if (summary.count !== null) {
        await appendResult(payload);
        return payload;
      }

      if (captchaErrorRe.test(summary.text)) {
        refreshCaptcha();
        await sleep(rand(CONFIG.runner.after_filter_ms));
        continue;
      }

      await appendResult(payload);
      return payload;
    }

    const failed = {
      task_id: task.task_id,
      district: task.district,
      plate: task.plate,
      listing_age: task.listing_age,
      recorded_at: now(),
      status: "captcha_exhausted",
      page_url: location.href
    };
    await appendResult(failed);
    return failed;
  }

  async function main() {
    updateOverlay("开始运行", `总任务 ${PLAN.count}`);
    const results = [];
    for (let i = 0; i < PLAN.items.length; i += 1) {
      try {
        const result = await runTask(PLAN.items[i], i);
        results.push(result);
      } catch (error) {
        const failed = {
          task_id: PLAN.items[i].task_id,
          district: PLAN.items[i].district,
          plate: PLAN.items[i].plate,
          listing_age: PLAN.items[i].listing_age,
          recorded_at: now(),
          status: "runner_error",
          error: String(error),
          page_url: location.href
        };
        await appendResult(failed);
        results.push(failed);
      }
      await sleep(rand(CONFIG.runner.between_queries_ms));
    }
    updateOverlay("运行完成", `success=${results.filter((item) => item.status === "success").length} / ${results.length}`);
    console.log("fangdi runner done", results);
  }

  main().catch((error) => {
    updateOverlay("运行失败", String(error));
    console.error(error);
  });
})();
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("config", help="fangdi poc config json")
    parser.add_argument("plan", help="query plan json from build_query_plan.py")
    parser.add_argument("output", help="where to write the browser runner js")
    args = parser.parse_args()

    config = json.loads(Path(args.config).read_text())
    plan = json.loads(Path(args.plan).read_text())

    script = TEMPLATE.replace("__CONFIG__", json.dumps(config, ensure_ascii=False, indent=2))
    script = script.replace("__PLAN__", json.dumps(plan, ensure_ascii=False, indent=2))

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(script, encoding="utf-8")
    print(json.dumps({"output": str(output_path), "count": plan["count"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
