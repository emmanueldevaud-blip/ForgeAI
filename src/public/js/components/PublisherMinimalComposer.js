/**
 * PublisherMinimalComposer — étape « Composer » volontairement minimale.
 *
 * Périmètre (refonte progressive) :
 *   - Story et Reel : plusieurs médias affichés, réordonnables et supprimables ;
 *   - jusqu'à 3 calques de texte par média, modifiés DIRECTEMENT sur la photo
 *     (sans champ de saisie dans le panneau) : tap sur le fond pour ajouter,
 *     tap sur un texte pour l'éditer, poignées d'angle pour taille/rotation ;
 *   - Story uniquement : mini-barre couleur/police/gras/italique/souligné/
 *     alignement/fond, rendue fidèlement dans l'export JPEG du canvas ;
 *   - aucun outil annexe (stickers, dessin, timeline, audio, éditeur lourd, etc.).
 *
 * La sélection des médias reste dans l'étape « Médias » (déjà multi-sélection).
 * Ce composant gère l'aperçu, l'ordre, la suppression et la synchronisation du
 * design v2 pour les médias et les calques retenus, sans toucher au parcours
 * Post/Carrousel.
 */

import { publisherStore } from '../stores/publisherStore.js';

const TEXT_ID = 'minimal-overlay-text';
const MAX_TEXT_LAYERS = 3;
const MAX_TEXT_LENGTH = 2200;
const TEXT_LAYER_IDS = [TEXT_ID, `${TEXT_ID}-2`, `${TEXT_ID}-3`];
// Positions fixes par emplacement : réordonner un calque change son empilement, pas sa place.
const TEXT_LAYER_Y = [960, 760, 1160];
const DESIGN_WIDTH = 1080;

/** Outils « fun » mais bornés : peu de choix, tous tactiles, aucun éditeur lourd. */
const COLOR_SWATCHES = ['#ffffff', '#000000', '#ff3b5c', '#ffcc00', '#34c759', '#0a84ff', '#ff9f0a', '#bf5af2'];
const FONT_CHOICES = [
  { value: 'Arial', label: 'A' },
  { value: 'Impact', label: 'IMP' },
  { value: 'Georgia', label: 'Geo' },
  { value: 'Trebuchet MS', label: 'Tré' },
];
const FONT_CSS = {
  Arial: 'Arial, sans-serif',
  Impact: 'Impact, Haettenschweiler, sans-serif',
  Georgia: 'Georgia, serif',
  'Trebuchet MS': '"Trebuchet MS", sans-serif',
};
const ALIGNMENTS = [
  { value: 'left', label: '←' },
  { value: 'center', label: '↔' },
  { value: 'right', label: '→' },
];
const CORNERS = ['nw', 'ne', 'sw', 'se'];

const DEFAULT_STYLE = {
  color: '#ffffff',
  font: 'Arial',
  bold: true,
  italic: false,
  underline: false,
  align: 'center',
  background: false,
  backgroundColor: '#000000',
  size: 72,
  rotation: 0,
};

const FORMATS = {
  story: { width: 1080, height: 1920, type: 'story_916', platform: 'instagram' },
  reel: { width: 1080, height: 1920, type: 'reel_916', platform: 'instagram' },
};

/** Identifiant photo numérique, compatible avec les ids préfixés `photo_`. */
function asPhotoId(value) {
  const raw = String(value ?? '').replace(/^photo_/, '');
  if (!/^\d+$/.test(raw)) return null;
  const id = Number(raw);
  return Number.isFinite(id) ? id : null;
}

/** Emplacement d'un calque à partir de son identifiant de design. */
function asLayerSlot(id) {
  const slot = TEXT_LAYER_IDS.indexOf(String(id));
  return slot >= 0 ? slot : null;
}

/** Échappement HTML minimal pour les contenus saisis. */
function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[char]));
}

/** Texte non vide uniquement : un calque vide ne produit pas d'élément de design. */
function cleanText(value) {
  const raw = String(value ?? '');
  return raw.trim() ? raw : '';
}

function clamp(value, min, max) {
  const number = Number(value);
  return Number.isFinite(number) ? Math.min(Math.max(number, min), max) : min;
}

/** Style d'un calque, toujours normalisé avant lecture/écriture. */
function normalizeStyle(value = {}) {
  const raw = value && typeof value === 'object' ? value : {};
  const hex = (candidate, fallback) => (
    /^#[0-9a-f]{6}$/i.test(String(candidate ?? '')) ? String(candidate) : fallback
  );
  return {
    color: hex(raw.color, DEFAULT_STYLE.color),
    font: FONT_CSS[raw.font] ? String(raw.font) : DEFAULT_STYLE.font,
    bold: raw.bold === undefined ? DEFAULT_STYLE.bold : Boolean(raw.bold),
    italic: Boolean(raw.italic),
    underline: Boolean(raw.underline),
    align: ALIGNMENTS.some((a) => a.value === raw.align) ? raw.align : DEFAULT_STYLE.align,
    background: Boolean(raw.background),
    backgroundColor: hex(raw.backgroundColor, DEFAULT_STYLE.backgroundColor),
    size: clamp(raw.size ?? DEFAULT_STYLE.size, 24, 220),
    rotation: clamp(raw.rotation ?? 0, -180, 180),
  };
}

