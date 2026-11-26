import { publisherStore } from '../stores/publisherStore.js';
import { searchInstagramMusic } from '../services/sportApi.js?v=16';

/**
 * Résout la sélection musicale d'un brouillon Publisher.
 * Priorité : draft.music → design.ig_audio (anciens brouillons) →
 * designDocuments[].ig_audio (anciens brouillons par slide).
 * `music.cleared` marque une suppression explicite et masque le legacy.
 */
export function resolveDraftMusic(draft) {
  const music = draft?.music;
  if (music && music.cleared) return null;
  if (music) {
    const ig = music.ig_audio;
    if (music.trackId || music.title) {
      return {
        trackId: music.trackId ? String(music.trackId) : null,
        title: music.title || '',
        artist: music.artist || '',
        durationInMs: music.duration_in_ms ?? null,
        source: music.source || 'instagram',
      };
    }
    if (ig && ig.audio_id) {
      return {
        trackId: String(ig.audio_id),
        title: ig.title || '',
        artist: ig.artist || '',
        durationInMs: ig.duration_in_ms ?? null,
        source: music.source || 'instagram',
      };
    }
    if (music.local_track) {
      const t = music.local_track;
      return {
        trackId: t.track_id ? String(t.track_id) : null,
        title: t.title || '',
        artist: t.artist || '',
        durationInMs: t.duration_in_ms ?? t.duration ?? null,
        source: 'local',
      };
    }
  }
  const top = draft?.design?.ig_audio;
  if (top && top.audio_id) {
    return {
      trackId: String(top.audio_id),
      title: top.title || '',
      artist: top.artist || '',
      durationInMs: top.duration_in_ms ?? null,
      source: 'instagram',
    };
  }
  const docs = draft?.design?.designDocuments;
  if (Array.isArray(docs)) {
    for (const doc of docs) {
      const audio = doc && doc.ig_audio;
      if (audio && audio.audio_id) {
        return {
          trackId: String(audio.audio_id),
          title: audio.title || '',
          artist: audio.artist || '',
          durationInMs: audio.duration_in_ms ?? null,
          source: 'instagram',
        };
      }
    }
  }
  return null;
}

export class PublisherMusicStep {
  constructor(options = {}) {
    this.search = options.searchInstagramMusic || searchInstagramMusic;
    this.host = null;
    this.element = null;
    this._items = [];
    this._unsubscribe = null;
  }

  mount(host) {
    this.host = host;
    host.innerHTML = `
      <div class="music-step">
        <div class="music-step-current" data-music-current></div>
        <div class="pre-music-tools">
          <button type="button" class="pre-music-button" data-action="music-open" aria-haspopup="dialog" aria-expanded="false">♫ Choisir une musique Instagram</button>
        </div>
        <section class="pre-music-panel" data-music-panel hidden aria-label="Catalogue de musiques Instagram">
          <form class="pre-music-search" data-music-form>
            <input type="search" minlength="2" maxlength="80" placeholder="Rechercher un titre ou un artiste" aria-label="Rechercher une musique">
            <button type="submit">Rechercher</button>
            <button type="button" data-action="music-close" aria-label="Fermer">✕</button>
          </form>
          <p class="pre-music-status" data-music-status></p>
          <div class="pre-music-results" data-music-results></div>
        </section>
      </div>`;
    this.element = host.firstElementChild || host;
    this._bind();
    this._renderCurrent();
    this._unsubscribe = publisherStore.subscribe((state) => this._renderCurrent(state));
  }

  destroy() {
    if (this._unsubscribe) {
      this._unsubscribe();
      this._unsubscribe = null;
    }
    if (this.host) this.host.innerHTML = '';
    this.host = null;
    this.element = null;
    this._items = [];
  }

