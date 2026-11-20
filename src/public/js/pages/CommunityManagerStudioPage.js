/**
 * Community Manager Studio Page - Refonte minimaliste
 * Vérifier, modifier et publier les contenus préparés.
 * Seul le strict nécessaire : photo, titre, texte, hashtags.
 */

// Instagram autorise au maximum 2 200 caractères dans une légende (accroche + hashtags).
const INSTAGRAM_CAPTION_MAX_LENGTH = 2200;
import {
  getStudioDraft,
  updateStudioDraft,
  validateStudioDraft,
  publishStudioDraft,
  publishStudioDraftFacebook,
  publishStudioDraftBoth,
  previewStudioDraft,
  regeneratePublicationContent,
  getSuggestedPhotos,
  refuseSuggestion,
  getInstagramConnectionStatus,
} from '../services/sportApi.js?v=14';
import { publicationPhotoUrl } from '../services/sportApi.js?v=14';
import {
  uploadPhotos,
  listPhotos,
  photoFileUrl,
  createStudioRender,
  getStudioRenderJob,
  cancelStudioRender,
  studioRenderFileUrl,
} from '../services/photosApi.js?v=8';
import { createStudioEditorView } from '../editor/StudioEditorView.js?v=2';

export class CommunityManagerStudioPage {
  constructor(router, publicationId, entryData = null, onBack = null) {
    this.router = router;
    this.publicationId = publicationId;
    this.entryData = entryData;
    this.onBack = onBack;
    this.element = null;
    this.publication = null;
    this.loading = true;
    this.saving = false;
    this.publishing = false;
    this.error = null;
    this.success = null;
    this.photoPickerOpen = false;
    this.suggestedPhotos = null;
    this.loadingPhotos = false;
    this.pendingPhotoIds = null;
    this.editorOpen = false;
    this.editorMounted = false;
    this.editorView = null;
    this.captionLength = 0;
    this.captionOverLimit = false;
    this.showShorten = false;
    this.previewOpen = false;
    this.previewHtml = '';
    this.previewLoading = false;
  }

  async initialize() {
    try {
      this.loading = true;
      const pub = await getStudioDraft(this.publicationId);
      this.publication = pub;
    } catch (error) {
      this.error = error?.data?.detail || error?.message || 'Impossible de charger le brouillon';
    } finally {
      this.loading = false;
    }
  }

