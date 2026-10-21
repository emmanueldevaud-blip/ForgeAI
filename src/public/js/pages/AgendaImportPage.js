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
};

export function createAgendaImportPage(router) {
  let element = null;
  let currentBatch = null;
  let users = [];
  let rows = [];
  let filters = { status: '', start_date: '', end_date: '' };
  let pagination = { limit: 200, offset: 0, total: 0 };
  let loading = false;

  const renderProgress = (state, message, detail = '') => {
    const container = element.querySelector('[data-progress]');
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
        ${detail ? `<span>${detail}</span>` : ''}
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

    renderProgress('uploading', 'Téléversement du fichier…');
    try {
      renderProgress('analyzing', 'Analyse du classeur et détection des anomalies…');
      const batch = await analyzeImport(file);
      currentBatch = batch;
      renderProgress('preview', 'Prévisualisation terminée', `${batch.rows_total} lignes, ${batch.rows_ready} prêtes, ${batch.rows_needs_review} à vérifier`);
      await loadPreview();
      showPreview();
    } catch (error) {
      renderProgress('error', error.message || 'Échec de l\'analyse');
      setTimeout(() => renderProgress(null), 5000);
    }
  }

  async function loadPreview() {
    loading = true;
    renderProgress('preview', 'Chargement des lignes…');
    try {
      const data = await getImportRows(currentBatch.id, {
        status: filters.status || undefined,
        start_date: filters.start_date || undefined,
        end_date: filters.end_date || undefined,
        limit: pagination.limit,
        offset: pagination.offset,
      });
      rows = data;
      renderProgress(null);
    } catch (error) {
      console.error('Erreur chargement lignes:', error);
    }
    loading = false;
    renderTable();
  }

  function showPreview() {
    const panel = element.querySelector('[data-tab-panel="preview"]');
    const importBtn = element.querySelector('[data-action="import"]');
    const previewBtn = element.querySelector('[data-action="preview"]');
    const validateBtn = element.querySelector('[data-action="validate"]');
    if (panel) panel.hidden = false;
    if (importBtn) importBtn.hidden = true;
    if (previewBtn) previewBtn.hidden = false;
    if (validateBtn) validateBtn.hidden = false;
    renderTable();
  }

  function renderTable() {
    const tbody = element.querySelector('[data-rows]');
    if (!tbody) return;
    tbody.innerHTML = rows.map(r => {
      const statusBadge = `<span class="badge ${STATUS_COLORS[r.status] || ''}">${STATUS_LABELS[r.status] || r.status}</span>`;
      const reason = r.review_reason ? `<span class="badge badge--secondary" title="${REVIEW_REASON_LABELS[r.review_reason] || r.review_reason}">${REVIEW_REASON_LABELS[r.review_reason] || r.review_reason}</span>` : '';
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
          <td>${r.period}${r.is_remote ? ' (télétravail)' : ''}</td>
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
    let html = `<select data-field="user_id" class="form-select form-select-sm" ${loading ? 'disabled' : ''}>`;
    html += `<option value="">${isExternal ? 'Inscription libre' : '— Choisir —'}</option>`;
    users.forEach(u => {
      const label = `${u.last_name} ${u.first_name}`;
      const selected = row.user_id === u.id ? 'selected' : '';
      html += `<option value="${u.id}" ${selected}>${label}</option>`;
    });
    html += '</select>';
    if (isExternal) {
      html += ` <input type="text" data-field="external_name" class="form-input form-input-sm" value="${escapeHtml(row.external_name)}" placeholder="Nom libre" style="max-width:150px" ${loading ? 'disabled' : ''}>`;
    }
    if (row.suggestions?.length) {
      html += ' <span class="badge badge--warning" title="Suggestions: ' + row.suggestions.map(s => s.label).join(', ') + '">⚠</span>';
    }
    return html;
  }

  function buildRoomSelect(row) {
    const sites = ['Cébazat', 'Riom', 'Puteaux'];
    let html = `<select data-field="room_id" class="form-select form-select-sm" ${loading ? 'disabled' : ''}>`;
    html += `<option value="">${row.room_id ? 'Sélectionné' : '— Choisir —'}</option>`;
    sites.forEach(s => {
      const selected = row.site_label === s ? 'selected' : '';
      html += `<option value="${s}" ${selected}>${s}</option>`;
    });
    html += '</select>';
    if (row.status === 'needs_review' && row.review_reason === 'site_manquant') {
      html += ' <span class="badge badge--warning">Site requis</span>';
    }
    return html;
  }

  async function handleRowAction(e) {
    const btn = e.target.closest('button[data-action]');
    if (!btn) return;
    const rowId = parseInt(btn.dataset.row, 10);
    const rowEl = element.querySelector(`tr[data-row="${rowId}"]`);
    const userSelect = rowEl.querySelector('[data-field="user_id"]');
    const externalInput = rowEl.querySelector('[data-field="external_name"]');
    const roomSelect = rowEl.querySelector('[data-field="room_id"]');

    const payload = {};
    if (userSelect) {
      payload.user_id = userSelect.value ? parseInt(userSelect.value, 10) : null;
    }
    if (externalInput) {
      payload.external_name = externalInput.value.trim() || null;
    }
    if (roomSelect) {
      // Map site label to room_id via service? For now send label, backend resolves
      payload.room_id = roomSelect.value; // temporary, will need mapping
    }
    if (btn.dataset.action === 'exclude-row') {
      payload.skip = true;
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
    if (!confirm('Valider l\'import ? Les lignes "Prêtes" seront créées en base.')) return;
    renderProgress('validating', 'Validation et enregistrement en base…');
    try {
      const result = await validateImport(currentBatch.id);
      renderProgress('done', `Import terminé: ${result.created} créées, ${result.skipped} ignorées`);
      currentBatch = result.batch;
      await loadPreview();
      setTimeout(() => renderProgress(null), 5000);
    } catch (error) {
      renderProgress('error', 'Échec validation: ' + error.message);
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
    return String(value ?? '').replace(/[&<>'"]/g, c => ({
      '&': '&',
      '<': '<',
      '>': '>',
      "'": '&#39;',
      '"': '"',
    }[c]));
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
      <div class="admin-tabs" role="tablist">
        <button role="tab" data-tab="import" class="admin-tab active">Importer</button>
        <button role="tab" data-tab="preview" class="admin-tab" hidden>Prévisualiser</button>
      </div>
      <div id="panel-import" class="admin-tab-panel admin-tab-panel--active" role="tabpanel" data-tab-content>
        <div class="card">
          <h2>Nouvel import</h2>
          <p>Sélectionnez le fichier <strong>Calendrier des présences.xlsx</strong> (format B uniquement : feuilles avec sites Cébazat/Riom/Puteaux).</p>
          <label class="btn btn-primary">
            <input type="file" accept=".xlsx" hidden data-file-input>
            Choisir un fichier
          </label>
          <span class="file-name" data-file-name></span>
        </div>
      </div>
      <div id="panel-preview" class="admin-tab-panel" role="tabpanel" data-tab-content hidden>
        <div class="card" style="margin-bottom:1rem">
          <div class="filters-row" style="display:flex; gap:1rem; flex-wrap:wrap; align-items:end">
            <div>
              <label class="form-label">Statut</label>
              <select class="form-select" data-filter-status>
                <option value="">Tous</option>
                <option value="ready">Prêtes</option>
                <option value="needs_review">À vérifier</option>
                <option value="skipped_existing">Déjà présentes</option>
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
              <button class="btn btn-secondary" data-action="refresh">Rafraîchir</button>
            </div>
          </div>
        </div>
        <div class="card">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem">
            <h2>Lignes à importer</h2>
            <div style="display:flex; gap:0.5rem">
              <button class="btn btn-primary" data-action="validate" ${currentBatch?.status === 'validated' ? 'disabled' : ''}>Valider l'import</button>
            </div>
          </div>
          <div class="table-responsive">
            <table class="table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Feuille</th>
                  <th>Nom</th>
                  <th>Site</th>
                  <th>Période</th>
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
      if (nameEl && e.target.files[0]) nameEl.textContent = ' → ' + e.target.files[0].name;
    });
    element.querySelectorAll('[data-tab]')?.forEach(btn => {
      btn.addEventListener('click', () => {
        element.querySelectorAll('[data-tab]').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const tab = btn.dataset.tab;
        element.querySelectorAll('[data-tab-content]').forEach(p => p.hidden = true);
        element.querySelector(`#panel-${tab}`)?.hidden = false;
      });
    });
    element.querySelector('[data-filter-status]')?.addEventListener('change', handleFilterChange);
    element.querySelector('[data-filter-start]')?.addEventListener('change', handleFilterChange);
    element.querySelector('[data-filter-end]')?.addEventListener('change', handleFilterChange);
    element.querySelector('[data-action="refresh"]')?.addEventListener('click', loadPreview);
    element.querySelector('[data-action="validate"]')?.addEventListener('click', handleValidate);
    element.querySelector('[data-rows]')?.addEventListener('click', handleRowAction);

    return element;
  }

  return { render };
}