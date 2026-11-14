/**
 * Timeline multipiste V2 (J1) — pistes/clips, curseur temporel, zoom,
 * déplacement, redimensionnement, découpe. Indépendante du moteur de rendu
 * vidéo futur ; consomme le design V2 (design.timeline).
 */

const TRACK_LABELS = {
  video: 'Vidéo',
  image: 'Images',
  text: 'Textes',
  sticker: 'Stickers',
  audio: 'Audio',
};

export class EditorTimeline {
  constructor({ root, state, onSelectClip = null, onSelectTrack = null }) {
    this.root = root;
    this.state = state;
    this.onSelectClip = onSelectClip;
    this.onSelectTrack = onSelectTrack;
    this._dragging = null;
    this._cursor = 0;
    this._zoom = 1;
    this._el = null;
    this._selectedClipId = null;
  }

  mount(host) {
    this._el = document.createElement('div');
    this._el.className = 'ed-timeline';
    this._el.innerHTML = `
      <div class="ed-timeline-toolbar">
        <span class="ed-timeline-title">Timeline</span>
        <button type="button" class="ed-timeline-btn" data-ed-tl-zoom-out title="Zoom arrière">−</button>
        <span class="ed-timeline-zoom" data-ed-tl-zoom>100%</span>
        <button type="button" class="ed-timeline-btn" data-ed-tl-zoom-in title="Zoom avant">+</button>
        <span class="ed-timeline-fps" data-ed-tl-fps></span>
        <button type="button" class="ed-timeline-btn ed-timeline-cut" data-ed-tl-cut title="Découper la piste">✂</button>
      </div>
      <div class="ed-timeline-scroll" data-ed-tl-scroll>
        <div class="ed-timeline-rows" data-ed-tl-rows></div>
        <div class="ed-timeline-playhead" data-ed-tl-playhead><div class="ed-timeline-cursor" data-ed-tl-cursor></div></div>
      </div>
    `;
    host.appendChild(this._el);
    this._bind();
    this._cursor = 0;
    this._zoom = 1;
    const cursor = this._el.querySelector('[data-ed-tl-cursor]');
    if (cursor) cursor.style.left = '0px';
    this.requestRender();
    return this;
  }

  destroy() {
    this._dragging = null;
    if (this._tlMove) { window.removeEventListener('pointermove', this._tlMove); window.removeEventListener('pointerup', this._tlMoveUp); window.removeEventListener('pointercancel', () => this._dragging = null); }
    if (this._tlResize) { window.removeEventListener('pointermove', this._tlResize); window.removeEventListener('pointerup', this._tlResizeUp); window.removeEventListener('pointercancel', () => this._dragging = null); }
    if (this._tlCursor) { window.removeEventListener('pointermove', this._tlCursor); window.removeEventListener('pointerup', this._tlCursorUp); window.removeEventListener('pointercancel', () => this._dragging = null); }
    this._tlMove = this._tlMoveUp = this._tlMoveCancel = null;
    this._tlResize = this._tlResizeUp = this._tlResizeCancel = null;
    this._tlCursor = this._tlCursorUp = this._tlCursorCancel = null;
    if (this._el && this._el.parentNode) this._el.parentNode.removeChild(this._el);
    this._el = null;
  }

