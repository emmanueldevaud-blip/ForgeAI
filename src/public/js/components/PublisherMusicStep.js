import { publisherStore } from '../stores/publisherStore.js';
import { getStoryAudioProposals, searchInstagramMusic } from '../services/sportApi.js?v=17';

/**
 * URL d'aperçu AUDIO lisible par <audio>.
 * Meta fournit `download_url` pour le fichier MP3 temporaire ;
 * `on_platform_audio_preview_link` est une page instagram.com, pas un flux audio.
 */
export function previewUrlFor(track) {
  const raw = track?.download_url
    || track?.preview_link
    || track?.preview_url
    || track?.audio_url
    || track?.preview;
  if (typeof raw !== 'string' || !raw.trim()) return '';
  try {
    const base = typeof window !== 'undefined' && window.location?.href
      ? window.location.href
      : 'http://localhost/';
    const url = new URL(raw.trim(), base);
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return '';
    const host = String(url.hostname || '').toLowerCase();
    if (host === 'instagram.com' || host.endsWith('.instagram.com')) return '';
    return url.href;
  } catch (error) {
    return '';
  }
}

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
    this.suggest = options.getStoryAudioProposals || getStoryAudioProposals;
    this.publicationId = options.publicationId ?? null;
    this.host = null;
    this.element = null;
    this._items = [];
    this._unsubscribe = null;
    this._suggestionRun = 0;
    this._suggestionMessage = '';
    this._autoSelected = false;
    // Les aperçus restent en mémoire : ils ne sont jamais écrits dans le
    // brouillon ni envoyés à publish() (A07 = brouillon créatif seulement).
    this._previews = new Map();
    this._audio = null;
    this._previewTrackId = null;
  }

  mount(host) {
    this.host = host;
    host.innerHTML = `
      <div class="music-step">
        <div class="music-step-current" data-music-current></div>
        <p class="music-step-suggestion" data-music-suggestion hidden></p>
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
    this._suggestInitialMusic();
  }

  destroy() {
    this._suggestionRun += 1;
    this._stopPreview();
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
      // Toute intervention manuelle annule une présélection encore en vol.
      this._suggestionRun += 1;
      this._setSuggestionMessage('');
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
      if (button) {
        const track = this._items[Number(button.dataset.musicIndex)];
        if (track) this._select(track);
        return;
      }
      const preview = event.target && event.target.closest ? event.target.closest('[data-music-preview]') : null;
      if (!preview) return;
      const track = this._items[Number(preview.dataset.musicIndex)];
      if (track) this._togglePreview(track);
    });
    root.querySelector('[data-music-current]').addEventListener('click', (event) => {
      const closest = event.target && event.target.closest ? event.target.closest.bind(event.target) : () => null;
      const preview = closest('[data-action="music-preview"]');
      if (preview?.dataset?.action === 'music-preview') {
        const trackId = String(publisherStore.draft?.music?.trackId || '');
        this._togglePreview({ audio_id: trackId, preview_link: this._previews.get(trackId) });
        return;
      }
      const button = closest('[data-action="music-remove"]');
      if (button?.dataset?.action === 'music-remove') this._remove();
    });
  }

  _setSuggestionMessage(message = '') {
    this._suggestionMessage = String(message || '');
    const el = this.element?.querySelector?.('[data-music-suggestion]');
    if (!el) return;
    el.textContent = this._suggestionMessage;
    el.hidden = !this._suggestionMessage;
  }

  /**
   * À l'ouverture de l'étape, présélectionne la première piste proposée par
   * l'analyse IA des photos du brouillon Story. Un choix explicite (ou un
   * retrait) n'est jamais écrasé, y compris si la réponse arrive tard.
   */
  async _suggestInitialMusic() {
    const draft = publisherStore.draft || {};
    if (draft.format && draft.format !== 'story') return;
    if (draft.music?.cleared || resolveDraftMusic(draft)) return;
    const publicationId = this.publicationId ?? draft.id;
    if (!publicationId) return;

    const run = ++this._suggestionRun;
    this._setSuggestionMessage('Présélection IA en cours…');
    try {
      const response = await this.suggest(publicationId);
      if (run !== this._suggestionRun || !this.element) return;
      const items = Array.isArray(response?.items) ? response.items : [];
      const track = items.find((item) => item?.audio_id);
      const current = publisherStore.draft || {};
      if (track && !current.music?.cleared && !resolveDraftMusic(current)) {
        this._autoSelected = true;
        this._select(track, { auto: true });
        this._setSuggestionMessage('');
        return;
      }
      this._setSuggestionMessage(track ? '' : (response?.reason || 'Aucune présélection IA disponible.'));
    } catch (error) {
      if (run !== this._suggestionRun || !this.element) return;
      this._setSuggestionMessage(error?.message || 'Présélection IA indisponible.');
    }
  }

  async _onSearch(event) {
    if (event && typeof event.preventDefault === 'function') event.preventDefault();
    const root = this.element;
    const form = root.querySelector('[data-music-form]');
    const input = form ? form.querySelector('input') : null;
    const query = String(input?.value || '').trim();
    if (query.length < 2) return;
    this._suggestionRun += 1;
    this._setSuggestionMessage('');
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
        results.innerHTML = items.map((track, index) => {
          const preview = previewUrlFor(track);
          if (preview) this._previews.set(String(track.audio_id), preview);
          return `
          <div class="pre-music-item">
            <button type="button" class="pre-music-result" data-music-result data-music-index="${index}">
              <span class="pre-music-note">♫</span>
              <span><strong>${this._esc(track.title || 'Titre inconnu')}</strong><small>${this._esc(track.display_artist || track.artist || 'Artiste inconnu')}</small></span>
              <span aria-hidden="true">＋</span>
            </button>
            ${preview ? `<button type="button" class="pre-music-preview" data-music-preview data-music-index="${index}"
                aria-label="Écouter l'aperçu de ${this._esc(track.title || 'cette piste')}" aria-pressed="false">▶</button>` : ''}
          </div>`;
        }).join('');
      }
    } catch (error) {
      if (status) status.textContent = error?.message || 'Recherche de musique impossible.';
    }
  }

  _select(track, { auto = false } = {}) {
    if (!track?.audio_id) return;
    this._autoSelected = Boolean(auto);
    const trackId = String(track.audio_id);
    const preview = previewUrlFor(track);
    if (preview) this._previews.set(trackId, preview);
    this._stopPreview();
    publisherStore.setMusic({
      trackId: String(track.audio_id),
      title: track.title || '',
      artist: track.display_artist || track.artist || '',
      duration_in_ms: track.duration_in_ms ?? null,
      source: 'instagram',
      cleared: false,
      preselectedBy: auto ? 'ai' : null,
    });
    const panel = this.element?.querySelector('[data-music-panel]');
    if (panel) panel.hidden = true;
  }

  _remove() {
    this._autoSelected = false;
    this._stopPreview();
    publisherStore.setMusic({
      trackId: null,
      title: null,
      artist: null,
      duration_in_ms: null,
      source: null,
      cleared: true,
      preselectedBy: null,
    });
  }

  /** Aperçu local uniquement : aucun octet audio n'entre dans le brouillon. */
  _togglePreview(track) {
    const trackId = String(track?.audio_id || '');
    const url = previewUrlFor(track) || this._previews.get(trackId);
    if (url) this._previews.set(trackId, url);
    const status = this.element?.querySelector?.('[data-music-status]');
    if (!trackId || !url) {
      if (status) status.textContent = 'Aperçu audio indisponible pour cette piste.';
      return;
    }
    if (this._previewTrackId === trackId && this._audio && !this._audio.paused) {
      this._stopPreview();
      return;
    }
    this._stopPreview();
    const doc = typeof document !== 'undefined' ? document : null;
    if (!doc || typeof doc.createElement !== 'function') return;
    const audio = doc.createElement('audio');
    audio.preload = 'none';
    audio.src = url;
    audio.addEventListener?.('ended', () => {
      if (this._audio === audio) this._stopPreview();
    });
    audio.addEventListener?.('error', () => {
      if (this._audio === audio) {
        this._stopPreview();
        if (status) status.textContent = 'Aperçu audio indisponible.';
      }
    });
    this._audio = audio;
    this._previewTrackId = trackId;
    this._syncPreviewButtons();
    const play = audio.play?.();
    this._syncPreviewButtons();
    if (play && typeof play.catch === 'function') {
      play.catch(() => {
        if (this._audio === audio) {
          this._stopPreview();
          if (status) status.textContent = 'Aperçu audio indisponible.';
        }
      });
    }
  }

  _stopPreview() {
    if (this._audio) {
      try { this._audio.pause?.(); } catch (error) { /* lecteur déjà arrêté */ }
      this._audio = null;
    }
    this._previewTrackId = null;
    this._syncPreviewButtons();
  }

  _syncPreviewButtons() {
    const playing = Boolean(this._audio && !this._audio.paused);
    this.element?.querySelectorAll?.('[data-music-preview], [data-action="music-preview"]')?.forEach((node) => {
      const index = node.dataset?.musicIndex;
      const trackId = index !== undefined
        ? String(this._items[Number(index)]?.audio_id || '')
        : String(publisherStore.draft?.music?.trackId || '');
      const active = playing && Boolean(trackId) && trackId === this._previewTrackId;
      node.setAttribute?.('aria-pressed', String(active));
      node.classList?.toggle?.('is-playing', active);
      if (typeof node.textContent === 'string') {
        node.textContent = active ? '❚❚' : (node.dataset?.action === 'music-preview' ? '▶ Écouter' : '▶');
      }
    });
  }

  _renderCurrent(state) {
    const host = this.element?.querySelector('[data-music-current]');
    if (!host) return;
    const draft = (state && state.draft) || publisherStore.draft;
    const selection = resolveDraftMusic(draft);
    if (!selection) {
      host.innerHTML = '<div class="music-step-empty">Aucune musique sélectionnée — vous pouvez continuer sans musique.</div>';
      return;
    }
    const auto = this._autoSelected || draft?.music?.preselectedBy === 'ai';
    const sourceLabel = auto
      ? 'Présélection IA · Instagram'
      : (selection.source === 'local' ? 'Piste locale' : 'Catalogue Instagram');
    const note = auto
      ? 'Présélection IA basée sur les photos de la Story : vérifiez ou remplacez le morceau. Piste sélectionnée, non intégrable à la publication actuelle : elle ne sera pas publiée avec la Story.'
      : 'Brouillon créatif : piste sélectionnée, non intégrable à la publication actuelle. Elle ne sera pas publiée avec la Story.';
    const preview = this._previews.get(String(selection.trackId || ''));
    host.innerHTML = `
      <div class="music-step-selected">
        <span class="pre-music-note" aria-hidden="true">♫</span>
        <span class="music-step-info"><strong>${this._esc(selection.title || 'Piste sans titre')}</strong>${selection.artist ? `<small>${this._esc(selection.artist)}</small>` : ''}</span>
        <span class="music-step-source">${sourceLabel}</span>
        ${preview ? `<button type="button" class="pre-music-button pre-music-preview" data-action="music-preview" aria-pressed="false" aria-label="Écouter l'aperçu">▶ Écouter</button>` : ''}
        <button type="button" class="pre-music-button" data-action="music-remove">Retirer</button>
      </div>
      <p class="music-step-note">${note}</p>`;
  }

  _esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
  }
}

export function createPublisherMusicStep(options = {}) {
  return new PublisherMusicStep(options);
}
