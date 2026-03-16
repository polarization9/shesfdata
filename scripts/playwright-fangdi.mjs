import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { chromium } from "playwright-core";

const chromePath =
  process.env.CHROME_PATH ||
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const targetUrl =
  process.env.TARGET_URL ||
  "https://www.fangdi.com.cn/old_house/old_house.html";
const headless = (process.env.HEADLESS || "false") === "true";
const holdMs = Number(process.env.HOLD_MS || "15000");
const outputDir = path.resolve(process.cwd(), "artifacts", "fangdi");

fs.mkdirSync(outputDir, { recursive: true });

const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "pw-fangdi-"));

function summarizeResponse(response) {
  return {
    url: response.url(),
    status: response.status(),
    fromServiceWorker: response.fromServiceWorker(),
  };
}

async function main() {
  const traffic = [];
  const context = await chromium.launchPersistentContext(userDataDir, {
    executablePath: chromePath,
    headless,
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
      Object.defineProperty(navigator, "languages", {
        get: () => ["zh-CN", "zh", "en-US", "en"],
      });
      Object.defineProperty(navigator, "plugins", {
        get: () => [1, 2, 3, 4, 5],
      });
    });

    const page = context.pages()[0] || (await context.newPage());

    page.on("request", (request) => {
      if (!request.url().includes("fangdi.com.cn")) {
        return;
      }
      traffic.push({
        kind: "request",
        url: request.url(),
        method: request.method(),
        resourceType: request.resourceType(),
        postData: request.postData(),
      });
    });

    page.on("response", async (response) => {
      if (!response.url().includes("fangdi.com.cn")) {
        return;
      }
      traffic.push({
        kind: "response",
        ...summarizeResponse(response),
      });
    });

    const response = await page.goto(targetUrl, {
      waitUntil: "domcontentloaded",
      timeout: 60000,
    });

    await page.waitForTimeout(holdMs);

    const result = {
      targetUrl,
      headless,
      initialStatus: response?.status() ?? null,
      finalUrl: page.url(),
      title: await page.title(),
      bodyText: ((await page.locator("body").innerText().catch(() => "")) || "").slice(
        0,
        3000
      ),
      forms: await page.evaluate(() =>
        Array.from(document.forms || []).map((form) => ({
          action: form.action,
          method: form.method,
          id: form.id,
          name: form.name,
          inputs: Array.from(form.querySelectorAll("input,select,textarea")).map((el) => ({
            tag: el.tagName,
            type: el.type || null,
            name: el.name || null,
            id: el.id || null,
            value: el.value || null,
          })),
        }))
      ),
      links: await page.evaluate(() =>
        Array.from(document.querySelectorAll("a"))
          .slice(0, 50)
          .map((a) => ({
            text: (a.innerText || "").trim(),
            href: a.href,
          }))
      ),
      cookies: await context.cookies(),
      traffic,
      capturedAt: new Date().toISOString(),
    };

    const basename = headless ? "playwright-headless" : "playwright-headful";
    const jsonPath = path.join(outputDir, `${basename}.json`);
    const pngPath = path.join(outputDir, `${basename}.png`);

    await page.screenshot({ path: pngPath, fullPage: true });
    fs.writeFileSync(jsonPath, JSON.stringify(result, null, 2));

    console.log(
      JSON.stringify(
        {
          initialStatus: result.initialStatus,
          finalUrl: result.finalUrl,
          title: result.title,
          bodyTextPreview: result.bodyText.slice(0, 500),
          forms: result.forms,
          cookieNames: result.cookies.map((cookie) => cookie.name),
          traffic: result.traffic.slice(0, 12),
          jsonPath,
          pngPath,
        },
        null,
        2
      )
    );
  } finally {
    await context.close();
  }
}

main().catch((error) => {
  console.error(error.stack || String(error));
  process.exit(1);
});
