#!/usr/bin/env node
import { existsSync, lstatSync, mkdirSync, readdirSync, realpathSync, symlinkSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const canonical = realpathSync(path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..'));
const workspace = path.resolve(canonical, '../../..');
const directories = readdirSync(workspace, { withFileTypes: true })
  .filter(entry => entry.isDirectory() && entry.name.startsWith('.') && entry.name !== '.agents')
  .map(entry => path.join(workspace, entry.name, 'skills'))
  .filter(directory => existsSync(directory));
// Cursor's installed CLI may predate common-directory discovery.
for (const vendor of ['.claude', '.cursor', '.grok', '.kiro']) {
  if (existsSync(path.join(workspace, vendor))) directories.push(path.join(workspace, vendor, 'skills'));
}
const links = [];
for (const directory of new Set(directories)) {
  mkdirSync(directory, { recursive: true });
  const file = path.join(directory, 'tastecode-design');
  let present = false;
  try { lstatSync(file); present = true; } catch (error) { if (error.code !== 'ENOENT') throw error; }
  if (present) {
    if (!lstatSync(file).isSymbolicLink() || realpathSync(file) !== canonical) throw new Error(`Preserving conflicting existing skill: ${file}`);
  } else symlinkSync(path.relative(directory, canonical), file, 'dir');
  links.push({ path: file, resolvesTo: realpathSync(file) });
}
process.stdout.write(JSON.stringify({ canonical, links }, null, 2) + '\n');