/** Style inline appliqué à l'overlay : cqw = taille relative à la largeur du stage. */
function styleCss(style) {
  const s = normalizeStyle(style);
  const size = (s.size / DESIGN_WIDTH * 100).toFixed(2);
  return `font-size:${size}cqw;`
    + `font-family:${FONT_CSS[s.font]};`
    + `font-weight:${s.bold ? 700 : 400};`
    + `font-style:${s.italic ? 'italic' : 'normal'};`
    + `text-decoration:${s.underline ? 'underline' : 'none'};`
    + `text-align:${s.align};`
    + `color:${s.color};`
    + (s.background ? `background-color:${s.backgroundColor}a6;` : '')
    + `transform:translate(-50%,-50%) rotate(${s.rotation}deg);`;
}

function blankLayer() {
  return { id: TEXT_LAYER_IDS[0], text: '', style: { ...DEFAULT_STYLE } };
}

/** Calques acceptés sous forme de chaîne, d'objets `{ id, text }` ou d'éléments design. */
export function normalizeTextLayers(value) {
  const source = Array.isArray(value) ? value.slice(0, MAX_TEXT_LAYERS) : [value];
  return source.map((entry, index) => {
    const isObject = entry !== null && typeof entry === 'object';
    const id = isObject && entry.id ? String(entry.id) : TEXT_LAYER_IDS[index];
    const text = String((isObject ? entry.text : entry) ?? '');
    const style = isObject ? normalizeStyle(entry.style || entry) : { ...DEFAULT_STYLE };
    return { id, text, style };
  });
}

/** Élément de design v2 d'un calque, centré sur le média (slot 0 = centre). */
export function buildOverlayTextElement(text, slot = 0, style = {}) {
  const index = Number.isInteger(slot) && slot >= 0 && slot < MAX_TEXT_LAYERS ? slot : 0;
  const s = normalizeStyle(style);
  return {
    id: TEXT_LAYER_IDS[index],
    type: 'text',
    text: cleanText(text),
    x: 540,
    y: TEXT_LAYER_Y[index],
    w: 864,
    h: 180,
    size: s.size,
    font: s.font,
    color: s.color,
    bold: s.bold,
    italic: s.italic,
    underline: s.underline,
    align: s.align,
    shadow: true,
    outline: false,
    background: s.background,
    backgroundColor: s.backgroundColor,
    opacity: 1,
    rotation: s.rotation,
  };
}

/** Éléments texte du design dans l'ordre d'empilement (le dernier est au-dessus). */
function buildTextElements(layers) {
  return normalizeTextLayers(layers)
    .filter((layer) => cleanText(layer.text))
    .map((layer, index) => buildOverlayTextElement(layer.text, asLayerSlot(layer.id) ?? index, layer.style));
}

/** Slides + designs Story reconstruits depuis les médias du brouillon.
 *
 * `layersByMedia` (tableau de tableaux) donne 3 calques indépendants par photo.
 * Sans lui, le comportement historique est conservé : texte sur la 1ʳᵉ slide.
 */
export function buildStoryDesign(media = [], text = '', layersByMedia = null) {
  const items = Array.isArray(media) ? media : [];
  const perMedia = Array.isArray(layersByMedia) && layersByMedia.some((entry) => Array.isArray(entry))
    ? layersByMedia
    : null;
  const overlays = buildTextElements(text);
  const slides = items.map((item, index) => ({
    type: 'photo',
    photo_indices: [index],
  }));
  const designDocuments = items.map((item, index) => {
    const photoId = asPhotoId(item?.photoId ?? item?.id);
    return {
      version: 2,
      format: { ...FORMATS.story },
      background: {
        type: 'photo',
        photo_id: photoId,
        crop: item?.crop || { x: 0, y: 0, w: 1, h: 1 },
      },
      elements: perMedia
        ? buildTextElements(perMedia[index] || [])
        : (index === 0 ? overlays.map((element) => ({ ...element })) : []),
      carousel: photoId !== null ? [photoId] : [],
      timeline: { fps: 30, tracks: [] },
    };
  });

  return { slides, designDocuments };
}

/** Design Reel v2 : on ne remplace que les éléments, le reste est conservé.
 *
 * `design.elements` reste le jeu du média affiché (compatibilité render), et
 * `design.mediaLayers` conserve les jeux de calques de chaque média.
 */
export function buildReelDesign(existingDesign = {}, text = '', layersByMedia = null) {
  const design = { ...(existingDesign || {}) };
  design.version = 2;
  design.format = { ...FORMATS.reel };
  design.elements = buildTextElements(text);
  if (Array.isArray(layersByMedia) && layersByMedia.some((entry) => Array.isArray(entry))) {
    design.mediaLayers = layersByMedia.map((layers) => buildTextElements(layers));
  }
  return design;
}

