/**
 * PublisherPreview — Aperçu unifié selon le format
 * Publication (feed), Reel (lecteur vidéo), Story (9:16 plein écran)
 */

import { publisherStore } from '../stores/publisherStore.js';
import { publisherDraftService } from '../services/publisherDraftService.js?v=3';
import { resolveDraftMusic } from './PublisherMusicStep.js?v=4';

export class PublisherPreview {
  constructor(options = {}) {
    this.format = options.format || 'post';
    this.draft = options.draft || publisherStore.draft;
    this.onBack = options.onBack || (() => {});
    this.element = null;
    this._unsubscribeStore = null;
    this._mediaIds = null; // ids des médias rendus pour détection de changement
    this._visualSignature = null;
    this.carouselIndex = 0;
  }

  mount(host) {
    this.element = document.createElement('div');
    this.element.className = `publisher-preview publisher-preview--${this.format}`;
    this.element.innerHTML = this._render();
    host.appendChild(this.element);

    this._bindEvents();
    this._subscribeStore();
    this._visualSignature = this._currentVisualSignature();
  }

  _subscribeStore() {
    this._unsubscribeStore = publisherStore.subscribe(state => {
      const prevDraft = this.draft;
      this.draft = state.draft;
      this._updatePreview(prevDraft);
    });
  }

  _render() {
    switch (this.format) {
      case 'post':
      case 'carousel':
        return this._renderPost();
      case 'reel':
        return this._renderReel();
      case 'story':
        return this._renderStory();
      default:
        return '<div class="pp-empty">Format non supporté</div>';
    }
  }

  _renderPost() {
    const media = this.draft.media;
    const isCarousel = media.length > 1;
    const caption = this.draft.caption;
    const accountName = this.draft.caption.accountUsername || 'Votre compte';

    return `
      <div class="pp-post">
        <div class="pp-post-header">
          <div class="pp-post-user">
            <div class="pp-avatar"></div>
            <div class="pp-user-info">
              <strong>${this._esc(accountName)}</strong>
              <span>À l'instant</span>
            </div>
            <button type="button" class="pp-more">⋮</button>
          </div>

          <div class="pp-post-media">
            ${isCarousel ? `
              <div class="pp-carousel" data-carousel>
                ${media.map((m, i) => `
                  <div class="pp-carousel-slide ${i === this.carouselIndex ? 'active' : ''}" style="background-image: url('${m.url || m.thumbnail_url || ''}')" aria-label="Photo ${i + 1} sur ${media.length}">
                    ${m.type === 'video' ? '<span class="pp-video-badge">▶</span>' : ''}
                  </div>
                `).join('')}
                <button type="button" class="pp-carousel-nav pp-carousel-nav--prev" data-carousel-nav="-1" aria-label="Photo précédente" ${this.carouselIndex === 0 ? 'disabled' : ''}>‹</button>
                <button type="button" class="pp-carousel-nav pp-carousel-nav--next" data-carousel-nav="1" aria-label="Photo suivante" ${this.carouselIndex >= media.length - 1 ? 'disabled' : ''}>›</button>
                <span class="pp-carousel-count" data-carousel-count>${this.carouselIndex + 1}/${media.length}</span>
              </div>
              <div class="pp-carousel-indicators">
                ${media.map((_, i) => `<button type="button" class="${i === this.carouselIndex ? 'active' : ''}" data-carousel-index="${i}" aria-label="Afficher la photo ${i + 1}"></button>`).join('')}
              </div>
            ` : `
              <div class="pp-single-media" style="background-image: url('${media[0]?.url || media[0]?.thumbnail_url || ''}')">
                ${media[0]?.type === 'video' ? '<span class="pp-video-badge">▶</span>' : ''}
                ${media[0] ? '' : '<span class="pp-media-placeholder">Aucune photo sélectionnée</span>'}
              </div>
            `}
          </div>

          <div class="pp-post-actions">
            <button class="pp-action" aria-label="J'aime"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 0 1-7.78 0L12 5.67l-1.06 1.06a5.5 5.5 0 0 1-7.78 0 5.5 5.5 0 0 1 0 7.78L12 21l7.78-7.78a5.5 5.5 0 0 1 0-7.78z"/></svg></button>
            <button class="pp-action" aria-label="Commenter"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg></button>
            <button class="pp-action" aria-label="Partager"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg></button>
            <button class="pp-action pp-save" aria-label="Enregistrer"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/></svg></button>
          </div>

          <div class="pp-post-caption">
            ${this.draft.caption.title ? `<strong>${this._esc(this.draft.caption.title)}</strong>` : ''}
            ${this.draft.caption.content ? `<span>${this._esc(this.draft.caption.content)}</span>` : ''}
            ${this.draft.caption.hashtags ? `<div class="pp-hashtags">${this._esc(this.draft.caption.hashtags)}</div>` : ''}
          </div>

          <div class="pp-post-comments">
            <span>Afficher tous les commentaires</span>
          </div>
        </div>
      </div>
    `;
  }

