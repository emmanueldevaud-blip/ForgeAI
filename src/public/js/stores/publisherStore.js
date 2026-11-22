/**
 * Publisher Store — État centralisé pour Community Publisher
 * Gère le brouillon actif, l'UI et la persistance locale
 */

const STORAGE_KEY = 'forgeai_publisher_draft';

const DEFAULT_DRAFT = {
  id: null,
  format: 'post', // 'post' | 'reel' | 'story'
  media: [],       // [{ id, url, thumbnail_url, crop: {x,y,w,h}, order, type: 'photo'|'video', source: 'library'|'garmin'|'upload' }]
  design: {},      // JSON v2 pour post/reel, slides pour story
  caption: { title: '', content: '', hashtags: '', accountId: null },
  music: { trackId: null, start: 0, end: 0, volume: 1, source: null }, // source: 'local' | 'instagram'
  garmin: { activityId: null, stats: {}, overlays: [] },
  status: 'draft', // 'draft' | 'preparing' | 'ready' | 'validated' | 'publishing' | 'published' | 'failed'
  createdAt: null,
  updatedAt: null,
  sourceEntryId: null, // calendar entry id d'origine
};

const DEFAULT_UI = {
  currentStep: 'media', // 'media' | 'adjust' | 'compose' | 'caption' | 'preview' | 'publish'
  previewOpen: false,
  aiPanelOpen: false,
  formatSelectorOpen: false,
  accountSelectorOpen: false,
};

function createDefaultDraft() {
  return {
    id: null,
    format: 'post',
    media: [],
    design: {},
    caption: { title: '', content: '', hashtags: '', accountId: null },
    music: { trackId: null, start: 0, end: 0, volume: 1, source: null },
    garmin: { activityId: null, stats: {}, overlays: [] },
    status: 'draft',
    createdAt: null,
    updatedAt: null,
    sourceEntryId: null,
  };
}

function createDefaultUI() {
  return {
    currentStep: 'media',
    previewOpen: false,
    aiPanelOpen: false,
    formatSelectorOpen: false,
    accountSelectorOpen: false,
  };
}

class PublisherStore {
  constructor() {
    this.draft = createDefaultDraft();
    this.ui = createDefaultUI();
    this.listeners = new Set();
    this._loadFromStorage();
  }

