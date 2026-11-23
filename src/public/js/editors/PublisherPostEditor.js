/**
 * PublisherPostEditor — Éditeur simple pour Publication (photo unique / carousel)
 * Recadrage, réorganisation, filtres basiques
 */

import { publisherStore } from '../stores/publisherStore.js';
import { coverCrop } from '../editor/editorGeometry.js?v=1';

export class PublisherPostEditor {
  constructor(options = {}) {
    this.onSave = options.onSave || (() => {});
    this.onBack = options.onBack || (() => {});
    this.element = null;
    this.mediaElements = new Map();
    this.selectedMediaId = null;
    this.cropMode = false;
    this.cropData = { x: 0, y: 0, w: 1, h: 1 };
    this._unsubscribeStore = null;
  }

  mount(host) {
    this.element = document.createElement('div');
    this.element.className = 'publisher-post-editor';
    this.element.innerHTML = this._render();
    host.appendChild(this.element);

    this._bindEvents();
    this._subscribeStore();
  }

  _subscribeStore() {
    this._unsubscribeStore = publisherStore.subscribe(state => {
      this._renderMediaGrid();
    });
  }

  _render() {
    const media = publisherStore.draft.media;
    return `
      <div class="ppe-header">
        <h2>Ajuster vos médias</h2>
        <p class="ppe-hint">${media.length} média${media.length > 1 ? 's' : ''} sélectionné${media.length > 1 ? 's' : ''} • Glissez pour réorganiser • Cliquez pour recadrer</p>
      </div>

      <div class="ppe-grid" data-grid>
        ${media.map((m, i) => this._renderMediaItem(m, i)).join('')}
      </div>
      <div class="ppe-empty" data-empty ${media.length ? 'hidden' : ''}>Aucun média sélectionné.</div>

      ${media.length > 0 ? `
        <div class="ppe-crop-panel" data-crop-panel hidden>
          <div class="ppe-crop-header">
            <h3>Recadrage</h3>
            <button type="button" class="ppe-btn ppe-btn-ghost" data-action="close-crop">✕</button>
          </div>
          <div class="ppe-crop-canvas" data-crop-canvas></div>
          <div class="ppe-crop-presets">
            <button type="button" class="ppe-crop-preset" data-preset="1:1">1:1</button>
            <button type="button" class="ppe-crop-preset" data-preset="4:5">4:5</button>
            <button type="button" class="ppe-crop-preset" data-preset="9:16">9:16</button>
            <button type="button" class="ppe-crop-preset" data-preset="16:9">16:9</button>
            <button type="button" class="ppe-crop-preset" data-preset="free">Libre</button>
          </div>
          <div class="ppe-crop-actions">
            <button type="button" class="ppe-btn ppe-btn-secondary" data-action="reset-crop">Réinitialiser</button>
            <button type="button" class="ppe-btn ppe-btn-primary" data-action="apply-crop">Appliquer</button>
          </div>
        </div>
      ` : ''}
    `;
  }

  _renderMediaItem(media, index) {
    return `
      <div class="ppe-media-item ${this.selectedMediaId === media.id ? 'selected' : ''}" data-media-id="${media.id}" draggable="true">
        <div class="ppe-media-preview" style="background-image: url('${media.thumbnail_url}')">
          ${media.type === 'video' ? '<span class="ppe-video-badge">▶</span>' : ''}
          <span class="ppe-order">${index + 1}</span>
        </div>
        <div class="ppe-media-actions">
          <button type="button" class="ppe-btn ppe-btn-sm" data-action="crop" title="Recadrer">✂️</button>
          <button type="button" class="ppe-btn ppe-btn-sm" data-action="remove" title="Supprimer">🗑</button>
        </div>
      </div>
    `;
  }

  _bindEvents() {
    // Grid - sélection, drag-drop, actions
    const grid = this.element.querySelector('[data-grid]');
    grid.addEventListener('click', (e) => {
      const item = e.target.closest('[data-media-id]');
      if (!item) return;

      const mediaId = item.dataset.mediaId;

      if (e.target.closest('[data-action="crop"]')) {
        e.stopPropagation();
        this._openCrop(mediaId);
        return;
      }
      if (e.target.closest('[data-action="remove"]')) {
        e.stopPropagation();
        publisherStore.removeMedia(mediaId);
        return;
      }

      this._selectMedia(mediaId);
    });

    // Drag-drop réorganisation
    grid.addEventListener('dragstart', (e) => {
      const item = e.target.closest('[data-media-id]');
      if (item) {
        item.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
      }
    });
    grid.addEventListener('dragend', (e) => {
      const item = e.target.closest('[data-media-id]');
      if (item) item.classList.remove('dragging');
    });
    grid.addEventListener('dragover', (e) => {
      e.preventDefault();
      const after = this._getDragAfterElement(grid, e.clientY);
      const draggable = document.querySelector('.dragging');
      if (after == null) grid.appendChild(draggable);
      else grid.insertBefore(draggable, after);
    });
    grid.addEventListener('drop', (e) => {
      e.preventDefault();
      this._reorderFromDOM();
    });

    // Crop panel (absent si la grille est montée sans média)
    this.element.querySelector('[data-action="close-crop"]')?.addEventListener('click', () => this._closeCrop());
    this.element.querySelector('[data-action="reset-crop"]')?.addEventListener('click', () => this._resetCrop());
    this.element.querySelector('[data-action="apply-crop"]')?.addEventListener('click', () => this._applyCrop());
    this.element.querySelectorAll('[data-preset]').forEach(btn => {
      btn.addEventListener('click', () => this._setCropPreset(btn.dataset.preset));
    });
  }