export class PublisherMinimalComposer {
  constructor(options = {}) {
    this.format = options.format === 'story' ? 'story' : 'reel';
    this.onBack = options.onBack || (() => {});
    this.element = null;
    this.activeIndex = 0;
    this.activeLayerIndex = 0;
    // Un jeu de calques par média : sélectionner une photo change de jeu.
    this.mediaLayers = [];
    this.layers = [blankLayer()];
  }

  mount(host) {
    if (!host) return;
    this.activeIndex = 0;
    this.mediaLayers = this._media().map((_, index) => this._currentLayers(index));
    this.layers = this.mediaLayers[0] || [blankLayer()];
    if (!this.mediaLayers.length) this.mediaLayers.push(this.layers);
    this.activeLayerIndex = 0;
    this.element = document.createElement('div');
    this.element.className = 'publisher-minimal-composer';
    host.appendChild(this.element);
    this._render();
  }

  /** Médias du brouillon, dans l'ordre de publication. */
  _media() {
    const draft = publisherStore.draft || {};
    return Array.isArray(draft.media) ? draft.media : [];
  }

  /** Média affiché dans le grand aperçu (index toujours dans les limites). */
  _activeMedia() {
    const media = this._media();
    if (!media.length) return null;
    this.activeIndex = Math.min(Math.max(this.activeIndex, 0), media.length - 1);
    return media[this.activeIndex];
  }

  /** Calques déjà présents dans le design d'un média (utile au retour arrière). */
  _currentLayers(index = this.activeIndex) {
    const draft = publisherStore.draft || {};
    const elements = this.format === 'story'
      ? draft.design?.designDocuments?.[index]?.elements || []
      : (draft.design?.designDocuments?.[index]?.elements
        || (index === 0 ? draft.design?.elements || [] : []));
    if (!Array.isArray(elements)) return [blankLayer()];
    const layers = normalizeTextLayers(
      elements.filter((el) => el && asLayerSlot(el.id) !== null).slice(0, MAX_TEXT_LAYERS),
    ).filter((layer) => asLayerSlot(layer.id) !== null);
    return layers.length ? layers : [blankLayer()];
  }

  /** Met en mémoire les textes édités sur la photo ; le repli sert à save(). */
  _syncTextsFromDom(allowFallback = false) {
    const read = (node) => String(node?.value ?? node?.textContent ?? '').slice(0, MAX_TEXT_LENGTH);
    const nodes = Array.from(this.element?.querySelectorAll?.('[data-pmc-layer-text]') || []);
    if (nodes.length) {
      nodes.forEach((node, index) => {
        if (this.layers[index]) this.layers[index].text = read(node);
      });
      return;
    }
    // Repli pour les hôtes DOM simplifiés : seul le premier calque est exposé.
    if (!allowFallback) return;
    const first = this.element?.querySelector?.('[data-pmc-text]');
    if (first && this.layers[0]) this.layers[0].text = read(first);
  }

  /** Bande de médias : aperçu, ordre et suppression, sans outil annexe. */
  _renderMediaStrip() {
    const media = this._media();
    if (!media.length) return '';
    return media.map((item, index) => {
      const photoId = asPhotoId(item?.photoId ?? item?.id);
      const thumb = item?.type === 'video'
        ? '<span class="pmc-thumb-icon" aria-hidden="true">🎬</span>'
        : `<img class="pmc-thumb-img" src="${esc(item?.thumbnail_url || item?.url)}" alt="">`;
      const active = index === this.activeIndex ? ' active' : '';
      return `
        <div class="pmc-media-item${active}" data-pmc-media-item data-index="${index}"
             data-media-id="${esc(item?.id)}" data-photo-id="${photoId ?? ''}">
          <button type="button" class="pmc-media-select" data-action="pmc-select" data-index="${index}"
                  aria-label="Afficher le média ${index + 1}" aria-pressed="${index === this.activeIndex}">
            <span class="pmc-thumb">${thumb}</span>
            <span class="pmc-media-index">${index + 1}</span>
          </button>
          <span class="pmc-media-controls">
            <button type="button" class="pmc-media-btn" data-action="pmc-move-up" data-index="${index}"
                    aria-label="Monter le média ${index + 1}" ${index === 0 ? 'disabled' : ''}>↑</button>
            <button type="button" class="pmc-media-btn" data-action="pmc-move-down" data-index="${index}"
                    aria-label="Descendre le média ${index + 1}" ${index === media.length - 1 ? 'disabled' : ''}>↓</button>
            <button type="button" class="pmc-media-btn pmc-media-btn--remove" data-action="pmc-remove" data-index="${index}"
                    aria-label="Retirer le média ${index + 1}">×</button>
          </span>
        </div>`;
    }).join('');
  }

