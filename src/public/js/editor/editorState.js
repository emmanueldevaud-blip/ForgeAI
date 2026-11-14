/**
 * État de l'éditeur graphique — modèle de design versionné, sélection,
 * transactions undo/redo. Aucun DOM : testable en Node.
 */

import { scaleDesign } from './editorGeometry.js';

export const FORMATS = [
  { key: 'ig_feed_11', platform: 'instagram', type: 'feed_11', width: 1080, height: 1080, label: 'Instagram · Feed 1:1' },
  { key: 'ig_feed_45', platform: 'instagram', type: 'feed_45', width: 1080, height: 1350, label: 'Instagram · Feed 4:5' },
  { key: 'ig_story', platform: 'instagram', type: 'story_916', width: 1080, height: 1920, label: 'Instagram · Story 9:16' },
  { key: 'ig_reel', platform: 'instagram', type: 'reel_916', width: 1080, height: 1920, label: 'Instagram · Reel 9:16' },
  { key: 'fb_photo', platform: 'facebook', type: 'fb_photo', width: 1200, height: 1200, label: 'Facebook · Photo' },
  { key: 'fb_album', platform: 'facebook', type: 'fb_album', width: 1200, height: 1200, label: 'Facebook · Album' },
  { key: 'fb_story', platform: 'facebook', type: 'fb_story', width: 1080, height: 1920, label: 'Facebook · Story' },
  { key: 'fb_video', platform: 'facebook', type: 'fb_video', width: 1280, height: 720, label: 'Facebook · Vidéo' },
];

export const TEXT_FONTS = [
  'Arial',
  'Helvetica',
  'Georgia',
  '"Times New Roman"',
  '"Trebuchet MS"',
  '"Courier New"',
  '"Arial Black"',
  'Impact',
];

export const STICKER_SET = [
  '🔥', '💪', '🏃', '🚴', '⛰️', '🏆', '❤️', '⭐',
  '🎉', '☀️', '🌙', '⚡', '🎯', '🥇', '😎', '🙌',
];

export const SHAPE_SET = ['circle', 'rect', 'line'];

export const FILTERS = [
  { key: 'none', label: 'Aucun', css: 'none' },
  { key: 'bw', label: 'Noir & blanc', css: 'grayscale(100%)' },
  { key: 'sepia', label: 'Sépia', css: 'sepia(75%)' },
  { key: 'warm', label: 'Chaud', css: 'saturate(140%) hue-rotate(-12deg) brightness(105%)' },
  { key: 'cool', label: 'Froid', css: 'saturate(130%) hue-rotate(16deg) brightness(102%)' },
  { key: 'punch', label: 'Contraste', css: 'contrast(135%) saturate(120%)' },
  { key: 'bright', label: 'Lumineux', css: 'brightness(115%)' },
  { key: 'soft', label: 'Doux', css: 'blur(0.6px) brightness(104%)' },
];

export function filterCss(key) {
  const f = FILTERS.find((x) => x.key === key);
  return f ? f.css : 'none';
}

let idCounter = 0;
function nextId(prefix = 'el') {
  idCounter += 1;
  return `${prefix}-${Date.now().toString(36)}-${idCounter}`;
}

export function defaultDesign(formatKey = 'ig_feed_45') {
  const fmt = FORMATS.find((f) => f.key === formatKey) || FORMATS[1];
  return {
    version: 2,
    format: {
      platform: fmt.platform,
      type: fmt.type,
      width: fmt.width,
      height: fmt.height,
    },
    background: { color: '#111111' },
    elements: [],
    carousel: [],
    cover: null,
    timeline: { fps: 30, tracks: [] },
  };
}

