/**
 * PublisherReelEditor — Éditeur Reel (wrap StudioEditorView)
 * Timeline, vidéo, audio, transitions, couverture
 */

import { publisherStore } from '../stores/publisherStore.js';
import { publisherDraftService } from '../services/publisherDraftService.js';
import { createStudioEditorView } from '../editor/StudioEditorView.js?v=2';

export class PublisherReelEditor {
  constructor(options = {}) {
    this.onSave = options.onSave || (() => {});
    this.onBack = options.onBack || (() => {});
    this.element = null;
    this.editorView = null;
    this._unsubscribeStore = null;
  }

  mount(host) {
    this.element = document.createElement('div');
    this.element.className = 'publisher-reel-editor';
    this.element.innerHTML = this._renderShell();
    host.appendChild(this.element);

    this._bindShell();
    this._subscribeStore();
    this._mountStudioEditor();
  }

  _subscribeStore() {
    this._unsubscribeStore = publisherStore.subscribe(state => {
      // Le StudioEditorView gère son propre état via EditorState
      // On sync juste le format
    });
  }

  _renderShell() {
    return `
      <header class="pre-header">
        <div class="pre-header-left">
          <button type="button" class="pre-btn pre-btn-back" data-action="back">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>
            </svg>
          </button>
          <h2>Monteur Reel</h2>
        </div>
        <div class="pre-header-right">
          <button type="button" class="pre-btn pre-btn-secondary" data-action="add-media">+ Ajouter</button>
          <button type="button" class="pre-btn pre-btn-primary" data-action="save">Suivant</button>
        </div>
      </header>

      <main class="pre-main" data-main>
        <div class="pre-studio-host" data-studio-host></div>
      </main>

      <footer class="pre-footer">
        <div class="pre-footer-left">
          <span class="pre-duration" data-duration>0:00</span>
        </div>
        <div class="pre-footer-right">
          <button type="button" class="pre-btn pre-btn-ghost" data-action="preview">Aperçu</button>
        </div>
      </footer>
    `;
  }

  _bindShell() {
    this.element.querySelector('[data-action="back"]').addEventListener('click', () => this.onBack());
    this.element.querySelector('[data-action="save"]').addEventListener('click', () => this.onSave());
    this.element.querySelector('[data-action="add-media"]').addEventListener('click', () => this._addMedia());
    this.element.querySelector('[data-action="preview"]').addEventListener('click', () => this._preview());
  }

  _mountStudioEditor() {
    const host = this.element.querySelector('[data-studio-host]');
    const design = publisherStore.draft.design || {};

    // Assurer le format Reel (vidéo 16:9 ou 9:16)
    if (!design.format) {
      design.format = { width: 1080, height: 1920, type: 'reel_916', platform: 'instagram' };
    }

    this.editorView = createStudioEditorView({
      draft: { id: publisherStore.draft.id || 'new', design },
      deps: {
        updateDraft: (id, data) => publisherDraftService.save({ design: data.design }),
        uploadPhotos: () => {}, // TODO
        getSuggestedPhotos: () => [],
        listPhotos: () => [],
        photoFileUrl: (id) => `/photos/${id}/file`,
        publicationPhotoUrl: (id) => `/photos/${id}/file`,
        createRender: (publicationId) => publisherDraftService.createRender?.(publicationId),
        getRenderJob: (jobId) => publisherDraftService.getRenderJob?.(jobId),
        cancelRender: (jobId) => publisherDraftService.cancelRender?.(jobId),
        renderFileUrl: (jobId) => `/studio-renders/${jobId}.mp4`,
      },
      callbacks: {
        onClose: () => this.onBack(),
        onSave: async (id, data) => {
          publisherStore.updateDesign(data);
          this.onSave();
        },
        onPublish: async (id, data) => {
          // Géré par PublisherPreview
        },
      },
    });

    this.editorView.mount(host);
  }

  _addMedia() {
    // Ouvrir le media picker en mode ajout
    // TODO: Intégrer PublisherMediaPicker en modal
    alert('Ajout média - à connecter avec PublisherMediaPicker');
  }

  _preview() {
    publisherStore.setStep('preview');
  }

  destroy() {
    if (this._unsubscribeStore) this._unsubscribeStore();
    if (this.editorView) this.editorView.destroy();
    if (this.element && this.element.parentNode) this.element.parentNode.removeChild(this.element);
  }
}

export function createPublisherReelEditor(options) {
  return new PublisherReelEditor(options);
}