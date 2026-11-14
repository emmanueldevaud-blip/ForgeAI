// Tests J4 — Studio V2 : traitement audio (volume / mute / solo / fades / ducking / mix plan).
// Exécution : node tests/frontend/editor_j4_audio.test.mjs
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

console.log('J4 — Clip audio : volume / fades / mute / undo / sauvegarde');
{
  const s = new EditorState();
  const tr = s.addTrack({ id: 'tr-audio-1', type: 'audio', hidden: false, locked: false, clips: [] });
  const clip = {
    id: 'clip-a1', type: 'audio', start: 0, duration: 30, trackId: 'tr-audio-1', mediaId: 77, source: 'pixabay',
    inPoint: 0, outPoint: 30, volume: 1, fadeIn: 0, fadeOut: 0, mute: false,
  };
  s.addClip('tr-audio-1', clip);
  s.updateClip('tr-audio-1', 'clip-a1', { volume: 0.8, fadeIn: 1, fadeOut: 2, mute: false });
  let saved = s.getTimeline().tracks[0].clips[0];
  check('J4 clip volume/fades', saved.volume === 0.8 && saved.fadeIn === 1 && saved.fadeOut === 2);

  s.undo();
  saved = s.getTimeline().tracks[0].clips[0];
  check('J4 undo clip volume/fades', saved.volume === 1 && saved.fadeIn === 0 && saved.fadeOut === 0);
  s.redo();
  saved = s.getTimeline().tracks[0].clips[0];
  check('J4 redo clip volume/fades', saved.volume === 0.8 && saved.fadeIn === 1 && saved.fadeOut === 2);

  const json = s.toJSON();
  const s2 = new EditorState(json);
  check('J4 sauvegarde/restauration clip audio', s2.getTimeline().tracks[0].clips[0].volume === 0.8);
}

console.log('J4 — Piste audio : volume / solo / ducking / undo / sauvegarde');
{
  const s = new EditorState();
  const tr = s.addTrack({ id: 'tr-audio-2', type: 'audio', hidden: false, locked: false, clips: [] });
  s.setTrackVolume('tr-audio-2', 0.5);
  check('J4 track volume', s.getTrackById('tr-audio-2').volume === 0.5);
  s.setTrackSolo('tr-audio-2', true);
  check('J4 track solo', s.getTrackById('tr-audio-2').solo === true);
  s.setTrackDucking('tr-audio-2', { enabled: true, level: 0.3 });
  const saved = s.getTrackById('tr-audio-2');
  check('J4 track ducking', saved.ducking.enabled === true && saved.ducking.level === 0.3);

  s.undo();
  check('J4 undo track ducking', !s.getTrackById('tr-audio-2')?.ducking?.enabled);
  s.redo();
  check('J4 redo track ducking', s.getTrackById('tr-audio-2').ducking.enabled === true);

  const json = s.toJSON();
  const s2 = new EditorState(json);
  check('J4 sauvegarde/restauration piste audio', s2.getTrackById('tr-audio-2')?.volume === 0.5);
}

console.log('J4 — Mix plan : pistes simultanées / gains / fades / mute / sync / durée');
{
  const view = new StudioEditorView({
    publication: { id: 7, design: null, photo_locked: false },
    deps: {},
    callbacks: { onClose: () => {}, onApplied: async () => {} },
  });
  const s = view.state;
  const tr1 = s.addTrack({ id: 'tr-audio-1', type: 'audio', hidden: false, locked: false, clips: [] });
  const tr2 = s.addTrack({ id: 'tr-audio-2', type: 'audio', hidden: false, locked: false, clips: [] });
  s.addClip('tr-audio-1', { id: 'clip-a1', type: 'audio', start: 0, duration: 10, trackId: 'tr-audio-1', mediaId: 77, source: 'pixabay', inPoint: 0, outPoint: 10, volume: 0.8, fadeIn: 0.5, fadeOut: 0.5, mute: false });
  s.addClip('tr-audio-2', { id: 'clip-a2', type: 'audio', start: 5, duration: 10, trackId: 'tr-audio-2', mediaId: 88, source: 'mixkit', inPoint: 0, outPoint: 10, volume: 0.5, fadeIn: 0, fadeOut: 0, mute: true });

  const plan = view._getMixPlan();
  check('J4 mix plan fps', plan.fps === 30);
  check('J4 mix plan pistes simultanées', plan.tracks.length === 2, `tracks=${plan.tracks.length}`);
  check('J4 mix plan gain clip1', plan.tracks[0].clips[0].gain > 0);
  check('J4 mix plan gain clip2 mute', plan.tracks[1].clips[0].gain === 0);
  check('J4 mix plan fades', plan.tracks[0].clips[0].fadeIn === 0.5 && plan.tracks[0].clips[0].fadeOut === 0.5);
  check('J4 mix plan sync origin', plan.sync.origin === 0);
  check('J4 mix plan durée finale', plan.finalDuration === 15, `finalDuration=${plan.finalDuration}`);

  view.state.setTrackVolume('tr-audio-1', 0.9);
  const plan2 = view._getMixPlan();
  check('J4 mix plan gain track volume', plan2.tracks[0].clips[0].gain > 0);
}

console.log('J4 — Sync / undo / sauvegarde (niveau state)');
{
  const view = new StudioEditorView({
    publication: { id: 8, design: null, photo_locked: false },
    deps: {},
    callbacks: { onClose: () => {}, onApplied: async () => {} },
  });
  view.timeline = { _cursor: 0 };
  view._seekMix(3);
  check('J4 seek mix met à jour cursor/timeline', view._cursor === 3 && view.timeline._cursor === 3);
  const s = view.state;
  s.addTrack({ id: 'tr-audio-1', type: 'audio', hidden: false, locked: false, clips: [] });
  s.setTrackDucking('tr-audio-1', { enabled: true, level: 0.2 });
  const json = s.toJSON();
  const s2 = new EditorState(json);
  check('J4 sauvegarde/restauration ducking', s2.getTrackById('tr-audio-1')?.ducking?.enabled === true);
}

console.log(failures === 0 ? '\nTOUS LES TESTS J4 PASSENT' : `\n${failures} ÉCHEC(S)`);
process.exit(failures === 0 ? 0 : 1);