  _renderReel() {
    const media = this.draft.media;
    const firstMedia = media[0];
    const caption = this.draft.caption;
    const accountName = this.draft.caption.accountUsername || 'Votre compte';
    const igAudio = this.draft.design?.ig_audio || {};
    const musicName = this.draft.music?.title || this.draft.music?.track?.title
      || igAudio.title || igAudio.name || this.draft.music?.trackId;

    return `
      <div class="pp-reel">
        <div class="pp-reel-header">
          <div class="pp-reel-user">
            <div class="pp-avatar"></div>
            <div class="pp-user-info">
              <strong>${this._esc(accountName)}</strong>
              <span>Reel · À l'instant</span>
            </div>
          </div>

          <div class="pp-reel-player" data-reel-player>
            ${firstMedia ? `
              ${firstMedia.type === 'video'
                ? `<video class="pp-reel-video" playsinline muted loop preload="metadata" poster="${firstMedia.thumbnail_url || ''}"><source src="${firstMedia.url}" type="video/mp4"></video>`
                : `<img class="pp-reel-poster" src="${firstMedia.url || firstMedia.thumbnail_url || ''}" alt="Aperçu du Reel">`}
            ` : '<div class="pp-reel-placeholder">Aucun média</div>'}
            <div class="pp-reel-design" aria-label="Texte et stickers du Reel">
              ${(this.draft.design?.elements || []).map(el => this._renderStudioElement(el)).join('')}
            </div>
            ${firstMedia?.type === 'video' ? '<button type="button" class="pp-reel-play" data-action="play-pause" aria-label="Lire la vidéo">▶</button>' : ''}
            <div class="pp-reel-caption">
              ${caption.title ? `<strong>${this._esc(caption.title)}</strong>` : ''}
              ${caption.content ? `<span>${this._esc(caption.content)}</span>` : ''}
              ${caption.hashtags ? `<div class="pp-hashtags">${this._esc(caption.hashtags)}</div>` : ''}
            </div>
          </div>

          <div class="pp-reel-sidebar">
            <div class="pp-reel-actions">
              <button class="pp-reel-action" aria-label="J'aime"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 0 1-7.78 0L12 5.67l-1.06 1.06a5.5 5.5 0 0 1-7.78 0 5.5 5.5 0 0 1 0 7.78L12 21l7.78-7.78a5.5 5.5 0 0 1 0-7.78z"/></svg></button>
              <button class="pp-reel-action" aria-label="Commenter"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg></button>
              <button class="pp-reel-action" aria-label="Partager"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg></button>
            </div>
            <div class="pp-reel-music">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>
              <span>${musicName ? this._esc(musicName) : 'Musique originale'}</span>
            </div>
          </div>
        </div>

      </div>
    `;
  }

