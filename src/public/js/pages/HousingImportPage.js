import {
  analyzeImport,
  validateImport,
} from '../services/housingApi.js';

const STATUS_LABELS = {
  ready: 'Prêt',
  duplicate: 'Doublon',
  ambiguous: 'Ambigu',
};

const STATUS_COLORS = {
  ready: 'badge--success',
  duplicate: 'badge--info',
  ambiguous: 'badge--warning',
};

export function createHousingImportPage(router) {
  let element = null;
  let currentBatch = null;
  let stays = [];
  let loading = false;

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

  async function handleFileSelect(e) {
    const file = e.target.files[0];
    if (!file) return;
    const input = e.target;
    input.value = '';

    renderProgress('uploading', 'Téléversement du fichier...');
    try {
      renderProgress('analyzing', 'Analyse du classeur et détection des séjours...');
      const batch = await analyzeImport(file);
      currentBatch = batch;
      renderProgress('preview', 'Analyse terminée', `${batch.stats.total_stays} séjours, ${batch.stats.ready} prêts, ${batch.stats.duplicate} doublons, ${batch.stats.ambiguous} ambigus`);
      renderPreviewUI();
    } catch (error) {
      renderProgress('error', error.message || 'Échec de l\'analyse');
      setTimeout(() => renderProgress(null), 5000);
    }
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
    tbody.innerHTML = stays.map(s => {
      const statusBadge = '<span class="badge ' + (STATUS_COLORS[s.status] || '') + '">' + (STATUS_LABELS[s.status] || s.status) + '</span>';
      const occupantsHtml = s.occupants.map(o => o.last_name + ' ' + o.first_name).join(', ');
      const housing = currentBatch?.stays?.find(x => x.housing_id === s.housing_id);
      const housingName = housing ? housing.housing_name : 'Logement ' + s.housing_id;
      const roomName = s.room_index === 0 ? 'Chambre 1' : s.room_index === 1 ? 'Chambre 2' : 'Chambre ' + (s.room_index + 1);
      const actions = s.status === 'ready' ? '' : `
        <button class="btn btn-sm btn-secondary" data-action="exclude" data-id="${s.occupant_id}-${s.housing_id}-${s.room_index}-${s.arrival_date}" ${loading ? 'disabled' : ''}>Exclure</button>
      `;
      return `
        <tr data-id="${s.occupant_id}-${s.housing_id}-${s.room_index}-${s.arrival_date}">
          <td>${s.arrival_date}</td>
          <td>${s.departure_date}</td>
          <td>${s.nb_nights}</td>
          <td>${occupantsHtml}</td>
          <td>${housingName}</td>
          <td>${roomName}</td>
          <td>${statusBadge}</td>
          <td>${actions}</td>
        </tr>
      `;
    }).join('');
  }

  async function handleRowAction(e) {
    const btn = e.target.closest('button[data-action]');
    if (!btn) return;
    const stayId = btn.dataset.id;
    const stay = stays.find(s => `${s.occupant_id}-${s.housing_id}-${s.room_index}-${s.arrival_date}` === stayId);
    if (!stay) return;

    if (btn.dataset.action === 'exclude') {
      stay.status = 'duplicate';
      renderTable();
    }
  }

  async function handleValidate() {
    if (!currentBatch) return;
    const readyStays = stays.filter(s => s.status === 'ready');
    if (readyStays.length === 0) {
      alert('Aucun séjour prêt à importer');
      return;
    }
    if (!confirm('Valider l\'import ? ' + readyStays.length + ' séjours seront créés en base.')) return;

    const validateBtn = element.querySelector('[data-action="validate"]');
    if (validateBtn) validateBtn.disabled = true;
    renderProgress('validating', 'Validation et enregistrement en base...');
    try {
      const result = await validateImport(readyStays);
      renderProgress('done', 'Import terminé: ' + result.created + ' créés, ' + result.skipped + ' ignorés');
      if (validateBtn) {
        validateBtn.disabled = true;
        validateBtn.textContent = 'Import validé';
      }
      setTimeout(() => {
        renderProgress(null);
        if (router && typeof router.navigate === 'function') {
          router.navigate('/housing');
        } else {
          window.location.href = '/housing';
        }
      }, 2000);
    } catch (error) {
      console.error('Erreur validation:', error);
      renderProgress('error', 'Échec validation: ' + (error.message || 'Erreur inconnue'));
      if (validateBtn) validateBtn.disabled = false;
    }
  }

  async function render() {
    element = document.createElement('div');
    element.className = 'page';
    element.innerHTML = `
      <div class="page-header">
        <h1>Import Occupation Logements</h1>
        <div class="import-progress" data-progress hidden></div>
      </div>

      <!-- Étape 1 : Upload -->
      <div id="upload-card" class="card">
        <h2>Nouvel import</h2>
        <p>Sélectionnez le fichier <strong>Occupation_Logements_2026_corrige.xlsx</strong> (format : Date en col A, chambres en colonnes B-I).</p>
        <label class="btn btn-primary">
          <input type="file" accept=".xlsx" hidden data-file-input>
          Choisir un fichier
        </label>
        <span class="file-name" data-file-name></span>
      </div>

      <!-- Étape 2 : Prévisualisation + Validation (cachée au début) -->
      <div id="preview-container" class="card" hidden>
        ${currentBatch ? `
        <div class="card" style="margin-bottom:1rem; background: var(--color-bg-secondary); padding: 1rem;">
          <h3 style="margin:0 0 0.5rem 0; font-size: var(--font-size-md);">Bilan de l'import</h3>
          <div style="display:flex; gap:1.5rem; flex-wrap:wrap; font-size: var(--font-size-sm);">
            <span><strong>Total séjours:</strong> ${currentBatch.stats.total_stays}</span>
            <span><strong>Prêts:</strong> ${currentBatch.stats.ready}</span>
            <span><strong>Doublons:</strong> ${currentBatch.stats.duplicate}</span>
            <span><strong>Ambigus:</strong> ${currentBatch.stats.ambiguous}</span>
            ${currentBatch.period_start ? '<span><strong>Période:</strong> ' + currentBatch.period_start.split('T')[0] + ' - ' + currentBatch.period_end.split('T')[0] + '</span>' : ''}
          </div>
        </div>
        ` : ''}
        <div class="card" style="margin-bottom:1rem">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem; padding: 1rem; border-bottom: 1px solid var(--color-border-light);">
            <h2 style="margin:0">Séjours détectés</h2>
            <div style="display:flex; gap:0.5rem">
              <button class="btn btn-primary" data-action="validate" ${currentBatch?.stats?.ready === 0 ? 'disabled' : ''}>Valider l'import</button>
            </div>
          </div>
          <div class="table-responsive" style="max-height: calc(100vh - 300px); overflow-y: auto;">
            <table class="table">
              <thead>
                <tr>
                  <th>Arrivée</th>
                  <th>Départ</th>
                  <th>Nuits</th>
                  <th>Occupants</th>
                  <th>Logement</th>
                  <th>Chambre</th>
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
    element.querySelector('[data-action="validate"]')?.addEventListener('click', handleValidate);
    element.querySelector('[data-rows]')?.addEventListener('click', handleRowAction);

    return element;
  }

  return { render, initialize: async () => {} };
}