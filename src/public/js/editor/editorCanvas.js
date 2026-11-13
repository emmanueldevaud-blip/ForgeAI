/**
 * Rendu Canvas 2D de l'éditeur graphique.
 *
 * Dessine le design (fond, images, textes, stickers) à l'échelle d'affichage,
 * l'overlay de sélection (cadre + poignées) et produit l'export bitmap.
 */

import { handlePoint, rotateHandlePoint, toGlobal, hitTest } from './editorGeometry.js?v=1';
import { filterCss } from './editorState.js?v=1';

const HANDLE_SCREEN = 9; // taille écran des poignées (px)
const HIT_RADIUS = 12; // rayon d'attraction des poignées (px écran)

export class EditorCanvas {
  constructor({ state, onSelect = null }) {
    this.state = state;
    this.onSelect = onSelect;
    this.container = null;
    this.canvas = null;
    this.ctx = null;
    this._mctx = null; // contexte de mesure texte
    this._measureCanvas = null;
    this.images = new Map(); // src -> HTMLImageElement
    this.imageErrors = new Set();
    this.scale = 1;
    this.offsetX = 0;
    this.offsetY = 0;
    this.overlayMode = 'select'; // 'select' | 'crop'
    this._ro = null;
    this._renderQueued = false;
  }

  mount(container) {
    this.container = container;
    this.canvas = document.createElement('canvas');
    this.canvas.className = 'ed-canvas';
    this.canvas.setAttribute('data-editor-canvas', '1');
    container.appendChild(this.canvas);
    this.ctx = this.canvas.getContext('2d');
    this._measureCanvas = document.createElement('canvas');
    this._mctx = this._measureCanvas.getContext('2d');
    if (typeof ResizeObserver !== 'undefined') {
      this._ro = new ResizeObserver(() => this.requestRender());
      this._ro.observe(container);
    }
    this.requestRender();
  }

  destroy() {
    if (this._ro) this._ro.disconnect();
    if (this.canvas && this.canvas.parentNode) this.canvas.parentNode.removeChild(this.canvas);
    this.canvas = null;
    this.ctx = null;
  }

  /** Précharge les images nécessaires au design puis rend. */
  async ensureImages() {
    const d = this.state.design;
    const srcs = new Set();
    for (const el of d.elements) {
      if (el.type === 'image' && el.src) srcs.add(el.src);
    }
    const jobs = [];
    for (const src of srcs) {
      if (this.images.has(src) || this.imageErrors.has(src)) continue;
      jobs.push(
        new Promise((resolve) => {
          const img = new Image();
          img.onload = () => {
            this.images.set(src, img);
            resolve();
          };
          img.onerror = () => {
            this.imageErrors.add(src);
            resolve();
          };
          img.src = src;
        })
      );
    }
    if (jobs.length) await Promise.all(jobs);
    this.requestRender();
  }

  requestRender() {
    if (this._renderQueued) return;
    this._renderQueued = true;
    requestAnimationFrame(() => {
      this._renderQueued = false;
      this.render();
    });
  }

  render() {
    if (!this.canvas || !this.ctx) return;
    const rect = this.container.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const cw = Math.max(1, rect.width);
    const ch = Math.max(1, rect.height);
    this.canvas.width = Math.round(cw * dpr);
    this.canvas.height = Math.round(ch * dpr);
    this.canvas.style.width = `${cw}px`;
    this.canvas.style.height = `${ch}px`;
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this._draw(this.ctx, cw, ch, { overlay: true });
  }

  _fit(viewW, viewH) {
    const d = this.state.design;
    const scale = Math.min(viewW / d.format.width, viewH / d.format.height) * 0.94;
    return {
      scale,
      ox: (viewW - d.format.width * scale) / 2,
      oy: (viewH - d.format.height * scale) / 2,
    };
  }

  _draw(ctx, viewW, viewH, opts = {}) {
    const d = this.state.design;
    const { scale, ox, oy } = this._fit(viewW, viewH);
    this.scale = scale;
    this.offsetX = ox;
    this.offsetY = oy;

    ctx.clearRect(0, 0, viewW, viewH);
    ctx.save();
    ctx.translate(ox, oy);
    ctx.scale(scale, scale);

    // Fond du design
    ctx.fillStyle = d.background?.color || '#111111';
    ctx.fillRect(0, 0, d.format.width, d.format.height);

    for (const el of d.elements) {
      this._drawElement(ctx, el);
    }

    if (opts.overlay && this.state.selectedId) {
      this._drawOverlay(ctx, scale);
    }

    ctx.restore();
  }