  _renderStory() {
    const slides = this.draft.design?.slides || [];
    const designs = this.draft.design?.designDocuments || [];
    const media = this.draft.media;
    const accountName = this.draft.caption.accountUsername || 'Votre compte';
    const music = resolveDraftMusic(this.draft);

    return `
      <div class="pp-story">
        <div class="pp-story-progress" data-story-progress>
          ${(slides.length || media.length) > 0 ? Array.from({ length: slides.length || media.length }, (_, i) => `<span class="${i === 0 ? 'active' : ''}"></span>`).join('') : ''}
        </div>
        <div class="pp-story-header">
          <div class="pp-story-user">
            <div class="pp-avatar"></div>
            <div class="pp-user-info"><strong>${this._esc(accountName)}</strong><span>À l’instant</span></div>
          </div>
          <button type="button" class="pp-story-close" data-action="back" aria-label="Fermer l’aperçu">×</button>
          <span class="pp-story-nav">
            <button type="button" class="pp-nav-btn" data-nav="prev" disabled>‹</button>
            <span class="pp-slide-indicator">1 / ${slides.length || media.length}</span>
            <button type="button" class="pp-nav-btn" data-nav="next" ${(slides.length || media.length) <= 1 ? 'disabled' : ''} ›</button>
          </span>
        </div>
        ${music ? `
        <div class="pp-story-music">
          <span class="pp-story-music-track">♫ ${this._esc(music.title || 'Piste sans titre')}${music.artist ? ` · ${this._esc(music.artist)}` : ''}</span>
          <span class="pp-story-music-status">Sélectionnée · non intégrable à la publication actuelle</span>
          <span class="pp-story-music-note">Brouillon créatif uniquement · la musique ne sera pas publiée avec cette Story.</span>
        </div>` : ''}

        <div class="pp-story-viewport" data-story-viewport>
          ${(slides.length || media.length) > 0 ? (slides.length > 0 ? slides.map((slide, i) => {
            const design = designs[i] || {};
            const publishedPhotoId = slide.published_photo_id;
            const photoId = publishedPhotoId || design.background?.photo_id || design.carousel?.[0];
            const normalizePhotoId = value => {
              const normalized = String(value ?? '').replace(/^photo_/, '');
              return /^\d+$/.test(normalized) ? normalized : '';
            };
            const normalizedId = normalizePhotoId(photoId);
            const matchingMedia = media.find(item => normalizedId && normalizePhotoId(item.id) === normalizedId)
              || media[slide.photo_indices?.[0] ?? i]
              || media[i];
            const mediaPhotoId = normalizePhotoId(matchingMedia?.id);
            // StoryEditorView resolves photo ids through this endpoint. Reuse that
            // path so the final preview does not depend on a stale picker URL.
            const imageUrl = normalizedId || mediaPhotoId
              ? `/photos/${encodeURIComponent(normalizedId || mediaPhotoId)}/file?size=medium`
              : (matchingMedia?.url || matchingMedia?.thumbnail_url || '');
            return `
            <div class="pp-story-slide ${i === 0 ? 'active' : ''}" data-slide="${i}" style="background: ${designs[i]?.background?.color || '#000'}">
              ${imageUrl ? `<img src="${this._esc(imageUrl)}" alt="Story ${i + 1}">` : ''}
              ${publishedPhotoId ? '' : (design.elements?.map(el => this._renderStoryElement(el)).join('') || '')}
            </div>
          `;
          }).join('') : media.map((m, i) => `
            <div class="pp-story-slide ${i === 0 ? 'active' : ''}" data-slide="${i}">
              <img src="${m.url || m.thumbnail_url || ''}" alt="Story ${i+1}">
            </div>
          `).join('')) : '<div class="pp-story-empty">Aucun contenu</div>'}
        </div>

        <div class="pp-story-reply"><span>Répondre à ${this._esc(accountName)}…</span><span>♡</span></div>
      </div>
    `;
  }

  _renderStoryElement(el) {
    // Dans EditorCanvas, x/y sont le centre de l'élément et w/h sa taille.
    // Garder cette convention pour que l'aperçu corresponde à l'export réel.
    const x = (Number(el.x) / 1080) * 100;
    const y = (Number(el.y) / 1920) * 100;
    const width = Math.max(0, (Number(el.w) / 1080) * 100);
    const opacity = Number(el.opacity ?? 1);
    const transform = `translate(-50%, -50%)${el.rotation ? ` rotate(${Number(el.rotation)}deg)` : ''}`;
    const position = `left:${x}%;top:${y}%;transform:${transform};opacity:${opacity};`;
    if (el.type === 'text') {
      return `<div class="pp-story-text" style="${position}width:${width}%;font-size:${(Number(el.size) / 1080) * 100}cqw;color:${this._esc(el.color || '#fff')};font-weight:${el.bold ? 'bold' : 'normal'};font-style:${el.italic ? 'italic' : 'normal'};text-align:${this._esc(el.align || 'left')};${el.shadow ? 'text-shadow:0 2px 4px rgba(0,0,0,0.5);' : ''}">${this._esc(el.text)}</div>`;
    }
    if (el.type === 'sticker') {
      return `<div class="pp-story-sticker" style="${position}font-size:${(Math.min(Number(el.w) || Number(el.size) || 80, Number(el.h) || Number(el.size) || 80) / 1080) * 100}cqw">${this._esc(el.text || el.sticker || '⭐')}</div>`;
    }
    if (el.type === 'sport_stats') {
      return `<div class="pp-story-stats" style="${position}width:${width || 80}%;font-size:${(Number(el.size || 32) / 1080) * 100}cqw;color:${this._esc(el.color || '#fff')}"><strong>${this._esc(el.value)} ${this._esc(el.unit)}</strong><br><small>${this._esc(el.label)}</small></div>`;
    }
    return '';
  }

