// Tests J6.3 — Studio V2 : scénario référence preview/export (2 clips vidéo + gap + audio).
// Exécution : node tests/frontend/editor_j6_3_preview_export.test.mjs
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

console.log('J6.3 — Scénario référence : clips vidéo + gap + pistes audio + volumes/fades/mute');
{
  const view = new StudioEditorView({
    publication: { id: 23, design: null, photo_locked: false },
    deps: {},
    callbacks: { onClose: () => {}, onApplied: async () => {} },
  });
  const s = view.state;
  check('J6.3 export autorise plusieurs clips vidéo', view._hasVideoClips() === false);

  const trV = s.addTrack({ id: 'tr-video-1', type: 'video', hidden: false, locked: false, clips: [] });
  s.addVideoClip('tr-video-1', { id: 'clip-v1', type: 'video', start: 0, duration: 5, trackId: 'tr-video-1', mediaId: 77, source: 'forgeai', inPoint: 0, outPoint: 5, rotation: 0, crop: null, mute: false });
  s.addVideoClip('tr-video-1', { id: 'clip-v2', type: 'video', start: 8, duration: 4, trackId: 'tr-video-1', mediaId: 88, source: 'forgeai', inPoint: 2, outPoint: 6, rotation: 0, crop: null, mute: false });
  check('J6.3 deux clips vidéo présents', s.getTimeline().tracks[0].clips.length === 2);
  check('J6.3 second clip avec in/out', s.getTimeline().tracks[0].clips[1].inPoint === 2 && s.getTimeline().tracks[0].clips[1].outPoint === 6);
  check('J6.3 export autorise deux clips vidéo', view._hasVideoClips() === true);

  const trA = s.addTrack({ id: 'tr-audio-1', type: 'audio', hidden: false, locked: false, clips: [], volume: 0.9 });
  s.addClip('tr-audio-1', { id: 'clip-a1', type: 'audio', start: 0, duration: 10, trackId: 'tr-audio-1', mediaId: 77, source: 'pixabay', inPoint: 0, outPoint: 10, volume: 0.8, fadeIn: 0.5, fadeOut: 0.5, mute: false });
  const trM = s.addTrack({ id: 'tr-audio-2', type: 'audio', hidden: false, locked: false, clips: [], volume: 0.5 });
  s.addClip('tr-audio-2', { id: 'clip-a2', type: 'audio', start: 2, duration: 6, trackId: 'tr-audio-2', mediaId: 88, source: 'mixkit', inPoint: 0, outPoint: 6, volume: 0.5, fadeIn: 0, fadeOut: 0, mute: true });

  const plan = view._getMixPlan();
  check('J6.3 scenario plan finalDuration (gap + clips)', plan.finalDuration === 12, `finalDuration=${plan.finalDuration}`);
  check('J6.3 scenario plan pistes audio', plan.tracks.length === 2, `tracks=${plan.tracks.length}`);
  check('J6.3 scenario plan gain voix (volume piste x clip)', Math.abs(plan.tracks[0].clips[0].gain - (0.8 * 0.9)) < 1e-9, `gain=${plan.tracks[0].clips[0].gain}`);
  check('J6.3 scenario plan gain musique (mute)', plan.tracks[1].clips[0].gain === 0);
  check('J6.3 scenario plan fades voix', plan.tracks[0].clips[0].fadeIn === 0.5 && plan.tracks[0].clips[0].fadeOut === 0.5);

  const json = s.toJSON();
  const s2 = new EditorState(json);
  const view2 = new StudioEditorView({ publication: { id: 24, design: json, photo_locked: false }, deps: {}, callbacks: { onClose: () => {}, onApplied: async () => {} } });
  const plan2 = view2._getMixPlan();
  check('J6.3 scenario sauvegarde/restauration plan coherent', plan2.finalDuration === plan.finalDuration && plan2.tracks.length === plan.tracks.length);
}

console.log(failures === 0 ? '\nTOUS LES TESTS J6.3 PASSENT' : `\n${failures} ÉCHEC(S)`);
process.exit(failures === 0 ? 0 : 1);
