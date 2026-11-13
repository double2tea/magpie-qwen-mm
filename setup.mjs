import { fileURLToPath } from 'node:url';
import { resolve, dirname, join } from 'node:path';
import { accessSync, constants, existsSync } from 'node:fs';
import { spawnSync } from 'node:child_process';

export const upstream = 'qwen-mm-plugins[api,search,video-spatio] @ git+https://github.com/QwenLM/Qwen-MM-Plugins.git@qwen-mm-plugins-video-spatio-v1.1.0';

export function setupPlan(directory) {
  const wrapper = resolve(directory, 'qwen_mm_gateway.py');
  return ['audio', 'search', 'video-spatio'].map(entry => ({
    name: 'qwen-mm-' + entry,
    command: 'uvx',
    args: ['--from', upstream, 'python', wrapper, entry],
  }));
}

export function dependencyChecks(environment = process.env, platform = process.platform) {
  return ['git', 'node', 'python3', 'uvx', 'ffmpeg', 'ffprobe'].map(command => {
    const extensions = platform === 'win32' ? ['', ...(environment.PATHEXT || '.EXE;.CMD;.BAT').split(';')] : [''];
    const separator = platform === 'win32' ? ';' : ':';
    const found = (environment.PATH || '').split(separator).filter(Boolean).some(directory => extensions.some(extension => {
      try { accessSync(join(directory, command + extension), platform === 'win32' ? constants.F_OK : constants.X_OK); return true; }
      catch (error) { if (['ENOENT', 'ENOTDIR', 'EACCES'].includes(error.code)) return false; throw error; }
    }));
    return { command, found };
  });
}

export function main(args) {
  if (args.length && (args.length !== 1 || !['--check', '--help'].includes(args[0]))) throw new Error('Usage: node setup.mjs [--check|--help]');
  if (args[0] === '--help') {
    console.log('Print a read-only MCP configuration plan for this installation. --check also checks executable availability on PATH. No dependencies are installed and no Magpie settings are written.');
    return;
  }
  const directory = dirname(fileURLToPath(import.meta.url));
  const plan = { installation: directory, wrapperExists: existsSync(join(directory, 'qwen_mm_gateway.py')), servers: setupPlan(directory),
    note: 'Add only the desired entries through Magpie Library → MCP and choose their Agent assignments. Existing entries are not replaced. First uvx use downloads pinned upstream dependencies.' };
  if (args[0] === '--check') {
    plan.dependencies = dependencyChecks();
    // Check only installed interpreter versions; never resolve uv environments or download a model.
    plan.versions = ['node', 'python3'].map(command => {
      if (!plan.dependencies.find(item => item.command === command).found) return { command, available: false };
      const result = spawnSync(command, ['--version'], { encoding: 'utf8', timeout: 5000 });
      return { command, available: result.status === 0, version: (result.stdout || result.stderr || '').trim(), error: result.error?.message };
    });
  }
  console.log(JSON.stringify(plan, null, 2));
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main(process.argv.slice(2));