  _drawElement(ctx, el) {
    ctx.save();
    ctx.globalAlpha = el.opacity ?? 1;
    ctx.translate(el.x, el.y);
    if (el.rotation) ctx.rotate((el.rotation * Math.PI) / 180);

    if (el.type === 'image') this._drawImage(ctx, el);
    else if (el.type === 'text') this._drawText(ctx, el);
    else if (el.type === 'sticker') this._drawSticker(ctx, el);

    ctx.restore();
  }

  _drawImage(ctx, el) {
    const img = this.images.get(el.src);
    if (!img || !img.naturalWidth) {
      ctx.fillStyle = 'rgba(255,255,255,0.08)';
      ctx.fillRect(-el.w / 2, -el.h / 2, el.w, el.h);
      ctx.strokeStyle = 'rgba(255,255,255,0.25)';
      ctx.strokeRect(-el.w / 2, -el.h / 2, el.w, el.h);
      return;
    }
    const crop = el.crop || { x: 0, y: 0, w: 1, h: 1 };
    const sx = crop.x * img.naturalWidth;
    const sy = crop.y * img.naturalHeight;
    const sw = Math.max(1, crop.w * img.naturalWidth);
    const sh = Math.max(1, crop.h * img.naturalHeight);

    ctx.save();
    try {
      ctx.filter = filterCss(el.filter);
    } catch (_e) {
      /* ctx.filter non supporté */
    }
    if (this.overlayMode === 'crop' && this.state.selectedId === el.id) {
      // En mode recadrage : image complète visible
      ctx.drawImage(img, -el.w / 2, -el.h / 2, el.w, el.h);
    } else {
      ctx.drawImage(img, sx, sy, sw, sh, -el.w / 2, -el.h / 2, el.w, el.h);
    }
    ctx.restore();
  }

  textMetrics(el) {
    const font = `${el.italic ? 'italic ' : ''}${el.bold ? 'bold ' : ''}${el.size || 32}px ${el.font || 'Arial'}`;
    const lineH = (el.size || 32) * 1.25;
    const ctx = this._mctx;
    ctx.font = font;
    const maxWidth = Math.max(20, el.w);
    const paragraphs = String(el.text ?? '').split('\n');
    const lines = [];
    for (const para of paragraphs) {
      const words = para.split(/\s+/).filter((w) => w.length);
      if (!words.length) {
        lines.push('');
        continue;
      }
      let current = words[0];
      for (let i = 1; i < words.length; i += 1) {
        const test = `${current} ${words[i]}`;
        if (ctx.measureText(test).width <= maxWidth) current = test;
        else {
          lines.push(current);
          current = words[i];
        }
      }
      lines.push(current);
    }
    return { font, lineH, lines, height: Math.max(lineH, lines.length * lineH) };
  }

  _drawText(ctx, el) {
    const m = this.textMetrics(el);
    ctx.font = m.font;
    ctx.fillStyle = el.color || '#ffffff';
    ctx.textBaseline = 'top';
    ctx.textAlign = el.align || 'left';
    if (el.shadow) {
      ctx.shadowColor = 'rgba(0,0,0,0.55)';
      ctx.shadowBlur = Math.max(2, (el.size || 32) * 0.12);
      ctx.shadowOffsetY = Math.max(1, (el.size || 32) * 0.05);
    }
    const left = -el.w / 2;
    const top = -m.height / 2;
    let x = left;
    if (el.align === 'center') x = 0;
    else if (el.align === 'right') x = left + el.w;
    m.lines.forEach((line, i) => {
      ctx.fillText(line, x, top + i * m.lineH, el.w);
    });
    ctx.shadowColor = 'transparent';
    ctx.shadowBlur = 0;
    ctx.shadowOffsetY = 0;
  }