/** Reconstruit un design complet depuis un design persisté (validation légère). */
export function normalizeDesign(raw) {
  if (!raw || typeof raw !== 'object' || !raw.format) return null;
  const fmt = FORMATS.find((f) => f.type === raw.format.type);
  const base = defaultDesign(fmt ? fmt.key : 'ig_feed_45');
  return {
    version: 2,
    format: {
      platform: raw.format.platform || base.format.platform,
      type: raw.format.type || base.format.type,
      width: Number(raw.format.width) || base.format.width,
      height: Number(raw.format.height) || base.format.height,
    },
    background: { color: raw.background?.color || '#111111' },
    elements: Array.isArray(raw.elements)
      ? raw.elements.filter((e) => e && e.id && e.type).map((e) => ({ ...e }))
      : [],
    carousel: Array.isArray(raw.carousel) ? raw.carousel.slice() : [],
    cover: raw.cover ?? null,
    timeline: Number(raw.version) >= 2 && raw.timeline && Array.isArray(raw.timeline.tracks)
      ? { fps: Number(raw.timeline.fps) || 30, tracks: raw.timeline.tracks }
      : convertV1ToV2Design(Array.isArray(raw.elements) ? raw.elements : []),
  };
}

/** Conversion design V1 (sans timeline) → design V2 (timeline reconstruit). */
function convertV1ToV2Design(elements) {
  const tracks = [];
  const byType = new Map();
  for (const el of elements) {
    if (!el || !el.id || !el.type) continue;
    const t = el.type;
    if (!byType.has(t)) {
      const track = { id: `tr-${t}-${tracks.length + 1}`, type: t, hidden: false, locked: false, clips: [] };
      byType.set(t, track);
      tracks.push(track);
    }
    const track = byType.get(t);
    track.clips.push({
      id: `clip-${el.id}`,
      type: el.type,
      start: Number(el.x) || 0,
      duration: Number(el.w) || Number(el.height) || 100,
      trackId: track.id,
      elementId: el.id,
    });
  }
  return { fps: 30, tracks };
}

export class EditorState {
  constructor(design = null) {
    this.design = normalizeDesign(design) || defaultDesign();
    this.selectedId = null;
    this.undoStack = [];
    this.redoStack = [];
    this._pending = null;
    this.onChange = null;
  }

  _notify() {
    if (typeof this.onChange === 'function') this.onChange(this);
  }

  _snapshot() {
    return JSON.stringify(this.design);
  }

  beginTransaction() {
    if (this._pending === null) this._pending = this._snapshot();
  }

  commitTransaction() {
    if (this._pending === null) return;
    const before = this._pending;
    this._pending = null;
    const after = this._snapshot();
    if (before !== after) {
      this.undoStack.push(before);
      if (this.undoStack.length > 40) this.undoStack.shift();
      this.redoStack = [];
      this._notify();
    }
  }

  _auto(fn) {
    this.beginTransaction();
    fn();
    this.commitTransaction();
  }

  undo() {
    if (!this.undoStack.length) return false;
    this._pending = null;
    this.redoStack.push(this._snapshot());
    this.design = JSON.parse(this.undoStack.pop());
    if (this.selectedId && !this.getElementById(this.selectedId)) {
      this.selectedId = null;
    }
    this._notify();
    return true;
  }

  redo() {
    if (!this.redoStack.length) return false;
    this._pending = null;
    this.undoStack.push(this._snapshot());
    this.design = JSON.parse(this.redoStack.pop());
    if (this.selectedId && !this.getElementById(this.selectedId)) {
      this.selectedId = null;
    }
    this._notify();
    return true;
  }

  getElementById(id) {
    return this.design.elements.find((e) => e.id === id) || null;
  }

  get selected() {
    return this.selectedId ? this.getElementById(this.selectedId) : null;
  }

  select(id) {
    if (this.selectedId === id) return;
    this.selectedId = id;
    this._notify();
  }

  addElement(el) {
    let added = null;
    this._auto(() => {
      added = { id: nextId(el.type || 'el'), rotation: 0, opacity: 1, ...el };
      this.design.elements.push(added);
      this.selectedId = added.id;
    });
    return added;
  }

  updateElement(id, patch) {
    this._auto(() => {
      const el = this.getElementById(id);
      if (el) Object.assign(el, patch);
    });
  }