  render() {
    if (!this.element) {
      this.element = document.createElement('div');
      this.element.className = 'cm-studio-container';
    }

    // L'éditeur graphique gère son propre rendu : ne pas réécrire le DOM.
    if (this.editorOpen && this.editorMounted) {
      return this.element;
    }

    const pub = this.publication;
    const calendarEntry = pub?.calendar_entry;
    const isSuggestion = calendarEntry?.source === 'suggestion'
      || calendarEntry?.content_type === 'story_souvenir'
      || calendarEntry?.content_type === 'story_edito';
    const isSportPublication = !isSuggestion && (
      pub?.source === 'garmin'
      || pub?.content_type === 'publication_sportive'
      || !!pub?.activity_id
      || !!calendarEntry?.source_activity_id
      || calendarEntry?.source === 'garmin'
      || calendarEntry?.content_type === 'publication_sportive'
    );
    this.isSportPublication = isSportPublication;
    const isShared = pub?.status === 'shared';
    const canPublish = pub && pub.status === 'validated' && pub.status !== 'shared' && pub.status !== 'refused' && pub.status !== 'failed' && pub.status !== 'publishing';
    const canValidate = pub && pub.status !== 'validated' && pub.status !== 'shared' && pub.status !== 'refused' && pub.status !== 'failed' && pub.status !== 'publishing';

    if (this.loading) {
      this.element.innerHTML = `<div class="cm-studio-loading">Chargement du contenu…</div>`;
      return this.element;
    }

    if (this.error) {
      this.element.innerHTML = `
        <div class="cm-studio-error">
          <p>${this._escape(this.error)}</p>
          <button class="btn btn-secondary" data-action="back">Retour</button>
        </div>`;
      return this.element;
    }

    const photoUrl = pub?.photo_id ? publicationPhotoUrl(pub.photo_id) : null;
    const title = pub?.title || '';
    const content = pub?.content || '';
    const hashtags = pub?.hashtags || '';
    // Nouveau format : titre + hashtags seulement (l'accroche est sur la photo)
    const fullCaption = [title, hashtags].filter(Boolean).join('\n\n');
    this.captionLength = fullCaption.length;
    this.captionOverLimit = this.captionLength > INSTAGRAM_CAPTION_MAX_LENGTH;
    const nearLimit = this.captionLength > INSTAGRAM_CAPTION_MAX_LENGTH * 0.9;

    this.element.innerHTML = `
      <div class="cm-studio-header">
        <h2>${isSuggestion ? 'Story suggérée' : 'Publication sportive'}</h2>
        <span class="cm-studio-badge ${this._escape(pub?.status || '')}">${this._escape(pub?.status || '')}</span>
      </div>

      <div class="cm-studio-body">
        <div class="cm-studio-photo">
          ${photoUrl ? `<img src="${photoUrl}" alt="Visuel" class="cm-studio-photo-img"/>` : '<div class="cm-studio-photo-empty">Aucune photo</div>'}
          ${pub?.error_message ? `<div class="cm-studio-warning">⚠ ${this._escape(pub.error_message)}</div>` : ''}
          ${pub?.photo_locked ? '<div class="cm-studio-warning">Photo verrouillée.</div>' : ''}
          ${isShared ? '' : `<div class="cm-studio-photo-actions">
            ${!isSportPublication ? `
            <button class="btn btn-primary btn-small" data-action="open-editor"
                    ${pub?.status === 'shared' ? 'disabled' : ''}>
              ✎ Éditeur graphique
            </button>` : ''}
            <button class="btn btn-secondary btn-small" data-action="toggle-photo-picker"
                    ${pub?.status === 'shared' || pub?.photo_locked ? 'disabled' : ''}>
              ${this.photoPickerOpen ? 'Fermer' : (photoUrl ? 'Changer la photo' : 'Choisir une photo')}
            </button>
            ${photoUrl && !pub?.photo_locked && pub?.status !== 'shared' ? `
              <button class="btn btn-secondary btn-small" data-action="remove-photo">Retirer la photo</button>` : ''}
            ${!isSportPublication ? `
              <button class="btn btn-secondary btn-small" data-action="regenerate" ${pub?.status === 'shared' ? 'disabled' : ''}>
                ${pub?.error_message ? 'Régénérer le contenu' : 'Régénérer le visuel'}
              </button>` : ''}
          </div>`}
          ${this._renderIgMusic(pub, isShared)}
          ${this.photoPickerOpen ? this._renderPhotoPicker() : ''}
        </div>

        <form data-form="studio-edit" class="cm-studio-form">
          <!-- Champs cachés pour l'API de sauvegarde -->
          <input type="hidden" name="title" value="${this._escape(title)}">
          <input type="hidden" name="content" value="${this._escape(content)}">
          <input type="hidden" name="hashtags" value="${this._escape(hashtags)}">

          <div class="form-group">
            <label>Légende Instagram complète</label>
            <textarea name="full_caption" rows="10" ${pub?.status === 'shared' ? 'disabled' : ''} placeholder="Titre (ligne 1), ligne vide, hashtags…">${this._escape(fullCaption)}</textarea>
            <div class="form-hint">Format : Titre sur la première ligne, ligne vide, hashtags sur la dernière ligne</div>
          </div>
          <div class="form-group cm-studio-counter ${this.captionOverLimit ? 'cm-studio-counter--over' : ''}">
            <span class="cm-studio-counter-current">${this.captionLength}</span>
            <span class="cm-studio-counter-separator"> / </span>
            <span class="cm-studio-counter-max">${INSTAGRAM_CAPTION_MAX_LENGTH}</span>
            <span class="cm-studio-counter-text">caractères</span>
            ${nearLimit && !this.captionOverLimit ? '<span class="cm-studio-counter-warning">⚠ Approche de la limite</span>' : ''}
            ${this.captionOverLimit ? '<span class="cm-studio-counter-error">⚠ Limite dépassée — publication bloquée</span>' : ''}
          </div>
        </form>

        ${isShared ? `
        <div class="cm-studio-actions">
          <button class="btn btn-secondary" data-action="back">Retour au calendrier</button>
        </div>` : `
        <div class="cm-studio-actions">
          <button class="btn btn-secondary" data-action="back">Annuler</button>
          <button class="btn btn-secondary" data-action="preview" ${this.previewLoading ? 'disabled' : ''}>
            ${this.previewLoading ? 'Chargement…' : 'Aperçu'}
          </button>
          <button class="btn btn-primary" data-action="save" ${pub?.status === 'shared' ? 'disabled' : ''}>
            ${this.saving ? 'Enregistrement…' : 'Enregistrer'}
          </button>
          ${canValidate ? `
            <button class="btn btn-primary" data-action="validate" ${this.publishing ? 'disabled' : ''}>
              ${this.publishing ? 'Validation en cours…' : 'Valider'}
            </button>
          ` : ''}
          ${isSuggestion && !canValidate && !canPublish ? `
            <button class="btn btn-secondary btn-small" data-action="refuse" ${pub?.status === 'shared' ? 'disabled' : ''}>
              ${this.publishing ? 'Refus…' : 'Refuser'}
            </button>
          ` : ''}
          ${canPublish && !this.captionOverLimit ? `
            <div class="cm-studio-publish-platform" style="display:flex;align-items:center;gap:8px;margin-right:16px;">
              <label style="font-size:12px;color:#666;">Publier sur :</label>
              <select id="cm-publish-platform" class="form-select form-select-sm" style="width:auto;min-width:160px;padding:4px 8px;" ${this.publishing ? 'disabled' : ''}>
                <option value="both">Instagram + Facebook</option>
                <option value="instagram">Instagram seulement</option>
                <option value="facebook">Facebook seulement</option>
              </select>
            </div>
            <button class="btn btn-success" data-action="publish" ${!canPublish || this.publishing ? 'disabled' : ''} style="min-width:100px;position:relative;z-index:10;">
              ${this.publishing ? 'Publication…' : 'Publier'}
            </button>
          ` : ''}
          ${this.captionOverLimit && this.showShorten ? `
            <button class="btn btn-secondary" data-action="shorten" ${this.publishing ? 'disabled' : ''}>
              Raccourcir automatiquement
            </button>
          ` : ''}
          ${this.captionOverLimit && !this.showShorten ? `
            <button class="btn btn-secondary" data-action="show-shorten">
              Raccourcir le texte
            </button>
          ` : ''}
        </div>`}
      </div>

      ${this.success ? `<div class="cm-studio-success">${this._escape(this.success)}</div>` : ''}

      ${this.previewOpen ? `
        <div class="cm-studio-preview-overlay" data-action="close-preview">
          <div class="cm-studio-preview-modal">
            <div class="cm-studio-preview-header">
              <span>Aperçu de la publication</span>
              <button class="btn btn-secondary btn-small" data-action="close-preview">Fermer</button>
            </div>
            <div class="cm-studio-preview-body">${this.previewHtml}</div>
          </div>
        </div>` : ''}
    `;

    this._bindEvents();
    if (this.editorOpen && !this.editorMounted) {
      this._mountEditor();
    }
    return this.element;
  }

