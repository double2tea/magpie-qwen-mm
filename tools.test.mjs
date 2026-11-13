import { test } from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { PassThrough } from 'node:stream';
import { createTools } from './tools.mjs';
import { spawn } from 'node:child_process';
import { mkdtempSync, writeFileSync, chmodSync, readFileSync, existsSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, delimiter } from 'node:path';
import { fileURLToPath } from 'node:url';

function worker(reply, delay = 1) {
  return () => {
    const child = new EventEmitter();
    child.stdin = new PassThrough(); child.stdout = new PassThrough(); child.stderr = new PassThrough();
    child.kill = () => { setImmediate(() => child.emit('close', 1)); return true; };
    child.stdin.on('finish', () => {
      if (reply === undefined) return;
      setTimeout(() => { child.stdout.emit('data', Buffer.from(JSON.stringify(reply))); child.emit('close', reply.error ? 1 : 0); }, delay);
    });
    return child;
  };
}
const context = agent => ({ agent, abort: new AbortController().signal });

test('all packaged tool schemas register with valid strings and no startup process', () => {
  let starts = 0;
  const tools = createTools({ spawnWorker: () => { starts++; } });
  assert.equal(Object.keys(tools).length, 26);
  assert.equal(starts, 0);
  for (const [name, spec] of Object.entries(tools)) {
    assert.match(name, /^[A-Za-z0-9_-]{1,48}$/);
    assert.equal(typeof spec.description, 'string');
    assert.equal(spec.args.type, 'object');
    assert.equal(typeof spec.execute, 'function');
  }
});
test('completed tool result returns under the native deadline', async () => {
  const tools = createTools({ spawnWorker: worker({ result: { text: 'hello' } }), waitMs: 100 });
  const result = await tools.qwen_transcribe_audio.execute({ audio_path: '/fixture.wav' }, context('test'));
  assert.equal(result.status, 'completed');
  assert.equal(result.result.text, 'hello');
});
test('slow tool returns a ticket, then only its Agent can read the result', async () => {
  const tools = createTools({ spawnWorker: worker({ result: 'finished' }, 30), waitMs: 1 });
  const result = await tools.qwen_web_search.execute({ query: 'fixture' }, context('test'));
  assert.equal(result.status, 'running');
  await assert.rejects(tools.qwen_task_status.execute({ job_id: result.job_id }, context('other')), /not found/);
  await new Promise(resolve => setTimeout(resolve, 40));
  assert.equal((await tools.qwen_task_status.execute({ job_id: result.job_id }, context('test'))).result, 'finished');
});
test('pending tasks can be cancelled by their Agent', async () => {
  const tools = createTools({ spawnWorker: worker(undefined), waitMs: 1 });
  const result = await tools.qwen_web_search.execute({}, context('test'));
  const cancelled = await tools.qwen_task_cancel.execute({ job_id: result.job_id }, context('test'));
  assert.equal(cancelled.status, 'failed');
  assert.match(cancelled.error, /cancelled/);
});
test('upstream failures are explicit task failures', async () => {
  const tools = createTools({ spawnWorker: worker({ error: 'ValueError: tool execution failed' }), waitMs: 100 });
  const result = await tools.qwen_web_search.execute({}, context('test'));
  assert.equal(result.status, 'failed');
  assert.match(result.error, /ValueError/);
});
test('caller identity and pre-cancelled calls fail before process start', async () => {
  let calls = 0;
  const tools = createTools({ spawnWorker: () => calls++ });
  await assert.rejects(tools.qwen_web_search.execute({}, {}), /identity/);
  const abort = new AbortController(); abort.abort();
  await assert.rejects(tools.qwen_web_search.execute({}, { agent: 'test', abort: abort.signal }), /cancelled/);
  assert.equal(calls, 0);
});

test('split UTF-8 chunks preserve non-ASCII results', async () => {
  const spawnWorker = () => {
    const child = new EventEmitter();
    child.stdin = new PassThrough(); child.stdout = new PassThrough(); child.stderr = new PassThrough(); child.kill = () => true;
    child.stdin.on('finish', () => {
      const bytes = Buffer.from(JSON.stringify({ result: '中文🎵' }));
      for (const byte of bytes) child.stdout.write(Buffer.from([byte]));
      child.emit('close', 0);
    });
    return child;
  };
  const tools = createTools({ spawnWorker, waitMs: 100 });
  assert.equal((await tools.qwen_web_search.execute({}, context('test'))).result, '中文🎵');
});
test('finished tickets expire without another task starting', async () => {
  const tools = createTools({ spawnWorker: worker({ result: 'ok' }), waitMs: 100, retentionMs: 5 });
  const job = await tools.qwen_web_search.execute({}, context('test'));
  await new Promise(resolve => setTimeout(resolve, 15));
  await assert.rejects(tools.qwen_task_status.execute({ job_id: job.job_id }, context('test')), /expired/);
});
test('runtime deadline marks unfinished work as failed', async () => {
  const tools = createTools({ spawnWorker: worker(undefined), waitMs: 50, timeoutMs: 5 });
  const job = await tools.qwen_web_search.execute({}, context('test'));
  assert.equal(job.status, 'failed');
  assert.match(job.error, /runtime limit/);
});

test('host death kills dependency preparation before Python starts', {skip: process.platform === 'win32'}, async () => {
  const directory = mkdtempSync(join(tmpdir(), 'qwen-native-supervisor-'));
  const marker = join(directory, 'started');
  const executable = join(directory, 'uvx');
  writeFileSync(executable, '#!' + process.execPath + '\n' + 'require("node:fs").writeFileSync(process.env.QWEN_TEST_MARKER,String(process.pid)); process.on("SIGTERM",()=>{}); setInterval(()=>{},1000);');
  chmodSync(executable, 0o700);
  const host = spawn(process.execPath, ['-e', 'setInterval(()=>{},1000)'], {stdio:'ignore'});
  const launcher = spawn(process.execPath, [fileURLToPath(new URL('./tool_launcher.mjs', import.meta.url)), 'unused.py', 'fixture'], {
    detached: true, stdio: 'ignore', env:{...process.env,PATH:directory+delimiter+process.env.PATH,QWEN_MM_HOST_PID:String(host.pid),QWEN_TEST_MARKER:marker},
  });
  try {
    const deadline=Date.now()+5000;
    while(!existsSync(marker) && Date.now()<deadline) await new Promise(resolve=>setTimeout(resolve,20));
    assert.ok(existsSync(marker),'dependency process started');
    const child=Number(readFileSync(marker,'utf8'));
    const stopped=new Promise(resolve=>launcher.once('close',resolve));
    host.kill('SIGKILL');
    await Promise.race([stopped,new Promise((_,reject)=>setTimeout(()=>reject(new Error('supervisor did not stop')),4000).unref())]);
    await new Promise(resolve=>setTimeout(resolve,100));
    assert.throws(()=>process.kill(child,0), /ESRCH/);
  } finally {
    host.kill('SIGKILL');
    try{process.kill(-launcher.pid,'SIGKILL');}catch(error){if(error.code!=='ESRCH')throw error;}
    rmSync(directory,{recursive:true,force:true});
  }
});
