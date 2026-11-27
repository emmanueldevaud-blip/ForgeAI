/**
 * PublisherMinimalComposer — étape « Composer » volontairement minimale.
 *
 * Périmètre (refonte progressive) :
 *   - Story et Reel : plusieurs médias affichés, réordonnables et supprimables ;
 *   - jusqu'à 3 calques de texte modifiés DIRECTEMENT sur la photo (sans champ
 *     de saisie dans le panneau) : tap sur le fond pour ajouter, tap sur un
 *     texte pour l'éditer, barre d'actions tactile pour l'ordre et la suppression ;
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

/** Calques acceptés sous forme de chaîne ou d'objets `{ id, text }`. */
export function normalizeTextLayers(value) {
  const source = Array.isArray(value) ? value.slice(0, MAX_TEXT_LAYERS) : [value];
  return source.map((entry, index) => {
    const isObject = entry !== null && typeof entry === 'object';
    const id = isObject && entry.id ? String(entry.id) : TEXT_LAYER_IDS[index];
    return { id, text: String((isObject ? entry.text : entry) ?? '') };
  });
}

/** Élément de design v2 d'un calque, centré sur le média (slot 0 = centre). */
export function buildOverlayTextElement(text, slot = 0) {
  const index = Number.isInteger(slot) && slot >= 0 && slot < MAX_TEXT_LAYERS ? slot : 0;
  return {
    id: TEXT_LAYER_IDS[index],
    type: 'text',
    text: cleanText(text),
    x: 540,
    y: TEXT_LAYER_Y[index],
    w: 864,
    h: 180,
    size: 72,
    font: 'Arial',
    color: '#ffffff',
    bold: true,
    italic: false,
    align: 'center',
    shadow: true,
    outline: false,
    background: false,
    backgroundColor: '#000000',
    opacity: 1,
    rotation: 0,
  };
}

/** Éléments texte du design dans l'ordre d'empilement (le dernier est au-dessus). */
function buildTextElements(text) {
  return normalizeTextLayers(text)
    .filter((layer) => cleanText(layer.text))
    .map((layer, index) => buildOverlayTextElement(layer.text, asLayerSlot(layer.id) ?? index));
}

/** Slides + designs Story reconstruits depuis les médias du brouillon. */
export function buildStoryDesign(media = [], text = '') {
  const items = Array.isArray(media) ? media : [];
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
      elements: index === 0 ? overlays.map((element) => ({ ...element })) : [],
      carousel: photoId !== null ? [photoId] : [],
      timeline: { fps: 30, tracks: [] },
    };
  });

  return { slides, designDocuments };
}

/** Design Reel v2 : on ne remplace que les éléments, le reste est conservé. */
export function buildReelDesign(existingDesign = {}, text = '') {
  const design = { ...(existingDesign || {}) };
  design.version = 2;
  design.format = { ...FORMATS.reel };
  design.elements = buildTextElements(text);
  return design;
}

export class PublisherMinimalComposer {
  constructor(options = {}) {
    this.format = options.format === 'story' ? 'story' : 'reel';
    this.onBack = options.onBack || (() => {});
    this.element = null;
    this.activeIndex = 0;
    this.activeLayerIndex = 0;
    this.layers = [{ id: TEXT_LAYER_IDS[0], text: '' }];
  }

  mount(host) {
    if (!host) return;
    this.layers = this._currentLayers();
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

  /** Calques déjà présents dans le design (utile en cas de retour arrière). */
  _currentLayers() {
    const draft = publisherStore.draft || {};
    const elements = this.format === 'story'
      ? draft.design?.designDocuments?.[0]?.elements || []
      : draft.design?.elements || [];
    if (!Array.isArray(elements)) return [{ id: TEXT_LAYER_IDS[0], text: '' }];
    const layers = elements
      .filter((el) => el && asLayerSlot(el.id) !== null)
      .slice(0, MAX_TEXT_LAYERS)
      .map((el) => ({ id: String(el.id), text: String(el.text ?? '') }));
    return layers.length ? layers : [{ id: TEXT_LAYER_IDS[0], text: '' }];
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
      return `<video class="pmc-media" src="${esc(item.url)}" poster="${esc(item.thumbnail_url)}" muted playsinline preload="metadata"></video>`;
    }
    return `<img class="pmc-media" src="${esc(item.url || item.thumbnail_url)}" alt="Média à composer">`;
  }