  _bind() {
    const root = this.element;
    root.querySelector('[data-action="music-open"]').addEventListener('click', () => {
      const panel = root.querySelector('[data-music-panel]');
      panel.hidden = !panel.hidden;
      if (!panel.hidden) {
        const input = panel.querySelector('input');
        if (input && typeof input.focus === 'function') input.focus();
      }
    });
    root.querySelector('[data-action="music-close"]').addEventListener('click', () => {
      root.querySelector('[data-music-panel]').hidden = true;
    });
    root.querySelector('[data-music-form]').addEventListener('submit', (event) => this._onSearch(event));
    root.querySelector('[data-music-results]').addEventListener('click', (event) => {
      const button = event.target && event.target.closest ? event.target.closest('[data-music-result]') : null;
      if (!button) return;
      const track = this._items[Number(button.dataset.musicIndex)];
      if (track) this._select(track);
    });
    root.querySelector('[data-music-current]').addEventListener('click', (event) => {
      const button = event.target && event.target.closest ? event.target.closest('[data-action="music-remove"]') : null;
      if (button) this._remove();
    });
  }

  async _onSearch(event) {
    if (event && typeof event.preventDefault === 'function') event.preventDefault();
    const root = this.element;
    const form = root.querySelector('[data-music-form]');
    const input = form ? form.querySelector('input') : null;
    const query = String(input?.value || '').trim();
    if (query.length < 2) return;
    const status = root.querySelector('[data-music-status]');
    const results = root.querySelector('[data-music-results]');
    if (status) status.textContent = 'Recherche…';
    if (results) results.innerHTML = '';
    try {
      const response = await this.search(query);
      const items = Array.isArray(response?.items) ? response.items : [];
      this._items = items;
      if (status) status.textContent = items.length ? `${items.length} résultat(s)` : 'Aucune musique trouvée.';
      if (results) {
        results.innerHTML = items.map((track, index) => `
          <button type="button" class="pre-music-result" data-music-result data-music-index="${index}">
            <span class="pre-music-note">♫</span>
            <span><strong>${this._esc(track.title || 'Titre inconnu')}</strong><small>${this._esc(track.display_artist || track.artist || 'Artiste inconnu')}</small></span>
            <span aria-hidden="true">＋</span>
          </button>`).join('');
      }
    } catch (error) {
      if (status) status.textContent = error?.message || 'Recherche de musique impossible.';
    }
  }

  _select(track) {
    if (!track?.audio_id) return;
    publisherStore.setMusic({
      trackId: String(track.audio_id),
      title: track.title || '',
      artist: track.display_artist || track.artist || '',
      duration_in_ms: track.duration_in_ms ?? null,
      source: 'instagram',
      cleared: false,
    });
    const panel = this.element?.querySelector('[data-music-panel]');
    if (panel) panel.hidden = true;
  }

  _remove() {
    publisherStore.setMusic({
      trackId: null,
      title: null,
      artist: null,
      duration_in_ms: null,
      source: null,
      cleared: true,
    });
  }

  _renderCurrent(state) {
    const host = this.element?.querySelector('[data-music-current]');
    if (!host) return;
    const selection = resolveDraftMusic((state && state.draft) || publisherStore.draft);
    if (!selection) {
      host.innerHTML = '<div class="music-step-empty">Aucune musique sélectionnée — vous pouvez continuer sans musique.</div>';
      return;
    }
    const sourceLabel = selection.source === 'local' ? 'Piste locale' : 'Catalogue Instagram';
    host.innerHTML = `
      <div class="music-step-selected">
        <span class="pre-music-note" aria-hidden="true">♫</span>
        <span class="music-step-info"><strong>${this._esc(selection.title || 'Piste sans titre')}</strong>${selection.artist ? `<small>${this._esc(selection.artist)}</small>` : ''}</span>
        <span class="music-step-source">${sourceLabel}</span>
        <button type="button" class="pre-music-button" data-action="music-remove">Retirer</button>
      </div>
      <p class="music-step-note">Piste sélectionnée · non intégrable à la publication actuelle.</p>`;
  }

  _esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
  }
}

export function createPublisherMusicStep(options = {}) {
  return new PublisherMusicStep(options);
}