  _renderStage() {
    const item = this._activeMedia();
    if (!item) return '<div class="pmc-empty">Aucun média sélectionné</div>';
    if (item.type === 'video') {
      return `<video class="pmc-media" src="${esc(item.url)}" poster="${esc(item.thumbnail_url)}" muted playsinline controls preload="metadata"></video>`;
    }
    return `<img class="pmc-media" src="${esc(item.url || item.thumbnail_url)}" alt="Média à composer">`;
  }

  /**
   * Calques éditables DIRECTEMENT sur la photo : chaque texte est contenteditable.
   * Une seule barre d'actions tactile suit le calque actif (ordre + suppression).
   * Le panneau latéral ne contient aucun champ de saisie.
   */
  _renderOverlays() {
    return this.layers.map((layer, index) => {
      const text = cleanText(layer.text);
      const slot = asLayerSlot(layer.id) ?? index;
      const active = index === this.activeLayerIndex;
      // Poignées sur tous les calques ; seules celles du calque actif sont
      // affichées en CSS. Ainsi un changement de sélection n'a pas à reconstruire
      // le DOM (le focus du texte reste intact). Le Reel est exclu : son rendu
      // vidéo FFmpeg n'intègre pas les éléments texte du design.
      const handles = this.format === 'story'
        ? CORNERS.map((corner) => `<span class="pmc-handle pmc-handle--${corner}" data-pmc-handle data-corner="${corner}" contenteditable="false" aria-hidden="true"></span>`).join('')
        : '';
      return `<div class="pmc-overlay pmc-overlay--layer pmc-overlay--slot-${slot}${text ? '' : ' pmc-overlay--placeholder'}${active ? ' active' : ''}"
                data-pmc-overlay data-layer-index="${index}" data-index="${index}"
                data-pmc-layer-text="${index}"
                ${index === 0 ? 'data-pmc-text ' : ''}contenteditable="true" spellcheck="false"
                role="textbox" aria-label="Texte du calque ${index + 1}"
                aria-multiline="true" aria-placeholder="Touchez pour écrire"
                data-placeholder="Touchez pour écrire"
                style="z-index:${10 + index};${styleCss(layer.style)}">${esc(text)}${handles}</div>`;
    }).join('');
  }

  /** Mini-barre de style : couleurs, polices, G/I/S, alignement et fond. */
  _renderStyleRow() {
    // Le rendu final d'un Reel (FFmpeg) n'honore pas les éléments texte : on
    // évite de proposer des outils dont l'effet ne serait visible qu'en aperçu.
    if (this.format !== 'story') return '';
    const style = normalizeStyle(this.layers[this.activeLayerIndex]?.style);
    const swatches = COLOR_SWATCHES.map((color) => `
      <button type="button" class="pmc-swatch${style.color === color ? ' active' : ''}"
              data-style="color" data-value="${color}" style="--swatch:${color}"
              aria-label="Couleur ${color}" aria-pressed="${style.color === color}"></button>`).join('');
    const fonts = FONT_CHOICES.map((font) => `
      <button type="button" class="pmc-style-btn${style.font === font.value ? ' active' : ''}"
              data-style="font" data-value="${esc(font.value)}" aria-pressed="${style.font === font.value}"
              title="Police ${esc(font.value)}">${esc(font.label)}</button>`).join('');
    const toggle = (key, label, pressed, title) => `
      <button type="button" class="pmc-style-btn${pressed ? ' active' : ''}" data-style="${key}"
              aria-label="${title}" aria-pressed="${pressed}" title="${title}">${label}</button>`;
    const aligns = ALIGNMENTS.map((align) => `
      <button type="button" class="pmc-style-btn${style.align === align.value ? ' active' : ''}"
              data-style="align" data-value="${align.value}"
              aria-label="Aligner ${align.value === 'left' ? 'à gauche' : align.value === 'right' ? 'à droite' : 'au centre'}"
              aria-pressed="${style.align === align.value}">${align.label}</button>`).join('');
    return `<div class="pmc-style-row" data-pmc-style-row role="group" aria-label="Style du calque">
        <span class="pmc-style-group" data-pmc-colors>${swatches}</span>
        <span class="pmc-style-group" data-pmc-fonts>${fonts}</span>
        <span class="pmc-style-group" data-pmc-format>
          ${toggle('bold', 'G', style.bold, 'Gras')}
          ${toggle('italic', 'I', style.italic, 'Italique')}
          ${toggle('underline', 'S', style.underline, 'Souligné')}
          ${aligns}
          ${toggle('background', 'F', style.background, 'Fond')}
        </span>
      </div>`;
  }