  _escape(text) {
    return String(text ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  _renderIgMusic(pub, isShared = false) {
    const music = this.isSportPublication ? pub?.design?.ig_audio : null;
    if (!music?.audio_id) return '';
    const preview = typeof music.preview_link === 'string' && music.preview_link.startsWith('http')
      ? `<a class="cm-studio-ig-music-link" href="${this._escape(music.preview_link)}" target="_blank" rel="noopener">Écouter</a>`
      : '';
    const suggestions = isShared ? [] : (Array.isArray(music.suggestions) ? music.suggestions : []);
    const options = suggestions.length ? suggestions.map((item, index) => `
      <option value="${this._escape(item.audio_id)}" ${String(item.audio_id) === String(music.audio_id) ? 'selected' : ''}>
        ${index + 1}. ${this._escape(item.title || 'Musique')} — ${this._escape(item.artist || 'Artiste')}
      </option>`).join('') : '';
    return `
      <div class="cm-studio-ig-music" title="${this._escape(music.raison || '')}">
        <span class="cm-studio-ig-music-icon">♪</span>
        <span class="cm-studio-ig-music-title">${this._escape(music.title || '')}</span>
        ${music.artist ? `<span class="cm-studio-ig-music-artist">— ${this._escape(music.artist)}</span>` : ''}
        ${preview}
        ${options ? `<label class="cm-studio-ig-music-select-label">Suggestions IA
          <select data-action="select-ig-music" class="cm-studio-ig-music-select">${options}</select>
        </label>` : ''}
        ${isShared ? '' : '<span class="cm-studio-ig-music-hint">10 titres avec paroles privilégiés selon la photo et le titre de sortie</span>'}
      </div>`;
  }

  _currentPhotoSelection() {
    const design = this.publication?.design;
    const carousel = Array.isArray(design?.carousel) ? design.carousel : null;
    if (carousel && carousel.length) return [...carousel];
    return this.publication?.photo_id ? [this.publication.photo_id] : [];
  }

  _renderPhotoPicker() {
    if (this.loadingPhotos) {
      return '<div class="cm-studio-photo-picker"><div class="loading">Chargement des photos…</div></div>';
    }
    const photos = this.suggestedPhotos || [];
    if (!photos.length) {
      return '<div class="cm-studio-photo-picker"><div class="cm-studio-photo-empty">Aucune photo disponible dans votre bibliothèque.</div></div>';
    }
    if (this.pendingPhotoIds === null) {
      this.pendingPhotoIds = this._currentPhotoSelection();
    }
    const pending = this.pendingPhotoIds;
    const multi = this.isSportPublication;
    const thumbs = photos.map(p => {
      const date = p.taken_at ? new Date(p.taken_at).toLocaleDateString('fr-FR') : '';
      const selIdx = pending.indexOf(p.id);
      const orderBadge = multi && selIdx >= 0
        ? `<span class="cm-studio-photo-order">${selIdx + 1}</span>`
        : '';
      return `
        <button type="button" class="cm-studio-photo-thumb ${p.is_current ? 'cm-studio-photo-thumb--current' : ''} ${selIdx >= 0 ? 'cm-studio-photo-thumb--selected' : ''}"
                data-photo-id="${p.id}" title="${this._escape(p.title || '')}">
          <img src="${p.thumbnail_url}" alt="${this._escape(p.title || 'Photo')}" loading="lazy">
          ${orderBadge}
          <span class="cm-photo-badge cm-photo-badge--${this._escape(p.badge_class || 'info')}">${this._escape(p.match_reason || '')}</span>
          <span class="cm-studio-photo-meta">${date}</span>
        </button>`;
    }).join('');
    const applyRow = multi ? `
        <div class="cm-studio-photo-picker-actions">
          <span class="cm-studio-photo-picker-hint">
            ${pending.length ? `${pending.length} photo(s) sélectionnée(s) — 1re = couverture` : 'Cliquez pour composer le diaporama (1re = couverture)'}
          </span>
          <button type="button" class="btn btn-primary btn-small" data-action="apply-photo-selection" ${this.saving ? 'disabled' : ''}>
            Appliquer le diaporama
          </button>
        </div>` : '';
    return `
      <div class="cm-studio-photo-picker">
        <div class="cm-studio-photo-picker-title">Photos suggérées : même jour qu'une activité, jour de la publication, favorites</div>
        <div class="cm-studio-photo-grid">${thumbs}</div>
        ${applyRow}
      </div>`;
  }

  async _togglePhotoPicker() {
    this.photoPickerOpen = !this.photoPickerOpen;
    this.pendingPhotoIds = null;
    if (this.photoPickerOpen && this.suggestedPhotos === null) {
      this.loadingPhotos = true;
      this.render();
      try {
        this.suggestedPhotos = await getSuggestedPhotos(this.publicationId);
      } catch (error) {
        this.error = error?.data?.detail || error?.message || 'Erreur chargement des photos';
        this.photoPickerOpen = false;
      } finally {
        this.loadingPhotos = false;
      }
    }
    this.render();
  }

  async _togglePhotoSelection(photoId) {
    if (this.saving) return;
    const pending = this.pendingPhotoIds === null
      ? [...this._currentPhotoSelection()]
      : [...this.pendingPhotoIds];
    const idx = pending.indexOf(photoId);
    if (idx >= 0) {
      pending.splice(idx, 1);
    } else {
      pending.push(photoId);
    }
    this.pendingPhotoIds = pending;
    this.render();
  }

  async _applyPhotoSelection() {
    if (this.saving) return;
    this.saving = true;
    try {
      const ids = this.pendingPhotoIds === null ? this._currentPhotoSelection() : this.pendingPhotoIds;
      await updateStudioDraft(this.publicationId, { photo_ids: ids });
      const updated = await getStudioDraft(this.publicationId);
      this.publication = updated;
      this.photoPickerOpen = false;
      this.pendingPhotoIds = null;
      this.success = ids.length
        ? `Diaporama appliqué (${ids.length} photo${ids.length > 1 ? 's' : ''}).`
        : 'Sélection vidée.';
      setTimeout(() => { this.success = null; this.render(); }, 1500);
    } catch (error) {
      this.error = error?.data?.detail || error?.message || 'Erreur sélection photos';
    } finally {
      this.saving = false;
      this.render();
    }
  }

  async _selectPhoto(photoId) {
    if (this.saving) return;
    this.saving = true;
    try {
      await updateStudioDraft(this.publicationId, { photo_id: photoId });
      const updated = await getStudioDraft(this.publicationId);
      this.publication = updated;
      this.photoPickerOpen = false;
      this.success = 'Photo sélectionnée.';
      setTimeout(() => { this.success = null; this.render(); }, 1500);
    } catch (error) {
      this.error = error?.data?.detail || error?.message || 'Erreur sélection photo';
    } finally {
      this.saving = false;
      this.render();
    }
  }

  async _removePhoto() {
    if (this.saving) return;
    this.saving = true;
    try {
      await updateStudioDraft(this.publicationId, { photo_id: null });
      const updated = await getStudioDraft(this.publicationId);
      this.publication = updated;
      this.success = 'Photo retirée.';
      setTimeout(() => { this.success = null; this.render(); }, 1500);
    } catch (error) {
      this.error = error?.data?.detail || error?.message || 'Erreur retrait photo';
    } finally {
      this.saving = false;
      this.render();
    }
  }

  /** Libère les ressources de l'éditeur (timeline, canvas, mix, timers). */
  destroy() {
    this.editorOpen = false;
    this.editorMounted = false;
    if (this.editorView) {
      this.editorView.destroy();
      this.editorView = null;
    }
  }

  /** Monte l'éditeur graphique plein écran dans la page studio. */
  _mountEditor() {
    const host = document.createElement('div');
    host.className = 'cm-studio-editor-host';
    this.element.innerHTML = '';
    this.element.appendChild(host);

    this.editorView = createStudioEditorView({
      publication: this.publication,
      deps: {
        updateDraft: (id, data) => updateStudioDraft(id, data),
        uploadPhotos,
        getSuggestedPhotos,
        listPhotos,
        photoFileUrl,
        publicationPhotoUrl,
        publicationId: this.publicationId,
        createRender: (publicationId) => createStudioRender(publicationId),
        getRenderJob: (jobId) => getStudioRenderJob(jobId),
        cancelRender: (jobId) => cancelStudioRender(jobId),
        renderFileUrl: (jobId) => studioRenderFileUrl(jobId, true),
      },
      callbacks: {
        onClose: () => this._closeEditor(),
        onApplied: async () => {
          try {
            this.publication = await getStudioDraft(this.publicationId);
          } catch (_err) {
            /* le design appliqué reste affiché */
          }
        },
      },
    });
    this.editorView.mount(host);
    this.editorMounted = true;
  }

  async _closeEditor() {
    this.destroy();
    try {
      this.publication = await getStudioDraft(this.publicationId);
    } catch (_err) {
      /* on garde la publication en mémoire */
    }
    this.render();
  }

  async _saveForm() {
    if (this.saving) return;
    this.saving = true;
    try {
      const form = this.element.querySelector('[data-form="studio-edit"]');
      const data = {
        title: form.elements.title.value,
        content: form.elements.content.value,
        hashtags: form.elements.hashtags.value,
      };
      await updateStudioDraft(this.publicationId, data);
      const updated = await getStudioDraft(this.publicationId);
      this.publication = updated;
      this.success = 'Modifications enregistrées.';
      setTimeout(() => { this.success = null; this.render(); }, 1500);
    } catch (error) {
      this.error = error?.data?.detail || error?.message || 'Erreur enregistrement';
    } finally {
      this.saving = false;
      this.render();
    }
  }

  async _refuseSuggestion() {
    if (this.publishing) return;
    const entryId = this.publication?.calendar_entry_id;
    if (!entryId) {
      this.error = 'Impossible de refuser : entrée de calendrier introuvable.';
      this.render();
      return;
    }
    this.publishing = true;
    this.error = null;
    try {
      await refuseSuggestion(entryId);
      const updated = await getStudioDraft(this.publicationId);
      this.publication = updated;
      this.success = 'Suggestion refusée.';
      setTimeout(() => { this.success = null; if (this.onBack) this.onBack(); else this.render(); }, 1500);
    } catch (error) {
      this.error = error?.data?.detail || error?.message || 'Erreur refus';
    } finally {
      this.publishing = false;
      this.render();
    }
  }

  async _openPreview() {
    if (this.previewLoading) return;
    this.previewLoading = true;
    this.error = null;
    this.render();
    try {
      // Sauvegarder le contenu actuel avant l'aperçu pour refléter les modifications en cours
      const form = this.element.querySelector('[data-form="studio-edit"]');
      if (form) {
        const data = {
          title: form.elements.title.value,
          content: form.elements.content.value,
          hashtags: form.elements.hashtags.value,
        };
        await updateStudioDraft(this.publicationId, data);
        this.publication = await getStudioDraft(this.publicationId);
      }
      const res = await previewStudioDraft(this.publicationId, 'feed');
      const html = typeof res === 'string'
        ? res
        : (res?.preview_html ?? res?.previewHtml ?? res?.html ?? '');
      this.previewHtml = typeof html === 'string' ? html : '';
      this.previewOpen = true;
    } catch (error) {
      this.error = error?.data?.detail || error?.message || 'Erreur lors de la génération de l’aperçu';
    } finally {
      this.previewLoading = false;
      this.render();
    }
  }

  _closePreview() {
    this.previewOpen = false;
    this.render();
  }

  _bindEvents() {
    // « Annuler » (et « Retour » sur l'écran d'erreur) : abandonne les
    // modifications non enregistrées et quitte le Studio.
    this.element.querySelectorAll('[data-action="back"]').forEach(backBtn => {
      backBtn.addEventListener('click', () => { if (this.onBack) this.onBack(); });
    });

    const openEditorBtn = this.element.querySelector('[data-action="open-editor"]');
    if (openEditorBtn) {
      openEditorBtn.addEventListener('click', () => {
        this.editorOpen = true;
        this.render();
      });
    }

    const togglePhotoBtn = this.element.querySelector('[data-action="toggle-photo-picker"]');
    if (togglePhotoBtn) togglePhotoBtn.addEventListener('click', () => this._togglePhotoPicker());

    const removePhotoBtn = this.element.querySelector('[data-action="remove-photo"]');
    if (removePhotoBtn) removePhotoBtn.addEventListener('click', () => this._removePhoto());

    const musicSelect = this.element.querySelector('[data-action="select-ig-music"]');
    if (musicSelect) musicSelect.addEventListener('change', async (event) => {
      const current = this.publication?.design?.ig_audio;
      const selected = current?.suggestions?.find((item) => String(item.audio_id) === String(event.target.value));
      if (!selected) return;
      try {
        this.saving = true;
        const igAudio = { ...current, ...selected, status: 'selected', raison: current.raison || 'Sélection IA selon la photo et le titre' };
        this.publication = await updateStudioDraft(this.publicationId, { design: { ig_audio: igAudio } });
        this.success = 'Musique sélectionnée.';
      } catch (error) {
        this.error = error?.data?.detail || error?.message || 'Impossible de sélectionner la musique';
      } finally {
        this.saving = false;
        this.render();
      }
    });

    this.element.querySelectorAll('[data-photo-id]').forEach(thumb => {
      thumb.addEventListener('click', () => {
        const id = parseInt(thumb.dataset.photoId, 10);
        if (this.isSportPublication) {
          this._togglePhotoSelection(id);
        } else {
          this._selectPhoto(id);
        }
      });
    });

    const applySelectionBtn = this.element.querySelector('[data-action="apply-photo-selection"]');
    if (applySelectionBtn) applySelectionBtn.addEventListener('click', () => this._applyPhotoSelection());

    const saveBtn = this.element.querySelector('[data-action="save"]');
    if (saveBtn) {
      saveBtn.addEventListener('click', () => this._saveForm());
    }

    // Compteur de caractères en temps réel (légende complète)
    const form = this.element.querySelector('[data-form="studio-edit"]');
    if (form) {
      const fullCaptionInput = form.elements.full_caption;
      const titleInput = form.elements.title;
      const contentInput = form.elements.content;
      const hashtagsInput = form.elements.hashtags;

      const parseFullCaption = (full) => {
        const parts = full.split('\n\n').map(p => p.trim()).filter(Boolean);
        let title = '';
        let hashtags = '';
        if (parts.length === 1) {
          // Only title or only hashtags
          if (parts[0].startsWith('#')) {
            hashtags = parts[0];
          } else {
            title = parts[0];
          }
        } else if (parts.length >= 2) {
          title = parts[0];
          hashtags = parts[parts.length - 1];
        }
        return { title, hashtags };
      };

      const updateHiddenFields = (full) => {
        const { title, hashtags } = parseFullCaption(full);
        if (titleInput) titleInput.value = title;
        if (hashtagsInput) hashtagsInput.value = hashtags;
      };

      const updateCounter = () => {
        const full = fullCaptionInput ? fullCaptionInput.value : '';
        updateHiddenFields(full);
        const newLen = full.length;
        const newOver = newLen > INSTAGRAM_CAPTION_MAX_LENGTH;
        const nearLimit = newLen > INSTAGRAM_CAPTION_MAX_LENGTH * 0.9;
        const prevNear = this.captionLength > INSTAGRAM_CAPTION_MAX_LENGTH * 0.9;

        const needsRender = (newOver !== this.captionOverLimit) || (nearLimit !== prevNear);
        this.captionLength = newLen;
        this.captionOverLimit = newOver;

        if (needsRender) {
          const active = document.activeElement;
          const activeName = active && active.name;
          const selStart = active ? active.selectionStart : null;
          const selEnd = active ? active.selectionEnd : null;
          this.render();
          if (activeName) {
            const f = this.element.querySelector('[data-form="studio-edit"]');
            const el = f && f.elements[activeName];
            if (el && typeof el.focus === 'function') {
              el.focus();
              if (selStart != null && selEnd != null && typeof el.setSelectionRange === 'function') {
                try { el.setSelectionRange(selStart, selEnd); } catch {}
              }
            }
          }
          return;
        }

        // Mise à jour légère sans re-render (préserve le focus pendant la saisie)
        const counterCurrent = this.element.querySelector('.cm-studio-counter-current');
        if (counterCurrent) counterCurrent.textContent = String(newLen);
        const counterWrap = this.element.querySelector('.cm-studio-counter');
        if (counterWrap) counterWrap.classList.toggle('cm-studio-counter--over', newOver);
      };
      if (fullCaptionInput) fullCaptionInput.addEventListener('input', updateCounter);
    }

    const regenerateBtn = this.element.querySelector('[data-action="regenerate"]');
    if (regenerateBtn) {
      regenerateBtn.addEventListener('click', async () => {
        try {
          const res = await regeneratePublicationContent(this.publicationId);
          this.success = res.error_message ? `Génération terminée avec avertissement : ${res.error_message}` : 'Contenu régénéré.';
          const updated = await getStudioDraft(this.publicationId);
          this.publication = updated;
          this.render();
        } catch (error) {
          this.error = error?.data?.detail || error?.message || 'Erreur régénération';
          this.render();
        }
      });
    }

const publishBtn = this.element.querySelector('[data-action="publish"]');
      if (publishBtn) {
        publishBtn.addEventListener('click', async () => {
          if (this.publishing) return;
          const platformSelect = this.element.querySelector('#cm-publish-platform');
          const platform = platformSelect ? platformSelect.value : 'both';
          this.publishing = true;
          try {
            let publishFn;
            switch (platform) {
              case 'facebook':
                publishFn = publishStudioDraftFacebook;
                break;
              case 'both':
                publishFn = publishStudioDraftBoth;
                break;
              case 'instagram':
              default:
                publishFn = publishStudioDraft;
                break;
            }
            await publishFn(this.publicationId, { confirm: true });
            const updated = await getStudioDraft(this.publicationId);
            this.publication = updated;
            const platformLabels = { instagram: 'Instagram', facebook: 'Facebook', both: 'Instagram + Facebook' };
            this.success = `Publication envoyée sur ${platformLabels[platform]}.`;
            setTimeout(() => { this.success = null; this.render(); }, 1500);
          } catch (error) {
            this.error = error?.data?.detail || error?.message || 'Erreur publication';
          } finally {
            this.publishing = false;
            this.render();
          }
        });
      }

    const validateBtn = this.element.querySelector('[data-action="validate"]');
    if (validateBtn) {
      validateBtn.addEventListener('click', async () => {
        if (this.publishing) return;
        this.publishing = true;
        this.error = null;
        try {
          await validateStudioDraft(this.publicationId, { confirm: true });
          const updated = await getStudioDraft(this.publicationId);
          this.publication = updated;
          this.success = 'Publication validée.';
          setTimeout(() => { this.success = null; this.render(); }, 1500);
        } catch (error) {
          this.error = error?.data?.detail || error?.message || 'Erreur validation';
        } finally {
          this.publishing = false;
          this.render();
        }
      });
    }

    const refuseBtn = this.element.querySelector('[data-action="refuse"]');
    if (refuseBtn) {
      refuseBtn.addEventListener('click', () => this._refuseSuggestion());
    }

    const previewBtn = this.element.querySelector('[data-action="preview"]');
    if (previewBtn) previewBtn.addEventListener('click', () => this._openPreview());

    this.element.querySelectorAll('[data-action="close-preview"]').forEach(el => {
      el.addEventListener('click', (e) => {
        if (e.currentTarget !== e.target && !e.currentTarget.classList.contains('btn')) return;
        this._closePreview();
      });
    });

    const showShortenBtn = this.element.querySelector('[data-action="show-shorten"]');
    if (showShortenBtn) {
      showShortenBtn.addEventListener('click', () => {
        this.showShorten = true;
        this.render();
      });
    }

    const shortenBtn = this.element.querySelector('[data-action="shorten"]');
    if (shortenBtn) {
      shortenBtn.addEventListener('click', async () => {
        if (this.publishing) return;
        this.publishing = true;
        this.error = null;
        try {
          const form = this.element.querySelector('[data-form="studio-edit"]');
          const title = form.elements.title.value;
          const hashtags = form.elements.hashtags.value;
          const fullCaption = title + (hashtags ? '\n\n' + hashtags : '');
          if (fullCaption.length <= INSTAGRAM_CAPTION_MAX_LENGTH) {
            this.showShorten = false;
            this.render();
            return;
          }
          // Raccourcir : couper les hashtags si besoin (titre non modifié)
          let newHashtags = hashtags;
          const maxHashtags = Math.max(0, INSTAGRAM_CAPTION_MAX_LENGTH - title.length - 2);
          if (hashtags && maxHashtags > 0) {
            newHashtags = hashtags.slice(0, maxHashtags).trim();
          }
          await updateStudioDraft(this.publicationId, { hashtags: newHashtags });
          const updated = await getStudioDraft(this.publicationId);
          this.publication = updated;
          this.showShorten = false;
          this.success = 'Hashtags raccourcis.';
          setTimeout(() => { this.success = null; this.render(); }, 1500);
        } catch (error) {
          this.error = error?.data?.detail || error?.message || 'Erreur raccourcissement';
        } finally {
          this.publishing = false;
          this.render();
        }
      });
    }
  }
}

export function createCommunityManagerStudioPage(router, publicationId, entryData = null, onBack = null) {
  return new CommunityManagerStudioPage(router, publicationId, entryData, onBack);
}
