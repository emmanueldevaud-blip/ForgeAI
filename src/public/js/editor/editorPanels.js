/**
 * Panneaux de l'éditeur : médias (bibliothèque + suggestions + upload),
 * calques, carrousel, propriétés contextuelles et outils.
 */

import {
  TEXT_FONTS,
  STICKER_SET,
  FILTERS,
} from './editorState.js?v=1';

const esc = (t) =>
  String(t ?? '').replace(
    /[&<>"']/g,
    (c) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
  );

export class EditorPanels {
  constructor({ root, state, canvas, interaction, deps, onAction }) {
    this.root = root;
    this.state = state;
    this.canvas = canvas;
    this.interaction = interaction;
    this.deps = deps; // { getSuggestedPhotos, listPhotos, uploadPhotos, photoFileUrl, publicationId }
    this.onAction = onAction || (() => {});
    this.tab = 'media';
    this._mediaLoaded = false;
    this._stickersOpen = false;
  }

  // ------------------------------------------------------------------
  // Layout
  // ------------------------------------------------------------------

  renderLayout() {
    this.root.innerHTML = `
      <div class="ed-layout">
        <aside class="ed-sidebar" data-ed-panel="left">
          <div class="ed-panel-tabs" role="tablist">
            <button type="button" class="ed-tab active" data-ed-tab="media">Médias</button>
            <button type="button" class="ed-tab" data-ed-tab="layers">Calques</button>
            <button type="button" class="ed-tab" data-ed-tab="carousel">Carrousel</button>
          </div>
          <div class="ed-panel-scroll">
            <div class="ed-tabbody" data-ed-tabbody="media"></div>
            <div class="ed-tabbody" data-ed-tabbody="layers" hidden></div>
            <div class="ed-tabbody" data-ed-tabbody="carousel" hidden></div>
          </div>
          <div class="ed-tools">
            <button type="button" class="ed-tool" data-ed-tool="text">＋ Texte</button>
            <button type="button" class="ed-tool ${this._stickersOpen ? 'active' : ''}" data-ed-tool="sticker">Stickers</button>
            <button type="button" class="ed-tool" data-ed-tool="shape">Formes</button>
            <label class="ed-tool ed-tool-color" title="Couleur de fond">
              Fond
              <input type="color" data-ed-bg value="${esc(this.state.design.background?.color || '#111111')}">
            </label>
          </div>
          <div class="ed-sticker-drawer" data-ed-stickers ${this._stickersOpen ? '' : 'hidden'}></div>
        </aside>

        <main class="ed-stage">
          <div class="ed-canvas-host" data-ed-canvas-host></div>
          <div class="ed-mobile-bar">
            <button type="button" class="btn btn-secondary btn-small" data-ed-drawer="left">Médias</button>
            <button type="button" class="btn btn-secondary btn-small" data-ed-drawer="right">Outils</button>
          </div>
        </main>

        <aside class="ed-props" data-ed-panel="right">
          <div class="ed-props-body" data-ed-props-body></div>
        </aside>
      </div>
    `;

    this.sidebar = this.root.querySelector('[data-ed-panel="left"]');
    this.props = this.root.querySelector('[data-ed-panel="right"]');
    this.propsBody = this.root.querySelector('[data-ed-props-body]');
    this.stage = this.root.querySelector('.ed-stage');
    this.canvasHost = this.root.querySelector('[data-ed-canvas-host]');

    this._bindTabs();
    this._bindTools();
    this._bindDrawers();
    this.refreshProps();
    this.refreshLayers();
    this.refreshCarousel();
    this.loadMedia();
  }

  _bindTabs() {
    this.root.querySelectorAll('[data-ed-tab]').forEach((btn) => {
      btn.addEventListener('click', () => {
        this.tab = btn.dataset.edTab;
        this.root.querySelectorAll('[data-ed-tab]').forEach((b) => {
          b.classList.toggle('active', b.dataset.edTab === this.tab);
        });
        this.root.querySelectorAll('[data-ed-tabbody]').forEach((body) => {
          body.hidden = body.dataset.edTabbody !== this.tab;
        });
        if (this.tab === 'layers') this.refreshLayers();
        if (this.tab === 'carousel') this.refreshCarousel();
        if (this.tab === 'media') this.loadMedia();
      });
    });
  }

  _bindTools() {
    this.root.querySelector('[data-ed-tool="text"]').addEventListener('click', () => {
      const d = this.state.design;
      const el = this.state.addElement({
        type: 'text',
        text: 'Votre texte',
        x: d.format.width / 2,
        y: d.format.height / 2,
        w: d.format.width * 0.8,
        h: 80,
        size: Math.round(d.format.width * 0.06),
        font: 'Arial',
        color: '#ffffff',
        align: 'center',
        bold: true,
        italic: false,
        shadow: true,
        rotation: 0,
        opacity: 1,
      });
      this.onAction('added', el);
      this.refreshProps();
      const ta = this.propsBody?.querySelector('[data-prop="text"]');
      if (ta) {
        ta.focus();
        ta.select();
      }
    });

    this.root.querySelector('[data-ed-tool="sticker"]').addEventListener('click', () => {
      this._stickersOpen = !this._stickersOpen;
      const drawer = this.root.querySelector('[data-ed-stickers]');
      drawer.hidden = !this._stickersOpen;
      this.root
        .querySelector('[data-ed-tool="sticker"]')
        .classList.toggle('active', this._stickersOpen);
      if (this._stickersOpen) this._renderStickerDrawer();
    });

    this.root.querySelector('[data-ed-tool="shape"]').addEventListener('click', () => {
      this._openShapePicker();
    });

    const bg = this.root.querySelector('[data-ed-bg]');
    bg.addEventListener('input', () => {
      this.state.setBackground(bg.value);
    });
    bg.addEventListener('change', () => {
      this.state.setBackground(bg.value);
    });
  }

  _bindDrawers() {
    this.root.querySelectorAll('[data-ed-drawer]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const side = btn.dataset.edDrawer;
        const panel = this.root.querySelector(`[data-ed-panel="${side}"]`);
        const other = this.root.querySelector(
          `[data-ed-panel="${side === 'left' ? 'right' : 'left'}"]`
        );
        if (other) other.classList.remove('ed-open');
        panel.classList.toggle('ed-open');
      });
    });
  }

  // ------------------------------------------------------------------
  // Outils : stickers / formes
  // ------------------------------------------------------------------

  _renderStickerDrawer() {
    const drawer = this.root.querySelector('[data-ed-stickers]');
    drawer.innerHTML = `
      <div class="ed-sticker-grid">
        ${STICKER_SET.map(
          (s) =>
            `<button type="button" class="ed-sticker-btn" data-sticker="${s}">${s}</button>`
        ).join('')}
      </div>
    `;
    drawer.querySelectorAll('[data-sticker]').forEach((btn) => {
      btn.addEventListener('click', () => {
        this._addSticker(btn.dataset.sticker);
      });
    });
  }

  _addSticker(sticker) {
    const d = this.state.design;
    const size = Math.round(d.format.width * 0.18);
    const el = this.state.addElement({
      type: 'sticker',
      sticker,
      x: d.format.width / 2,
      y: d.format.height / 2,
      w: size,
      h: size,
      color: '#ff5722',
      rotation: 0,
      opacity: 1,
    });
    this.onAction('added', el);
  }

  _openShapePicker() {
    let box = this.root.querySelector('[data-ed-shape-picker]');
    if (box) {
      box.remove();
      return;
    }
    box = document.createElement('div');
    box.className = 'ed-popover';
    box.dataset.edShapePicker = '1';
    box.innerHTML = `
      <div class="ed-popover-title">Formes</div>
      <div class="ed-shape-row">
        <button type="button" data-shape="circle" title="Cercle">●</button>
        <button type="button" data-shape="rect" title="Rectangle">■</button>
        <button type="button" data-shape="line" title="Ligne">▬</button>
      </div>
    `;
    this.root.querySelector('[data-ed-panel="left"]').appendChild(box);
    box.querySelectorAll('[data-shape]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const d = this.state.design;
        const size = Math.round(d.format.width * 0.22);
        const isLine = btn.dataset.shape === 'line';
        const el = this.state.addElement({
          type: 'sticker',
          sticker: btn.dataset.shape,
          x: d.format.width / 2,
          y: d.format.height / 2,
          w: isLine ? d.format.width * 0.5 : size,
          h: isLine ? 14 : size,
          color: '#4f8cff',
          rotation: 0,
          opacity: 1,
        });
        this.onAction('added', el);
        box.remove();
      });
    });
  }

  // ------------------------------------------------------------------
  // Médias
  // ------------------------------------------------------------------

  async loadMedia() {
    const body = this.root.querySelector('[data-ed-tabbody="media"]');
    body.innerHTML = `
      <div class="ed-media-actions">
        <label class="btn btn-secondary btn-small ed-upload-label">
          Importer
          <input type="file" accept="image/*" multiple data-ed-upload hidden>
        </label>
        <label class="btn btn-secondary btn-small ed-upload-label">
          Importer vidéo
          <input type="file" accept="video/*,.mov,.mp4" multiple data-ed-upload-video hidden>
        </label>
      </div>
      <div class="ed-media-section">Photos suggérées</div>
      <div class="ed-media-grid" data-ed-suggested><div class="loading">Chargement…</div></div>
      <div class="ed-media-section">Bibliothèque</div>
      <div class="ed-media-grid" data-ed-library><div class="loading">Chargement…</div></div>
    `;

    body.querySelector('[data-ed-upload]').addEventListener('change', async (e) => {
      const files = e.target.files;
      if (!files || !files.length) return;
      try {
        await this.deps.uploadPhotos(files);
        this._mediaLoaded = false;
        await this.loadMedia();
        this.onAction('uploaded');
      } catch (err) {
        this.onAction('error', err);
      }
    });

    body.querySelector('[data-ed-upload-video]').addEventListener('change', async (e) => {
      const files = e.target.files;
      if (!files || !files.length) return;
      try {
        const res = await this.deps.uploadPhotos(files);
        const created = Array.isArray(res?.items) ? res.items : res;
        for (const item of created || []) {
          this.onAction('add-video', { photoId: item?.id, duration: item?.duration });
        }
        this._mediaLoaded = false;
        await this.loadMedia();
        this.onAction('uploaded');
      } catch (err) {
        this.onAction('error', err);
      }
    });

    const renderGrid = (el, items, emptyMsg) => {
      if (!items.length) {
        el.innerHTML = `<div class="ed-empty">${esc(emptyMsg)}</div>`;
        return;
      }
      el.innerHTML = items
        .map(
          (p) => `
        <div class="ed-media-item" data-photo-id="${p.id}">
          <img src="${esc(this.deps.photoFileUrl(p.id, 'small'))}" alt="" loading="lazy">
          <div class="ed-media-item-actions">
            <button type="button" data-media-action="bg" title="Mettre en fond">Fond</button>
            <button type="button" data-media-action="carousel" title="Ajouter au carrousel">＋</button>
            <button type="button" data-media-action="add-video" title="Importer en clip vidéo">🎬</button>
          </div>
        </div>`
        )
        .join('');
      el.querySelectorAll('[data-photo-id]').forEach((item) => {
        const id = Number(item.dataset.photoId);
        item.querySelectorAll('[data-media-action]').forEach((btn) => {
          btn.addEventListener('click', (ev) => {
            ev.stopPropagation();
            if (btn.dataset.mediaAction === 'bg') this.onAction('set-bg', { photoId: id });
            else if (btn.dataset.mediaAction === 'carousel') this.onAction('add-carousel', { photoId: id });
            else if (btn.dataset.mediaAction === 'add-video') this.onAction('add-video', { photoId: id });
          });
        });
      });
    };

    try {
      const suggested = await this.deps.getSuggestedPhotos(this.deps.publicationId, 12);
      renderGrid(
        body.querySelector('[data-ed-suggested]'),
        suggested || [],
        'Aucune photo suggérée.'
      );
    } catch (_err) {
      body.querySelector('[data-ed-suggested]').innerHTML =
        '<div class="ed-empty">Chargement impossible.</div>';
    }

    try {
      const lib = await this.deps.listPhotos({ page: 1, page_size: 24 });
      const items = Array.isArray(lib) ? lib : lib?.items || [];
      renderGrid(body.querySelector('[data-ed-library]'), items, 'Bibliothèque vide.');
    } catch (_err) {
      body.querySelector('[data-ed-library]').innerHTML =
        '<div class="ed-empty">Chargement impossible.</div>';
    }
    this._mediaLoaded = true;
  }

  // ------------------------------------------------------------------
  // Calques
  // ------------------------------------------------------------------

  refreshLayers() {
    const body = this.root.querySelector('[data-ed-tabbody="layers"]');
    if (!body) return;
    const els = this.state.design.elements.slice().reverse();
    if (!els.length) {
      body.innerHTML = '<div class="ed-empty">Aucun calque. Ajoutez un texte ou un sticker.</div>';
      return;
    }
    body.innerHTML = els
      .map((el) => {
        const label =
          el.type === 'text'
            ? `Texte · ${esc((el.text || '').slice(0, 18))}`
            : el.type === 'image'
              ? 'Image'
              : `Sticker · ${el.sticker === 'circle' ? 'Cercle' : el.sticker === 'rect' ? 'Rectangle' : el.sticker === 'line' ? 'Ligne' : el.sticker}`;
        const sel = el.id === this.state.selectedId ? ' selected' : '';
        return `
          <div class="ed-layer${sel}" data-layer-id="${el.id}">
            <span class="ed-layer-label">${label}</span>
            <span class="ed-layer-actions">
              <button type="button" data-layer="up" title="Monter">↑</button>
              <button type="button" data-layer="down" title="Descendre">↓</button>
              <button type="button" data-layer="del" title="Supprimer">✕</button>
            </span>
          </div>`;
      })
      .join('');

    body.querySelectorAll('[data-layer-id]').forEach((row) => {
      const id = row.dataset.layerId;
      row.addEventListener('click', (e) => {
        if (e.target.closest('[data-layer]')) return;
        this.state.select(id);
      });
      row.querySelectorAll('[data-layer]').forEach((btn) => {
        btn.addEventListener('click', (e) => {
          e.stopPropagation();
          const act = btn.dataset.layer;
          if (act === 'up') this.state.moveLayer(id, 'up');
          else if (act === 'down') this.state.moveLayer(id, 'down');
          else this.state.removeElement(id);
        });
      });
    });
  }

  // ------------------------------------------------------------------
  // Carrousel
  // ------------------------------------------------------------------

  refreshCarousel() {
    const body = this.root.querySelector('[data-ed-tabbody="carousel"]');
    if (!body) return;
    const list = this.state.design.carousel || [];
    const cover = this.state.design.cover;
    if (!list.length) {
      body.innerHTML =
        '<div class="ed-empty">Ajoutez des photos depuis l’onglet Médias (bouton +) pour composer un album.</div>';
      return;
    }
    body.innerHTML = list
      .map((photoId, i) => {
        const isCover = photoId === cover;
        return `
        <div class="ed-carousel-item${isCover ? ' cover' : ''}" data-carousel-index="${i}">
          <img src="${esc(this.deps.photoFileUrl(photoId, 'small'))}" alt="">
          <div class="ed-carousel-meta">
            ${isCover ? '<span class="ed-badge-cover">Couverture</span>' : `<span>#${i + 1}</span>`}
            <span class="ed-layer-actions">
              <button type="button" data-car="up" ${i === 0 ? 'disabled' : ''}>↑</button>
              <button type="button" data-car="down" ${i === list.length - 1 ? 'disabled' : ''}>↓</button>
              <button type="button" data-car="cover" ${isCover ? 'disabled' : ''}>★</button>
              <button type="button" data-car="del">✕</button>
            </span>
          </div>
        </div>`;
      })
      .join('');

    body.querySelectorAll('[data-carousel-index]').forEach((row) => {
      const idx = Number(row.dataset.carouselIndex);
      row.querySelectorAll('[data-car]').forEach((btn) => {
        btn.addEventListener('click', () => {
          const cur = (this.state.design.carousel || []).slice();
          const act = btn.dataset.car;
          if (act === 'up' && idx > 0) {
            [cur[idx - 1], cur[idx]] = [cur[idx], cur[idx - 1]];
            this.state.setCarousel(cur);
          } else if (act === 'down' && idx < cur.length - 1) {
            [cur[idx + 1], cur[idx]] = [cur[idx], cur[idx + 1]];
            this.state.setCarousel(cur);
          } else if (act === 'cover') {
            this.state.setCover(cur[idx]);
            this.onAction('cover', { photoId: cur[idx] });
          } else if (act === 'del') {
            cur.splice(idx, 1);
            this.state.setCarousel(cur);
            if (this.state.design.cover === cur[idx]) this.state.setCover(cur[0] ?? null);
          }
        });
      });
    });
  }

  // ------------------------------------------------------------------
  // Propriétés contextuelles
  // ------------------------------------------------------------------

  refreshProps() {
    if (!this.propsBody) return;
    const el = this.state.selected;
    if (!el) {
      const d = this.state.design;
      this.propsBody.innerHTML = `
        <div class="ed-props-title">Propriétés</div>
        <div class="ed-empty">Sélectionnez un élément sur le canvas pour le modifier.</div>
        <div class="ed-field">
          <label>Format</label>
          <div class="ed-format-info">${esc(d.format.width)} × ${esc(d.format.height)} px</div>
        </div>
      `;
      return;
    }

    const rotation = el.rotation || 0;
    const opacity = el.opacity ?? 1;
    let specific = '';

    if (el.type === 'text') {
      specific = `
        <div class="ed-field">
          <label>Texte</label>
          <textarea data-prop="text" rows="3">${esc(el.text)}</textarea>
        </div>
        <div class="ed-field ed-field-row">
          <label>Police</label>
          <select data-prop="font">
            ${TEXT_FONTS.map(
              (f) =>
                `<option value="${esc(f)}" ${f === el.font ? 'selected' : ''}>${f.replace(/"/g, '')}</option>`
            ).join('')}
          </select>
        </div>
        <div class="ed-field ed-field-row">
          <label>Taille</label>
          <input type="range" data-prop="size" min="12" max="220" value="${el.size || 32}">
        </div>
        <div class="ed-field ed-field-row">
          <label>Couleur</label>
          <input type="color" data-prop="color" value="${esc(el.color || '#ffffff')}">
        </div>
        <div class="ed-field ed-field-row">
          <label>Alignement</label>
          <span class="ed-seg">
            ${['left', 'center', 'right']
              .map(
                (a) =>
                  `<button type="button" data-prop-align="${a}" class="${(el.align || 'left') === a ? 'active' : ''}">${a === 'left' ? 'Gauche' : a === 'center' ? 'Centre' : 'Droite'}</button>`
              )
              .join('')}
          </span>
        </div>
        <div class="ed-field ed-checks">
          <label><input type="checkbox" data-prop="bold" ${el.bold ? 'checked' : ''}> Gras</label>
          <label><input type="checkbox" data-prop="italic" ${el.italic ? 'checked' : ''}> Italique</label>
          <label><input type="checkbox" data-prop="shadow" ${el.shadow ? 'checked' : ''}> Ombre</label>
        </div>
      `;
    } else if (el.type === 'image') {
      const cropping = this.canvas.overlayMode === 'crop';
      specific = `
        <div class="ed-field ed-field-row">
          <label>Filtre</label>
          <select data-prop="filter">
            ${FILTERS.map(
              (f) =>
                `<option value="${f.key}" ${(el.filter || 'none') === f.key ? 'selected' : ''}>${f.label}</option>`
            ).join('')}
          </select>
        </div>
        <div class="ed-field">
          <button type="button" class="btn btn-secondary btn-small" data-prop-crop>
            ${cropping ? '✓ Terminer le recadrage' : '✂ Recadrer'}
          </button>
        </div>
        <div class="ed-field ed-field-row">
          <label>Opacité</label>
          <input type="range" data-prop="opacity" min="10" max="100" value="${Math.round(opacity * 100)}">
        </div>
      `;
    } else if (el.type === 'sticker') {
      specific = `
        ${
          ['circle', 'rect', 'line'].includes(el.sticker)
            ? `<div class="ed-field ed-field-row"><label>Couleur</label><input type="color" data-prop="color" value="${esc(el.color || '#4f8cff')}"></div>`
            : `<div class="ed-field"><label>Sticker</label><div class="ed-sticker-grid ed-sticker-grid-sm">
                ${STICKER_SET.map(
                  (s) =>
                    `<button type="button" class="ed-sticker-btn ${s === el.sticker ? 'active' : ''}" data-change-sticker="${s}">${s}</button>`
                ).join('')}
              </div></div>`
        }
        <div class="ed-field ed-field-row">
          <label>Opacité</label>
          <input type="range" data-prop="opacity" min="10" max="100" value="${Math.round(opacity * 100)}">
        </div>
      `;
    }

    this.propsBody.innerHTML = `
      <div class="ed-props-title">${
        el.type === 'text' ? 'Texte' : el.type === 'image' ? 'Image' : 'Sticker'
      }</div>
      ${specific}
      <div class="ed-field ed-field-row">
        <label>Rotation</label>
        <input type="range" data-prop="rotation" min="0" max="359" value="${Math.round(rotation)}">
      </div>
      <div class="ed-field ed-field-row">
        <label>Opacité</label>
        <input type="range" data-prop="opacity-global" min="10" max="100" value="${Math.round(opacity * 100)}">
      </div>
      <div class="ed-props-actions">
        <button type="button" class="btn btn-secondary btn-small" data-prop-front>↑ Devant</button>
        <button type="button" class="btn btn-secondary btn-small" data-prop-back>↓ Derrière</button>
        <button type="button" class="btn btn-danger btn-small" data-prop-delete>Supprimer</button>
      </div>
    `;

    this._bindProps(el);
  }

  _bindProps(el) {
    const body = this.propsBody;
    const bind = (selector, event, fn) => {
      const node = body.querySelector(selector);
      if (node) node.addEventListener(event, fn);
    };

    if (el.type === 'text') {
      bind('[data-prop="text"]', 'input', (e) => {
        this.state.updateElementLive(el.id, { text: e.target.value });
        this.canvas.requestRender();
      });
      bind('[data-prop="text"]', 'change', () => this.state.commitTransaction());
      bind('[data-prop="font"]', 'change', (e) =>
        this.state.updateElement(el.id, { font: e.target.value })
      );
      bind('[data-prop="size"]', 'input', (e) => {
        this.state.updateElementLive(el.id, { size: Number(e.target.value) });
        this.canvas.requestRender();
      });
      bind('[data-prop="size"]', 'change', () => this.state.commitTransaction());
      bind('[data-prop="color"]', 'input', (e) => {
        this.state.updateElementLive(el.id, { color: e.target.value });
        this.canvas.requestRender();
      });
      bind('[data-prop="color"]', 'change', () => this.state.commitTransaction());
      body.querySelectorAll('[data-prop-align]').forEach((btn) => {
        btn.addEventListener('click', () =>
          this.state.updateElement(el.id, { align: btn.dataset.propAlign })
        );
      });
      ['bold', 'italic', 'shadow'].forEach((key) => {
        bind(`[data-prop="${key}"]`, 'change', (e) =>
          this.state.updateElement(el.id, { [key]: e.target.checked })
        );
      });
    }

    if (el.type === 'image') {
      bind('[data-prop="filter"]', 'change', (e) =>
        this.state.updateElement(el.id, { filter: e.target.value })
      );
      bind('[data-prop="opacity"]', 'input', (e) => {
        this.state.updateElementLive(el.id, { opacity: Number(e.target.value) / 100 });
        this.canvas.requestRender();
      });
      bind('[data-prop="opacity"]', 'change', () => this.state.commitTransaction());
      bind('[data-prop-crop]', 'click', () => {
        const entering = this.canvas.overlayMode !== 'crop';
        this.interaction.setCropMode(entering);
        this.refreshProps();
      });
    }

    if (el.type === 'sticker') {
      bind('[data-prop="color"]', 'input', (e) => {
        this.state.updateElementLive(el.id, { color: e.target.value });
        this.canvas.requestRender();
      });
      bind('[data-prop="color"]', 'change', () => this.state.commitTransaction());
      body.querySelectorAll('[data-change-sticker]').forEach((btn) => {
        btn.addEventListener('click', () =>
          this.state.updateElement(el.id, { sticker: btn.dataset.changeSticker })
        );
      });
      bind('[data-prop="opacity"]', 'input', (e) => {
        this.state.updateElementLive(el.id, { opacity: Number(e.target.value) / 100 });
        this.canvas.requestRender();
      });
      bind('[data-prop="opacity"]', 'change', () => this.state.commitTransaction());
    }

    bind('[data-prop="rotation"]', 'input', (e) => {
      this.state.updateElementLive(el.id, { rotation: Number(e.target.value) });
      this.canvas.requestRender();
    });
    bind('[data-prop="rotation"]', 'change', () => this.state.commitTransaction());
    bind('[data-prop="opacity-global"]', 'input', (e) => {
      this.state.updateElementLive(el.id, { opacity: Number(e.target.value) / 100 });
      this.canvas.requestRender();
    });
    bind('[data-prop="opacity-global"]', 'change', () => this.state.commitTransaction());

    bind('[data-prop-front]', 'click', () => this.state.bringToFront(el.id));
    bind('[data-prop-back]', 'click', () => this.state.sendToBack(el.id));
    bind('[data-prop-delete]', 'click', () => {
      if (this.canvas.overlayMode === 'crop') {
        this.interaction.setCropMode(false);
      }
      this.state.removeElement(el.id);
    });
  }

  /** Ferme le mode crop si la sélection change. */
  onSelectionChanged() {
    if (this.canvas.overlayMode === 'crop') {
      this.interaction.setCropMode(false);
    }
    this.refreshProps();
    this.refreshLayers();
  }
}