  /** Une seule barre d'actions, attachée au calque actif (plus de doublon par calque). */
  _renderLayerActions() {
    const index = this.activeLayerIndex;
    const slot = asLayerSlot(this.layers[index]?.id) ?? index;
    return `<div class="pmc-overlay-actions pmc-overlay--slot-${slot} active"
                data-pmc-overlay-actions data-layer-index="${index}" data-index="${index}"
                style="z-index:${20 + this.layers.length}">
        <div class="pmc-action-row">
          <button type="button" class="pmc-overlay-btn" data-action="pmc-layer-up" data-index="${index}"
                  aria-label="Monter le calque ${index + 1}" ${index === this.layers.length - 1 ? 'disabled' : ''}>↑</button>
          <button type="button" class="pmc-overlay-btn" data-action="pmc-layer-down" data-index="${index}"
                  aria-label="Descendre le calque ${index + 1}" ${index === 0 ? 'disabled' : ''}>↓</button>
          <button type="button" class="pmc-overlay-btn pmc-overlay-btn--remove" data-action="pmc-layer-remove"
                  data-index="${index}" aria-label="Supprimer le calque ${index + 1}">×</button>
        </div>
        ${this._renderStyleRow()}
      </div>`;
  }

  /** Puces de sélection uniquement : aucun champ d'édition dans le panneau. */
  _renderLayerList() {
    return this.layers.map((layer, index) => {
      const active = index === this.activeLayerIndex;
      const preview = cleanText(layer.text) || `Calque ${index + 1}`;
      return `<button type="button" class="pmc-layer-chip${active ? ' active' : ''}"
                   data-pmc-layer-chip data-action="pmc-layer-select" data-index="${index}"
                   aria-pressed="${active}" aria-label="Sélectionner le calque ${index + 1}">
            <span class="pmc-layer-index">${index + 1}</span>
            <span class="pmc-layer-preview">${esc(preview)}</span>
          </button>`;
    }).join('');
  }

  _render() {
    if (!this.element) return;
    const media = this._media();
    const limitReached = this.layers.length >= MAX_TEXT_LAYERS;
    const mediaLabel = media.length ? `Média ${this.activeIndex + 1} / ${media.length}` : 'Aucun média';
    this.element.innerHTML = `
      <div class="pmc-preview" data-pmc-preview>
        <div class="pmc-stage" data-pmc-stage>
          ${this._renderStage()}
          ${this._renderOverlays()}
          ${this._renderLayerActions()}
          <span class="pmc-media-count" data-pmc-media-count aria-live="polite">${mediaLabel}</span>
        </div>
        <div class="pmc-media-strip" data-pmc-media-strip ${media.length > 1 ? '' : 'hidden'}>
          <div class="pmc-media-list" data-pmc-media-list>${this._renderMediaStrip()}</div>
        </div>
      </div>
      <div class="pmc-panel" role="group" aria-labelledby="pmc-layer-label">
        <span class="pmc-label" id="pmc-layer-label">Calques de texte (${this.layers.length} / ${MAX_TEXT_LAYERS})</span>
        <div class="pmc-layer-list" data-pmc-layer-list>${this._renderLayerList()}</div>
        <button type="button" class="pmc-layer-add" data-action="pmc-add-layer"
                aria-label="Ajouter un calque" ${limitReached ? 'disabled' : ''}>+</button>
        <p class="pmc-layer-limit" data-pmc-layer-limit ${limitReached ? '' : 'hidden'}>Limite de 3 calques atteinte</p>
      </div>
    `;
    this._bindEvents();
  }

