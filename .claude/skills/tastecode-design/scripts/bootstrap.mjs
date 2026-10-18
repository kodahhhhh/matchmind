import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { cpSync, existsSync, mkdirSync, readFileSync, realpathSync, renameSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

export const revision = '3ee7948d8ec9d3f2ac538c7ac9b6c9fa8e345c28';
export const scripts = path.dirname(fileURLToPath(import.meta.url));
export const home = path.resolve(process.env.TASTECODE_DESIGN_HOME || path.join(homedir(), '.local/share/tastecode'));
export const runtime = path.join(home, 'runtime', revision);
export const source = path.join(home, 'upstream');
const manifest = readFileSync(path.join(scripts, 'runtime-package.json'));
const lock = () => readFileSync(path.join(scripts, 'runtime-package-lock.json'));
const version = () => createHash('sha256').update(readFileSync(fileURLToPath(import.meta.url))).update(manifest).update(lock()).digest('hex');

function exec(command, args, cwd) {
  const r = spawnSync(command, args, { cwd, stdio: 'inherit' });
  if (r.error) throw r.error;
  if (r.status !== 0) throw new Error(`${command} failed (${r.status})`);
}
export async function setup() {
  mkdirSync(home, { recursive: true });
  const guard = path.join(home, '.design-setup-lock');
  try { mkdirSync(guard); } catch { throw new Error(`Setup is already locked at ${guard}. Check for an active setup before removing a stale lock.`); }
  try {
    if (!existsSync(source)) {
      exec('git', ['clone', '--no-checkout', 'https://github.com/Leonxlnx/tastecode.git', source], home);
      exec('git', ['checkout', '--detach', revision], source);
    }
    const sha = spawnSync('git', ['rev-parse', 'HEAD'], { cwd: source, encoding: 'utf8' });
    if (sha.status !== 0 || sha.stdout.trim() !== revision) throw new Error(`Expected TasteCode ${revision} at ${source}; preserve that checkout and select another TASTECODE_DESIGN_HOME if it differs.`);
    const dirty = spawnSync('git', ['status', '--porcelain', '--untracked-files=no'], { cwd: source, encoding: 'utf8' });
    if (dirty.status !== 0 || dirty.stdout.trim()) throw new Error('TasteCode source has tracked edits; refusing to extract an unverified revision.');
    const library = path.join(source, 'packages/design-agent/references/library');
    const catalog = JSON.parse(readFileSync(path.join(library, 'catalog.json')));
    let images = 0;
    for (const entry of catalog.references) for (const [key, hash] of Object.entries(entry.sha256)) {
      const file = realpathSync(path.resolve(library, entry[key]));
      if (!file.startsWith(realpathSync(library) + path.sep)) throw new Error('Reference leaves the library');
      if (createHash('sha256').update(readFileSync(file)).digest('hex') !== hash) throw new Error(`Reference hash mismatch: ${entry.id}/${key}`);
      images++;
    }
    mkdirSync(runtime, { recursive: true });
    cpSync(path.join(scripts, 'runtime-package.json'), path.join(runtime, 'package.json'));
    cpSync(path.join(scripts, 'runtime-package-lock.json'), path.join(runtime, 'package-lock.json'));
    exec('npm', ['ci', '--no-audit', '--no-fund'], runtime);
    // Keep the complete original core, tests, references and notices outside the app.
    for (const pkg of ['design-agent', 'proc']) {
      const dest = path.join(runtime, 'packages', pkg);
      mkdirSync(dest, { recursive: true });
      cpSync(path.join(source, 'packages', pkg, 'src'), path.join(dest, 'src'), { recursive: true });
      cpSync(path.join(source, 'packages', pkg, 'package.json'), path.join(dest, 'package.json'));
      const refs = path.join(source, 'packages', pkg, 'references');
      if (existsSync(refs) && !existsSync(path.join(dest, 'references'))) symlinkSync(refs, path.join(dest, 'references'), 'dir');
    }
    for (const name of ['LICENSE', 'NOTICE', 'THIRD_PARTY_NOTICES.md']) cpSync(path.join(source, name), path.join(runtime, name));
    cpSync(path.join(source, 'licenses'), path.join(runtime, 'licenses'), { recursive: true });
    const core = path.join(runtime, 'packages/design-agent');
    const quality = path.join(core, 'src/source-quality.ts');
    const original = readFileSync(quality, 'utf8');
    const marker = 'function designSourceFiles(workspacePath: string): string[] {';
    if (!original.includes(marker)) throw new Error('Source-scope patch no longer matches the pinned source');
    writeFileSync(quality, original.replace(marker, `${marker}
  // Modified for the portable skill: caller supplies an enumerated, confined source scope.
  // Without this option, original full-workspace behavior is preserved (including tests).
  if (process.env.TASTECODE_SOURCE_FILES) {
    const files: unknown = JSON.parse(process.env.TASTECODE_SOURCE_FILES);
    if (!Array.isArray(files) || !files.every(f => typeof f === 'string' && normalizeWorkspaceFile(f)))
      throw new Error('Invalid portable Design source scope');
    return [...new Set(files as string[])].sort();
  }
`));
    const server = path.join(runtime, 'server');
    mkdirSync(server, { recursive: true });
    for (const name of ['design-preview-runner', 'design-static-preview', 'api-workspace-paths', 'safe-command-environment'])
      cpSync(path.join(source, 'apps/server/src', `${name}.ts`), path.join(server, `${name}.ts`));
    for (const name of ['preview-dom-audit', 'preview-settle'])
      cpSync(path.join(source, 'apps/desktop/src', `${name}.ts`), path.join(server, `${name}.ts`));
    const { build } = await import(pathToFileURL(path.join(runtime, 'node_modules/esbuild/lib/main.js')));
    const shared = { bundle: true, platform: 'node', format: 'esm', target: 'node22', packages: 'external' };
    await build({ ...shared, entryPoints: [path.join(core, 'src/index.ts')], outfile: path.join(core, 'dist/index.js') });
    const proc = path.join(runtime, 'packages/proc/src');
    await build({ ...shared, entryPoints: [path.join(server, 'design-preview-runner.ts')], outfile: path.join(runtime, 'preview.mjs'), alias: {
      '@harness/proc/cli': path.join(proc, 'cli.ts'), '@harness/proc/desktop-path': path.join(proc, 'desktop-path.ts'),
    } });
    for (const name of ['preview-dom-audit', 'preview-settle'])
      await build({ ...shared, entryPoints: [path.join(server, `${name}.ts`)], outfile: path.join(runtime, `${name}.mjs`) });
    const receipt = { revision, build: version(), references: catalog.references.length, images, source, runtime };
    const temp = path.join(runtime, 'installation.tmp');
    writeFileSync(temp, JSON.stringify(receipt, null, 2) + '\n');
    renameSync(temp, path.join(runtime, 'installation.json'));
    return receipt;
  } finally { rmSync(guard, { recursive: true }); }
}
export function installation() {
  try {
    const receipt = JSON.parse(readFileSync(path.join(runtime, 'installation.json')));
    if (receipt.revision !== revision || receipt.build !== version()) throw new Error('outdated');
    return receipt;
  } catch { throw new Error(`Run node ${path.join(scripts, 'tastecode.mjs')} setup first.`); }
}
export async function modules() {
  installation();
  return {
    core: await import(pathToFileURL(path.join(runtime, 'packages/design-agent/dist/index.js'))),
    preview: await import(pathToFileURL(path.join(runtime, 'preview.mjs'))),
    playwright: await import(pathToFileURL(path.join(runtime, 'node_modules/playwright/index.mjs'))),
    audit: await import(pathToFileURL(path.join(runtime, 'preview-dom-audit.mjs'))),
    settle: await import(pathToFileURL(path.join(runtime, 'preview-settle.mjs'))),
  };
}
