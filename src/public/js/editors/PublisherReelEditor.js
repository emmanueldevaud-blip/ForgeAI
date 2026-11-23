/**
 * PublisherReelEditor — Hôte du StudioEditorView (montage timeline) dans le
 * parcours Publisher.
 *
 * Pas de chrome propre : StudioEditorView fournit sa propre barre d'outils,
 * le wizard (header/footer du publisher) pilote la navigation.
 */

import { publisherStore } from '../stores/publisherStore.js';
import { publisherDraftService } from '../services/publisherDraftService.js';
import { createStudioEditorView } from '../editor/StudioEditorView.js?v=2';
import { listPhotos, photoFileUrl, uploadPhotos } from '../services/photosApi.js?v=8';

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
    this.element.innerHTML = '<div class="pre-studio-host" data-studio-host></div>';
    host.appendChild(this.element);

    this._subscribeStore();
    this._mountStudioEditor();
  }

  _subscribeStore() {
    // StudioEditorView gère son propre état (EditorState) : pas de re-render.
    this._unsubscribeStore = publisherStore.subscribe(() => {});
  }

  /**
   * Pousse le design (et éventuellement la photo exportée) dans le store
   * local, puis dans le brouillon backend s'il existe.
   */
  async _updateDraft(data = {}) {
    if (data.design) publisherStore.updateDesign(data.design);

    if (data.photo_id !== undefined && data.photo_id !== null) {
      const pid = String(data.photo_id);
      publisherStore.draft.media = [
        {
          id: pid,
          url: `/photos/${pid}/file`,
          thumbnail_url: `/photos/${pid}/file?size=small`,
          crop: { x: 0, y: 0, w: 1, h: 1 },
          order: 0,
          type: 'photo',
          source: 'library',
        },
      ];
      publisherStore._notify();
    }

    if (publisherDraftService.currentDraftId) {
      await publisherDraftService.save({
        design: data.design,
        photoId: data.photo_id,
        visualType: data.visual_type,
      });
    }
    return true;
  }

  /**
   * Sauvegarde le design courant du Studio dans le store local
   * (et backend si un brouillon est chargé). Appelée avant de quitter
   * l'étape compose pour éviter toute perte de modification.
   */
  async save() {
    if (!this.editorView) return;
    const design = this.editorView.state.toJSON();
    await this._updateDraft({ design });
  }

  _mountStudioEditor() {
    const host = this.element.querySelector('[data-studio-host]');
    const draft = publisherStore.draft;
    const design = { ...(draft.design || {}) };

    // Assurer le format Reel (9:16)
    if (!design.format) {
      design.format = { width: 1080, height: 1920, type: 'reel_916', platform: 'instagram' };
    }

    const publication = {
      id: publisherDraftService.currentDraftId || draft.id || 'new',
      design,
      photo_id: null,
      photo_locked: false,
    };

    this.editorView = createStudioEditorView({
      publication,
      deps: {
        publicationId: publication.id,
        updateDraft: (id, data) => this._updateDraft(data),
        uploadPhotos: (files) => uploadPhotos(files),
        listPhotos: (params) => listPhotos(params),
        getSuggestedPhotos: () =>
          publisherDraftService.getSuggestedPhotos(12).catch(() => []),
        photoFileUrl: (id, size) => photoFileUrl(id, size || 'medium'),
        createRender: (publicationId) => publisherDraftService.createRender(publicationId),
        getRenderJob: (jobId) => publisherDraftService.getRenderJob(jobId),
        cancelRender: (jobId) => publisherDraftService.cancelRender(jobId),
        renderFileUrl: (jobId) => `/studio-renders/${jobId}.mp4`,
      },
      callbacks: {
        onClose: () => this.onBack(),
        // onApplied : le design/photo sont déjà poussés par updateDraft,
        // on laisse l'utilisateur relire avant de passer à l'étape suivante.
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

export function createPublisherReelEditor(options) {
  return new PublisherReelEditor(options);
}
