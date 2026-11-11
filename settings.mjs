import { readFileSync, writeFileSync, renameSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";

export const configRoot = process.env.MAGPIE_CONFIG_DIR || join(homedir(), ".config/magpie");
export const configFile = join(configRoot, "qwen-mm/config");
const modelKeys = { vl: "QWEN_MM_API_VL_MODEL", omni: "QWEN_MM_API_OMNI_MODEL" };

export function readConfig(file = configFile) {
  const text = readFileSync(file, "utf8");
  const values = {};
  for (const line of text.split(/\r?\n/)) {
    const match = line.match(/^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$/);
    if (!match) continue;
    let value = match[2];
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) value = value.slice(1, -1);
    values[match[1]] = value;
  }
  return { text, values };
}

export function readSettings(file = configFile) {
  let values;
  try { ({ values } = readConfig(file)); }
  catch (error) {
    if (error.code !== "ENOENT") throw error;
    values = {};
  }
  return {
    connected: Boolean(values.DASHSCOPE_BASE_URL && values.DASHSCOPE_API_KEY),
    vl: values[modelKeys.vl] || "",
    omni: values[modelKeys.omni] || "",
    omniWarning: omniWarning(values[modelKeys.omni] || ""),
  };
}

export function omniWarning(model) {
  return model.startsWith("agy-cli/gemini-") ? "agy-cli Gemini 当前渠道不支持音频输入，请选择 Gemini Native 或 Qwen Omni。" : "";
}

export function modelChoices(root = configRoot) {
  const { providers, groups } = JSON.parse(readFileSync(join(root, "providers.json"), "utf8"));
  const models = [];
  for (const provider of providers) {
    if (provider.off) continue;
    for (const model of provider.models || []) {
      if (typeof model === "string") models.push({ id: `${provider.id}/${model}`, name: `${model} · ${provider.name || provider.id}`, omniWarning: omniWarning(`${provider.id}/${model}`) });
    }
  }
  for (const group of groups || []) models.push({ id: `group/${group.id}`, name: `${group.name || group.id} · 路由组` });
  return models.sort((a, b) => a.name.localeCompare(b.name));
}

export function saveModels(update, file = configFile, allowed = modelChoices()) {
  if (!update || typeof update !== "object" || Array.isArray(update) || !Object.keys(update).length || Object.keys(update).some(key => !Object.hasOwn(modelKeys, key))) {
    throw new Error("请选择 VL 或 Omni 模型。");
  }
  const valid = new Set(allowed.map(model => model.id));
  for (const value of Object.values(update)) {
    if (typeof value !== "string" || !valid.has(value)) throw new Error("模型已停用或不在当前 Magpie 配置中，请刷新列表。");
  }
  if (update.omni && omniWarning(update.omni)) throw new Error(omniWarning(update.omni));
  const { text, values } = readConfig(file);
  if (!values.DASHSCOPE_BASE_URL || !values.DASHSCOPE_API_KEY) throw new Error("请先在 Agent 页面接入 magpie-agent-qwen-mm-plugins。");
  const pending = new Map(Object.entries(update).map(([key, value]) => [modelKeys[key], value]));
  const seen = new Set();
  const lines = text.split(/\r?\n/).map(line => {
    const key = line.match(/^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=/)?.[1];
    if (!pending.has(key)) return line;
    seen.add(key);
    return `${key}=${pending.get(key)}`;
  });
  for (const [key, value] of pending) if (!seen.has(key)) lines.push(`${key}=${value}`);
  const temporary = `${file}.pending`;
  writeFileSync(temporary, lines.join("\n").replace(/\n*$/, "\n"), { mode: 0o600 });
  renameSync(temporary, file);
  return readSettings(file);
}