  // ========== Persistance ==========
  _loadFromStorage() {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        this.draft = { ...createDefaultDraft(), ...parsed.draft };
        this.ui = { ...createDefaultUI(), ...parsed.ui };
        // Ne pas restaurer les étapes finales
        if (['publishing', 'published', 'failed'].includes(this.draft.status)) {
          this.draft.status = 'draft';
        }
        if (['preview', 'publish'].includes(this.ui.currentStep)) {
          this.ui.currentStep = 'caption';
        }
      }
    } catch (e) {
      console.warn('[PublisherStore] Impossible de charger le brouillon:', e);
      this._clearStorage();
    }
  }

  _saveToStorage() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        draft: this.draft,
        ui: this.ui,
        savedAt: Date.now(),
      }));
    } catch (e) {
      console.warn('[PublisherStore] Impossible de sauvegarder:', e);
    }
  }

  _clearStorage() {
    localStorage.removeItem(STORAGE_KEY);
  }

  // ========== Abonnements ==========
  subscribe(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  _notify() {
    this._saveToStorage();
    this.listeners.forEach(fn => fn(this.getState()));
  }

  getState() {
    return { draft: { ...this.draft }, ui: { ...this.ui } };
  }

  // ========== Actions Draft ==========
  resetDraft(format = 'post', sourceEntryId = null) {
    this.draft = { ...createDefaultDraft(), format, sourceEntryId, createdAt: Date.now(), updatedAt: Date.now() };
    this.ui = { ...createDefaultUI(), currentStep: 'media' };
    this._notify();
  }

  setFormat(format) {
    if (['post', 'reel', 'story'].includes(format)) {
      this.draft.format = format;
      this.draft.updatedAt = Date.now();
      // Réinitialiser le design selon le format
      if (format === 'story') {
        this.draft.design = { slides: [], designDocuments: [] };
      } else {
        this.draft.design = {};
      }
      this._notify();
    }
  }

  // Médias
  addMedia(mediaItems) {
    const startOrder = this.draft.media.length;
    const newItems = mediaItems.map((m, i) => ({
      id: m.id || `local_${Date.now()}_${i}`,
      url: m.url || m.file_url || `/photos/${m.id}/file`,
      thumbnail_url: m.thumbnail_url || m.url || `/photos/${m.id}/file?size=small`,
      crop: { x: 0, y: 0, w: 1, h: 1 },
      order: startOrder + i,
      type: m.type || (m.mime_type?.startsWith('video/') ? 'video' : 'photo'),
      source: m.source || 'library',
      garminActivityId: m.garminActivityId || null,
    }));
    this.draft.media.push(...newItems);
    this.draft.updatedAt = Date.now();
    this._notify();
  }

  removeMedia(mediaId) {
    this.draft.media = this.draft.media.filter(m => m.id !== mediaId);
    // Réindexer les orders
    this.draft.media.forEach((m, i) => { m.order = i; });
    this.draft.updatedAt = Date.now();
    this._notify();
  }

  reorderMedia(fromIndex, toIndex) {
    const [item] = this.draft.media.splice(fromIndex, 1);
    this.draft.media.splice(toIndex, 0, item);
    this.draft.media.forEach((m, i) => { m.order = i; });
    this.draft.updatedAt = Date.now();
    this._notify();
  }

  updateMediaCrop(mediaId, crop) {
    const media = this.draft.media.find(m => m.id === mediaId);
    if (media) {
      media.crop = { ...media.crop, ...crop };
      this.draft.updatedAt = Date.now();
      this._notify();
    }
  }

  // Légende
  updateCaption(field, value) {
    if (field in this.draft.caption) {
      this.draft.caption[field] = value;
      this.draft.updatedAt = Date.now();
      this._notify();
    }
  }

  // Musique
  setMusic(config) {
    this.draft.music = { ...this.draft.music, ...config };
    this.draft.updatedAt = Date.now();
    this._notify();
  }

  // Garmin
  setGarmin(activityId, stats, overlays = []) {
    this.draft.garmin = { activityId, stats, overlays };
    this.draft.updatedAt = Date.now();
    this._notify();
  }

  // Design (pour post/reel: JSON v2; pour story: slides)
  updateDesign(design) {
    this.draft.design = design;
    this.draft.updatedAt = Date.now();
    this._notify();
  }

  updateStorySlides(slides, designDocuments) {
    if (this.draft.format === 'story') {
      this.draft.design = { slides, designDocuments };
      this.draft.updatedAt = Date.now();
      this._notify();
    }
  }

  // Statut
  setStatus(status) {
    const validStatuses = ['draft', 'preparing', 'ready', 'validated', 'publishing', 'published', 'failed'];
    if (validStatuses.includes(status)) {
      this.draft.status = status;
      this.draft.updatedAt = Date.now();
      this._notify();
    }
  }

  // ========== Actions UI ==========
  setStep(step) {
    const validSteps = ['media', 'adjust', 'compose', 'caption', 'preview', 'publish'];
    if (validSteps.includes(step)) {
      this.ui.currentStep = step;
      this._notify();
    }
  }

  _formatSteps() {
    const format = this.draft?.format || 'post';
    if (format === 'post') return ['media', 'adjust', 'caption', 'preview', 'publish'];
    return ['media', 'adjust', 'compose', 'caption', 'preview', 'publish'];
  }

  nextStep() {
    const steps = this._formatSteps();
    const idx = steps.indexOf(this.ui.currentStep);
    if (idx >= 0 && idx < steps.length - 1) this.setStep(steps[idx + 1]);
  }

  prevStep() {
    const steps = this._formatSteps();
    const idx = steps.indexOf(this.ui.currentStep);
    if (idx > 0) this.setStep(steps[idx - 1]);
  }

  togglePreview(open) {
    this.ui.previewOpen = open !== undefined ? open : !this.ui.previewOpen;
    this._notify();
  }

  toggleAIPanel(open) {
    this.ui.aiPanelOpen = open !== undefined ? open : !this.ui.aiPanelOpen;
    this._notify();
  }

  toggleFormatSelector(open) {
    this.ui.formatSelectorOpen = open !== undefined ? open : !this.ui.formatSelectorOpen;
    this._notify();
  }

  toggleAccountSelector(open) {
    this.ui.accountSelectorOpen = open !== undefined ? open : !this.ui.accountSelectorOpen;
    this._notify();
  }

  // ========== Export/Import ==========
  exportDraft() {
    return JSON.stringify(this.draft, null, 2);
  }

  importDraft(json) {
    try {
      const parsed = JSON.parse(json);
      this.draft = { ...createDefaultDraft(), ...parsed };
      this.draft.updatedAt = Date.now();
      this._notify();
      return true;
    } catch (e) {
      console.error('[PublisherStore] Import invalide:', e);
      return false;
    }
  }

  // ========== Nettoyage ==========
  clear() {
    this._clearStorage();
    this.draft = createDefaultDraft();
    this.ui = createDefaultUI();
    // Ne pas appeler _notify() pour éviter de ré-écrire un brouillon vide dans le storage
    this.listeners.forEach(fn => fn(this.getState()));
  }
}

// Instance singleton
export const publisherStore = new PublisherStore();

// Helpers pour composants
export function usePublisherStore() {
  return publisherStore;
}

export function selectDraft(selector) {
  return selector(publisherStore.draft);
}

export function selectUI(selector) {
  return selector(publisherStore.ui);
}