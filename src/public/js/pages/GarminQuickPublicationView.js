import {
  companionVideoUrl,
  getStudioDraft,
  getSuggestedPhotos,
  publishStudioDraft,
  updateStudioDraft,
  validateStudioDraft,
} from '../services/sportApi.js?v=14';

/** Parcours Garmin sans timeline ni Studio graphique. */
export class GarminQuickPublicationView {
  constructor(publicationId, onBack) {
    this.publicationId = publicationId;
    this.onBack = onBack;
    this.element = null;
    this.publication = null;
    this.photos = [];
    this.selected = [];
    this.busy = false;
    this.error = null;
    this.videoReady = false;
    this.pollTimer = null;
  }

  async initialize() {
    try {
      this.publication = await getStudioDraft(this.publicationId);
      this.photos = await getSuggestedPhotos(this.publicationId, 20);
      const carousel = this.publication?.design?.carousel;
      this.selected = Array.isArray(carousel) && carousel.length
        ? [...carousel] : (this.publication?.photo_id ? [this.publication.photo_id] : []);
    } catch (error) {
      this.error = error?.data?.detail || error?.message || 'Impossible de charger les photos.';
    }
    this.render();
  }

  render() {
    if (!this.element) this.element = document.createElement('div');
    this.element.className = 'page-content garmin-quick-publication';
    const pub = this.publication || {};
    const status = pub.companion_video_status || 'none';
    const ready = this.videoReady || status === 'ready';
    const caption = [pub.title, pub.hashtags].filter(Boolean).join('\n\n');
    this.element.innerHTML = `
      <div class="page-header"><div><h1>${this._escape(pub.title || 'Publication Garmin')}</h1>
        <p class="page-subtitle">${ready ? 'Aperçu et publication' : 'Choisissez vos photos'}</p></div></div>
      ${this.error ? `<div class="alert alert-error">${this._escape(this.error)}</div>` : ''}
      ${!ready ? `<section class="cm-studio-photo-picker garmin-quick-photos">
        <p>Sélectionnez une ou plusieurs photos. La première sera la couverture.</p>
        <div class="cm-studio-photo-grid">${this.photos.map(p => this._photo(p)).join('')}</div>
        <button class="btn btn-primary" data-action="create" ${!this.selected.length || this.busy ? 'disabled' : ''}>
          ${this.busy ? 'Création de la vidéo…' : 'Créer ma vidéo'}
        </button>
      </section>` : `<section class="garmin-quick-result">
        <video controls playsinline class="garmin-quick-video" src="${companionVideoUrl(this.publicationId)}"></video>
        <label>Légende Instagram</label>
        <pre class="garmin-quick-caption">${this._escape(caption)}</pre>
        <div class="cm-studio-actions">
          <button class="btn btn-secondary" data-action="back-photos">Modifier les photos</button>
          <button class="btn btn-success" data-action="publish" ${this.busy ? 'disabled' : ''}>
            ${this.busy ? 'Publication…' : 'Valider et publier'}
          </button>
        </div>
      </section>`}
      <button class="btn btn-secondary" data-action="back">Retour au calendrier</button>`;
    this._bind();
    return this.element;
  }

  _photo(photo) {
    const id = Number(photo.id);
    return `<button type="button" class="cm-studio-photo-thumb ${this.selected.includes(id) ? 'cm-studio-photo-thumb--selected' : ''}" data-photo-id="${id}">
      <img src="${this._escape(photo.thumbnail_url || `/photos/${id}/file?size=small`)}" alt="Photo" loading="lazy">
      ${this.selected.includes(id) ? `<span class="cm-studio-photo-order">${this.selected.indexOf(id) + 1}</span>` : ''}
    </button>`;
  }

  _bind() {
    this.element.querySelectorAll('[data-photo-id]').forEach(btn => btn.addEventListener('click', () => {
      const id = Number(btn.dataset.photoId);
      const index = this.selected.indexOf(id);
      if (index >= 0) this.selected.splice(index, 1);
      else this.selected.push(id);
      this.render();
    }));
    this.element.querySelector('[data-action="create"]')?.addEventListener('click', () => this._create());
    this.element.querySelector('[data-action="publish"]')?.addEventListener('click', () => this._publish());
    this.element.querySelector('[data-action="back-photos"]')?.addEventListener('click', () => {
      this.videoReady = false; this.error = null; this.render();
    });
    this.element.querySelector('[data-action="back"]')?.addEventListener('click', () => this.onBack?.());
  }

  async _create() {
    if (this.busy || !this.selected.length) return;
    this.busy = true; this.error = null; this.render();
    try {
      this.publication = await updateStudioDraft(this.publicationId, { photo_ids: this.selected });
      await this._waitForVideo();
    } catch (error) {
      this.error = error?.data?.detail || error?.message || 'La génération vidéo a échoué.';
      this.busy = false; this.render();
    }
  }

  async _waitForVideo() {
    for (let attempt = 0; attempt < 180; attempt += 1) {
      this.publication = await getStudioDraft(this.publicationId);
      const status = this.publication.companion_video_status;
      if (status === 'ready') { this.videoReady = true; this.busy = false; this.render(); return; }
      if (status === 'failed') throw new Error(this.publication.companion_video_error || 'Rendu vidéo impossible.');
      this.render();
      await new Promise(resolve => { this.pollTimer = setTimeout(resolve, 1000); });
    }
    throw new Error('La génération prend plus de temps que prévu. Réessayez dans un instant.');
  }

  async _publish() {
    if (this.busy) return;
    this.busy = true; this.error = null; this.render();
    try {
      await validateStudioDraft(this.publicationId, { confirm: true });
      await publishStudioDraft(this.publicationId, { confirm: true });
      this.publication = await getStudioDraft(this.publicationId);
      this.busy = false; this.render();
    } catch (error) {
      this.error = error?.data?.detail || error?.message || 'Publication impossible.';
      this.busy = false; this.render();
    }
  }

  _escape(value) {
    return String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  destroy() { if (this.pollTimer) clearTimeout(this.pollTimer); }
}

export function createGarminQuickPublicationView(publicationId, onBack) {
  return new GarminQuickPublicationView(publicationId, onBack);
}