  _drawSticker(ctx, el) {
    const color = el.color || '#ff5722';
    if (el.sticker === 'circle') {
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(0, 0, Math.min(el.w, el.h) / 2, 0, Math.PI * 2);
      ctx.fill();
    } else if (el.sticker === 'rect') {
      ctx.fillStyle = color;
      ctx.fillRect(-el.w / 2, -el.h / 2, el.w, el.h);
    } else if (el.sticker === 'line') {
      ctx.strokeStyle = color;
      ctx.lineWidth = Math.max(4, el.h / 4);
      ctx.lineCap = 'round';
      ctx.beginPath();
      ctx.moveTo(-el.w / 2, 0);
      ctx.lineTo(el.w / 2, 0);
      ctx.stroke();
    } else {
      ctx.font = `${Math.min(el.w, el.h)}px "Apple Color Emoji","Segoe UI Emoji","Noto Color Emoji",sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(el.sticker || '⭐', 0, 0);
    }
  }

  _textHeight(el) {
    if (el.type !== 'text') return el.h;
    return this.textMetrics(el).height;
  }

  _drawOverlay(ctx, scale) {
    const el = this.state.selected;
    if (!el) return;
    const th = this._textHeight(el);
    const inv = 1 / scale;

    ctx.save();
    ctx.translate(el.x, el.y);
    if (el.rotation) ctx.rotate((el.rotation * Math.PI) / 180);

    if (this.overlayMode === 'crop' && el.type === 'image') {
      this._drawCropOverlay(ctx, el, inv);
      ctx.restore();
      return;
    }

    // Cadre de sélection
    ctx.strokeStyle = '#4f8cff';
    ctx.lineWidth = Math.max(1, 2 * inv);
    ctx.strokeRect(-el.w / 2, -th / 2, el.w, th);

    // Poignées de redimensionnement
    const hs = HANDLE_SCREEN * inv;
    ctx.fillStyle = '#ffffff';
    ctx.strokeStyle = '#1f2937';
    ctx.lineWidth = Math.max(1, 1.2 * inv);
    for (const h of ['nw', 'ne', 'se', 'sw', 'n', 's', 'e', 'w']) {
      const p = handlePoint({ ...el, h: th }, h, th);
      // position en coordonnées locales de l'élément (repère déjà appliqué)
      const local = this._globalToOverlayLocal(p, el, th, h);
      ctx.fillRect(local.x - hs / 2, local.y - hs / 2, hs, hs);
      ctx.strokeRect(local.x - hs / 2, local.y - hs / 2, hs, hs);
    }

    // Poignée de rotation
    if (el.type !== 'text' || true) {
      const top = -th / 2;
      const stem = -Math.max(18 * inv, el.w * 0.06);
      ctx.beginPath();
      ctx.moveTo(0, top);
      ctx.lineTo(0, top + (stem - top) * 0); // tige courte
      const stickEnd = top - Math.max(14 * inv, 10 * inv);
      ctx.moveTo(0, top);
      ctx.lineTo(0, stickEnd);
      ctx.strokeStyle = '#4f8cff';
      ctx.lineWidth = Math.max(1, 1.5 * inv);
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(0, stickEnd, hs * 0.7, 0, Math.PI * 2);
      ctx.fillStyle = '#4f8cff';
      ctx.fill();
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = Math.max(1, 1 * inv);
      ctx.stroke();
    }

    ctx.restore();
  }

  /** Convertit un point global en coordonnées locales de l'overlay (déjà en rotation). */
  _globalToOverlayLocal(_point, el, _th, handle) {
    // L'overlay est dessiné dans le repère local de l'élément : les handles
    // sont exprimés directement en coordonnées locales.
    const hw = el.w / 2;
    const hh = _th / 2;
    const map = {
      nw: [-hw, -hh],
      n: [0, -hh],
      ne: [hw, -hh],
      e: [hw, 0],
      se: [hw, hh],
      s: [0, hh],
      sw: [-hw, hh],
      w: [-hw, 0],
    };
    const [x, y] = map[handle];
    return { x, y };
  }

  _drawCropOverlay(ctx, el, inv) {
    const crop = el.crop || { x: 0, y: 0, w: 1, h: 1 };
    const x0 = (crop.x - 0.5) * el.w;
    const y0 = (crop.y - 0.5) * el.h;
    const cw = crop.w * el.w;
    const ch = crop.h * el.h;

    // Assombrir l'extérieur du rect de crop
    ctx.save();
    ctx.fillStyle = 'rgba(0,0,0,0.5)';
    ctx.fillRect(-el.w / 2, -el.h / 2, el.w, el.h);
    ctx.clearRect(x0, y0, cw, ch);
    // Recoller l'image nette dans la zone (le clear laisse le fond transp.)
    const img = this.images.get(el.src);
    if (img && img.naturalWidth) {
      const sx = crop.x * img.naturalWidth;
      const sy = crop.y * img.naturalHeight;
      const sw = Math.max(1, crop.w * img.naturalWidth);
      const sh = Math.max(1, crop.h * img.naturalHeight);
      ctx.drawImage(img, sx, sy, sw, sh, x0, y0, cw, ch);
    }
    ctx.restore();

    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = Math.max(1, 1.5 * inv);
    ctx.strokeRect(x0, y0, cw, ch);

    const hs = HANDLE_SCREEN * inv;
    ctx.fillStyle = '#4f8cff';
    for (const [cx, cy] of [
      [x0, y0],
      [x0 + cw, y0],
      [x0, y0 + ch],
      [x0 + cw, y0 + ch],
    ]) {
      ctx.fillRect(cx - hs / 2, cy - hs / 2, hs, hs);
    }
  }

  // ------------------------------------------------------------------
  // Coordonnées
  // ------------------------------------------------------------------

  screenToDesign(clientX, clientY) {
    const rect = this.canvas.getBoundingClientRect();
    const sx = clientX - rect.left;
    const sy = clientY - rect.top;
    return {
      x: (sx - this.offsetX) / this.scale,
      y: (sy - this.offsetY) / this.scale,
    };
  }

  // ------------------------------------------------------------------
  // Hit testing
  // ------------------------------------------------------------------

  elementAt(px, py) {
    const els = this.state.design.elements;
    for (let i = els.length - 1; i >= 0; i -= 1) {
      const el = els[i];
      const th = this._textHeight(el);
      if (hitTest(px, py, el, th)) return el;
    }
    return null;
  }

  /** Retourne 'nw'|…|'rotate'|'crop-nw'|…|null sous le point design. */
  handleAt(px, py) {
    const el = this.state.selected;
    if (!el) return null;
    const th = this._textHeight(el);
    const r = HIT_RADIUS / this.scale;

    if (this.overlayMode === 'crop' && el.type === 'image') {
      const crop = el.crop || { x: 0, y: 0, w: 1, h: 1 };
      const x0 = (crop.x - 0.5) * el.w;
      const y0 = (crop.y - 0.5) * el.h;
      const cw = crop.w * el.w;
      const ch = crop.h * el.h;
      const corners = [
        ['crop-nw', x0, y0],
        ['crop-ne', x0 + cw, y0],
        ['crop-sw', x0, y0 + ch],
        ['crop-se', x0 + cw, y0 + ch],
      ];
      for (const [name, lx, ly] of corners) {
        const g = toGlobal(lx, ly, el);
        if (Math.hypot(px - g.x, py - g.y) <= r * 1.4) return name;
      }
      return null;
    }

    const rot = rotateHandlePoint({ ...el, h: th }, th);
    if (Math.hypot(px - rot.x, py - rot.y) <= r * 1.4) return 'rotate';

    for (const h of ['nw', 'ne', 'se', 'sw', 'n', 's', 'e', 'w']) {
      const p = handlePoint({ ...el, h: th }, h, th);
      if (Math.hypot(px - p.x, py - p.y) <= r * 1.4) return h;
    }
    return null;
  }

  // ------------------------------------------------------------------
  // Export
  // ------------------------------------------------------------------

  async exportBlob(type = 'image/jpeg', quality = 0.92) {
    const d = this.state.design;
    const off = document.createElement('canvas');
    off.width = d.format.width;
    off.height = d.format.height;
    const ctx = off.getContext('2d');
    if (type === 'image/jpeg') {
      ctx.fillStyle = d.background?.color || '#ffffff';
      ctx.fillRect(0, 0, off.width, off.height);
    }
    this._drawExportScene(ctx);
    return new Promise((resolve) => {
      off.toBlob((blob) => resolve(blob), type, quality);
    });
  }

  _drawExportScene(ctx) {
    const d = this.state.design;
    const prevMode = this.overlayMode;
    const prevSel = this.state.selectedId;
    this.overlayMode = 'select';
    this.state.selectedId = null;
    try {
      for (const el of d.elements) {
        this._drawElement(ctx, el);
      }
    } finally {
      this.overlayMode = prevMode;
      this.state.selectedId = prevSel;
    }
  }
}
