import { existsSync, readFileSync, accessSync, constants, realpathSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export function checkInstallation(directory, environment = process.env) {
  const required = ['tools.mjs', 'tools.json', 'tool_launcher.mjs', 'tool_worker.py', 'qwen_mm_gateway.py'];
  const dependencies = ['uvx', 'ffmpeg', 'ffprobe'].map(command => {
    const found = (environment.PATH || '').split(process.platform === 'win32' ? ';' : ':').filter(Boolean).some(path => {
      const suffixes = process.platform === 'win32' ? ['', '.exe', '.cmd'] : [''];
      return suffixes.some(suffix => {
        try { accessSync(join(path, command + suffix), constants.X_OK); return true; }
        catch (error) { if (['ENOENT', 'ENOTDIR', 'EACCES'].includes(error.code)) return false; throw error; }
      });
    });
    return { command, found };
  });
  const files = required.map(name => ({ name, found: existsSync(join(directory, name)) }));
  const manifest = JSON.parse(readFileSync(join(directory, 'tools.json'), 'utf8'));
  return { version: JSON.parse(readFileSync(join(directory, 'package.json'), 'utf8')).version, files, dependencies,
    nativeTools: manifest.length + 2,
    registration: 'Magpie registers this plugin through its native tools hook. No manual MCP commands or paths are required.',
    firstUse: 'The first uvx tool call downloads the pinned upstream runtime. It may return a task ticket while preparing dependencies.' };
}

if (process.argv[1] && realpathSync(resolve(process.argv[1])) === fileURLToPath(import.meta.url)) {
  if (process.argv.slice(2).some(arg => arg !== '--check') || process.argv.length > 3) throw new Error('Usage: node setup.mjs [--check]');
  console.log(JSON.stringify(checkInstallation(dirname(fileURLToPath(import.meta.url))), null, 2));
}
