// Tests de la CommunityPublisherPage — wiring evenements / etapes / publication.
// Exécution : node tests/frontend/community_publisher_page.test.mjs
import fs from 'node:fs';

const FILE = new URL('../../src/public/js/pages/CommunityPublisherPage.js', import.meta.url);
let src = fs.readFileSync(FILE, 'utf8');
src = src.replace(/^import\s[\s\S]*?from\s+['"][^'"]+['"];?\s*$/gm, '');
src = src.replace(/export class/g, 'class');
src = src.replace(/export function/g, 'function');

const failures = [];
function check(name, cond) {
  if (cond) console.log(`  OK ${name}`);
  else { failures.push(name); console.log(`  KO ${name}`); }
}

// --- Stub DOM : element factice avec recherche par attribut ---
function makeFake() {
  const handlers = {};
  const subs = new Map();
  const el = {
    className: '',
    children: [],
    _html: '',
    set innerHTML(v) { this._html = String(v); this.children = []; },
    get innerHTML() { return this._html; },
    appendChild(c) { el.children.push(c); return c; },
    addEventListener(type, handler) { (handlers[type] ||= []).push(handler); },
    querySelector(sel) {
      const cached = subs.get(sel);
      if (cached) return cached;
      for (const child of el.children) {
        const found = child.querySelector(sel);
        if (found) { subs.set(sel, found); return found; }
      }
      const created = makeFake();
      subs.set(sel, created);
      return created;
    },
    querySelectorAll(sel) {
      const cached = subs.get(sel);
      if (cached) return cached;
      const found = [];
      for (const child of el.children) found.push(...child.querySelectorAll(sel));
      if (found.length) { subs.set(sel, found); return found; }
      const created = [makeFake()];
      subs.set(sel, created);
      return created;
    },
    click() { (handlers.click || []).forEach(h => h({ stopPropagation() {} })); },
    __handlers: handlers,
    __subs: subs,
    dataset: {},
    disabled: false,
    textContent: '',
    style: {},
    classList: { add() {}, remove() {}, toggle() {} },
  };
  return el;
}

const documentStub = { createElement: () => makeFake() };

// --- Stubs store / services / createurs ---
const calls = { nextStep: 0, prevStep: 0, publish: 0, saveDraft: 0, routerNavigate: null, pickerMounted: false };
const listeners = new Set();
const publisherStoreStub = {
  draft: {
    format: 'post', media: [], design: {},
    caption: { title: '', content: '', hashtags: '', accountId: null },
    music: {}, garmin: { activityId: null, stats: {}, overlays: [] },
    status: 'draft',
  },
  ui: { currentStep: 'media', previewOpen: false, aiPanelOpen: false, formatSelectorOpen: false, accountSelectorOpen: false },
  subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); },
  _notify() { listeners.forEach(fn => fn({ draft: this.draft, ui: this.ui })); },
  resetDraft() { this.ui.currentStep = 'media'; this._notify(); },
  setStep(step) { this.ui.currentStep = step; this._notify(); },
  nextStep() { calls.nextStep++; },
  prevStep() { calls.prevStep++; },
  clear() { calls.cleared = true; },
  updateCaption() {},
};
const publisherDraftServiceStub = {
  save: async () => { calls.saveDraft++; return ({}); },
  publish: async () => { calls.publish++; return { status: 'published' }; },
};
const createPublisherMediaPickerStub = () => {
  calls.pickerMounted = true;
  return { mount: () => {}, destroy: () => {} };
};
const createPublisherCaptionEditorStub = () => ({ mount: () => {}, destroy: () => {} });
const createPublisherPreviewStub = () => ({ mount: () => {}, destroy: () => {} });
const createPublisherReelEditorStub = () => ({ mount: () => {}, destroy: () => {} });
const createPublisherStoryEditorStub = () => ({ mount: () => {}, destroy: () => {} });
const routerStub = { navigate: (to) => { calls.routerNavigate = to; } };

const paramNames = [
  'publisherStore', 'publisherDraftService',
  'createPublisherMediaPicker', 'createPublisherCaptionEditor', 'createPublisherPreview',
  'createPublisherReelEditor', 'createPublisherStoryEditor',
  'document', 'router',
];
const factory = new Function(...paramNames, `${src}\nreturn { CommunityPublisherPage };`);
const { CommunityPublisherPage } = factory(
  publisherStoreStub, publisherDraftServiceStub, createPublisherMediaPickerStub,
  createPublisherCaptionEditorStub, createPublisherPreviewStub, createPublisherReelEditorStub,
  createPublisherStoryEditorStub, documentStub, routerStub,
);

function makePage() {
  calls.nextStep = 0; calls.prevStep = 0; calls.publish = 0; calls.saveDraft = 0;
  calls.routerNavigate = null; calls.pickerMounted = false;
  return new CommunityPublisherPage(routerStub, { format: 'post' });
}

// --- Tests ---
{
  console.log('T1: render monte le media picker et wire le footer');
  const page = makePage();
  const el = page.render();
  check('T1: media picker monte sur l etape media', calls.pickerMounted === true);
  check('T1: bouton header Retour wired', (el.__subs.get('[data-action="back"]').__handlers.click || []).length > 0);
  check('T1: bouton Brouillon wired', (el.__subs.get('[data-action="save-draft"]').__handlers.click || []).length > 0);
  const nextBtn = el.__subs.get('[data-action="next-step"]');
  check('T1: bouton Suivant wired', (nextBtn.__handlers.click || []).length > 0);
  nextBtn.click();
  check('T1: Suivant sur media -> nextStep', calls.nextStep === 1);
}

{
  console.log('T2: footer final (etape publish) -> declenche la publication');
  const page = makePage();
  page.render();
  publisherStoreStub.ui.currentStep = 'publish';
  publisherStoreStub._notify();
  const publishHost = page.element.querySelector('[data-publish-host]');
  const publishBtn = publishHost.querySelector('[data-action="publish-final"]');
  publishBtn.click();
  check('T2: bouton Publier declenche _publish', calls.publish === 1);
}

{
  console.log('T3: bouton Retour header -> navigation back');
  const page = makePage();
  const el = page.render();
  el.__subs.get('[data-action="back"]').click();
  check('T3: retour -> navigate community-manager', calls.routerNavigate === '/community-manager');
}

console.log(failures.length === 0 ? '\nTOUS LES TESTS PASSENT' : `\n${failures.length} ECHEC(S)`);
process.exit(failures.length === 0 ? 0 : 1);
