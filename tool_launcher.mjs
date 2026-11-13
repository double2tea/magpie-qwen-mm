// Parent monitoring must start before uvx prepares dependencies and Python exists.
import { spawn } from 'node:child_process';

const [worker, upstream] = process.argv.slice(2);
const parent = Number(process.env.QWEN_MM_HOST_PID);
if (!worker || !upstream || !Number.isSafeInteger(parent) || parent <= 1) throw new Error('Invalid native tool launch');
const child = spawn('uvx', ['--python', '3.13', '--from', upstream, 'python', worker], { stdio: 'inherit', windowsHide: true });
const watch = setInterval(() => {
  try { process.kill(parent, 0); }
  catch (error) {
    if (error.code !== 'ESRCH') throw error;
    if (process.platform !== 'win32') process.kill(-process.pid, 'SIGKILL');
    child.kill('SIGKILL');
    process.exit(1);
  }
}, 1000);
child.on('error', () => { clearInterval(watch); process.exit(1); });
child.on('close', code => { clearInterval(watch); process.exit(code ?? 1); });