  /** Mise à jour patchée d'un clip pendant un geste continu : sans transaction (le geste committera). */
  updateClipLive(trackId, clipId, patch) {
    const tr = (this.getTimeline().tracks || []).find((t) => t.id === trackId);
    const clip = (tr?.clips || []).find((c) => c.id === clipId);
    if (!clip) return;
    Object.assign(clip, patch);
  }

  /** Volume de piste pendant un geste continu : sans transaction (le geste committera). */
  setTrackVolumeLive(id, volume) {
    const tr = this.getTrackById(id);
    if (!tr) return;
    tr.volume = Math.min(1, Math.max(0, Number(volume) || 0));
  }

  /** Mise à jour pendant un geste continu : pas de transaction unitaire. */
  updateElementLive(id, patch) {
    const el = this.getElementById(id);
    if (el) Object.assign(el, patch);
  }

  removeElement(id) {
    this._auto(() => {
      this.design.elements = this.design.elements.filter((e) => e.id !== id);
      if (this.selectedId === id) this.selectedId = null;
    });
  }

  moveLayer(id, dir) {
    this._auto(() => {
      const els = this.design.elements;
      const i = els.findIndex((e) => e.id === id);
      if (i < 0) return;
      const j = dir === 'up' ? i + 1 : i - 1;
      if (j < 0 || j >= els.length) return;
      [els[i], els[j]] = [els[j], els[i]];
    });
  }

  bringToFront(id) {
    this._auto(() => {
      const els = this.design.elements;
      const i = els.findIndex((e) => e.id === id);
      if (i < 0) return;
      els.push(els.splice(i, 1)[0]);
    });
  }

  sendToBack(id) {
    this._auto(() => {
      const els = this.design.elements;
      const i = els.findIndex((e) => e.id === id);
      if (i < 0) return;
      els.unshift(els.splice(i, 1)[0]);
    });
  }

  setFormat(key) {
    this._auto(() => {
      const fmt = FORMATS.find((f) => f.key === key);
      if (!fmt) return;
      this.design = scaleDesign(this.design, fmt.width, fmt.height);
      this.design.format = {
        platform: fmt.platform,
        type: fmt.type,
        width: fmt.width,
        height: fmt.height,
      };
    });
  }

  setBackground(color) {
    this._auto(() => {
      this.design.background = { color };
    });
  }

  setCarousel(list) {
    this._auto(() => {
      this.design.carousel = list.slice();
    });
  }

  setCover(photoId) {
    this._auto(() => {
      this.design.cover = photoId;
    });
  }

  getTimeline() {
    if (!this.design.timeline) {
      this.design.timeline = { fps: 30, tracks: [] };
    }
    return this.design.timeline;
  }

  setTimeline(patch) {
    this._auto(() => {
      this.design.timeline = { ...this.getTimeline(), ...(patch || {}) };
      if (!Array.isArray(this.design.timeline.tracks)) this.design.timeline.tracks = [];
    });
  }

  addTrack(track) {
    this._auto(() => {
      this.getTimeline().tracks.push(track);
    });
    return track;
  }

  updateTrack(id, patch) {
    this._auto(() => {
      const tracks = this.getTimeline().tracks || [];
      const tr = tracks.find((t) => t.id === id);
      if (tr) Object.assign(tr, patch);
    });
  }

  removeTrack(id) {
    this._auto(() => {
      if (this.design.timeline) {
        this.design.timeline.tracks = (this.design.timeline.tracks || []).filter((t) => t.id !== id);
      }
    });
  }

  addClip(trackId, clip) {
    this._auto(() => {
      const tr = (this.getTimeline().tracks || []).find((t) => t.id === trackId);
      if (tr) tr.clips.push(clip);
    });
    return clip;
  }

  updateClip(trackId, clipId, patch) {
    this._auto(() => {
      const tr = (this.getTimeline().tracks || []).find((t) => t.id === trackId);
      const clip = (tr?.clips || []).find((c) => c.id === clipId);
      if (clip) Object.assign(clip, patch);
    });
  }

