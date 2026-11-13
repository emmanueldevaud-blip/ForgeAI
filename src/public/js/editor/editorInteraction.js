/**
 * Interaction pointer de l'éditeur : sélection, déplacement,
 * redimensionnement (8 poignées), rotation, recadrage.
 */

import {
  solveResize,
  solveCrop,
  angleToPoint,
  clampRotation,
  toLocal,
} from './editorGeometry.js?v=1';

const MIN_SIZE = 24;

export class EditorInteraction {
  constructor({ canvas, state, onEditText = null, onGesture = null }) {
    this.canvas = canvas;
    this.state = state;
    this.onEditText = onEditText;
    this.onGesture = onGesture; // début/fin de geste (pour rafraîchir les panneaux)
    this._mode = null;
    this._handle = null;
    this._start = null;
    this._startEl = null;
    this._startAngle = 0;
    this._pointerId = null;
    this._bound = [];
  }

  attach(target = this.canvas.canvas) {
    this.target = target;
    this._on('pointerdown', (e) => this._down(e));
    this._on('pointermove', (e) => this._move(e));
    this._on('pointerup', (e) => this._up(e));
    this._on('pointercancel', (e) => this._up(e));
    this._on('dblclick', (e) => this._dbl(e));
  }

  detach() {
    for (const [type, fn, el] of this._bound) {
      el.removeEventListener(type, fn);
    }
    this._bound = [];
  }

  _on(type, fn) {
    this.target.addEventListener(type, fn);
    this._bound.push([type, fn, this.target]);
  }

  _pos(e) {
    return this.canvas.screenToDesign(e.clientX, e.clientY);
  }

  _down(e) {
    if (e.button !== undefined && e.button !== 0) return;
    const p = this._pos(e);
    const selected = this.state.selected;

    const handle = this.canvas.handleAt(p.x, p.y);
    if (handle && selected) {
      this.state.beginTransaction();
      this._start = p;
      this._startEl = { ...selected };
      this._startAngle = angleToPoint(selected, p.x, p.y);
      if (handle.startsWith('crop')) {
        this._mode = 'crop';
        this._handle = handle.replace('crop-', '');
      } else if (handle === 'rotate') {
        this._mode = 'rotate';
        this._handle = null;
      } else {
        this._mode = 'resize';
        this._handle = handle;
      }
      this._pointerId = e.pointerId;
      if (this.target.setPointerCapture) {
        try {
          this.target.setPointerCapture(e.pointerId);
        } catch (_err) {
          /* ignore */
        }
      }
      e.preventDefault();
      return;
    }

    const hit = this.canvas.elementAt(p.x, p.y);
    if (hit) {
      if (this.state.selectedId !== hit.id) this.state.select(hit.id);
      this.state.beginTransaction();
      this._mode = 'drag';
      this._start = p;
      this._startEl = { ...hit };
      this._pointerId = e.pointerId;
      if (this.target.setPointerCapture) {
        try {
          this.target.setPointerCapture(e.pointerId);
        } catch (_err) {
          /* ignore */
        }
      }
      e.preventDefault();
    } else {
      if (this.state.selectedId) this.state.select(null);
    }
  }

  _move(e) {
    if (!this._mode) return;
    const p = this._pos(e);
    const el = this.state.selected;
    if (!el) {
      this._end();
      return;
    }

    if (this._mode === 'drag') {
      const dx = p.x - this._start.x;
      const dy = p.y - this._start.y;
      this.state.updateElementLive(el.id, {
        x: this._startEl.x + dx,
        y: this._startEl.y + dy,
      });
    } else if (this._mode === 'resize') {
      const th =
        el.type === 'text' ? this.canvas.textMetrics(el).height : undefined;
      const next = solveResize(this._startEl, this._handle, p.x, p.y, {
        minSize: MIN_SIZE,
        aspect: el.type === 'image',
        textHeight: th,
      });
      this.state.updateElementLive(el.id, next);
    } else if (this._mode === 'rotate') {
      const current = angleToPoint(this._startEl, p.x, p.y);
      let deg = this._startEl.rotation + (current - this._startAngle);
      deg = clampRotation(deg, e.shiftKey ? 15 : 0);
      this.state.updateElementLive(el.id, { rotation: deg });
    } else if (this._mode === 'crop') {
      const local = toLocal(p.x, p.y, this._startEl);
      const crop = solveCrop(
        this._startEl.crop,
        this._handle,
        local.x,
        local.y,
        this._startEl.w,
        this._startEl.h
      );
      this.state.updateElementLive(el.id, { crop });
    }

    this.canvas.requestRender();
  }

  _up(e) {
    if (this._pointerId !== null && this.target.releasePointerCapture) {
      try {
        this.target.releasePointerCapture(this._pointerId);
      } catch (_err) {
        /* ignore */
      }
    }
    this._end();
    if (e) e.preventDefault();
  }

  _end() {
    if (this._mode) {
      this.state.commitTransaction();
      if (this.onGesture) this.onGesture(this._mode);
    }
    this._mode = null;
    this._handle = null;
    this._start = null;
    this._startEl = null;
    this._pointerId = null;
    this.canvas.requestRender();
  }

  _dbl(e) {
    const p = this._pos(e);
    const hit = this.canvas.elementAt(p.x, p.y);
    if (hit && hit.type === 'text' && this.onEditText) {
      this.state.select(hit.id);
      this.onEditText(hit);
      e.preventDefault();
    }
  }

  /** Active/désactive le mode recadrage sur l'image sélectionnée. */
  setCropMode(enabled) {
    const el = this.state.selected;
    if (enabled && (!el || el.type !== 'image')) return false;
    this.canvas.overlayMode = enabled ? 'crop' : 'select';
    this.canvas.requestRender();
    return true;
  }
}
