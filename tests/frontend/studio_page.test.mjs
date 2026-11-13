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

// --- C : les deux boutons Annuler sont liés et déclenchent le même comportement
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

// --- D : effacement puis sauvegarde d'un champ (valeur transmise telle quelle)
{
  const p = makePage({ ...V1_PUB });
  p.element.querySelector = (sel) => {
    if (sel === '[data-form="studio-edit"]') {
      return { elements: { title: { value: '' }, content: { value: 'Texte conservé.' }, hashtags: { value: '#garmin' } } };
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
      return { elements: { title: { value: 'Nouveau titre' }, content: { value: 'Nouveau texte' }, hashtags: { value: '#new' } } };
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

console.log(failures === 0 ? '\nTOUS LES TESTS PASSENT' : `\n${failures} ÉCHEC(S)`);
process.exit(failures === 0 ? 0 : 1);
