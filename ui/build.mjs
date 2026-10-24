import { cp, mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const out = path.join(root, 'dist');
await mkdir(path.join(out, 'ui'), { recursive: true });
for (const name of ['index.html', 'checkout.html', 'confirmation.html', 'app.js', 'checkout.js', 'styles.css']) await cp(path.join(root, name), path.join(out, name));
for (const name of ['index.html', 'styles.css', 'icon.svg', 'app.mjs', 'api.mjs', 'mock-api.mjs', 'format.mjs']) await cp(path.join(root, 'ui', name), path.join(out, 'ui', name));
console.log('Built booking sandbox and /ui/. Only public frontend files were copied to dist/.');
