/**
 * Community Manager Studio Page - Refonte minimaliste
 * Vérifier, modifier et publier les contenus préparés.
 * Seul le strict nécessaire : photo, titre, texte, hashtags.
 */
import {
  getStudioDraft,
  updateStudioDraft,
  validateStudioDraft,
  publishStudioDraft,
  regeneratePublicationContent,
  getSuggestedPhotos,
  refuseSuggestion,
} from '../services/sportApi.js?v=14';
import { publicationPhotoUrl } from '../services/sportApi.js?v=14';

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

    const pub = this.publication;
    const calendarEntry = pub?.calendar_entry;
    const isSuggestion = calendarEntry?.source === 'suggestion'
      || calendarEntry?.content_type === 'story_souvenir'
      || calendarEntry?.content_type === 'story_edito';
    const canPublish = pub && pub.status === 'validated' && !isSuggestion;

    if (this.loading) {
      this.element.innerHTML = `<div class="cm-studio-loading">Chargement du contenu…</div>`;
      return this.element;
    }

    if (this.error) {
      this.element.innerHTML = `
        <div class="cm-studio-error">
          <p>${this.error}</p>
          <button class="btn btn-secondary" data-action="back">Retour</button>
        </div>`;
      return this.element;
    }

    const photoUrl = pub?.photo_id ? publicationPhotoUrl(pub.photo_id) : null;
    const title = pub?.title || '';
    const content = pub?.content || '';
    const hashtags = pub?.hashtags || '';

    this.element.innerHTML = `
      <div class="cm-studio-header">
        <button class="btn btn-secondary" data-action="back">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>
          Retour
        </button>
        <h2>${isSuggestion ? 'Story suggérée' : 'Publication sportive'}</h2>
        <span class="cm-studio-badge ${pub?.status}">${pub?.status}</span>
      </div>

      <div class="cm-studio-body">
        <div class="cm-studio-photo">
          ${photoUrl ? `<img src="${photoUrl}" alt="Visuel" class="cm-studio-photo-img"/>` : '<div class="cm-studio-photo-empty">Aucune photo</div>'}
          ${pub?.error_message ? `<div class="cm-studio-warning">⚠ ${pub.error_message}</div>` : ''}
          ${pub?.photo_locked ? '<div class="cm-studio-warning">Photo verrouillée.</div>' : ''}
          <div class="cm-studio-photo-actions">
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
        </form>

        <div class="cm-studio-actions">
          <button class="btn btn-secondary" data-action="back">Annuler</button>
          <button class="btn btn-primary" data-action="save" ${pub?.status === 'shared' ? 'disabled' : ''}>
            ${this.saving ? 'Enregistrement…' : 'Enregistrer'}
          </button>
          ${isSuggestion ? `
            <button class="btn btn-secondary btn-small" data-action="refuse" ${pub?.status === 'shared' ? 'disabled' : ''}>
              ${this.publishing ? 'Refus…' : 'Refuser'}
            </button>
            <button class="btn btn-primary" data-action="validate" ${pub?.status === 'shared' || pub?.status === 'refused' ? 'disabled' : ''}>
              ${this.publishing ? 'Validation…' : 'Valider la story'}
            </button>
          ` : `
            <button class="btn btn-success" data-action="publish" ${!canPublish || this.publishing ? 'disabled' : ''}>
              ${this.publishing ? 'Publication…' : 'Publier sur Instagram'}
            </button>
          `}
        </div>
      </div>

      ${this.success ? `<div class="cm-studio-success">${this.success}</div>` : ''}
    `;

    this._bindEvents();
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

  _bindEvents() {
    this.element.querySelectorAll('[data-action="back"]').forEach(backBtn => {
      backBtn.addEventListener('click', () => { if (this.onBack) this.onBack(); });
    });

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
        try {
          await validateStudioDraft(this.publicationId, { confirm: true });
          const updated = await getStudioDraft(this.publicationId);
          this.publication = updated;
          this.success = 'Story validée.';
          setTimeout(() => { this.success = null; this.render(); }, 1500);
        } catch (error) {
          this.error = error?.data?.detail || error?.message || 'Erreur validation';
          this.render();
        }
      });
    }

    const refuseBtn = this.element.querySelector('[data-action="refuse"]');
    if (refuseBtn) {
      refuseBtn.addEventListener('click', () => this._refuseSuggestion());
    }
  }
}

export function createCommunityManagerStudioPage(router, publicationId, entryData = null, onBack = null) {
  return new CommunityManagerStudioPage(router, publicationId, entryData, onBack);
}