  _bindEvents() {
    // Les calques sont édités sur la photo (contenteditable), pas dans le panneau.
    const editable = Array.from(this.element?.querySelectorAll?.('[data-pmc-layer-text]') || []);
    const bindText = (node, index) => {
      if (!node) return;
      node.addEventListener?.('input', () => {
        const raw = String(node.textContent ?? node.value ?? '');
        const text = raw.length > MAX_TEXT_LENGTH ? raw.slice(0, MAX_TEXT_LENGTH) : raw;
        if (text !== raw) {
          if (node.isContentEditable) node.textContent = text;
          else node.value = text;
        }
        if (this.layers[index]) this.layers[index].text = text;
        this._updatePreview();
        // Écriture continue : aucune frappe ne doit être perdue si l'utilisateur
        // quitte l'étape par Précédent, Retour, Brouillon ou un changement de format.
        this._writeDesign();
      });
      node.addEventListener?.('focus', () => {
        if (index !== this.activeLayerIndex) this._selectLayer(index);
        else this._refreshLayerState();
      });
      node.addEventListener?.('click', () => this._selectLayer(index));
    };
    editable.forEach((node) => bindText(node, Number(node.dataset?.index ?? 0)));
    if (!editable.length) bindText(this.element?.querySelector?.('[data-pmc-text]'), 0);

    // Mobile uniquement : tap sur le fond = nouveau calque directement focusé.
    // Sur desktop, le bouton "+" du panneau est le seul point d'entrée (pas de doublon).
    // Le test est fait au clic (et non au montage) pour suivre les changements
    // de viewport sans dépendre du cache du navigateur.
    const stage = this.element?.querySelector?.('[data-pmc-stage]');
    stage?.addEventListener?.('click', (event) => {
      const touch = typeof window !== 'undefined'
        && typeof window.matchMedia === 'function'
        && window.matchMedia('(hover: none), (max-width: 899px)').matches;
      if (!touch) return;
      const target = event?.target;
      if (target?.closest?.('[data-pmc-overlay], [data-pmc-overlay-actions], [data-style], [data-pmc-handle], [data-action], [data-pmc-media-count], video')) return;
      if (this._addLayer()) this._focusLayer(this.activeLayerIndex);
    });

    const bindAll = (selector, handler) => {
      this.element?.querySelectorAll?.(selector).forEach((node) => {
        node.addEventListener('click', () => handler(Number(node.dataset?.index)));
      });
    };
    bindAll('[data-action="pmc-select"]', (index) => this._selectMedia(index));
    bindAll('[data-action="pmc-move-up"]', (index) => this._moveMedia(index, -1));
    bindAll('[data-action="pmc-move-down"]', (index) => this._moveMedia(index, 1));
    bindAll('[data-action="pmc-remove"]', (index) => this._removeMedia(index));
    bindAll('[data-action="pmc-layer-select"]', (index) => this._selectLayer(index));
    bindAll('[data-action="pmc-layer-up"]', (index) => this._moveLayer(index, 1));
    bindAll('[data-action="pmc-layer-down"]', (index) => this._moveLayer(index, -1));
    bindAll('[data-action="pmc-layer-remove"]', (index) => this._removeLayer(index));

    const add = this.element?.querySelector?.('[data-action="pmc-add-layer"]');
    if (add) add.addEventListener('click', () => this._addLayer());

    // Outils de style du calque actif (mini-barre sur la photo).
    this.element?.querySelectorAll?.('[data-style]')?.forEach((node) => {
      node.addEventListener?.('click', (event) => {
        event?.stopPropagation?.();
        this._applyStyle(node.dataset?.style, node.dataset?.value);
      });
    });

    // Poignées aux angles du texte actif : agrandir et tourner au doigt.
    this.element?.querySelectorAll?.('[data-pmc-handle]')?.forEach((node) => {
      node.addEventListener?.('pointerdown', (event) => this._startTransform(event, node));
    });
  }

  _selectMedia(index) {
    const media = this._media();
    if (!Number.isInteger(index) || index < 0 || index >= media.length) return;
    this._syncTextsFromDom();
    this.mediaLayers[this.activeIndex] = this.layers;
    this.activeIndex = index;
    this.layers = this.mediaLayers[index] || (this.mediaLayers[index] = this._currentLayers(index));
    this.activeLayerIndex = Math.min(this.activeLayerIndex, this.layers.length - 1);
    this._render();
    this._writeDesign();
  }

  /** Déplace un média et resynchronise immédiatement le design v2. */
  _moveMedia(index, delta) {
    const media = this._media();
    const target = index + delta;
    if (!Number.isInteger(index) || index < 0 || index >= media.length
      || target < 0 || target >= media.length) return;

    const activeId = media[this.activeIndex]?.id;
    // Les calques suivent leur photo dans l'ordre de publication.
    const [movedLayers] = this.mediaLayers.splice(index, 1);
    if (movedLayers) this.mediaLayers.splice(target, 0, movedLayers);
    if (typeof publisherStore.reorderMedia === 'function') {
      publisherStore.reorderMedia(index, target);
    } else {
      const [item] = media.splice(index, 1);
      media.splice(target, 0, item);
      media.forEach((m, i) => { m.order = i; });
    }
    const next = media.findIndex((m) => String(m.id) === String(activeId));
    this.activeIndex = next >= 0 ? next : Math.min(this.activeIndex, media.length - 1);
    this.save();
    this._render();
  }

  /** Retire un média et resynchronise immédiatement le design v2. */
  _removeMedia(index) {
    const media = this._media();
    if (!Number.isInteger(index) || index < 0 || index >= media.length) return;
    const remaining = media.length - 1;
    const id = media[index]?.id;
    this.mediaLayers.splice(index, 1);
    if (typeof publisherStore.removeMedia === 'function') {
      publisherStore.removeMedia(id);
    } else {
      media.splice(index, 1);
      media.forEach((m, i) => { m.order = i; });
    }
    this.activeIndex = Math.min(index, Math.max(0, remaining - 1));
    this.layers = this.mediaLayers[this.activeIndex] || [blankLayer()];
    if (!this.mediaLayers[this.activeIndex]) this.mediaLayers[this.activeIndex] = this.layers;
    this.activeLayerIndex = Math.min(this.activeLayerIndex, this.layers.length - 1);
    this.save();
    this._render();
  }

  _selectLayer(index) {
    if (!Number.isInteger(index) || index < 0 || index >= this.layers.length) return;
    this._syncTextsFromDom();
    this.activeLayerIndex = index;
    this._refreshLayerState();
  }

