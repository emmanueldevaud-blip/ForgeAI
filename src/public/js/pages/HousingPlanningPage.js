import { authStore } from '../stores/auth.js';
import {
  getPlanning,
  listHousings,
  createOccupancy,
  updateOccupancy,
  changeOccupancyStatus,
  listOccupants,
  quickCreateOccupant,
  createCleaning,
  updateCleaning,
  listCleanings,
  listEmailTemplates,
  sendConfirmationEmail,
  sendCustomMessage,
  listEmailLogs,
} from '../services/housingApi.js';

const DAY_NAMES_SHORT = ['Dim', 'Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam'];
const DAY_NAMES_LONG = ['Dimanche', 'Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi'];
const MONTH_NAMES = [
  'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
  'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'
];

const STATUS_LABELS = {
  pre_reserved: 'Pré-réservé',
  confirmed: 'Confirmé',
  in_progress: 'En cours',
  completed: 'Terminé',
  cancelled: 'Annulé',
};

const STATUS_COLORS = {
  pre_reserved: { bg: '#f3f4f6', border: '#9ca3af', text: '#374151' },
  confirmed: { bg: '#fef3c7', border: '#f59e0b', text: '#92400e' },
  in_progress: { bg: '#dbeafe', border: '#3b82f6', text: '#1e40af' },
  completed: { bg: '#d1fae5', border: '#10b981', text: '#065f46' },
  cancelled: { bg: '#fee2e2', border: '#ef4444', text: '#991b1b' },
};

const CLEANING_STATUS_LABELS = {
  planned: 'Planifié',
  in_progress: 'En cours',
  completed: 'Terminé',
  verified: 'Vérifié',
};

const CLEANING_STATUS_COLORS = {
  planned: '#f59e0b',
  in_progress: '#3b82f6',
  completed: '#10b981',
  verified: '#6b7280',
};