  removeClip(trackId, clipId) {
    this._auto(() => {
      const tr = (this.getTimeline().tracks || []).find((t) => t.id === trackId);
      if (!tr) return;
      tr.clips = (tr.clips || []).filter((c) => c.id !== clipId);
    });
  }

  moveClip(trackId, clipId, start) {
    this._auto(() => {
      const tr = (this.getTimeline().tracks || []).find((t) => t.id === trackId);
      const clip = (tr?.clips || []).find((c) => c.id === clipId);
      if (!clip) return;
      const target = Number(start) || 0;
      const delta = target - (Number(clip.start) || 0);
      const el = clip.elementId ? this.getElementById(clip.elementId) : null;
      if (el) el.x = (Number(el.x) || 0) + delta;
      clip.start = target;
    });
  }

  /** Déplacement pendant un geste continu : sans transaction (le geste committera). */
  moveClipLive(trackId, clipId, start) {
    const tr = (this.getTimeline().tracks || []).find((t) => t.id === trackId);
    const clip = (tr?.clips || []).find((c) => c.id === clipId);
    if (!clip) return;
    const target = Number(start) || 0;
    const delta = target - (Number(clip.start) || 0);
    const el = clip.elementId ? this.getElementById(clip.elementId) : null;
    if (el) el.x = (Number(el.x) || 0) + delta;
    clip.start = target;
  }

  resizeClip(trackId, clipId, duration) {
    this._auto(() => {
      const tr = (this.getTimeline().tracks || []).find((t) => t.id === trackId);
      const clip = (tr?.clips || []).find((c) => c.id === clipId);
      if (!clip) return;
      const dur = Math.max(0, Number(duration) || 0);
      clip.duration = dur;
      const el = clip.elementId ? this.getElementById(clip.elementId) : null;
      if (el) {
        el.w = dur;
        if (el.type === 'text') el.h = dur;
      }
    });
  }

  /** Redimensionnement pendant un geste continu : sans transaction (le geste committera). */
  resizeClipLive(trackId, clipId, duration) {
    const tr = (this.getTimeline().tracks || []).find((t) => t.id === trackId);
    const clip = (tr?.clips || []).find((c) => c.id === clipId);
    if (!clip) return;
    const dur = Math.max(0, Number(duration) || 0);
    clip.duration = dur;
    const el = clip.elementId ? this.getElementById(clip.elementId) : null;
    if (el) {
      el.w = dur;
      if (el.type === 'text') el.h = dur;
    }
  }

  cutClip(trackId, clipId, at) {
    this._auto(() => {
      const tr = (this.getTimeline().tracks || []).find((t) => t.id === trackId);
      const clip = (tr?.clips || []).find((c) => c.id === clipId);
      if (!clip) return;
      const start = Number(clip.start) || 0;
      const duration = Number(clip.duration) || 0;
      const cutAt = Number(at) || 0;
      if (!(cutAt > start && cutAt < start + duration)) return;
      const tailDuration = start + duration - cutAt;
      const srcEl = clip.elementId ? this.getElementById(clip.elementId) : null;
      if (srcEl) {
        const tailEl = JSON.parse(JSON.stringify(srcEl));
        tailEl.id = nextId('el');
        tailEl.x = cutAt;
        tailEl.w = tailDuration;
        if (tailEl.type === 'text') tailEl.h = tailDuration;
        this.design.elements.push(tailEl);
        clip.duration = cutAt - start;
        clip.elementId = tailEl.id;
      } else {
        clip.duration = cutAt - start;
      }
    });
  }

  addVideoClip(trackId, clip) {
    this._auto(() => {
      const tr = (this.getTimeline().tracks || []).find((t) => t.id === trackId);
      if (!tr) return;
      tr.clips.push(clip);
    });
    return clip;
  }

