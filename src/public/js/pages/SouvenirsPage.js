import { getSouvenirs, photoFileUrl } from '../services/photosApi.js?v=8';

const INTRO_MS = 3200;
const KIND_LABELS = { person: 'Personne', place: 'Lieu', event: 'Événement' };
const KB_VARIANTS = ['kb-1', 'kb-2', 'kb-3', 'kb-4'];

// Musique embarquée (CC0, voir /music/CREDITS.txt) + fichier local optionnel.
const MUSIC_TRACKS = [
  { value: '/music/lovely-piano.mp3', label: 'Piano doux' },
  { value: '/music/calm-piano.mp3', label: 'Piano calme' },
  { value: '/music/infinite-peace.mp3', label: 'Paix infinie' },
];

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

function formatDate(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' });
}

export class SouvenirsPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.stories = [];
    this.storyIndex = -1;
    this.current = null;
    this.photoIndex = -1;
    this.playing = false;
    this.timer = null;
    this.slideMs = 6000;
    this.layerIndex = 0;
    this.introPending = false;
    this.musicUrl = null;
    this.localMusicUrl = null;
    this.loading = false;
    this._onKey = this._onKey.bind(this);
  }

  async initialize() {}

  render() {
    this.element = document.createElement('div');
    this.element.className = 'page-content souvenirs-page';
    this.element.innerHTML = `
      <div class="page-header">
        <div class="page-header-left">
          <h1>Souvenirs</h1>
          <p class="page-subtitle">Vos photos regroupées en histoires : personnes, lieux, événements.</p>
        </div>
        <div class="page-header-actions">
          <button type="button" class="btn btn-secondary" data-action="regen">Régénérer</button>
          <button type="button" class="btn btn-secondary" data-action="fullscreen">Plein écran</button>
          <button type="button" class="btn btn-secondary" data-action="back">Retour</button>
        </div>
      </div>

      <div class="souvenirs-chips" data-chips></div>

      <div class="souvenirs-stage" data-stage tabindex="-1">
        <div class="souvenirs-layer" data-layer="0"></div>
        <div class="souvenirs-layer" data-layer="1"></div>
        <div class="souvenirs-intro" data-intro hidden>
          <span class="souvenirs-intro-kind" data-intro-kind></span>
          <h2 data-intro-title></h2>
          <p data-intro-meta></p>
        </div>
        <div class="souvenirs-caption" data-caption hidden>
          <span class="souvenirs-caption-title" data-caption-title></span>
          <span class="souvenirs-caption-meta" data-caption-meta></span>
        </div>
        <div class="souvenirs-dots" data-dots></div>
        <p class="souvenirs-empty" data-empty hidden>
          Aucun souvenir à afficher. Importez d’abord des photos dans Photos.
        </p>
        <div class="souvenirs-controls">
          <button type="button" class="btn btn-secondary btn-sm" data-action="prev" title="Photo précédente">◀</button>
          <button type="button" class="btn btn-primary btn-sm" data-action="play">Lancer</button>
          <button type="button" class="btn btn-secondary btn-sm" data-action="next" title="Photo suivante">▶</button>
          <label class="souvenirs-control">Durée
            <select class="form-control form-control-sm" data-duration>
              <option value="4000">4 s</option>
              <option value="6000" selected>6 s</option>
              <option value="8000">8 s</option>
              <option value="10000">10 s</option>
            </select>
          </label>
          <label class="souvenirs-control">Musique
            <select class="form-control form-control-sm" data-music>
              <option value="">Aucune</option>
              ${MUSIC_TRACKS.map((track) => `<option value="${track.value}">${esc(track.label)}</option>`).join('')}
              <option value="local">Fichier local…</option>
            </select>
          </label>
          <label class="souvenirs-control">Volume
            <input type="range" data-volume min="0" max="1" step="0.05" value="0.7">
          </label>
          <button type="button" class="btn btn-secondary btn-sm" data-action="mute">Son</button>
          <input type="file" accept="audio/*" data-music-file hidden>
        </div>
      </div>

      <p class="souvenirs-help">Espace : lecture / pause · ← → : photo · F : plein écran</p>
      <p class="souvenirs-credits">Musique libre de droits (CC0) — <a href="/music/CREDITS.txt" target="_blank" rel="noopener">crédits</a></p>
      <audio data-audio loop preload="none"></audio>
    `;
    this._bind();
    return this.element;
  }

  destroy() {
    this._stop();
    const audio = this._audio();
    audio.pause();
    audio.removeAttribute('src');
    if (this.localMusicUrl) {
      URL.revokeObjectURL(this.localMusicUrl);
      this.localMusicUrl = null;
    }
    document.removeEventListener('keydown', this._onKey);
    this.element?.remove();
    this.element = null;
  }

  // ------------------------------------------------------------- données
  async load(options = {}) {
    if (!this.element || this.loading) return;
    this.loading = true;
    const subtitle = this.element.querySelector('[data-subtitle]');
    try {
      const params = { count: 8 };
      if (options.seed != null) params.seed = options.seed;
      const result = await getSouvenirs(params);
      this.stories = result?.stories || [];
      this._renderChips();
      const empty = this.element.querySelector('[data-empty]');
      if (!this.stories.length) {
        empty.hidden = false;
        this.current = null;
        this._stop();
        return;
      }
      empty.hidden = true;
      if (subtitle) subtitle.textContent = `${this.stories.length} souvenir(s) — lecture aléatoire, personnes, lieux et événements.`;
      this._openStory(0, { intro: true });
      if (options.autoplay) this._play();
    } catch (error) {
      console.error('[souvenirs] chargement impossible:', error);
      if (subtitle) subtitle.textContent = error.message || 'Chargement impossible';
    } finally {
      this.loading = false;
    }
  }

  // ------------------------------------------------------------- lecture
  _openStory(index, { intro = true } = {}) {
    const story = this.stories[index];
    if (!story || !story.photo_ids?.length) return;
    this.storyIndex = index;
    this.current = story;
    this.photoIndex = -1;
    this.introPending = intro;
    this._showIntro(story);
    this._renderChips();
    this._renderCaption(story);
    this._renderDots(story);
    this._prefetch(story, 0);
    if (intro) {
      this._showIntro(story);
      this._schedule(INTRO_MS);
    } else {
      this._advance();
    }
  }

  _advance() {
    const story = this.current;
    if (!story) return;
    this.photoIndex += 1;
    if (this.photoIndex >= story.photo_ids.length) {
      const next = (this.storyIndex + 1) % this.stories.length;
      this._openStory(next, { intro: true });
      return;
    }
    this._paint(story.photo_ids[this.photoIndex]);
    this._renderCaption(story);
    this._renderDots(story);
    this._prefetch(story, this.photoIndex + 1);
    this._schedule(this.slideMs);
  }

  _tick() {
    this.timer = null;
    if (!this.playing) return;
    if (!this.element?.isConnected) {
      this._stop();
      return;
    }
    if (this.introPending) {
      this.introPending = false;
      this._hideIntro();
    }
    this._advance();
  }

  _schedule(ms) {
    this._clearTimer();
    if (!this.playing) return;
    this.timer = setTimeout(() => this._tick(), ms);
  }

  _clearTimer() {
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
  }

  _play() {
    if (!this.current) return;
    this.playing = true;
    this._updatePlayButton();
    if (this.introPending) this._schedule(INTRO_MS);
    else this._schedule(this.slideMs);
    const audio = this._audio();
    if (audio.src) audio.play().catch(() => {});
  }

  _pause() {
    this.playing = false;
    this._clearTimer();
    this._updatePlayButton();
    this._audio().pause();
  }

  _stop() {
    this.playing = false;
    this._clearTimer();
    this._updatePlayButton();
  }

  _updatePlayButton() {
    const btn = this.element?.querySelector('[data-action="play"]');
    if (btn) btn.textContent = this.playing ? 'Pause' : 'Lancer';
  }

  // ------------------------------------------------------------- rendu
  _showIntro(story) {
    const intro = this.element.querySelector('[data-intro]');
    if (!intro) return;
    this.element.querySelector('[data-intro-kind]').textContent = KIND_LABELS[story.kind] || 'Souvenir';
    this.element.querySelector('[data-intro-title]').textContent = story.title;
    const meta = [story.count ? `${story.count} photos` : '', formatDate(story.date_from)]
      .filter(Boolean).join(' · ');
    this.element.querySelector('[data-intro-meta]').textContent = meta;
    intro.hidden = false;
  }

  _hideIntro() {
    const intro = this.element.querySelector('[data-intro]');
    if (intro) intro.hidden = true;
  }

  _paint(photoId) {
    const stage = this.element.querySelector('[data-stage]');
    if (!stage) return;
    const nextIndex = this.layerIndex === 0 ? 1 : 0;
    const nextLayer = stage.querySelector(`[data-layer="${nextIndex}"]`);
    const prevLayer = stage.querySelector(`[data-layer="${this.layerIndex}"]`);
    if (!nextLayer) return;
    const img = document.createElement('img');
    img.className = `souvenirs-photo ${KB_VARIANTS[Math.floor(Math.random() * KB_VARIANTS.length)]}`;
    img.alt = '';
    img.decoding = 'async';
    img.style.setProperty('--slide-ms', `${this.slideMs}ms`);
    img.addEventListener('load', () => {
      nextLayer.classList.add('is-active');
      prevLayer?.classList.remove('is-active');
    }, { once: true });
    img.addEventListener('error', () => {
      if (this.playing && this.current) this._advance();
    }, { once: true });
    nextLayer.replaceChildren(img);
    img.src = photoFileUrl(photoId, 'large');
    this.layerIndex = nextIndex;
  }

  _renderCaption(story) {
    const caption = this.element.querySelector('[data-caption]');
    if (!caption || !story) return;
    this.element.querySelector('[data-caption-title]').textContent = story.title;
    const meta = [KIND_LABELS[story.kind], formatDate(story.date_from)].filter(Boolean).join(' · ');
    this.element.querySelector('[data-caption-meta]').textContent = meta;
    caption.hidden = false;
  }

  _renderDots(story) {
    const dots = this.element.querySelector('[data-dots]');
    if (!dots || !story) return;
    const total = story.photo_ids.length;
    const position = Math.min(this.photoIndex + (this.introPending ? 1 : 0), total);
    dots.innerHTML = Array.from({ length: total }, (_, i) =>
      `<span class="souvenirs-dot ${i === this.photoIndex ? 'is-current' : ''} ${i < position ? 'is-seen' : ''}"></span>`
    ).join('');
  }

  _renderChips() {
    const chips = this.element.querySelector('[data-chips]');
    if (!chips) return;
    chips.innerHTML = this.stories.map((story, index) => `
      <button type="button" class="souvenirs-chip ${index === this.storyIndex ? 'is-current' : ''}"
              data-story="${index}" title="${esc(story.title)}">
        <span class="souvenirs-chip-kind">${esc(KIND_LABELS[story.kind] || '')}</span>
        <span class="souvenirs-chip-title">${esc(story.title)}</span>
      </button>`).join('');
    chips.querySelectorAll('[data-story]').forEach((btn) => {
      btn.addEventListener('click', () => {
        this._openStory(Number(btn.dataset.story), { intro: true });
        if (!this.playing) this._play();
      });
    });
  }

  _prefetch(story, index) {
    const id = story?.photo_ids?.[index];
    if (!id) return;
    const img = new Image();
    img.src = photoFileUrl(id, 'large');
  }

  _audio() {
    return this.element.querySelector('[data-audio]');
  }

  // ------------------------------------------------------------- musique
  _setMusic(value) {
    const audio = this._audio();
    if (!audio) return;
    if (!value) {
      audio.pause();
      audio.removeAttribute('src');
      this.musicUrl = null;
      return;
    }
    audio.src = value;
    this.musicUrl = value;
    audio.volume = Number(this.element.querySelector('[data-volume]')?.value ?? 0.7);
    if (this.playing) audio.play().catch(() => {});
  }

  // ------------------------------------------------------------- events
  _bind() {
    this.element.querySelector('[data-action="back"]')?.addEventListener('click', () => {
      this.router.navigate('/photos');
    });
    this.element.querySelector('[data-action="play"]')?.addEventListener('click', () => {
      if (this.playing) this._pause(); else this._play();
    });
    this.element.querySelector('[data-action="prev"]')?.addEventListener('click', () => this._jump(-1));
    this.element.querySelector('[data-action="next"]')?.addEventListener('click', () => this._jump(1));
    this.element.querySelector('[data-action="regen"]')?.addEventListener('click', () => {
      this.load({ seed: Math.floor(Math.random() * 1e9), autoplay: this.playing });
    });
    this.element.querySelector('[data-action="fullscreen"]')?.addEventListener('click', () => {
      const stage = this.element.querySelector('[data-stage]');
      if (document.fullscreenElement) document.exitFullscreen?.();
      else stage?.requestFullscreen?.();
    });
    this.element.querySelector('[data-duration]')?.addEventListener('change', (e) => {
      this.slideMs = Number(e.target.value) || 6000;
      if (this.playing && !this.introPending) this._schedule(this.slideMs);
    });
    this.element.querySelector('[data-volume]')?.addEventListener('input', (e) => {
      this._audio().volume = Number(e.target.value);
      if (this._audio().muted && Number(e.target.value) > 0) {
        this._audio().muted = false;
        const muteBtn = this.element.querySelector('[data-action="mute"]');
        if (muteBtn) muteBtn.textContent = 'Son';
      }
    });
    this.element.querySelector('[data-action="mute"]')?.addEventListener('click', (e) => {
      const audio = this._audio();
      audio.muted = !audio.muted;
      e.currentTarget.textContent = audio.muted ? 'Muet' : 'Son';
    });
    this.element.querySelector('[data-music]')?.addEventListener('change', (e) => {
      const value = e.target.value;
      if (value === 'local') {
        this.element.querySelector('[data-music-file]')?.click();
        return;
      }
      this._setMusic(value);
    });
    this.element.querySelector('[data-music-file]')?.addEventListener('change', (e) => {
      const file = e.target.files?.[0];
      if (!file) return;
      if (this.localMusicUrl) URL.revokeObjectURL(this.localMusicUrl);
      this.localMusicUrl = URL.createObjectURL(file);
      this._setMusic(this.localMusicUrl);
    });
    document.addEventListener('keydown', this._onKey);
  }

  _jump(delta) {
    if (!this.current) return;
    const story = this.current;
    let index = this.photoIndex + delta;
    if (index < 0) {
      const prev = (this.storyIndex - 1 + this.stories.length) % this.stories.length;
      this._openStory(prev, { intro: false });
      return;
    }
    if (index >= story.photo_ids.length) {
      const next = (this.storyIndex + 1) % this.stories.length;
      this._openStory(next, { intro: false });
      return;
    }
    this.introPending = false;
    this._hideIntro();
    this.photoIndex = index;
    this._paint(story.photo_ids[index]);
    this._renderCaption(story);
    this._renderDots(story);
    this._prefetch(story, index + 1);
    if (this.playing) this._schedule(this.slideMs);
  }

  _onKey(event) {
    if (!this.element?.isConnected) {
      document.removeEventListener('keydown', this._onKey);
      return;
    }
    const tag = event.target?.tagName;
    if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return;
    if (event.key === ' ') {
      event.preventDefault();
      if (this.playing) this._pause(); else this._play();
    } else if (event.key === 'ArrowRight') {
      this._jump(1);
    } else if (event.key === 'ArrowLeft') {
      this._jump(-1);
    } else if (event.key === 'f' || event.key === 'F') {
      const stage = this.element.querySelector('[data-stage]');
      if (document.fullscreenElement) document.exitFullscreen?.();
      else stage?.requestFullscreen?.();
    }
  }
}

export function createSouvenirsPage(router) {
  return new SouvenirsPage(router);
}