  /** Active un calque sans reconstruire le DOM (le focus doit rester sur le texte). */
  _refreshLayerState() {
    const index = this.activeLayerIndex;
    Array.from(this.element?.querySelectorAll?.('[data-pmc-overlay]') || []).forEach((node, nodeIndex) => {
      node.classList?.toggle?.('active', nodeIndex === index);
    });
    Array.from(this.element?.querySelectorAll?.('[data-pmc-layer-chip]') || []).forEach((node, nodeIndex) => {
      node.classList?.toggle?.('active', nodeIndex === index);
      node.setAttribute?.('aria-pressed', String(nodeIndex === index));
    });

    // Une seule barre d'actions : elle suit le calque actif au lieu d'être
    // désactivée parce qu'elle est la première de la liste.
    const actions = this.element?.querySelector?.('[data-pmc-overlay-actions]');
    if (actions) {
      const slot = asLayerSlot(this.layers[index]?.id) ?? index;
      actions.className = `pmc-overlay-actions pmc-overlay--slot-${slot} active`;
      actions.dataset.index = String(index);
      actions.dataset.layerIndex = String(index);
      const up = actions.querySelector?.('[data-action="pmc-layer-up"]');
      const down = actions.querySelector?.('[data-action="pmc-layer-down"]');
      const remove = actions.querySelector?.('[data-action="pmc-layer-remove"]');
      if (up) {
        up.disabled = index === this.layers.length - 1;
        up.dataset.index = String(index);
        up.setAttribute?.('aria-label', `Monter le calque ${index + 1}`);
      }
      if (down) {
        down.disabled = index === 0;
        down.dataset.index = String(index);
        down.setAttribute?.('aria-label', `Descendre le calque ${index + 1}`);
      }
      if (remove) {
        remove.dataset.index = String(index);
        remove.setAttribute?.('aria-label', `Supprimer le calque ${index + 1}`);
      }
    }
    this._refreshStyleState();
  }

