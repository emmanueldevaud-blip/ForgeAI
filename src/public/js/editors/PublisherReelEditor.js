/**
 * PublisherReelEditor — Hôte du StudioEditorView (montage timeline) dans le
 * parcours Publisher.
 *
 * Pas de chrome propre : StudioEditorView fournit sa propre barre d'outils,
 * le wizard (header/footer du publisher) pilote la navigation.
 */

import { publisherStore } from '../stores/publisherStore.js';
import { publisherDraftService } from '../services/publisherDraftService.js?v=3';
import { createStudioEditorView } from '../editor/StudioEditorView.js?v=2';
import { listPhotos, photoFileUrl, uploadPhotos } from '../services/photosApi.js?v=8';
import { searchInstagramMusic } from '../services/sportApi.js?v=16';

export class PublisherReelEditor {
  constructor(options = {}) {
    this.onSave = options.onSave || (() => {});
    this.onBack = options.onBack || (() => {});
    this.element = null;
    this.editorView = null;
    this._unsubscribeStore = null;
    this._musicItems = [];
  }

  mount(host) {
    this.element = document.createElement('div');
    this.element.className = 'publisher-reel-editor';
    this.element.innerHTML = `
      <div class="pre-music-tools">
        <button type="button" class="pre-music-button" data-action="music-open">♫ Choisir une musique Instagram</button>
        <span class="pre-music-selected" data-music-selected></span>
      </div>
      <section class="pre-music-panel" data-music-panel hidden aria-label="Catalogue de musiques Instagram">
        <form class="pre-music-search" data-music-form>
          <input type="search" minlength="2" maxlength="80" placeholder="Rechercher un titre ou un artiste" aria-label="Rechercher une musique">
          <button type="submit">Rechercher</button>
          <button type="button" data-action="music-close" aria-label="Fermer">✕</button>
        </form>
        <p class="pre-music-status" data-music-status></p>
        <div class="pre-music-results" data-music-results></div>
      </section>
      <div class="pre-studio-host" data-studio-host></div>`;
    host.appendChild(this.element);

    this._subscribeStore();
    this._bindMusicPicker();
    this._syncMusicLabel();
    this._mountStudioEditor();
  }

  _bindMusicPicker() {
    const panel = this.element.querySelector('[data-music-panel]');
    const form = this.element.querySelector('[data-music-form]');
    this.element.querySelector('[data-action="music-open"]').addEventListener('click', () => {
      panel.hidden = !panel.hidden;
      if (!panel.hidden) form.querySelector('input').focus();
    });
    this.element.querySelector('[data-action="music-close"]').addEventListener('click', () => { panel.hidden = true; });
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const query = form.querySelector('input').value.trim();
      if (query.length < 2) return;
      const status = this.element.querySelector('[data-music-status]');
      const results = this.element.querySelector('[data-music-results]');
      status.textContent = 'Recherche…';
      results.innerHTML = '';
      try {
        const response = await searchInstagramMusic(query);
        this._musicItems = Array.isArray(response?.items) ? response.items : [];
        status.textContent = this._musicItems.length ? `${this._musicItems.length} résultat(s)` : 'Aucune musique trouvée.';
        results.innerHTML = this._musicItems.map((track, index) => `
          <button type="button" class="pre-music-result" data-music-index="${index}">
            <span class="pre-music-note">♫</span>
            <span><strong>${this._esc(track.title || 'Titre inconnu')}</strong><small>${this._esc(track.display_artist || track.artist || 'Artiste inconnu')}</small></span>
            <span aria-hidden="true">＋</span>
          </button>`).join('');
        results.querySelectorAll('[data-music-index]').forEach((button) => {
          button.addEventListener('click', () => this._selectMusic(this._musicItems[Number(button.dataset.musicIndex)]));
        });
      } catch (error) {
        status.textContent = error.message || 'Recherche de musique impossible.';
      }
    });
  }

  async _selectMusic(track) {
    if (!track?.audio_id) return;
    const igAudio = {
      audio_id: String(track.audio_id),
      title: track.title || '',
      artist: track.display_artist || track.artist || '',
      duration_in_ms: track.duration_in_ms || null,
      start_time_ms: 0,
    };
    const design = { ...(publisherStore.draft.design || {}), ig_audio: igAudio };
    try {
      await this._updateDraft({ design });
      this.element.querySelector('[data-music-panel]').hidden = true;
      this._syncMusicLabel();
    } catch (error) {
      this.element.querySelector('[data-music-status]').textContent = error.message || 'Enregistrement impossible.';
    }
  }

  _syncMusicLabel() {
    const audio = publisherStore.draft.design?.ig_audio;
    const label = this.element?.querySelector('[data-music-selected]');
    if (label) label.textContent = audio?.title ? `${audio.title}${audio.artist ? ` · ${audio.artist}` : ''}` : '';
  }

  _esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
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