  duplicateClip(trackId, clipId) {
    let result = null;
    this._auto(() => {
      const tr = (this.getTimeline().tracks || []).find((t) => t.id === trackId);
      const clip = (tr?.clips || []).find((c) => c.id === clipId);
      if (!tr || !clip) return;
      const copy = JSON.parse(JSON.stringify(clip));
      copy.id = nextId('clip');
      copy.trackId = trackId;
      copy.start = (Number(clip.start) || 0) + (Number(clip.duration) || 0);
      copy.duration = Number(clip.duration) || 0;
      tr.clips.push(copy);
      result = copy;
    });
    return result;
  }

  splitClip(trackId, clipId, at) {
    this._auto(() => {
      const tr = (this.getTimeline().tracks || []).find((t) => t.id === trackId);
      const clip = (tr?.clips || []).find((c) => c.id === clipId);
      if (!tr || !clip) return null;
      const start = Number(clip.start) || 0;
      const duration = Number(clip.duration) || 0;
      const splitAt = Number(at) || 0;
      if (!(splitAt > start && splitAt < start + duration)) return null;
      const tailDuration = start + duration - splitAt;
      const tail = JSON.parse(JSON.stringify(clip));
      tail.id = nextId('clip');
      tail.start = splitAt;
      tail.duration = tailDuration;
      tail.elementId = null;
      tr.clips.push(tail);
      clip.duration = splitAt - start;
      return tail;
    });
  }

  selectTrack(id) {
    this._auto(() => {
      this.selectedId = id;
    });
  }

  setTrackHidden(id, hidden) {
    this._auto(() => {
      const tr = (this.getTimeline().tracks || []).find((t) => t.id === id);
      if (tr) tr.hidden = !!hidden;
    });
  }

  setTrackLocked(id, locked) {
    this._auto(() => {
      const tr = (this.getTimeline().tracks || []).find((t) => t.id === id);
      if (tr) tr.locked = !!locked;
    });
  }

  setFps(fps) {
    this._auto(() => {
      const f = Number(fps) || 30;
      if (f > 0) this.design.timeline.fps = f;
    });
  }

  getClipById(clipId) {
    const timeline = this.getTimeline();
    for (const tr of timeline.tracks || []) {
      const clip = (tr.clips || []).find((c) => c.id === clipId);
      if (clip) return { trackId: tr.id, ...clip };
    }
    return null;
  }

  selectClip(trackId, clipId) {
    this._auto(() => {
      this.selectedId = clipId;
      this._selectedTrackId = trackId || null;
    });
  }

  getSelectedClip() {
    const sel = this.selectedId ? this.getClipById(this.selectedId) : null;
    if (sel) return sel;
    const el = this.getElementById(this.selectedId);
    if (el) return { trackId: null, elementId: el.id, type: el.type, start: Number(el.x) || 0, duration: Number(el.w) || 0, ...el };
    return null;
  }

  getTrackById(id) {
    const tracks = this.getTimeline().tracks || [];
    return tracks.find((t) => t.id === id) || null;
  }

  setTrackVolume(id, volume) {
    this._auto(() => {
      const tr = this.getTrackById(id);
      if (!tr) return;
      tr.volume = Math.min(1, Math.max(0, Number(volume) || 0));
    });
  }

  setTrackSolo(id, solo) {
    this._auto(() => {
      const tr = this.getTrackById(id);
      if (!tr) return;
      tr.solo = !!solo;
    });
  }

  setTrackDucking(id, ducking) {
    this._auto(() => {
      const tr = this.getTrackById(id);
      if (!tr) return;
      tr.ducking = {
        enabled: !!(ducking && ducking.enabled),
        level: Math.min(1, Math.max(0, Number((ducking && ducking.level) ?? 0))),
      };
    });
  }

  toJSON() {
    return JSON.parse(this._snapshot());
  }

  static formatKeyOf(design) {
    const f = FORMATS.find(
      (x) => x.type === design?.format?.type && x.platform === design?.format?.platform
    );
    return f ? f.key : 'ig_feed_45';
  }
}
