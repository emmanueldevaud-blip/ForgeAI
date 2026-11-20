import {
  companionVideoUrl,
  getStudioDraft,
  getSuggestedPhotos,
  publishStudioDraftBoth,
  updateStudioDraft,
  validateStudioDraft,
  searchStudioMusic,
  getEditorialBrief,
  regeneratePublicationContent,
  getLocalStudioMusic,
  getStudioAudioMatch,
  getStudioAudioProposals,
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
    this.audioProposals = [];
    this.audioProposalLoading = false;
    this.audioProposalError = null;
    this.audioProposalVersion = 0;
    this.audioProposalTimer = null;
    this.audioProposalExclude = [];
    this.previewAudio = null;
    this.audioPlayingId = null;
    this.audioPlaybackError = null;
    this.localMusicItems = [];
    this.musicLoading = false;
    this.musicError = null;
    this.musicQueryIndex = 0;
    this.captionSaveTimer = null;
    this.musicMuted = true;
    this.musicSelectionTimer = null;
    this.editorialBrief = null;
    this.musicQueries = ['trail running motivation', 'running energy songs', 'mountain adventure music', 'happy workout music', 'freedom running songs'];
  }

  async initialize() {
    try {
      this.publication = await getStudioDraft(this.publicationId);
      this.editedTitle = this.publication?.title || '';
      this.editedHashtags = this.publication?.hashtags || '';
      // Publication déjà partagée : lecture seule, on ne charge que le contenu publié.
      if (this.publication?.status === 'shared') {
        if (this.publication?.companion_video_status === 'ready') {
          this.videoReady = true;
          await this._loadVideoPreview();
        }
        this.render();
        return;
      }
      this.photos = await getSuggestedPhotos(this.publicationId, this.photosLimit);
      try { this.editorialBrief = await getEditorialBrief(this.publicationId); } catch (_) { this.editorialBrief = null; }
      const carousel = this.publication?.design?.carousel;
      this.selected = Array.isArray(carousel) && carousel.length
        ? [...carousel] : (this.publication?.photo_id ? [this.publication.photo_id] : []);
      // La recherche du catalogue Meta est indépendante du chargement du brouillon.
      // Ne pas bloquer l'ouverture de la publication sur un fournisseur externe.
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
    this._loadLocalMusic();
    this._scheduleAudioProposals();
    if (this.publication?.status !== 'shared') this._loadMusic(false);
  }

  render() {
    if (this.publication?.status === 'shared') return this._renderLegacy();
    return this._renderModern();
  }

  _renderLegacy() {
    if (!this.element) this.element = document.createElement('div');
    this.element.className = 'page-content garmin-quick-publication';
    const pub = this.publication || {};
    const status = pub.companion_video_status || 'none';
    const ready = this.videoReady && status === 'ready';
    const isShared = pub.status === 'shared';
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

    // Publication déjà partagée : lecture seule, seul le retour est possible.
    if (isShared) {
      const music = pub.design?.ig_audio;
      const publishedMusic = (ready && music?.audio_id && music?.preview_link) ? music : null;
      this.element.innerHTML = `
        <div class="page-header"><div><h1>${this._escape(pub.title || 'Publication Garmin')}</h1>
          <p class="page-subtitle">Publication publiée</p></div></div>
        ${this.error ? `<div class="alert alert-error">${this._escape(this.error)}</div>` : ''}
        <section class="garmin-quick-result">
          ${ready ? `<video controls playsinline preload="metadata" class="garmin-quick-video" src="${this._escape(this.videoUrl || '')}"${publishedMusic ? ' muted' : ''}></video>` : (status === 'ready' ? '<div class="garmin-quick-video garmin-quick-video--loading">Chargement de l’aperçu vidéo…</div>' : '')}
          ${publishedMusic ? `<div class="garmin-music-preview"><audio data-music-audio data-start-time-ms="${Number(publishedMusic.start_time_ms) || 0}" src="${this._escape(publishedMusic.preview_link)}" preload="metadata"></audio></div>` : ''}
          <div class="garmin-quick-caption-card"><strong>${this._escape(title)}</strong><span>${this._escape(hashtags)}</span></div>
          ${music?.title ? `<div class="garmin-quick-music">🎵 <span>${this._escape(music.title)}${music.artist ? ` — ${this._escape(music.artist)}` : ''}</span></div>` : ''}
        </section>
        <button class="btn btn-secondary" data-action="back">Retour au calendrier</button>`;
      this._bind();
      return this.element;
    }

    this.element.innerHTML = `
      <div class="page-header"><div><h1>${this._escape(pub.title || 'Publication Garmin')}</h1>
        <p class="page-subtitle">${ready ? 'Aperçu et publication' : 'Choisissez vos photos'}</p></div></div>
      ${this.error ? `<div class="alert alert-error">${this._escape(this.error)}</div>` : ''}
      ${!ready ? `<section class="cm-studio-photo-picker garmin-quick-photos">
        <p class="garmin-quick-intro"><span class="garmin-quick-intro-icon" aria-hidden="true">📸</span><span><strong>Composez votre Reel</strong><small>Choisissez vos photos · la première sera la couverture</small></span></p>
        ${this.editorialBrief?.direction ? `<div class="garmin-editorial-brief"><span>🎨</span><label for="garmin-editorial-style">Ambiance</label><select id="garmin-editorial-style" data-action="editorial-style"><option value="cinematique">Cinématique</option><option value="humour">Humour</option><option value="dynamique">Dynamique</option><option value="performance">Performance</option></select><small>${this._escape(this.editorialBrief.direction.reason || '')}</small></div>` : ''}
        <div class="cm-studio-photo-grid">${this.photos.map(p => this._photo(p)).join('')}</div>
        ${this.photos.length >= this.photosLimit ? '<button class="btn btn-secondary" data-action="more-photos">Voir plus</button>' : ''}
        ${this.generating ? '<p class="garmin-quick-progress">Préparation de la vidéo et publication en cours…</p>' : ''}
        <div class="garmin-quick-caption-card"><label for="garmin-title">Légende</label><input id="garmin-title" class="form-control" data-field="title" value="${this._escape(title)}"><label for="garmin-hashtags">Hashtags</label><textarea id="garmin-hashtags" class="form-control" data-field="hashtags" rows="2">${this._escape(hashtags)}</textarea><small data-caption-status></small></div>
        <div class="garmin-quick-music">🎵 <label for="garmin-local-music-select">Musique du Reel</label><select id="garmin-local-music-select" data-action="local-music-select"><option value="">${this._escape(pub.design?.audio?.title || 'Choisir une piste locale')}</option>${this.localMusicItems.map(item => `<option value="${this._escape(item.track_id)}" ${String(item.track_id) === String(pub.design?.audio?.track_id) ? 'selected' : ''}>${this._escape(item.title)} — ${this._escape(item.artist)}</option>`).join('')}</select><button class="btn btn-link" data-action="audio-match">🎧 Proposition IA</button><label for="garmin-music-select">Musique Instagram (Meta)</label><select id="garmin-music-select" data-action="music-select"><option value="">${this._escape(pub.design?.ig_audio?.title || 'Choisir un titre')}</option>${this.musicItems.map((item, index) => `<option value="${index}" ${String(item.audio_id) === String(pub.design?.ig_audio?.audio_id) ? 'selected' : ''}>${this._escape(item.title || 'Sans titre')} — ${this._escape(item.display_artist || 'Artiste')}</option>`).join('')}</select><button class="btn btn-link" data-action="music-refresh">10 autres titres</button>${this.musicLoading ? '<small>Recherche musicale…</small>' : ''}${this.musicError ? `<small class="text-danger">${this._escape(this.musicError)} <button class="btn btn-link" data-action="music-retry">Réessayer</button></small>` : ''}${pub.design?.audio?.url ? `<div class="garmin-music-preview"><audio data-music-audio src="${this._escape(pub.design.audio.url)}" preload="metadata" loop ${this.musicMuted ? 'muted' : ''} controls></audio><button type="button" class="btn btn-link" data-action="music-mute">${this.musicMuted ? '🔇' : '🔊'}</button><small>Extrait : ${Number(pub.design.audio.audio_match?.start_time || 0).toFixed(1)}s → ${Number(pub.design.audio.audio_match?.end_time || 0).toFixed(1)}s. ${this._escape(pub.design.audio.audio_match?.reason || 'Piste locale vérifiée.')}</small></div>` : '<small>Musique locale indisponible pour le moment.</small>'}</div>
        <div class="garmin-quick-actions"><button class="btn btn-secondary" data-action="preview">👀 Aperçu</button><button class="btn btn-secondary" data-action="regenerate-editorial">🔄 Nouvelle idée</button>
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

  _renderModern() {
    if (!this.element) this.element = document.createElement('div');
    this.element.className = 'page-content garmin-quick-publication';
    const pub = this.publication || {};
    const design = pub.design || {};
    const ready = this.videoReady && pub.companion_video_status === 'ready';
    const title = this.editedTitle || pub.title || '';
    const hashtags = this.editedHashtags || pub.hashtags || '';
    const style = design.editorial_engine?.style || 'performance';
    const audio = design.audio || {};
    const excerpt = audio.audio_match || {};
    const styleCards = [
      ['cinematique', 'Cinématique', 'Mouvements doux · émotion'],
      ['humour', 'Humour', 'Rythme léger · autodérision'],
      ['dynamique', 'Dynamique', 'Transitions rapides · énergie'],
      ['performance', 'Performance', 'Stats fortes · rythme sobre'],
    ];
    const musicOptions = this.localMusicItems.map(item => `<option value="${this._escape(item.track_id)}" ${String(item.track_id) === String(audio.track_id) ? 'selected' : ''}>${this._escape(item.title)} — ${this._escape(item.artist)}</option>`).join('');
    const photoCount = this.selected.length;
    this.element.innerHTML = `
      <header class="garmin-quick-header"><div><span class="garmin-quick-kicker">GARMIN QUICK REEL</span><h1>${this._escape(pub.title || 'Créer votre Reel')}</h1><p>Photos · ambiance · musique · publication</p></div><button class="btn btn-secondary" data-action="back">Retour</button></header>
      ${this.error ? `<div class="alert alert-error">${this._escape(this.error)}</div>` : ''}
      <main class="garmin-quick-flow">
        <section class="garmin-quick-step" data-step="1"><div class="garmin-step-heading"><span>01</span><div><h2>Photos</h2><p>${photoCount} photo${photoCount > 1 ? 's' : ''} sélectionnée${photoCount > 1 ? 's' : ''} · glissez pour réorganiser</p></div></div><div class="garmin-modern-photo-grid">${this.photos.map(p => this._photo(p)).join('')}</div>${this.photos.length >= this.photosLimit ? '<button class="btn btn-link" data-action="more-photos">Afficher plus de photos</button>' : ''}</section>
        <section class="garmin-quick-step" data-step="2"><div class="garmin-step-heading"><span>02</span><div><h2>Ambiance</h2><p>ForgeAI adapte le rythme et les effets du montage.</p></div></div><div class="garmin-style-grid">${styleCards.map(([value, label, hint]) => `<button type="button" class="garmin-style-card ${style === value ? 'is-selected' : ''}" data-style-value="${value}"><strong>${label}</strong><small>${hint}</small></button>`).join('')}</div></section>
        <section class="garmin-quick-step garmin-music-card" data-step="3"><div class="garmin-step-heading"><span>03</span><div><h2>Musique</h2><p>${audio.title ? 'Proposition locale intégrable au MP4' : 'ForgeAI choisira une piste compatible avec le rendu'}</p></div></div><div class="garmin-music-row"><div class="garmin-music-icon">♪</div><div class="garmin-music-main"><select data-action="local-music-select" aria-label="Musique du Reel"><option value="">${this._escape(audio.title || 'Choisir une musique')}</option>${musicOptions}</select><strong>${this._escape(audio.title || 'Aucune piste sélectionnée')}</strong><small>${this._escape(audio.artist || 'Musique locale vérifiée')}</small></div><button class="btn btn-secondary" data-action="audio-match">Autre proposition</button><button class="btn btn-link" data-action="music-alt">Catalogue</button></div>${audio.url ? `<audio class="garmin-audio-player" data-music-audio src="${this._escape(audio.url)}" preload="metadata" controls ${this.musicMuted ? 'muted' : ''}></audio><div class="garmin-excerpt"><span>Extrait ${Number(excerpt.start_time || 0).toFixed(1)}s → ${Number(excerpt.end_time || 0).toFixed(1)}s</span><button class="btn btn-link" data-action="audio-range">Modifier</button><small>${this._escape(excerpt.reason || 'Extrait choisi automatiquement')}</small></div>` : '<div class="garmin-empty-music">Sélectionnez une piste locale pour écouter et intégrer la musique.</div>'}</section>
        <section class="garmin-quick-step" data-step="4"><div class="garmin-step-heading"><span>04</span><div><h2>Légende</h2><p>Modifiez le texte avant publication.</p></div></div><label>Titre<input class="form-control" data-field="title" value="${this._escape(title)}"></label><label>Hashtags<textarea class="form-control" data-field="hashtags" rows="2">${this._escape(hashtags)}</textarea></label><small data-caption-status></small></section>
        <section class="garmin-quick-step garmin-output-step" data-step="5"><div class="garmin-step-heading"><span>05</span><div><h2>Aperçu et publication</h2><p>${ready ? 'Votre Reel est prêt.' : 'Générez un aperçu vidéo fidèle au rendu final.'}</p></div></div>${ready && this.videoUrl ? `<video controls playsinline preload="metadata" class="garmin-final-preview" src="${this._escape(this.videoUrl)}"></video>` : `<div class="garmin-mini-preview">${this.selected.map((id, i) => `<img src="/photos/${id}/file?size=medium" alt="Photo ${i + 1}">`).join('') || '<span>Sélectionnez au moins une photo</span>'}</div>`}<div class="garmin-output-actions"><button class="btn btn-secondary" data-action="preview">Aperçu</button><button class="btn btn-primary" data-action="publish" ${!this.selected.length || this.busy || this.generating ? 'disabled' : ''}>${this.busy ? 'Publication…' : 'Publier sur Instagram et Facebook'}</button></div>${this.generating ? '<p class="garmin-render-status">Génération du Reel en cours…</p>' : ''}</section>
      </main>`;
    const captionStep = this.element.querySelector('[data-step="4"]');
    if (captionStep) {
      captionStep.innerHTML = `<div class="garmin-step-heading"><span>04</span><div><h2>Légende</h2><p>Modifiez le texte avant publication.</p></div></div><div class="garmin-caption-fields"><label for="garmin-title-modern">Titre</label><input id="garmin-title-modern" class="form-control" data-field="title" value="${this._escape(title)}"><label for="garmin-hashtags-modern">Hashtags</label><textarea id="garmin-hashtags-modern" class="form-control" data-field="hashtags" rows="4">${this._escape(hashtags)}</textarea><small data-caption-status></small></div>`;
    }
    const outputStep = this.element.querySelector('[data-step="5"]');
    if (outputStep) {
      outputStep.innerHTML = `<div class="garmin-step-heading"><span>05</span><div><h2>Aperçu du Reel</h2><p>Vérifie ton montage avant de le publier.</p></div></div><button class="btn btn-primary garmin-preview-trigger" data-action="preview">Aperçu vidéo</button>`;
    }
    const musicSelect = this.element.querySelector('[data-action="local-music-select"]');
    if (musicSelect) musicSelect.outerHTML = this._audioProposalsHtml();
    this.element.querySelector('[data-action="music-alt"]')?.remove();
    this.element.querySelector('[data-action="audio-match"]')?.remove();
    if (this.previewOpen) this._appendPreviewModal();
    if (this.audioPlaybackError) this.element.querySelector('[data-audio-proposals]')?.insertAdjacentHTML('afterbegin', `<small class="garmin-audio-playback-error">${this._escape(this.audioPlaybackError)}</small>`);
    const metaAudio = design.ig_audio?.preview_link;
    if (metaAudio) this.element.querySelector('.garmin-music-card')?.insertAdjacentHTML('beforeend', `<div class="garmin-meta-audio-note"><audio controls preload="metadata" src="${this._escape(metaAudio)}"></audio><small>Aperçu Instagram uniquement · cette référence Meta ne sera pas intégrée au MP4 local.</small></div>`);
    this.element.querySelector('.garmin-music-card .garmin-audio-player')?.remove();
    this.element.querySelector('.garmin-music-card .garmin-meta-audio-note')?.remove();
    this._bind();
    this.element.querySelectorAll('[data-style-value]').forEach(button => button.addEventListener('click', async () => {
      const next = button.dataset.styleValue;
      const current = design.editorial_engine || {};
      try { this.publication = await updateStudioDraft(this.publicationId, { design: { editorial_engine: { ...current, style: next } } }); this.audioProposalExclude = []; this.render(); this._scheduleAudioProposals(); } catch (error) { this.error = error?.data?.detail || error?.message || 'Ambiance impossible à enregistrer.'; this.render(); }
    }));
    this.element.querySelectorAll('[data-audio-proposal]').forEach(button => button.addEventListener('click', () => this._selectAudioProposal(button.dataset.audioProposal)));
    this.element.querySelector('[data-action="audio-regenerate"]')?.addEventListener('click', () => { this._stopPreviewAudio(); this.audioProposalExclude = this.audioProposals.map(item => item.track_id); this._loadAudioProposals(); });
    this.element.querySelector('[data-action="music-alt"]')?.addEventListener('click', () => this._chooseMusic());
    return this.element;
  }

  _appendPreviewModal() {
    const modalContent = this.generating
      ? '<div class="garmin-preview-loading">Génération de l’aperçu vidéo…</div>'
      : (this.videoUrl ? `<video controls playsinline preload="metadata" class="garmin-modal-video" src="${this._escape(this.videoUrl)}"></video>` : '<div class="garmin-preview-loading">Préparation de l’aperçu…</div>');
    this.element.insertAdjacentHTML('beforeend', `<div class="garmin-preview-overlay" data-action="close-preview"><div class="garmin-preview-modal garmin-preview-modal--video" role="dialog" aria-modal="true" aria-label="Aperçu du Reel" data-preview-panel><button class="garmin-preview-close" data-action="close-preview" aria-label="Fermer">×</button><div class="garmin-preview-account">Aperçu du Reel</div>${modalContent}<div class="garmin-modal-caption"><strong>${this._escape(this.editedTitle || this.publication?.title || '')}</strong><span>${this._escape(this.editedHashtags || this.publication?.hashtags || '')}</span></div><button class="btn btn-success garmin-modal-publish" data-action="publish" ${this.busy || this.generating || !this.videoReady ? 'disabled' : ''}>${this.busy ? 'Publication…' : 'Publier sur Instagram et Facebook'}</button></div></div>`);
  }

  _photo(photo) {
    const id = Number(photo.id);
    return `<button type="button" draggable="true" class="cm-studio-photo-thumb ${this.selected.includes(id) ? 'cm-studio-photo-thumb--selected' : ''}" data-photo-id="${id}">
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
      this.audioProposalExclude = [];
      this._scheduleAudioProposals();
    }));
    this.element.querySelectorAll('[data-photo-id]').forEach(btn => {
      btn.addEventListener('dragstart', event => {
        event.dataTransfer?.setData('text/plain', btn.dataset.photoId);
        if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move';
      });
      btn.addEventListener('dragover', event => event.preventDefault());
      btn.addEventListener('drop', async event => {
        event.preventDefault();
        const from = this.selected.indexOf(Number(event.dataTransfer?.getData('text/plain')));
        const to = this.selected.indexOf(Number(btn.dataset.photoId));
        if (from < 0 || to < 0 || from === to) return;
        const [photoId] = this.selected.splice(from, 1);
        this.selected.splice(to, 0, photoId);
        this.render();
        await this._savePhotoOrder();
        this.audioProposalExclude = [];
        this._scheduleAudioProposals();
      });
    });
    this.element.querySelector('[data-action="publish"]')?.addEventListener('click', () => this._publish());
    this.element.querySelector('[data-action="regenerate-editorial"]')?.addEventListener('click', () => this._regenerateEditorial());
    const styleSelect = this.element.querySelector('[data-action="editorial-style"]');
    if (styleSelect) {
      styleSelect.value = this.publication?.design?.editorial_engine?.style || 'performance';
      styleSelect.addEventListener('change', async (event) => {
        const design = this.publication?.design && typeof this.publication.design === 'object' ? this.publication.design : {};
        const engine = design.editorial_engine && typeof design.editorial_engine === 'object' ? design.editorial_engine : {};
        this.publication = await updateStudioDraft(this.publicationId, { design: { editorial_engine: { ...engine, style: event.target.value } } });
        this.render();
      });
    }
    this.element.querySelector('[data-action="preview"]')?.addEventListener('click', () => {
      if (!this.videoReady && this.selected.length) { this.previewOpen = true; this._create(); }
      else { this.previewOpen = true; this.render(); }
    });
    this.element.querySelector('[data-action="music"]')?.addEventListener('click', () => this._chooseMusic());
    this.element.querySelector('[data-action="music-refresh"]')?.addEventListener('click', () => this._loadMusic(true));
    this.element.querySelector('[data-action="music-retry"]')?.addEventListener('click', () => this._loadMusic(false));
    this.element.querySelector('[data-action="more-photos"]')?.addEventListener('click', async () => { this.photosLimit += 20; this.photos = await getSuggestedPhotos(this.publicationId, this.photosLimit); this.render(); });
    this.element.querySelector('[data-action="music-select"]')?.addEventListener('change', event => this._selectMusic(Number(event.target.value)));
    this.element.querySelector('[data-action="local-music-select"]')?.addEventListener('change', event => this._selectLocalMusic(event.target.value));
    this.element.querySelector('[data-action="audio-match"]')?.addEventListener('click', () => this._applyAudioMatch());
    this.element.querySelector('[data-action="audio-range"]')?.addEventListener('click', () => this._editAudioRange());
    this.element.querySelector('[data-action="music-mute"]')?.addEventListener('click', event => {
      const audio = this.element.querySelector('[data-music-audio]');
      if (!audio) return;
      audio.muted = !audio.muted;
      this.musicMuted = audio.muted;
      event.currentTarget.textContent = audio.muted ? '🔇' : '🔊';
    });
    const musicAudio = this.element.querySelector('[data-music-audio]');
    if (musicAudio) musicAudio.addEventListener('loadedmetadata', () => {
      const start = Number(musicAudio.dataset.startTimeMs || (this.publication?.design?.audio?.audio_match?.start_time || 0) * 1000) / 1000;
      if (start > 0 && Number.isFinite(start) && start < musicAudio.duration) musicAudio.currentTime = start;
    }, { once: true });
    const publishedVideo = this.element.querySelector('video');
    const publishedAudio = this.element.querySelector('[data-music-audio]');
    if (publishedVideo && publishedAudio) {
      publishedVideo.addEventListener('play', () => { const p = publishedAudio.play(); if (p && p.catch) p.catch(() => {}); });
      publishedVideo.addEventListener('pause', () => publishedAudio.pause());
      publishedVideo.addEventListener('timeupdate', () => {
        if (publishedAudio.paused || !publishedAudio.duration || !Number.isFinite(Number(publishedAudio.duration))) return;
        const target = Number(publishedVideo.currentTime) || 0;
        if (Math.abs((Number(publishedAudio.currentTime) || 0) - target) > 0.25) publishedAudio.currentTime = target;
      });
    }
    this.element.querySelector('[data-field="title"]')?.addEventListener('input', event => this._queueCaptionSave('title', event.target.value));
    this.element.querySelector('[data-field="hashtags"]')?.addEventListener('input', event => this._queueCaptionSave('hashtags', event.target.value));
    this.element.querySelector('[data-action="edit-caption"]')?.addEventListener('click', () => this._editCaption());
    this.element.querySelectorAll('[data-action="close-preview"]').forEach(el => el.addEventListener('click', event => { if (event.target === el || event.target.dataset.action === 'close-preview') { this.previewOpen = false; this._stopPreviewAudio(); this.render(); } }));
    this.element.querySelector('[data-action="back-photos"]')?.addEventListener('click', () => {
      this._stopPreviewAudio();
      this.videoReady = false; this.error = null; this.previewOpen = false;
      this.publication = { ...(this.publication || {}), companion_video_status: 'none', companion_video_path: null };
      if (this.videoUrl?.startsWith('blob:')) URL.revokeObjectURL(this.videoUrl);
      this.videoUrl = null;
      this.render();
    });
    this.element.querySelector('[data-action="back"]')?.addEventListener('click', () => { this._stopPreviewAudio(); this.onBack?.(); });
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

  async _savePhotoOrder() {
    try {
      this.publication = await updateStudioDraft(this.publicationId, { photo_ids: this.selected });
    } catch (error) {
      this.error = error?.data?.detail || error?.message || 'Réorganisation impossible.';
      this.render();
    }
  }

  async _regenerateEditorial() {
    if (this.busy || this.generating) return;
    this.busy = true;
    this.error = null;
    this.render();
    try {
      await regeneratePublicationContent(this.publicationId);
      const updated = await getStudioDraft(this.publicationId);
      this.publication = updated;
      // La régénération concerne le contenu, jamais la sélection de photos.
      const carousel = updated?.design?.carousel;
      if (Array.isArray(carousel) && carousel.length) this.selected = [...carousel];
      else if (updated?.photo_id) this.selected = [updated.photo_id];
      this.editedTitle = updated?.title || this.editedTitle;
      this.editedHashtags = updated?.hashtags || this.editedHashtags;
      this.success = 'Nouvelle proposition générée.';
    } catch (error) {
      this.error = error?.data?.detail || error?.message || 'Régénération impossible.';
    } finally {
      this.busy = false;
      this.render();
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
    this.busy = true; this.generating = true; this.error = null;
    clearTimeout(this.musicSelectionTimer);
    this.render();
    try {
      // Ne renvoyer que titre/hashtags : les photo_ids sont déjà synchronisés.
      // Renvoyer photo_ids déclencherait un rechoix musical qui remplacerait
      // la piste sélectionnée par l'utilisateur juste avant la publication.
      this.publication = await updateStudioDraft(this.publicationId, {
        title: this.editedTitle,
        hashtags: this.editedHashtags,
      });
      await validateStudioDraft(this.publicationId, { confirm: true });
      await publishStudioDraftBoth(this.publicationId, { confirm: true });
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
      this.publication = await updateStudioDraft(this.publicationId, { design: { ig_audio: { source: 'instagram', status: 'selected', audio_id: String(item.audio_id), title: item.title || '', artist: item.display_artist || '', duration_in_ms: item.duration_in_ms, start_time_ms: item.start_time_ms || 0, preview_link: item.on_platform_audio_preview_link || item.download_url } } });
      this.musicItems = this.musicItems.map((candidate, candidateIndex) => candidateIndex === choice ? item : candidate);
      this.render();
    } catch (error) { this.error = error?.data?.detail || error?.message || 'Choix musical impossible.'; this.render(); }
  }

  async _loadMusic(refresh) {
    this.musicLoading = true;
    this.musicError = null;
    this.render();
    try {
      if (refresh) this.musicQueryIndex = (this.musicQueryIndex + 1) % this.musicQueries.length;
      const result = await searchStudioMusic(this.publicationId, this.musicQueries[this.musicQueryIndex]);
      this.musicItems = (result?.items || []).slice(0, 10);
    } catch (error) {
      this.musicError = error?.data?.detail || error?.message || 'Musiques Instagram indisponibles.';
    } finally {
      this.musicLoading = false;
      this.render();
    }
  }

  async _loadLocalMusic() {
    try {
      const result = await getLocalStudioMusic(this.publicationId);
      this.localMusicItems = result?.items || [];
      this.render();
    } catch (_) {
      // La création du Reel reste possible sans musique locale.
    }
  }

  _audioProposalsHtml() {
    const selected = this.publication?.design?.ig_audio?.audio_id || this.publication?.design?.audio?.track_id;
    if (this.audioProposalLoading) return '<div class="garmin-audio-proposals" data-audio-proposals><p>ForgeAI recherche 10 musiques adaptées à tes photos et à ton activité…</p></div>';
    if (this.audioProposalError) return `<div class="garmin-audio-proposals" data-audio-proposals><p>${this._escape(this.audioProposalError)}</p><button class="btn btn-link" data-action="audio-regenerate">Réessayer</button></div>`;
    if (!this.audioProposals.length) return '<div class="garmin-audio-proposals" data-audio-proposals><p>Aucune proposition Instagram disponible pour cette sélection.</p><small>Vérifiez la connexion Meta, les photos sélectionnées et les droits du catalogue.</small><button class="btn btn-link" data-action="audio-regenerate">Régénérer 10 musiques</button></div>';
    return `<div class="garmin-audio-proposals" data-audio-proposals><div class="garmin-audio-proposal-heading"><strong>Les ${this.audioProposals.length} musiques choisies pour ton Reel</strong><button class="btn btn-secondary" data-action="audio-regenerate">Régénérer 10 musiques</button></div>${this.audioProposals.map((item, index) => { const id = String(item.track_id); const isSelected = id === String(selected); const isPlaying = id === String(this.audioPlayingId); return `<button type="button" class="garmin-audio-proposal ${isSelected ? 'is-selected' : ''} ${isPlaying ? 'is-playing' : ''}" data-audio-proposal="${this._escape(id)}"><span class="garmin-audio-rank">${index + 1}</span><span class="garmin-audio-proposal-main"><strong>${this._escape(item.title)}</strong><small>${this._escape(item.artist || 'Artiste inconnu')} · extrait ${Number(item.excerpt?.start_time || 0).toFixed(1)}–${Number(item.excerpt?.end_time || 0).toFixed(1)}s</small><em>${this._escape(item.reason || 'Proposition Instagram')}${item.preview_link ? '' : ' · Aperçu indisponible sur Instagram'}</em></span><span>${isPlaying ? 'En lecture' : (isSelected ? 'Sélectionné' : 'Choisir')}</span></button>`; }).join('')}</div>`;
  }

  _scheduleAudioProposals() {
    clearTimeout(this.audioProposalTimer);
    const version = ++this.audioProposalVersion;
    this.audioProposalTimer = setTimeout(() => this._loadAudioProposals(version), 450);
  }

  async _loadAudioProposals(version = this.audioProposalVersion) {
    this._stopPreviewAudio();
    this.audioProposalLoading = true;
    this.audioProposalError = null;
    this.render();
    try {
      const result = await getStudioAudioProposals(this.publicationId, this.audioProposalExclude);
      if (version !== this.audioProposalVersion) return;
      this.audioProposals = (result?.items || []).map(item => ({ ...item, track_id: item.audio_id, artist: item.artist || item.display_artist || '', excerpt: { start_time: Number(item.start_time_ms || 0) / 1000, end_time: Number((item.start_time_ms || 0) + (item.duration_in_ms || 0)) / 1000, duration: Number(item.duration_in_ms || 0) / 1000 } }));
    } catch (error) {
      if (version !== this.audioProposalVersion) return;
      this.audioProposalError = error?.data?.detail || error?.message || 'Impossible de proposer des musiques.';
    } finally {
      if (version === this.audioProposalVersion) {
        this.audioProposalLoading = false;
        this.render();
      }
    }
  }

  async _selectAudioProposal(trackId) {
    const item = this.audioProposals.find(candidate => String(candidate.track_id) === String(trackId));
    if (!item) return;
    this._toggleProposalAudio(item);
    try {
      this.publication = await updateStudioDraft(this.publicationId, { design: { ig_audio: { source: 'instagram', status: 'available_on_meta', audio_id: String(item.audio_id), title: item.title || '', artist: item.artist || item.display_artist || '', duration_in_ms: item.duration_in_ms, start_time_ms: item.start_time_ms || 0, preview_link: item.preview_link || item.on_platform_audio_preview_link || null, recommendation_reason: item.reason || '' } } });
      this.render();
    } catch (error) {
      this.error = error?.data?.detail || error?.message || 'Sélection musicale impossible.';
      this.render();
    }
  }

  _stopPreviewAudio() {
    if (this.previewAudio) {
      this.previewAudio.pause();
      this.previewAudio.currentTime = 0;
      this.previewAudio.onended = null;
      this.previewAudio.onerror = null;
    }
    this.previewAudio = null;
    this.audioPlayingId = null;
  }

  _toggleProposalAudio(item) {
    const id = String(item.track_id);
    if (!item.preview_link) {
      this._stopPreviewAudio();
      this.audioPlaybackError = 'Aperçu indisponible sur Instagram.';
      this.render();
      return;
    }
    if (this.audioPlayingId === id && this.previewAudio) {
      if (this.previewAudio.paused) {
        this.previewAudio.play().catch(() => { this.audioPlaybackError = 'Lecture refusée par le navigateur.'; this.render(); });
      } else {
        this.previewAudio.pause();
        this.audioPlayingId = null;
        this.render();
      }
      return;
    }
    this._stopPreviewAudio();
    const AudioCtor = typeof window !== 'undefined' && window.Audio ? window.Audio : null;
    if (!AudioCtor) return;
    const audio = new AudioCtor(item.preview_link);
    this.previewAudio = audio;
    this.audioPlayingId = id;
    this.audioPlaybackError = null;
    audio.onended = () => { if (this.previewAudio === audio) { this.audioPlayingId = null; this.render(); } };
    audio.onerror = () => { if (this.previewAudio === audio) { this.audioPlayingId = null; this.audioPlaybackError = 'Aperçu indisponible sur Instagram.'; this.render(); } };
    audio.play().catch(() => { if (this.previewAudio === audio) { this.audioPlayingId = null; this.audioPlaybackError = 'Lecture refusée par le navigateur.'; this.render(); } });
    this.render();
  }

  async _selectLocalMusic(trackId) {
    const item = this.localMusicItems.find(candidate => candidate.track_id === trackId);
    if (!item) return;
    try {
      this.publication = await updateStudioDraft(this.publicationId, {
        design: { audio: { source: 'library_local', track_id: item.track_id, track: item.track_id, title: item.title, artist: item.artist, url: item.url, duration: item.duration, license: item.license, license_name: item.license_name, license_url: item.license_url, attribution: item.attribution, enabled: true, audio_status: 'selected', embedded: false } },
      });
      this.render();
    } catch (error) {
      this.error = error?.data?.detail || error?.message || 'Sélection de la piste impossible.';
      this.render();
    }
  }

  async _applyAudioMatch() {
    try {
      const result = await getStudioAudioMatch(this.publicationId);
      const item = result?.item;
      if (!item?.track_id) return;
      const maxDuration = Number(item.analysis?.duration || item.duration || 0);
      const suggested = item.excerpt || {};
      const start = window.prompt(`Début de l'extrait (0 à ${maxDuration.toFixed(1)} s)`, String(suggested.start_time || 0));
      if (start === null) return;
      const end = window.prompt(`Fin de l'extrait (supérieure à ${start} et inférieure à ${maxDuration.toFixed(1)} s)`, String(suggested.end_time || Math.min(maxDuration, 12)));
      if (end === null) return;
      const startValue = Number(start);
      const endValue = Number(end);
      if (!Number.isFinite(startValue) || !Number.isFinite(endValue) || startValue < 0 || endValue <= startValue || (maxDuration > 0 && endValue > maxDuration)) {
        this.error = 'Les limites de l’extrait sont invalides.';
        this.render();
        return;
      }
      this.publication = await updateStudioDraft(this.publicationId, { design: { audio: { track_id: item.track_id, track: item.track_id, title: item.title, artist: item.artist, url: item.url, duration: item.duration, license: item.license, audio_match: { ...suggested, start_time: startValue, end_time: endValue, duration: endValue - startValue, reason: 'Extrait validé dans le Quick Reel' }, enabled: true } } });
      this.render();
    } catch (error) {
      this.error = error?.data?.detail || error?.message || 'Proposition audio indisponible.';
      this.render();
    }
  }

  async _editAudioRange() {
    const current = this.publication?.design?.audio?.audio_match || {};
    const max = Number(this.publication?.design?.audio?.duration || 0);
    const start = Number(window.prompt('Début de l’extrait (secondes)', String(current.start_time || 0)));
    const end = Number(window.prompt('Fin de l’extrait (secondes)', String(current.end_time || Math.min(max || 12, 12))));
    if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end <= start || (max > 0 && end > max)) {
      this.error = 'Les limites de l’extrait sont invalides.';
      this.render();
      return;
    }
    try {
      this.publication = await updateStudioDraft(this.publicationId, { design: { audio: { audio_match: { ...current, start_time: start, end_time: end, duration: end - start, reason: 'Extrait modifié manuellement' } } } });
      this.render();
    } catch (error) {
      this.error = error?.data?.detail || error?.message || 'Modification de l’extrait impossible.';
      this.render();
    }
  }

  async _selectMusic(index) {
    const item = this.musicItems[index];
    if (!item?.audio_id) return;
    // Annuler l'analyse musicale planifiée : elle ne doit pas remplacer
    // le choix manuel de l'utilisateur.
    clearTimeout(this.musicSelectionTimer);
    try {
      this.publication = await updateStudioDraft(this.publicationId, { design: { ig_audio: { source: 'instagram', status: 'selected', audio_id: String(item.audio_id), title: item.title || '', artist: item.display_artist || '', duration_in_ms: item.duration_in_ms, start_time_ms: item.start_time_ms || 0, preview_link: item.on_platform_audio_preview_link || item.download_url } } });
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
