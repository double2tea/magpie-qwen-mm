import { createServer } from "node:http";
import { readFileSync, writeFileSync, mkdirSync, linkSync, unlinkSync } from "node:fs";
import { join } from "node:path";
import { randomBytes } from "node:crypto";
import { fileURLToPath } from "node:url";
import { configRoot, readSettings, saveModels, modelChoices } from "./settings.mjs";

export const port = 3496;
const identity = "magpie-qwen-mm-settings";

export async function startServer({ listenPort = port } = {}) {
  const directory = join(configRoot, "qwen-mm");
  mkdirSync(directory, { recursive: true, mode: 0o700 });
  const tokenFile = join(directory, "page-token");
  // Publish a complete credential before another Magpie host can read its name.
  const candidate = join(directory, `.page-token-${randomBytes(16).toString("hex")}`);
  writeFileSync(candidate, randomBytes(32).toString("hex"), { flag: "wx", mode: 0o600 });
  try {
    try { linkSync(candidate, tokenFile); }
    catch (error) { if (error.code !== "EEXIST") throw error; }
  } finally { unlinkSync(candidate); }
  const token = readFileSync(tokenFile, "utf8");
  if (!/^[a-f0-9]{64}$/.test(token)) throw new Error("Qwen MM page credential is invalid; restore page-token from a private backup.");
  const version = JSON.parse(readFileSync(new URL("./package.json", import.meta.url), "utf8")).version;
  const htmlFile = fileURLToPath(new URL("./page/settings.html", import.meta.url));
  const server = createServer(async (request, response) => {
    response.setHeader("Cache-Control", "no-store");
    response.setHeader("X-Content-Type-Options", "nosniff");
    const send = (status, data) => {
      response.writeHead(status, { "Content-Type": "application/json; charset=utf-8" });
      response.end(JSON.stringify(data));
    };
    const path = new URL(request.url, `http://127.0.0.1:${port}`).pathname;
    if (path.startsWith("/api/")) {
      response.setHeader("Access-Control-Allow-Origin", "null");
      response.setHeader("Access-Control-Allow-Headers", "content-type, x-qwen-mm-form");
      response.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
      response.setHeader("Vary", "Origin");
      if (request.method === "OPTIONS") { response.writeHead(204); return response.end(); }
    }
    if (request.method === "GET" && path === "/health") return send(200, { app: identity, version });
    if (request.method === "GET" && path === "/") {
      response.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
      return response.end(readFileSync(htmlFile, "utf8").replace("__FORM_TOKEN__", token).replace("__PLUGIN_VERSION__", version));
    }
    if (request.headers["x-qwen-mm-form"] !== token) return send(403, { error: "页面已过期，请重新打开 Qwen MM。" });
    try {
      if (request.method === "GET" && path === "/api/settings") return send(200, { ...readSettings(), models: modelChoices() });
      if (request.method === "POST" && path === "/api/models") {
        let body = "";
        for await (const chunk of request) {
          body += chunk;
          if (body.length > 8192) return send(413, { error: "请求过大。" });
        }
        const update = JSON.parse(body);
        return send(200, saveModels(update));
      }
      return send(404, { error: "页面不存在。" });
    } catch (error) {
      return send(400, { error: error.message });
    }
  });
  return new Promise((resolve, reject) => {
    server.once("error", async error => {
      // Magpie's desktop, web and CLI hosts can load the same plugin concurrently.
      if (error.code !== "EADDRINUSE" || listenPort === 0) return reject(error);
      let response;
      try {
        response = await fetch(`http://127.0.0.1:${listenPort}/health`, { signal: AbortSignal.timeout(2000) });
      } catch {
        // The previous host can exit after bind fails; let the lifecycle retry ownership.
        return resolve(null);
      }
      try {
        const data = await response.json();
        if (data.app !== identity) throw new Error(`Port ${listenPort} is used by another service`);
        resolve(null);
      } catch (probeError) { reject(probeError); }
    });
    server.listen(listenPort, "127.0.0.1", () => resolve(server));
  });
}