function formatDateISO(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function formatDateShort(d) {
  return d.toLocaleDateString('fr-FR', { day: 'numeric' });
}

function formatDateFull(d) {
  return d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' });
}

function getOccupantDisplayName(occ) {
  if (!occ) return '';
  return `${occ.last_name || ''} ${occ.first_name || ''}`.trim();
}

export class HousingPlanningPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.currentDate = new Date();
    this.viewMode = 'month';
    this.housings = [];
    this.entries = [];
    this.housingFilter = [];
    this.statusFilter = null;
    this.selectedEntry = null;
    this.dragState = null;
    this.modalState = null;
    this._cleanup = [];
  }

  async initialize() {}

  async loadData() {
    const { startDate, endDate } = this._getDateRange();

    try {
      const resp = await listHousings({ page_size: 1000, is_active: true });
      this.housings = resp.items || [];
    } catch (e) {
      console.error('Erreur chargement logements:', e);
      this.housings = [];
    }

    try {
      const params = {};
      if (this.housingFilter.length > 0) params.housing_ids = JSON.stringify(this.housingFilter);
      if (this.statusFilter) params.status_filter = this.statusFilter;
      const resp = await getPlanning(
        formatDateISO(startDate),
        formatDateISO(endDate),
        this.viewMode,
        this.housingFilter.length > 0 ? JSON.stringify(this.housingFilter) : null,
        this.statusFilter
      );
      this.entries = resp.entries || [];
    } catch (e) {
      console.error('Erreur chargement planning:', e);
      this.entries = [];
    }

    this._renderGrid();
  }

  _getDateRange() {
    const d = this.currentDate;
    const year = d.getFullYear();
    const month = d.getMonth();

    if (this.viewMode === 'day') {
      return { startDate: new Date(d), endDate: new Date(d) };
    }

    if (this.viewMode === 'week') {
      const start = new Date(d);
      start.setDate(d.getDate() - d.getDay());
      const end = new Date(start);
      end.setDate(start.getDate() + 6);
      return { startDate: start, endDate: end };
    }

    const startDate = new Date(year, month, 1);
    const endDate = new Date(year, month + 1, 0);
    return { startDate, endDate };
  }

  _getDays() {
    const { startDate, endDate } = this._getDateRange();
    const days = [];
    const current = new Date(startDate);
    while (current <= endDate) {
      days.push(new Date(current));
      current.setDate(current.getDate() + 1);
    }
    return days;
  }

  _getEntriesForDate(housingId, dateStr) {
    return this.entries.filter(e => {
      if (e.housing_id !== housingId) return false;
      const arrival = (e.arrival_date || '').slice(0, 10);
      const departure = (e.departure_date || '').slice(0, 10);
      return dateStr >= arrival && dateStr <= departure;
    });
  }

  _renderGrid() {
    if (!this.element) return;
    const container = this.element.querySelector('[data-planning]');
    if (!container) return;

    const days = this._getDays();
    const { startDate } = this._getDateRange();
    const year = this.currentDate.getFullYear();
    const month = this.currentDate.getMonth();

    const monthLabel = this.element.querySelector('[data-month-label]');
    if (monthLabel) {
      if (this.viewMode === 'day') {
        monthLabel.textContent = formatDateFull(this.currentDate);
      } else if (this.viewMode === 'week') {
        const { endDate } = this._getDateRange();
        monthLabel.textContent = `${formatDateShort(startDate)} — ${formatDateShort(endDate)} ${MONTH_NAMES[endDate.getMonth()]} ${endDate.getFullYear()}`;
      } else {
        monthLabel.textContent = `${MONTH_NAMES[month]} ${year}`;
      }
    }

    let html = '<div class="planning-wrapper"><table class="planning-table"><thead><tr>';
    html += '<th class="planning-housing-col">Logement</th>';
    days.forEach(day => {
      const dayOfWeek = day.getDay();
      const isWeekend = dayOfWeek === 0 || dayOfWeek === 6;
      const isToday = formatDateISO(day) === formatDateISO(new Date());
      const cls = ['planning-day-col'];
      if (isWeekend) cls.push('planning-weekend');
      if (isToday) cls.push('planning-today');
      const label = this.viewMode === 'day'
        ? `${DAY_NAMES_LONG[dayOfWeek]} ${formatDateShort(day)}`
        : `${DAY_NAMES_SHORT[dayOfWeek]}<br>${formatDateShort(day)}`;
      html += `<th class="${cls.join(' ')}"><div>${label}</div></th>`;
    });
    html += '</tr></thead><tbody>';

    const filteredHousings = this.housingFilter.length > 0
      ? this.housings.filter(h => this.housingFilter.includes(h.id))
      : this.housings;

    if (filteredHousings.length === 0) {
      html += `<tr><td colspan="${days.length + 1}" style="text-align:center;padding:2rem;color:var(--text-secondary);">Aucun logement trouvé</td></tr>`;
    }

    filteredHousings.forEach(housing => {
      html += '<tr>';
      html += `<td class="planning-housing-cell" title="${housing.name || ''}">${housing.name || '-'}</td>`;

      days.forEach(day => {
        const dateStr = formatDateISO(day);
        const entries = this._getEntriesForDate(housing.id, dateStr);
        html += `<td class="planning-cell" data-housing-id="${housing.id}" data-date="${dateStr}">`;
        entries.forEach(entry => {
          const sc = STATUS_COLORS[entry.status] || STATUS_COLORS.pre_reserved;
          const isArrival = dateStr === (entry.arrival_date || '').slice(0, 10);
          const isDeparture = dateStr === (entry.departure_date || '').slice(0, 10);
          const primaryOccupant = (entry.occupants && entry.occupants[0]) || null;
          const name = getOccupantDisplayName(primaryOccupant);
          const extraCount = (entry.occupants || []).length - 1;
          const extraLabel = extraCount > 0 ? ` +${extraCount}` : '';
          const cleaningDot = entry.has_cleaning_planned
            ? `<span class="planning-cleaning-dot" style="background:${CLEANING_STATUS_COLORS[entry.cleaning_status] || '#9ca3af'}" title="Nettoyage: ${CLEANING_STATUS_LABELS[entry.cleaning_status] || 'Planifié'}"></span>`
            : '';
          html += `<span class="planning-occupancy" data-entry-id="${entry.occupancy_id}" style="background:${sc.bg};border-left:3px solid ${sc.border};color:${sc.text}" title="${name}${extraLabel} (${STATUS_LABELS[entry.status] || entry.status})">`;
          if (isArrival) html += '<span class="planning-marker planning-arrival">&#9654;</span>';
          if (isDeparture) html += '<span class="planning-marker planning-departure">&#9664;</span>';
          html += `<span class="planning-entry-text">${name}${extraLabel}</span>`;
          html += cleaningDot;
          html += '</span>';
        });
        html += '</td>';
      });

      html += '</tr>';
    });

    html += '</tbody></table></div>';
    container.innerHTML = html;

    this._bindGridEvents();
  }

  _bindGridEvents() {
    if (!this.element) return;

    this.element.querySelectorAll('.planning-cell').forEach(cell => {
      cell.addEventListener('mousedown', (e) => {
        if (e.target.closest('.planning-occupancy')) return;
        const housingId = parseInt(cell.dataset.housingId);
        const date = cell.dataset.date;
        this.dragState = { housingId, startDate: date, endDate: date };
        cell.classList.add('planning-cell--selected');
      });

      cell.addEventListener('mouseenter', (e) => {
        if (!this.dragState) return;
        const housingId = parseInt(cell.dataset.housingId);
        if (housingId !== this.dragState.housingId) return;
        const date = cell.dataset.date;
        this.dragState.endDate = date;
        this._highlightDragRange();
      });
    });

    document.addEventListener('mouseup', () => {
      if (this.dragState) {
        this._onDragEnd();
        this.dragState = null;
        this.element.querySelectorAll('.planning-cell--selected').forEach(c => c.classList.remove('planning-cell--selected'));
      }
    });

    this.element.querySelectorAll('.planning-occupancy').forEach(el => {
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        const entryId = parseInt(el.dataset.entryId);
        const entry = this.entries.find(en => en.occupancy_id === entryId);
        if (entry) this._showEntryDetailModal(entry);
      });
    });
  }

  _highlightDragRange() {
    if (!this.dragState || !this.element) return;
    this.element.querySelectorAll('.planning-cell--drag').forEach(c => c.classList.remove('planning-cell--drag'));
    const { housingId, startDate, endDate } = this.dragState;
    const [start, end] = startDate <= endDate ? [startDate, endDate] : [endDate, startDate];
    this.element.querySelectorAll(`.planning-cell[data-housing-id="${housingId}"]`).forEach(cell => {
      const d = cell.dataset.date;
      if (d >= start && d <= end) {
        cell.classList.add('planning-cell--drag');
      }
    });
  }

  _onDragEnd() {
    if (!this.dragState) return;
    let { startDate, endDate, housingId } = this.dragState;
    if (startDate > endDate) [startDate, endDate] = [endDate, startDate];
    this._showNewOccupancyModal(housingId, startDate, endDate);
  }

  _showNewOccupancyModal(housingId, startDate, endDate) {
    const housing = this.housings.find(h => h.id === housingId);
    if (!housing) return;
    this._openModal(this._buildOccupancyFormModal(housing, startDate, endDate));
  }

  _showEntryDetailModal(entry) {
    this.selectedEntry = entry;
    this._openModal(this._buildEntryDetailModal(entry));
  }

  _openModal(html) {
    this._closeModal();
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay open';
    overlay.style.cssText = 'position:fixed;inset:0;z-index:1000;display:flex;align-items:center;justify-content:center;';
    overlay.innerHTML = `<div class="modal-content" style="max-width:640px;width:95%;max-height:90vh;overflow-y:auto;">${html}</div>`;
    document.body.appendChild(overlay);
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) this._closeModal();
    });
    this._currentModal = overlay;
    this._bindModalEvents(overlay);
  }

  _closeModal() {
    if (this._currentModal) {
      this._currentModal.remove();
      this._currentModal = null;
    }
  }

  _bindModalEvents(overlay) {
    overlay.querySelectorAll('[data-dismiss]').forEach(btn => {
      btn.addEventListener('click', () => this._closeModal());
    });
  }

  _buildOccupancyFormModal(housing, startDate, endDate) {
    return `
      <div class="modal-header">
        <h2>Nouvelle réservation</h2>
        <button class="modal-close" data-dismiss>&times;</button>
      </div>
      <div class="modal-body">
        <div class="modal-form">
          <div class="form-group">
            <label>Logement</label>
            <input type="text" value="${housing.name || ''}" disabled class="form-control">
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>Arrivée</label>
              <input type="date" id="occ-arrival" value="${startDate}" class="form-control">
            </div>
            <div class="form-group">
              <label>Départ</label>
              <input type="date" id="occ-departure" value="${endDate}" class="form-control">
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>Statut</label>
              <select id="occ-status" class="form-control">
                <option value="pre_reserved">Pré-réservé</option>
                <option value="confirmed">Confirmé</option>
              </select>
            </div>
            <div class="form-group">
              <label>Nombre de personnes</label>
              <input type="number" id="occ-nb-persons" value="1" min="1" class="form-control">
            </div>
          </div>
          <div class="form-group">
            <label>Occupants principaux</label>
            <div id="occ-occupant-list" class="occupant-list-container">
              <div class="occupant-entry" data-index="0">
                <select class="form-control occ-occupant-select" data-index="0">
                  <option value="">— Choisir ou créer —</option>
                </select>
                <button class="btn btn-sm btn-secondary occ-quick-create" data-index="0" title="Créer rapidement">+</button>
              </div>
            </div>
            <button class="btn btn-sm btn-secondary" id="occ-add-occupant" style="margin-top:4px;">+ Ajouter un occupant</button>
          </div>
          <div class="form-group">
            <label>Notes</label>
            <textarea id="occ-notes" class="form-control" rows="2" placeholder="Notes internes..."></textarea>
          </div>
          <div class="modal-footer" style="margin-top:1rem;display:flex;gap:8px;justify-content:flex-end;">
            <button class="btn btn-secondary" data-dismiss>Annuler</button>
            <button class="btn btn-primary" id="occ-save">Enregistrer</button>
          </div>
        </div>
      </div>
    `;
  }

  _buildEntryDetailModal(entry) {
    const sc = STATUS_COLORS[entry.status] || STATUS_COLORS.pre_reserved;
    const primaryOccupant = (entry.occupants && entry.occupants[0]) || null;
    const housing = this.housings.find(h => h.id === entry.housing_id);

    let occupantsHtml = '';
    (entry.occupants || []).forEach((occ, i) => {
      occupantsHtml += `
        <div class="detail-occupant-row" style="display:flex;gap:8px;align-items:center;padding:4px 0;">
          <span style="flex:1;">${getOccupantDisplayName(occ)}</span>
          ${i === 0 ? '<span class="badge badge-sm">Principal</span>' : ''}
          <span style="color:var(--text-secondary);font-size:12px;">${occ.email || ''}</span>
        </div>`;
    });

    return `
      <div class="modal-header">
        <h2>${getOccupantDisplayName(primaryOccupant) || 'Réservation'}</h2>
        <button class="modal-close" data-dismiss>&times;</button>
      </div>
      <div class="modal-body">
        <div style="display:flex;gap:12px;margin-bottom:12px;">
          <div style="flex:1;">
            <label style="font-weight:600;font-size:12px;color:var(--text-secondary);">Statut</label>
            <div>
              <span class="badge" style="background:${sc.bg};color:${sc.text};border:1px solid ${sc.border};">${STATUS_LABELS[entry.status] || entry.status}</span>
            </div>
          </div>
          <div style="flex:1;">
            <label style="font-weight:600;font-size:12px;color:var(--text-secondary);">Logement</label>
            <div>${housing ? housing.name : entry.housing_name || '-'}</div>
          </div>
        </div>
        <div style="display:flex;gap:12px;margin-bottom:12px;">
          <div style="flex:1;">
            <label style="font-weight:600;font-size:12px;color:var(--text-secondary);">Arrivée</label>
            <div>${formatDateShort(new Date(entry.arrival_date))}</div>
          </div>
          <div style="flex:1;">
            <label style="font-weight:600;font-size:12px;color:var(--text-secondary);">Départ</label>
            <div>${formatDateShort(new Date(entry.departure_date))}</div>
          </div>
          <div style="flex:1;">
            <label style="font-weight:600;font-size:12px;color:var(--text-secondary);">Personnes</label>
            <div>${entry.nb_persons || 1}</div>
          </div>
        </div>
        ${entry.has_cleaning_planned ? `
        <div style="margin-bottom:12px;">
          <label style="font-weight:600;font-size:12px;color:var(--text-secondary);">Nettoyage</label>
          <div>
            <span class="badge" style="background:${CLEANING_STATUS_COLORS[entry.cleaning_status] || '#9ca3af'};color:white;">${CLEANING_STATUS_LABELS[entry.cleaning_status] || 'Planifié'}</span>
          </div>
        </div>` : ''}
        <div style="margin-bottom:12px;">
          <label style="font-weight:600;font-size:12px;color:var(--text-secondary);">Occupants</label>
          ${occupantsHtml || '<div style="color:var(--text-secondary);">Aucun occupant</div>'}
        </div>
        <div class="modal-footer" style="margin-top:1rem;display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap;">
          <button class="btn btn-secondary" data-dismiss>Fermer</button>
          ${entry.status !== 'confirmed' ? `<button class="btn btn-primary" data-action="confirm">Confirmer</button>` : ''}
          ${entry.status !== 'in_progress' && entry.status !== 'completed' ? `<button class="btn btn-warning" data-action="checkin">Check-in</button>` : ''}
          ${entry.status === 'in_progress' ? `<button class="btn btn-success" data-action="checkout">Check-out</button>` : ''}
          ${!entry.has_cleaning_planned ? `<button class="btn btn-secondary" data-action="schedule-cleaning">Planifier nettoyage</button>` : ''}
          <button class="btn btn-secondary" data-action="send-email">Envoyer e-mail</button>
        </div>
      </div>
    `;
  }

  _buildEmailComposerModal(entry) {
    const primaryOccupant = (entry.occupants && entry.occupants[0]) || null;
    return `
      <div class="modal-header">
        <h2>Envoyer un e-mail</h2>
        <button class="modal-close" data-dismiss>&times;</button>
      </div>
      <div class="modal-body">
        <div class="modal-form">
          <div class="form-group">
            <label>Destinataires</label>
            <div id="email-recipients" style="display:flex;flex-wrap:wrap;gap:4px;">
              ${(entry.occupants || []).map((occ, i) => `
                <label class="checkbox-label" style="display:flex;align-items:center;gap:4px;padding:2px 8px;border:1px solid var(--border-color);border-radius:4px;">
                  <input type="checkbox" class="email-recipient" value="${occ.id}" ${i === 0 ? 'checked' : ''}>
                  <span>${getOccupantDisplayName(occ)}</span>
                </label>`).join('')}
            </div>
          </div>
          <div class="form-group">
            <label>Modèle (optionnel)</label>
            <select id="email-template" class="form-control">
              <option value="">— Sans modèle —</option>
            </select>
          </div>
          <div class="form-group">
            <label>Sujet</label>
            <input type="text" id="email-subject" class="form-control" placeholder="Objet de l'e-mail">
          </div>
          <div class="form-group">
            <label>Message</label>
            <textarea id="email-body" class="form-control" rows="6" placeholder="Contenu du message..."></textarea>
          </div>
          <div class="modal-footer" style="margin-top:1rem;display:flex;gap:8px;justify-content:flex-end;">
            <button class="btn btn-secondary" data-dismiss>Annuler</button>
            <button class="btn btn-primary" id="email-send">Envoyer</button>
          </div>
        </div>
      </div>
    `;
  }

  _buildCleaningModal(entry) {
    return `
      <div class="modal-header">
        <h2>Planifier un nettoyage</h2>
        <button class="modal-close" data-dismiss>&times;</button>
      </div>
      <div class="modal-body">
        <div class="modal-form">
          <div class="form-group">
            <label>Date prévue</label>
            <input type="date" id="cleaning-date" class="form-control" value="${(entry.departure_date || '').slice(0, 10)}">
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>Type</label>
              <select id="cleaning-type" class="form-control">
                <option value="departure">Départ</option>
                <option value="arrival">Arrivée</option>
                <option value="intermediate">Intermédiaire</option>
                <option value="deep">Complète</option>
              </select>
            </div>
            <div class="form-group">
              <label>Statut</label>
              <select id="cleaning-status" class="form-control">
                <option value="planned">Planifié</option>
                <option value="in_progress">En cours</option>
              </select>
            </div>
          </div>
          <div class="form-group">
            <label>Notes</label>
            <textarea id="cleaning-notes" class="form-control" rows="2" placeholder="Instructions de nettoyage..."></textarea>
          </div>
          <div class="modal-footer" style="margin-top:1rem;display:flex;gap:8px;justify-content:flex-end;">
            <button class="btn btn-secondary" data-dismiss>Annuler</button>
            <button class="btn btn-primary" id="cleaning-save">Enregistrer</button>
          </div>
        </div>
      </div>
    `;
  }

  async _bindModalEvents(overlay) {
    overlay.querySelectorAll('[data-dismiss]').forEach(btn => {
      btn.addEventListener('click', () => this._closeModal());
    });

    const occSelects = overlay.querySelectorAll('.occ-occupant-select');
    const quickBtns = overlay.querySelectorAll('.occ-quick-create');
    const addBtn = overlay.querySelector('#occ-add-occupant');
    const saveBtn = overlay.querySelector('#occ-save');

    if (occSelects.length > 0) {
      try {
        const resp = await listOccupants({ page_size: 500, is_active: true });
        const occupantList = resp.items || [];
        occSelects.forEach(sel => {
          occupantList.forEach(o => {
            const opt = document.createElement('option');
            opt.value = o.id;
            opt.textContent = `${o.last_name || ''} ${o.first_name || ''}`.trim();
            sel.appendChild(opt);
          });
        });
      } catch (e) {
        console.error('Erreur chargement occupants:', e);
      }
    }

    quickBtns.forEach(btn => {
      btn.addEventListener('click', async () => {
        const index = parseInt(btn.dataset.index);
        const name = prompt('Nom et prénom de l\'occupant (ex: Dupont Jean):');
        if (!name) return;
        const parts = name.trim().split(' ');
        const lastName = parts[0] || '';
        const firstName = parts.slice(1).join(' ') || '';
        const email = prompt('Email (optionnel):') || '';
        try {
          const newOcc = await quickCreateOccupant({ last_name: lastName, first_name: firstName, email });
          const sel = overlay.querySelector(`.occ-occupant-select[data-index="${index}"]`);
          if (sel) {
            const opt = document.createElement('option');
            opt.value = newOcc.id;
            opt.textContent = `${newOcc.last_name || ''} ${newOcc.first_name || ''}`.trim();
            sel.appendChild(opt);
            sel.value = newOcc.id;
          }
        } catch (e) {
          console.error('Erreur création occupant:', e);
          alert('Erreur lors de la création de l\'occupant');
        }
      });
    });

    if (addBtn) {
      addBtn.addEventListener('click', () => {
        const container = overlay.querySelector('#occ-occupant-list');
        const entries = container.querySelectorAll('.occupant-entry');
        const nextIndex = entries.length;
        const row = document.createElement('div');
        row.className = 'occupant-entry';
        row.dataset.index = nextIndex;
        row.innerHTML = `
          <select class="form-control occ-occupant-select" data-index="${nextIndex}">
            <option value="">— Choisir —</option>
          </select>
          <button class="btn btn-sm btn-secondary occ-quick-create" data-index="${nextIndex}" title="Créer rapidement">+</button>
        `;
        container.appendChild(row);
        const sel = row.querySelector('.occ-occupant-select');
        const existingOpts = overlay.querySelector('.occ-occupant-select')?.options;
        if (existingOpts) {
          Array.from(existingOpts).forEach(opt => {
            if (opt.value) {
              const newOpt = opt.cloneNode(true);
              sel.appendChild(newOpt);
            }
          });
        }
        row.querySelector('.occ-quick-create').addEventListener('click', async () => {
          const name = prompt('Nom et prénom de l\'occupant:');
          if (!name) return;
          const parts = name.trim().split(' ');
          const lastName = parts[0] || '';
          const firstName = parts.slice(1).join(' ') || '';
          const email = prompt('Email (optionnel):') || '';
          try {
            const newOcc = await quickCreateOccupant({ last_name: lastName, first_name: firstName, email });
            const opt = document.createElement('option');
            opt.value = newOcc.id;
            opt.textContent = `${newOcc.last_name || ''} ${newOcc.first_name || ''}`.trim();
            sel.appendChild(opt);
            sel.value = newOcc.id;
          } catch (e) {
            alert('Erreur lors de la création');
          }
        });
      });
    }

    if (saveBtn) {
      saveBtn.addEventListener('click', async () => {
        const arrival = overlay.querySelector('#occ-arrival')?.value;
        const departure = overlay.querySelector('#occ-departure')?.value;
        const status = overlay.querySelector('#occ-status')?.value;
        const nbPersons = parseInt(overlay.querySelector('#occ-nb-persons')?.value) || 1;
        const notes = overlay.querySelector('#occ-notes')?.value || '';
        const occupantSelects = overlay.querySelectorAll('.occ-occupant-select');
        const occupantIds = [];
        occupantSelects.forEach(sel => {
          if (sel.value) occupantIds.push(parseInt(sel.value));
        });

        if (!arrival || !departure) {
          alert('Veuillez remplir les dates d\'arrivée et de départ');
          return;
        }

        const housingId = parseInt(overlay.querySelector('[data-housing-id]')?.dataset?.housingId)
          || this._modalHousingId;

        try {
          await createOccupancy({
            housing_id: housingId,
            arrival_date: arrival,
            departure_date: departure,
            status,
            nb_persons: nbPersons,
            occupant_ids: occupantIds,
            notes,
          });
          this._closeModal();
          await this.loadData();
        } catch (e) {
          console.error('Erreur création réservation:', e);
          alert('Erreur lors de la création de la réservation');
        }
      });
    }

    const emailSendBtn = overlay.querySelector('#email-send');
    if (emailSendBtn) {
      try {
        const tplResp = await listEmailTemplates({ page_size: 100, is_active: true });
        const tplSel = overlay.querySelector('#email-template');
        (tplResp.items || []).forEach(t => {
          const opt = document.createElement('option');
          opt.value = t.id;
          opt.textContent = t.name;
          tplSel.appendChild(opt);
        });
      } catch (e) { /* ignore */ }

      emailSendBtn.addEventListener('click', async () => {
        const subject = overlay.querySelector('#email-subject')?.value;
        const body = overlay.querySelector('#email-body')?.value;
        const recipientCheckboxes = overlay.querySelectorAll('.email-recipient:checked');
        const recipientIds = Array.from(recipientCheckboxes).map(cb => parseInt(cb.value));
        const templateId = overlay.querySelector('#email-template')?.value || null;

        if (!subject || !body) {
          alert('Veuillez remplir le sujet et le message');
          return;
        }
        if (recipientIds.length === 0) {
          alert('Veuillez sélectionner au moins un destinataire');
          return;
        }

        try {
          await sendCustomMessage(
            this.selectedEntry?.occupancy_id,
            subject,
            body,
            recipientIds,
            templateId ? parseInt(templateId) : null
          );
          alert('E-mail envoyé avec succès');
          this._closeModal();
        } catch (e) {
          console.error('Erreur envoi e-mail:', e);
          alert('Erreur lors de l\'envoi');
        }
      });
    }

    const confirmBtn = overlay.querySelector('[data-action="confirm"]');
    if (confirmBtn) {
      confirmBtn.addEventListener('click', async () => {
        try {
          await changeOccupancyStatus(this.selectedEntry.occupancy_id, 'confirmed');
          this._closeModal();
          await this.loadData();
        } catch (e) {
          alert('Erreur lors de la confirmation');
        }
      });
    }

    const checkinBtn = overlay.querySelector('[data-action="checkin"]');
    if (checkinBtn) {
      checkinBtn.addEventListener('click', async () => {
        try {
          await changeOccupancyStatus(this.selectedEntry.occupancy_id, 'in_progress');
          this._closeModal();
          await this.loadData();
        } catch (e) {
          alert('Erreur lors du check-in');
        }
      });
    }

    const checkoutBtn = overlay.querySelector('[data-action="checkout"]');
    if (checkoutBtn) {
      checkoutBtn.addEventListener('click', async () => {
        try {
          await changeOccupancyStatus(this.selectedEntry.occupancy_id, 'completed');
          this._closeModal();
          await this.loadData();
        } catch (e) {
          alert('Erreur lors du check-out');
        }
      });
    }

    const cleaningBtn = overlay.querySelector('[data-action="schedule-cleaning"]');
    if (cleaningBtn) {
      cleaningBtn.addEventListener('click', () => {
        this._closeModal();
        this._openModal(this._buildCleaningModal(this.selectedEntry));
      });
    }

    const sendEmailBtn = overlay.querySelector('[data-action="send-email"]');
    if (sendEmailBtn) {
      sendEmailBtn.addEventListener('click', () => {
        this._closeModal();
        this._openModal(this._buildEmailComposerModal(this.selectedEntry));
      });
    }

    const cleaningSaveBtn = overlay.querySelector('#cleaning-save');
    if (cleaningSaveBtn) {
      cleaningSaveBtn.addEventListener('click', async () => {
        const scheduledDate = overlay.querySelector('#cleaning-date')?.value;
        const type = overlay.querySelector('#cleaning-type')?.value;
        const status = overlay.querySelector('#cleaning-status')?.value;
        const notes = overlay.querySelector('#cleaning-notes')?.value || '';

        if (!scheduledDate) {
          alert('Veuillez sélectionner une date');
          return;
        }

        try {
          await createCleaning({
            housing_id: this.selectedEntry.housing_id,
            occupancy_id: this.selectedEntry.occupancy_id,
            scheduled_date: scheduledDate,
            type,
            status,
            notes,
          });
          this._closeModal();
          await this.loadData();
        } catch (e) {
          console.error('Erreur création nettoyage:', e);
          alert('Erreur lors de la création du nettoyage');
        }
      });
    }
  }

  _updateViewButtons() {
    if (!this.element) return;
    this.element.querySelectorAll('[data-view]').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.view === this.viewMode);
    });
  }

  render() {
    this.element = document.createElement('div');
    this.element.className = 'page-content';
    this.element.innerHTML = `
      <div class="page-header">
        <div class="page-header-left">
          <h1>Planning d'occupation</h1>
          <p class="page-subtitle">Vue calendrier des réservations</p>
        </div>
        <div class="page-header-right" style="display:flex;gap:8px;align-items:center;">
          <div class="btn-group" style="display:flex;border:1px solid var(--border-color);border-radius:var(--radius-md);overflow:hidden;">
            <button class="btn btn-secondary btn-sm" data-view="day" style="border-radius:0;border:none;">Jour</button>
            <button class="btn btn-secondary btn-sm" data-view="week" style="border-radius:0;border:none;">Semaine</button>
            <button class="btn btn-secondary btn-sm active" data-view="month" style="border-radius:0;border:none;">Mois</button>
          </div>
        </div>
      </div>
      <div class="calendar-nav" style="display:flex;align-items:center;gap:12px;margin-bottom:1rem;">
        <button class="btn btn-secondary" data-action="prev">&larr;</button>
        <h2 data-month-label style="margin:0;min-width:200px;text-align:center;"></h2>
        <button class="btn btn-secondary" data-action="next">&rarr;</button>
        <button class="btn btn-secondary" data-action="today">Aujourd'hui</button>
        <div style="margin-left:auto;display:flex;gap:8px;">
          <select class="form-control" id="status-filter" style="width:auto;padding:4px 8px;font-size:13px;">
            <option value="">Tous les statuts</option>
            <option value="pre_reserved">Pré-réservé</option>
            <option value="confirmed">Confirmé</option>
            <option value="in_progress">En cours</option>
            <option value="completed">Terminé</option>
            <option value="cancelled">Annulé</option>
          </select>
        </div>
      </div>
      <div data-planning style="min-height:200px;"></div>
    `;

    this.element.querySelector('[data-action="prev"]')?.addEventListener('click', () => {
      if (this.viewMode === 'day') {
        this.currentDate.setDate(this.currentDate.getDate() - 1);
      } else if (this.viewMode === 'week') {
        this.currentDate.setDate(this.currentDate.getDate() - 7);
      } else {
        this.currentDate.setMonth(this.currentDate.getMonth() - 1);
      }
      this.loadData();
    });

    this.element.querySelector('[data-action="next"]')?.addEventListener('click', () => {
      if (this.viewMode === 'day') {
        this.currentDate.setDate(this.currentDate.getDate() + 1);
      } else if (this.viewMode === 'week') {
        this.currentDate.setDate(this.currentDate.getDate() + 7);
      } else {
        this.currentDate.setMonth(this.currentDate.getMonth() + 1);
      }
      this.loadData();
    });

    this.element.querySelector('[data-action="today"]')?.addEventListener('click', () => {
      this.currentDate = new Date();
      this.loadData();
    });

    this.element.querySelectorAll('[data-view]').forEach(btn => {
      btn.addEventListener('click', () => {
        this.viewMode = btn.dataset.view;
        this._updateViewButtons();
        this.loadData();
      });
    });

    this.element.querySelector('#status-filter')?.addEventListener('change', (e) => {
      this.statusFilter = e.target.value || null;
      this.loadData();
    });

    this._updateViewButtons();
    this.loadData();

    return this.element;
  }

  destroy() {
    this._cleanup.forEach(fn => fn());
    this._cleanup = [];
    this._closeModal();
    if (this.element) this.element.remove();
    this.element = null;
  }
}

export function createHousingPlanningPage(router) {
  return new HousingPlanningPage(router);
}
