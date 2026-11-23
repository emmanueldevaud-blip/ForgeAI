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
    this.element.innerHTML = this._renderShell(p, story, legacy);
    this._bindEvents();
    return this.element;
  }

  _renderShell(p, story, legacy) {
    const caption = this.captionValue;
    const photoUrl = (id) => (publicationPhotoUrl ? publicationPhotoUrl(id) : `/photos/${id}/file?size=medium`);
    const media = p.photo_id ? `<img src="${this._esc(photoUrl(p.photo_id))}" alt="Aperçu de la publication">` : '<div class="cm-ig-empty">Choisissez une photo pour voir l’aperçu</div>';

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
      <header class="cm-ig-topbar"><button type="button" class="cm-ig-back" data-action="back">Annuler</button><strong>Nouvelle publication</strong><span>Instagram</span></header>
      <div class="cm-ig-workspace">
        <section class="cm-ig-phone" aria-label="Aperçu Instagram">
          <div class="cm-ig-post-head"><span class="cm-ig-avatar">${this._esc((p.title || 'F').slice(0, 1).toUpperCase())}</span><strong>${this._esc(p.instagram_username || 'votre_compte')}</strong><span>•••</span></div>
          <div class="cm-ig-media">${media}</div>
          <div class="cm-ig-post-actions"><span>♡</span><span>♧</span><span>➤</span><span class="cm-ig-save">♧</span></div>
          <div class="cm-ig-caption"><strong>${this._esc(p.instagram_username || 'votre_compte')}</strong> ${this._esc([p.title, p.hashtags].filter(Boolean).join('\n\n') || 'Votre légende Instagram apparaîtra ici.')}</div>
          <div class="cm-ig-time">À L’INSTANT</div>
        </section>
        <section class="cm-ig-editor">
          <div class="cm-ig-editor-heading"><div><span class="cm-ig-kicker">CRÉATION</span><h1>${legacy ? 'Publication sportive' : 'Préparer la publication'}</h1></div><span class="cm-ig-network">◎ Instagram</span></div>
          <form data-form="studio-edit" class="cm-ig-form">
            <label>Titre<input name="title" maxlength="200" value="${this._esc(p.title || '')}" placeholder="Le titre de votre publication"></label>
            <label>Texte sur le visuel<textarea name="content" rows="4" class="cm-studio-caption" placeholder="Texte affiché sur l’image">${this._esc(p.content || '')}</textarea></label>
            <label>Légende et hashtags<textarea name="hashtags" rows="5" placeholder="Écrivez la légende de votre publication">${this._esc(p.hashtags || '')}</textarea></label>
            <div class="cm-ig-form-footer"><span>${this.captionLength} caractères</span><button type="button" class="btn btn-secondary" data-action="photos">${p.photo_id ? 'Changer la photo' : 'Choisir une photo'}</button><button type="button" class="btn btn-primary" data-action="save-form">Enregistrer</button></div>
          </form>
          <div class="cm-ig-publish-row"><span>Vérifiez l’aperçu avant publication.</span><button type="button" class="btn btn-primary" data-action="publish">Publier</button></div>
        </section>
      </div>
    `;

    const picker = this.photoPickerOpen ? `
      <section class="cm-studio-photo-panel cm-studio-photo-picker">
        <div class="cm-ig-picker-heading"><strong>Choisir une photo</strong><button type="button" class="btn btn-secondary" data-action="apply-photos">Utiliser la sélection</button></div>
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
      </section>
    ` : '';

    return `
      <div class="cm-studio-root ${story ? '' : 'cm-ig-studio'}">
        ${story ? storyView : `
          <div class="cm-ig-main">${storyView}</div>
        `}
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

    const photoBtn = el.querySelector?.('[data-action="photos"]');
    if (photoBtn) photoBtn.addEventListener('click', async () => { await this._togglePhotoPicker(); this.render(); });
    const applyPhotosBtn = el.querySelector?.('[data-action="apply-photos"]');
    if (applyPhotosBtn) applyPhotosBtn.addEventListener('click', async () => { await this._applyPhotoSelection(); this.render(); });

    const saveBtn = el.querySelector?.('[data-action="save-form"]');
    if (saveBtn) saveBtn.addEventListener('click', async () => { await this._saveForm(); this.render(); });

    el.querySelectorAll?.('[data-photo-id]').forEach((btn) => {
      btn.addEventListener('click', () => { this._togglePhotoSelection(btn.dataset.photoId); this.render(); });
    });

    const form = el.querySelector?.('[data-form="studio-edit"]');
    form?.addEventListener('input', () => {
      const title = form.elements.title?.value || '';
      const hashtags = form.elements.hashtags?.value || '';
      const caption = el.querySelector('.cm-ig-caption');
      if (caption) caption.innerHTML = `<strong>${this._esc(this.publication?.instagram_username || 'votre_compte')}</strong> ${this._esc([title, hashtags].filter(Boolean).join('\n\n') || 'Votre légende Instagram apparaîtra ici.')}`;
      const counter = el.querySelector('.cm-ig-form-footer > span');
      if (counter) counter.textContent = `${[title, hashtags].filter(Boolean).join('\n\n').length} caractères`;
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
    this.publication = { ...this.publication, ...values };
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
    this.publication = { ...p, photo_id: ids[0] ?? null };
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
