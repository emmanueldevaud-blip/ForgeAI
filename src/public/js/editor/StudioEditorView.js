/**
 * Vue de l'éditeur graphique du Studio : barre d'actions, format,
 * undo/redo, sauvegarde du design et export vers une photo publiable.
 */

import { EditorState, FORMATS, normalizeDesign } from './editorState.js?v=1';
import { EditorCanvas } from './editorCanvas.js?v=1';
import { EditorInteraction } from './editorInteraction.js?v=1';
import { EditorPanels } from './editorPanels.js?v=1';
import { coverCrop } from './editorGeometry.js?v=1';

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
    this.root = null;
    this.busy = false;
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
          <button type="button" class="btn btn-primary" data-ed-apply>Appliquer &amp; enregistrer</button>
        </div>
      </div>
      <div class="ed-body" data-ed-body></div>
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

    this.state.onChange = () => {
      this.canvas.requestRender();
      this.panels.onSelectionChanged();
      this._updateUndoButtons();
    };

    this._bindHeader();
    this._updateUndoButtons();
    this.canvas.ensureImages();
    return this.root;
  }

  destroy() {
    if (this.interaction) this.interaction.detach();
    if (this.canvas) this.canvas.destroy();
    if (this.root && this.root.parentNode) this.root.parentNode.removeChild(this.root);
    this.root = null;
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
  }

  _updateUndoButtons() {
    if (!this.root) return;
    const undo = this.root.querySelector('[data-ed-undo]');
    const redo = this.root.querySelector('[data-ed-redo]');
    if (undo) undo.disabled = !this.state.undoStack.length;
    if (redo) redo.disabled = !this.state.redoStack.length;
  }

  _setStatus(msg, kind = 'info') {
    const el = this.root?.querySelector('[data-ed-status]');
    if (!el) return;
    el.textContent = msg || '';
    el.className = `ed-status ed-status--${kind}`;
    if (msg) {
      clearTimeout(this._statusTimer);
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
