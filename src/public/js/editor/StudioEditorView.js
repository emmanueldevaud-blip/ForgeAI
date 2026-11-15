/**
 * Vue de l'éditeur graphique du Studio : barre d'actions, format,
 * undo/redo, sauvegarde du design et export vers une photo publiable.
 */

import { EditorState, FORMATS, normalizeDesign } from './editorState.js?v=1';
import { EditorCanvas } from './editorCanvas.js?v=1';
import { EditorInteraction } from './editorInteraction.js?v=1';
import { EditorPanels } from './editorPanels.js?v=2';
import { coverCrop } from './editorGeometry.js?v=1';
import { EditorTimeline } from './editorTimeline.js?v=2';

const esc = (t) =>
  String(t ?? '').replace(
    /[&<>"']/g,
    (c) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
  );

export class StudioEditorView {
  /**
   * @param {Object} p
   * @param {Object} p.publication  brouillon courant (design/photo_id…)
   * @param {Object} p.deps         { updateDraft, uploadPhotos, getSuggestedPhotos,
   *                                  listPhotos, photoFileUrl, publicationPhotoUrl }
   * @param {Object} p.callbacks    { onClose, onApplied }
   */
  constructor({ publication, deps, callbacks = {} }) {
    this.publication = publication;
    this.deps = deps;
    this.callbacks = callbacks;
    this.state = new EditorState(normalizeDesign(publication?.design));
    this.canvas = new EditorCanvas({ state: this.state });
    this.interaction = null;
    this.panels = null;
    this.timeline = null;
    this.audioHost = null;
    this.audioEl = null;
    this._mixSources = [];
    this._audioBuffers = new Map();
    this._audioCtx = null;
    this._audioDest = null;
    this._mixPlaying = false;
    this._videoClipStart = 0;
    this._videoInPoint = 0;
    this.root = null;
    this.busy = false;
    this._renderPollTimer = null;
    this._renderJobId = null;
  }

  mount(host) {
    this.root = document.createElement('div');
    this.root.className = 'ed-root';
    this.root.innerHTML = `
      <div class="ed-header">
        <button type="button" class="btn btn-secondary" data-ed-close>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>
          Retour
        </button>
        <label class="ed-format-select">
          <span>Format</span>
          <select data-ed-format>
            ${FORMATS.map(
              (f) =>
                `<option value="${f.key}" ${
                  f.type === this.state.design.format.type &&
                  f.platform === this.state.design.format.platform
                    ? 'selected'
                    : ''
                }>${esc(f.label)}</option>`
            ).join('')}
          </select>
        </label>
        <div class="ed-header-actions">
          <span class="ed-status" data-ed-status></span>
          <button type="button" class="btn btn-secondary btn-small" data-ed-undo title="Annuler">↶</button>
          <button type="button" class="btn btn-secondary btn-small" data-ed-redo title="Rétablir">↷</button>
          <button type="button" class="btn btn-secondary" data-ed-save>Enregistrer</button>
          <button type="button" class="btn btn-secondary btn-small" data-ed-cancel ${this._renderJobId ? '' : 'disabled'}>Annuler le rendu</button>
          <button type="button" class="btn btn-secondary" data-ed-export-video>Exporter MP4</button>
          <button type="button" class="btn btn-primary" data-ed-apply>Appliquer &amp; enregistrer</button>
        </div>
      </div>
      <div class="ed-body" data-ed-body></div>
      <div class="ed-bottom" data-ed-bottom>
        <div class="ed-resize-handle" data-ed-resize title="Glisser pour redimensionner la timeline"></div>
        <div class="ed-transport" data-ed-transport></div>
        <div class="ed-timeline-host" data-ed-tl-host></div>
      </div>
    `;
    host.appendChild(this.root);

    const body = this.root.querySelector('[data-ed-body]');
    this.panels = new EditorPanels({
      root: body,
      state: this.state,
      canvas: this.canvas,
      interaction: null,
      deps: this.deps,
      onAction: (action, payload) => this._onAction(action, payload),
    });
    this.panels.renderLayout();

    this.canvas.mount(this.panels.canvasHost);
    this.interaction = new EditorInteraction({
      canvas: this.canvas,
      state: this.state,
      onGesture: () => this.panels.refreshProps(),
    });
    this.interaction.attach();
    this.panels.interaction = this.interaction;

    const transport = this.root.querySelector('[data-ed-transport]');
    const apHost = document.createElement('div');
    apHost.className = 'ed-audio-preview-host';
    transport.appendChild(apHost);
    this.audioHost = apHost;
    apHost.innerHTML = `
      <audio class="ed-audio-preview" preload="metadata" playsinline></audio>
      <div class="ed-audio-controls">
        <button type="button" class="ed-audio-btn" data-ed-audio-play title="Lecture">▶</button>
        <button type="button" class="ed-audio-btn" data-ed-audio-pause title="Pause">⏸</button>
        <span class="ed-audio-time" data-ed-audio-time>0:00 / 0:00</span>
      </div>
      <div class="ed-audio-mixer">
        <span class="ed-mixer-label">Mixage</span>
        <label class="ed-audio-field">
          <span>Volume</span>
          <input type="range" min="0" max="1" step="0.05" value="1" data-ed-audio-volume>
        </label>
        <button type="button" class="ed-audio-btn" data-ed-audio-mute title="Mute">🔇</button>
        <button type="button" class="ed-audio-btn" data-ed-audio-solo title="Solo">🎧</button>
        <label class="ed-audio-field">Fondu-in <input type="number" min="0" max="60" step="0.1" value="0" data-ed-audio-fade-in></label>
        <label class="ed-audio-field">Fondu-out <input type="number" min="0" max="60" step="0.1" value="0" data-ed-audio-fade-out></label>
        <label class="ed-audio-field">Ducking <input type="number" min="0" max="1" step="0.05" value="0" data-ed-audio-duck></label>
      </div>
    `;
    this.audioEl = apHost.querySelector('audio');
    this.audioEl.addEventListener('loadedmetadata', () => {
      const clip = this.state.getSelectedClip ? this.state.getSelectedClip() : null;
      if (clip && clip.mediaId) {
        const url = this.deps.photoFileUrl ? this.deps.photoFileUrl(clip.mediaId, 'medium') : `/photos/${clip.mediaId}/file?size=medium`;
        this.audioEl.src = url;
        this.audioEl.load();
      }
    });
    this.audioEl.addEventListener('timeupdate', () => {
      const t = this.audioEl.currentTime;
      this._cursor = t;
      const timeEl = apHost.querySelector('[data-ed-audio-time]');
      if (timeEl) timeEl.textContent = `${this._fmtVideoTime(t)} / ${this._fmtVideoTime(this.audioEl.duration || 0)}`;
    });
    this.audioEl.addEventListener('error', () => {
      this._setStatus('Chargement audio impossible.', 'err');
    });
    apHost.querySelector('[data-ed-audio-play]').addEventListener('click', (e) => { e.stopPropagation(); this._playAudio(); });
    apHost.querySelector('[data-ed-audio-pause]').addEventListener('click', (e) => { e.stopPropagation(); this._pauseAudio(); });
    const audioVolume = apHost.querySelector('[data-ed-audio-volume]');
    if (audioVolume) {
      audioVolume.addEventListener('input', (e) => {
        const v = Number(e.target.value);
        const t = this._mixSel();
        this.state.beginTransaction();
        if (t.clipId) this.state.updateClipLive(t.trackId, t.clipId, { volume: v });
        else if (t.trackId) this.state.setTrackVolumeLive(t.trackId, v);
      });
      audioVolume.addEventListener('change', (e) => {
        this.state.commitTransaction();
      });
      audioVolume.addEventListener('blur', (e) => {
        this.state.commitTransaction();
      });
    }
    const audioMute = apHost.querySelector('[data-ed-audio-mute]');
    if (audioMute) {
      audioMute.addEventListener('click', (e) => {
        const t = this._mixSel();
        if (t.clipId) {
          const clip = this.state.getClipById(t.clipId);
          if (clip) this.state.updateClip(t.trackId, t.clipId, { mute: !clip.mute });
        }
      });
    }
    const audioSolo = apHost.querySelector('[data-ed-audio-solo]');
    if (audioSolo) {
      audioSolo.addEventListener('click', (e) => {
        const t = this._mixSel();
        if (t.trackId) this.state.setTrackSolo(t.trackId, !this.state.getTrackById(t.trackId)?.solo);
      });
    }
    const audioFadeIn = apHost.querySelector('[data-ed-audio-fade-in]');
    if (audioFadeIn) {
      audioFadeIn.addEventListener('change', (e) => {
        const t = this._mixSel();
        if (t.clipId) this.state.updateClip(t.trackId, t.clipId, { fadeIn: Number(e.target.value) || 0 });
      });
    }
    const audioFadeOut = apHost.querySelector('[data-ed-audio-fade-out]');
    if (audioFadeOut) {
      audioFadeOut.addEventListener('change', (e) => {
        const t = this._mixSel();
        if (t.clipId) this.state.updateClip(t.trackId, t.clipId, { fadeOut: Number(e.target.value) || 0 });
      });
    }
    const audioDuck = apHost.querySelector('[data-ed-audio-duck]');
    if (audioDuck) {
      audioDuck.addEventListener('change', (e) => {
        const t = this._mixSel();
        if (t.trackId) this.state.setTrackDucking(t.trackId, { enabled: Number(e.target.value) > 0, level: Number(e.target.value) });
      });
    }

    const vpHost = document.createElement('div');
    vpHost.className = 'ed-video-preview-host';
    transport.insertBefore(vpHost, apHost);
    this.videoHost = vpHost;
    vpHost.innerHTML = `
      <video class="ed-video-preview" preload="metadata" playsinline></video>
      <div class="ed-video-controls">
        <button type="button" class="ed-video-btn" data-ed-video-play title="Lecture">▶</button>
        <button type="button" class="ed-video-btn" data-ed-video-pause title="Pause">⏸</button>
        <span class="ed-video-time" data-ed-video-time>0:00 / 0:00</span>
      </div>
    `;
    this.videoEl = vpHost.querySelector('video');
    this.videoEl.addEventListener('loadedmetadata', () => {
      const clip = this.state.getSelectedClip ? this.state.getSelectedClip() : null;
      if (clip && clip.mediaId) {
        const url = this.deps.photoFileUrl ? this.deps.photoFileUrl(clip.mediaId, 'medium') : `/photos/${clip.mediaId}/file?size=medium`;
        this.videoEl.src = url;
        this.videoEl.load();
        this._videoClipStart = Number(clip.start) || 0;
        this._videoInPoint = Number(clip.inPoint) || 0;
      }
    });
    this.videoEl.addEventListener('timeupdate', () => {
      const t = this.videoEl.currentTime;
      this._cursor = t;
      if (this.timeline) this.timeline._cursor = t;
      const timeEl = vpHost.querySelector('[data-ed-video-time]');
      if (timeEl) timeEl.textContent = `${this._fmtVideoTime(t)} / ${this._fmtVideoTime(this.videoEl.duration || 0)}`;
    });
    this.videoEl.addEventListener('error', () => {
      this._setStatus('Chargement de la vidéo impossible.', 'err');
    });
    vpHost.querySelector('[data-ed-video-play]').addEventListener('click', (e) => { e.stopPropagation(); this._playVideo(); });
    vpHost.querySelector('[data-ed-video-pause]').addEventListener('click', (e) => { e.stopPropagation(); this._pauseVideo(); });
    const tlHost = this.root.querySelector('[data-ed-tl-host]');
    this.timeline = new EditorTimeline({
      root: this,
      state: this.state,
      // Sélection posée au pointerdown (avant beginTransaction du drag) : le
      // click final est supprimé par Chrome quand le clip est reconstruit
      // pendant le pointerup.
      onSelectClip: (clipId) => {
        const info = this.state.getClipById(clipId);
        if (info) this.state.selectClip(info.trackId, clipId);
      },
    });
    this.timeline.mount(tlHost);
    // Échelle de départ : zoom maximal pour des clips lisibles.
    this.timeline._zoom = 4;
    this.timeline._syncZoom();
    this.timeline.requestRender();
    this._mountRuler();
    this._bindTimelineSelection();
    this._bindBottomResize();

    this.state.onChange = () => {
      this.canvas.requestRender();
      this.panels.onSelectionChanged();
      this._updateUndoButtons();
      if (this.timeline) this.timeline.requestRender();
      this._syncClipSelection();
      this._renderRuler();
      const sel = this.state.getSelectedClip ? this.state.getSelectedClip() : null;
      if (sel && sel.type === 'video' && sel.mediaId && this.videoEl) {
        const url = this.deps.photoFileUrl ? this.deps.photoFileUrl(sel.mediaId, 'medium') : `/photos/${sel.mediaId}/file?size=medium`;
        if (this.videoEl.dataset.src !== url) {
          this.videoEl.dataset.src = url;
          this.videoEl.src = url;
          this.videoEl.load();
        }
      }
    };

    this._bindHeader();
    this._updateUndoButtons();
    this.canvas.ensureImages();
    return this.root;
  }

  destroy() {
    this._stopRenderPoll();
    this._stopMix();
    if (this._rulerZoomObs) { this._rulerZoomObs.disconnect(); this._rulerZoomObs = null; }
    if (this._rulerNeedleObs) { this._rulerNeedleObs.disconnect(); this._rulerNeedleObs = null; }
    if (this._bottomDrag) { this._bottomDrag.up(); this._bottomDrag = null; }
    this._rulerEl = null;
    this._rulerTicks = null;
    this._rulerNeedle = null;
    if (this.audioEl) { try { this.audioEl.pause(); } catch (_e) { /* ignore */ } }
    if (this.audioEl && this.audioEl.parentNode) this.audioEl.parentNode.removeChild(this.audioEl);
    if (this.videoEl) { try { this.videoEl.pause(); } catch (_e) { /* ignore */ } }
    if (this.videoHost && this.videoEl && this.videoHost.parentNode) this.videoHost.parentNode.removeChild(this.videoHost);
    if (this._audioCtx) { try { void this._audioCtx.close(); } catch (_e) { /* ignore */ } this._audioCtx = null; this._audioDest = null; }
    this._audioBuffers = new Map();
    this._mixSources = [];
    this._mixPlaying = false;
    clearTimeout(this._statusTimer);
    if (this.interaction) this.interaction.detach();
    if (this.canvas) this.canvas.destroy();
    if (this.timeline) this.timeline.destroy();
    if (this.videoEl) {
      try { this.videoEl.pause(); } catch (_err) { /* ignore */ }
      if (this.videoHost && this.videoHost.parentNode) this.videoHost.parentNode.removeChild(this.videoHost);
    }
    if (this.audioEl) {
      try { this.audioEl.pause(); } catch (_err) { /* ignore */ }
      if (this.audioHost && this.audioHost.parentNode) this.audioHost.parentNode.removeChild(this.audioHost);
    }
    if (this.root && this.root.parentNode) this.root.parentNode.removeChild(this.root);
    this.root = null;
  }

  async _getAudioBuffer(url) {
    const key = url;
    if (this._audioBuffers && this._audioBuffers.has(key)) {
      return this._audioBuffers.get(key);
    }
    if (!this._audioCtx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      this._audioCtx = new AC();
      this._audioDest = this._audioCtx.createGain();
      this._audioDest.gain.value = 1;
      this._audioDest.connect(this._audioCtx.destination);
    }
    const res = await fetch(url);
    const buf = await this._audioCtx.decodeAudioData(await res.arrayBuffer());
    if (!this._audioBuffers) this._audioBuffers = new Map();
    this._audioBuffers.set(key, buf);
    return buf;
  }

  async _startMix() {
    this._stopMix();
    if (!this._audioCtx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      this._audioCtx = new AC();
      this._audioDest = this._audioCtx.createGain();
      this._audioDest.gain.value = 1;
      this._audioDest.connect(this._audioCtx.destination);
    }
    const ctx = this._audioCtx;
    const dest = this._audioDest;
    const origin = Number(this._cursor) || 0;
    const plan = this._getMixPlan();
    const tasks = [];
    for (const tr of plan.tracks) {
      for (const clip of tr.clips) {
        if (clip.mute) continue;
        const url = this.deps.photoFileUrl ? this.deps.photoFileUrl(clip.mediaId, 'medium') : `/photos/${clip.mediaId}/file?size=medium`;
        tasks.push(
          this._getAudioBuffer(url).then((buf) => {
            const src = ctx.createBufferSource();
            src.buffer = buf;
            const gain = ctx.createGain();
            const gainValue = Math.max(0, Number(clip.gain) || 0);
            const sourceStart = ctx.currentTime + Math.max(0, clip.start - origin);
            const sourceOffset = (Number(clip.inPoint) || 0) + Math.max(0, origin - clip.start);
            const sourceDuration = Math.max(0, (Number(clip.inPoint) || 0) + (Number(clip.duration) || 0) - sourceOffset);
            const fadeIn = Math.max(0, Number(clip.fadeIn) || 0);
            const fadeOut = Math.max(0, Number(clip.fadeOut) || 0);
            gain.gain.setValueAtTime(gainValue, sourceStart);
            if (fadeIn > 0) gain.gain.linearRampToValueAtTime(gainValue, sourceStart + fadeIn);
            if (fadeOut > 0) {
              gain.gain.setValueAtTime(gainValue, Math.max(sourceStart, sourceStart + Math.max(0, sourceDuration - fadeOut)));
              gain.gain.linearRampToValueAtTime(0, sourceStart + sourceDuration);
            }
            src.connect(gain);
            gain.connect(dest);
            src.start(sourceStart, sourceOffset, sourceDuration);
            this._mixSources.push({ src, gain });
            return true;
          })
        );
      }
    }
    this._mixPlaying = true;
    return Promise.all(tasks).then(() => {
      this._mixSources = this._mixSources.filter((x) => x);
    });
  }

  _stopMix() {
    for (const s of this._mixSources) {
      try { s.src.stop(); } catch (_e) { /* ignore */ }
      try { s.src.disconnect(); } catch (_e) { /* ignore */ }
      try { s.gain.disconnect(); } catch (_e) { /* ignore */ }
    }
    this._mixSources = [];
    this._mixPlaying = false;
  }

  async _playMix() {
    await this._startMix();
  }

  async _pauseMix() {
    this._stopMix();
  }

  _seekMix(t) {
    const nt = Number(t);
    if (Number.isNaN(nt)) return;
    this._cursor = nt;
    if (this.timeline) this.timeline._cursor = nt;
    if (this._mixPlaying) this._startMix();
  }

  _playAudio() {
    this._playMix().catch(() => this._setStatus('Lecture audio impossible.', 'err'));
  }

  _pauseAudio() {
    this._stopMix();
  }

  _seekAudio(t) {
    this._seekMix(t);
  }

  _playVideo() {
    if (!this.videoEl) return;
    const p = this.videoEl.play();
    if (p && p.catch) p.catch(() => this._setStatus('Lecture vidéo impossible.', 'err'));
    this._playMix().catch(() => this._setStatus('Lecture audio impossible.', 'err'));
  }

  _pauseVideo() {
    if (this.videoEl) this.videoEl.pause();
    this._stopMix();
  }

  _seekVideo(t) {
    const nt = Number(t);
    if (Number.isNaN(nt)) return;
    const sourceTime = (Number(this._videoInPoint) || 0) + Math.max(0, nt - (Number(this._videoClipStart) || 0));
    if (this.videoEl) this.videoEl.currentTime = sourceTime;
    this._seekMix(nt);
  }

  _getMixPlan() {
    const design = this.state.design;
    const timeline = design.timeline || { fps: 30, tracks: [] };
    const tracks = [];
    const audioTracks = (timeline.tracks || []).filter((t) => t && t.type === 'audio');
    const anySolo = audioTracks.some((t) => t.solo);
    let finalDuration = 0;
    for (const tr of audioTracks) {
      if (tr.hidden) continue;
      if (anySolo && !tr.solo) continue;
      const duckLevel = tr.ducking && tr.ducking.enabled ? Math.max(0, 1 - (Number(tr.ducking.level) || 0)) : 1;
      const trackGain = Math.max(0, ((Number.isFinite(Number(tr.volume)) ? Number(tr.volume) : 1) * duckLevel));
      const clips = [];
      for (const clip of tr.clips || []) {
        if (!clip || !clip.id) continue;
        const inPoint = Math.max(0, Number(clip.inPoint) || 0);
        const outPoint = Math.max(inPoint, Number(clip.outPoint ?? (inPoint + (Number(clip.duration) || 0))) || inPoint);
        const duration = Math.max(0, outPoint - inPoint);
        const start = Number(clip.start) || 0;
        const gain = Math.max(0, ((Number.isFinite(Number(clip.volume)) ? Number(clip.volume) : 1) * trackGain) * (clip.mute ? 0 : 1));
        clips.push({ trackId: tr.id, clipId: clip.id, mediaId: clip.mediaId ?? null, start, duration, gain, fadeIn: Math.max(0, Number(clip.fadeIn) || 0), fadeOut: Math.max(0, Number(clip.fadeOut) || 0), mute: !!clip.mute, inPoint });
        finalDuration = Math.max(finalDuration, start + duration);
      }
      if (!clips.length) continue;
      tracks.push({ trackId: tr.id, type: tr.type, order: tracks.length, hidden: false, solo: !!tr.solo, volume: trackGain, clips });
    }
    for (const tr of timeline.tracks || []) {
      if (!tr || !tr.id || tr.type !== 'video') continue;
      if (tr.hidden) continue;
      for (const clip of tr.clips || []) {
        if (!clip || !clip.id) continue;
        const inPoint = Math.max(0, Number(clip.inPoint) || 0);
        const outPoint = Math.max(inPoint, Number(clip.outPoint ?? (inPoint + (Number(clip.duration) || 0))) || inPoint);
        const duration = Math.max(0, outPoint - inPoint);
        finalDuration = Math.max(finalDuration, (Number(clip.start) || 0) + duration);
      }
    }
    return { fps: Number(timeline.fps) || 30, finalDuration, sync: { mode: 'timeline', origin: Number(this._cursor) || 0 }, tracks };
  }

  _fmtVideoTime(sec) {
    const t = Number(sec) || 0;
    const m = Math.floor(t / 60);
    const r = Math.floor(t % 60);
    return `${m}:${String(r).padStart(2, '0')}`;
  }

  // ------------------------------------------------------------------
  // Cible du mixage, sélection des clips, règle et redimensionnement
  // ------------------------------------------------------------------

  /** Cible des commandes de mixage : clip audio sélectionné, sinon piste. */
  _mixSel() {
    const st = this.state;
    const sel = st.getSelectedClip ? st.getSelectedClip() : null;
    if (sel && sel.trackId && sel.type === 'audio' && (sel.id || sel.elementId)) {
      return { trackId: sel.trackId, clipId: sel.id || sel.elementId };
    }
    const trackId =
      st.selectedId && st.getTrackById && st.getTrackById(st.selectedId) ? st.selectedId : null;
    return { trackId, clipId: null };
  }

  /** Met en évidence visuellement le clip sélectionné dans la timeline. */
  _syncClipSelection() {
    const tl = this.timeline && this.timeline._el;
    if (!tl) return;
    const selId = this.state.selectedId;
    tl.querySelectorAll('[data-clip-id]').forEach((el) => {
      el.classList.toggle('is-selected', el.getAttribute('data-clip-id') === selId);
    });
  }

  /**
   * Sélection au clic dans la timeline : le clic remonte jusqu'à la ligne de
   * piste (selectTrack) qui écrase la sélection du clip ; on restaure alors la
   * cible réellement cliquée.
   */
  _bindTimelineSelection() {
    const tl = this.timeline && this.timeline._el;
    if (!tl) return;
    tl.addEventListener(
      'pointerdown',
      (e) => {
        const clipEl = e.target && e.target.closest ? e.target.closest('[data-clip-id]') : null;
        this._clickOnClip = clipEl ? clipEl.getAttribute('data-clip-id') : null;
      },
      true
    );
    tl.addEventListener('click', () => {
      const clipId = this._clickOnClip;
      this._clickOnClip = null;
      if (clipId) {
        const info = this.state.getClipById(clipId);
        if (info) this.state.selectClip(info.trackId, clipId);
      }
      this._syncClipSelection();
      if (this.panels) this.panels.onSelectionChanged();
      if (this.canvas) this.canvas.requestRender();
    });
  }

  /** Règle temporelle (graduations + aiguille) synchronisée avec la timeline. */
  _mountRuler() {
    const tl = this.timeline && this.timeline._el;
    if (!tl) return;
    const scroll = tl.querySelector('[data-ed-tl-scroll]');
    if (!scroll) return;
    const ruler = document.createElement('div');
    ruler.className = 'ed-tl-ruler';
    ruler.innerHTML = `
      <span class="ed-tl-ruler-head">Temps</span>
      <div class="ed-tl-ruler-viewport">
        <div class="ed-tl-ruler-inner">
          <div data-ed-ruler-ticks></div>
          <div class="ed-tl-ruler-needle" data-ed-ruler-needle></div>
        </div>
      </div>
    `;
    tl.insertBefore(ruler, scroll);
    this._rulerEl = ruler;
    this._rulerTicks = ruler.querySelector('[data-ed-ruler-ticks]');
    this._rulerNeedle = ruler.querySelector('[data-ed-ruler-needle]');

    if (typeof MutationObserver !== 'undefined') {
      const zoomLabel = tl.querySelector('[data-ed-tl-zoom]');
      if (zoomLabel) {
        this._rulerZoomObs = new MutationObserver(() => this._renderRuler());
        this._rulerZoomObs.observe(zoomLabel, { childList: true, characterData: true, subtree: true });
      }
      const cursorEl = tl.querySelector('[data-ed-tl-cursor]');
      if (cursorEl) {
        this._rulerNeedleObs = new MutationObserver(() => this._syncRulerNeedle());
        this._rulerNeedleObs.observe(cursorEl, { attributes: true, attributeFilter: ['style'] });
      }
    }
    this._renderRuler();
    this._syncRulerNeedle();
  }

  _rulerZoom() {
    return Number(this.timeline && this.timeline._zoom) || 1;
  }

  _renderRuler() {
    if (!this._rulerTicks) return;
    const zoom = this._rulerZoom();
    const tracks =
      (this.state.design && this.state.design.timeline && this.state.design.timeline.tracks) || [];
    let maxT = 0;
    for (const tr of tracks) {
      if (!tr || tr.hidden) continue;
      for (const c of tr.clips || []) {
        maxT = Math.max(maxT, (Number(c.start) || 0) + (Number(c.duration) || 0));
      }
    }
    const span = Math.max(maxT + 5, 20);
    const steps = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1800, 3600];
    let step = steps[steps.length - 1];
    const target = 64 / Math.max(zoom, 0.0001);
    for (const s of steps) {
      if (s >= target) {
        step = s;
        break;
      }
    }
    while (span / step > 400) {
      const idx = steps.indexOf(step);
      if (idx < 0 || idx >= steps.length - 1) break;
      step = steps[idx + 1];
    }
    const fmt = (t) => {
      const m = Math.floor(t / 60);
      const s = Math.floor(t % 60);
      return `${m}:${String(s).padStart(2, '0')}`;
    };
    const parts = [];
    const minor = step >= 5 ? step / 5 : 0;
    if (minor) {
      for (let t = 0; t <= span + 1e-9; t += minor) {
        parts.push(`<i class="ed-tl-ruler-tick" style="left:${(t * zoom).toFixed(1)}px"></i>`);
      }
    }
    for (let t = 0; t <= span + 1e-9; t += step) {
      const x = (t * zoom).toFixed(1);
      parts.push(`<i class="ed-tl-ruler-tick ed-tl-ruler-tick--major" style="left:${x}px"></i>`);
      parts.push(`<span class="ed-tl-ruler-label" style="left:${x}px">${fmt(t)}</span>`);
    }
    this._rulerTicks.innerHTML = parts.join('');
    this._syncRulerNeedle();
  }

  _syncRulerNeedle() {
    if (!this._rulerNeedle || !this.timeline) return;
    const t = Number(this.timeline._cursor) || 0;
    this._rulerNeedle.style.left = `${(t * this._rulerZoom()).toFixed(2)}px`;
  }

  /** Redimensionnement vertical de la zone basse (timeline) par glisser-déposer. */
  _bindBottomResize() {
    const handle = this.root && this.root.querySelector('[data-ed-resize]');
    if (!handle) return;
    handle.addEventListener('pointerdown', (e) => {
      e.preventDefault();
      const bottom = this.root.querySelector('[data-ed-bottom]');
      if (!bottom) return;
      const startY = e.clientY;
      const startH = bottom.getBoundingClientRect().height;
      const clamp = (h) => {
        const maxH = Math.max(320, Math.min(640, Math.round(window.innerHeight * 0.62)));
        const minH = Math.max(260, Math.min(440, bottom.scrollHeight));
        return Math.min(maxH, Math.max(minH, h));
      };
      const move = (ev) => {
        this.root.style.setProperty('--ed-bottom-h', `${clamp(startH + (startY - ev.clientY))}px`);
      };
      const up = () => {
        window.removeEventListener('pointermove', move);
        window.removeEventListener('pointerup', up);
        window.removeEventListener('pointercancel', up);
        this._bottomDrag = null;
      };
      this._bottomDrag = { up };
      window.addEventListener('pointermove', move);
      window.addEventListener('pointerup', up);
      window.addEventListener('pointercancel', up);
      try {
        handle.setPointerCapture(e.pointerId);
      } catch (_err) {
        /* capture optionnelle */
      }
    });
  }

  _bindHeader() {
    this.root.querySelector('[data-ed-close]').addEventListener('click', () => {
      if (this.callbacks.onClose) this.callbacks.onClose();
    });

    this.root.querySelector('[data-ed-format]').addEventListener('change', (e) => {
      this.state.setFormat(e.target.value);
      this.canvas.ensureImages();
    });

    this.root.querySelector('[data-ed-undo]').addEventListener('click', () => {
      this.state.undo();
      this.canvas.ensureImages();
    });
    this.root.querySelector('[data-ed-redo]').addEventListener('click', () => {
      this.state.redo();
      this.canvas.ensureImages();
    });

    this.root.querySelector('[data-ed-save]').addEventListener('click', () => {
      this._saveDesign();
    });
    this.root.querySelector('[data-ed-apply]').addEventListener('click', () => {
      this._apply();
    });
    this.root.querySelector('[data-ed-export-video]').addEventListener('click', () => {
      this._exportVideo();
    });
    this.root.querySelector('[data-ed-cancel]').addEventListener('click', async () => {
      await this._cancelRender();
    });
    this._updateExportVideoButton();
  }

  _hasVideoClips() {
    const tracks = this.state.getTimeline().tracks || [];
    return tracks.some(
      (t) =>
        t.type === 'video' &&
        !t.hidden &&
        (t.clips || []).some((c) => c.type === 'video' && c.mediaId)
    );
  }

  _updateExportVideoButton() {
    const btn = this.root?.querySelector('[data-ed-export-video]');
    if (!btn) return;
    btn.disabled = this.busy || !this._hasVideoClips() || !!this._renderJobId;
  }

  _stopRenderPoll() {
    if (this._renderPollTimer) {
      clearInterval(this._renderPollTimer);
      this._renderPollTimer = null;
    }
  }

  static stageLabel(stage) {
    const labels = {
      pending: 'en attente',
      video: 'vidéo',
      audio: 'audio',
      finalize: 'finalisation',
      done: 'terminé',
      cancelled: 'annulé',
    };
    return labels[stage] || stage || '';
  }

  async _cancelRender() {
    const jobId = this._renderJobId;
    if (!jobId) return;
    try {
      const job = await this.deps.cancelRender(jobId);
      if (job) {
        this._renderJobId = null;
        this.busy = false;
        this._stopRenderPoll();
        this._updateExportVideoButton();
        this._setStatus('Rendu MP4 annulé.', 'warn', true);
      }
    } catch (err) {
      this._setStatus(err?.data?.detail || err?.message || 'Erreur annulation.', 'err');
    }
  }

  async _exportVideo() {
    if (this.busy || !this.deps.createRender) return;
    if (!this._hasVideoClips()) {
      this._setStatus('Ajoutez au moins une vidéo à la timeline.', 'warn');
      return;
    }
    this.busy = true;
    this._updateExportVideoButton();
    const cancelBtn = this.root?.querySelector('[data-ed-export-video]');
    if (cancelBtn) cancelBtn.disabled = true;
    try {
      const design = this.state.toJSON();
      await this.deps.updateDraft(this.publication.id, { design });
      this.publication.design = design;

      const job = await this.deps.createRender(this.publication.id);
      if (!job?.id) throw new Error('Création du rendu impossible.');
      this._renderJobId = job.id;
      this._setStatus(
        `Rendu MP4 — ${StudioEditorView.stageLabel(job.progress?.stage || 'pending')} 0%`,
        'info',
        true
      );
      this._startRenderPoll(job.id);
    } catch (err) {
      this._renderJobId = null;
      this._setStatus(err?.data?.detail || err?.message || 'Erreur de rendu MP4.', 'err');
      this._updateExportVideoButton();
      this.busy = false;
    }
  }

  _startRenderPoll(jobId) {
    this._stopRenderPoll();
    this._renderPollTimer = setInterval(async () => {
      if (!this.root || !this.deps.getRenderJob) {
        this._stopRenderPoll();
        return;
      }
      try {
        const job = await this.deps.getRenderJob(jobId);
        if (!job) return;
        const progress = job.progress || {};
        const stage = progress.stage || job.status;
        const percent = Number(progress.percent) || 0;
        const label = StudioEditorView.stageLabel(stage);

        if (job.status === 'done' || stage === 'done') {
          this._stopRenderPoll();
          this._renderJobId = null;
          this.busy = false;
          this._setStatus('Rendu MP4 terminé.', 'ok', true);
          if (this.deps.renderFileUrl) {
            const url = this.deps.renderFileUrl(jobId);
            const el = this.root?.querySelector('[data-ed-status]');
            if (el) {
              const a = document.createElement('a');
              a.href = url;
              a.textContent = ' Télécharger le MP4';
              a.download = '';
              el.appendChild(a);
            }
          }
          this._updateExportVideoButton();
          return;
        }

        if (job.status === 'failed' || stage === 'cancelled') {
          this._stopRenderPoll();
          this._renderJobId = null;
          this.busy = false;
          this._setStatus(
            job.error || (stage === 'cancelled' ? 'Rendu annulé.' : 'Rendu MP4 en échec.'),
            stage === 'cancelled' ? 'warn' : 'err',
            true
          );
          this._updateExportVideoButton();
          return;
        }

        this._setStatus(`Rendu MP4 — ${label} ${percent}%`, 'info', true);
      } catch (_err) {
        /* polling silencieux : on retentera au tick suivant */
      }
    }, 1000);
  }

  _updateUndoButtons() {
    if (!this.root) return;
    const undo = this.root.querySelector('[data-ed-undo]');
    const redo = this.root.querySelector('[data-ed-redo]');
    if (undo) undo.disabled = !this.state.undoStack.length;
    if (redo) redo.disabled = !this.state.redoStack.length;
    this._updateExportVideoButton();
  }

  _setStatus(msg, kind = 'info', sticky = false) {
    const el = this.root?.querySelector('[data-ed-status]');
    if (!el) return;
    el.textContent = msg || '';
    el.className = `ed-status ed-status--${kind}`;
    clearTimeout(this._statusTimer);
    if (msg && !sticky) {
      this._statusTimer = setTimeout(() => {
        if (el) {
          el.textContent = '';
          el.className = 'ed-status';
        }
      }, 3000);
    }
  }

  async _onAction(action, payload) {
    try {
      if (action === 'set-bg') {
        await this._setBackgroundPhoto(payload.photoId);
      } else if (action === 'add-carousel') {
        const cur = (this.state.design.carousel || []).slice();
        if (!cur.includes(payload.photoId)) {
          this.state.setCarousel([...cur, payload.photoId]);
          if (this.state.design.cover == null) this.state.setCover(payload.photoId);
        }
        this.panels.refreshCarousel();
        this._setStatus('Ajouté au carrousel.', 'ok');
      } else if (action === 'cover') {
        if (this.publication && this.deps.updateDraft) {
          if (!this.publication.photo_locked) {
            await this.deps.updateDraft(this.publication.id, { photo_id: payload.photoId });
            this.publication.photo_id = payload.photoId;
          }
          this._setStatus(
            this.publication.photo_locked
              ? 'Photo verrouillée : couverture non modifiable.'
              : 'Couverture définie.',
            this.publication.photo_locked ? 'warn' : 'ok'
          );
        }
        this.panels.refreshCarousel();
      } else if (action === 'uploaded') {
        this._setStatus('Photos importées.', 'ok');
      } else if (action === 'add-video') {
        const mediaId = payload?.photoId;
        if (!mediaId) return;
        const tl = this.state.getTimeline();
        let tr = (tl.tracks || []).find((t) => t.type === 'video' && !t.hidden);
        if (!tr) {
          tr = { id: `tr-video-${Date.now().toString(36)}`, type: 'video', hidden: false, locked: false, clips: [] };
          this.state.addTrack(tr);
        }
        const duration = Number(payload?.duration) || 0;
        if (!(duration > 0)) {
          this._setStatus('Durée vidéo indisponible : import impossible.', 'warn');
          return;
        }
        const clip = {
          id: `clip-${Date.now().toString(36)}`,
          type: 'video',
          start: 0,
          duration,
          trackId: tr.id,
          mediaId,
          source: payload.source || 'forgeai',
          inPoint: 0,
          outPoint: duration,
          rotation: 0,
          crop: null,
          mute: false,
        };
        this.state.addVideoClip(tr.id, clip);
        this._setStatus('Vidéo ajoutée à la timeline.', 'ok');
      } else if (action === 'error') {
        this._setStatus(payload?.data?.detail || payload?.message || 'Erreur.', 'err');
      }
    } catch (err) {
      this._setStatus(err?.data?.detail || err?.message || 'Erreur.', 'err');
    }
  }

  /**
   * Place une photo de la bibliothèque comme image de fond du design
   * (couvre tout le format, crop « cover »).
   */
  async _setBackgroundPhoto(photoId) {
    const d = this.state.design;
    const src = this.deps.photoFileUrl(photoId, 'medium');
    const img = await this._loadImage(src);
    const iw = img?.naturalWidth || d.format.width;
    const ih = img?.naturalHeight || d.format.height;
    const crop = coverCrop(iw, ih, d.format.width, d.format.height);

    const existingBg = d.elements.find((e) => e.type === 'image' && e.isBackground);
    if (existingBg) {
      this.state.updateElement(existingBg.id, { photoId, src, crop, filter: existingBg.filter });
    } else {
      this.state.addElement({
        type: 'image',
        photoId,
        src,
        isBackground: true,
        x: d.format.width / 2,
        y: d.format.height / 2,
        w: d.format.width,
        h: d.format.height,
        crop,
        filter: 'none',
        rotation: 0,
        opacity: 1,
      });
    }
    await this.canvas.ensureImages();
    this._setStatus('Photo placée en fond.', 'ok');
  }

  _loadImage(src) {
    return new Promise((resolve) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => resolve(null);
      img.src = src;
    });
  }

  async _saveDesign() {
    if (this.busy) return;
    this.busy = true;
    try {
      const design = this.state.toJSON();
      await this.deps.updateDraft(this.publication.id, { design });
      this.publication.design = design;
      this._setStatus('Design enregistré.', 'ok');
    } catch (err) {
      this._setStatus(err?.data?.detail || err?.message || 'Erreur de sauvegarde.', 'err');
    } finally {
      this.busy = false;
    }
  }

  /**
   * Exporte le rendu, l'importe comme photo ForgeAI, puis attache la photo
   * et le design au brouillon. Le flux publish existant reste inchangé.
   */
  async _apply() {
    if (this.busy) return;
    this.busy = true;
    const applyBtn = this.root?.querySelector('[data-ed-apply]');
    if (applyBtn) applyBtn.disabled = true;
    try {
      const blob = await this.canvas.exportBlob('image/jpeg', 0.92);
      if (!blob) throw new Error('Export impossible.');
      const file = new File([blob], `studio-${Date.now()}.jpg`, {
        type: 'image/jpeg',
      });
      const res = await this.deps.uploadPhotos([file]);
      const items = Array.isArray(res?.items) ? res.items : res;
      const created = items?.[0];
      if (!created?.id) throw new Error('Import de la photo impossible.');

      const design = this.state.toJSON();
      const patch = { design, photo_id: created.id, visual_type: 'photo' };
      if (this.publication.photo_locked) {
        delete patch.photo_id;
      }
      await this.deps.updateDraft(this.publication.id, patch);
      this.publication.design = design;
      if (!this.publication.photo_locked) this.publication.photo_id = created.id;

      if (this.callbacks.onApplied) await this.callbacks.onApplied();
      this._setStatus('Visuel appliqué et enregistré.', 'ok');
    } catch (err) {
      this._setStatus(err?.data?.detail || err?.message || 'Erreur lors de l’export.', 'err');
    } finally {
      this.busy = false;
      if (applyBtn) applyBtn.disabled = false;
    }
  }
}

export function createStudioEditorView(params) {
  return new StudioEditorView(params);
}