  _getDragAfterElement(container, y) {
    const elements = [...container.querySelectorAll('.ppe-media-item:not(.dragging)')];
    return elements.reduce((closest, child) => {
      const box = child.getBoundingClientRect();
      const offset = y - box.top - box.height / 2;
      if (offset < 0 && offset > closest.offset) return { offset, element: child };
      return closest;
    }, { offset: Number.NEGATIVE_INFINITY }).element;
  }

  _reorderFromDOM() {
    const grid = this.element.querySelector('[data-grid]');
    const newOrder = [...grid.querySelectorAll('[data-media-id]')].map(el => String(el.dataset.mediaId));
    const media = publisherStore.draft.media;
    const reordered = newOrder.map(id => media.find(m => String(m.id) === id)).filter(Boolean);
    media.forEach(m => { if (!newOrder.includes(String(m.id))) reordered.push(m); });
    reordered.forEach((m, i) => { m.order = i; });
    publisherStore.draft.media = reordered;
    publisherStore._notify();
  }

  _selectMedia(mediaId) {
    const id = String(mediaId);
    this.selectedMediaId = id;
    this.element.querySelectorAll('[data-media-id]').forEach(el => {
      el.classList.toggle('selected', String(el.dataset.mediaId) === id);
    });
  }

  _findMedia(mediaId) {
    const id = String(mediaId);
    return publisherStore.draft.media.find(m => String(m.id) === id);
  }

  _openCrop(mediaId) {
    this.cropMode = true;
    this.selectedMediaId = String(mediaId);
    const media = this._findMedia(mediaId);
    if (!media) return;

    this.cropData = { ...media.crop };
    const panel = this.element.querySelector('[data-crop-panel]');
    if (!panel) return;
    panel.hidden = false;
    this._renderCropCanvas(media);
  }

  _closeCrop() {
    this.cropMode = false;
    const panel = this.element.querySelector('[data-crop-panel]');
    if (panel) panel.hidden = true;
  }

  _resetCrop() {
    this.cropData = { x: 0, y: 0, w: 1, h: 1 };
    this._renderCropCanvas(this._findMedia(this.selectedMediaId));
  }

  _applyCrop() {
    const media = this._findMedia(this.selectedMediaId);
    if (media) {
      media.crop = { ...this.cropData };
      publisherStore._notify();
    }
    this._closeCrop();
  }

  _setCropPreset(preset) {
    const ratios = { '1:1': 1, '4:5': 0.8, '9:16': 0.5625, '16:9': 1.777 };
    if (preset === 'free') {
      this.cropData = { x: 0, y: 0, w: 1, h: 1 };
    } else {
      const ratio = ratios[preset];
      this.cropData = coverCrop(1, 1, ratio, 1);
    }
    this._renderCropCanvas(this._findMedia(this.selectedMediaId));
  }

  _renderCropCanvas(media) {
    const canvasHost = this.element.querySelector('[data-crop-canvas]');
    if (!media || !canvasHost) return;

    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('2d');
      const maxW = 600, maxH = 600;
      let w = img.width, h = img.height;
      if (w > maxW || h > maxH) {
        const scale = Math.min(maxW / w, maxH / h);
        w *= scale; h *= scale;
      }
      canvas.width = w; canvas.height = h;
      ctx.drawImage(img, 0, 0, w, h);

      // Dessiner le cadre de recadrage
      const crop = this.cropData;
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 2;
      ctx.setLineDash([8, 4]);
      ctx.strokeRect(crop.x * w, crop.y * h, crop.w * w, crop.h * h);

      canvasHost.innerHTML = '';
      canvasHost.appendChild(canvas);
    };
    img.src = media.url;
  }

  _renderMediaGrid() {
    const grid = this.element.querySelector('[data-grid]');
    if (!grid) return;
    const media = publisherStore.draft.media;
    grid.innerHTML = media.map((m, i) => this._renderMediaItem(m, i)).join('');
    const empty = this.element.querySelector('[data-empty]');
    if (empty) empty.hidden = media.length > 0;
    if (media.length === 0) this._closeCrop();
    if (this.selectedMediaId && !media.some(m => String(m.id) === String(this.selectedMediaId))) {
      this.selectedMediaId = null;
    }
  }

  destroy() {
    if (this._unsubscribeStore) this._unsubscribeStore();
    if (this.element && this.element.parentNode) this.element.parentNode.removeChild(this.element);
  }

  _esc(text) {
    return String(text ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }
}

export function createPublisherPostEditor(options) {
  return new PublisherPostEditor(options);
}
