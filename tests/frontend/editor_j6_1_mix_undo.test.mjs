// Tests J6.1 — Studio V2 : fiabilisation plan de mixage (_getMixPlan) et historique undo/redo (gestes).
// Exécution : node tests/frontend/editor_j6_1_mix_undo.test.mjs
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const editorDir = path.join(here, '../../src/public/js/editor');

let failures = 0;
const check = (label, cond, extra = '') => {
  if (cond) console.log(`  ok - ${label}`);
  else { failures++; console.log(`  FAIL - ${label} ${extra}`); }
};

const { EditorState } = await import(path.join(editorDir, 'editorState.js'));
const { StudioEditorView } = await import(path.join(editorDir, 'StudioEditorView.js'));

console.log('J6.1 — Mix plan : pistes / gains / fades / mute / hidden / solo / undo');
{
  const view = new StudioEditorView({
    publication: { id: 21, design: null, photo_locked: false },
    deps: {},
    callbacks: { onClose: () => {}, onApplied: async () => {} },
  });
  const s = view.state;
  const tr1 = s.addTrack({ id: 'tr-audio-1', type: 'audio', hidden: false, locked: false, clips: [] });
  const tr2 = s.addTrack({ id: 'tr-audio-2', type: 'audio', hidden: false, locked: false, clips: [] });
  s.addClip('tr-audio-1', { id: 'clip-a1', type: 'audio', start: 0, duration: 10, trackId: 'tr-audio-1', mediaId: 77, source: 'pixabay', inPoint: 0, outPoint: 10, volume: 0.8, fadeIn: 0.5, fadeOut: 0.5, mute: false });
  s.addClip('tr-audio-2', { id: 'clip-a2', type: 'audio', start: 5, duration: 10, trackId: 'tr-audio-2', mediaId: 88, source: 'mixkit', inPoint: 0, outPoint: 10, volume: 0.5, fadeIn: 0, fadeOut: 0, mute: true });

  const plan = view._getMixPlan();
  check('J6.1 mix plan fps', plan.fps === 30);
  check('J6.1 mix plan pistes', plan.tracks.length === 2, `tracks=${plan.tracks.length}`);
  check('J6.1 mix plan gain clip1', plan.tracks[0].clips[0].gain > 0);
  check('J6.1 mix plan mute clip2 gain 0', plan.tracks[1].clips[0].gain === 0);
  check('J6.1 mix plan fades', plan.tracks[0].clips[0].fadeIn === 0.5 && plan.tracks[0].clips[0].fadeOut === 0.5);
  check('J6.1 mix plan sync origin', plan.sync.origin === 0);
  check('J6.1 mix plan finalDuration', plan.finalDuration === 15, `finalDuration=${plan.finalDuration}`);

  s.setTrackHidden('tr-audio-2', true);
  check('J6.1 mix plan piste masquee exclue', view._getMixPlan().tracks.length === 1);

  s.setTrackHidden('tr-audio-2', false);
  s.setTrackSolo('tr-audio-1', true);
  check('J6.1 mix plan solo exclut l autre piste', view._getMixPlan().tracks.length === 1);
  check('J6.1 mix plan solo garde la piste solee', view._getMixPlan().tracks[0].solo === true);

  s.setTrackSolo('tr-audio-1', false);
  check('J6.1 mix plan solo desactive', view._getMixPlan().tracks.length === 2);

  s.setTrackVolume('tr-audio-1', 0.9);
  check('J6.1 mix plan gain recalculé', Math.abs(view._getMixPlan().tracks[0].volume - 0.9) < 1e-9);

  s.undo();
  const restored = new EditorState(s.toJSON());
  check('J6.1 mix plan sauvegarde/restauration coherent', !!restored.getTimeline());
}

console.log('J6.1 — Undo/redo : un geste = une transaction');
{
  const s = new EditorState();
  const el = s.addElement({ type: 'image', photoId: 1, x: 100, y: 0, w: 200, h: 200 });
  const tr = s.addTrack({ id: 'tr-image-1', type: 'image', hidden: false, locked: false, clips: [{ id: `clip-${el.id}`, type: 'image', start: 100, duration: 200, trackId: 'tr-image-1', elementId: el.id }] });

  const beforeLen = s.undoStack.length;
  s.beginTransaction();
  s.moveClipLive('tr-image-1', `clip-${el.id}`, 150);
  s.moveClipLive('tr-image-1', `clip-${el.id}`, 175);
  s.commitTransaction();
  check('J6.1 geste move = 1 transaction', s.undoStack.length === beforeLen + 1, `undoStack=${s.undoStack.length}`);
  check('J6.1 geste move applique', s.getElementById(el.id).x === 175);
  s.undo();
  check('J6.1 undo geste move restaure', s.getElementById(el.id).x === 100);
  s.redo();
  check('J6.1 redo geste move', s.getElementById(el.id).x === 175);

  s.beginTransaction();
  s.resizeClipLive('tr-image-1', `clip-${el.id}`, 300);
  s.commitTransaction();
  check('J6.1 geste resize = 1 transaction', s.undoStack.length === beforeLen + 2, `undoStack=${s.undoStack.length}`);
  check('J6.1 geste resize applique', s.getElementById(el.id).w === 300);
  s.undo();
  check('J6.1 undo geste resize', s.getElementById(el.id).w === 200);

  const lenBefore = s.undoStack.length;
  s.beginTransaction();
  s.moveClipLive('tr-image-1', `clip-${el.id}`, s.getElementById(el.id).x);
  s.commitTransaction();
  check('J6.1 geste sans changement = 0 undo', s.undoStack.length === lenBefore);
}

console.log(failures === 0 ? '\nTOUS LES TESTS J6.1 PASSENT' : `\n${failures} ÉCHEC(S)`);
process.exit(failures === 0 ? 0 : 1);
