// Tests J2.1 — Studio V2 : finalisation interface vidéo (import/add/select/preview data).
// Exécution : node tests/frontend/editor_j2_1_video.test.mjs
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const editorDir = path.join(here, '../../src/public/js/editor');

let failures = 0;
const check = (label, cond, extra = '') => {
  if (cond) console.log(`  ok - ${label}`);
  else { failures++; console.log(`  FAIL - ${label} ${extra}`); }
};

const { StudioEditorView } = await import(path.join(editorDir, 'StudioEditorView.js'));

console.log('J2.1 — Import vidéo via action add-video');
{
  const view = new StudioEditorView({
    publication: { id: 5, design: null, photo_locked: false },
    deps: {},
    callbacks: { onClose: () => {}, onApplied: async () => {} },
  });
  await view._onAction('add-video', { photoId: 55, duration: 12 });
  const clip = view.state.getClipById(view.state.getTimeline().tracks[0].clips[0].id);
  check('J2.1 add-video crée clip video', !!clip && clip.type === 'video' && clip.mediaId === 55);
  check('J2.1 add-video start/duration', clip && clip.start === 0 && clip.duration === 12);

  view.state.selectClip(view.state.getTimeline().tracks[0].id, clip.id);
  const sel = view.state.getSelectedClip();
  check('J2.1 sélection clip → getSelectedClip', !!sel && sel.mediaId === 55 && sel.type === 'video');

  const json = view.state.toJSON();
  const s2 = new (await import(path.join(editorDir, 'editorState.js'))).EditorState(json);
  check('J2.1 sauvegarde/restauration V2 clip video', s2.getClipById(json.timeline.tracks[0].clips[0].id).mediaId === 55);
}

console.log('J2.1 — Import sans média / preview structure');
{
  const view = new StudioEditorView({
    publication: { id: 6, design: null, photo_locked: false },
    deps: {},
    callbacks: { onClose: () => {}, onApplied: async () => {} },
  });
  await view._onAction('add-video', {});
  check('J2.1 add-video sans mediaId ne crée pas de clip', view.state.getTimeline().tracks.every((t) => !(t.clips || []).length));
}

console.log(failures === 0 ? '\nTOUS LES TESTS J2.1 PASSENT' : `\n${failures} ÉCHEC(S)`);
process.exit(failures === 0 ? 0 : 1);
