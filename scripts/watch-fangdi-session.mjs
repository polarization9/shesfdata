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
const debugPort = Number(process.env.CDP_PORT || "9225");
const watchMs = Number(process.env.WATCH_MS || "180000");
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
  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "fangdi-watch-"));
  const args = [
    `--remote-debugging-port=${debugPort}`,
    `--user-data-dir=${userDataDir}`,
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-blink-features=AutomationControlled",
    "--window-size=1440,1400",
    targetUrl,
  ];

  return {
    userDataDir,
    proc: spawn(chromePath, args, {
      stdio: "ignore",
      detached: false,
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
  const sessions = new Map();
  const traffic = [];

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
      sessions.set(message.params.sessionId, message.params.targetInfo);
      return;
    }

    if (message.method === "Network.requestWillBeSent") {
      const request = message.params?.request;
      if (request?.url?.includes("fangdi.com.cn")) {
        traffic.push({
          ts: Date.now(),
          kind: "request",
          sessionId: message.sessionId || null,
          url: request.url,
          method: request.method,
          type: message.params.type || null,
          postData: request.postData || null,
          headers: request.headers || {},
        });
      }
      return;
    }

    if (message.method === "Network.responseReceived") {
      const response = message.params?.response;
      if (response?.url?.includes("fangdi.com.cn")) {
        traffic.push({
          ts: Date.now(),
          kind: "response",
          sessionId: message.sessionId || null,
          url: response.url,
          status: response.status,
          mimeType: response.mimeType,
          headers: response.headers || {},
        });
      }
    }
  });

  function send(method, params = {}, sessionId = null) {
    const payload = { id: ++id, method, params };
    if (sessionId) {
      payload.sessionId = sessionId;
    }
    ws.send(JSON.stringify(payload));
    return new Promise((resolve, reject) => {
      pending.set(payload.id, { resolve, reject });
    });
  }

  return { ws, send, sessions, traffic };
}

async function attachExistingTargets(send, sessions) {
  const targets = await send("Target.getTargets");
  for (const targetInfo of targets.targetInfos) {
    if (targetInfo.type !== "page") {
      continue;
    }
    try {
      const { sessionId } = await send(
        "Target.attachToTarget",
        { targetId: targetInfo.targetId, flatten: true },
        null
      );
      sessions.set(sessionId, targetInfo);
      await send("Page.enable", {}, sessionId);
      await send("Network.enable", {}, sessionId);
      await send("Runtime.enable", {}, sessionId);
    } catch {}
  }
}

async function snapshotPages(send, sessions) {
  const snapshots = [];
  for (const [sessionId, targetInfo] of sessions.entries()) {
    if (targetInfo.type !== "page") {
      continue;
    }
    try {
      const state = await send(
        "Runtime.evaluate",
        {
          expression: `
            (() => ({
              href: location.href,
              title: document.title,
              text: document.body ? document.body.innerText.slice(0, 2000) : '',
              html: document.documentElement.outerHTML.slice(0, 20000)
            }))()
          `,
          returnByValue: true,
        },
        sessionId
      );
      snapshots.push({
        sessionId,
        targetInfo,
        pageState: state.result.value,
      });
    } catch {}
  }
  return snapshots;
}

async function main() {
  const { proc } = launchChrome();
  let ws;

  try {
    const { ws: cdpWs, send, sessions, traffic } = await connectCdp();
    ws = cdpWs;
    await send("Target.setDiscoverTargets", { discover: true }, null);
    await send("Target.setAutoAttach", {
      autoAttach: true,
      waitForDebuggerOnStart: false,
      flatten: true,
    });

    await attachExistingTargets(send, sessions);

    console.log(
      `Chrome 已打开，接下来 ${Math.round(watchMs / 1000)} 秒内请手动完成验证、查询、切换区/板块、翻页。`
    );
    await sleep(watchMs);

    const pageSnapshots = await snapshotPages(send, sessions);
    const result = {
      targetUrl,
      watchMs,
      capturedAt: new Date().toISOString(),
      traffic,
      pageSnapshots,
    };

    const outputPath = path.join(outputDir, "manual-watch.json");
    fs.writeFileSync(outputPath, JSON.stringify(result, null, 2));
    console.log(`已写入 ${outputPath}`);
    console.log(`共记录 ${traffic.length} 条 fangdi 请求/响应事件`);
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
