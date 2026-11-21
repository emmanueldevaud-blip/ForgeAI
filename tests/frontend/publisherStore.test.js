/**
 * Tests for Publisher Store - Node.js version
 */

// Simple test runner without ES modules
const STORAGE_KEY = 'forgeai_publisher_draft';

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

  _loadFromStorage() {
    try {
      const stored = global.localStorage?.getItem?.(STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        this.draft = { ...createDefaultDraft(), ...parsed.draft };
        this.ui = { ...createDefaultUI(), ...parsed.ui };
        if (['publishing', 'published', 'failed'].includes(this.draft.status)) {
          this.draft.status = 'draft';
        }
        if (['preview', 'publish'].includes(this.ui.currentStep)) {
          this.ui.currentStep = 'draft';
        }
      }
    } catch (e) {
      console.warn('[PublisherStore] Impossible de charger le brouillon:', e);
      this._clearStorage();
    }
  }

  _saveToStorage() {
    try {
      global.localStorage?.setItem?.(STORAGE_KEY, JSON.stringify({
        draft: this.draft,
        ui: this.ui,
        savedAt: Date.now(),
      }));
    } catch (e) {
      console.warn('[PublisherStore] Impossible de sauvegarder:', e);
    }
  }

  _clearStorage() {
    global.localStorage?.removeItem?.(STORAGE_KEY);
  }

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

  resetDraft(format = 'post', sourceEntryId = null) {
    this.draft = { ...createDefaultDraft(), format, sourceEntryId, createdAt: Date.now(), updatedAt: Date.now() };
    this.ui = { ...createDefaultUI(), currentStep: 'media' };
    this._notify();
  }

  setFormat(format) {
    if (['post', 'reel', 'story'].includes(format)) {
      this.draft.format = format;
      this.draft.updatedAt = Date.now();
      if (format === 'story') {
        this.draft.design = { slides: [], designDocuments: [] };
      } else {
        this.draft.design = {};
      }
      this._notify();
    }
  }

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

  updateCaption(field, value) {
    if (field in this.draft.caption) {
      this.draft.caption[field] = value;
      this.draft.updatedAt = Date.now();
      this._notify();
    }
  }

  setMusic(config) {
    this.draft.music = { ...this.draft.music, ...config };
    this.draft.updatedAt = Date.now();
    this._notify();
  }

  setGarmin(activityId, stats, overlays = []) {
    this.draft.garmin = { activityId, stats, overlays };
    this.draft.updatedAt = Date.now();
    this._notify();
  }

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

  setStatus(status) {
    const validStatuses = ['draft', 'preparing', 'ready', 'validated', 'publishing', 'published', 'failed'];
    if (validStatuses.includes(status)) {
      this.draft.status = status;
      this.draft.updatedAt = Date.now();
      this._notify();
    }
  }

  setStep(step) {
    const validSteps = ['media', 'adjust', 'compose', 'caption', 'preview', 'publish'];
    if (validSteps.includes(step)) {
      this.ui.currentStep = step;
      this._notify();
    }
  }

  nextStep() {
    const steps = ['media', 'adjust', 'compose', 'caption', 'preview', 'publish'];
    const idx = steps.indexOf(this.ui.currentStep);
    if (idx < steps.length - 1) this.setStep(steps[idx + 1]);
  }

  prevStep() {
    const steps = ['media', 'adjust', 'compose', 'caption', 'preview', 'publish'];
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

  clear() {
    this._clearStorage();
    this.draft = createDefaultDraft();
    this.ui = createDefaultUI();
    this.listeners.forEach(fn => fn(this.getState()));
  }
}

// Mock localStorage for Node
const mockStorage = {};
global.localStorage = {
  getItem: (key) => mockStorage[key] || null,
  setItem: (key, value) => { mockStorage[key] = value; },
  removeItem: (key) => { delete mockStorage[key]; },
};

// Test runner
let passed = 0;
let failed = 0;

function assert(condition, message) {
  if (!condition) throw new Error(`Assertion failed: ${message}`);
}

