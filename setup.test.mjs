import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { checkInstallation } from './setup.mjs';

test('read-only check describes native tools without a manual MCP plan', () => {
  const plan = checkInstallation(import.meta.dirname, { PATH: '' });
  assert.equal(plan.nativeTools, 26);
  assert.equal(plan.servers, undefined);
  assert.ok(plan.files.every(file => file.found));
  assert.ok(plan.dependencies.every(dep => !dep.found));
});
test('check CLI never writes configuration', () => {
  const directory = mkdtempSync(join(tmpdir(), 'qwen-native-check-'));
  try {
    const result = spawnSync(process.execPath, ['setup.mjs', '--check'], { cwd: import.meta.dirname, env: { ...process.env, HOME: directory }, encoding: 'utf8' });
    assert.equal(result.status, 0, result.stderr);
    assert.equal(JSON.parse(result.stdout).nativeTools, 26);
    assert.deepEqual(readdirSync(directory), []);
  } finally { rmSync(directory, {recursive: true}); }
});
