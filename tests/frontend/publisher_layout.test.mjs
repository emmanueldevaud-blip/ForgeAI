// Vérifie les étapes médias/ajustement aux largeurs mobile et bureau.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { coverCrop } from '../../src/public/js/editor/editorGeometry.js';

const css = fs.readFileSync(new URL('../../src/public/css/publisher.css', import.meta.url), 'utf8');
const indexHtml = fs.readFileSync(new URL('../../src/public/index.html', import.meta.url), 'utf8');
const file = new URL('../../src/public/js/editors/PublisherPostEditor.js', import.meta.url);
let source = fs.readFileSync(file, 'utf8');
source = source.replace(/^import\s[\s\S]*?from\s+['"][^'"]+['"];?\s*$/gm, '');
source = source.replace(/export class/g, 'class').replace(/export function/g, 'function');
const publisherStore = { draft: { media: [] } };
const { PublisherPostEditor } = new Function('publisherStore', 'coverCrop', `${source}\nreturn { PublisherPostEditor };`)(publisherStore, coverCrop);

const editor = new PublisherPostEditor();
editor.element = { querySelector: () => null };
editor._setCropPreset('4:5');
assert.deepEqual(editor.cropData, { x: 0.09999999999999998, y: 0, w: 0.8, h: 1 });
editor._setCropPreset('9:16');
assert.equal(editor.cropData.w, 0.5625);
assert.equal(editor.cropData.h, 1);

const pickerIndex = css.indexOf('.publisher-media-picker {');
const cropPanelIndex = css.indexOf('.ppe-crop-panel {');
const mobileBreakpointIndex = css.indexOf('@media (max-width: 480px)', pickerIndex);
assert.ok(pickerIndex > 0 && cropPanelIndex > pickerIndex);
assert.ok(mobileBreakpointIndex > cropPanelIndex, 'les styles du sélecteur et de l’ajustement doivent être globaux');
assert.match(css, /\.pmp-body\s*\{[^}]*display:\s*flex;[^}]*flex:\s*1;[^}]*min-height:\s*0;/s);
assert.match(css, /\.pmp-selection-head\s*\{[^}]*display:\s*flex;[^}]*align-items:\s*center;/s);
assert.match(css, /\.pmp-check\[hidden\][\s\S]*?\.pmp-order\[hidden\]\s*\{\s*display:\s*none;/);
assert.match(css, /\.ppe-crop-panel\s*\{[^}]*position:\s*fixed;/s);
assert.match(css, /@media\s*\(min-width:\s*768px\)\s*\{\s*\.ppe-crop-panel\s*\{[^}]*left:\s*50%;[^}]*transform:\s*translate\(-50%,\s*-50%\);/s);
assert.match(css, /@media\s*\(hover:\s*none\),\s*\(pointer:\s*coarse\)\s*\{\s*\.ppe-media-actions\s*\{\s*opacity:\s*1;/s);
assert.match(indexHtml, /publisher\.css\?v=2/);

console.log('Styles du sélecteur/ajustement et formats de recadrage OK.');
