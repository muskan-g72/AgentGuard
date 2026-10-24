// Copy-only packaging: no framework, bundler, dependencies, or backend files.
import { cp, mkdir, readFile, readdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const output = path.resolve(process.argv[2] || path.join(root, 'dist/food-sites'));
if (output === root || output === path.dirname(root)) throw new Error('Choose a separate output directory.');
await mkdir(output, { recursive: true });
const allowed = new Set(['foodhub', 'quickbite', 'dinedash', 'food-demo', 'data', 'vercel.json', '.vercel', '.gitignore']);
for (const item of await readdir(output)) if (!allowed.has(item)) throw new Error('Output contains unrelated files; choose an empty directory.');
const publicFiles = new Set(['vercel.json', 'data/food.json',
  ...['foodhub', 'quickbite', 'dinedash'].flatMap(slug => ['index.html', 'dish.html', 'checkout.html', 'confirmation.html'].map(file => `${slug}/${file}`)),
  ...['index.html', 'site.mjs', 'logic.mjs', 'styles.css', 'plate.svg'].map(file => `food-demo/${file}`)]);
async function inspect(directory, prefix = '') {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const relative = prefix + entry.name;
    if (relative === '.vercel' || relative === '.gitignore') continue;
    if (entry.isSymbolicLink()) throw new Error('Output contains a symlink; choose an empty directory.');
    if (entry.isDirectory()) await inspect(path.join(directory, entry.name), relative + '/');
    else if (!publicFiles.has(relative)) throw new Error('Output contains unrelated files; choose an empty directory.');
  }
}
await inspect(output);
for (const slug of ['foodhub', 'quickbite', 'dinedash']) {
  await mkdir(path.join(output, slug), { recursive: true });
  for (const file of ['index.html', 'dish.html', 'checkout.html', 'confirmation.html']) await cp(path.join(root, slug, file), path.join(output, slug, file));
}
await mkdir(path.join(output, 'food-demo'), { recursive: true });
for (const file of ['index.html', 'site.mjs', 'logic.mjs', 'styles.css', 'plate.svg']) await cp(path.join(root, 'food-demo', file), path.join(output, 'food-demo', file));
await mkdir(path.join(output, 'data'), { recursive: true });
await cp(path.join(root, 'data/food.json'), path.join(output, 'data/food.json'));
await cp(path.join(root, 'food-demo/vercel.json'), path.join(output, 'vercel.json'));
const data = JSON.parse(await readFile(path.join(output, 'data/food.json'), 'utf8'));
if (!data.synthetic || data.options.length !== 7) throw new Error('Expected seven labelled synthetic dishes.');
console.log('Static food-only bundle:', output);
