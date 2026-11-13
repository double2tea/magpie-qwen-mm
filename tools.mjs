import { spawn } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';

const manifest = JSON.parse(readFileSync(new URL('./tools.json', import.meta.url), 'utf8'));
const upstream = 'qwen-mm-plugins[api,search,video-spatio] @ git+https://github.com/QwenLM/Qwen-MM-Plugins.git@qwen-mm-plugins-video-spatio-v1.1.0';
const worker = fileURLToPath(new URL('./tool_worker.py', import.meta.url));
const launcher = fileURLToPath(new URL('./tool_launcher.mjs', import.meta.url));

export function createTools({ spawnWorker = spawn, waitMs = 20000, timeoutMs = 15 * 60 * 1000, retentionMs = 30 * 60 * 1000 } = {}) {
  const jobs = new Map();
  const owner = ctx => {
    if (typeof ctx.agent !== 'string' || !ctx.agent) throw new Error('Calling Agent identity is required');
    return ctx.agent;
  };
  function prune() {
    for (const [id, job] of jobs) if (job.finished && Date.now() - job.finished > retentionMs) jobs.delete(id);
  }
  function result(job) {
    return { job_id: job.id, status: job.status, ...(job.status === 'completed' ? { result: job.result } : {}), ...(job.error ? { error: job.error } : {}) };
  }
  function find(id, ctx) {
    prune();
    const job = jobs.get(id);
    if (!job || job.owner !== owner(ctx)) throw new Error('Task not found for this Agent; it may have expired or the plugin host restarted');
    return job;
  }
  async function execute(spec, args, ctx) {
    const agent = owner(ctx);
    if (ctx.abort?.aborted) throw new Error('Tool call was cancelled');
    prune();
    if ([...jobs.values()].filter(job => job.status === 'running').length >= 8) throw new Error('Eight tasks are already running; poll or cancel existing tasks');
    if (jobs.size >= 128) {
      const oldest = [...jobs.values()].find(job => job.finished);
      if (oldest) jobs.delete(oldest.id);
    }
    const job = { id: randomUUID(), owner: agent, status: 'running' };
    jobs.set(job.id, job);
    const child = spawnWorker(process.execPath, [launcher, worker, upstream], { stdio: ['pipe', 'pipe', 'pipe'], detached: process.platform !== 'win32', windowsHide: true, env: { ...process.env, QWEN_MM_HOST_PID: String(process.pid) } });
    let output = '', outputBytes = 0;
    let complete;
    const done = new Promise(resolve => { complete = resolve; });
    const finish = (status, value) => {
      if (job.status !== 'running') return;
      job.status = status;
      job.finished = Date.now();
      if (status === 'completed') job.result = value;
      else job.error = value;
      clearTimeout(deadline);
      job.cancel = () => {};
      output = '';
      const expiry = setTimeout(() => jobs.delete(job.id), retentionMs);
      expiry.unref();
      complete();
    };
    function stop(reason) {
      if (job.status !== 'running') return;
      finish('failed', reason);
      const signal = name => {
        try {
          if (process.platform !== 'win32' && Number.isInteger(child.pid)) process.kill(-child.pid, name);
          else child.kill(name);
        } catch (error) { if (error.code !== 'ESRCH') throw error; }
      };
      signal('SIGTERM');
      const kill = setTimeout(() => signal('SIGKILL'), 1000);
      kill.unref();
    }
    const deadline = setTimeout(() => stop('Task exceeded its 15-minute runtime limit'), timeoutMs);
    deadline.unref();
    job.cancel = () => stop('Task cancelled');
    child.stdout.setEncoding('utf8');
    child.stdout.on('data', data => {
      if (job.status !== 'running') return;
      outputBytes += Buffer.byteLength(data);
      if (outputBytes > 32 * 1024 * 1024) return stop('Task result exceeded 32 MiB');
      output += data.toString();
    });
    // Drain SDK/progress logs without exposing keys, signed URLs or file contents.
    child.stderr.on('data', () => {});
    child.on('error', error => finish('failed', error.code === 'ENOENT' ? 'uvx is not on the Magpie plugin host PATH' : 'Unable to start the Python tool worker'));
    child.stdin.on('error', () => {});
    child.on('close', code => {
      if (job.status !== 'running') return;
      let value;
      try { value = JSON.parse(output); }
      catch { return finish('failed', 'Tool worker returned an invalid or incomplete result'); }
      if (code !== 0 || value.error) return finish('failed', value.error || 'Tool worker exited unsuccessfully');
      finish('completed', value.result);
    });
    child.stdin.end(JSON.stringify({ entry: spec.entry, name: spec.name, arguments: args }));
    const abort = () => job.cancel();
    ctx.abort?.addEventListener('abort', abort, { once: true });
    let wait;
    try {
      await Promise.race([done, new Promise(resolve => { wait = setTimeout(resolve, waitMs); })]);
      return result(job);
    } finally {
      clearTimeout(wait);
      ctx.abort?.removeEventListener('abort', abort);
    }
  }
  const tools = {};
  for (const spec of manifest) {
    tools['qwen_' + spec.name] = {
      description: spec.description + '\nNative Qwen-MM tool. Returns status and result; if running, poll qwen_task_status with job_id. Tasks are owned by the calling Agent and expire after completion or host restart.',
      args: spec.inputSchema,
      execute: (args, ctx) => execute(spec, args, ctx),
    };
  }
  tools.qwen_task_status = {
    description: 'Read a Qwen-MM task started by this Agent. Completed results expire after 30 minutes or host restart. Call again later if running.',
    args: { type: 'object', properties: { job_id: { type: 'string' } }, required: ['job_id'], additionalProperties: false },
    execute: async (args, ctx) => result(find(args.job_id, ctx)),
  };
  tools.qwen_task_cancel = {
    description: 'Cancel a running Qwen-MM task started by this Agent. Completed tasks are left unchanged.',
    args: tools.qwen_task_status.args,
    execute: async (args, ctx) => { const job = find(args.job_id, ctx); job.cancel(); return result(job); },
  };
  return tools;
}
