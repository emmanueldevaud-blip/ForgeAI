// Tests du Studio (DOM factice) — story suggérée, refus, boutons, formulaire, V1, photos.
// Exécution : node tests/frontend/studio_page.test.mjs
import fs from 'node:fs';

const FILE = new URL('../../src/public/js/pages/CommunityManagerStudioPage.js', import.meta.url);
let src = fs.readFileSync(FILE, 'utf8');
src = src.replace(/^import\s[\s\S]*?from\s+['"][^'"]+['"];?\s*$/gm, '');
src = src.replace(/export class/g, 'class');
src = src.replace(/export function/g, 'function');

const calls = [];
const record = (name, fn) => (...args) => { calls.push([name, ...args]); return fn ? fn(...args) : undefined; };

const PHOTOS = [
  { id: 11, title: 'paysage.jpg', taken_at: '2026-11-10T08:00:00', thumbnail_url: '/photos/11/file?size=small', match_reason: 'Activité : Sortie trail', badge_class: 'success', is_current: false },
];

const stubs = {
  getStudioDraft: record('getDraft', async () => ({ id: 5, status: 'draft', photo_id: null, title: '', content: '', hashtags: '' })),
  updateStudioDraft: record('update', async () => ({})),
  validateStudioDraft: record('validate', async () => ({})),
  publishStudioDraft: record('publish', async () => ({})),
  regeneratePublicationContent: record('regen', async () => ({})),
  getSuggestedPhotos: record('getPhotos', async () => PHOTOS),
  refuseSuggestion: record('refuse', async () => ({})),
  publicationPhotoUrl: (id) => `/photos/${id}/file?size=medium`,
  document: { createElement: () => makeEl() },
};

const paramNames = Object.keys(stubs);
const factory = new Function(...paramNames, `${src}\nreturn { CommunityManagerStudioPage };`);
const { CommunityManagerStudioPage } = factory(...paramNames.map(k => stubs[k]));

function makeEl() {
  return {
    className: '',
    _html: '',
    set innerHTML(v) { this._html = String(v); },
    get innerHTML() { return this._html; },
    replaceChildren() {},
    querySelectorAll: () => [],
    querySelector: () => null,
    addEventListener() {},
  };
}

function makeButton() {
  const listeners = {};
  return {
    listeners,
    addEventListener(type, handler) { (listeners[type] ||= []).push(handler); },
    click() { (listeners.click || []).forEach(h => h()); },
  };
}

const STORY_PUB = {
  id: 5,
  status: 'draft',
  photo_id: null,
  calendar_entry_id: 42,
  calendar_entry: { id: 42, source: 'suggestion', content_type: 'story_souvenir', status: 'pending' },
  title: 'Un souvenir',
  content: 'Texte de la story.',
  hashtags: '#trail',
};

const V1_PUB = {
  id: 6,
  status: 'validated',
  photo_id: null,
  calendar_entry_id: null,
  calendar_entry: null,
  title: 'Publication V1',
  content: 'Contenu V1.',
  hashtags: '#garmin',
};

function makePage(publication) {
  calls.length = 0;
  const p = new CommunityManagerStudioPage({}, 5);
  p.element = makeEl();
  p.loading = false;
  p.publication = publication;
  return p;
}

let failures = 0;
const check = (label, cond, extra = '') => {
  if (cond) console.log(`  ok - ${label}`);
  else { failures++; console.log(`  FAIL - ${label} ${extra}`); }
};
const findCall = (n) => calls.find(c => c[0] === n);
const hasCall = (n) => calls.some(c => c[0] === n);

// --- A : story suggérée identifiée et affichée
{
  const p = makePage({ ...STORY_PUB });
  const html = p.render().innerHTML;
  check('A: titre « Story suggérée »', html.includes('Story suggérée'));
  check('A: bouton Refuser présent', html.includes('data-action="refuse"'));
  check('A: bouton « Valider la story »', html.includes('Valider la story'));
  check('A: pas de bouton Publier Instagram', !html.includes('data-action="publish"'));
  check('A: pas de badge publication sportive', !html.includes('>publication sportive<'));
}

// --- B : refus réellement appelé (parcours frontend -> API)
{
  const p = makePage({ ...STORY_PUB });
  await p._refuseSuggestion();
  const refuse = findCall('refuse');
  check('B: refuseSuggestion(calendar_entry_id)', !!refuse && refuse[1] === 42, JSON.stringify(refuse));
  check('B: brouillon rechargé après refus', hasCall('getDraft'));
  check('B: message de succès', p.success === 'Suggestion refusée.', `success=${p.success}`);
  check('B: pas d’erreur', p.error === null, `err=${p.error}`);
}

