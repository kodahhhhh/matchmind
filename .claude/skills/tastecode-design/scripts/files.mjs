import { createHash, randomUUID } from 'node:crypto';
import { existsSync, lstatSync, mkdirSync, readFileSync, readdirSync, realpathSync, renameSync, rmSync, writeFileSync } from 'node:fs';
import path from 'node:path';

export const hash = value => createHash('sha256').update(value).digest('hex');
export const fileHash = file => hash(readFileSync(file));
export function inside(root, name, mustExist = true) {
  const base = realpathSync(root);
  const target = path.resolve(base, name);
  if (target !== base && !target.startsWith(base + path.sep)) throw new Error(`Path leaves workspace: ${name}`);
  let ancestor = target;
  while (!existsSync(ancestor)) ancestor = path.dirname(ancestor);
  const real = realpathSync(ancestor);
  if (real !== base && !real.startsWith(base + path.sep)) throw new Error(`Symlink leaves workspace: ${name}`);
  if (mustExist && !existsSync(target)) throw new Error(`Missing file: ${name}`);
  return target;
}
export function privateDirectory(directory) {
  mkdirSync(directory, { recursive: true, mode: 0o700 });
  if (lstatSync(directory).isSymbolicLink() || !lstatSync(directory).isDirectory()) throw new Error(`Expected real directory: ${directory}`);
}
export function atomic(file, value) {
  privateDirectory(path.dirname(file));
  const tmp = `${file}.${randomUUID()}.tmp`;
  try {
    writeFileSync(tmp, JSON.stringify(value, null, 2) + '\n', { mode: 0o600, flag: 'wx' });
    renameSync(tmp, file);
  } finally { rmSync(tmp, { force: true }); }
}
export function readJSON(file) {
  if (lstatSync(file).size > 16_000_000) throw new Error('JSON input exceeds 16 MB');
  return JSON.parse(readFileSync(file, 'utf8'));
}
const excluded = new Set(['.git', '.taste', '.ax', '.next', '.next-ax', '.turbo', 'node_modules', '.pnpm-store', 'dist', 'build', 'out', 'coverage', 'vendor']);
const sources = /\.(?:css|scss|sass|less|html|[cm]?js|jsx|ts|tsx|vue|svelte|svg)$/i;
export function scopedFiles(workspace, scopes, sourceOnly = false) {
  const files = new Set();
  let count = 0;
  function walk(file) {
    if (++count > 25_000) throw new Error('Scope exceeds 25,000 entries; select the actual feature paths');
    const stat = lstatSync(file);
    if (stat.isSymbolicLink()) throw new Error(`Choose the real source path instead of a symlink: ${file}`);
    if (stat.isDirectory()) {
      for (const name of readdirSync(file)) if (!excluded.has(name)) walk(path.join(file, name));
    } else if (stat.isFile()) {
      const rel = path.relative(workspace, file).split(path.sep).join('/');
      if (/(?:^|\/)\.env(?:\.|$)|(?:^|\/)(?:auth\.json|credentials|id_rsa|id_ed25519|\.npmrc)$/i.test(rel)) return;
      if (!sourceOnly || (sources.test(rel) && !/(?:\.(?:test|spec)\.[cm]?[jt]sx?$|(?:^|\/)__tests__\/)/i.test(rel))) files.add(rel);
    }
  }
  for (const scope of scopes) {
    const target = inside(workspace, scope, false);
    if (existsSync(target)) walk(target);
  }
  return [...files].sort();
}
export function snapshot(workspace, scopes) {
  return Object.fromEntries(scopedFiles(workspace, scopes).map(f => [f, fileHash(inside(workspace, f))]));
}
export function inScope(file, scopes) {
  return scopes.some(scope => scope === '.' || file === scope || file.startsWith(scope.replace(/\/$/, '') + '/'));
}
export function sourceKey(state) {
  return hash(JSON.stringify(snapshot(state.workspace, state.scopes)));
}
export async function locked(run, callback) {
  const directory = path.join(run, '.lock');
  try { mkdirSync(directory); } catch { throw new Error(`Run is busy: ${directory}. If interrupted, verify no command is active before removing this lock directory.`); }
  try { return await callback(); } finally { rmSync(directory, { recursive: true }); }
}