  requestRender() {
    if (this._dragging) return;
    if (!this._el) return;
    const timeline = this.state && this.state.design ? this.state.design.timeline : null;
    const tracks = (timeline && Array.isArray(timeline.tracks) ? timeline.tracks : []).filter(
      (t) => t && t.id
    );
    const rows = this._el.querySelector('[data-ed-tl-rows]');
    rows.innerHTML = '';
    for (const tr of tracks) {
      if (tr.hidden) continue;
      const row = document.createElement('div');
      row.className = 'ed-timeline-row';
      row.setAttribute('data-timeline-track-id', tr.id);
      const gutter = document.createElement('div');
      gutter.className = 'ed-timeline-row-gutter';
      const label = document.createElement('span');
      label.className = 'ed-timeline-track-label';
      label.textContent = TRACK_LABELS[tr.type] || tr.type;
      gutter.appendChild(label);
      const trackBtns = document.createElement('span');
      trackBtns.className = 'ed-timeline-track-btns';
      const hideBtn = document.createElement('button');
      hideBtn.type = 'button';
      hideBtn.className = 'ed-timeline-mini-btn';
      hideBtn.setAttribute('data-ed-tl-hide', tr.id);
      hideBtn.textContent = '👁';
      hideBtn.title = 'Masquer la piste';
      const lockBtn = document.createElement('button');
      lockBtn.type = 'button';
      lockBtn.className = 'ed-timeline-mini-btn';
      lockBtn.setAttribute('data-ed-tl-lock', tr.id);
      lockBtn.textContent = '🔒';
      lockBtn.title = 'Verrouiller la piste';
      trackBtns.appendChild(hideBtn);
      trackBtns.appendChild(lockBtn);
      gutter.appendChild(trackBtns);
      row.appendChild(gutter);
      const clipsHost = document.createElement('div');
      clipsHost.className = 'ed-timeline-clips';
      for (const clip of tr.clips || []) {
        if (!clip || !clip.id) continue;
        const clipEl = document.createElement('div');
        clipEl.className = 'ed-timeline-clip';
        clipEl.setAttribute('data-clip-id', clip.id);
        clipEl.style.left = `${(Number(clip.start) || 0) * this._zoom}px`;
        clipEl.style.width = `${Math.max(0, Number(clip.duration) || 0) * this._zoom}px`;
        const handle = document.createElement('div');
        handle.className = 'ed-timeline-resize';
        handle.setAttribute('data-clip-resize', clip.id);
        handle.title = 'Redimensionner';
        clipEl.appendChild(handle);
        clipsHost.appendChild(clipEl);
      }
      row.appendChild(clipsHost);
      row.addEventListener('click', () => {
        this.state.selectTrack(tr.id);
        if (this.onSelectTrack) this.onSelectTrack(tr.id);
      });
      rows.appendChild(row);
    }
    const fpsEl = this._el.querySelector('[data-ed-tl-fps]');
    if (fpsEl) fpsEl.textContent = `FPS ${(this.state.design && this.state.design.timeline && this.state.design.timeline.fps) || 30}`;
    const playhead = this._el.querySelector('[data-ed-tl-playhead]');
    if (playhead) playhead.style.transform = `translateX(${(Number(this._cursor) || 0) * this._zoom}px)`;
    const cursor = this._el.querySelector('[data-ed-tl-cursor]');
    if (cursor) cursor.style.left = `${(Number(this._cursor) || 0) * this._zoom}px`;
  }

  _bind() {
    const tl = this._el;
    const scroll = tl.querySelector('[data-ed-tl-scroll]');
    tl.addEventListener('pointerdown', (e) => {
      const t = e.target;
      const clipEl = t && t.closest ? t.closest('[data-clip-id]') : null;
      const handleEl = t && t.closest ? t.closest('[data-clip-resize]') : null;
      const hideBtn = t && t.closest ? t.closest('[data-ed-tl-hide]') : null;
      const lockBtn = t && t.closest ? t.closest('[data-ed-tl-lock]') : null;
      const zoomIn = t && t.closest ? t.closest('[data-ed-tl-zoom-in]') : null;
      const zoomOut = t && t.closest ? t.closest('[data-ed-tl-zoom-out]') : null;
      const cutBtn = t && t.closest ? t.closest('[data-ed-tl-cut]') : null;
      const playhead = tl.querySelector('[data-ed-tl-playhead]');
      const cursorEl = tl.querySelector('[data-ed-tl-cursor]');
      if (zoomIn) { e.preventDefault(); this._zoom = Math.min(4, this._zoom * 1.25); this._syncZoom(); this.requestRender(); return; }
      if (zoomOut) { e.preventDefault(); this._zoom = Math.max(0.25, this._zoom / 1.25); this._syncZoom(); this.requestRender(); return; }
      if (hideBtn) { e.preventDefault(); this.state.setTrackHidden(hideBtn.getAttribute('data-ed-tl-hide'), true); this.requestRender(); return; }
      if (lockBtn) { e.preventDefault(); this.state.setTrackLocked(lockBtn.getAttribute('data-ed-tl-lock'), true); this.requestRender(); return; }
      if (cutBtn) { e.preventDefault(); const clip = this._findClip(this._selectedClipId); if (clip) this.state.cutClip(clip.trackId, clip.id, this._cursor); return; }
      if (handleEl) { this._startResize(e, handleEl.getAttribute('data-clip-resize')); return; }
      if (clipEl) { this._startMove(e, clipEl); return; }
      if (playhead || cursorEl) { this._startCursor(e); }
    });
    scroll.addEventListener('scroll', () => {
      if (scroll.parentNode) scroll.parentNode.style.setProperty('--ed-scroll-x', `${scroll.scrollLeft}px`);
    });
  }

  _syncZoom() {
    const z = this._el.querySelector('[data-ed-tl-zoom]');
    if (z) z.textContent = `${Math.round(this._zoom * 100)}%`;
  }

