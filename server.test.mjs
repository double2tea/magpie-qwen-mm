import { test, after } from "node:test";
import { createServer } from "node:http";
import { spawn } from "node:child_process";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync, statSync, unlinkSync } from "node:fs";
import { join } from "node:path";
import { once } from "node:events";

const root = mkdtempSync("/tmp/qwen-mm-server-test-");
process.env.MAGPIE_CONFIG_DIR = root;
after(() => rmSync(root, { recursive: true, force: true }));
const { startServer } = await import("./server.mjs");
const version = JSON.parse(readFileSync(new URL("./package.json", import.meta.url), "utf8")).version;

test("a page opened before service restart can save with the same credential", async () => {
  mkdirSync(join(root, "qwen-mm"));
  writeFileSync(join(root, "qwen-mm/config"), "DASHSCOPE_BASE_URL=http://127.0.0.1:3425/v1\nDASHSCOPE_API_KEY=test-gateway-key\nQWEN_MM_API_VL_MODEL=google/gemini-3.8-flash\nQWEN_MM_API_OMNI_MODEL=qwen-cn/qwen3.8-omni-flash\n");
  writeFileSync(join(root, "providers.json"), JSON.stringify({ providers: [
    { id: "google", models: ["gemini-3.8-flash"] },
    { id: "qwen-cn", models: ["qwen3.8-omni-flash"] },
  ], groups: [] }));
  let server;
  try {
    server = await startServer({ listenPort: 0 });
    let base = `http://127.0.0.1:${server.address().port}`;
    const html = await (await fetch(base)).text();
    const token = html.match(/name="qwen-mm-form" content="([^"]+)"/)[1];
    assert.ok(html.includes(`v${version}`));
    assert.equal(statSync(join(root, "qwen-mm/page-token")).mode & 0o777, 0o600);
    assert.equal(readFileSync(join(root, "qwen-mm/page-token"), "utf8"), token);
    server.close();
    await once(server, "close");
    server = await startServer({ listenPort: 0 });
    base = `http://127.0.0.1:${server.address().port}`;
    const headers = { "Content-Type": "application/json", "X-Qwen-MM-Form": token, Origin: "null" };
    const saved = await fetch(base + "/api/models", { method: "POST", headers, body: JSON.stringify({ omni: "google/gemini-3.8-flash" }) });
    assert.equal(saved.status, 200);
    assert.equal(saved.headers.get("access-control-allow-origin"), "null");
    const settings = await saved.json();
    assert.equal(settings.omni, "google/gemini-3.8-flash");
    assert.equal(settings.vl, "google/gemini-3.8-flash");
    assert.ok(!JSON.stringify(settings).includes("test-gateway-key"));
    const rejected = await fetch(base + "/api/models", { method: "POST", headers: { ...headers, "X-Qwen-MM-Form": "wrong" }, body: JSON.stringify({ omni: "qwen-cn/qwen3.8-omni-flash" }) });
    assert.equal(rejected.status, 403);
    assert.equal(JSON.parse(await (await fetch(base + "/api/settings", { headers })).text()).omni, "google/gemini-3.8-flash");
    const duplicate = await startServer({ listenPort: server.address().port });
    assert.equal(duplicate, null);
    assert.equal((await (await fetch(base + "/health")).json()).version, version);
  } finally {
    if (server?.listening) {
      server.close();
      await once(server, "close");
    }
  }
});

test("concurrent cold starts publish a complete credential before readers can see it", async () => {
  const tokenFile = join(root, "qwen-mm/page-token");
  unlinkSync(tokenFile);
  const moduleURL = new URL("./server.mjs", import.meta.url).href;
  const child = `
    import {startServer} from ${JSON.stringify(moduleURL)};
    import {readFileSync} from 'node:fs';
    const server = await startServer({listenPort:0});
    const html = await (await fetch('http://127.0.0.1:'+server.address().port)).text();
    const token = html.match(/name="qwen-mm-form" content="([^"]+)"/)[1];
    if (!/^[a-f0-9]{64}$/.test(token) || readFileSync(${JSON.stringify(tokenFile)}, 'utf8') !== token) process.exitCode = 1;
    await new Promise(resolve=>server.close(resolve));
  `;
  await Promise.all(Array.from({ length: 8 }, () => new Promise((resolve, reject) => {
    const process = spawn(globalThis.process.execPath, ["--input-type=module", "-e", child], { env: globalThis.process.env, stdio: ["ignore", "ignore", "pipe"] });
    let stderr = "";
    process.stderr.on("data", chunk => { stderr += chunk; });
    process.on("error", reject);
    process.on("close", code => code === 0 ? resolve() : reject(new Error(stderr || `worker exited ${code}`)));
  })));
  assert.match(readFileSync(tokenFile, "utf8"), /^[a-f0-9]{64}$/);
  const token = readFileSync(tokenFile, "utf8");
  writeFileSync(tokenFile, "");
  try { await assert.rejects(startServer({ listenPort: 0 }), /credential is invalid/); }
  finally { writeFileSync(tokenFile, token); }
});

test("an owner exiting during the port probe leaves the lifecycle free to retry", async () => {
  const departing = createServer((request, response) => {
    response.socket.destroy();
    departing.close();
  });
  await new Promise(resolve => departing.listen(0, "127.0.0.1", resolve));
  const listenPort = departing.address().port;
  assert.equal(await startServer({ listenPort }), null);
  if (departing.listening) await once(departing, "close");
  const server = await startServer({ listenPort });
  try {
    assert.equal((await fetch(`http://127.0.0.1:${listenPort}/health`)).status, 200);
  } finally {
    server.close();
    await once(server, "close");
  }
});
