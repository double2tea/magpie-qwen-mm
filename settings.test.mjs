import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync, readFileSync, rmSync, statSync } from "node:fs";
import { join } from "node:path";
import { saveModels, readSettings, omniWarning } from "./settings.mjs";

const allowed = [{ id: "google/gemini-3.8-flash" }, { id: "qwen-cn/qwen3.8-omni-flash" }];
const initial = '# unrelated settings stay intact\nDASHSCOPE_BASE_URL=http://127.0.0.1:3425/v1\nDASHSCOPE_API_KEY=test-gateway-key\nQWEN_MM_API_VL_MODEL=qwen-cn/qwen3.8-omni-flash\nQWEN_MM_API_OMNI_MODEL=qwen-cn/qwen3.8-omni-flash\nCUSTOM=value\n';

test("saving either model preserves the other, credentials, and unrelated entries", () => {
  const dir = mkdtempSync("/tmp/qwen-mm-settings-test-");
  try {
    const file = join(dir, "config");
    writeFileSync(file, initial, { mode: 0o600 });
    saveModels({ vl: allowed[0].id }, file, allowed);
    assert.equal(readSettings(file).omni, allowed[1].id);
    saveModels({ omni: allowed[0].id }, file, allowed);
    assert.equal(readSettings(file).vl, allowed[0].id);
    const result = readFileSync(file, "utf8");
    assert.ok(result.includes("DASHSCOPE_API_KEY=test-gateway-key\n"));
    assert.ok(result.includes("CUSTOM=value\n"));
    assert.ok(result.startsWith("# unrelated settings stay intact\n"));
    assert.equal(statSync(file).mode & 0o777, 0o600);
    assert.ok(!JSON.stringify(readSettings(file)).includes("test-gateway-key"));
  } finally { rmSync(dir, { recursive: true }); }
});

test("invalid models and disconnected state leave the configuration unchanged", () => {
  const dir = mkdtempSync("/tmp/qwen-mm-settings-test-");
  try {
    const file = join(dir, "config");
    writeFileSync(file, initial);
    for (const input of [{ vl: "missing/model" }, { vl: "x\nDASHSCOPE_API_KEY=bad" }, { unexpected: "value" }, { constructor: "value" }]) {
      assert.throws(() => saveModels(input, file, allowed));
      assert.equal(readFileSync(file, "utf8"), initial);
    }
    writeFileSync(file, "QWEN_MM_API_VL_MODEL=google/gemini-3.8-flash\n");
    assert.throws(() => saveModels({ omni: allowed[1].id }, file, allowed), /接入/);
  } finally { rmSync(dir, { recursive: true }); }
});

test("known visual-only channel stays visible but cannot silently save as an audio model", () => {
  const dir = mkdtempSync("/tmp/qwen-mm-channel-test-");
  try {
    const file = join(dir, "config");
    const current = initial.replace("QWEN_MM_API_OMNI_MODEL=qwen-cn/qwen3.8-omni-flash", "QWEN_MM_API_OMNI_MODEL=agy-cli/gemini-3.8-flash");
    writeFileSync(file, current);
    assert.match(readSettings(file).omniWarning, /音频/);
    assert.throws(() => saveModels({ omni: "agy-cli/gemini-3.8-flash" }, file, [...allowed, {id: "agy-cli/gemini-3.8-flash"}]), /音频/);
    assert.equal(readFileSync(file, "utf8"), current);
    saveModels({ vl: allowed[0].id }, file, allowed);
    assert.equal(readSettings(file).omni, "agy-cli/gemini-3.8-flash");
    saveModels({ omni: allowed[1].id }, file, allowed);
    assert.equal(readSettings(file).omniWarning, "");
    assert.equal(omniWarning(allowed[0].id), "");
  } finally { rmSync(dir, { recursive: true }); }
});

test("a fresh installation without managed config is shown as disconnected", () => {
  const dir = mkdtempSync("/tmp/qwen-mm-fresh-test-");
  try { assert.equal(readSettings(join(dir, "missing-config")).connected, false); }
  finally { rmSync(dir, { recursive: true }); }
});