  /**
   * Calques éditables DIRECTEMENT sur la photo : chaque texte est contenteditable
   * et porte sa propre barre d'actions tactile (ordre + suppression). Le panneau
   * latéral ne contient aucun champ de saisie.
   */
  _renderOverlays() {
    const parts = this.layers.map((layer, index) => {
      const text = cleanText(layer.text);
      const slot = asLayerSlot(layer.id) ?? index;
      const active = index === this.activeLayerIndex;
      const overlay = `<div class="pmc-overlay pmc-overlay--layer pmc-overlay--slot-${slot}${text ? '' : ' pmc-overlay--placeholder'}${active ? ' active' : ''}"
                data-pmc-overlay data-layer-index="${index}" data-index="${index}"
                data-pmc-layer-text="${index}"
                ${index === 0 ? 'data-pmc-text ' : ''}contenteditable="true" spellcheck="false"
                role="textbox" aria-label="Texte du calque ${index + 1}" data-placeholder="Touchez pour écrire"
                style="z-index:${10 + index}">${esc(text)}</div>`;
      const actions = `<div class="pmc-overlay-actions pmc-overlay--slot-${slot}${active ? ' active' : ''}"
                data-pmc-overlay-actions data-layer-index="${index}" style="z-index:${20 + index}">
          <button type="button" class="pmc-overlay-btn" data-action="pmc-layer-up" data-index="${index}"
                  aria-label="Monter le calque ${index + 1}" ${index === this.layers.length - 1 ? 'disabled' : ''}>↑</button>
          <button type="button" class="pmc-overlay-btn" data-action="pmc-layer-down" data-index="${index}"
                  aria-label="Descendre le calque ${index + 1}" ${index === 0 ? 'disabled' : ''}>↓</button>
          <button type="button" class="pmc-overlay-btn pmc-overlay-btn--remove" data-action="pmc-layer-remove"
                  data-index="${index}" aria-label="Supprimer le calque ${index + 1}">×</button>
        </div>`;
      return overlay + actions;
    });
    return parts.join('');
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
    this.element.innerHTML = `
      <div class="pmc-preview" data-pmc-preview>
        <div class="pmc-stage" data-pmc-stage>
          ${this._renderStage()}
          ${this._renderOverlays()}
        </div>
        <div class="pmc-media-strip" data-pmc-media-strip>
          <div class="pmc-media-strip-head">
            <span class="pmc-media-count" data-pmc-media-count>Média ${media.length ? this.activeIndex + 1 : 0} / ${media.length}</span>
            <span class="pmc-media-hint">Ordre de publication</span>
          </div>
          <div class="pmc-media-list" data-pmc-media-list>${this._renderMediaStrip()}</div>
        </div>
      </div>
      <div class="pmc-panel">
        <label class="pmc-label" for="pmc-layer-text-0">Calques de texte (${this.layers.length} / ${MAX_TEXT_LAYERS})</label>
        <div class="pmc-layer-list" data-pmc-layer-list>${this._renderLayerList()}</div>
        <button type="button" class="pmc-layer-add" data-action="pmc-add-layer" ${limitReached ? 'disabled' : ''}>+ Ajouter un calque</button>
        <p class="pmc-layer-limit" data-pmc-layer-limit ${limitReached ? '' : 'hidden'}>Limite de 3 calques atteinte</p>
        <div class="pmc-panel-footer">
          <p class="pmc-hint">Touchez la photo pour ajouter un texte (3 max), touchez un texte pour l’éditer directement. ↑/↓ changent l’empilement, × supprime.</p>
          <button type="button" class="pmc-clear" data-action="pmc-clear" ${cleanText(this.layers[this.activeLayerIndex]?.text) ? '' : 'disabled'}>Effacer ce calque</button>
        </div>
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
      });
      node.addEventListener?.('focus', () => {
        if (index !== this.activeLayerIndex) this._selectLayer(index);
        else this._refreshLayerState();
      });
      node.addEventListener?.('click', () => this._selectLayer(index));
    };
    editable.forEach((node) => bindText(node, Number(node.dataset?.index ?? 0)));
    if (!editable.length) bindText(this.element?.querySelector?.('[data-pmc-text]'), 0);

    // Tap sur le fond de la photo : nouveau calque directement focusé (clavier mobile).
    const stage = this.element?.querySelector?.('[data-pmc-stage]');
    stage?.addEventListener?.('click', (event) => {
      const target = event?.target;
      if (target?.closest?.('[data-pmc-overlay], [data-pmc-overlay-actions], [data-action]')) return;
      if (this._addLayer()) this._focusLayer(this.activeLayerIndex);
    });

    const clear = this.element?.querySelector?.('[data-action="pmc-clear"]');
    if (clear) {
      clear.addEventListener('click', () => this._clearLayer(this.activeLayerIndex));
    }

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
  }

  _selectMedia(index) {
    const media = this._media();
    if (!Number.isInteger(index) || index < 0 || index >= media.length) return;
    this.activeIndex = index;
    this._render();
  }

  /** Déplace un média et resynchronise immédiatement le design v2. */
  _moveMedia(index, delta) {
    const media = this._media();
    const target = index + delta;
    if (!Number.isInteger(index) || index < 0 || index >= media.length
      || target < 0 || target >= media.length) return;

    const activeId = media[this.activeIndex]?.id;
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
    if (typeof publisherStore.removeMedia === 'function') {
      publisherStore.removeMedia(id);
    } else {
      media.splice(index, 1);
      media.forEach((m, i) => { m.order = i; });
    }
    this.activeIndex = Math.min(index, Math.max(0, remaining - 1));
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
    ['[data-pmc-overlay]', '[data-pmc-overlay-actions]', '[data-pmc-layer-chip]'].forEach((selector) => {
      Array.from(this.element?.querySelectorAll?.(selector) || []).forEach((node, index) => {
        node.classList?.toggle?.('active', index === this.activeLayerIndex);
        node.setAttribute?.('aria-pressed', String(index === this.activeLayerIndex));
      });
    });
    const clear = this.element?.querySelector?.('[data-action="pmc-clear"]');
    if (clear) clear.disabled = !cleanText(this.layers[this.activeLayerIndex]?.text);
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
    this.layers.push({ id: TEXT_LAYER_IDS[slot < 0 ? this.layers.length : slot], text: '' });
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
    if (!this.layers.length) this.layers = [{ id: TEXT_LAYER_IDS[0], text: '' }];
    this.activeLayerIndex = Math.min(index, this.layers.length - 1);
    this._render();
    this._writeDesign();
  }

  _clearLayer(index) {
    this._syncTextsFromDom();
    if (!this.layers[index]) return;
    this.layers[index].text = '';
    this._render();
    this._writeDesign();
    this._focusLayer(index);
  }

  _updatePreview() {
    const overlays = Array.from(this.element?.querySelectorAll?.('[data-pmc-overlay]') || []);
    const activeNode = this.element?.ownerDocument?.activeElement
      || (typeof document !== 'undefined' ? document.activeElement : null);
    const apply = (node, index) => {
      if (!node) return;
      const text = cleanText(this.layers[index]?.text);
      // Ne pas réécrire le noeud en cours de frappe : cela casserait le curseur.
      if (node !== activeNode) node.textContent = text;
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
    const overlays = this.layers
      .filter((layer) => cleanText(layer.text))
      .map((layer) => ({ id: layer.id, text: layer.text }));

    if (this.format === 'story') {
      const { slides, designDocuments } = buildStoryDesign(this._media(), overlays);
      publisherStore.updateStorySlides(slides, designDocuments);
    } else {
      publisherStore.updateDesign(buildReelDesign(publisherStore.draft?.design || {}, overlays));
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
