import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";

const chromePath =
  process.env.CHROME_PATH ||
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const targetUrl =
  process.env.TARGET_URL ||
  "https://www.fangdi.com.cn/old_house/old_house.html";
const runHeadless = (process.env.HEADLESS || "true") !== "false";
const debugPort = Number(process.env.CDP_PORT || "9224");
const outputDir = path.resolve(process.cwd(), "artifacts", "fangdi");

fs.mkdirSync(outputDir, { recursive: true });

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForJson(url, attempts = 60) {
  for (let i = 0; i < attempts; i += 1) {
    try {
      const response = await fetch(url);
      if (response.ok) {
        return response.json();
      }
    } catch {}
    await sleep(250);
  }
  throw new Error(`Timed out waiting for ${url}`);
}

function launchChrome() {
  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "fangdi-chrome-"));
  const args = [
    `--remote-debugging-port=${debugPort}`,
    `--user-data-dir=${userDataDir}`,
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-background-networking",
    "--disable-background-timer-throttling",
    "--disable-default-apps",
    "--disable-sync",
    "--disable-blink-features=AutomationControlled",
    "--window-size=1440,1400",
    "about:blank",
  ];
  if (runHeadless) {
    args.unshift("--headless=new", "--disable-gpu");
  }
  return {
    userDataDir,
    proc: spawn(chromePath, args, {
      stdio: "ignore",
    }),
  };
}

async function connectCdp() {
  const version = await waitForJson(`http://127.0.0.1:${debugPort}/json/version`);
  const ws = new WebSocket(version.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    ws.addEventListener("open", resolve, { once: true });
    ws.addEventListener("error", reject, { once: true });
  });
  let id = 0;
  const pending = new Map();
  let sessionId = null;
  const requests = [];
  const responses = [];

  ws.addEventListener("message", (event) => {
    const message = JSON.parse(event.data.toString());
    if (message.id && pending.has(message.id)) {
      const { resolve, reject } = pending.get(message.id);
      pending.delete(message.id);
      if (message.error) {
        reject(new Error(JSON.stringify(message.error)));
      } else {
        resolve(message.result);
      }
      return;
    }

    if (message.method === "Target.attachedToTarget") {
      sessionId = message.params.sessionId;
      return;
    }

    if (
      message.method === "Network.requestWillBeSent" &&
      message.params?.request?.url?.includes("fangdi.com.cn")
    ) {
      requests.push({
        url: message.params.request.url,
        method: message.params.request.method,
        type: message.params.type,
      });
    }

    if (
      message.method === "Network.responseReceived" &&
      message.params?.response?.url?.includes("fangdi.com.cn")
    ) {
      responses.push({
        url: message.params.response.url,
        status: message.params.response.status,
        mimeType: message.params.response.mimeType,
      });
    }
  });

  function send(method, params = {}, sid = sessionId) {
    const payload = { id: ++id, method, params };
    if (sid) {
      payload.sessionId = sid;
    }
    ws.send(JSON.stringify(payload));
    return new Promise((resolve, reject) => {
      pending.set(payload.id, { resolve, reject });
    });
  }

  return { ws, send, requests, responses, getSessionId: () => sessionId };
}

function jsString(value) {
  return JSON.stringify(value);
}

async function main() {
  const { proc } = launchChrome();
  let ws;

  try {
    const cdp = await connectCdp();
    ws = cdp.ws;
    const { send, requests, responses, getSessionId } = cdp;

    const { targetId } = await send("Target.createTarget", { url: "about:blank" }, null);
    await send("Target.attachToTarget", { targetId, flatten: true }, null);

    for (let i = 0; i < 80 && !getSessionId(); i += 1) {
      await sleep(100);
    }
    if (!getSessionId()) {
      throw new Error("Failed to attach to target session");
    }

    const userAgent =
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36";

    await send("Page.enable");
    await send("Runtime.enable");
    await send("Network.enable");
    await send("Network.setUserAgentOverride", {
      userAgent,
      acceptLanguage: "zh-CN,zh;q=0.9,en;q=0.8",
      platform: "macOS",
    });
    await send("Page.addScriptToEvaluateOnNewDocument", {
      source: `
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en-US'] });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4] });
      `,
    });

    await send("Page.navigate", { url: targetUrl });
    await sleep(12000);

    const pageState = await send("Runtime.evaluate", {
      expression: `
        (() => {
          const text = document.body ? document.body.innerText : '';
          const forms = Array.from(document.forms || []).map(form => ({
            action: form.action,
            method: form.method,
            id: form.id,
            name: form.name,
            inputNames: Array.from(form.querySelectorAll('input,select,textarea')).map(el => ({
              tag: el.tagName,
              name: el.name,
              id: el.id,
              type: el.type || null,
              value: el.value || null
            }))
          }));
          const links = Array.from(document.querySelectorAll('a')).slice(0, 30).map(a => ({
            text: (a.innerText || '').trim(),
            href: a.href
          }));
          return {
            title: document.title,
            text,
            html: document.documentElement.outerHTML,
            forms,
            links,
            location: location.href
          };
        })()
      `,
      returnByValue: true,
    });

    const cookies = await send("Network.getCookies", {
      urls: [targetUrl],
    });

    const screenshot = await send("Page.captureScreenshot", {
      format: "png",
      captureBeyondViewport: true,
    });

    const result = {
      targetUrl,
      headless: runHeadless,
      pageState: pageState.result.value,
      cookies: cookies.cookies,
      requests,
      responses,
      capturedAt: new Date().toISOString(),
    };

    fs.writeFileSync(
      path.join(outputDir, runHeadless ? "probe-headless.json" : "probe-headful.json"),
      JSON.stringify(result, null, 2)
    );
    fs.writeFileSync(
      path.join(outputDir, runHeadless ? "probe-headless.png" : "probe-headful.png"),
      Buffer.from(screenshot.data, "base64")
    );

    console.log(JSON.stringify({
      title: result.pageState.title,
      location: result.pageState.location,
      textPreview: result.pageState.text.slice(0, 300),
      forms: result.pageState.forms,
      cookies: result.cookies.map((cookie) => ({
        name: cookie.name,
        domain: cookie.domain,
        httpOnly: cookie.httpOnly,
      })),
      responses: result.responses.slice(0, 10),
      artifactJson: path.join(outputDir, runHeadless ? "probe-headless.json" : "probe-headful.json"),
      artifactPng: path.join(outputDir, runHeadless ? "probe-headless.png" : "probe-headful.png"),
    }, null, 2));
  } finally {
    try {
      ws?.close();
    } catch {}
    proc.kill("SIGTERM");
  }
}

main().catch((error) => {
  console.error(error.stack || String(error));
  process.exit(1);
});
