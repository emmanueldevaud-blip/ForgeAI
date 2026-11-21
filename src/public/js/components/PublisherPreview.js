/**
 * PublisherPreview — Aperçu unifié selon le format
 * Publication (feed), Reel (lecteur vidéo), Story (9:16 plein écran)
 */

import { publisherStore } from '../stores/publisherStore.js';
import { publisherDraftService } from '../services/publisherDraftService.js';

export class PublisherPreview {
  constructor(options = {}) {
    this.format = options.format || 'post';
    this.draft = options.draft || publisherStore.draft;
    this.onBack = options.onBack || (() => {});
    this.onPublish = options.onPublish || (() => {});
    this.element = null;
    this._unsubscribeStore = null;
  }

  mount(host) {
    this.element = document.createElement('div');
    this.element.className = `publisher-preview publisher-preview--${this.format}`;
    this.element.innerHTML = this._render();
    host.appendChild(this.element);

    this._bindEvents();
    this._subscribeStore();
  }

  _subscribeStore() {
    this._unsubscribeStore = publisherStore.subscribe(state => {
      this.draft = state.draft;
      this._updatePreview();
    });
  }

  _render() {
    switch (this.format) {
      case 'post':
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

    return `
      <div class="pp-post">
        <div class="pp-post-header">
          <div class="pp-post-user">
            <div class="pp-avatar"></div>
            <div class="pp-user-info">
              <strong>Votre compte</strong>
              <span>À l'instant</span>
            </div>
            <button type="button" class="pp-more">⋮</button>
          </div>

          <div class="pp-post-media">
            ${isCarousel ? `
              <div class="pp-carousel" data-carousel>
                ${media.map((m, i) => `
                  <div class="pp-carousel-slide ${i === 0 ? 'active' : ''}" style="background-image: url('${m.thumbnail_url}')">
                    ${m.type === 'video' ? '<span class="pp-video-badge">▶</span>' : ''}
                  </div>
                `).join('')}
              </div>
              <div class="pp-carousel-indicators">
                ${media.map((_, i) => `<span class="${i === 0 ? 'active' : ''}"></span>`).join('')}
              </div>
            ` : `
              <div class="pp-single-media" style="background-image: url('${media[0]?.thumbnail_url || ''}')">
                ${media[0]?.type === 'video' ? '<span class="pp-video-badge">▶</span>' : ''}
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

      <div class="pp-preview-footer">
        <button type="button" class="pp-btn pp-btn-secondary" data-action="back">Retour</button>
        <button type="button" class="pp-btn pp-btn-success" data-action="publish">Publier</button>
      </div>
    `;
  }

  _renderReel() {
    const media = this.draft.media;
    const firstMedia = media[0];
    const caption = this.draft.caption;

    return `
      <div class="pp-reel">
        <div class="pp-reel-header">
          <div class="pp-reel-user">
            <div class="pp-avatar"></div>
            <div class="pp-user-info">
              <strong>Votre compte</strong>
              <span>Reel · À l'instant</span>
            </div>
          </div>

          <div class="pp-reel-player" data-reel-player>
            ${firstMedia ? `
              <video class="pp-reel-video" playsinline muted loop preload="metadata"
                     style="background-image: url('${firstMedia.thumbnail_url}')">
                <source src="${firstMedia.url}" type="${firstMedia.type === 'video' ? 'video/mp4' : 'image/jpeg'}">
              </video>
            ` : '<div class="pp-reel-placeholder">Aucun média</div>'}
            <div class="pp-reel-overlay">
              <button class="pp-reel-play" data-action="play-pause">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21"/></svg>
              </button>
            </div>
            <div class="pp-reel-progress" data-progress><div class="pp-reel-progress-bar"></div></div>
          </div>

          <div class="pp-reel-sidebar">
            <div class="pp-reel-actions">
              <button class="pp-reel-action" aria-label="J'aime"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 0 1-7.78 0L12 5.67l-1.06 1.06a5.5 5.5 0 0 1-7.78 0 5.5 5.5 0 0 1 0 7.78L12 21l7.78-7.78a5.5 5.5 0 0 1 0-7.78z"/></svg></button>
              <button class="pp-reel-action" aria-label="Commenter"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg></button>
              <button class="pp-reel-action" aria-label="Partager"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg></button>
            </div>
            <div class="pp-reel-music">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>
              <span>Musique originale</span>
            </div>
          </div>
        </div>

        <div class="pp-reel-caption">
          ${caption.title ? `<strong>${this._esc(caption.title)}</strong>` : ''}
          ${caption.content ? `<span>${this._esc(caption.content)}</span>` : ''}
          ${caption.hashtags ? `<div class="pp-hashtags">${this._esc(caption.hashtags)}</div>` : ''}
        </div>

        <div class="pp-preview-footer">
          <button type="button" class="pp-btn pp-btn-secondary" data-action="back">Retour</button>
          <button type="button" class="pp-btn pp-btn-success" data-action="publish">Publier le Reel</button>
        </div>
      </div>
    `;
  }

  _renderStory() {
    const slides = this.draft.design?.slides || [];
    const designs = this.draft.design?.designDocuments || [];
    const media = this.draft.media;

    return `
      <div class="pp-story">
        <div class="pp-story-header">
          <button type="button" class="pp-btn pp-btn-back" data-action="back">✕</button>
          <span class="pp-story-title">Aperçu Story (${slides.length || media.length} slide${slides.length > 1 ? 's' : ''})</button>
          <span class="pp-story-nav">
            <button type="button" class="pp-nav-btn" data-nav="prev" disabled>‹</button>
            <span class="pp-slide-indicator">1 / ${slides.length || media.length}</span>
            <button type="button" class="pp-nav-btn" data-nav="next" ${(slides.length || media.length) <= 1 ? 'disabled' : ''} ›</button>
          </span>
        </div>

        <div class="pp-story-viewport" data-story-viewport>
          ${(slides.length || media.length) > 0 ? (slides.length > 0 ? slides.map((slide, i) => `
            <div class="pp-story-slide ${i === 0 ? 'active' : ''}" data-slide="${i}" style="background: ${designs[i]?.background?.color || '#000'}">
              ${designs[i]?.background?.type === 'photo' && media[i] ? `<img src="${media[i].thumbnail_url}" alt="Slide ${i+1}">` : ''}
              ${designs[i]?.elements?.map(el => this._renderStoryElement(el)).join('') || ''}
            </div>
          `).join('') : media.map((m, i) => `
            <div class="pp-story-slide ${i === 0 ? 'active' : ''}" data-slide="${i}">
              <img src="${m.thumbnail_url}" alt="Story ${i+1}">
            </div>
          `).join('')} ) : '<div class="pp-story-empty">Aucun contenu</div>'}
        </div>

        <div class="pp-story-footer">
          <div class="pp-story-progress">
            ${(slides.length || media.length) > 0 ? Array.from({ length: slides.length || media.length }, (_, i) => `<span class="${i === 0 ? 'active' : ''}"></span>`).join('') : ''}
          </div>
        </div>

        <div class="pp-preview-footer">
          <button type="button" class="pp-btn pp-btn-secondary" data-action="back">Retour</button>
          <button type="button" class="pp-btn pp-btn-success" data-action="publish">Publier les Stories</button>
        </div>
      </div>
    `;
  }

  _renderStoryElement(el) {
    if (el.type === 'text') {
      return `<div class="pp-story-text" style="left:${el.x}px;top:${el.y}px;font-size:${el.size}px;color:${el.color};font-weight:${el.bold?'bold':'normal'};text-align:${el.align};${el.shadow?'text-shadow:0 2px 4px rgba(0,0,0,0.5)':''}">${this._esc(el.text)}</div>`;
    }
    if (el.type === 'sticker') {
      return `<div class="pp-story-sticker" style="left:${el.x}px;top:${el.y}px;font-size:${el.size}px">${this._esc(el.text)}</div>`;
    }
    if (el.type === 'sport_stats') {
      return `<div class="pp-story-stats" style="left:${el.x}px;top:${el.y}px"><strong>${el.value} ${el.unit}</strong><br><small>${el.label}</small></div>`;
    }
    return '';
  }

  _bindEvents() {
    this.element.querySelector('[data-action="back"]').addEventListener('click', () => this.onBack());
    this.element.querySelector('[data-action="publish"]').addEventListener('click', () => this.onPublish());

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
  }

  _updatePreview() {
    // Re-render seulement les parties dynamiques
    if (this.format === 'post') this._updatePostPreview();
    else if (this.format === 'reel') this._updateReelPreview();
    else if (this.format === 'story') this._updateStoryPreview();
  }

  _updatePostPreview() {
    // Mise à jour légende
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

  _updateReelPreview() {
    this._updatePostPreview(); // Même logique pour la légende
  }

  _updateStoryPreview() {
    // Les slides sont générées depuis le design, pas besoin de mise à jour temps réel pour l'instant
  }

  _esc(text) {
    return String(text ?? '').replace(/[&<>"']/g, c => ({ '&': '&', '<': '<', '>': '>', '"': '"', "'": ''' }[c]));
  }

  destroy() {
    if (this._unsubscribeStore) this._unsubscribeStore();
    if (this.element && this.element.parentNode) this.element.parentNode.removeChild(this.element);
  }
}

export function createPublisherPreview(options) {
  return new PublisherPreview(options);
}