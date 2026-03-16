import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { chromium } from "playwright-core";

const chromePath =
  process.env.CHROME_PATH ||
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const targetUrl =
  process.env.TARGET_URL ||
  "https://www.fangdi.com.cn/old_house/old_house.html";
const waitReadyMs = Number(process.env.WAIT_READY_MS || "180000");
const attempts = Number(process.env.OCR_ATTEMPTS || "20");
const perAttemptTimeoutMs = Number(process.env.ATTEMPT_TIMEOUT_MS || "12000");
const outputDir = path.resolve(process.cwd(), "artifacts", "fangdi", "ocr");

fs.mkdirSync(outputDir, { recursive: true });

const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "pw-fangdi-ocr-"));

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function ts() {
  return new Date().toISOString().replace(/[:.]/g, "-");
}

function log(message) {
  console.log(`[fangdi-ocr] ${message}`);
}

function runOcr(imagePath) {
  const result = spawnSync(
    path.resolve(process.cwd(), ".venv", "bin", "python"),
    [path.resolve(process.cwd(), "scripts", "ocr_captcha.py"), imagePath],
    { encoding: "utf-8" }
  );
  if (result.status !== 0) {
    throw new Error(result.stderr || result.stdout || "ocr failed");
  }
  return JSON.parse(result.stdout);
}

async function getFormHandles(page) {
  const captchaInput = page
    .locator(
      "xpath=(//*[contains(normalize-space(.), '验证码')]/following::input[1] | //input[contains(@placeholder,'验证码')])[1]"
    )
    .first();
  const captchaImage = page
    .locator(
      "xpath=(//*[contains(normalize-space(.), '验证码')]/following::img[1] | //img[contains(@src,'captcha') or contains(@src,'verify')])[1]"
    )
    .first();
  const queryButton = page
    .locator(
      "xpath=(//button[contains(normalize-space(.), '查询')] | //input[@type='submit' and contains(@value, '查询')] | //a[contains(normalize-space(.), '查询')])[1]"
    )
    .first();
  const countText = page.locator("text=/显示记录共\\d+条/").first();

  return { captchaInput, captchaImage, queryButton, countText };
}

async function waitUntilReady(page) {
  const start = Date.now();
  while (Date.now() - start < waitReadyMs) {
    try {
      const { captchaInput, captchaImage, queryButton } = await getFormHandles(page);
      if (
        (await captchaInput.count()) > 0 &&
        (await captchaImage.count()) > 0 &&
        (await queryButton.count()) > 0
      ) {
        return true;
      }
    } catch {}
    await sleep(1000);
  }
  return false;
}

async function readPageSummary(page) {
  return page.evaluate(() => {
    const text = document.body ? document.body.innerText : "";
    const countMatch = text.match(/显示记录共\s*(\d+)\s*条/);
    return {
      url: location.href,
      text: text.slice(0, 4000),
      count: countMatch ? Number(countMatch[1]) : null,
    };
  });
}

function classifyOutcome(summaryBefore, summaryAfter) {
  const afterText = summaryAfter.text || "";
  if (/验证码.{0,6}(错误|不正确|有误|重新输入)/.test(afterText)) {
    return "captcha_error";
  }
  if (summaryAfter.count !== null) {
    if (summaryBefore.count === null) {
      return "success";
    }
    if (summaryAfter.count === summaryBefore.count) {
      return "success_same_count";
    }
    return "success_new_count";
  }
  return "unknown";
}

async function main() {
  const context = await chromium.launchPersistentContext(userDataDir, {
    executablePath: chromePath,
    headless: false,
    viewport: { width: 1440, height: 1400 },
    locale: "zh-CN",
    timezoneId: "Asia/Shanghai",
    userAgent:
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    args: [
      "--disable-blink-features=AutomationControlled",
      "--disable-dev-shm-usage",
      "--window-size=1440,1400",
    ],
  });

  try {
    await context.addInitScript(() => {
      Object.defineProperty(navigator, "webdriver", { get: () => undefined });
    });

    const page = context.pages()[0] || (await context.newPage());
    await page.goto(targetUrl, { waitUntil: "domcontentloaded", timeout: 60000 }).catch(() => {});

    log(`浏览器已打开。请在 ${Math.round(waitReadyMs / 1000)} 秒内手动完成进站验证，并把页面停在可查询状态。`);
    const ready = await waitUntilReady(page);
    if (!ready) {
      throw new Error("query form not detected within wait window");
    }

    log("检测到查询表单，开始 OCR 测试。请不要手动操作页面。");

    const attemptsData = [];
    const { captchaInput, captchaImage, queryButton } = await getFormHandles(page);

    for (let i = 1; i <= attempts; i += 1) {
      const before = await readPageSummary(page);
      const imagePath = path.join(outputDir, `${ts()}-attempt-${i}.png`);
      await captchaImage.screenshot({ path: imagePath });

      const ocr = runOcr(imagePath);
      const guess = ocr.best || "";

      if (!guess) {
        attemptsData.push({
          attempt: i,
          guess,
          outcome: "empty_guess",
          imagePath,
          ocr,
        });
        await captchaImage.click({ timeout: 3000 }).catch(() => {});
        await sleep(1500);
        continue;
      }

      await captchaInput.fill("");
      await captchaInput.fill(guess);

      await Promise.allSettled([
        page.waitForLoadState("networkidle", { timeout: perAttemptTimeoutMs }),
        queryButton.click({ timeout: 5000 }),
      ]);

      await sleep(2000);
      const after = await readPageSummary(page);
      const outcome = classifyOutcome(before, after);

      attemptsData.push({
        attempt: i,
        guess,
        outcome,
        beforeCount: before.count,
        afterCount: after.count,
        imagePath,
        ocr,
      });

      log(`attempt ${i}/${attempts}: guess=${guess} outcome=${outcome}`);

      await captchaImage.click({ timeout: 3000 }).catch(() => {});
      await sleep(1500);
    }

    const successes = attemptsData.filter((item) =>
      item.outcome.startsWith("success")
    ).length;
    const report = {
      targetUrl,
      attempts,
      successes,
      successRate: attempts > 0 ? successes / attempts : 0,
      capturedAt: new Date().toISOString(),
      attemptsData,
    };

    const reportPath = path.join(outputDir, `report-${ts()}.json`);
    fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
    log(`测试完成。success=${successes}/${attempts}，报告已写入 ${reportPath}`);
  } finally {
    await context.close();
  }
}

main().catch((error) => {
  console.error(error.stack || String(error));
  process.exit(1);
});
