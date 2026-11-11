import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";

const html = readFileSync(new URL("./page/settings.html", import.meta.url), "utf8");
const [, script] = html.match(/<script>([\s\S]*?)<\/script>/);
const original = "fixture/original";
const vlModel = "fixture/visual";
const omniModel = "fixture/audio";
const invalidOmni = "agy-cli/gemini-fixture";
const warning = "该渠道不支持音频输入";

class Element {
  value = "";
  disabled = false;
  textContent = "";
  className = "";
  hidden = false;
  options = [];
  listeners = {};

  addEventListener(event, listener) { this.listeners[event] = listener; }
  replaceChildren() { this.options = []; this.value = ""; }
  append(option) {
    this.options.push(option);
    if (this.options.length === 1) this.value = option.value;
  }
}

async function createPage(omni = original) {
  const elements = { status: new Element(), refresh: new Element(), "omni-warning": new Element() };
  const buttons = {};
  for (const key of ["vl", "omni"]) {
    const select = elements[key] = new Element();
    const button = buttons[key] = new Element();
    elements[key + "-form"] = { querySelector: selector => selector === "button" ? button : select };
    elements[key + "-feedback"] = new Element();
  }
  const models = [original, vlModel, omniModel, invalidOmni].map(id => ({
    id, name: id, omniWarning: id === invalidOmni ? warning : "",
  }));
  const backend = { connected: true, vl: original, omni, omniWarning: omni === invalidOmni ? warning : "" };
  const writes = [];
  const response = data => ({ ok: true, status: 200, json: async () => data });
  await runInNewContext(script, {
    URLSearchParams,
    location: { hash: "", reload() { throw new Error("Unexpected page reload"); } },
    document: {
      querySelector: () => ({ content: "fixture-token" }),
      getElementById: id => elements[id],
      createElement: () => new Element(),
      querySelectorAll: () => [elements.vl, elements.omni, buttons.vl, buttons.omni],
    },
    fetch: async (path, options) => {
      if (!options.body) {
        assert.equal(path, "api/settings");
        return response({ ...backend, models });
      }
      assert.equal(path, "api/models");
      const update = JSON.parse(options.body);
      Object.assign(backend, update);
      backend.omniWarning = backend.omni === invalidOmni ? warning : "";
      const snapshot = { ...backend };
      return new Promise(resolve => writes.push({ update, respond: () => resolve(response(snapshot)) }));
    },
  });
  return {
    elements, buttons, backend, writes,
    choose(key, value) {
      assert.equal(elements[key].disabled, false);
      assert.ok(elements[key].options.some(option => option.value === value));
      elements[key].value = value;
      elements[key].listeners.change();
    },
    save(key) {
      assert.equal(buttons[key].disabled, false);
      return buttons[key].listeners.click();
    },
  };
}

test("reordered independent save responses preserve the other model's saved baseline", async () => {
  const page = await createPage();
  page.choose("vl", vlModel);
  const vlSave = page.save("vl");
  page.choose("omni", omniModel);
  const omniSave = page.save("omni");
  assert.equal(page.writes.length, 2);
  page.writes[1].respond();
  await omniSave;
  page.writes[0].respond();
  await vlSave;
  assert.equal(page.buttons.vl.disabled, true);
  assert.equal(page.buttons.omni.disabled, true);

  page.choose("omni", original);
  assert.equal(page.backend.omni, omniModel);
  assert.equal(page.buttons.omni.disabled, false);
  const restore = page.save("omni");
  assert.deepEqual(page.writes[2].update, { omni: original });
  page.writes[2].respond();
  await restore;
  assert.equal(page.backend.omni, original);
  assert.equal(page.buttons.omni.disabled, true);
});

test("editing during a save keeps that field locked and preserves the new choice", async () => {
  const page = await createPage();
  page.choose("vl", vlModel);
  const firstSave = page.save("vl");
  page.choose("vl", omniModel);
  assert.equal(page.buttons.vl.disabled, true);
  assert.equal(page.writes.length, 1);
  page.choose("omni", omniModel);
  assert.equal(page.buttons.omni.disabled, false);

  page.writes[0].respond();
  await firstSave;
  assert.equal(page.backend.vl, vlModel);
  assert.equal(page.elements.vl.value, omniModel);
  assert.equal(page.buttons.vl.disabled, false);
  assert.equal(page.elements.omni.value, omniModel);
  assert.equal(page.buttons.omni.disabled, false);
  const nextSave = page.save("vl");
  page.writes[1].respond();
  await nextSave;
  assert.equal(page.backend.vl, omniModel);
  assert.equal(page.buttons.vl.disabled, true);
});

test("saving VL preserves an existing unsupported Omni choice and its warning", async () => {
  const page = await createPage(invalidOmni);
  assert.equal(page.elements.omni.value, invalidOmni);
  assert.equal(page.elements["omni-warning"].textContent, warning);
  assert.equal(page.elements["omni-warning"].hidden, false);
  assert.equal(page.buttons.omni.disabled, true);
  page.choose("vl", vlModel);
  const save = page.save("vl");
  page.writes[0].respond();
  await save;
  assert.equal(page.backend.omni, invalidOmni);
  assert.equal(page.elements.omni.value, invalidOmni);
  assert.equal(page.elements["omni-warning"].textContent, warning);
  assert.equal(page.elements["omni-warning"].hidden, false);
  assert.equal(page.buttons.omni.disabled, true);
});
