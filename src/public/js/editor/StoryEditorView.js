/**
 * Story Studio Editor — Éditeur graphique mobile-first pour Instagram Stories.
 * Format 9:16 immersif, tactile, inspiré de l'expérience Instagram Stories.
 *
 * Architecture modulaire réutilisant :
 * - EditorState, EditorCanvas, EditorInteraction (existant)
 * - Nouveaux modules : StoryNavigation, StoryLayerManager, StoryStickers, StoryTextEditor
 */

import { EditorState, FORMATS, normalizeDesign } from './editorState.js?v=2';
import { EditorCanvas } from './editorCanvas.js?v=1';
import { EditorInteraction } from './editorInteraction.js?v=1';
import { EditorPanels } from './editorPanels.js?v=2';
import { EditorTimeline } from './editorTimeline.js?v=2';
import { coverCrop } from './editorGeometry.js?v=1';

const esc = (t) =>
  String(t ?? '').replace(
    /[&<>"']/g,
    (c) =>
      ({ '&': '&', '<': '<', '>': '>', '"': '"', "'": "'" }[c])
  );

// ----------------------------------------------------------
// Configuration Story (9:16)
// ----------------------------------------------------------
const STORY_FORMAT = {
  key: 'story_916',
  label: 'Story Instagram (9:16)',
  type: 'story_916',
  platform: 'instagram',
  width: 1080,
  height: 1920,
};

const STORY_SLIDE_DURATION = 5000; // 5s par slide par défaut

// Bibliothèques de stickers
const STICKER_LIBRARIES = {
  emojis: ['🏃‍♂️', '🏔️', '💪', '🔥', '😅', '🥵', '🏁', '🚀', '⛰️', '🌲', '☀️', '🌧️', '❤️', '💚', '💛', '🎵', '📸', '✨', '💯', '🥇'],
  shapes: ['circle', 'square', 'triangle', 'heart', 'star', 'arrow-up', 'arrow-right', 'flag'],
  badges: ['NEW', 'BEST', 'PR', 'D+', 'KM', 'TIME', 'PACE', 'HR'],
  sport: ['🏃‍♂️ Trail', '⛰️ Montagne', '🏔️ Sommet', '🌲 Forêt', '🏁 Finish', '💪 Force', '🔥 Feu', '😅 Galère'],
  brand: ['#Jepepagtrail', 'ForgeAI', 'Trail Running', 'Ultra Trail'],
};

const FONTS = [
  { id: 'arial', label: 'Arial', family: 'Arial, sans-serif' },
  { id: 'georgia', label: 'Georgia', family: 'Georgia, serif' },
  { id: 'impact', label: 'Impact', family: 'Impact, sans-serif' },
  { id: 'montserrat', label: 'Montserrat', family: '"Montserrat", sans-serif' },
  { id: 'roboto', label: 'Roboto', family: '"Roboto", sans-serif' },
  { id: 'oswald', label: 'Oswald', family: '"Oswald", sans-serif' },
];

const TEXT_COLORS = [
  '#ffffff', '#000000', '#ff0000', '#ff6b00', '#ffcc00', '#00ff00', '#00ccff', '#ff00cc',
  '#ff6b6b', '#4ecdc4', '#ffe66d', '#95e1d3', '#f38181', '#aa96da', '#fcbad3', '#a8d8ea',
];

const BG_COLORS = [
  'transparent', '#000000', '#ffffff', '#ff0000', '#ff6b00', '#ffcc00', '#00ff00', '#00ccff', '#ff00cc',
  '#1a1a2e', '#16213e', '#0f3460', '#e94560', '#212121', '#424242',
];

// ----------------------------------------------------------
// StoryEditorView — Point d'entrée principal
// ----------------------------------------------------------
export class StoryEditorView {
  /**
   * @param {Object} params
   * @param {StoryDraft} params.draft - Brouillon StoryDraft chargé
   * @param {Object} params.deps - Dépendances API
   * @param {Function} params.onClose - Callback fermeture
   * @param {Function} params.onSave - Callback sauvegarde
   * @param {Function} params.onPublish - Callback publication
   */
  constructor({ draft, deps, onClose, onSave, onPublish }) {
    this.draft = draft;
    this.deps = deps;
    this.callbacks = { onClose, onSave, onPublish };

    // État global
    this.currentSlideIndex = 0;
    this.slides = draft.slides || [];
    this.designDocuments = draft.design_documents || [];
    this.selectedElementId = null;
    this.history = [];
    this.historyIndex = -1;
    this.isPlaying = false;
    this.playTimer = null;

    // Modules
    this.state = null;
    this.canvas = null;
    this.interaction = null;
    this.panels = null;
    this.timeline = null;
    this.layerManager = null;
    this.stickerPicker = null;
    this.textEditor = null;
    this.drawingMode = false;
    this.drawingPaths = [];
    this.currentDrawingPath = null;

    // DOM
    this.root = null;
    this.canvasHost = null;
    this.topBar = null;
    this.bottomBar = null;
    this.slideNav = null;
  }

  mount(host) {
    this.root = document.createElement('div');
    this.root.className = 'story-editor-root';
    this.root.innerHTML = this._renderShell();
    host.appendChild(this.root);

    this._bindShell();
    this._initSlide(0);
    this._setupTouchGestures();
    this._setupKeyboardShortcuts();

    return this.root;
  }

  _renderShell() {
    const slide = this.slides[this.currentSlideIndex] || {};
    const design = this.designDocuments[this.currentSlideIndex] || {};

    return `
      <!-- Barre supérieure -->
      <header class="story-editor-topbar" data-topbar>
        <div class="story-topbar-left">
          <button type="button" class="story-btn story-btn-icon" data-action="close" title="Fermer">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>
            </svg>
          </button>
          <button type="button" class="story-btn story-btn-icon" data-action="undo" title="Annuler" disabled>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M3 7v6h6"/><path d="M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6 2.3L3 13"/>
            </svg>
          </button>
          <button type="button" class="story-btn story-btn-icon" data-action="redo" title="Rétablir" disabled>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 7v6h-6"/><path d="M3 17a9 9 0 0 1 9-9 9 9 0 0 1 6 2.3l3 2.7"/>
            </svg>
          </button>
        </div>
        <div class="story-topbar-center">
          <span class="story-title">${esc(slide.hook || 'Nouvelle Story')}</span>
        </div>
        <div class="story-topbar-right">
          <button type="button" class="story-btn story-btn-icon" data-action="add-text" title="Ajouter du texte">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="4 7 4 4 20 4 20 7"/><line x1="9" y1="20" x2="15" y2="20"/><line x1="12" y1="4" x2="12" y2="20"/>
            </svg>
          </button>
          <button type="button" class="story-btn story-btn-icon" data-action="draw" title="Dessiner">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 19l7-7 3 3-7 7-3-3z"/><path d="M18 13l-1.5-7.5L2 2l3.5 14.5L13 18l5-5z"/><path d="M2 2l7.586 7.586"/><circle cx="11" cy="11" r="2"/>
            </svg>
          </button>
          <button type="button" class="story-btn story-btn-icon" data-action="stickers" title="Stickers">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
            </svg>
          </button>
          <button type="button" class="story-btn story-btn-icon" data-action="gif" title="GIF">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="2" y="2" width="20" height="20" rx="2"/><circle cx="8" cy="8" r="2"/><path d="M16 8h.01"/><circle cx="16" cy="16" r="2"/><path d="M8 16h.01"/>
            </svg>
          </button>
          <button type="button" class="story-btn story-btn-icon" data-action="music" title="Musique">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>
            </svg>
          </button>
          <button type="button" class="story-btn story-btn-icon" data-action="crop" title="Recadrer">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M6 2v14a2 2 0 0 0 2 2h14"/><path d="M18 22V8a2 2 0 0 0-2-2H2"/>
            </svg>
          </button>
          <button type="button" class="story-btn story-btn-primary" data-action="save">Enregistrer</button>
        </div>
      </header>

      <!-- Zone centrale : Canvas + Navigation slides -->
      <main class="story-editor-main" data-main>
        <!-- Navigation latérale slides (desktop) / inférieure (mobile) -->
        <aside class="story-slide-nav" data-slide-nav role="navigation" aria-label="Navigation des Stories">
          ${this.slides.map((s, i) => `
            <button type="button" class="story-slide-thumb ${i === this.currentSlideIndex ? 'active' : ''}"
                    data-slide-index="${i}" title="Slide ${i + 1}: ${esc(s.hook || s.type || 'Slide')}">
              <span class="story-slide-type">${esc(s.type || '📷')}</span>
              <span class="story-slide-num">${i + 1}</span>
            </button>
          `).join('')}
          <button type="button" class="story-slide-thumb story-slide-add" data-action="add-slide" title="Ajouter une Story">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
          </button>
        </aside>

        <!-- Canvas principal -->
        <div class="story-canvas-host" data-canvas-host>
          <canvas class="story-canvas" data-canvas></canvas>
          <!-- Poignées de sélection (overlay) -->
          <div class="story-selection-overlay" data-selection-overlay></div>
        </div>

        <!-- Mini-timeline pour la slide courante -->
        <div class="story-slide-timeline" data-slide-timeline>
          <div class="story-timeline-track" data-timeline-track>
            <div class="story-timeline-playhead" data-playhead></div>
          </div>
          <div class="story-timeline-controls">
            <button type="button" class="story-btn story-btn-sm" data-action="play-pause" title="Lecture/Pause">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21"/></svg>
            </button>
            <span class="story-timeline-time" data-timeline-time>0.0s / ${(STORY_SLIDE_DURATION / 1000).toFixed(1)}s</span>
          </div>
        </div>
      </main>

      <!-- Barre inférieure : Outils contextuels -->
      <footer class="story-editor-bottombar" data-bottombar>
        <div class="story-tools" data-tools-panel>
          <!-- Outils par défaut -->
          <div class="story-tool-group" data-tool-group="default">
            <button type="button" class="story-tool-btn" data-tool="select" title="Sélection" aria-pressed="true">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M3 3l18 18"/><path d="M3 21l18-18"/>
              </svg>
            </button>
            <button type="button" class="story-tool-btn" data-tool="text" title="Texte">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="4 7 4 4 20 4 20 7"/><line x1="9" y1="20" x2="15" y2="20"/><line x1="12" y1="4" x2="12" y2="20"/>
              </svg>
            </button>
            <button type="button" class="story-tool-btn" data-tool="draw" title="Dessin">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 19l7-7 3 3-7 7-3-3z"/><path d="M18 13l-1.5-7.5L2 2l3.5 14.5L13 18l5-5z"/>
              </svg>
            </button>
            <button type="button" class="story-tool-btn" data-tool="sticker" title="Stickers">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/>
              </svg>
            </button>
          </div>

          <!-- Propriétés Texte (quand élément texte sélectionné) -->
          <div class="story-tool-group hidden" data-tool-group="text">
            <select class="story-font-select" data-text-font aria-label="Police">
              ${FONTS.map(f => `<option value="${f.id}">${esc(f.label)}</option>`).join('')}
            </select>
            <div class="story-color-picker" data-text-color>
              ${TEXT_COLORS.map(c => `<button type="button" class="story-color-swatch" style="background:${c}" data-color="${c}" title="${c}"></button>`).join('')}
            </div>
            <div class="story-slider-group">
              <label>Taille <input type="range" min="12" max="120" value="48" data-text-size></label>
              <label>Interlignage <input type="range" min="0.8" max="2.5" step="0.1" value="1.2" data-text-lineheight></label>
              <label>Opacité <input type="range" min="0" max="1" step="0.05" value="1" data-text-opacity></label>
            </div>
            <div class="story-text-actions">
              <button type="button" class="story-btn story-btn-sm" data-text-bold title="Gras"><strong>B</strong></button>
              <button type="button" class="story-btn story-btn-sm" data-text-italic title="Italique"><em>I</em></button>
              <button type="button" class="story-btn story-btn-sm" data-text-shadow title="Ombre">🌑</button>
              <button type="button" class="story-btn story-btn-sm" data-text-outline title="Contour">⬜</button>
              <button type="button" class="story-btn story-btn-sm" data-text-bg title="Fond">🎨</button>
              <button type="button" class="story-btn story-btn-sm" data-text-align-left title="Aligner à gauche">⬛</button>
              <button type="button" class="story-btn story-btn-sm" data-text-align-center title="Centrer">⬜</button>
              <button type="button" class="story-btn story-btn-sm" data-text-align-right title="Aligner à droite">⬛</button>
            </div>
            <button type="button" class="story-btn story-btn-danger story-btn-sm" data-action="delete-element" title="Supprimer">🗑</button>
          </div>

          <!-- Propriétés Dessin -->
          <div class="story-tool-group hidden" data-tool-group="draw">
            <div class="story-color-picker" data-draw-color>
              ${TEXT_COLORS.map(c => `<button type="button" class="story-color-swatch" style="background:${c}" data-color="${c}"></button>`).join('')}
            </div>
            <label>Épaisseur <input type="range" min="1" max="20" value="3" data-draw-width></label>
            <button type="button" class="story-btn story-btn-sm" data-draw-eraser title="Gomme">🧽</button>
            <button type="button" class="story-btn story-btn-sm" data-draw-undo title="Annuler trait">↶</button>
            <button type="button" class="story-btn story-btn-sm" data-draw-redo title="Rétablir trait">↷</button>
            <button type="button" class="story-btn story-btn-primary story-btn-sm" data-draw-finish title="Valider dessin">✓ Terminer</button>
          </div>

          <!-- Sélecteur Stickers -->
          <div class="story-tool-group hidden" data-tool-group="sticker">
            <div class="story-sticker-tabs">
              <button type="button" class="story-sticker-tab active" data-sticker-cat="emojis">😀</button>
              <button type="button" class="story-sticker-tab" data-sticker-cat="sport">🏃</button>
              <button type="button" class="story-sticker-tab" data-sticker-cat="badges">🏷</button>
              <button type="button" class="story-sticker-tab" data-sticker-cat="shapes">🔷</button>
              <button type="button" class="story-sticker-tab" data-sticker-cat="brand">🏷</button>
            </div>
            <div class="story-sticker-grid" data-sticker-grid></div>
          </div>
        </div>

        <!-- Actions globales -->
        <div class="story-global-actions">
          <button type="button" class="story-btn story-btn-secondary" data-action="duplicate-slide">⎘ Dupliquer</button>
          <button type="button" class="story-btn story-btn-danger" data-action="delete-slide">🗑 Supprimer</button>
          <button type="button" class="story-btn story-btn-primary" data-action="preview-all">▶ Aperçu global</button>
          <button type="button" class="story-btn story-btn-success" data-action="validate-publish">✓ Valider et publier</button>
        </div>
      </footer>

      <!-- Modales -->
      <div class="story-modals" data-modals></div>
    `;
  }

  _bindShell() {
    // Barre supérieure
    this.root.querySelector('[data-action="close"]').addEventListener('click', () => this.callbacks.onClose?.());
    this.root.querySelector('[data-action="undo"]').addEventListener('click', () => this._undo());
    this.root.querySelector('[data-action="redo"]').addEventListener('click', () => this._redo());
    this.root.querySelector('[data-action="add-text"]').addEventListener('click', () => this._addTextElement());
    this.root.querySelector('[data-action="draw"]').addEventListener('click', () => this._toggleDrawMode());
    this.root.querySelector('[data-action="stickers"]').addEventListener('click', () => this._openStickerPicker());
    this.root.querySelector('[data-action="gif"]').addEventListener('click', () => this._openGifPicker());
    this.root.querySelector('[data-action="music"]').addEventListener('click', () => this._openMusicPicker());
    this.root.querySelector('[data-action="crop"]').addEventListener('click', () => this._openCropTool());
    this.root.querySelector('[data-action="save"]').addEventListener('click', () => this._saveDraft());

    // Navigation slides
    this.root.querySelectorAll('[data-slide-index]').forEach(btn => {
      btn.addEventListener('click', () => this._switchSlide(parseInt(btn.dataset.slideIndex, 10)));
    });
    this.root.querySelector('[data-action="add-slide"]').addEventListener('click', () => this._addSlide());

    // Timeline slide
    this.root.querySelector('[data-action="play-pause"]').addEventListener('click', () => this._togglePlay());
    this.root.querySelector('[data-timeline-track]').addEventListener('click', (e) => this._seekTimeline(e));

    // Outils
    this.root.querySelectorAll('[data-tool]').forEach(btn => {
      btn.addEventListener('click', () => this._setActiveTool(btn.dataset.tool));
    });

    // Propriétés texte
    this.root.querySelector('[data-text-font]').addEventListener('change', (e) => this._updateTextProperty('font', e.target.value));
    this.root.querySelectorAll('[data-text-color]').forEach(btn => {
      btn.addEventListener('click', () => this._updateTextProperty('color', btn.dataset.color));
    });
    this.root.querySelector('[data-text-size]').addEventListener('input', (e) => this._updateTextProperty('size', parseInt(e.target.value, 10)));
    this.root.querySelector('[data-text-lineheight]').addEventListener('input', (e) => this._updateTextProperty('lineHeight', parseFloat(e.target.value)));
    this.root.querySelector('[data-text-opacity]').addEventListener('input', (e) => this._updateTextProperty('opacity', parseFloat(e.target.value)));
    this.root.querySelector('[data-text-bold]').addEventListener('click', () => this._toggleTextProperty('bold'));
    this.root.querySelector('[data-text-italic]').addEventListener('click', () => this._toggleTextProperty('italic'));
    this.root.querySelector('[data-text-shadow]').addEventListener('click', () => this._toggleTextProperty('shadow'));
    this.root.querySelector('[data-text-outline]').addEventListener('click', () => this._toggleTextProperty('outline'));
    this.root.querySelector('[data-text-bg]').addEventListener('click', () => this._toggleTextProperty('background'));
    this.root.querySelector('[data-text-align-left]').addEventListener('click', () => this._updateTextProperty('align', 'left'));
    this.root.querySelector('[data-text-align-center]').addEventListener('click', () => this._updateTextProperty('align', 'center'));
    this.root.querySelector('[data-text-align-right]').addEventListener('click', () => this._updateTextProperty('align', 'right'));

    // Dessin
    this.root.querySelector('[data-draw-color]').addEventListener('click', (e) => {
      if (e.target.matches('[data-color]')) this._setDrawColor(e.target.dataset.color);
    });
    this.root.querySelector('[data-draw-width]').addEventListener('input', (e) => this._setDrawWidth(parseInt(e.target.value, 10)));
    this.root.querySelector('[data-draw-eraser]').addEventListener('click', () => this._toggleEraser());
    this.root.querySelector('[data-draw-undo]').addEventListener('click', () => this._undoDrawing());
    this.root.querySelector('[data-draw-redo]').addEventListener('click', () => this._redoDrawing());
    this.root.querySelector('[data-draw-finish]').addEventListener('click', () => this._finishDrawing());

    // Stickers
    this.root.querySelectorAll('[data-sticker-cat]').forEach(btn => {
      btn.addEventListener('click', () => this._switchStickerCategory(btn.dataset.stickerCat));
    });

    // Actions globales
    this.root.querySelector('[data-action="duplicate-slide"]').addEventListener('click', () => this._duplicateSlide());
    this.root.querySelector('[data-action="delete-slide"]').addEventListener('click', () => this._deleteSlide());
    this.root.querySelector('[data-action="preview-all"]').addEventListener('click', () => this._previewAll());
    this.root.querySelector('[data-action="validate-publish"]').addEventListener('click', () => this._validateAndPublish());
    this.root.querySelector('[data-action="delete-element"]').addEventListener('click', () => this._deleteSelectedElement());

    // Gestionnaires de clic sur le canvas (délégation)
    this.canvasHost = this.root.querySelector('[data-canvas-host]');
    this.canvasHost.addEventListener('pointerdown', (e) => this._onCanvasPointerDown(e));
    this.canvasHost.addEventListener('pointermove', (e) => this._onCanvasPointerMove(e));
    this.canvasHost.addEventListener('pointerup', (e) => this._onCanvasPointerUp(e));
    this.canvasHost.addEventListener('wheel', (e) => this._onCanvasWheel(e), { passive: false });
  }

  // ----------------------------------------------------------
  // Initialisation par slide
  // ----------------------------------------------------------
  _initSlide(index) {
    if (index < 0 || index >= this.designDocuments.length) return;

    this.currentSlideIndex = index;
    const design = this.designDocuments[index] || this._createEmptyDesign();
    this.slides[index] = this.slides[index] || { type: 'photo' };

    // Créer l'état éditeur pour ce design
    this.state = new EditorState(normalizeDesign(design));
    this.state.format = STORY_FORMAT;

    // Canvas
    const canvasEl = this.root.querySelector('[data-canvas]');
    this.canvas = new EditorCanvas({ state: this.state, canvas: canvasEl });
    this.canvas.mount(this.canvasHost);

    // Interaction
    this.interaction = new EditorInteraction({
      canvas: this.canvas,
      state: this.state,
      onGesture: () => this._onSelectionChanged(),
    });
    this.interaction.attach();

    // Panneaux (props, layers, etc.)
    const panelsHost = document.createElement('div');
    panelsHost.className = 'story-panels-host';
    this.root.querySelector('[data-tools-panel]').appendChild(panelsHost);
    this.panels = new EditorPanels({
      root: panelsHost,
      state: this.state,
      canvas: this.canvas,
      interaction: this.interaction,
      deps: this.deps,
      onAction: (action, payload) => this._onPanelAction(action, payload),
    });
    this.panels.renderLayout();

    // Timeline (simplifiée pour Story)
    const tlHost = this.root.querySelector('[data-slide-timeline]');
    this.timeline = new EditorTimeline({
      root: this,
      state: this.state,
      onSelectClip: (clipId) => {
        const info = this.state.getClipById(clipId);
        if (info) this.state.selectClip(info.trackId, clipId);
      },
    });
    this.timeline.mount(tlHost);
    this.timeline._zoom = 8; // Zoom plus grand pour 5s
    this.timeline._syncZoom();

    // Mettre à jour la navigation
    this._updateSlideNav();

    // Historique
    this.history = [this.state.toJSON()];
    this.historyIndex = 0;
    this._updateUndoRedo();
  }

  _createEmptyDesign() {
    return {
      version: 2,
      format: STORY_FORMAT,
      background: { color: '#000000' },
      elements: [],
      carousel: [],
      timeline: { fps: 30, tracks: [] },
    };
  }

  _switchSlide(index) {
    if (index === this.currentSlideIndex) return;
    if (index < 0 || index >= this.slides.length) return;

    // Sauvegarder le design courant
    if (this.state) {
      this.designDocuments[this.currentSlideIndex] = this.state.toJSON();
    }

    // Nettoyer l'ancien
    this._cleanupSlide();

    // Initialiser le nouveau
    this._initSlide(index);
  }

  _cleanupSlide() {
    if (this.interaction) { this.interaction.detach(); this.interaction = null; }
    if (this.canvas) { this.canvas.destroy(); this.canvas = null; }
    if (this.panels) { this.panels = null; }
    if (this.timeline) { this.timeline.destroy(); this.timeline = null; }
    const panelsHost = this.root.querySelector('.story-panels-host');
    if (panelsHost) panelsHost.remove();
  }

  _updateSlideNav() {
    this.root.querySelectorAll('[data-slide-index]').forEach((btn, i) => {
      btn.classList.toggle('active', i === this.currentSlideIndex);
    });
  }

  // ----------------------------------------------------------
  // Gestion des outils
  // ----------------------------------------------------------
  _setActiveTool(tool) {
    this.root.querySelectorAll('[data-tool]').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.tool === tool);
      btn.setAttribute('aria-pressed', btn.dataset.tool === tool);
    });
    this.root.querySelectorAll('[data-tool-group]').forEach(group => {
      group.classList.toggle('hidden', group.dataset.toolGroup !== tool);
    });
    this.currentTool = tool;

    if (tool === 'draw') this._toggleDrawMode(true);
    else if (this.drawingMode) this._toggleDrawMode(false);
    if (tool === 'sticker') this._openStickerPicker();
  }

  // ----------------------------------------------------------
  // Texte
  // ----------------------------------------------------------
  _addTextElement() {
    const w = STORY_FORMAT.width, h = STORY_FORMAT.height;
    const el = this.state.addElement({
      type: 'text',
      text: 'Nouveau texte',
      x: w / 2,
      y: h / 2,
      w: w * 0.8,
      h: 120,
      size: 48,
      font: 'arial',
      color: '#ffffff',
      bold: false,
      italic: false,
      align: 'center',
      shadow: true,
      outline: false,
      background: false,
      backgroundColor: '#000000',
      opacity: 1,
      rotation: 0,
    });
    this.state.selectElement(el.id);
    this._setActiveTool('text');
    this._pushHistory();
  }

  _updateTextProperty(prop, value) {
    const el = this.state.getSelectedElement?.();
    if (!el || el.type !== 'text') return;
    this.state.beginTransaction();
    if (prop === 'font') this.state.updateElement(el.id, { font: value });
    else if (prop === 'color') this.state.updateElement(el.id, { color: value });
    else if (prop === 'size') this.state.updateElement(el.id, { size: value });
    else if (prop === 'lineHeight') this.state.updateElement(el.id, { lineHeight: value });
    else if (prop === 'opacity') this.state.updateElement(el.id, { opacity: value });
    else if (prop === 'align') this.state.updateElement(el.id, { align: value });
    this.state.commitTransaction();
    this._pushHistory();
  }

  _toggleTextProperty(prop) {
    const el = this.state.getSelectedElement?.();
    if (!el || el.type !== 'text') return;
    const current = el[prop];
    this.state.beginTransaction();
    this.state.updateElement(el.id, { [prop]: !current });
    this.state.commitTransaction();
    this._pushHistory();
    // Mettre à jour l'UI
    const btn = this.root.querySelector(`[data-text-${prop}]`);
    if (btn) btn.classList.toggle('active', !current);
  }

  // ----------------------------------------------------------
  // Dessin
  // ----------------------------------------------------------
  _toggleDrawMode(force) {
    this.drawingMode = force !== undefined ? force : !this.drawingMode;
    const btn = this.root.querySelector('[data-tool="draw"]');
    if (btn) btn.classList.toggle('active', this.drawingMode);

    if (this.drawingMode) {
      this._setActiveTool('draw');
      this.currentDrawingPath = { points: [], color: '#ffffff', width: 3 };
      this.drawingPaths = [];
    } else {
      this._setActiveTool('select');
    }
  }

  _onCanvasPointerDown(e) {
    if (!this.drawingMode) return;
    const rect = this.canvasHost.getBoundingClientRect();
    const x = (e.clientX - rect.left) * (STORY_FORMAT.width / rect.width);
    const y = (e.clientY - rect.top) * (STORY_FORMAT.height / rect.height);
    this.currentDrawingPath = {
      points: [{ x, y }],
      color: this.drawColor || '#ffffff',
      width: this.drawWidth || 3,
    };
    this.canvasHost.setPointerCapture(e.pointerId);
  }

  _onCanvasPointerMove(e) {
    if (!this.drawingMode || !this.currentDrawingPath) return;
    const rect = this.canvasHost.getBoundingClientRect();
    const x = (e.clientX - rect.left) * (STORY_FORMAT.width / rect.width);
    const y = (e.clientY - rect.top) * (STORY_FORMAT.height / rect.height);
    this.currentDrawingPath.points.push({ x, y });
    this._renderDrawingPreview();
  }

  _onCanvasPointerUp(e) {
    if (!this.drawingMode || !this.currentDrawingPath) return;
    this.canvasHost.releasePointerCapture(e.pointerId);
    if (this.currentDrawingPath.points.length > 1) {
      this.drawingPaths.push(this.currentDrawingPath);
      this._commitDrawing();
    }
    this.currentDrawingPath = null;
  }

  _renderDrawingPreview() {
    if (!this.currentDrawingPath) return;
    const ctx = this.canvas.ctx;
    ctx.save();
    ctx.strokeStyle = this.currentDrawingPath.color;
    ctx.lineWidth = this.currentDrawingPath.width;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.beginPath();
    this.currentDrawingPath.points.forEach((p, i) => {
      if (i === 0) ctx.moveTo(p.x, p.y);
      else ctx.lineTo(p.x, p.y);
    });
    ctx.stroke();
    ctx.restore();
  }

  _commitDrawing() {
    // Convertir les paths en éléments SVG/dessin persistants
    // Pour l'instant, on stocke dans le design comme élément "drawing"
    const drawingEl = this.state.addElement({
      type: 'drawing',
      paths: this.drawingPaths.map(p => ({
        points: p.points,
        color: p.color,
        width: p.width,
      })),
      x: 0, y: 0, w: STORY_FORMAT.width, h: STORY_FORMAT.height,
      opacity: 1,
    });
    this.state.selectElement(drawingEl.id);
    this._pushHistory();
  }

  _setDrawColor(color) {
    this.drawColor = color;
    this.root.querySelectorAll('[data-draw-color] .story-color-swatch').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.color === color);
    });
  }

  _setDrawWidth(width) {
    this.drawWidth = width;
  }

  _toggleEraser() {
    this.isEraser = !this.isEraser;
    this._setDrawColor(this.isEraser ? '#000000' : (this.drawColor || '#ffffff'));
    const btn = this.root.querySelector('[data-draw-eraser]');
    if (btn) btn.classList.toggle('active', this.isEraser);
  }

  _undoDrawing() {
    if (this.drawingPaths.length > 0) {
      this.drawingPaths.pop();
      this._commitDrawing();
    }
  }

  _redoDrawing() {
    // TODO: pile de redo pour dessin
  }

  _finishDrawing() {
    this._toggleDrawMode(false);
  }

  // ----------------------------------------------------------
  // Stickers
  // ----------------------------------------------------------
  _openStickerPicker() {
    this._setActiveTool('sticker');
    this._renderStickerGrid('emojis');
  }

  _switchStickerCategory(cat) {
    this.root.querySelectorAll('[data-sticker-cat]').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.stickerCat === cat);
    });
    this._renderStickerGrid(cat);
  }

  _renderStickerGrid(cat) {
    const grid = this.root.querySelector('[data-sticker-grid]');
    const items = STICKER_LIBRARIES[cat] || [];
    grid.innerHTML = items.map(item => {
      const isEmoji = typeof item === 'string' && item.length <= 2;
      const label = isEmoji ? item : (typeof item === 'string' ? item : item.label);
      return `<button type="button" class="story-sticker-item" data-sticker="${esc(label)}" title="${esc(label)}">${isEmoji ? `<span style="font-size:2rem">${label}</span>` : `<span>${label}</span>`}</button>`;
    }).join('');

    grid.querySelectorAll('[data-sticker]').forEach(btn => {
      btn.addEventListener('click', () => this._addSticker(btn.dataset.sticker));
    });
  }

  _addSticker(label) {
    const w = STORY_FORMAT.width, h = STORY_FORMAT.height;
    const el = this.state.addElement({
      type: 'sticker',
      text: label,
      x: w / 2,
      y: h / 2,
      w: 120,
      h: 120,
      size: 48,
      font: 'arial',
      color: '#ffffff',
      opacity: 1,
      rotation: 0,
    });
    this.state.selectElement(el.id);
    this._pushHistory();
  }

  _openGifPicker() {
    // TODO: Intégrer API GIPHY/Tenor quand droits disponibles
    alert('Recherche GIF : à connecter avec une API (GIPHY/Tenor) quand les droits le permettent.');
  }

  _openMusicPicker() {
    // Réutiliser le système audio existant
    alert('Sélection musicale : réutilise le système audio ForgeAI existant (audio local + catalogue Meta).');
  }

  _openCropTool() {
    // TODO: Outil de recadrage 9:16
    alert('Recadrage 9:16 : à implémenter avec editorGeometry.coverCrop');
  }

  // ----------------------------------------------------------
  // Gestion slides
  // ----------------------------------------------------------
  _addSlide() {
    const newIndex = this.slides.length;
    const w = STORY_FORMAT.width, h = STORY_FORMAT.height;

    // Nouveau design vide
    const design = this._createEmptyDesign();
    this.designDocuments.push(design);
    this.slides.push({ type: 'photo' });

    // Ajouter à la nav
    const nav = this.root.querySelector('[data-slide-nav]');
    const addBtn = nav.querySelector('[data-action="add-slide"]');
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'story-slide-thumb';
    btn.dataset.slideIndex = newIndex;
    btn.title = `Slide ${newIndex + 1}`;
    btn.innerHTML = `<span class="story-slide-type">📷</span><span class="story-slide-num">${newIndex + 1}</span>`;
    btn.addEventListener('click', () => this._switchSlide(newIndex));
    nav.insertBefore(btn, addBtn);

    this._switchSlide(newIndex);
  }

  _duplicateSlide() {
    const currentDesign = this.state.toJSON();
    const newIndex = this.slides.length;

    this.designDocuments.push(JSON.parse(JSON.stringify(currentDesign)));
    this.slides.push({ ...this.slides[this.currentSlideIndex] });

    const nav = this.root.querySelector('[data-slide-nav]');
    const addBtn = nav.querySelector('[data-action="add-slide"]');
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'story-slide-thumb';
    btn.dataset.slideIndex = newIndex;
    btn.innerHTML = `<span class="story-slide-type">${esc(this.slides[newIndex].type || '📷')}</span><span class="story-slide-num">${newIndex + 1}</span>`;
    btn.addEventListener('click', () => this._switchSlide(newIndex));
    nav.insertBefore(btn, addBtn);

    this._switchSlide(newIndex);
  }

  _deleteSlide() {
    if (this.slides.length <= 1) {
      alert('Impossible de supprimer la dernière Story.');
      return;
    }
    if (!confirm('Supprimer cette Story ?')) return;

    this.designDocuments.splice(this.currentSlideIndex, 1);
    this.slides.splice(this.currentSlideIndex, 1);

    // Reconstruire la nav
    const nav = this.root.querySelector('[data-slide-nav]');
    nav.querySelectorAll('[data-slide-index]').forEach(btn => btn.remove());
    const addBtn = nav.querySelector('[data-action="add-slide"]');
    this.slides.forEach((s, i) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'story-slide-thumb' + (i === this.currentSlideIndex ? ' active' : '');
      btn.dataset.slideIndex = i;
      btn.innerHTML = `<span class="story-slide-type">${esc(s.type || '📷')}</span><span class="story-slide-num">${i + 1}</span>`;
      btn.addEventListener('click', () => this._switchSlide(i));
      nav.insertBefore(btn, addBtn);
    });

    const newIndex = Math.min(this.currentSlideIndex, this.slides.length - 1);
    this._switchSlide(newIndex);
  }

  // ----------------------------------------------------------
  // Timeline / Lecture
  // ----------------------------------------------------------
  _togglePlay() {
    this.isPlaying = !this.isPlaying;
    const btn = this.root.querySelector('[data-action="play-pause"]');
    btn.innerHTML = this.isPlaying
      ? '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>'
      : '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21"/></svg>';

    if (this.isPlaying) {
      this._startPlayback();
    } else {
      this._stopPlayback();
    }
  }

  _startPlayback() {
    const track = this.root.querySelector('[data-timeline-track]');
    const playhead = this.root.querySelector('[data-playhead]');
    const timeEl = this.root.querySelector('[data-timeline-time]');
    const duration = STORY_SLIDE_DURATION;
    const startTime = Date.now();

    const animate = () => {
      if (!this.isPlaying) return;
      const elapsed = Date.now() - startTime;
      const progress = Math.min(elapsed / duration, 1);
      playhead.style.left = `${progress * 100}%`;
      timeEl.textContent = `${(elapsed / 1000).toFixed(1)}s / ${(duration / 1000).toFixed(1)}s`;

      if (progress >= 1) {
        this.isPlaying = false;
        this._togglePlay();
        return;
      }
      this.playTimer = requestAnimationFrame(animate);
    };
    animate();
  }

  _stopPlayback() {
    if (this.playTimer) {
      cancelAnimationFrame(this.playTimer);
      this.playTimer = null;
    }
  }

  _seekTimeline(e) {
    const track = e.currentTarget;
    const rect = track.getBoundingClientRect();
    const progress = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const playhead = this.root.querySelector('[data-playhead]');
    const timeEl = this.root.querySelector('[data-timeline-time]');
    const duration = STORY_SLIDE_DURATION;

    playhead.style.left = `${progress * 100}%`;
    timeEl.textContent = `${(progress * duration / 1000).toFixed(1)}s / ${(duration / 1000).toFixed(1)}s`;
  }

  // ----------------------------------------------------------
  // Historique Undo/Redo
  // ----------------------------------------------------------
  _pushHistory() {
    if (!this.state) return;
    const current = this.state.toJSON();
    this.history = this.history.slice(0, this.historyIndex + 1);
    this.history.push(current);
    this.historyIndex = this.history.length - 1;
    if (this.history.length > 50) { this.history.shift(); this.historyIndex--; }
    this._updateUndoRedo();
  }

  _undo() {
    if (this.historyIndex <= 0) return;
    this.historyIndex--;
    this._restoreHistory();
  }

  _redo() {
    if (this.historyIndex >= this.history.length - 1) return;
    this.historyIndex++;
    this._restoreHistory();
  }

  _restoreHistory() {
    const design = this.history[this.historyIndex];
    this.state.replaceDesign(design);
    this.designDocuments[this.currentSlideIndex] = design;
    this.canvas.requestRender();
    this._updateUndoRedo();
  }

  _updateUndoRedo() {
    this.root.querySelector('[data-action="undo"]').disabled = this.historyIndex <= 0;
    this.root.querySelector('[data-action="redo"]').disabled = this.historyIndex >= this.history.length - 1;
  }

  // ----------------------------------------------------------
  // Sélection & Suppression
  // ----------------------------------------------------------
  _onSelectionChanged() {
    const el = this.state.getSelectedElement?.();
    const hasSelection = !!el;

    // Mettre à jour les outils selon le type d'élément
    if (hasSelection) {
      if (el.type === 'text') this._setActiveTool('text');
      else if (el.type === 'drawing') this._setActiveTool('draw');
      else if (el.type === 'sticker') this._setActiveTool('sticker');
    }

    // Mettre à jour l'UI propriétés texte
    if (el && el.type === 'text') {
      this.root.querySelector('[data-text-font]').value = el.font || 'arial';
      this.root.querySelector('[data-text-size]').value = el.size || 48;
      this.root.querySelector('[data-text-lineheight]').value = el.lineHeight || 1.2;
      this.root.querySelector('[data-text-opacity]').value = el.opacity || 1;
      this.root.querySelector('[data-text-bold]').classList.toggle('active', el.bold);
      this.root.querySelector('[data-text-italic]').classList.toggle('active', el.italic);
      this.root.querySelector('[data-text-shadow]').classList.toggle('active', el.shadow);
      this.root.querySelector('[data-text-outline]').classList.toggle('active', el.outline);
      this.root.querySelector('[data-text-bg]').classList.toggle('active', el.background);
    }
  }

  _deleteSelectedElement() {
    const el = this.state.getSelectedElement?.();
    if (!el) return;
    this.state.deleteElement(el.id);
    this._pushHistory();
  }

  // ----------------------------------------------------------
  // Aperçu & Publication
  // ----------------------------------------------------------
  _previewAll() {
    // Créer une modale d'aperçu global
    const modal = document.createElement('div');
    modal.className = 'story-preview-modal';
    modal.innerHTML = `
      <div class="story-preview-overlay" data-action="close-preview">
        <div class="story-preview-container">
          <header class="story-preview-header">
            <h3>Aperçu de la série (${this.slides.length} Stories)</h3>
            <button type="button" class="story-btn story-btn-icon" data-action="close-preview">×</button>
          </header>
          <div class="story-preview-grid">
            ${this.designDocuments.map((design, i) => `
              <div class="story-preview-slide" data-slide="${i}">
                <canvas class="story-preview-canvas" width="270" height="480"></canvas>
                <div class="story-preview-info">
                  <span class="story-preview-num">${i + 1}/${this.slides.length}</span>
                  <span class="story-preview-type">${esc(this.slides[i].type || 'photo')}</span>
                </div>
              </div>
            `).join('')}
          </div>
          <footer class="story-preview-footer">
            <button type="button" class="story-btn story-btn-secondary" data-action="close-preview">Fermer</button>
            <button type="button" class="story-btn story-btn-success" data-action="validate-publish">✓ Valider et publier</button>
          </footer>
        </div>
      </div>
    `;
    this.root.querySelector('[data-modals]').appendChild(modal);

    // Rendre chaque slide dans le canvas de preview
    this.designDocuments.forEach((design, i) => {
      const canvas = modal.querySelector(`[data-slide="${i}"] canvas`);
      const ctx = canvas.getContext('2d');
      // Rendu simplifié : fond + éléments
      ctx.fillStyle = design.background?.color || '#000000';
      ctx.fillRect(0, 0, 270, 480);
      // TODO: Rendu complet des éléments (texte, images, stickers)
    });

    modal.querySelectorAll('[data-action="close-preview"]').forEach(btn => {
      btn.addEventListener('click', () => modal.remove());
    });
    modal.querySelector('[data-action="validate-publish"]').addEventListener('click', () => {
      modal.remove();
      this._validateAndPublish();
    });
  }

  _validateAndPublish() {
    // Sauvegarder tous les designs
    this.designDocuments[this.currentSlideIndex] = this.state.toJSON();

    const payload = {
      slides: this.slides,
      design_documents: this.designDocuments,
      status: 'awaiting_validation',
    };

    this.callbacks.onPublish?.(this.draft.id, payload);
  }

  _saveDraft() {
    this.designDocuments[this.currentSlideIndex] = this.state.toJSON();

    const payload = {
      slides: this.slides,
      design_documents: this.designDocuments,
      status: 'editing',
    };

    this.callbacks.onSave?.(this.draft.id, payload);
  }

  // ----------------------------------------------------------
  // Gestes tactiles & Clavier
  // ----------------------------------------------------------
  _setupTouchGestures() {
    let touchStart = null;
    let initialScale = 1;
    let initialRotation = 0;

    this.canvasHost.addEventListener('touchstart', (e) => {
      if (e.touches.length === 2) {
        // Pinch to zoom / rotate sur élément sélectionné
        const el = this.state.getSelectedElement?.();
        if (el) {
          touchStart = {
            midX: (e.touches[0].clientX + e.touches[1].clientX) / 2,
            midY: (e.touches[0].clientY + e.touches[1].clientY) / 2,
            dist: Math.hypot(
              e.touches[0].clientX - e.touches[1].clientX,
              e.touches[0].clientY - e.touches[1].clientY
            ),
            angle: Math.atan2(
              e.touches[0].clientY - e.touches[1].clientY,
              e.touches[0].clientX - e.touches[1].clientX
            ),
            initialScale: el.scale || 1,
            initialRotation: el.rotation || 0,
          };
        }
      }
    }, { passive: false });

    this.canvasHost.addEventListener('touchmove', (e) => {
      if (!touchStart || e.touches.length !== 2) return;
      e.preventDefault();

      const el = this.state.getSelectedElement?.();
      if (!el) return;

      const midX = (e.touches[0].clientX + e.touches[1].clientX) / 2;
      const midY = (e.touches[0].clientY + e.touches[1].clientY) / 2;
      const dist = Math.hypot(
        e.touches[0].clientX - e.touches[1].clientX,
        e.touches[0].clientY - e.touches[1].clientY
      );
      const angle = Math.atan2(
        e.touches[0].clientY - e.touches[1].clientY,
        e.touches[0].clientX - e.touches[1].clientX
      );

      const scale = touchStart.initialScale * (dist / touchStart.dist);
      const rotation = touchStart.initialRotation + (angle - touchStart.angle);

      this.state.beginTransaction();
      this.state.updateElement(el.id, {
        scale: Math.max(0.1, Math.min(5, scale)),
        rotation: rotation * 180 / Math.PI,
      });
      this.state.commitTransaction();
      this.canvas.requestRender();
    }, { passive: false });

    this.canvasHost.addEventListener('touchend', () => {
      if (touchStart) {
        this._pushHistory();
        touchStart = null;
      }
    });
  }

  _setupKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

      if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
        e.preventDefault();
        e.shiftKey ? this._redo() : this._undo();
      }
      if ((e.ctrlKey || e.metaKey) && e.key === 'y') {
        e.preventDefault();
        this._redo();
      }
      if (e.key === 'Delete' || e.key === 'Backspace') {
        this._deleteSelectedElement();
      }
      if (e.key === 'Escape') {
        this.callbacks.onClose?.();
      }
      if (e.key === ' ') {
        e.preventDefault();
        this._togglePlay();
      }
      if (e.key === 'ArrowLeft') {
        this._switchSlide(this.currentSlideIndex - 1);
      }
      if (e.key === 'ArrowRight') {
        this._switchSlide(this.currentSlideIndex + 1);
      }
    });
  }

  // ----------------------------------------------------------
  // Wheel zoom (desktop)
  // ----------------------------------------------------------
  _onCanvasWheel(e) {
    if (!e.ctrlKey && !e.metaKey) return;
    e.preventDefault();

    const el = this.state.getSelectedElement?.();
    if (!el) return;

    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    const newScale = Math.max(0.1, Math.min(5, (el.scale || 1) * delta));

    this.state.beginTransaction();
    this.state.updateElement(el.id, { scale: newScale });
    this.state.commitTransaction();
    this.canvas.requestRender();
    this._pushHistory();
  }

  // ----------------------------------------------------------
  // Panel actions (depuis EditorPanels)
  // ----------------------------------------------------------
  _onPanelAction(action, payload) {
    // Relay actions from panels (photo upload, background, etc.)
    if (action === 'set-photo' || action === 'set-bg' || action === 'add-carousel') {
      // Géré par le panel, on push history
      this._pushHistory();
    }
  }

  // ----------------------------------------------------------
  // Nettoyage
  // ----------------------------------------------------------
  destroy() {
    this._stopPlayback();
    this._cleanupSlide();
    if (this.root && this.root.parentNode) this.root.parentNode.removeChild(this.root);
    this.root = null;
  }
}

export function createStoryEditorView(params) {
  return new StoryEditorView(params);
}