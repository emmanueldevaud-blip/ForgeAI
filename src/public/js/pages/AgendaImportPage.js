import { authStore } from '../stores/auth.js';
import {
  analyzeImport,
  listImports,
  getImportRows,
  updateImportRow,
  validateImport,
  getAgendaUsers,
} from '../services/agendaApi.js';

const STATUS_LABELS = {
  ready: 'Prête',
  needs_review: 'À vérifier',
  skipped_existing: 'Déjà présente',
  excluded: 'Exclue',
  validated: 'Validée',
};

const STATUS_COLORS = {
  ready: 'badge--success',
  needs_review: 'badge--warning',
  skipped_existing: 'badge--info',
  excluded: 'badge--secondary',
  validated: 'badge--success',
};

const REVIEW_REASON_LABELS = {
  site_manquant: 'Site manquant (P sans X)',
  utilisateur_ambiguous: 'Utilisateur ambigu',
  utilisateur_proche: 'Nom proche d\'un utilisateur',
  sites_multiples: 'Sites multiples marqués',
};

export function createAgendaImportPage(router) {
  let element = null;
  let currentBatch = null;
  let users = [];
  let rows = [];
  let filters = { status: '', start_date: '', end_date: '' };
  let pagination = { limit: 200, offset: 0, total: 0 };
  let loading = false;
  let step = 'upload';

  const renderProgress = (state, message, detail = '') => {
    const container = element?.querySelector('[data-progress]');
    if (!container) return;
    if (!state) {
      container.hidden = true;
      return;
    }
    container.hidden = false;
    const pct = state === 'uploading' ? 10 : state === 'analyzing' ? 30 : state === 'preview' ? 60 : state === 'validating' ? 90 : 100;
    container.innerHTML = `
      <div class="import-progress-header">
        <strong>${message}</strong>
        ${detail ? '<span>' + detail + '</span>' : ''}
      </div>
      <div class="import-progress-bar"><span style="width:${pct}%"></span></div>
    `;
  };

  async function loadUsers() {
    try {
      users = await getAgendaUsers();
    } catch (e) {
      console.error('Erreur chargement utilisateurs:', e);
    }
  }

  async function handleFileSelect(e) {
    const file = e.target.files[0];
    if (!file) return;
    const input = e.target;
    input.value = '';

    renderProgress('uploading', 'Televersement du fichier...');
    try {
      renderProgress('analyzing', 'Analyse du classeur et detection des anomalies...');
      const batch = await analyzeImport(file);
      currentBatch = batch;
      step = 'preview';
      await loadPreview();
      renderPreviewUI();
    } catch (error) {
      renderProgress('error', error.message || 'Echec de l\'analyse');
      setTimeout(() => renderProgress(null), 5000);
    }
  }

  async function loadPreview() {
    loading = true;
    renderProgress('preview', 'Chargement des lignes...');
    try {
      const params = {
        limit: pagination.limit,
        offset: pagination.offset,
      };
      if (filters.status) params.status = filters.status;
      if (filters.start_date) params.start_date = filters.start_date;
      if (filters.end_date) params.end_date = filters.end_date;
      const data = await getImportRows(currentBatch.id, params);
      rows = data;
      if (rows.length === 0 && currentBatch && currentBatch.status !== 'validated') {
        renderProgress('info', 'Aucune ligne a afficher (toutes les lignes sont "Deja presentes" ou exclues)');
      } else {
        renderProgress(null);
      }
    } catch (error) {
      console.error('Erreur chargement lignes:', error);
      renderProgress('error', 'Impossible de charger les lignes: ' + (error.message || 'Erreur reseau'));
      loading = false;
      return;
    }
    loading = false;
    renderTable();
  }

  function renderPreviewUI() {
    if (!element) return;
    const uploadCard = element.querySelector('#upload-card');
    const previewContainer = element.querySelector('#preview-container');
    if (uploadCard) uploadCard.style.display = 'none';
    if (previewContainer) previewContainer.hidden = false;
    renderTable();
  }

  function renderTable() {
    const tbody = element?.querySelector('[data-rows]');
    if (!tbody) return;
    tbody.innerHTML = rows.map(r => {
      const statusBadge = '<span class="badge ' + (STATUS_COLORS[r.status] || '') + '">' + (STATUS_LABELS[r.status] || r.status) + '</span>';
      const reason = r.review_reason ? '<span class="badge badge--secondary" title="' + (REVIEW_REASON_LABELS[r.review_reason] || r.review_reason) + '">' + (REVIEW_REASON_LABELS[r.review_reason] || r.review_reason) + '</span>' : '';
      const userSelect = buildUserSelect(r);
      const roomSelect = buildRoomSelect(r);
      const actions = r.status === 'validated' ? '' : `
        <button class="btn btn-sm btn-secondary" data-action="save-row" data-row="${r.id}" ${loading ? 'disabled' : ''}>Sauvegarder</button>
        <button class="btn btn-sm btn-danger" data-action="exclude-row" data-row="${r.id}" ${loading ? 'disabled' : ''}>Exclure</button>
      `;
      return `
        <tr data-row="${r.id}">
          <td>${r.presence_date}</td>
          <td>${r.sheet_name}</td>
          <td>${r.raw_label}</td>
          <td>${r.site_label || '-'}</td>
          <td>${r.period}${r.is_remote ? ' (teletravail)' : ''}</td>
          <td>${userSelect}</td>
          <td>${roomSelect}</td>
          <td>${r.needs_workstation ? 'oui' : 'non'}</td>
          <td>${r.needs_meal ? 'oui' : 'non'}</td>
          <td>${statusBadge} ${reason}</td>
          <td>${actions}</td>
        </tr>
      `;
    }).join('');
  }

  function buildUserSelect(row) {
    const isExternal = !row.user_id && row.external_name;
    let html = '<select data-field="user_id" class="form-select form-select-sm" ' + (loading ? 'disabled' : '') + '>';
    if (isExternal) {
      html += '<option value="">Inscription libre</option>';
    } else {
      html += '<option value="">— Choisir —</option>';
    }
    if (row.suggestions?.length) {
      html += '<optgroup label="Suggestions">';
      row.suggestions.forEach(s => {
        const selected = row.user_id === s.user_id ? 'selected' : '';
        html += '<option value="' + s.user_id + '" ' + selected + '>' + s.label + ' (suggere)</option>';
      });
      html += '</optgroup>';
    }
    html += '<optgroup label="Tous les utilisateurs">';
    users.forEach(u => {
      const label = u.last_name + ' ' + u.first_name;
      const selected = row.user_id === u.id ? 'selected' : '';
      if (row.suggestions?.some(s => s.user_id === u.id)) return;
      html += '<option value="' + u.id + '" ' + selected + '>' + label + '</option>';
    });
    html += '</optgroup>';
    html += '</select>';
    if (isExternal) {
      html += ' <input type="text" data-field="external_name" class="form-input form-input-sm" value="' + escapeHtml(row.external_name) + '" placeholder="Nom libre" style="max-width:150px" ' + (loading ? 'disabled' : '') + '>';
    }
    if (row.status === 'needs_review' && row.review_reason && row.review_reason.startsWith('utilisateur_')) {
      html += ' <button type="button" class="btn btn-sm btn-secondary" data-action="set-external" data-row="' + row.id + '" ' + (loading ? 'disabled' : '') + '>Inscription libre</button>';
    }
    return html;
  }

  function buildRoomSelect(row) {
    const sites = ['Cebazat', 'Riom', 'Puteaux'];
    let html = '<select data-field="site_label" class="form-select form-select-sm" ' + (loading ? 'disabled' : '') + '>';
    html += '<option value="">' + (row.site_label ? 'Selectionne' : '— Choisir —') + '</option>';
    sites.forEach(s => {
      const selected = row.site_label === s ? 'selected' : '';
      html += '<option value="' + s + '" ' + selected + '>' + s + '</option>';
    });
    html += '</select>';
    if (row.status === 'needs_review' && row.review_reason === 'site_manquant') {
      html += ' <span class="badge badge--warning">Site requis</span>';
    }
    if (row.status === 'needs_review' && row.review_reason === 'sites_multiples') {
      html += ' <span class="badge badge--danger">Sites multiples</span>';
    }
    return html;
  }

  async function handleRowAction(e) {
    const btn = e.target.closest('button[data-action]');
    if (!btn) return;
    const rowId = parseInt(btn.dataset.row, 10);
    const rowEl = element.querySelector('tr[data-row="' + rowId + '"]');
    const userSelect = rowEl.querySelector('[data-field="user_id"]');
    const externalInput = rowEl.querySelector('[data-field="external_name"]');
    const siteSelect = rowEl.querySelector('[data-field="site_label"]');

    const payload = {};
    if (userSelect) {
      payload.user_id = userSelect.value ? parseInt(userSelect.value, 10) : null;
    }
    if (externalInput) {
      payload.external_name = externalInput.value.trim() || null;
    }
    if (siteSelect) {
      payload.site_label = siteSelect.value;
    }
    if (btn.dataset.action === 'exclude-row') {
      payload.skip = true;
    }
    if (btn.dataset.action === 'set-external') {
      const row = rows.find(r => r.id === rowId);
      if (row) {
        payload.external_name = row.raw_label;
        payload.user_id = null;
      }
    }

    try {
      loading = true;
      renderTable();
      const updated = await updateImportRow(currentBatch.id, rowId, payload);
      if (updated) {
        const idx = rows.findIndex(r => r.id === rowId);
        if (idx >= 0) rows[idx] = updated;
      }
    } catch (error) {
      alert('Erreur: ' + error.message);
    }
    loading = false;
    renderTable();
  }

  async function handleValidate() {
    if (!currentBatch) return;
    if (!confirm('Valider l\'import ? Les lignes "Pretes" seront creees en base.')) return;
    const validateBtn = element.querySelector('[data-action="validate"]');
    if (validateBtn) validateBtn.disabled = true;
    renderProgress('validating', 'Validation et enregistrement en base...');
    try {
      const result = await validateImport(currentBatch.id);
      renderProgress('done', 'Import termine: ' + result.created + ' creees, ' + result.skipped + ' ignorees');
      currentBatch = result.batch;
      if (validateBtn) {
        validateBtn.disabled = true;
        validateBtn.textContent = 'Import valide';
      }
      await loadPreview();
      setTimeout(() => renderProgress(null), 5000);
    } catch (error) {
      console.error('[DEBUG] handleValidate error:', error);
      renderProgress('error', 'Echec validation: ' + (error.message || 'Erreur inconnue'));
      if (validateBtn) validateBtn.disabled = false;
    }
  }

  function handleFilterChange() {
    filters = {
      status: element.querySelector('[data-filter-status]')?.value || '',
      start_date: element.querySelector('[data-filter-start]')?.value || '',
      end_date: element.querySelector('[data-filter-end]')?.value || '',
    };
    pagination.offset = 0;
    loadPreview();
  }

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, c => {
      if (c === '&') return '&';
      if (c === '<') return '<';
      if (c === '>') return '>';
      if (c === '"') return '"';
      return c;
    });
  }

  async function render() {
    await loadUsers();
    element = document.createElement('div');
    element.className = 'page';
    element.innerHTML = `
      <div class="page-header">
        <h1>Import Agenda</h1>
        <div class="import-progress" data-progress hidden></div>
      </div>

      <!-- Etape 1 : Upload -->
      <div id="upload-card" class="card">
        <h2>Nouvel import</h2>
        <p>Selectionnez le fichier <strong>Calendrier des presences.xlsx</strong> (format B uniquement : feuilles avec sites Cebazat/Riom/Puteaux).</p>
        <label class="btn btn-primary">
          <input type="file" accept=".xlsx" hidden data-file-input>
          Choisir un fichier
        </label>
        <span class="file-name" data-file-name></span>
      </div>

      <!-- Etape 2 : Previsualisation + Validation (cachee au debut) -->
      <div id="preview-container" class="card" hidden>
        ${currentBatch ? `
        <div class="card" style="margin-bottom:1rem; background: var(--color-bg-secondary); padding: 1rem;">
          <h3 style="margin:0 0 0.5rem 0; font-size: var(--font-size-md);">Bilan de l'import</h3>
          <div style="display:flex; gap:1.5rem; flex-wrap:wrap; font-size: var(--font-size-sm);">
            <span><strong>Total:</strong> ${currentBatch.rows_total}</span>
            <span><strong>Pretes:</strong> ${currentBatch.rows_ready}</span>
            <span><strong>A verifier:</strong> ${currentBatch.rows_needs_review}</span>
            <span><strong>Deja presentes:</strong> ${currentBatch.rows_skipped_existing}</span>
            <span><strong>Exclues:</strong> ${currentBatch.rows_excluded}</span>
            ${currentBatch.week_start ? '<span><strong>Periode:</strong> ' + currentBatch.week_start + ' - ' + currentBatch.week_end + '</span>' : ''}
          </div>
        </div>
        ` : ''}
        <div class="card" style="margin-bottom:1rem">
          <div class="filters-row" style="display:flex; gap:1rem; flex-wrap:wrap; align-items:end; padding: 1rem; border-bottom: 1px solid var(--color-border-light);">
            <div>
              <label class="form-label">Statut</label>
              <select class="form-select" data-filter-status>
                <option value="">Tous</option>
                <option value="ready">Pretes</option>
                <option value="needs_review">A verifier</option>
                <option value="skipped_existing">Deja presentes</option>
                <option value="excluded">Exclues</option>
              </select>
            </div>
            <div>
              <label class="form-label">Du</label>
              <input type="date" class="form-input" data-filter-start>
            </div>
            <div>
              <label class="form-label">Au</label>
              <input type="date" class="form-input" data-filter-end>
            </div>
            <div style="margin-top:auto">
              <button class="btn btn-secondary" data-action="refresh">Rafraichir</button>
            </div>
          </div>
        </div>
        <div class="card" style="position: sticky; top: 0; z-index: 10; background: var(--color-surface-raised);">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem; padding: 1rem; border-bottom: 1px solid var(--color-border-light);">
            <h2 style="margin:0">Lignes a importer</h2>
            <div style="display:flex; gap:0.5rem">
              <button class="btn btn-primary" data-action="validate" ${currentBatch?.status === 'validated' ? 'disabled' : ''}>Valider l'import</button>
            </div>
          </div>
          <div class="table-responsive" style="max-height: calc(100vh - 300px); overflow-y: auto;">
            <table class="table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Feuille</th>
                  <th>Nom</th>
                  <th>Site</th>
                  <th>Periode</th>
                  <th>Utilisateur / Inscription libre</th>
                  <th>Local</th>
                  <th>Poste</th>
                  <th>Repas</th>
                  <th>Statut</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody data-rows></tbody>
            </table>
          </div>
        </div>
      </div>
    `;

    element.querySelector('[data-file-input]')?.addEventListener('change', handleFileSelect);
    element.querySelector('[data-file-input]')?.addEventListener('change', e => {
      const nameEl = element.querySelector('[data-file-name]');
      if (nameEl && e.target.files[0]) nameEl.textContent = ' -> ' + e.target.files[0].name;
    });
    element.querySelector('[data-filter-status]')?.addEventListener('change', handleFilterChange);
    element.querySelector('[data-filter-start]')?.addEventListener('change', handleFilterChange);
    element.querySelector('[data-filter-end]')?.addEventListener('change', handleFilterChange);
    element.querySelector('[data-action="refresh"]')?.addEventListener('click', loadPreview);
    element.querySelector('[data-action="validate"]')?.addEventListener('click', handleValidate);
    element.querySelector('[data-rows]')?.addEventListener('click', handleRowAction);

    return element;
  }

  return { render, initialize: async () => {} };
}