  _findClip(clipId) {
    const timeline = this.state && this.state.design ? this.state.design.timeline : null;
    for (const tr of timeline?.tracks || []) {
      const clip = (tr.clips || []).find((c) => c.id === clipId);
      if (clip) return { trackId: tr.id, ...clip };
    }
    return null;
  }

  _startMove(e, clipEl) {
    const clipId = clipEl.getAttribute('data-clip-id');
    const info = this._findClip(clipId);
    if (!info) return;
    const clip = info.clip;
    if (clip.locked) return;
    this._selectedClipId = clipId;
    if (this.onSelectClip) this.onSelectClip(clipId);
    this.state.beginTransaction();
    const startX = e.clientX;
    const origStart = Number(clip.start) || 0;
    const move = (ev) => {
      const dx = ev.clientX - startX;
      const newStart = origStart + dx / this._zoom;
      this.state.moveClipLive(info.trackId, clipId, newStart);
    };
    const up = () => {
      this.state.commitTransaction();
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
      window.removeEventListener('pointercancel', cancel);
      this._dragging = null;
    };
    const cancel = () => {
      this.state.commitTransaction();
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
      window.removeEventListener('pointercancel', cancel);
      this._dragging = null;
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
    window.addEventListener('pointercancel', cancel);
    this._tlMove = move;
    this._tlMoveUp = up;
    this._tlMoveCancel = cancel;
    this._dragging = { mode: 'move', trackId: info.trackId, clipId, origStart, origDuration: Number(clip.duration) || 0, startX, zoom: this._zoom };
  }

  _startResize(e, clipId) {
    const info = this._findClip(clipId);
    if (!info) return;
    const clip = info.clip;
    if (clip.locked) return;
    this.state.beginTransaction();
    const startX = e.clientX;
    const origDuration = Number(clip.duration) || 0;
    const resize = (ev) => {
      const dx = ev.clientX - startX;
      const newDur = origDuration + dx / this._zoom;
      this.state.resizeClipLive(info.trackId, clipId, newDur);
    };
    const up = () => {
      this.state.commitTransaction();
      window.removeEventListener('pointermove', resize);
      window.removeEventListener('pointerup', up);
      window.removeEventListener('pointercancel', cancel);
      this._dragging = null;
    };
    const cancel = () => {
      this.state.commitTransaction();
      window.removeEventListener('pointermove', resize);
      window.removeEventListener('pointerup', up);
      window.removeEventListener('pointercancel', cancel);
      this._dragging = null;
    };
    window.addEventListener('pointermove', resize);
    window.addEventListener('pointerup', up);
    window.addEventListener('pointercancel', cancel);
    this._tlResize = resize;
    this._tlResizeUp = up;
    this._tlResizeCancel = cancel;
    this._dragging = { mode: 'resize', trackId: info.trackId, clipId, origStart: Number(clip.start) || 0, origDuration, startX, zoom: this._zoom };
  }

  _startCursor(e) {
    const move = (ev) => {
      const sc = this._el.querySelector('[data-ed-tl-scroll]');
      const rect = sc ? sc.getBoundingClientRect() : { left: 0 };
      const x = ev.clientX - rect.left - (sc ? sc.scrollLeft : 0);
      this._cursor = Math.max(0, x / this._zoom);
      const cursor = this._el.querySelector('[data-ed-tl-cursor]');
      if (cursor) cursor.style.left = `${(this._cursor * this._zoom).toFixed(2)}px`;
    };
    const up = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
      this._dragging = null;
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
    window.addEventListener('pointercancel', () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
      this._dragging = null;
    });
    this._tlCursor = move;
    this._tlCursorUp = up;
    this._dragging = { mode: 'cursor' };
  }

  destroy() {
    this._dragging = null;
    if (this._tlMove) { window.removeEventListener('pointermove', this._tlMove); window.removeEventListener('pointerup', this._tlMoveUp); window.removeEventListener('pointercancel', () => this._dragging = null); }
    if (this._tlResize) { window.removeEventListener('pointermove', this._tlResize); window.removeEventListener('pointerup', this._tlResizeUp); window.removeEventListener('pointercancel', () => this._dragging = null); }
    if (this._tlCursor) { window.removeEventListener('pointermove', this._tlCursor); window.removeEventListener('pointerup', this._tlCursorUp); window.removeEventListener('pointercancel', () => this._dragging = null); }
    this._tlMove = this._tlMoveUp = this._tlMoveCancel = null;
    this._tlResize = this._tlResizeUp = this._tlResizeCancel = null;
    this._tlCursor = this._tlCursorUp = this._tlCursorCancel = null;
    if (this._el && this._el.parentNode) this._el.parentNode.removeChild(this._el);
    this._el = null;
  }
}

export function createEditorTimeline(params) {
  return new EditorTimeline(params);
}