// --- B2 : erreur API du refus
{
  const failing = { ...stubs, refuseSuggestion: record('refuse', async () => { throw { data: { detail: 'Refus impossible' } }; }) };
  const F = new Function(...paramNames, `${src}\nreturn { CommunityManagerStudioPage };`);
  const mod = F(...paramNames.map(k => failing[k]));
  const p = new mod.CommunityManagerStudioPage({}, 5);
  p.element = makeEl();
  p.loading = false;
  p.publication = { ...STORY_PUB };
  await p._refuseSuggestion();
  check('B2: erreur affichée', p.error === 'Refus impossible', `err=${p.error}`);
  check('B2: pas de succès', p.success === null);
}

// --- B3 : refus sans entrée de calendrier
{
  const p = makePage({ ...V1_PUB, calendar_entry_id: null });
  await p._refuseSuggestion();
  check('B3: erreur sans entrée', (p.error || '').includes('entrée de calendrier'), `err=${p.error}`);
  check('B3: aucun appel API', !hasCall('refuse'));
}

// --- C : « Annuler » (vue principale) et « Retour » (vue erreur) sont liés à onBack
{
  calls.length = 0;
  let backCount = 0;
  const p = new CommunityManagerStudioPage({}, 5, null, () => { backCount++; });
  const b1 = makeButton();
  const b2 = makeButton();
  p.element = {
    querySelectorAll: (sel) => (sel === '[data-action="back"]' ? [b1, b2] : []),
    querySelector: () => null,
  };
  p._bindEvents();
  b1.click();
  b2.click();
  check('C: bouton 1 lié', (b1.listeners.click || []).length === 1);
  check('C: bouton 2 lié', (b2.listeners.click || []).length === 1);
  check('C: les 2 déclenchent onBack (2 appels)', backCount === 2, `backCount=${backCount}`);
}

// --- C2 : pas de bouton « Retour » dans l'en-tête du Studio
{
  const p = makePage({ ...V1_PUB });
  const html = p.render().innerHTML;
  check('C2: en-tête sans bouton Retour', !html.includes('>Retour<'), 'bouton Retour présent');
  check('C2: bouton Annuler présent', html.includes('data-action="back"') && html.includes('>Annuler<'));
}

// --- D : effacement puis sauvegarde d'un champ (valeur transmise telle quelle)
{
  const p = makePage({ ...V1_PUB });
  p.element.querySelector = (sel) => {
    if (sel === '[data-form="studio-edit"]') {
      return { elements: { title: { value: '' }, content: { value: 'Texte conservé.', addEventListener() {} }, hashtags: { value: '#garmin', addEventListener() {} } } };
    }
    return null;
  };
  await p._saveForm();
  const upd = findCall('update');
  check('D: title vide transmis ("")', !!upd && upd[2] && upd[2].title === '', JSON.stringify(upd?.[2]));
  check('D: contenu non modifié transmis', upd?.[2]?.content === 'Texte conservé.');
  check('D: message de succès', p.success === 'Modifications enregistrées.');
}

// --- D2 : valeur non vide transmise intacte
{
  const p = makePage({ ...V1_PUB });
  p.element.querySelector = (sel) => {
    if (sel === '[data-form="studio-edit"]') {
      return { elements: { title: { value: 'Nouveau titre' }, content: { value: 'Nouveau texte', addEventListener() {} }, hashtags: { value: '#new', addEventListener() {} } } };
    }
    return null;
  };
  await p._saveForm();
  const upd = findCall('update');
  check('D2: valeurs transmises telles quelles', upd?.[2]?.title === 'Nouveau titre' && upd?.[2]?.hashtags === '#new', JSON.stringify(upd?.[2]));
}

// --- E : publication V1 Garmin sans impact
{
  const p = makePage({ ...V1_PUB });
  const html = p.render().innerHTML;
  check('E: titre « Publication sportive »', html.includes('Publication sportive'));
  check('E: bouton Publier présent et actif', html.includes('data-action="publish"') && !/data-action="publish"[^>]*disabled/.test(html));
  check('E: pas de bouton Refuser', !html.includes('data-action="refuse"'));
  check('E: pas de bouton Valider la story', !html.includes('Valider la story'));
  await p._publish();
  const publish = findCall('publish');
  check('E: action publication appelle l’API avec confirmation', !!publish && publish[1] === 5 && publish[2]?.confirm === true, JSON.stringify(publish));
  check('E: succès affiché après réponse API', p.success === 'Publié avec succès.', `success=${p.success}`);
}

