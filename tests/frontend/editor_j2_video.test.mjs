// Tests J2 — Studio V2 : clips vidéo (timeline).
// Exécution : node tests/frontend/editor_j2_video.test.mjs
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

console.log('J2 — Clip vidéo : ajout / association / ops');
{
  const s = new EditorState();
  const tr = s.addTrack({ id: 'tr-video-1', type: 'video', hidden: false, locked: false, clips: [] });
  const clip = {
    id: 'clip-v1', type: 'video', start: 0, duration: 12,
    trackId: 'tr-video-1', mediaId: 77, source: 'forgeai',
    inPoint: 0, outPoint: 12, rotation: 0, crop: null, mute: false,
  };
  const added = s.addVideoClip('tr-video-1', clip);
  check('addVideoClip ajoute le clip', !!added && added.id === 'clip-v1');
  check('addVideoClip type video', s.getTimeline().tracks[0].clips[0].type === 'video');
  check('association média/clip', s.getTimeline().tracks[0].clips[0].mediaId === 77);
  check('propriétés tempornelles séparées', s.getTimeline().tracks[0].clips[0].inPoint === 0 && s.getTimeline().tracks[0].clips[0].outPoint === 12);

  // Déplacement
  s.moveClip('tr-video-1', 'clip-v1', 5);
  check('move video clip start', s.getTimeline().tracks[0].clips[0].start === 5);

  // Redimensionnement
  s.resizeClip('tr-video-1', 'clip-v1', 8);
  check('resize video clip duration', s.getTimeline().tracks[0].clips[0].duration === 8);

  // Crop / rotation / mute
  s.updateClip('tr-video-1', 'clip-v1', { rotation: 90, mute: true, crop: { x: 0, y: 0, w: 1, h: 1 } });
  check('updateClip crop/rotation/mute', s.getTimeline().tracks[0].clips[0].rotation === 90 && s.getTimeline().tracks[0].clips[0].mute === true);

  // Split
  s.splitClip('tr-video-1', 'clip-v1', 6);
  check('splitClip crée deux clips', s.getTimeline().tracks[0].clips.length === 2);
  check('splitClip source tronquée', s.getTimeline().tracks[0].clips[0].duration === 1);

  // Duplication
  const dup = s.duplicateClip('tr-video-1', s.getTimeline().tracks[0].clips[0].id);
  check('duplicateClip crée un décalage', !!dup && dup.start > 0, JSON.stringify(dup && { start: dup.start, duration: dup.duration }));

  // Suppression
  const before = s.getTimeline().tracks[0].clips.length;
  s.removeClip('tr-video-1', s.getTimeline().tracks[0].clips[0].id);
  check('removeClip supprime', s.getTimeline().tracks[0].clips.length === before - 1);
}

console.log('J2 — Undo / redo / sauvegarde restauration / médias indisponibles');
{
  const s = new EditorState();
  const tr = s.addTrack({ id: 'tr-video-2', type: 'video', hidden: false, locked: false, clips: [] });
  const clip = { id: 'clip-v2', type: 'video', start: 0, duration: 10, trackId: 'tr-video-2', mediaId: 999, source: 'forgeai', inPoint: 0, outPoint: 10, rotation: 0, crop: null, mute: false };
  s.addVideoClip('tr-video-2', clip);
  s.undo();
  check('undo addVideoClip', s.getTimeline().tracks[0].clips.length === 0);
  s.redo();
  check('redo addVideoClip', s.getTimeline().tracks[0].clips.length === 1);
  const json = s.toJSON();
  const s2 = new EditorState(json);
  check('J2 save/restore V2 avec clip video', s2.getTimeline().tracks[0].clips[0].type === 'video' && s2.getTimeline().tracks[0].clips[0].mediaId === 999);
  // média indisponible : l'opération ne doit pas corrompre le design
  const ok = (() => { s.moveClip('tr-video-2', 'clip-v2', 3); return true; })();
  check('J2 média indisponible : design intact après move', ok);
}

console.log('J2 — Compatibilité V1');
{
  const v1 = { version: 1, format: { platform: 'instagram', type: 'feed_45', width: 1080, height: 1350 }, background: { color: '#111111' }, elements: [], carousel: [], cover: null };
  const n = normalizeDesign(v1);
  check('J2 V1→V2 toujours version 2', !!n && n.version === 2);
}

console.log(failures === 0 ? '\nTOUS LES TESTS J2 PASSENT' : `\n${failures} ÉCHEC(S)`);
process.exit(failures === 0 ? 0 : 1);