function assertEqual(actual, expected, message) {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`${message}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

function test(name, fn) {
  // Clear mock storage before each test for isolation
  Object.keys(mockStorage).forEach(key => delete mockStorage[key]);
  try {
    fn();
    console.log(`  ✅ ${name}`);
    passed++;
  } catch (err) {
    console.log(`  ❌ ${name}: ${err.message}`);
    failed++;
  }
}

async function runTests() {
  console.log('\n🧪 Testing Publisher Store...\n');

  const store = new PublisherStore();

  test('resetDraft sets format and sourceEntryId', () => {
    store.resetDraft('post', 123);
    const s = store.getState();
    assert(s.draft.format === 'post', 'Format should be post');
    assert(s.draft.sourceEntryId === 123, 'Source entry ID should be 123');
    assert(s.draft.status === 'draft', 'Status should be draft');
    assert(s.ui.currentStep === 'media', 'Step should be media');
  });

  test('setFormat changes format and resets design', () => {
    store.setFormat('reel');
    const s = store.getState();
    assert(s.draft.format === 'reel', 'Format should be reel');
  });

  test('setFormat story creates slides structure', () => {
    store.setFormat('story');
    const s = store.getState();
    assert(s.draft.format === 'story', 'Format should be story');
    assert(Array.isArray(s.draft.design.slides), 'Slides should be array');
    assert(Array.isArray(s.draft.design.designDocuments), 'Design documents should be array');
  });

  test('addMedia adds items with order', () => {
    store.resetDraft('post');
    store.addMedia([
      { id: 'photo_1', url: '/photos/1/file', thumbnail_url: '/photos/1/thumb', type: 'photo', source: 'library' },
      { id: 'photo_2', url: '/photos/2/file', thumbnail_url: '/photos/2/thumb', type: 'photo', source: 'library' },
    ]);
    const s = store.getState();
    assert(s.draft.media.length === 2, 'Should have 2 media items');
    assert(s.draft.media[0].order === 0, 'First item order should be 0');
    assert(s.draft.media[1].order === 1, 'Second item order should be 1');
  });

  test('removeMedia removes item and reindexes', () => {
    store.removeMedia('photo_1');
    const s = store.getState();
    assert(s.draft.media.length === 1, 'Should have 1 media item');
    assert(s.draft.media[0].id === 'photo_2', 'Remaining item should be photo_2');
    assert(s.draft.media[0].order === 0, 'Order should be reindexed to 0');
  });

  test('reorderMedia moves items correctly', () => {
    const store = new PublisherStore();
    store.resetDraft('post');
    store.addMedia([
      { id: 'photo_1', url: '/photos/1/file', thumbnail_url: '/photos/1/thumb', type: 'photo', source: 'library' },
      { id: 'photo_2', url: '/photos/2/file', thumbnail_url: '/photos/2/thumb', type: 'photo', source: 'library' },
      { id: 'photo_3', url: '/photos/3/file', thumbnail_url: '/photos/3/thumb', type: 'photo', source: 'library' },
    ]);
    store.reorderMedia(0, 2); // Move first to last (index 2 = after last item)
    const s = store.getState();
    // After moving index 0 to index 2 (end), order should be: photo_2, photo_3, photo_1
    assert(s.draft.media[0].id === 'photo_2', 'First should be photo_2');
    assert(s.draft.media[1].id === 'photo_3', 'Second should be photo_3');
    assert(s.draft.media[2].id === 'photo_1', 'Third should be photo_1');
  });

  test('updateCaption sets fields', () => {
    store.updateCaption('title', 'Mon titre');
    store.updateCaption('hashtags', '#trail #running');
    const s = store.getState();
    assert(s.draft.caption.title === 'Mon titre', 'Title should be set');
    assert(s.draft.caption.hashtags === '#trail #running', 'Hashtags should be set');
  });

  test('step navigation works', () => {
    store.setStep('caption');
    assert(store.getState().ui.currentStep === 'caption', 'Step should be caption');
    store.nextStep();
    assert(store.getState().ui.currentStep === 'preview', 'Next step should be preview');
    store.prevStep();
    assert(store.getState().ui.currentStep === 'caption', 'Prev step should be caption');
  });

  test('setGarmin stores activity and stats', () => {
    store.setGarmin(456, { distance: '10.5 km', elevation: '500 m' }, [{ type: 'stats' }]);
    const s = store.getState();
    assert(s.draft.garmin.activityId === 456, 'Garmin activity ID should be set');
    assert(s.draft.garmin.stats.distance === '10.5 km', 'Stats should be set');
  });

  test('updateDesign updates design object', () => {
    store.updateDesign({ format: { type: 'post_carousel' }, elements: [] });
    const s = store.getState();
    assert(s.draft.design.format?.type === 'post_carousel', 'Design should be updated');
  });

  test('updateStorySlides works for story format', () => {
    store.setFormat('story');
    store.updateStorySlides(
      [{ type: 'photo' }, { type: 'stats' }],
      [{ version: 2 }, { version: 2 }]
    );
    const s = store.getState();
    assert(s.draft.design.slides.length === 2, 'Should have 2 slides');
    assert(s.draft.design.designDocuments.length === 2, 'Should have 2 design docs');
  });

  test('setStatus updates status', () => {
    store.setStatus('validated');
    assert(store.getState().draft.status === 'validated', 'Status should be validated');
  });

  test('exportDraft returns JSON string', () => {
    const exported = store.exportDraft();
    assert(typeof exported === 'string', 'Export should be string');
    assert(exported.includes('Mon titre'), 'Export should contain title');
  });

  test('importDraft parses JSON', () => {
    const exported = store.exportDraft();
    const imported = store.importDraft(exported);
    assert(imported === true, 'Import should succeed');
  });

  test('clear resets everything', () => {
    const store = new PublisherStore();
    store.resetDraft('post');
    store.addMedia([{ id: 'test_1', url: '/test', thumbnail_url: '/test', type: 'photo', source: 'library' }]);
    store.updateCaption('title', 'Test');
    store.clear();
    const s = store.getState();
    assert(s.draft.format === 'post', 'Should reset to post');
    assert(s.draft.media.length === 0, 'Media should be empty');
    assert(s.draft.caption.title === '', 'Caption should be empty');
  });

  console.log(`\n📊 Results: ${passed} passed, ${failed} failed`);
  if (failed > 0) process.exit(1);
}

runTests();