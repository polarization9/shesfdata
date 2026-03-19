#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


TEMPLATE = r"""// ==UserScript==
// @name         Fangdi Count Runner
// @namespace    polarization9
// @version      0.1.0
// @description  Persisted count-query runner for fangdi.com.cn
// @match        https://www.fangdi.com.cn/old_house/*
// @grant        GM_xmlhttpRequest
// @grant        unsafeWindow
// @connect      127.0.0.1
// @connect      localhost
// ==/UserScript==

(function () {
  "use strict";

  const CONFIG = __CONFIG__;
  const PLAN = __PLAN__;
  const STATE_KEY = "__fangdi_userscript_state_v1";
  const BOOT_KEY = "__fangdi_userscript_booting_v1";
  const ALERT_KEY = "__fangdi_userscript_last_alert_v1";

  const labels = CONFIG.runner.labels || {};
  const selectors = CONFIG.runner.selectors || {};
  const successRe = new RegExp(CONFIG.runner.success_pattern);
  const captchaErrorRe = new RegExp(CONFIG.runner.captcha_error_pattern);
  const STABILITY_INTERVAL_MS = 500;
  const STABILITY_READS_REQUIRED = 3;

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const rand = ([minMs, maxMs]) => minMs + Math.floor(Math.random() * (maxMs - minMs + 1));
  const now = () => new Date().toISOString();

  (function patchAlert() {
    if (window.__fangdiAlertPatched) return;
    window.__fangdiAlertPatched = true;

    const patchFnSource = `
      (() => {
        if (window.__fangdiPageAlertPatched) return;
        window.__fangdiPageAlertPatched = true;
        const alertKey = ${JSON.stringify(ALERT_KEY)};
        const originalAlert = window.alert;
        window.alert = function(message) {
          try {
            localStorage.setItem(alertKey, String(message || ""));
          } catch (e) {}
          if (/验证码/.test(String(message || ""))) {
            console.warn("fangdi alert suppressed:", message);
            return undefined;
          }
          return originalAlert.call(window, message);
        };
      })();
    `;

    try {
      const script = document.createElement("script");
      script.textContent = patchFnSource;
      (document.head || document.documentElement).appendChild(script);
      script.remove();
    } catch (error) {
      console.warn("inject page alert patch failed:", error);
    }

    const localOriginalAlert = window.alert;
    window.alert = function (message) {
      try {
        localStorage.setItem(ALERT_KEY, String(message || ""));
      } catch {}
      if (/验证码/.test(String(message || ""))) {
        console.warn("fangdi userscript alert suppressed:", message);
        return undefined;
      }
      return localOriginalAlert.call(window, message);
    };

    try {
      if (typeof unsafeWindow !== "undefined" && unsafeWindow) {
        unsafeWindow.alert = window.alert;
      }
    } catch {}
  })();

  function popLastAlert() {
    try {
      const value = localStorage.getItem(ALERT_KEY) || "";
      localStorage.removeItem(ALERT_KEY);
      return value;
    } catch {
      return "";
    }
  }

  async function httpJson(url, payload) {
    if (typeof GM_xmlhttpRequest === "function") {
      return new Promise((resolve, reject) => {
        GM_xmlhttpRequest({
          method: "POST",
          url,
          headers: { "Content-Type": "application/json" },
          data: JSON.stringify(payload),
          onload: (response) => {
            if (response.status < 200 || response.status >= 300) {
              reject(new Error(`http ${response.status}`));
              return;
            }
            try {
              resolve(JSON.parse(response.responseText));
            } catch (error) {
              reject(error);
            }
          },
          onerror: () => reject(new Error("GM_xmlhttpRequest network error"))
        });
      });
    }

    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!response.ok) {
      throw new Error(`http ${response.status}`);
    }
    return response.json();
  }

  function defaultState() {
    return {
      active: false,
      index: 0,
      phase: "idle",
      currentTask: null,
      lastError: "",
      lastMessage: "",
      runStartedAt: "",
      successCount: 0,
      failureCount: 0,
      marketStatsCaptured: false
    };
  }

  function loadState() {
    try {
      return { ...defaultState(), ...(JSON.parse(localStorage.getItem(STATE_KEY) || "{}")) };
    } catch {
      return defaultState();
    }
  }

  function saveState(patch) {
    const next = { ...loadState(), ...patch };
    localStorage.setItem(STATE_KEY, JSON.stringify(next));
    updateOverlay(next);
    return next;
  }

  function resetState() {
    const next = defaultState();
    localStorage.setItem(STATE_KEY, JSON.stringify(next));
    updateOverlay(next);
    return next;
  }

  function normalizeSpace(text) {
    return (text || "").replace(/\s+/g, " ").trim();
  }

  function visible(el) {
    if (!el) return false;
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden";
  }

  function firstVisible(candidates) {
    return candidates.find((el) => el && visible(el)) || candidates.find(Boolean) || null;
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

  function getCaptchaImage() {
    return (
      byCss(selectors.captcha_image) ||
      xpathFirst(`(//*[contains(normalize-space(.), "${labels.captcha}")]/following::img[1])[1]`)
    );
  }

  function getCaptchaInput() {
    if (selectors.captcha_input) {
      return byCss(selectors.captcha_input);
    }

    const captchaImage = getCaptchaImage();
    if (captchaImage) {
      const inputs = [...document.querySelectorAll("input")].filter((el) => visible(el));
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

  function getDistrictControl() {
    return firstVisible([
      byCss(selectors.district_control),
      document.querySelector('select[name="district"]'),
      findLabeledControl(labels.district)
    ]);
  }

  function getPlateControl() {
    return firstVisible([
      byCss(selectors.plate_control),
      document.querySelector('select[name="region"]'),
      findLabeledControl(labels.plate)
    ]);
  }

  function getListingAgeControl() {
    return firstVisible([
      byCss(selectors.listing_age_control),
      document.querySelector('select[name="time"]'),
      findLabeledControl(labels.listing_age)
    ]);
  }

  function fireInputEvents(el) {
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function findRenderedSelect(selectEl) {
    if (!selectEl) return null;
    const next = selectEl.nextElementSibling;
    if (next && next.classList && next.classList.contains("layui-form-select")) {
      return next;
    }
    const parentMatch = selectEl.parentElement && selectEl.parentElement.querySelector(".layui-form-select");
    return parentMatch || null;
  }

  function renderedSelectedText(selectEl) {
    const rendered = findRenderedSelect(selectEl);
    if (!rendered) return "";
    const titleInput = rendered.querySelector(".layui-select-title input");
    if (titleInput && normalizeSpace(titleInput.value || "")) {
      return normalizeSpace(titleInput.value || "");
    }
    const title = rendered.querySelector(".layui-select-title");
    return title ? normalizeSpace(title.innerText || title.textContent || "") : "";
  }

  function renderedSelectHasOption(selectEl, optionText) {
    const rendered = findRenderedSelect(selectEl);
    if (!rendered) return true;
    const candidates = [...rendered.querySelectorAll("dl dd")]
      .filter((el) => normalizeSpace(el.textContent) === optionText && !el.classList.contains("layui-disabled"));
    return candidates.length > 0;
  }

  async function selectViaRenderedDropdown(selectEl, optionText) {
    const rendered = findRenderedSelect(selectEl);
    if (!rendered) {
      const option = [...selectEl.options].find((item) => normalizeSpace(item.textContent) === optionText);
      if (!option) {
        throw new Error(`select option not found: ${optionText}`);
      }
      selectEl.value = option.value;
      fireInputEvents(selectEl);
      return;
    }

    const title = rendered.querySelector(".layui-select-title input") || rendered.querySelector(".layui-select-title");
    if (!title) {
      throw new Error(`rendered select title not found: ${optionText}`);
    }

    title.click();
    await sleep(250);

    const candidates = [...rendered.querySelectorAll("dl dd")]
      .filter((el) => normalizeSpace(el.textContent) === optionText && !el.classList.contains("layui-disabled"));

    if (!candidates.length) {
      throw new Error(`select option not found: ${optionText}`);
    }

    candidates[0].click();
    await sleep(350);
  }

  async function waitFor(predicate, timeoutMs, intervalMs = 200) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      const value = predicate();
      if (value) return value;
      await sleep(intervalMs);
    }
    return null;
  }

  async function waitForStableValue(readValue, isAcceptable, timeoutMs, intervalMs = STABILITY_INTERVAL_MS, requiredReads = STABILITY_READS_REQUIRED) {
    const start = Date.now();
    let streak = 0;
    let lastSerialized = "";
    while (Date.now() - start < timeoutMs) {
      const value = readValue();
      if (isAcceptable(value)) {
        const serialized = JSON.stringify(value);
        if (serialized === lastSerialized) {
          streak += 1;
        } else {
          streak = 1;
          lastSerialized = serialized;
        }
        if (streak >= requiredReads) {
          return value;
        }
      } else {
        streak = 0;
        lastSerialized = "";
      }
      await sleep(intervalMs);
    }
    return null;
  }

  async function waitForReady() {
    return waitFor(() => {
      const district = getDistrictControl();
      const plate = getPlateControl();
      const listingAge = getListingAgeControl();
      const captchaInput = getCaptchaInput();
      const captchaImage = getCaptchaImage();
      const queryButton = findQueryButton();
      return district && plate && listingAge && captchaInput && captchaImage && queryButton
        ? { district, plate, listingAge, captchaInput, captchaImage, queryButton }
        : null;
    }, 15000);
  }

  function snapshotFieldForControl(control, snapshot) {
    if (!control || !snapshot) return "";
    if (control.id === "district" || control.name === "district") {
      return snapshot.district_text || "";
    }
    if (control.id === "regionid" || control.name === "region") {
      return snapshot.plate_text || "";
    }
    if (control.id === "timeVal" || control.name === "time") {
      return snapshot.listing_age_text || "";
    }
    return "";
  }

  async function setSelectValue(control, text) {
    const option = [...control.options].find((item) => normalizeSpace(item.textContent) === text);
    if (!option) {
      throw new Error(`select option not found: ${text}`);
    }
    const targetValue = option.value;

    for (let attempt = 0; attempt < 3; attempt += 1) {
      await selectViaRenderedDropdown(control, text);

      const applied = await waitForStableValue(
        () => {
          const snapshot = currentFormSnapshot();
          return {
            fieldText: snapshotFieldForControl(control, snapshot),
            renderedText: normalizeSpace(renderedSelectedText(control)),
            controlValue: control.value || ""
          };
        },
        (value) => value &&
          value.fieldText === text &&
          (!value.renderedText || value.renderedText === text) &&
          value.controlValue === targetValue,
        4500
      );

      if (applied) {
        return;
      }

      control.value = targetValue;
      fireInputEvents(control);
      await sleep(300);
    }

    throw new Error(`select value not applied: ${text}`);
  }

  async function ensurePlateSelection(task) {
    const plateControl = await waitForPlateOption(task.plate);
    if (!plateControl) {
      return { ok: false, reason: "missing_option" };
    }

    for (let attempt = 0; attempt < 3; attempt += 1) {
      await setSelectValue(plateControl, task.plate);
      const stable = await waitForStableValue(
        () => currentFormSnapshot(),
        (snapshot) =>
          snapshot &&
          snapshot.district_text === task.district &&
          (!snapshot.district_rendered_text || snapshot.district_rendered_text === task.district) &&
          snapshot.plate_value &&
          snapshot.plate_text === task.plate &&
          (!snapshot.plate_rendered_text || snapshot.plate_rendered_text === task.plate),
        5000
      );
      if (stable) {
        return { ok: true, control: plateControl };
      }
      await sleep(300);
    }

    return { ok: false, reason: "not_applied" };
  }

  async function waitForPlateOption(text) {
    return waitFor(() => {
      const control = getPlateControl();
      if (!control || control.tagName.toLowerCase() !== "select") return null;
      const option = [...control.options].find((item) => normalizeSpace(item.textContent) === text);
      if (!option) return null;
      return renderedSelectHasOption(control, text) ? control : null;
    }, 8000, 250);
  }

  function captureCaptchaDataUrl() {
    const img = getCaptchaImage();
    if (!img) throw new Error("captcha image not found");
    const canvas = document.createElement("canvas");
    canvas.width = img.naturalWidth || img.width;
    canvas.height = img.naturalHeight || img.height;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(img, 0, 0);
    return canvas.toDataURL("image/png");
  }

  function currentFormSnapshot() {
    const district = getDistrictControl();
    const plate = getPlateControl();
    const listingAge = getListingAgeControl();
    const captchaInput = getCaptchaInput();

    const selectedText = (control) => {
      if (!control) return "";
      if (control.tagName && control.tagName.toLowerCase() === "select") {
        const option = control.options[control.selectedIndex];
        return option ? normalizeSpace(option.textContent) : "";
      }
      return normalizeSpace(control.value || "");
    };

    return {
      district_value: district ? district.value : "",
      district_text: selectedText(district),
      district_rendered_text: district ? normalizeSpace(renderedSelectedText(district)) : "",
      plate_value: plate ? plate.value : "",
      plate_text: selectedText(plate),
      plate_rendered_text: plate ? normalizeSpace(renderedSelectedText(plate)) : "",
      listing_age_value: listingAge ? listingAge.value : "",
      listing_age_text: selectedText(listingAge),
      listing_age_rendered_text: listingAge ? normalizeSpace(renderedSelectedText(listingAge)) : "",
      captcha_value: captchaInput ? (captchaInput.value || "") : ""
    };
  }

  function readDailyMarketStats() {
    const text = document.body ? normalizeSpace(document.body.innerText || "") : "";
    const transactionCountMatch =
      text.match(/昨日二手房成交套数[:：]?\s*([0-9,]+)\s*套/) ||
      text.match(/昨日成交套数[:：]?\s*([0-9,]+)\s*套/);
    const transactionAreaMatch =
      text.match(/昨日二手房成交面积[:：]?\s*([0-9,.]+)\s*(?:㎡|m²|m2)/i) ||
      text.match(/昨日成交面积[:：]?\s*([0-9,.]+)\s*(?:㎡|m²|m2)/i);
    const updateTimeMatch =
      text.match(/数据更新时间(?:每日)?\s*([0-9]{1,2}:[0-9]{2})/) ||
      text.match(/更新时间(?:每日)?\s*([0-9]{1,2}:[0-9]{2})/);

    const transactionCount = transactionCountMatch ? Number(String(transactionCountMatch[1]).replace(/,/g, "")) : null;
    const transactionArea = transactionAreaMatch ? Number(String(transactionAreaMatch[1]).replace(/,/g, "")) : null;
    const updateTime = updateTimeMatch ? updateTimeMatch[1] : "";

    if (transactionCount === null && transactionArea === null && !updateTime) {
      return null;
    }

    return {
      transaction_count: Number.isFinite(transactionCount) ? transactionCount : null,
      transaction_area_sqm: Number.isFinite(transactionArea) ? transactionArea : null,
      update_time: updateTime,
      source_page_url: location.href
    };
  }

  async function captureDailyMarketStatsIfNeeded(state) {
    if (state.marketStatsCaptured) return state;
    const stats = readDailyMarketStats();
    if (!stats) return state;
    await appendResult({
      status: "market_stats_snapshot",
      recorded_at: now(),
      page_url: location.href,
      market_stats: stats
    });
    return saveState({
      marketStatsCaptured: true,
      lastMessage: state.lastMessage || "已抓取昨日成交概览"
    });
  }

  function currentResultSignature() {
    const rowTexts = [...document.querySelectorAll("table tbody tr")]
      .filter((row) => visible(row))
      .slice(0, 5)
      .map((row) => normalizeSpace(row.innerText || row.textContent || ""))
      .filter(Boolean);

    const pagerTexts = [...document.querySelectorAll(".layui-laypage, .page, .pagination")]
      .filter((el) => visible(el))
      .slice(0, 2)
      .map((el) => normalizeSpace(el.innerText || el.textContent || ""))
      .filter(Boolean);

    return [...rowTexts, ...pagerTexts].join(" || ");
  }

  function currentPagerSignature() {
    const pagerTexts = [...document.querySelectorAll(".layui-laypage, .page, .pagination")]
      .filter((el) => visible(el))
      .map((el) => normalizeSpace(el.innerText || el.textContent || ""))
      .filter(Boolean);
    return pagerTexts.join(" || ");
  }

  function formMatchesTask(task) {
    const snapshot = currentFormSnapshot();
    return (
      snapshot.district_text === task.district &&
      (!snapshot.district_rendered_text || snapshot.district_rendered_text === task.district) &&
      snapshot.plate_text === task.plate &&
      (!snapshot.plate_rendered_text || snapshot.plate_rendered_text === task.plate) &&
      snapshot.listing_age_text === task.listing_age
      && (!snapshot.listing_age_rendered_text || snapshot.listing_age_rendered_text === task.listing_age)
    );
  }

  function snapshotMatchesTask(snapshot, task) {
    return (
      snapshot &&
      snapshot.district_text === task.district &&
      (!snapshot.district_rendered_text || snapshot.district_rendered_text === task.district) &&
      snapshot.plate_text === task.plate &&
      (!snapshot.plate_rendered_text || snapshot.plate_rendered_text === task.plate) &&
      snapshot.listing_age_text === task.listing_age
      && (!snapshot.listing_age_rendered_text || snapshot.listing_age_rendered_text === task.listing_age)
    );
  }

  function resultSampleForTask(task) {
    const summary = readCount();
    const form = currentFormSnapshot();
    return {
      count: summary.count,
      matchedCount: summary.matchedCount,
      pageCount: summary.pageCount,
      urlCount: summary.urlCount,
      summaryText: summary.summaryText,
      resultSignature: currentResultSignature(),
      pagerSignature: currentPagerSignature(),
      form_snapshot: form,
      query_params: currentQueryParams(),
      text: summary.text || "",
      page_url: location.href,
      form_matches_task: snapshotMatchesTask(form, task)
    };
  }

  function queryParamsMatchTask(sample, task) {
    const submitted = task && task.form_snapshot;
    const params = sample && sample.query_params;
    if (!submitted || !params) return false;
    return (
      (!!submitted.district_value && params.district === submitted.district_value) &&
      (!!submitted.plate_value && params.region === submitted.plate_value) &&
      (!!submitted.listing_age_value && params.time === submitted.listing_age_value)
    );
  }

  function currentQueryParams() {
    try {
      const params = new URL(location.href).searchParams;
      return {
        district: params.get("district") || "",
        region: params.get("region") || "",
        time: params.get("time") || ""
      };
    } catch {
      return { district: "", region: "", time: "" };
    }
  }

  async function ocrCaptcha() {
    return httpJson(`${CONFIG.api_base}/ocr`, { image_data_url: captureCaptchaDataUrl() });
  }

  async function appendResult(payload) {
    return httpJson(`${CONFIG.api_base}/append-result`, payload);
  }

  function peekLastAlert() {
    try {
      return localStorage.getItem(ALERT_KEY) || "";
    } catch {
      return "";
    }
  }

  function readCount() {
    const text = document.body ? document.body.innerText : "";
    const match = text.match(successRe);
    let urlCount = null;
    let urlPageCount = null;
    try {
      const params = new URL(location.href).searchParams;
      const rawCount = params.get("RecordCount");
      const rawPageCount = params.get("PageCount");
      if (rawCount && /^\d+$/.test(rawCount)) {
        urlCount = Number(rawCount);
      }
      if (rawPageCount && /^\d+$/.test(rawPageCount)) {
        urlPageCount = Number(rawPageCount);
      }
    } catch {}
    return {
      count: match ? Number(match[1]) : urlCount,
      matchedCount: match ? Number(match[1]) : null,
      summaryText: match ? normalizeSpace(match[0] || "") : "",
      pageCount: urlPageCount,
      urlCount,
      text
    };
  }

  async function waitForSubmissionOutcome(task) {
    const settleMs = CONFIG.runner.post_submit_settle_ms || 2500;
    const waitMs = CONFIG.runner.result_wait_ms || 12000;

    await sleep(settleMs);

    const found = await waitForStableValue(
      () => {
        const sample = resultSampleForTask(task);
        const alertMessage = peekLastAlert();
        const resultSignatureChanged = sample.resultSignature && sample.resultSignature !== (task.pre_submit_result_signature || "");
        const pagerSignatureChanged = sample.pagerSignature && sample.pagerSignature !== (task.pre_submit_pager_signature || "");
        const summaryTextChanged = sample.summaryText && sample.summaryText !== (task.pre_submit_summary_text || "");
        const pageAdvanced = resultSignatureChanged || pagerSignatureChanged || summaryTextChanged;
        const queryMatchesTask = queryParamsMatchTask(sample, task);
        return {
          kind:
            (captchaErrorRe.test(sample.text || "") || captchaErrorRe.test(alertMessage || "") || /验证码/.test(alertMessage || "")) ? "captcha_error" :
            (sample.count !== null && sample.form_matches_task && (pageAdvanced || queryMatchesTask) ? "success" : "pending"),
          sample,
          pageAdvanced,
          queryMatchesTask
        };
      },
      (value) => value && (value.kind === "captcha_error" || value.kind === "success"),
      waitMs
    );

    if (found) {
      if (found.kind === "captcha_error") {
        return { kind: "captcha_error", summary: found.sample };
      }
      return { kind: "success", summary: found.sample };
    }

    const finalSummary = resultSampleForTask(task);
    const finalAlert = peekLastAlert();
    const resultSignatureChanged = finalSummary.resultSignature && finalSummary.resultSignature !== (task.pre_submit_result_signature || "");
    const pagerSignatureChanged = finalSummary.pagerSignature && finalSummary.pagerSignature !== (task.pre_submit_pager_signature || "");
    const summaryTextChanged = finalSummary.summaryText && finalSummary.summaryText !== (task.pre_submit_summary_text || "");
    const pageAdvanced = resultSignatureChanged || pagerSignatureChanged || summaryTextChanged;
    const queryMatchesTask = queryParamsMatchTask(finalSummary, task);

    if (captchaErrorRe.test(finalAlert || "") || /验证码/.test(finalAlert || "")) {
      return { kind: "captcha_error", summary: finalSummary };
    }

    if (finalSummary.count !== null && finalSummary.form_matches_task && queryMatchesTask) {
      return { kind: "success", summary: finalSummary };
    }

    if (finalSummary.count !== null && pageAdvanced && !finalSummary.form_matches_task) {
      return { kind: "mismatched_result", summary: finalSummary };
    }

    if (finalSummary.count !== null && !pageAdvanced && !queryMatchesTask) {
      return { kind: "stale_result", summary: finalSummary };
    }

    return { kind: "unknown", summary: finalSummary };
  }

  function refreshCaptcha() {
    const img = getCaptchaImage();
    if (!img) throw new Error("captcha image not found");
    img.click();
  }

  function getOverlay() {
    let box = document.getElementById("__fangdiUserscriptBox");
    if (box) return box;
    box = document.createElement("div");
    box.id = "__fangdiUserscriptBox";
    box.style.cssText = "position:fixed;right:16px;bottom:16px;z-index:999999;background:#fff;border:2px solid #0a84ff;padding:12px;width:340px;font:14px/1.4 sans-serif;color:#111;";
    box.innerHTML = `
      <div style="font-weight:700;margin-bottom:8px;">Fangdi Userscript</div>
      <div id="__fangdiUserscriptStatus">未启动</div>
      <div id="__fangdiUserscriptMeta" style="margin-top:6px;color:#555;white-space:pre-wrap;"></div>
      <div style="display:flex;gap:8px;margin-top:10px;">
        <button id="__fangdiStartBtn" style="padding:6px 10px;">开始</button>
        <button id="__fangdiStopBtn" style="padding:6px 10px;">停止</button>
        <button id="__fangdiResetBtn" style="padding:6px 10px;">重置</button>
      </div>
    `;
    document.body.appendChild(box);
    box.querySelector("#__fangdiStartBtn").onclick = () => {
      const next = saveState({
        active: true,
        phase: "prepare",
        lastError: "",
        lastMessage: "手动启动",
        runStartedAt: loadState().runStartedAt || now()
      });
      scheduleTick(400);
      updateOverlay(next);
    };
    box.querySelector("#__fangdiStopBtn").onclick = () => {
      updateOverlay(saveState({ active: false, phase: "idle", lastMessage: "已手动停止" }));
    };
    box.querySelector("#__fangdiResetBtn").onclick = () => {
      updateOverlay(resetState());
    };
    return box;
  }

  function updateOverlay(state = loadState()) {
    const box = getOverlay();
    const total = PLAN.items.length;
    const current = Math.min(state.index + 1, total);
    box.querySelector("#__fangdiUserscriptStatus").textContent =
      state.active ? `运行中 ${current}/${total} (${state.phase})` : `未运行 (${current}/${total})`;
    box.querySelector("#__fangdiUserscriptMeta").textContent =
      `success=${state.successCount || 0} failure=${state.failureCount || 0}\n${state.lastMessage || ""}\n${state.lastError || ""}`;
  }

  function scheduleTick(delayMs = 250) {
    if (window.__fangdiUserscriptTimer) {
      clearTimeout(window.__fangdiUserscriptTimer);
    }
    window.__fangdiUserscriptTimer = setTimeout(tick, delayMs);
  }

  async function processSubmittedPage(state) {
    const task = state.currentTask;
    if (!task) {
      return saveState({ active: false, phase: "idle", lastError: "missing currentTask after refresh" });
    }

    const outcome = await waitForSubmissionOutcome(task);
    const summary = outcome.summary;
    const alertMessage = popLastAlert();
    const queryParams = currentQueryParams();
    const currentSnapshot = currentFormSnapshot();
    const basePayload = {
      task_id: task.task_id,
      district: task.district,
      plate: task.plate,
      listing_age: task.listing_age,
      captcha_guess: task.captcha_guess,
      captcha_attempt: task.captcha_attempt,
      recorded_at: now(),
      page_url: location.href,
      alert_message: alertMessage,
      form_snapshot: task.form_snapshot || null,
      current_form_snapshot: currentSnapshot || null
    };

    const submittedWithoutPlate =
      !queryParams.region ||
      !currentSnapshot.plate_value ||
      !currentSnapshot.plate_text;

    if (submittedWithoutPlate) {
      const attempts = task.captcha_attempt || 1;
      if (attempts >= CONFIG.runner.max_captcha_refresh) {
        await appendResult({
          ...basePayload,
          status: "submission_mismatch_exhausted",
          count: summary.count,
          page_count: summary.pageCount,
          page_excerpt: (summary.text || "").slice(0, 1000)
        });
        const next = saveState({
          index: state.index + 1,
          phase: "prepare",
          currentTask: null,
          failureCount: (state.failureCount || 0) + 1,
          lastMessage: `${task.district} / ${task.plate} / ${task.listing_age} 提交时板块丢失，重试耗尽`,
          lastError: ""
        });
        if (next.index >= PLAN.items.length) {
          saveState({ active: false, phase: "done", lastMessage: "全部任务完成" });
        } else {
          scheduleTick(rand(CONFIG.runner.between_queries_ms));
        }
        return;
      }

      saveState({
        phase: "prepare",
        currentTask: { ...task, captcha_attempt: attempts + 1 },
        lastMessage: `${task.district} / ${task.plate} / ${task.listing_age} 提交时板块为空，重试`,
        lastError: ""
      });
      scheduleTick(rand(CONFIG.runner.after_filter_ms));
      return;
    }

    if (outcome.kind === "success" && summary.count !== null) {
      await appendResult({ ...basePayload, status: "success", count: summary.count, page_count: summary.pageCount });
      const next = saveState({
        index: state.index + 1,
        phase: "prepare",
        currentTask: null,
        successCount: (state.successCount || 0) + 1,
        lastMessage: `${task.district} / ${task.plate} / ${task.listing_age} = ${summary.count}`,
        lastError: ""
      });
      if (next.index >= PLAN.items.length) {
        saveState({ active: false, phase: "done", lastMessage: "全部任务完成" });
      } else {
        scheduleTick(rand(CONFIG.runner.between_queries_ms));
      }
      return;
    }

    if (outcome.kind === "captcha_error") {
      const attempts = task.captcha_attempt || 1;
      if (attempts >= CONFIG.runner.max_captcha_refresh) {
        await appendResult({ ...basePayload, status: "captcha_exhausted", count: null });
        const next = saveState({
          index: state.index + 1,
          phase: "prepare",
          currentTask: null,
          failureCount: (state.failureCount || 0) + 1,
          lastMessage: `${task.district} / ${task.plate} / ${task.listing_age} 验证码重试耗尽`,
          lastError: ""
        });
        if (next.index >= PLAN.items.length) {
          saveState({ active: false, phase: "done", lastMessage: "全部任务完成" });
        } else {
          scheduleTick(rand(CONFIG.runner.between_queries_ms));
        }
        return;
      }

      saveState({
        phase: "prepare",
        currentTask: { ...task, captcha_attempt: attempts + 1 },
        lastMessage: `${task.district} / ${task.plate} / ${task.listing_age} 验证码错误，重试`,
        lastError: ""
      });
      scheduleTick(rand(CONFIG.runner.after_filter_ms));
      return;
    }

    if (outcome.kind === "stale_result") {
      const attempts = task.captcha_attempt || 1;
      if (attempts >= CONFIG.runner.max_captcha_refresh) {
        await appendResult({
          ...basePayload,
          status: "stale_result_exhausted",
          count: summary.count,
          page_count: summary.pageCount,
          page_excerpt: (summary.text || "").slice(0, 1000)
        });
        const next = saveState({
          index: state.index + 1,
          phase: "prepare",
          currentTask: null,
          failureCount: (state.failureCount || 0) + 1,
          lastMessage: `${task.district} / ${task.plate} / ${task.listing_age} 结果未刷新，重试耗尽`,
          lastError: ""
        });
        if (next.index >= PLAN.items.length) {
          saveState({ active: false, phase: "done", lastMessage: "全部任务完成" });
        } else {
          scheduleTick(rand(CONFIG.runner.between_queries_ms));
        }
        return;
      }

      saveState({
        phase: "prepare",
        currentTask: { ...task, captcha_attempt: attempts + 1 },
        lastMessage: `${task.district} / ${task.plate} / ${task.listing_age} 页面结果未刷新，重试`,
        lastError: ""
      });
      scheduleTick(rand(CONFIG.runner.after_filter_ms));
      return;
    }

    if (outcome.kind === "mismatched_result") {
      const attempts = task.captcha_attempt || 1;
      if (attempts >= CONFIG.runner.max_captcha_refresh) {
        await appendResult({
          ...basePayload,
          status: "mismatched_result_exhausted",
          count: summary.count,
          page_count: summary.pageCount,
          page_excerpt: (summary.text || "").slice(0, 1000)
        });
        const next = saveState({
          index: state.index + 1,
          phase: "prepare",
          currentTask: null,
          failureCount: (state.failureCount || 0) + 1,
          lastMessage: `${task.district} / ${task.plate} / ${task.listing_age} 结果归属不一致，重试耗尽`,
          lastError: ""
        });
        if (next.index >= PLAN.items.length) {
          saveState({ active: false, phase: "done", lastMessage: "全部任务完成" });
        } else {
          scheduleTick(rand(CONFIG.runner.between_queries_ms));
        }
        return;
      }

      saveState({
        phase: "prepare",
        currentTask: { ...task, captcha_attempt: attempts + 1 },
        lastMessage: `${task.district} / ${task.plate} / ${task.listing_age} 结果归属不一致，重试`,
        lastError: ""
      });
      scheduleTick(rand(CONFIG.runner.after_filter_ms));
      return;
    }

    if (alertMessage) {
      const looksLikeCaptcha = captchaErrorRe.test(alertMessage) || /验证码/.test(alertMessage);
      if (looksLikeCaptcha) {
        const attempts = task.captcha_attempt || 1;
        if (attempts >= CONFIG.runner.max_captcha_refresh) {
          await appendResult({ ...basePayload, status: "captcha_exhausted", count: null, page_excerpt: (summary.text || "").slice(0, 1000) });
          const next = saveState({
            index: state.index + 1,
            phase: "prepare",
            currentTask: null,
            failureCount: (state.failureCount || 0) + 1,
            lastMessage: `${task.district} / ${task.plate} / ${task.listing_age} 验证码重试耗尽`,
            lastError: alertMessage
          });
          if (next.index >= PLAN.items.length) {
            saveState({ active: false, phase: "done", lastMessage: "全部任务完成" });
          } else {
            scheduleTick(rand(CONFIG.runner.between_queries_ms));
          }
          return;
        }

        saveState({
          phase: "prepare",
          currentTask: { ...task, captcha_attempt: attempts + 1 },
          lastMessage: `${task.district} / ${task.plate} / ${task.listing_age} ${alertMessage}`,
          lastError: ""
        });
        scheduleTick(rand(CONFIG.runner.after_filter_ms));
        return;
      }
    }

    await appendResult({ ...basePayload, status: "unknown", count: null, page_excerpt: (summary.text || "").slice(0, 1000) });
    saveState({
      active: false,
      phase: "error",
      failureCount: (state.failureCount || 0) + 1,
      lastMessage: `${task.district} / ${task.plate} / ${task.listing_age} 返回未知页面`,
      lastError: alertMessage || "提交后未识别到结果数，也不是验证码错误"
    });
  }

  async function failCurrentTaskAndContinue(state, task, status, message, extra = {}) {
    await appendResult({
      task_id: task.task_id,
      district: task.district,
      plate: task.plate,
      listing_age: task.listing_age,
      recorded_at: now(),
      status,
      page_url: location.href,
      ...extra
    });

    const next = saveState({
      index: state.index + 1,
      phase: "prepare",
      currentTask: null,
      failureCount: (state.failureCount || 0) + 1,
      lastMessage: message,
      lastError: ""
    });

    if (next.index >= PLAN.items.length) {
      saveState({ active: false, phase: "done", lastMessage: "全部任务完成" });
    } else {
      scheduleTick(rand(CONFIG.runner.between_queries_ms));
    }
  }

  async function runCurrentTask(state) {
    if (state.index >= PLAN.items.length) {
      saveState({ active: false, phase: "done", lastMessage: "全部任务完成", lastError: "" });
      return;
    }

    const task = state.currentTask || { ...PLAN.items[state.index], captcha_attempt: 1 };
    const ready = await waitForReady();
    if (!ready) {
      saveState({ active: false, phase: "error", lastError: "页面控件未准备好", lastMessage: "未找到查询表单" });
      return;
    }

    try {
      await setSelectValue(ready.district, task.district);
      await sleep(rand(CONFIG.runner.after_filter_ms));

      const plateSelection = await ensurePlateSelection(task);
      if (!plateSelection.ok && plateSelection.reason === "missing_option") {
        await failCurrentTaskAndContinue(
          state,
          task,
          "invalid_plate",
          `${task.district} / ${task.plate} 不在当前网站板块列表里`
        );
        return;
      }
      if (!plateSelection.ok) {
        saveState({
          phase: "prepare",
          currentTask: { ...task, captcha_attempt: task.captcha_attempt },
          lastMessage: `${task.district} / ${task.plate} 板块选择未生效，重试`,
          lastError: ""
        });
        scheduleTick(rand(CONFIG.runner.after_filter_ms));
        return;
      }

      await sleep(rand(CONFIG.runner.after_filter_ms));
      await setSelectValue(getListingAgeControl(), task.listing_age);
      await sleep(rand(CONFIG.runner.after_filter_ms));
    } catch (error) {
      const message = String(error);
      if (message.includes("select option not found:")) {
        const missing = message.split("select option not found:")[1].trim();
        const status =
          missing === task.plate ? "invalid_plate" :
          missing === task.district ? "invalid_district" :
          missing === task.listing_age ? "invalid_listing_age" :
          "invalid_option";

        await failCurrentTaskAndContinue(
          state,
          task,
          status,
          `${task.district} / ${task.plate} / ${task.listing_age} 配置值不存在: ${missing}`,
          { invalid_value: missing }
        );
        return;
      }
      throw error;
    }

    for (let retries = 0; retries < CONFIG.runner.max_captcha_refresh; retries += 1) {
      const stableSnapshot = await waitForStableValue(
        () => currentFormSnapshot(),
        (snapshot) => snapshotMatchesTask(snapshot, task),
        5000
      );

      if (!stableSnapshot) {
        saveState({
          phase: "prepare",
          currentTask: { ...task, captcha_attempt: task.captcha_attempt },
          lastMessage: `${task.district} / ${task.plate} / ${task.listing_age} 表单未稳定，重试`,
          lastError: ""
        });
        scheduleTick(rand(CONFIG.runner.after_filter_ms));
        return;
      }

      const ocr = await ocrCaptcha();
      const guess = (ocr.best || "").trim();

      if (guess.length !== 4) {
        refreshCaptcha();
        await sleep(rand(CONFIG.runner.after_filter_ms));
        continue;
      }

      const captchaInput = getCaptchaInput();
      const queryButton = findQueryButton();
      if (!captchaInput || !queryButton) {
        saveState({ active: false, phase: "error", lastError: "验证码输入框或查询按钮未找到" });
        return;
      }

      captchaInput.focus();
      captchaInput.value = "";
      fireInputEvents(captchaInput);
      captchaInput.value = guess;
      fireInputEvents(captchaInput);

      const finalSnapshot = currentFormSnapshot();
      if (!snapshotMatchesTask(finalSnapshot, task)) {
        saveState({
          phase: "prepare",
          currentTask: { ...task, captcha_attempt: task.captcha_attempt },
          lastMessage: `${task.district} / ${task.plate} / ${task.listing_age} 提交前表单回退，重试`,
          lastError: ""
        });
        scheduleTick(rand(CONFIG.runner.after_filter_ms));
        return;
      }

      const preSubmitSummary = readCount();
      saveState({
        phase: "submitted",
        currentTask: {
          ...task,
          captcha_guess: guess,
          captcha_attempt: task.captcha_attempt,
          form_snapshot: finalSnapshot,
          pre_submit_count: preSubmitSummary.count,
          pre_submit_page_count: preSubmitSummary.pageCount,
          pre_submit_page_url: location.href,
          pre_submit_summary_text: preSubmitSummary.summaryText,
          pre_submit_result_signature: currentResultSignature(),
          pre_submit_pager_signature: currentPagerSignature()
        },
        lastMessage: `提交中 ${task.district} / ${task.plate} / ${task.listing_age}`,
        lastError: ""
      });

      queryButton.click();
      // Some captcha failures do not navigate away; they only refresh the captcha
      // in place after alert/check() handling. Schedule the next state check either
      // way so the submitted phase can recover on same-page failures.
      scheduleTick(200);
      return;
    }

    await appendResult({
      task_id: task.task_id,
      district: task.district,
      plate: task.plate,
      listing_age: task.listing_age,
      recorded_at: now(),
      status: "captcha_exhausted_before_submit",
      page_url: location.href
    });
    const next = saveState({
      index: state.index + 1,
      phase: "prepare",
      currentTask: null,
      failureCount: (state.failureCount || 0) + 1,
      lastMessage: `${task.district} / ${task.plate} / ${task.listing_age} OCR 无法得到 4 位验证码`,
      lastError: ""
    });
    if (next.index >= PLAN.items.length) {
      saveState({ active: false, phase: "done", lastMessage: "全部任务完成" });
    } else {
      scheduleTick(rand(CONFIG.runner.between_queries_ms));
    }
  }

  async function tick() {
    if (window[BOOT_KEY]) return;
    window[BOOT_KEY] = true;
    try {
      let state = loadState();
      updateOverlay(state);
      if (!state.active) return;
      state = await captureDailyMarketStatsIfNeeded(state);
      if (state.phase === "submitted") {
        await processSubmittedPage(state);
      } else {
        await runCurrentTask(state);
      }
    } catch (error) {
      saveState({ active: false, phase: "error", lastError: String(error), lastMessage: "运行异常停止" });
      console.error(error);
    } finally {
      window[BOOT_KEY] = false;
    }
  }

  getOverlay();
  updateOverlay(loadState());
  if (loadState().active) {
    scheduleTick(600);
  }
})();
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("config", help="fangdi poc config json")
    parser.add_argument("plan", help="query plan json from build_query_plan.py")
    parser.add_argument("output", help="where to write the userscript js")
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
