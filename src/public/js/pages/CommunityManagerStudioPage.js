/**
 * CommunityManagerStudioPage — Studio d'édition d'une publication existante
 * (Story suggérée ou publication sportive / V1) ouverte depuis le calendrier
 * du Community Manager.
 *
 * Deux vues selon la nature de la publication :
 *  - story suggérée (calendar_entry.source === 'suggestion') : refuser / valider la story
 *  - publication sportive (legacy sans entrée calendrier, ou source Garmin) : éditer + publier
 *
 * Pas de chrome propre : la page parente (CommunityManagerPage) pilote le retour.
 */

import {
  getStudioDraft,
  updateStudioDraft,
  publishStudioDraft,
  refuseSuggestion,
  getSuggestedPhotos,
  publicationPhotoUrl,
} from '../services/sportApi.js?v=16';

export class CommunityManagerStudioPage {
  constructor(router, publicationId, options = {}, onBack = null) {
    this.router = router;
    this.publicationId = publicationId;
    this.options = options || {};
    this.onBack = onBack || null;
    this.element = null;
    this.publication = null;
    this.loading = false;
    this.error = null;
    this.success = null;
    this.photoPickerOpen = false;
    this.suggestedPhotos = [];
    this.selectedPhotoIds = new Set();
  }

  get isSportPublication() {
    const p = this.publication || {};
    return p.source === 'garmin';
  }

  get captionValue() {
    const p = this.publication || {};
    const parts = [];
    if (p.title) parts.push(p.title);
    if (p.hashtags) parts.push(p.hashtags);
    return parts.join('\n\n');
  }

  get captionLength() {
    return this.captionValue.length;
  }

  async initialize() {
    try {
      this.loading = true;
      this.error = null;
      this.success = null;
      const pub = await getStudioDraft(this.publicationId);
      this.publication = pub;
    } catch (error) {
      this.error = error?.data?.detail || error?.message || 'Chargement impossible.';
    } finally {
      this.loading = false;
    }
  }

  render() {
    if (!this.element) {
      this.element = document.createElement('div');
      this.element.className = 'cm-studio';
    }
    const p = this.publication || {};
    const story = p.calendar_entry?.source === 'suggestion';
    const legacy = !p.calendar_entry_id;
    const multi = !!p.photo_id;
    const pickerClass = multi ? 'cm-studio-photo-picker' : 'cm-studio-photo-grid';
    this.element.innerHTML = this._renderShell(p, story, legacy, pickerClass);
    this._bindEvents();
    return this.element;
  }

  _renderShell(p, story, legacy, pickerClass) {
    const caption = this.captionValue;
    const photoUrl = (id) => (publicationPhotoUrl ? publicationPhotoUrl(id) : `/photos/${id}/file?size=medium`);

    const storyView = story ? `
      <header class="cm-studio-header">
        <button type="button" class="cm-btn cm-btn-back" data-action="back">Annuler</button>
        <h1 class="cm-studio-title">Story suggérée</h1>
      </header>
      <form data-form="studio-edit">
        <div class="cm-studio-field">
          <label>Légende</label>
          <textarea name="content" class="cm-studio-caption">${this._esc(caption)}</textarea>
        </div>
      </form>
      <div class="cm-studio-actions cm-studio-actions--story">
        <button type="button" class="cm-btn cm-btn-danger" data-action="refuse">Refuser</button>
        <button type="button" class="cm-btn cm-btn-primary" data-action="validate-story">Valider la story</button>
      </div>
    ` : `
      <header class="cm-studio-header">
        <button type="button" class="cm-btn cm-btn-back" data-action="back">Annuler</button>
        <h1 class="cm-studio-title">${legacy ? 'Publication sportive' : 'Publication'}</h1>
      </header>
      <form data-form="studio-edit">
        <div class="cm-studio-field">
          <label>Légende</label>
          <textarea name="content" class="cm-studio-caption">${this._esc(caption)}</textarea>
        </div>
      </form>
      <div class="cm-studio-actions cm-studio-actions--sport">
        <button type="button" class="cm-btn cm-btn-primary" data-action="publish">Publier</button>
      </div>
    `;

    const picker = this.photoPickerOpen ? `
      <div class="cm-studio-photo-panel ${pickerClass}">
        <div class="cm-studio-photo-grid">
          ${(this.suggestedPhotos || []).map((photo, idx) => {
            const id = String(photo.id);
            const selected = this.selectedPhotoIds.has(id);
            const badgeClass = photo.badge_class ? `cm-photo-badge--${photo.badge_class}` : '';
            return `
              <button type="button" class="cm-studio-photo-thumb ${selected ? 'cm-studio-photo-thumb--selected' : ''}" data-photo-id="${id}">
                <img src="${photo.thumbnail_url || photoUrl(photo.id)}" alt="${this._esc(photo.title || '')}" loading="lazy">
                ${badgeClass ? `<span class="cm-photo-badge ${badgeClass}">${this._esc(photo.badge_class)}</span>` : ''}
                ${(this.selectedPhotoIds.size > 0) ? `<span class="cm-studio-photo-order">${idx + 1}</span>` : ''}
              </button>
            `;
          }).join('')}
        </div>
      </div>
    ` : '';

    return `
      <div class="cm-studio-root">
        ${storyView}
        ${picker}
        ${this.error ? `<div class="cm-studio-alert cm-studio-alert--error">${this._esc(this.error)}</div>` : ''}
        ${this.success ? `<div class="cm-studio-alert cm-studio-alert--success">${this._esc(this.success)}</div>` : ''}
      </div>
    `;
  }

