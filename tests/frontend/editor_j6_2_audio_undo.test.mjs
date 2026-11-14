// Tests J6.2 — Studio V2 : gestes audio, parametres volume/fades/mute/solo/ducking et undo/redo.
// Exécution : node tests/frontend/editor_j6_2_audio_undo.test.mjs
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

console.log('J6.2 — Parametres audio : volume piste / clip, mute, solo, ducking, fades');
{
  const view = new StudioEditorView({
    publication: { id: 22, design: null, photo_locked: false },
    deps: {},
    callbacks: { onClose: () => {}, onApplied: async () => {} },
  });
  const s = view.state;
  const tr1 = s.addTrack({ id: 'tr-audio-1', type: 'audio', hidden: false, locked: false, clips: [], volume: 1 });
  s.addClip('tr-audio-1', { id: 'clip-a1', type: 'audio', start: 0, duration: 10, trackId: 'tr-audio-1', mediaId: 77, source: 'pixabay', inPoint: 0, outPoint: 10, volume: 0.8, fadeIn: 0, fadeOut: 0, mute: false });
  check('J6.2 baseline undoStack = 2', s.undoStack.length === 2, `undoStack=${s.undoStack.length}`);

  s.beginTransaction();
  s.setTrackVolumeLive('tr-audio-1', 0.5);
  s.commitTransaction();
  check('J6.2 geste volume piste = 1 undo', s.undoStack.length === 3, `undoStack=${s.undoStack.length}`);
  check('J6.2 geste volume piste applique', s.getTrackById('tr-audio-1').volume === 0.5);
  check('J6.2 plan volume recalculé', Math.abs(view._getMixPlan().tracks[0].volume - 0.5) < 1e-9);
  s.undo();
  check('J6.2 undo volume piste', s.getTrackById('tr-audio-1').volume === 1);
  s.redo();
  check('J6.2 redo volume piste', s.getTrackById('tr-audio-1').volume === 0.5);

  s.beginTransaction();
  s.updateClipLive('tr-audio-1', 'clip-a1', { volume: 0.25 });
  s.commitTransaction();
  check('J6.2 geste volume clip = 1 undo', s.undoStack.length === 4, `undoStack=${s.undoStack.length}`);
  check('J6.2 geste volume clip applique', s.getTimeline().tracks[0].clips[0].volume === 0.25);
  check('J6.2 plan gain clip recalculé', view._getMixPlan().tracks[0].clips[0].gain > 0);
  s.undo();
  check('J6.2 undo volume clip', s.getTimeline().tracks[0].clips[0].volume === 0.8);
  s.redo();
  check('J6.2 redo volume clip', s.getTimeline().tracks[0].clips[0].volume === 0.25);

  s.updateClip('tr-audio-1', 'clip-a1', { mute: true });
  check('J6.2 mute = 1 undo', s.undoStack.length === 5, `undoStack=${s.undoStack.length}`);
  s.undo();
  check('J6.2 undo mute', s.getTimeline().tracks[0].clips[0].mute === false);
  s.redo();
  check('J6.2 redo mute', s.getTimeline().tracks[0].clips[0].mute === true);

  s.updateClip('tr-audio-1', 'clip-a1', { fadeIn: 1.5, fadeOut: 2.5 });
  check('J6.2 fade = 1 undo', s.undoStack.length === 6, `undoStack=${s.undoStack.length}`);
  s.undo();
  check('J6.2 undo fade', s.getTimeline().tracks[0].clips[0].fadeIn === 0 && s.getTimeline().tracks[0].clips[0].fadeOut === 0);
  s.redo();
  check('J6.2 redo fade', s.getTimeline().tracks[0].clips[0].fadeIn === 1.5 && s.getTimeline().tracks[0].clips[0].fadeOut === 2.5);

  s.setTrackDucking('tr-audio-1', { enabled: true, level: 0.3 });
  check('J6.2 ducking = 1 undo', s.undoStack.length === 7, `undoStack=${s.undoStack.length}`);
  s.undo();
  check('J6.2 undo ducking', !s.getTrackById('tr-audio-1')?.ducking?.enabled);
}

console.log('J6.2 — Robustesse : geste audio sans changement = 0 undo supplementaire');
{
  const s = new EditorState();
  const tr = s.addTrack({ id: 'tr-audio-2', type: 'audio', hidden: false, locked: false, clips: [] });
  s.addClip('tr-audio-2', { id: 'clip-b1', type: 'audio', start: 0, duration: 10, trackId: 'tr-audio-2', mediaId: 88, source: 'mixkit', inPoint: 0, outPoint: 10, volume: 1, fadeIn: 0, fadeOut: 0, mute: false });
  check('J6.2 baseline undoStack = 2', s.undoStack.length === 2);
  const lenBefore = s.undoStack.length;
  s.beginTransaction();
  s.updateClipLive('tr-audio-2', 'clip-b1', { volume: 1 });
  s.commitTransaction();
  check('J6.2 geste audio sans changement = 0 undo', s.undoStack.length === lenBefore);
}

console.log(failures === 0 ? '\nTOUS LES TESTS J6.2 PASSENT' : `\n${failures} ÉCHEC(S)`);
process.exit(failures === 0 ? 0 : 1);