  /** Applique un outil de style au calque actif et écrit le design. */
  _applyStyle(key, value) {
    if (this.format !== 'story') return;
    const layer = this.layers[this.activeLayerIndex];
    if (!layer) return;
    const style = normalizeStyle(layer.style);
    if (key === 'color' && /^#[0-9a-f]{6}$/i.test(String(value))) style.color = value;
    else if (key === 'font' && FONT_CSS[value]) style.font = value;
    else if (key === 'bold') style.bold = !style.bold;
    else if (key === 'italic') style.italic = !style.italic;
    else if (key === 'underline') style.underline = !style.underline;
    else if (key === 'background') style.background = !style.background;
    else if (key === 'align' && ALIGNMENTS.some((entry) => entry.value === value)) style.align = value;
    else return;
    layer.style = style;
    this._applyLayerStyle(this.activeLayerIndex);
    this._writeDesign();
  }

  /** Met à jour l'overlay sans reconstruire le DOM (focus et curseur préservés). */
  _applyLayerStyle(index) {
    const node = this.element?.querySelector?.(`[data-pmc-layer-text="${index}"]`);
    const layer = this.layers[index];
    if (!node || !layer) return;
    if (typeof node.style?.setProperty === 'function') {
      node.style.cssText = `z-index:${10 + index};${styleCss(layer.style)}`;
    }
    this._refreshStyleState();
  }

  /** Synchronise les boutons de style avec le calque actif. */
  _refreshStyleState() {
    const style = normalizeStyle(this.layers[this.activeLayerIndex]?.style);
    this.element?.querySelectorAll?.('[data-style]')?.forEach((node) => {
      const key = node.dataset?.style;
      let pressed = false;
      if (key === 'color') pressed = node.dataset?.value === style.color;
      else if (key === 'font') pressed = node.dataset?.value === style.font;
      else if (key === 'align') pressed = node.dataset?.value === style.align;
      else if (key === 'bold') pressed = style.bold;
      else if (key === 'italic') pressed = style.italic;
      else if (key === 'underline') pressed = style.underline;
      else if (key === 'background') pressed = style.background;
      node.classList?.toggle?.('active', pressed);
      node.setAttribute?.('aria-pressed', String(pressed));
    });
  }

  /** Poignée d'angle du texte : taille par la distance, rotation par l'angle. */
  _startTransform(event, node) {
    if (this.format !== 'story') return;
    const layer = this.layers[this.activeLayerIndex];
    if (!layer || !event) return;
    event.preventDefault?.();
    event.stopPropagation?.();
    const overlay = node?.closest?.('[data-pmc-overlay]');
    const rect = overlay?.getBoundingClientRect?.();
    const win = typeof window !== 'undefined' ? window : null;
    if (!rect || !win?.addEventListener) return;
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    const startStyle = normalizeStyle(layer.style);
    const startDist = Math.max(1, Math.hypot(event.clientX - cx, event.clientY - cy));
    const startAngle = Math.atan2(event.clientY - cy, event.clientX - cx);
    const move = (ev) => {
      if (!ev || typeof ev.clientX !== 'number') return;
      const dist = Math.max(1, Math.hypot(ev.clientX - cx, ev.clientY - cy));
      const angle = Math.atan2(ev.clientY - cy, ev.clientX - cx);
      const style = normalizeStyle(layer.style);
      style.size = clamp(startStyle.size * dist / startDist, 24, 220);
      style.rotation = clamp(startStyle.rotation + (angle - startAngle) * 180 / Math.PI, -180, 180);
      layer.style = style;
      this._applyLayerStyle(this.activeLayerIndex);
      this._writeDesign();
    };
    const end = () => {
      win.removeEventListener?.('pointermove', move);
      win.removeEventListener?.('pointerup', end);
      win.removeEventListener?.('pointercancel', end);
    };
    win.addEventListener('pointermove', move);
    win.addEventListener('pointerup', end);
    win.addEventListener('pointercancel', end);
  }

  /** Donne le focus au texte éditable d'un calque (clavier mobile). */
  _focusLayer(index) {
    const node = this.element?.querySelector?.(`[data-pmc-layer-text="${index}"]`);
    node?.focus?.();
    return node;
  }

  /** Ajoute un calque libre, sans dépasser la limite de 3. */
  _addLayer() {
    this._syncTextsFromDom();
    if (this.layers.length >= MAX_TEXT_LAYERS) return false;
    const used = new Set(this.layers.map((layer) => layer.id));
    const slot = TEXT_LAYER_IDS.findIndex((id) => !used.has(id));
    this.layers.push({
      id: TEXT_LAYER_IDS[slot < 0 ? this.layers.length : slot],
      text: '',
      style: { ...DEFAULT_STYLE },
    });
    this.activeLayerIndex = this.layers.length - 1;
    this._render();
    this._focusLayer(this.activeLayerIndex);
    this._writeDesign();
    return true;
  }

  /** `delta > 0` monte le calque devant les autres, `delta < 0` le descend derrière. */
  _moveLayer(index, delta) {
    this._syncTextsFromDom();
    const target = index + delta;
    if (!Number.isInteger(index) || index < 0 || index >= this.layers.length
      || target < 0 || target >= this.layers.length) return;
    [this.layers[index], this.layers[target]] = [this.layers[target], this.layers[index]];
    this.activeLayerIndex = target;
    this._render();
    this._writeDesign();
  }

  _removeLayer(index) {
    this._syncTextsFromDom();
    if (!Number.isInteger(index) || index < 0 || index >= this.layers.length) return;
    this.layers.splice(index, 1);
    if (!this.layers.length) this.layers = [blankLayer()];
    this.activeLayerIndex = Math.min(index, this.layers.length - 1);
    this._render();
    this._writeDesign();
  }

  _updatePreview() {
    const overlays = Array.from(this.element?.querySelectorAll?.('[data-pmc-overlay]') || []);
    const activeNode = this.element?.ownerDocument?.activeElement
      || (typeof document !== 'undefined' ? document.activeElement : null);
    const apply = (node, index) => {
      if (!node) return;
      const text = cleanText(this.layers[index]?.text);
      // Ne pas réécrire le noeud en cours de frappe : cela casserait le curseur.
      // Les poignées sont conservées lors de la réécriture d'un calque inactif.
      if (node !== activeNode) {
        const handles = Array.from(node.querySelectorAll?.('[data-pmc-handle]') || []);
        node.textContent = text;
        handles.forEach((handle) => node.appendChild(handle));
      }
      node.classList?.toggle?.('pmc-overlay--placeholder', !text);
    };
    if (overlays.length) overlays.forEach((node, index) => apply(node, index));
    else apply(this.element?.querySelector?.('[data-pmc-overlay]'), 0);
    this._refreshLayerState();
    const previews = Array.from(this.element?.querySelectorAll?.('.pmc-layer-preview') || []);
    previews.forEach((node, index) => {
      const text = cleanText(this.layers[index]?.text);
      node.textContent = text || `Calque ${index + 1}`;
    });
  }

  /** Écrit le design v2 depuis l'état en mémoire (déjà resynchronisé). */
  _writeDesign() {
    const media = this._media();
    const perMedia = media.map((_, index) => {
      const layers = index === this.activeIndex ? this.layers : (this.mediaLayers[index] || []);
      return layers
        .filter((layer) => cleanText(layer.text))
        .map((layer) => ({ id: layer.id, text: layer.text, style: layer.style }));
    });
    const active = perMedia[this.activeIndex] || [];

    if (this.format === 'story') {
      const { slides, designDocuments } = buildStoryDesign(media, '', perMedia);
      publisherStore.updateStorySlides(slides, designDocuments);
    } else {
      publisherStore.updateDesign(buildReelDesign(publisherStore.draft?.design || {}, active, perMedia));
    }
    return true;
  }

  /** Appelée par le wizard avant de quitter l'étape compose. */
  save() {
    this._syncTextsFromDom(true);
    return this._writeDesign();
  }

  destroy() {
    if (this.element?.parentNode) {
      this.element.parentNode.removeChild(this.element);
    }
    this.element = null;
  }
}

export function createPublisherMinimalComposer(options) {
  return new PublisherMinimalComposer(options);
}
