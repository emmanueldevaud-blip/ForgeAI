// UX Composer façon Instagram : validation média, aperçu légende et retour de publication.
// Exécution : node tests/frontend/composer_instagram_ux.test.mjs
import assert from 'node:assert/strict';
import fs from 'node:fs';

const root = new URL('../../', import.meta.url);
const read = (relative) => fs.readFileSync(new URL(relative, root), 'utf8');
const load = (relative, name, args, deps) => {
  let source = read(relative);
  source = source.replace(/^import\s[\s\S]*?from\s+['"][^'"]+['"];?\s*$/gm, '');
  source = source.replace(/export class/g, 'class').replace(/export function/g, 'function');
  return new Function(...args, `${source}\nreturn { ${name} };`)(...deps)[name];
};

console.log('1. Sélecteur média : MIME réel et limites Instagram');
{
  const store = {
    draft: { media: [] },
    addMedia(items) { this.draft.media.push(...items); },
    removeMedia() {},
    _notify() {},
  };
  const MediaPicker = load(
    'src/public/js/components/PublisherMediaPicker.js',
    'PublisherMediaPicker',
    ['publisherStore', 'listPhotos', 'uploadPhotos', 'listAlbums', 'listSportActivities', 'getSuggestedPhotos'],
    [store, async () => ({}), async () => ({ items: [{ id: 1 }] }), async () => ({}), async () => ({}), async () => []],
  );

  const notice = { textContent: '', hidden: true };
  const queue = { innerHTML: '' };
  const picker = new MediaPicker({ format: 'post', allowedTypes: ['photo'], maxSelection: 1 });
  picker.element = { querySelector(sel) { return sel === '[data-notice]' ? notice : queue; } };

  assert.equal(picker._fileKind({ type: 'image/jpeg', name: 'a.jpg' }), 'photo');
  assert.equal(picker._fileKind({ type: '', name: 'clip.MP4' }), 'video');
  assert.equal(picker._fileKind({ type: 'application/pdf', name: 'doc.pdf' }), null);

  picker._handleFiles([{ type: 'video/mp4', name: 'clip.mp4' }]);
  assert.match(notice.textContent, /images sont acceptées/);
  assert.equal(picker.uploadQueue.length, 0, 'une vidéo est refusée pour un post photo');

  store.draft.media = [{ id: 'photo_1' }];
  picker._handleFiles([{ type: 'image/jpeg', name: 'a.jpg' }]);
  assert.match(notice.textContent, /Limite de 1 médias/);
  assert.equal(picker.uploadQueue.length, 0, 'l’import ne contourne pas maxSelection');

  const multi = new MediaPicker({ format: 'reel', allowedTypes: ['photo', 'video'], maxSelection: 2 });
  multi.element = picker.element;
  store.draft.media = [];
  multi._handleFiles([
    { type: 'image/png', name: 'a.png' },
    { type: 'video/quicktime', name: 'b.mov' },
    { type: 'image/jpeg', name: 'c.jpg' },
  ]);
  assert.equal(multi.uploadQueue.length, 2, 'seuls les fichiers dans la limite sont files');
  assert.match(multi.notice, /1 ignoré\(s\)/);
}

console.log('2. Légende : aperçu live et hashtags suggérés');
{
  const store = {
    draft: {
      caption: { title: 'Trail du dimanche', content: 'Belle sortie', hashtags: '#running', accountUsername: '@forgeai' },
      media: [{ thumbnail_url: '/photos/12/file?size=small' }],
    },
    updateCaption(name, value) { this.draft.caption[name] = value; },
    _notify() {},
  };
  const CaptionEditor = load(
    'src/public/js/components/PublisherCaptionEditor.js',
    'PublisherCaptionEditor',
    ['publisherStore', 'getMetaInstagramAccount'],
    [store, async () => ({})],
  );

  const fields = {
    '[name="hashtags"]': { value: '#running' },
  };
  const previewNodes = {
    '[data-preview-caption]': { textContent: '' },
    '[data-preview-account]': { textContent: '' },
    '[data-preview-thumb]': { style: {} },
  };
  const editor = new CaptionEditor();
  editor.element = {
    querySelector(sel) { return fields[sel] || (sel === '[data-caption-preview]' ? card : null); },
  };
  const card = { querySelector(sel) { return previewNodes[sel] || null; } };

  editor._appendHashtag('#trailrunning');
  assert.equal(fields['[name="hashtags"]'].value, '#running #trailrunning');
  editor._appendHashtag('#trailrunning');
  assert.equal(fields['[name="hashtags"]'].value, '#running #trailrunning', 'pas de doublon');

  editor._updateCaptionPreview();
  assert.match(previewNodes['[data-preview-caption]'].textContent, /Trail du dimanche/);
  assert.equal(previewNodes['[data-preview-account]'].textContent, '@forgeai');
  assert.match(previewNodes['[data-preview-thumb]'].style.backgroundImage, /photos\/12\/file/);
}

console.log('3. Câblage et styles');
{
  const page = read('src/public/js/pages/CommunityPublisherPage.js');
  assert.match(page, /publisherDraftService\.clearCurrent\?\.\(\);/, 'changement de format détache le brouillon serveur');
  assert.match(page, /Publication envoyée · traitement en cours/, 'statut queued annoncé correctement');
  assert.match(page, /shortCaption\(caption\.title\)/, 'résumé de publication échappé');
  const picker = read('src/public/js/components/PublisherMediaPicker.js');
  assert.match(picker, /data-notice/);
  assert.match(picker, /_allowedFile\(f\)/);
  const caption = read('src/public/js/components/PublisherCaptionEditor.js');
  assert.match(caption, /data-caption-preview/);
  assert.match(caption, /data-hashtag=/);
  const css = read('src/public/css/publisher.css');
  assert.match(css, /\.pmp-notice\s*\{/);
  assert.match(css, /\.pce-live-preview\s*\{/);
  assert.match(css, /\.pce-hashtag-suggestions\s*\{/);
  assert.match(css, /\.pmc-media-strip\s*\{/);
  assert.match(css, /\.pmc-layer-list\s*\{/);
  assert.match(css, /\.pmc-layer-add\s*\{/);
  assert.match(css, /\.pmc-overlay--slot-1\s*\{/);
  assert.match(css, /\.pmc-preview\s*\{/);
  assert.match(css, /\.pmc-overlay-actions\s*\{/);
  assert.match(css, /touch-action: manipulation/);
  assert.match(css, /@media \(hover: none\), \(max-width: 899px\)/);
  assert.match(css, /@media \(min-width: 900px\) and \(min-height: 620px\)/);
  assert.match(read('src/public/index.html'), /publisher\.css\?v=20/);
}

console.log('UX Composer Instagram OK.');
