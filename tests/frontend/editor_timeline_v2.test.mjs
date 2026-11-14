// Tests J1 — Timeline multipiste V2 : conversion V1→V2, ops timeline, undo/redo.
// Exécution : node tests/frontend/editor_timeline_v2.test.mjs
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const editorDir = path.join(here, '../../src/public/js/editor');

let failures = 0;
const check = (label, cond, extra = '') => {
  if (cond) console.log(`  ok - ${label}`);
  else { failures++; console.log(`  FAIL - ${label} ${extra}`); }
};

const { EditorState, defaultDesign, normalizeDesign } = await import(
  path.join(editorDir, 'editorState.js')
);

console.log('Conversion V1 → V2');
{
  const v1 = {
    version: 1,
    format: { platform: 'instagram', type: 'feed_45', width: 1080, height: 1350 },
    background: { color: '#111111' },
    elements: [{ id: 'e1', type: 'text', x: 100, y: 200, w: 300, h: 50, text: 'Bonjour' }],
    carousel: [],
    cover: null,
  };
  const n = normalizeDesign(v1);
  check('V1→V2 version 2', !!n && n.version === 2);
  check('V1→V2 timeline ok', !!n && Array.isArray(n.timeline && n.timeline.tracks));
  check('V1→V2 elements conservés', !!n && n.elements.length === 1);
  check('V1→V2 clip créé', !!n && n.timeline.tracks[0].clips.length === 1);
}

console.log('Design V2 par défaut');
{
  const d = defaultDesign('ig_feed_45');
  check('defaultDesign version 2', d.version === 2 && Array.isArray(d.timeline.tracks));
}

console.log('Sauvegarde / restauration');
{
  const s = new EditorState();
  s.addElement({ type: 'sticker', sticker: '🔥', x: 0, y: 0, w: 50, h: 50 });
  const json = s.toJSON();
  check('toJSON version 2', json.version === 2 && json.timeline && Array.isArray(json.timeline.tracks));
  const s2 = new EditorState(json);
  check('restauration design identique', JSON.stringify(s2.design) === JSON.stringify(json));
}

console.log('Déplacement temporel');
{
  const s = new EditorState();
  const el = s.addElement({ type: 'image', photoId: 1, x: 100, y: 0, w: 200, h: 200 });
  const tr = s.addTrack({
    id: 'tr-image-1', type: 'image', hidden: false, locked: false,
    clips: [{ id: `clip-${el.id}`, type: 'image', start: 100, duration: 200, trackId: 'tr-image-1', elementId: el.id }],
  });
  check('track ajouté', s.getTimeline().tracks.length === 1);
  check('clip présent', s.getTimeline().tracks[0].clips.length === 1);
  s.moveClip('tr-image-1', `clip-${el.id}`, 250);
  check('moveClip shift element x', s.getElementById(el.id).x === 250, `x=${s.getElementById(el.id).x}`);
  check('moveClip update clip start', s.getTimeline().tracks[0].clips[0].start === 250);
  s.undo();
  check('undo moveClip', s.getElementById(el.id).x === 100);
  s.redo();
  check('redo moveClip', s.getElementById(el.id).x === 250);
}

console.log('Redimensionnement');
{
  const s = new EditorState();
  const el = s.addElement({ type: 'image', photoId: 1, x: 0, y: 0, w: 200, h: 200 });
  const tr = s.addTrack({
    id: 'tr-image-2', type: 'image', hidden: false, locked: false,
    clips: [{ id: `clip-${el.id}`, type: 'image', start: 0, duration: 200, trackId: 'tr-image-2', elementId: el.id }],
  });
  s.resizeClip('tr-image-2', `clip-${el.id}`, 300);
  check('resizeClip update element w', s.getElementById(el.id).w === 300);
  check('resizeClip update clip duration', s.getTimeline().tracks[0].clips[0].duration === 300);
  s.undo();
  check('undo resizeClip', s.getElementById(el.id).w === 200);
}

console.log('Découpage');
{
  const s = new EditorState();
  const el = s.addElement({ type: 'image', photoId: 1, x: 0, y: 0, w: 200, h: 200 });
  const tr = s.addTrack({
    id: 'tr-image-3', type: 'image', hidden: false, locked: false,
    clips: [{ id: `clip-${el.id}`, type: 'image', start: 0, duration: 200, trackId: 'tr-image-3', elementId: el.id }],
  });
  s.cutClip('tr-image-3', `clip-${el.id}`, 80);
  const clip = s.getTimeline().tracks[0].clips[0];
  check('cutClip truncate source', clip.duration === 80);
  check('cutClip create tail element', s.design.elements.length === 2);
}

console.log('Plusieurs pistes / chevauchement / durées invalides');
{
  const s = new EditorState();
  const e1 = s.addElement({ type: 'sticker', sticker: '🔥', x: 0, y: 0, w: 50, h: 50 });
  const e2 = s.addElement({ type: 'sticker', sticker: '⭐', x: 0, y: 0, w: 50, h: 50 });
  const t1 = s.addTrack({ id: 'tr-a', type: 'sticker', hidden: false, locked: false, clips: [{ id: 'c1', type: 'sticker', start: 0, duration: 50, trackId: 'tr-a', elementId: e1.id }] });
  const t2 = s.addTrack({ id: 'tr-b', type: 'sticker', hidden: false, locked: false, clips: [{ id: 'c2', type: 'sticker', start: 0, duration: 50, trackId: 'tr-b', elementId: e2.id }] });
  check('plusieurs pistes', s.getTimeline().tracks.length === 2);
  const t3 = s.addTrack({ id: 'tr-c', type: 'image', hidden: false, locked: false, clips: [
    { id: 'c3a', type: 'image', start: 0, duration: 100, trackId: 'tr-c', elementId: e1.id },
    { id: 'c3b', type: 'image', start: 50, duration: 100, trackId: 'tr-c', elementId: e2.id },
  ] });
  check('chevauchement autorisé (data)', s.getTimeline().tracks[2].clips.length === 2);
  s.resizeClip('tr-a', 'c1', -5);
  check('durée invalide clampée à 0', s.getTimeline().tracks[0].clips[0].duration === 0);
}

console.log('Pistes / fps');
{
  const s = new EditorState();
  const tr = s.addTrack({ id: 'tr-x', type: 'text', hidden: false, locked: false, clips: [] });
  s.setTrackHidden('tr-x', true);
  check('setTrackHidden', s.getTimeline().tracks[0].hidden === true);
  s.setTrackLocked('tr-x', true);
  check('setTrackLocked', s.getTimeline().tracks[0].locked === true);
  s.setFps(30);
  check('setFps', s.getTimeline().fps === 30);
}

console.log(failures === 0 ? '\nTOUS LES TESTS J1 PASSENT' : `\n${failures} ÉCHEC(S)`);
process.exit(failures === 0 ? 0 : 1);
