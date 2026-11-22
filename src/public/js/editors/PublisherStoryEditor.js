/**
 * PublisherStoryEditor — Éditeur Story (wrap StoryEditorView)
 * Slides 9:16, navigation, stickers, dessin, texte
 */

import { publisherStore } from '../stores/publisherStore.js';
import { publisherDraftService } from '../services/publisherDraftService.js';
import { createStoryEditorView } from '../editor/StoryEditorView.js?v=1';

export class PublisherStoryEditor {
  constructor(options = {}) {
    this.onSave = options.onSave || (() => {});
    this.onBack = options.onBack || (() => {});
    this.element = null;
    this.editorView = null;
    this._unsubscribeStore = null;
  }

  mount(host) {
    this.element = document.createElement('div');
    this.element.className = 'publisher-story-editor';
    this.element.innerHTML = this._renderShell();
    host.appendChild(this.element);

    this._bindShell();
    this._subscribeStore();
    this._mountStoryEditor();
  }

  _subscribeStore() {
    this._unsubscribeStore = publisherStore.subscribe(state => {
      // Sync format
    });
  }

  _renderShell() {
    return `
      <header class="pse-header">
        <div class="pse-header-left">
          <button type="button" class="pse-btn pse-btn-back" data-action="back">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>
            </svg>
          </button>
          <h2>Éditeur Story</h2>
        </div>
        <div class="pse-header-right">
          <button type="button" class="pse-btn pse-btn-secondary" data-action="add-slide">+ Slide</button>
          <button type="button" class="pse-btn pse-btn-primary" data-action="save">Suivant</button>
        </div>
      </header>

      <main class="pse-main" data-main>
        <div class="pse-story-host" data-story-host></div>
      </main>

      <footer class="pse-footer">
        <div class="pse-footer-left">
          <span class="pse-slide-count" data-slide-count>0 slides</span>
        </div>
        <div class="pse-footer-right">
          <button type="button" class="pse-btn pse-btn-ghost" data-action="preview">Aperçu</button>
        </div>
      </footer>
    `;
  }

  _bindShell() {
    this.element.querySelector('[data-action="back"]').addEventListener('click', () => this.onBack());
    this.element.querySelector('[data-action="save"]').addEventListener('click', () => this.onSave());
    this.element.querySelector('[data-action="add-slide"]').addEventListener('click', () => this._addSlide());
    this.element.querySelector('[data-action="preview"]').addEventListener('click', () => this._preview());
  }

  _mountStoryEditor() {
    const host = this.element.querySelector('[data-story-host]');
    const draft = publisherStore.draft;

    // Construire un StoryDraft compatible avec StoryEditorView
    const storyDraft = {
      id: draft.id || 'new',
      slides: draft.design?.slides || draft.media.map((m, i) => ({
        type: 'photo',
        photo_indices: [i],
        hook: i === 0 ? draft.caption.title : undefined,
        caption: i > 0 ? draft.caption.content : undefined,
      })),
      design_documents: draft.design?.designDocuments || draft.media.map((m, i) => ({
        version: 2,
        format: { width: 1080, height: 1920, type: 'story_916', platform: 'instagram' },
        background: { type: 'photo', photo_id: parseInt(m.id.replace('photo_', '')) || m.id, crop: m.crop },
        elements: [],
        carousel: [parseInt(m.id.replace('photo_', '')) || m.id],
        timeline: { fps: 30, tracks: [] },
      })),
    };

    this.editorView = createStoryEditorView({
      draft: storyDraft,
      deps: {
        photoFileUrl: (id) => `/photos/${id}/file`,
        updateDraft: (id, data) => publisherDraftService.save({ design: data }),
        updateSlideDesign: (id, slideIndex, design) => publisherDraftService.saveStorySlide(id, slideIndex, design),
        renderSlide: (id, slideIndex) => publisherDraftService.renderStorySlide(id, slideIndex),
        getRenderJobs: (id) => publisherDraftService.getStoryRenderJobs(id),
        validateDraft: (id) => publisherDraftService.validate(),
        publishDraft: (id, data) => publisherDraftService.publish(data),
        previewDraft: (id) => publisherDraftService.preview(id),
      },
      callbacks: {
        onClose: () => this.onBack(),
        onSave: async (draftId, data) => {
          publisherStore.updateStorySlides(data.slides, data.design_documents);
          this.onSave();
        },
        onPublish: async (draftId, data) => {
          // Géré par PublisherPreview
        },
      },
    });

    this.editorView.mount(host);
    this._updateSlideCount();
  }

  _addSlide() {
    if (this.editorView) {
      this.editorView._addSlide();
      this._updateSlideCount();
    }
  }

  _preview() {
    publisherStore.setStep('preview');
  }

  _updateSlideCount() {
    const countEl = this.element.querySelector('[data-slide-count]');
    if (countEl && this.editorView) {
      const count = this.editorView.slides?.length || 0;
      countEl.textContent = `${count} slide${count > 1 ? 's' : ''}`;
    }
  }

  destroy() {
    if (this._unsubscribeStore) this._unsubscribeStore();
    if (this.editorView) this.editorView.destroy();
    if (this.element && this.element.parentNode) this.element.parentNode.removeChild(this.element);
  }
}

export function createPublisherStoryEditor(options) {
  return new PublisherStoryEditor(options);
}