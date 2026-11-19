import {
  companionVideoUrl,
  getStudioDraft,
  getSuggestedPhotos,
  publishStudioDraft,
  updateStudioDraft,
  validateStudioDraft,
  searchStudioMusic,
} from '../services/sportApi.js?v=14';

/** Parcours Garmin sans timeline ni Studio graphique. */
export class GarminQuickPublicationView {
  constructor(publicationId, onBack) {
    this.publicationId = publicationId;
    this.onBack = onBack;
    this.element = null;
    this.publication = null;
    this.photos = [];
    this.photosLimit = 20;
    this.selected = [];
    this.busy = false;
    this.generating = false;
    this.error = null;
    this.videoReady = false;
    this.editedTitle = '';
    this.editedHashtags = '';
    this.videoUrl = null;
    this.previewOpen = false;
    this.pollTimer = null;
    this.musicItems = [];
    this.musicQueryIndex = 0;
    this.captionSaveTimer = null;
    this.musicMuted = true;
    this.musicSelectionTimer = null;
    this.musicQueries = ['trail running motivation', 'running energy songs', 'mountain adventure music', 'happy workout music', 'freedom running songs'];
  }

  async initialize() {
    try {
      this.publication = await getStudioDraft(this.publicationId);
      this.photos = await getSuggestedPhotos(this.publicationId, this.photosLimit);
      const carousel = this.publication?.design?.carousel;
      this.selected = Array.isArray(carousel) && carousel.length
        ? [...carousel] : (this.publication?.photo_id ? [this.publication.photo_id] : []);
      this.editedTitle = this.publication?.title || '';
      this.editedHashtags = this.publication?.hashtags || '';
      await this._loadMusic(false);
      const savedSuggestions = this.publication?.design?.ig_audio?.suggestions;
      if (Array.isArray(savedSuggestions) && savedSuggestions.length) {
        this.musicItems = savedSuggestions;
      }
      if (this.publication?.companion_video_status === 'ready') {
        this.videoReady = true;
        await this._loadVideoPreview();
      }
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
    const ready = this.videoReady && status === 'ready';
    const title = this.editedTitle || pub.title || '';
    const hashtags = this.editedHashtags || pub.hashtags || '';
    const caption = [title, hashtags].filter(Boolean).join('\n\n');
    const sportStats = Array.isArray(pub.design?.elements)
      ? pub.design.elements.filter(element => element?.type === 'sport_stats')
      : [];
    const previewStats = sportStats.map(element => `
      <span class="garmin-preview-stat">
        <small>${this._escape(element.label || '')}</small>
        <strong>${this._escape(element.value || '')} ${this._escape(element.unit || '')}</strong>
      </span>`).join('');
    this.element.innerHTML = `
      <div class="page-header"><div><h1>${this._escape(pub.title || 'Publication Garmin')}</h1>
        <p class="page-subtitle">${ready ? 'Aperçu et publication' : 'Choisissez vos photos'}</p></div></div>
      ${this.error ? `<div class="alert alert-error">${this._escape(this.error)}</div>` : ''}
      ${!ready ? `<section class="cm-studio-photo-picker garmin-quick-photos">
        <p class="garmin-quick-intro"><span class="garmin-quick-intro-icon" aria-hidden="true">📸</span><span><strong>Composez votre Reel</strong><small>Choisissez vos photos · la première sera la couverture</small></span></p>
        <div class="cm-studio-photo-grid">${this.photos.map(p => this._photo(p)).join('')}</div>
        ${this.photos.length >= this.photosLimit ? '<button class="btn btn-secondary" data-action="more-photos">Voir plus</button>' : ''}
        ${this.generating ? '<p class="garmin-quick-progress">Préparation de la vidéo et publication en cours…</p>' : ''}
        <div class="garmin-quick-caption-card"><label for="garmin-title">Légende</label><input id="garmin-title" class="form-control" data-field="title" value="${this._escape(title)}"><label for="garmin-hashtags">Hashtags</label><textarea id="garmin-hashtags" class="form-control" data-field="hashtags" rows="2">${this._escape(hashtags)}</textarea><small data-caption-status></small></div>
        <div class="garmin-quick-music">🎵 <select id="garmin-music-select" data-action="music-select"><option value="">${this._escape(pub.design?.ig_audio?.title || 'Choisir un titre')}</option>${this.musicItems.map((item, index) => `<option value="${index}" ${String(item.audio_id) === String(pub.design?.ig_audio?.audio_id) ? 'selected' : ''}>${this._escape(item.title || 'Sans titre')} — ${this._escape(item.display_artist || 'Artiste')}</option>`).join('')}</select><button class="btn btn-link" data-action="music-refresh">10 autres titres</button>${pub.design?.ig_audio?.preview_link ? `<div class="garmin-music-preview"><audio data-music-audio src="${this._escape(pub.design.ig_audio.preview_link)}" autoplay loop ${this.musicMuted ? 'muted' : ''} controls></audio><button type="button" class="btn btn-link" data-action="music-mute">${this.musicMuted ? '🔇' : '🔊'}</button></div>` : ''}</div>
        <div class="garmin-quick-actions"><button class="btn btn-secondary" data-action="preview">👀 Aperçu</button>
        <button class="btn btn-primary" data-action="publish" ${!this.selected.length || this.busy || this.generating ? 'disabled' : ''}>
          ${this.busy ? 'Publication…' : '🚀 Publier'}
        </button></div>
      </section>` : `<section class="garmin-quick-result">
        ${this.videoUrl ? `<video controls playsinline preload="metadata" class="garmin-quick-video" src="${this._escape(this.videoUrl)}"></video>` : '<div class="garmin-quick-video garmin-quick-video--loading">Chargement de l’aperçu vidéo…</div>'}
        <div class="garmin-quick-caption-card"><strong>${this._escape(title)}</strong><span>${this._escape(hashtags)}</span><button class="btn btn-link" data-action="edit-caption">Modifier la légende</button></div>
        <div class="garmin-quick-music">🎵 <label for="garmin-music-select">Musique Instagram</label><select id="garmin-music-select" data-action="music-select"><option value="">${this._escape(pub.design?.ig_audio?.title || 'Choisir une musique')}</option>${this.musicItems.map((item, index) => `<option value="${index}" ${String(item.audio_id) === String(pub.design?.ig_audio?.audio_id) ? 'selected' : ''}>${this._escape(item.title || 'Sans titre')} — ${this._escape(item.display_artist || 'Artiste')}</option>`).join('')}</select><button class="btn btn-link" data-action="music-refresh">10 autres titres</button><small class="garmin-quick-music-status">${pub.design?.ig_audio?.audio_id ? 'Musique retenue pour la publication Instagram' : 'La musique sera ajoutée à la publication Instagram'}</small></div>
        <div class="cm-studio-actions">
          <button class="btn btn-secondary" data-action="back-photos">📸 Photos</button>
          <button class="btn btn-secondary" data-action="preview">👀 Aperçu</button>
          <button class="btn btn-success" data-action="publish" ${this.busy ? 'disabled' : ''}>
            ${this.busy ? 'Publication…' : '🚀 Publier'}
          </button>
        </div>
      </section>`}
      <button class="btn btn-secondary" data-action="back">Retour au calendrier</button>`;
    if (this.previewOpen) { const previewDuration = Math.max(this.selected.length * 2.4, 2.4); this.element.insertAdjacentHTML('beforeend', `<div class="garmin-preview-overlay" data-action="close-preview"><div class="garmin-preview-modal" role="dialog" aria-label="Aperçu du montage" data-preview-panel><button class="garmin-preview-close" data-action="close-preview">×</button><div class="garmin-preview-account">Aperçu du Reel · Instagram / Facebook</div><div class="garmin-preview-slideshow" style="--preview-duration:${previewDuration}s">${this.selected.map((id, index) => `<img src="/photos/${id}/file?size=medium" alt="Photo ${index + 1}" loading="lazy" style="--slide-delay:${index * 2.4}s">`).join('')}<div class="garmin-preview-stats">${previewStats || '<span class="garmin-preview-stat garmin-preview-stat--empty">Statistiques Garmin indisponibles</span>'}</div></div><div class="garmin-preview-audio">🎵 ${this._escape(pub.design?.ig_audio?.title || 'Titre sélectionné')}</div><div class="garmin-preview-caption"><strong>${this._escape(title)}</strong><br>${this._escape(hashtags)}</div></div></div>`); }
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
      this._schedulePhotoMusicAnalysis();
    }));
    this.element.querySelector('[data-action="publish"]')?.addEventListener('click', () => this._publish());
    this.element.querySelector('[data-action="preview"]')?.addEventListener('click', () => { this.previewOpen = true; this.render(); });
    this.element.querySelector('[data-action="music"]')?.addEventListener('click', () => this._chooseMusic());
    this.element.querySelector('[data-action="music-refresh"]')?.addEventListener('click', () => this._loadMusic(true));
    this.element.querySelector('[data-action="more-photos"]')?.addEventListener('click', async () => { this.photosLimit += 20; this.photos = await getSuggestedPhotos(this.publicationId, this.photosLimit); this.render(); });
    this.element.querySelector('[data-action="music-select"]')?.addEventListener('change', event => this._selectMusic(Number(event.target.value)));
    this.element.querySelector('[data-action="music-mute"]')?.addEventListener('click', event => {
      const audio = this.element.querySelector('[data-music-audio]');
      if (!audio) return;
      audio.muted = !audio.muted;
      this.musicMuted = audio.muted;
      event.currentTarget.textContent = audio.muted ? '🔇' : '🔊';
    });
    this.element.querySelector('[data-field="title"]')?.addEventListener('input', event => this._queueCaptionSave('title', event.target.value));
    this.element.querySelector('[data-field="hashtags"]')?.addEventListener('input', event => this._queueCaptionSave('hashtags', event.target.value));
    this.element.querySelector('[data-action="edit-caption"]')?.addEventListener('click', () => this._editCaption());
    this.element.querySelectorAll('[data-action="close-preview"]').forEach(el => el.addEventListener('click', event => { if (event.target === el || event.target.dataset.action === 'close-preview') { this.previewOpen = false; this.render(); } }));
    this.element.querySelector('[data-action="back-photos"]')?.addEventListener('click', () => {
      this.videoReady = false; this.error = null; this.previewOpen = false;
      this.publication = { ...(this.publication || {}), companion_video_status: 'none', companion_video_path: null };
      if (this.videoUrl?.startsWith('blob:')) URL.revokeObjectURL(this.videoUrl);
      this.videoUrl = null;
      this.render();
    });
    this.element.querySelector('[data-action="back"]')?.addEventListener('click', () => this.onBack?.());
  }

  async _create() {
    if (this.busy || !this.selected.length) return;
    this.busy = true; this.error = null; this.render();
    try {
      this.publication = await updateStudioDraft(this.publicationId, {
        photo_ids: this.selected,
        quick_generation: true,
      });
      // La requête ne doit pas attendre l'encodage FFmpeg : le job est déjà
      // planifié par le backend lors de la mise à jour des photos.
      this.busy = false;
      this.generating = true;
      this.render();
      this._pollVideo().catch(error => {
        this.error = error?.message || 'La génération vidéo a échoué.';
        this.generating = false;
        this.render();
      });
    } catch (error) {
      this.error = error?.data?.detail || error?.message || 'La génération vidéo a échoué.';
      this.busy = false; this.render();
    }
  }

  _schedulePhotoMusicAnalysis() {
    clearTimeout(this.musicSelectionTimer);
    if (!this.selected.length) return;
    this.musicSelectionTimer = setTimeout(async () => {
      try {
        this.error = null;
        const updated = await updateStudioDraft(this.publicationId, {
          photo_ids: this.selected,
          quick_generation: true,
        });
        this.publication = updated;
        const audio = updated?.design?.ig_audio;
        if (Array.isArray(audio?.suggestions) && audio.suggestions.length) {
          this.musicItems = audio.suggestions.slice(0, 10);
        }
        this.render();
      } catch (error) {
        this.error = error?.data?.detail || error?.message || 'Analyse musicale impossible.';
        this.render();
      }
    }, 500);
  }

  async _pollVideo() {
    for (let attempt = 0; attempt < 180; attempt += 1) {
      this.publication = await getStudioDraft(this.publicationId);
      const status = this.publication.companion_video_status;
      if (status === 'ready') {
        this.videoReady = true;
        this.generating = false;
        await this._loadVideoPreview();
        this.render();
        return;
      }
      if (status === 'failed') throw new Error(this.publication.companion_video_error || 'Rendu vidéo impossible.');
      this.render();
      await new Promise(resolve => { this.pollTimer = setTimeout(resolve, 1000); });
    }
    throw new Error('La génération prend plus de temps que prévu. Réessayez dans un instant.');
  }

  async _publish() {
    if (this.busy) return;
    this.busy = true; this.generating = true; this.error = null; this.render();
    try {
      this.publication = await updateStudioDraft(this.publicationId, {
        photo_ids: this.selected,
        quick_generation: true,
        title: this.editedTitle,
        hashtags: this.editedHashtags,
      });
      await validateStudioDraft(this.publicationId, { confirm: true });
      await publishStudioDraft(this.publicationId, { confirm: true });
      this.publication = await getStudioDraft(this.publicationId);
      this.busy = false; this.generating = false; this.videoReady = false; this.render();
      setTimeout(() => this.onBack?.(), 500);
    } catch (error) {
      this.error = error?.data?.detail || error?.message || 'Publication impossible.';
      this.busy = false; this.generating = false; this.render();
    }
  }

  async _chooseMusic() {
    const query = window.prompt('Rechercher une musique Instagram (paroles, artiste ou ambiance) :', 'trail running motivation');
    if (!query) return;
    try {
      const result = await searchStudioMusic(this.publicationId, query);
      const items = result?.items || [];
      if (!items.length) { window.alert('Aucune musique Instagram trouvée.'); return; }
      const labels = items.map((item, index) => `${index + 1}. ${item.title || 'Sans titre'} — ${item.display_artist || 'Artiste'}`).join('\n');
      const choice = Number(window.prompt(`Choisissez une musique :\n${labels}`, '1')) - 1;
      const item = items[choice];
      if (!item?.audio_id) return;
      this.publication = await updateStudioDraft(this.publicationId, { design: { ig_audio: { source: 'instagram', status: 'selected', audio_id: String(item.audio_id), title: item.title || '', artist: item.display_artist || '', duration_in_ms: item.duration_in_ms, preview_link: item.on_platform_audio_preview_link || item.download_url } } });
      this.musicItems = this.musicItems.map((candidate, candidateIndex) => candidateIndex === index ? item : candidate);
      this.render();
    } catch (error) { this.error = error?.data?.detail || error?.message || 'Choix musical impossible.'; this.render(); }
  }

  async _loadMusic(refresh) {
    try {
      if (refresh) this.musicQueryIndex = (this.musicQueryIndex + 1) % this.musicQueries.length;
      const result = await searchStudioMusic(this.publicationId, this.musicQueries[this.musicQueryIndex]);
      this.musicItems = (result?.items || []).slice(0, 10);
      this.render();
    } catch (error) {
      this.error = error?.data?.detail || error?.message || 'Musiques Instagram indisponibles.';
      this.render();
    }
  }

  async _selectMusic(index) {
    const item = this.musicItems[index];
    if (!item?.audio_id) return;
    try {
      this.publication = await updateStudioDraft(this.publicationId, { design: { ig_audio: { source: 'instagram', status: 'selected', audio_id: String(item.audio_id), title: item.title || '', artist: item.display_artist || '', duration_in_ms: item.duration_in_ms, preview_link: item.on_platform_audio_preview_link || item.download_url } } });
      this.render();
    } catch (error) { this.error = error?.data?.detail || error?.message || 'Sélection musicale impossible.'; this.render(); }
  }

  async _editCaption() {
    const title = window.prompt('Titre de la publication :', this.editedTitle);
    if (title === null) return;
    const hashtags = window.prompt('Hashtags :', this.editedHashtags);
    if (hashtags === null) return;
    try {
      this.publication = await updateStudioDraft(this.publicationId, { title: title.trim(), hashtags: hashtags.trim() });
      this.editedTitle = title.trim(); this.editedHashtags = hashtags.trim(); this.render();
    } catch (error) { this.error = error?.data?.detail || error?.message || 'Modification impossible.'; this.render(); }
  }

  _queueCaptionSave(field, value) {
    if (field === 'title') this.editedTitle = value;
    if (field === 'hashtags') this.editedHashtags = value;
    const status = this.element.querySelector('[data-caption-status]');
    if (status) status.textContent = 'Modification en cours…';
    clearTimeout(this.captionSaveTimer);
    this.captionSaveTimer = setTimeout(async () => {
      try {
        this.publication = await updateStudioDraft(this.publicationId, { title: this.editedTitle, hashtags: this.editedHashtags });
        const saved = this.element.querySelector('[data-caption-status]');
        if (saved) saved.textContent = 'Enregistré automatiquement';
      } catch (error) {
        const failed = this.element.querySelector('[data-caption-status]');
        if (failed) failed.textContent = 'Échec de l’enregistrement';
      }
    }, 600);
  }

  async _loadVideoPreview() {
    const url = `${companionVideoUrl(this.publicationId)}?v=${encodeURIComponent(this.publication?.companion_video_generated_at || '')}`;
    const response = await fetch(url, { credentials: 'include', headers: { Accept: 'video/mp4' } });
    if (!response.ok) throw new Error(`Aperçu vidéo indisponible (${response.status}).`);
    const blob = await response.blob();
    if (this.videoUrl?.startsWith('blob:')) URL.revokeObjectURL(this.videoUrl);
    this.videoUrl = URL.createObjectURL(blob);
  }

  _escape(value) {
    return String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  destroy() {
    if (this.pollTimer) clearTimeout(this.pollTimer);
    clearTimeout(this.captionSaveTimer);
    if (this.videoUrl?.startsWith('blob:')) URL.revokeObjectURL(this.videoUrl);
  }
}

export function createGarminQuickPublicationView(publicationId, onBack) {
  return new GarminQuickPublicationView(publicationId, onBack);
}
