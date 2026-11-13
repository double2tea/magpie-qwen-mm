import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, chmodSync, rmSync, readdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import { setupPlan, dependencyChecks } from './setup.mjs';

test('plan uses actual installation path and argv, including spaces', () => {
  const directory = resolve(tmpdir(), 'plugin with spaces');
  const plan = setupPlan(directory);
  assert.deepEqual(plan.map(entry => entry.name), ['qwen-mm-audio', 'qwen-mm-search', 'qwen-mm-video-spatio']);
  for (const entry of plan) {
    assert.equal(entry.command, 'uvx');
    assert.equal(entry.args[3], join(directory, 'qwen_mm_gateway.py'));
    assert.equal(entry.args[4], entry.name.slice('qwen-mm-'.length));
  }
});

test('dependency check reports only supplied PATH executables', () => {
  const directory = mkdtempSync(join(tmpdir(), 'qwen-setup-check-'));
  try {
    writeFileSync(join(directory, 'ffmpeg'), 'fixture');
    chmodSync(join(directory, 'ffmpeg'), 0o755);
    const result = dependencyChecks({ PATH: directory }, 'darwin');
    assert.equal(result.find(entry => entry.command === 'ffmpeg').found, true);
    assert.equal(result.find(entry => entry.command === 'uvx').found, false);
  } finally { rmSync(directory, { recursive: true }); }
});

test('CLI emits a plan without writing configuration', () => {
  const directory = mkdtempSync(join(tmpdir(), 'qwen-setup-home-'));
  try {
    const result = spawnSync(process.execPath, ['setup.mjs'], { cwd: import.meta.dirname, env: { ...process.env, HOME: directory }, encoding: 'utf8' });
    assert.equal(result.status, 0, result.stderr);
    const plan = JSON.parse(result.stdout);
    assert.equal(plan.wrapperExists, true);
    assert.equal(plan.servers.length, 3);
    assert.deepEqual(readdirSync(directory), []);
    const invalid = spawnSync(process.execPath, ['setup.mjs', '--apply'], { cwd: import.meta.dirname, encoding: 'utf8' });
    assert.notEqual(invalid.status, 0);
  } finally { rmSync(directory, { recursive: true }); }
});
