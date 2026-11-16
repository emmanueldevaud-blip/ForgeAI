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
    const fullCaption = content + (hashtags ? '\n\n' + hashtags : '');
    this.captionLength = fullCaption.length;
    this.captionOverLimit = this.captionLength > INSTAGRAM_CAPTION_MAX_LENGTH;
    const remaining = INSTAGRAM_CAPTION_MAX_LENGTH - this.captionLength;
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
          <div class="cm-studio-photo-actions">
            <button class="btn btn-primary btn-small" data-action="open-editor"
                    ${pub?.status === 'shared' ? 'disabled' : ''}>
              ✎ Éditeur graphique
            </button>
            <button class="btn btn-secondary btn-small" data-action="toggle-photo-picker"
                    ${pub?.status === 'shared' || pub?.photo_locked ? 'disabled' : ''}>
              ${this.photoPickerOpen ? 'Fermer' : (photoUrl ? 'Changer la photo' : 'Choisir une photo')}
            </button>
            ${photoUrl && !pub?.photo_locked && pub?.status !== 'shared' ? `
              <button class="btn btn-secondary btn-small" data-action="remove-photo">Retirer la photo</button>` : ''}
            <button class="btn btn-secondary btn-small" data-action="regenerate" ${pub?.status === 'shared' ? 'disabled' : ''}>
              ${pub?.error_message ? 'Régénérer le contenu' : 'Régénérer le visuel'}
            </button>
          </div>
          ${this.photoPickerOpen ? this._renderPhotoPicker() : ''}
        </div>

        <form data-form="studio-edit" class="cm-studio-form">
          <div class="form-group">
            <label>Titre</label>
            <input name="title" type="text" value="${this._escape(title)}" ${pub?.status === 'shared' ? 'disabled' : ''} placeholder="Titre de la publication">
          </div>
          <div class="form-group">
            <label>Texte d'accroche</label>
            <textarea name="content" rows="6" ${pub?.status === 'shared' ? 'disabled' : ''} placeholder="Votre texte…">${this._escape(content)}</textarea>
          </div>
          <div class="form-group">
            <label>Hashtags</label>
            <input name="hashtags" type="text" value="${this._escape(hashtags)}" ${pub?.status === 'shared' ? 'disabled' : ''} placeholder="#trail #running">
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
            <button class="btn btn-success" data-action="publish" ${!canPublish || this.publishing ? 'disabled' : ''}>
              ${this.publishing ? 'Publication…' : 'Publier sur Instagram'}
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
        </div>
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

  _renderPhotoPicker() {
    if (this.loadingPhotos) {
      return '<div class="cm-studio-photo-picker"><div class="loading">Chargement des photos…</div></div>';
    }
    const photos = this.suggestedPhotos || [];
    if (!photos.length) {
      return '<div class="cm-studio-photo-picker"><div class="cm-studio-photo-empty">Aucune photo disponible dans votre bibliothèque.</div></div>';
    }
    const thumbs = photos.map(p => {
      const date = p.taken_at ? new Date(p.taken_at).toLocaleDateString('fr-FR') : '';
      return `
        <button type="button" class="cm-studio-photo-thumb ${p.is_current ? 'cm-studio-photo-thumb--current' : ''}"
                data-photo-id="${p.id}" title="${this._escape(p.title || '')}">
          <img src="${p.thumbnail_url}" alt="${this._escape(p.title || 'Photo')}" loading="lazy">
          <span class="cm-photo-badge cm-photo-badge--${this._escape(p.badge_class || 'info')}">${this._escape(p.match_reason || '')}</span>
          <span class="cm-studio-photo-meta">${date}</span>
        </button>`;
    }).join('');
    return `
      <div class="cm-studio-photo-picker">
        <div class="cm-studio-photo-picker-title">Photos suggérées : même jour qu'une activité, jour de la publication, favorites</div>
        <div class="cm-studio-photo-grid">${thumbs}</div>
      </div>`;
  }

  async _togglePhotoPicker() {
    this.photoPickerOpen = !this.photoPickerOpen;
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

    this.element.querySelectorAll('[data-photo-id]').forEach(thumb => {
      thumb.addEventListener('click', () => this._selectPhoto(parseInt(thumb.dataset.photoId, 10)));
    });

    const saveBtn = this.element.querySelector('[data-action="save"]');
    if (saveBtn) {
      saveBtn.addEventListener('click', () => this._saveForm());
    }

    // Compteur de caractères en temps réel (contenu + hashtags)
    const form = this.element.querySelector('[data-form="studio-edit"]');
    if (form) {
      const contentInput = form.elements.content;
      const hashtagsInput = form.elements.hashtags;
      const updateCounter = () => {
        const c = contentInput ? contentInput.value : '';
        const h = hashtagsInput ? hashtagsInput.value : '';
        const full = c + (h ? '\n\n' + h : '');
        this.captionLength = full.length;
        this.captionOverLimit = this.captionLength > INSTAGRAM_CAPTION_MAX_LENGTH;
        this.render();
      };
      if (contentInput) contentInput.addEventListener('input', updateCounter);
      if (hashtagsInput) hashtagsInput.addEventListener('input', updateCounter);
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
        this.publishing = true;
        try {
          await publishStudioDraft(this.publicationId, { confirm: true });
          const updated = await getStudioDraft(this.publicationId);
          this.publication = updated;
          this.success = 'Publication envoyée sur Instagram.';
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
          const content = form.elements.content.value;
          const hashtags = form.elements.hashtags.value;
          const fullCaption = content + (hashtags ? '\n\n' + hashtags : '');
          if (fullCaption.length <= INSTAGRAM_CAPTION_MAX_LENGTH) {
            this.showShorten = false;
            this.render();
            return;
          }
          // Raccourcir : garder l'accroche, couper les hashtags si besoin, puis couper le texte
          const maxHashtags = hashtags ? Math.max(0, INSTAGRAM_CAPTION_MAX_LENGTH - content.length - 3) : 0;
          let newHashtags = hashtags;
          if (hashtags && maxHashtags > 0) {
            newHashtags = hashtags.slice(0, maxHashtags).trim();
          }
          let newContent = content;
          const remaining = INSTAGRAM_CAPTION_MAX_LENGTH - (newHashtags ? 2 + newHashtags.length : 0);
          if (newContent.length > remaining) {
            newContent = newContent.slice(0, remaining - 3).trim() + '…';
          }
          await updateStudioDraft(this.publicationId, { content: newContent, hashtags: newHashtags });
          const updated = await getStudioDraft(this.publicationId);
          this.publication = updated;
          this.showShorten = false;
          this.success = 'Texte raccourci.';
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
