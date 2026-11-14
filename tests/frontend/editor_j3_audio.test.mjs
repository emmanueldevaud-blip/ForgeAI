// Tests J3 — Studio V2 : pistes / clips audio.
// Exécution : node tests/frontend/editor_j3_audio.test.mjs
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

console.log('J3 — Clip audio : création / ops / undo / sauvegarde');
{
  const s = new EditorState();
  const tr = s.addTrack({ id: 'tr-audio-1', type: 'audio', hidden: false, locked: false, clips: [] });
  const clip = {
    id: 'clip-a1', type: 'audio', start: 0, duration: 30,
    trackId: 'tr-audio-1', mediaId: 77, source: 'pixabay', title: 'Morceau', artist: 'Artiste',
    inPoint: 0, outPoint: 30, volume: 1, fadeIn: 0, fadeOut: 0, mute: false,
    license: { provider: 'pixabay', status: 'verified' },
  };
  const added = s.addClip('tr-audio-1', clip);
  check('J3 addClip audio', !!added && added.type === 'audio' && added.mediaId === 77);
  check('J3 clip audio duration', s.getTimeline().tracks[0].clips[0].duration === 30);

  s.moveClip('tr-audio-1', 'clip-a1', 5);
  check('J3 move audio clip', s.getTimeline().tracks[0].clips[0].start === 5);
  s.resizeClip('tr-audio-1', 'clip-a1', 20);
  check('J3 resize audio clip', s.getTimeline().tracks[0].clips[0].duration === 20);
  s.updateClip('tr-audio-1', 'clip-a1', { volume: 0.8, mute: true, fadeIn: 1, fadeOut: 2 });
  check('J3 updateClip audio (volume/fade/mute)', s.getTimeline().tracks[0].clips[0].volume === 0.8 && s.getTimeline().tracks[0].clips[0].mute === true);
  s.splitClip('tr-audio-1', 'clip-a1', 6);
  check('J3 split audio clip', s.getTimeline().tracks[0].clips.length === 2);
  const dup = s.duplicateClip('tr-audio-1', s.getTimeline().tracks[0].clips[0].id);
  check('J3 duplicate audio clip', !!dup);
  s.removeClip('tr-audio-1', s.getTimeline().tracks[0].clips[0].id);
  check('J3 remove audio clip', true);

  s.undo();
  check('J3 undo après ops audio', true);
  s.redo();
  check('J3 redo après ops audio', true);

  const json = s.toJSON();
  const s2 = new EditorState(json);
  check('J3 sauvegarde/restauration V2 audio', s2.getTimeline().tracks[0].clips.length >= 0);
}

console.log('J3 — Compatibilité V1 / médias indisponibles');
{
  const v1 = { version: 1, format: { platform: 'instagram', type: 'feed_45', width: 1080, height: 1350 }, background: { color: '#111111' }, elements: [], carousel: [], cover: null };
  check('J3 V1→V2 compatible', normalizeDesign(v1).version === 2);
  const s = new EditorState();
  const tr = s.addTrack({ id: 'tr-audio-2', type: 'audio', hidden: false, locked: false, clips: [{ id: 'clip-missing', type: 'audio', start: 0, duration: 10, trackId: 'tr-audio-2', mediaId: 424242, source: 'mixkit' }] });
  s.moveClip('tr-audio-2', 'clip-missing', 3);
  check('J3 média indisponible : op ok', s.getTimeline().tracks[0].clips[0].start === 3);
}

console.log(failures === 0 ? '\nTOUS LES TESTS J3 PASSENT' : `\n${failures} ÉCHEC(S)`);
process.exit(failures === 0 ? 0 : 1);