  _renderStudioElement(el) {
    if (!['text', 'sticker', 'sport_stats'].includes(el.type)) return '';
    const width = Number(this.draft.design?.format?.width) || 1080;
    const height = Number(this.draft.design?.format?.height) || 1920;
    const x = (Number(el.x) / width) * 100;
    const y = (Number(el.y) / height) * 100;
    const style = `left:${x}%;top:${y}%;opacity:${Number(el.opacity ?? 1)};transform:translate(-50%,-50%)${el.rotation ? ` rotate(${Number(el.rotation)}deg)` : ''};`;
    if (el.type === 'text') {
      const size = (Number(el.size) / width) * 100;
      return `<div class="pp-reel-design-text" style="${style}font-size:${size}cqw;color:${this._esc(el.color || '#fff')};font-weight:${el.bold ? 'bold' : 'normal'};font-style:${el.italic ? 'italic' : 'normal'};text-align:${this._esc(el.align || 'center')};">${this._esc(el.text)}</div>`;
    }
    if (el.type === 'sticker') {
      const sticker = el.sticker || '⭐';
      const size = (Math.min(Number(el.w) || Number(el.size) || 80, Number(el.h) || Number(el.size) || 80) / width) * 100;
      return `<div class="pp-reel-design-sticker" style="${style}font-size:${size}cqw">${this._esc(sticker)}</div>`;
    }
    const size = (Number(el.size) / width) * 100;
    return `<div class="pp-reel-design-text" style="${style}font-size:${size}cqw;color:${this._esc(el.color || '#fff')};font-weight:bold;text-align:${this._esc(el.align || 'center')};">${this._esc(el.value || '')} ${this._esc(el.unit || '')}<br><small>${this._esc(el.label || '')}</small></div>`;
  }

  _bindEvents() {
    const backBtn = this.element.querySelector('[data-action="back"]');
    if (backBtn) backBtn.addEventListener('click', () => this.onBack());

    if (this.format === 'reel') {
      const video = this.element.querySelector('.pp-reel-video');
      const playButton = this.element.querySelector('[data-action="play-pause"]');
      playButton?.addEventListener('click', async () => {
        if (!video) return;
        if (video.paused) {
          try { await video.play(); } catch (_error) { return; }
          playButton.textContent = 'Ⅱ';
          playButton.setAttribute('aria-label', 'Mettre en pause');
        } else {
          video.pause();
          playButton.textContent = '▶';
          playButton.setAttribute('aria-label', 'Lire la vidéo');
        }
      });
      video?.addEventListener('ended', () => {
        if (playButton) { playButton.textContent = '▶'; playButton.setAttribute('aria-label', 'Lire la vidéo'); }
      });
    }

    // Story navigation
    if (this.format === 'story') {
      let currentSlide = 0;
      const slides = this.element.querySelectorAll('.pp-story-slide');
      const indicator = this.element.querySelector('.pp-slide-indicator');
      const prevBtn = this.element.querySelector('[data-nav="prev"]');
      const nextBtn = this.element.querySelector('[data-nav="next"]');

      const updateSlide = (idx) => {
        currentSlide = Math.max(0, Math.min(idx, slides.length - 1));
        slides.forEach((s, i) => s.classList.toggle('active', i === currentSlide));
        if (indicator) indicator.textContent = `${currentSlide + 1} / ${slides.length}`;
        if (prevBtn) prevBtn.disabled = currentSlide === 0;
        if (nextBtn) nextBtn.disabled = currentSlide === slides.length - 1;
        this.element.querySelectorAll('[data-story-progress] span').forEach((segment, i) => {
          segment.classList.toggle('active', i <= currentSlide);
        });
      };

      prevBtn?.addEventListener('click', () => updateSlide(currentSlide - 1));
      nextBtn?.addEventListener('click', () => updateSlide(currentSlide + 1));

      // Swipe support
      let touchStartX = 0;
      const viewport = this.element.querySelector('[data-story-viewport]');
      viewport?.addEventListener('touchstart', (e) => { touchStartX = e.touches[0].clientX; });
      viewport?.addEventListener('touchend', (e) => {
        const dx = e.changedTouches[0].clientX - touchStartX;
        if (Math.abs(dx) > 50) updateSlide(currentSlide + (dx > 0 ? -1 : 1));
      });
    }

    if (this.draft.media?.length > 1) {
      this.element.querySelectorAll('[data-carousel-nav]').forEach((button) => {
        button.addEventListener('click', () => this._setCarouselIndex(this.carouselIndex + Number(button.dataset.carouselNav)));
      });
      this.element.querySelectorAll('[data-carousel-index]').forEach((button) => {
        button.addEventListener('click', () => this._setCarouselIndex(Number(button.dataset.carouselIndex)));
      });
    }
  }