  _bindEvents() {
    const el = this.element;
    if (!el) return;

    const backBtns = el.querySelectorAll?.('[data-action="back"]') || [];
    backBtns.forEach((btn) => {
      btn.addEventListener('click', () => this.onBack?.());
    });

    const refuseBtn = el.querySelector?.('[data-action="refuse"]');
    if (refuseBtn) refuseBtn.addEventListener('click', () => this._refuseSuggestion());

    const validateBtn = el.querySelector?.('[data-action="validate-story"]');
    if (validateBtn) validateBtn.addEventListener('click', () => this._validateStory());

    const publishBtn = el.querySelector?.('[data-action="publish"]');
    if (publishBtn) publishBtn.addEventListener('click', () => this._publish());

    const saveBtn = el.querySelector?.('[data-action="save-form"]');
    if (saveBtn) saveBtn.addEventListener('click', () => this._saveForm());

    el.querySelectorAll?.('[data-photo-id]').forEach((btn) => {
      btn.addEventListener('click', () => this._togglePhotoSelection(btn.dataset.photoId));
    });
  }

  async _refuseSuggestion() {
    const entry = this.publication?.calendar_entry;
    const entryId = entry?.id ?? this.publication?.calendar_entry_id;
    if (!entryId) {
      this.error = 'Aucune entrée de calendrier liée à ce brouillon.';
      this.success = null;
      return;
    }
    this.error = null;
    try {
      await refuseSuggestion(entryId);
      this.success = 'Suggestion refusée.';
      await getStudioDraft(this.publicationId).then((pub) => { this.publication = pub; });
    } catch (error) {
      this.error = error?.data?.detail || error?.message || 'Refus impossible.';
      this.success = null;
    }
  }

  async _validateStory() {
    const entry = this.publication?.calendar_entry;
    const entryId = entry?.id ?? this.publication?.calendar_entry_id;
    if (!entryId) {
      this.error = 'Aucune entrée de calendrier liée à ce brouillon.';
      return;
    }
    try {
      await updateStudioDraft(this.publicationId, { status: 'awaiting_validation' });
      this.success = 'Story validée.';
    } catch (error) {
      this.error = error?.data?.detail || error?.message || 'Validation impossible.';
    }
  }

  async _publish() {
    try {
      this.error = null;
      await publishStudioDraft?.(this.publicationId, { confirm: true });
      this.success = 'Publié avec succès.';
    } catch (error) {
      this.error = error?.data?.detail || error?.message || 'Publication impossible.';
    }
  }

  async _saveForm() {
    const form = this.element?.querySelector?.('[data-form="studio-edit"]');
    const values = { title: '', content: '', hashtags: '' };
    if (form && form.elements) {
      values.title = form.elements.title?.value ?? '';
      values.content = form.elements.content?.value ?? '';
      values.hashtags = form.elements.hashtags?.value ?? '';
    }
    await updateStudioDraft(this.publicationId, values);
    this.success = 'Modifications enregistrées.';
    this.error = null;
  }

  async _togglePhotoPicker() {
    this.photoPickerOpen = true;
    this.error = null;
    try {
      const res = await getSuggestedPhotos(null, 20);
      this.suggestedPhotos = Array.isArray(res) ? res : (res?.items || []);
    } catch (error) {
      this.suggestedPhotos = [];
      this.error = error?.data?.detail || error?.message || 'Photos indisponibles.';
    }
  }

  _togglePhotoSelection(photoId) {
    const id = String(photoId);
    if (this.selectedPhotoIds.has(id)) this.selectedPhotoIds.delete(id);
    else this.selectedPhotoIds.add(id);
  }

  async _applyPhotoSelection() {
    const p = this.publication || {};
    const ids = [];
    if (p.photo_id != null) ids.push(Number(p.photo_id));
    for (const id of this.selectedPhotoIds) {
      const n = Number(id);
      if (!ids.includes(n)) ids.push(n);
    }
    await updateStudioDraft(this.publicationId, { photo_ids: ids });
    this.success = 'Sélection appliquée.';
    this.error = null;
  }

  async _removePhoto() {
    await updateStudioDraft(this.publicationId, { photo_id: null });
    this.success = 'Photo retirée.';
    this.error = null;
  }

  async _selectPhoto(photoId) {
    this.selectedPhotoIds = new Set([String(photoId)]);
    await updateStudioDraft(this.publicationId, { photo_id: Number(photoId) });
    this.success = 'Photo sélectionnée.';
    this.error = null;
  }

  _esc(text) {
    return String(text ?? '').replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
  }

  destroy() {
    if (this.element && this.element.parentNode) this.element.parentNode.removeChild(this.element);
    this.element = null;
  }
}

export function createCommunityManagerStudioPage(router, publicationId, options, onBack) {
  return new CommunityManagerStudioPage(router, publicationId, options, onBack);
}