// --- F : sélecteur de photos (non régressé)
{
  const p = makePage({ ...V1_PUB });
  await p._togglePhotoPicker();
  check('F: sélecteur ouvert + photos chargées', p.photoPickerOpen === true && hasCall('getPhotos'));
  p.suggestedPhotos = PHOTOS;
  const html = p.render().innerHTML;
  check('F: grille et badge présents', html.includes('cm-studio-photo-grid') && html.includes('cm-photo-badge--success'));
  await p._selectPhoto(11);
  check('F: sélection envoie photo_id=11', findCall('update')?.[2]?.photo_id === 11);
  await p._removePhoto();
  const updates = calls.filter(c => c[0] === 'update');
  check('F: retrait envoie photo_id=null', updates[updates.length - 1]?.[2]?.photo_id === null);
}

// --- G : titre, texte visuel et légende Instagram sont éditables séparément
{
  const p = makePage({ ...V1_PUB, title: 'Publication V1', content: 'Contenu V1.', hashtags: '#garmin' });
  const html = p.render().innerHTML;
  check('G: aperçu post Instagram présent', html.includes('cm-ig-phone') && html.includes('cm-ig-post-head') && html.includes('cm-ig-post-actions'));
  check('G: champs titre, texte visuel et hashtags présents', /name="title"/.test(html) && /name="content"/.test(html) && /name="hashtags"/.test(html));
  check('G: aperçu reprend titre et légende', html.includes('Publication V1') && html.includes('#garmin'));
  check('G: actions photo, sauvegarde et publication accessibles', ['photos', 'save-form', 'publish'].every(action => html.includes(`data-action="${action}"`)));
  check('G: compteur légende = contenu attendu', p.captionLength === 'Publication V1\n\n#garmin'.length, `len=${p.captionLength}`);
}

// --- H : modal d'aperçu lisible et scrollable (y compris iPhone)
{
  const css = fs.readFileSync(new URL('../../src/public/css/app.css', import.meta.url), 'utf8');
  const header = [...css.matchAll(/\.cm-studio-preview-header\s*\{[^}]*\}/g)].at(-1)?.[0];
  const body = css.match(/\.cm-studio-preview-body\s*\{[^}]*\}/);
  const modal = css.match(/\.cm-studio-preview-modal\s*\{[^}]*\}/);
  check('H: en-tête aperçu avec couleur explicite (pas de blanc sur blanc)', !!header && /color:\s*(?:var\([^)]*,\s*)?#111827/.test(header));
  check('H: corps modal scrollable (flex + min-height: 0)', !!body && /min-height:\s*0/.test(body[0]) && /flex:\s*1/.test(body[0]));
  check('H: scroll tactile iPhone (overflow scrolling)', !!body && /-webkit-overflow-scrolling:\s*touch/.test(body[0]));
  check('H: hauteur dynamique du viewport (dvh)', !!modal && /max-height:\s*90dvh/.test(modal[0]));
}

// --- F2 : sélection multi-photos (sport Garmin -> diaporama Reel + musique)
{
  const p = makePage({
    id: 7,
    status: 'draft',
    photo_id: 3,
    source: 'garmin',
    calendar_entry: null,
    title: '',
    content: '',
    hashtags: '',
    design: { carousel: [] },
  });
  const html = p.render().innerHTML;
  check('F2: publication sport Garmin identifiée', p.isSportPublication === true);
  await p._togglePhotoPicker();
  p.suggestedPhotos = PHOTOS;
  const html2 = p.render().innerHTML;
  check('F2: picker multi rendu (sélecteur de diaporama)', html2.includes('cm-studio-photo-picker') && html2.includes('cm-studio-photo-order') === false);
  await p._togglePhotoSelection(11);
  const html3 = p.render().innerHTML;
  check('F2: badge d ordre affiché', html3.includes('cm-studio-photo-order'));
  check('F2: photo sélectionnée marquée', html3.includes('cm-studio-photo-thumb--selected'));
  await p._applyPhotoSelection();
  const upd = findCall('update');
  check('F2: appliquer envoie photo_ids', !!upd && Array.isArray(upd[2]?.photo_ids) && upd[2]?.photo_ids[0] === 3 && upd[2]?.photo_ids[1] === 11, JSON.stringify(upd?.[2]));
}

console.log(failures === 0 ? '\nTOUS LES TESTS PASSENT' : `\n${failures} ÉCHEC(S)`);
process.exit(failures === 0 ? 0 : 1);
