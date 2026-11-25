/**
 * PublisherStoryEditor — Hôte du StoryEditorView dans le parcours Publisher
 *
 * Pas de chrome propre : StoryEditorView fournit sa propre barre d'outils,
 * le wizard (header/footer du publisher) pilote la navigation.
 */

import { publisherStore } from '../stores/publisherStore.js';
import { createStoryEditorView } from '../editor/StoryEditorView.js?v=3';
import { listPhotos, uploadPhotos } from '../services/photosApi.js?v=8';
import { searchInstagramMusic } from '../services/sportApi.js?v=16';

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
    this.element.innerHTML = '<div class="pse-story-host" data-story-host></div>';
    host.appendChild(this.element);

    this._subscribeStore();
    this._mountStoryEditor();
  }

  _subscribeStore() {
    this._unsubscribeStore = publisherStore.subscribe(() => {
      // Le StoryEditorView gère son propre état interne
    });
  }

  _photoId(mediaItem) {
    const raw = String(mediaItem?.id ?? '').replace(/^photo_/, '');
    if (raw === '') return null;
    const n = Number(raw);
    return Number.isFinite(n) ? n : null;
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
      design_documents: draft.design?.designDocuments || draft.media.map((m) => {
        const photoId = this._photoId(m);
        return {
          version: 2,
          format: { width: 1080, height: 1920, type: 'story_916', platform: 'instagram' },
          background: { type: 'photo', photo_id: photoId, crop: m.crop },
          elements: [],
          carousel: photoId !== null ? [photoId] : [],
          timeline: { fps: 30, tracks: [] },
        };
      }),
    };

    this.editorView = createStoryEditorView({
      draft: storyDraft,
      deps: {
        publicationId: draft.id || null,
        photoFileUrl: (id, size) => `/photos/${id}/file${size ? `?size=${size}` : ''}`,
        uploadPhotos: (files) => uploadPhotos(files),
        listPhotos: (params) => listPhotos(params),
        getSuggestedPhotos: () => Promise.resolve([]),
        searchInstagramMusic: (query) => searchInstagramMusic(query),
      },
      callbacks: {
        onClose: () => this.onBack(),
        onSave: async (draftId, data) => {
          publisherStore.updateStorySlides(data.slides, data.design_documents);
          this.onSave();
        },
        onPublish: async (draftId, data) => {
          // "Valider et publier" de la modale d'aperçu Story :
          // on sauvegarde les slides puis on rejoint l'aperçu final du wizard.
          publisherStore.updateStorySlides(data.slides, data.design_documents);
          publisherStore.setStep('preview');
        },
      },
    });

    this.editorView.mount(host);
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