  _setCarouselIndex(index) {
    const slides = this.element?.querySelectorAll?.('.pp-carousel-slide') || [];
    if (!slides.length) return;
    this.carouselIndex = Math.max(0, Math.min(index, slides.length - 1));
    slides.forEach((slide, i) => slide.classList.toggle('active', i === this.carouselIndex));
    this.element.querySelectorAll('[data-carousel-index]').forEach((dot, i) => dot.classList.toggle('active', i === this.carouselIndex));
    this.element.querySelectorAll('[data-carousel-nav]').forEach((button) => {
      const direction = Number(button.dataset.carouselNav);
      button.disabled = direction < 0 ? this.carouselIndex === 0 : this.carouselIndex === slides.length - 1;
    });
    const count = this.element.querySelector('[data-carousel-count]');
    if (count) count.textContent = `${this.carouselIndex + 1}/${slides.length}`;
  }

  _updatePreview(prevDraft) {
    const signature = this._currentVisualSignature();
    // Les textes, stickers, crops et la musique font partie du visuel publié.
    // Sinon, on met à jour seulement le caption pour éviter de perdre le focus
    // sur les champs de saisie pendant l'édition.
    if (signature !== this._visualSignature) {
      this.carouselIndex = 0;
      this.element.innerHTML = this._render();
      this._bindEvents();
      this._mediaIds = this._currentMediaIds();
      this._visualSignature = signature;
    }
    this._updateCaption();
  }

  _currentVisualSignature() {
    return JSON.stringify({ media: this.draft.media || [], design: this.draft.design || {}, music: this.draft.music || {} });
  }

  _mediaChanged(prevDraft) {
    if (!prevDraft) return true;
    const prevIds = (prevDraft.media || []).map(m => String(m.id)).join(',');
    const currIds = (this.draft.media || []).map(m => String(m.id)).join(',');
    return prevIds !== currIds;
  }

  _currentMediaIds() {
    return (this.draft.media || []).map(m => String(m.id)).sort().join(',');
  }

  _updateCaption() {
    if (this.format === 'post' || this.format === 'carousel') this._updatePostCaption();
    else if (this.format === 'reel') this._updateReelCaption();
    else if (this.format === 'story') this._updateStoryCaption();
  }

  _updatePostCaption() {
    const captionEl = this.element.querySelector('.pp-post-caption');
    if (captionEl) {
      const c = this.draft.caption;
      captionEl.innerHTML = `
        ${c.title ? `<strong>${this._esc(c.title)}</strong>` : ''}
        ${c.content ? `<span>${this._esc(c.content)}</span>` : ''}
        ${c.hashtags ? `<div class="pp-hashtags">${this._esc(c.hashtags)}</div>` : ''}
      `;
    }
  }

  _updateReelCaption() {
    const captionEl = this.element.querySelector('.pp-reel-caption');
    if (!captionEl) return;
    const caption = this.draft.caption;
    captionEl.innerHTML = `
      ${caption.title ? `<strong>${this._esc(caption.title)}</strong>` : ''}
      ${caption.content ? `<span>${this._esc(caption.content)}</span>` : ''}
      ${caption.hashtags ? `<div class="pp-hashtags">${this._esc(caption.hashtags)}</div>` : ''}
    `;
  }

  _updateStoryCaption() {
    // Les slides sont générées depuis le design, pas besoin de mise à jour temps réel pour l'instant
  }

  _esc(text) {
    return String(text ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  destroy() {
    if (this._unsubscribeStore) this._unsubscribeStore();
    if (this.element && this.element.parentNode) this.element.parentNode.removeChild(this.element);
  }
}

export function createPublisherPreview(options) {
  return new PublisherPreview(options);
}
