#!/usr/bin/env python3
import argparse
from pathlib import Path


TEMPLATE = r"""(() => {
  const DISTRICT_SELECTOR = "#district";
  const PLATE_SELECTOR = "#regionid";
  const LISTING_AGE_SELECTOR = "#timeVal";

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const visible = (el) => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.display !== "none" && s.visibility !== "hidden";
  };

  function firstVisible(candidates) {
    return candidates.find((el) => el && visible(el)) || candidates.find(Boolean) || null;
  }

  function getDistrictControl() {
    return firstVisible([
      document.querySelector(DISTRICT_SELECTOR),
      document.querySelector('select[name="district"]')
    ]);
  }

  function getPlateControl() {
    return firstVisible([
      document.querySelector(PLATE_SELECTOR) ||
      document.querySelector('select[name="region"]') ||
      document.evaluate(
        '(//*[contains(normalize-space(.), "所属板块")]/following::select[1])[1]',
        document,
        null,
        XPathResult.FIRST_ORDERED_NODE_TYPE,
        null
      ).singleNodeValue
    ]);
  }

  function getListingAgeControl() {
    return firstVisible([
      document.querySelector(LISTING_AGE_SELECTOR) ||
      document.querySelector('select[name="time"]') ||
      document.evaluate(
        '(//*[contains(normalize-space(.), "挂牌时间")]/following::select[1])[1]',
        document,
        null,
        XPathResult.FIRST_ORDERED_NODE_TYPE,
        null
      ).singleNodeValue
    ]);
  }

  function normalizeSpace(text) {
    return (text || "").replace(/\s+/g, " ").trim();
  }

  function optionSnapshot(selectEl) {
    return [...selectEl.options]
      .map((opt) => ({
        value: opt.value,
        name: normalizeSpace(opt.textContent),
      }))
      .filter((item) => item.value && item.name && item.name !== "不限");
  }

  function signature(selectEl) {
    return optionSnapshot(selectEl)
      .map((item) => `${item.value}:${item.name}`)
      .join("|");
  }

  function fireEvents(el) {
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  async function waitFor(predicate, timeoutMs, intervalMs = 250) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      const value = predicate();
      if (value) return value;
      await sleep(intervalMs);
    }
    return null;
  }

  function getOverlay() {
    let box = document.getElementById("__fangdiDimensionsExporter");
    if (box) return box;
    box = document.createElement("div");
    box.id = "__fangdiDimensionsExporter";
    box.style.cssText = "position:fixed;right:16px;bottom:16px;z-index:999999;background:#fff;border:2px solid #0a84ff;padding:12px;width:360px;font:14px/1.4 sans-serif;color:#111;";
    box.innerHTML = `
      <div style="font-weight:700;margin-bottom:8px;">Fangdi Dimensions Exporter</div>
      <div id="__fangdiDimensionsStatus">未开始</div>
      <div id="__fangdiDimensionsMeta" style="margin-top:6px;color:#555;white-space:pre-wrap;"></div>
      <div style="display:flex;gap:8px;margin-top:10px;">
        <button id="__fangdiDimensionsStart" style="padding:6px 10px;">开始导出</button>
      </div>
    `;
    document.body.appendChild(box);
    return box;
  }

  function updateOverlay(status, meta = "") {
    const box = getOverlay();
    box.querySelector("#__fangdiDimensionsStatus").textContent = status;
    box.querySelector("#__fangdiDimensionsMeta").textContent = meta;
  }

  async function setDistrict(control, option) {
    control.value = option.value;
    fireEvents(control);
  }

  async function waitForPlateRefresh(expectedDistrictValue, previousSig, allowSameSig = false) {
    return waitFor(() => {
      const district = getDistrictControl();
      const plate = getPlateControl();
      if (!district || !plate) return null;
      if (district.value !== expectedDistrictValue) return null;
      const currentSig = signature(plate);
      const items = optionSnapshot(plate);
      if (!items.length) return null;
      if (allowSameSig || currentSig !== previousSig) {
        return { currentSig, items };
      }
      return null;
    }, 10000, 300);
  }

  function downloadJson(payload, filename) {
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  async function main() {
    const district = getDistrictControl();
    if (!district) {
      throw new Error("未找到 district 控件");
    }

    const districtOptions = optionSnapshot(district);
    const originalDistrictValue = district.value;
    const initialPlate = getPlateControl();
    const originalPlateSig = initialPlate ? signature(initialPlate) : "";

    const districts = [];
    updateOverlay("导出中", `共 ${districtOptions.length} 个区`);

    for (let i = 0; i < districtOptions.length; i += 1) {
      const item = districtOptions[i];
      updateOverlay("导出中", `${i + 1}/${districtOptions.length} ${item.name}`);

      const currentPlate = getPlateControl();
      const previousSig = currentPlate ? signature(currentPlate) : "";
      await setDistrict(district, item);
      await sleep(600);

      const refreshed = await waitForPlateRefresh(
        item.value,
        previousSig,
        item.value === originalDistrictValue && previousSig === originalPlateSig
      );

      if (!refreshed) {
        districts.push({
          name: item.name,
          value: item.value,
          plates: [],
          error: "plate options not refreshed"
        });
        continue;
      }

      districts.push({
        name: item.name,
        value: item.value,
        plates: refreshed.items
      });
    }

    const listingAge = getListingAgeControl();
    const listingAgeOptions = listingAge ? optionSnapshot(listingAge) : [];

    const payload = {
      generated_at: new Date().toISOString(),
      source_url: location.href,
      district_count: districts.length,
      listing_age_buckets: listingAgeOptions.map((item) => item.name),
      districts
    };

    updateOverlay(
      "导出完成",
      `区数=${districts.length}\n有效板块数=${districts.reduce((acc, d) => acc + (d.plates || []).length, 0)}`
    );
    downloadJson(payload, "fangdi-dimensions.json");
    console.log("fangdi dimensions exported", payload);
  }

  getOverlay();
  updateOverlay("待开始", "打开查询页后点击“开始导出”");
  document.getElementById("__fangdiDimensionsStart").onclick = () => {
    main().catch((error) => {
      updateOverlay("导出失败", String(error));
      console.error(error);
    });
  };
})();"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", help="where to write exporter js")
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(TEMPLATE, encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()
