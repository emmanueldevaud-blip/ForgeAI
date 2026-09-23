import { authStore } from '../stores/auth.js';
import {
  getPlanning,
  listHousings,
  createOccupancy,
  deleteOccupancy,
  changeOccupancyStatus,
  listOccupants,
  createOccupant,
  createCleaning,
  updateCleaning,
  deleteCleaning,
  cancelCleaning,
  listCleanings,
  getCleaningInvitationDetails,
  listVolunteers,
  sendCleaningVolunteerRequest,
  confirmCleaningVolunteers,
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
};

const STATUS_COLORS = {
  pre_reserved: { bg: '#fef3c7', border: '#f59e0b', text: '#92400e' },
  confirmed: { bg: '#dcfce7', border: '#22c55e', text: '#166534' },
};

const CLEANING_STATUS_LABELS = {
  not_planned: 'Non planifié',
  planned: 'Planifié',
  in_progress: 'Planification en cours',
  completed: 'Terminé',
  verified: 'Vérifié',
};

const CLEANING_STATUS_COLORS = {
  not_planned: '#ef4444',
  planned: '#22c55e',
  in_progress: '#f59e0b',
  completed: '#10b981',
  verified: '#6b7280',
};

function formatDateISO(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function getNextWeekdayAfter(dateValue) {
  const date = new Date(`${dateValue.slice(0, 10)}T00:00:00`);
  date.setDate(date.getDate() + 1);
  while (date.getDay() === 0 || date.getDay() === 6) {
    date.setDate(date.getDate() + 1);
  }
  return formatDateISO(date);
}

function parseRoomNames(str, count) {
  let names = [];
  try { names = JSON.parse(str || '[]'); } catch { names = []; }
  return Array.from({ length: count }, (_, i) => names[i] || `Chambre ${i + 1}`);
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

function escapeHtml(value) {
  const div = document.createElement('div');
  div.textContent = value == null ? '' : String(value);
  return div.innerHTML;
}

function getEmailTemplateContext(entry, occupant) {
  return {
    occupant_first_name: occupant?.first_name || '',
    occupant_last_name: occupant?.last_name || '',
    occupant_email: occupant?.email || '',
    arrival_date: entry.arrival_date ? new Date(entry.arrival_date).toLocaleDateString('fr-FR') : '',
    departure_date: entry.departure_date ? new Date(entry.departure_date).toLocaleDateString('fr-FR') : '',
    housing_name: entry.housing_name || '',
    housing_reference: entry.housing_reference || '',
    building_name: entry.building_name || '',
    site_name: entry.site_name || '',
    room_index: entry.room_index ?? 0,
    nb_persons: entry.nb_persons || 1,
    guest_type: entry.guest_type || '',
    purpose: entry.purpose || '',
    observations: entry.observations || '',
  };
}

function renderEmailTemplate(value, context, html = false) {
  return String(value || '').replace(/{{\s*([a-zA-Z0-9_]+)\s*}}/g, (_, variable) => {
    const replacement = context[variable] ?? '';
    return html ? escapeHtml(replacement) : String(replacement);
  });
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
      console.error('Erreur chargement chambres:', e);
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
      this.entries = (resp.entries || []).filter((entry) => (
        entry.status === 'pre_reserved' || entry.status === 'confirmed'
      ));
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

    const isMobile = window.innerWidth <= 640;
    const startStr = formatDateISO(startDate);

    let html = '<div class="planning-container"><div class="planning-wrapper"><table class="planning-table"><thead><tr>';
    html += '<th class="planning-housing-col"><span class="housing-col-header">Chambre</span></th>';
    
    days.forEach(day => {
      const dayOfWeek = day.getDay();
      const isWeekend = dayOfWeek === 0 || dayOfWeek === 6;
      const isToday = formatDateISO(day) === formatDateISO(new Date());
      const cls = ['planning-day-col'];
      if (isWeekend) cls.push('planning-weekend');
      if (isToday) cls.push('planning-today');
      
      const dayName = isMobile ? DAY_NAMES_SHORT[dayOfWeek].charAt(0) : DAY_NAMES_SHORT[dayOfWeek];
      const label = this.viewMode === 'day'
        ? `${DAY_NAMES_LONG[dayOfWeek]} ${formatDateShort(day)}`
        : `<span class="day-name">${dayName}</span><span class="day-num">${formatDateShort(day)}</span>`;
      html += `<th class="${cls.join(' ')}"><div>${label}</div></th>`;
    });
    html += '</tr></thead><tbody>';

    const filteredHousings = this.housingFilter.length > 0
      ? this.housings.filter(h => this.housingFilter.includes(h.id))
      : this.housings;

    if (filteredHousings.length === 0) {
      html += `<tr><td colspan="${days.length + 1}" style="text-align:center;padding:2rem;color:var(--text-secondary);">Aucune chambre trouvée</td></tr>`;
    }

    const housingOccupancies = this._getOccupanciesByHousing();

    const groupedByBuilding = {};
    filteredHousings.forEach(housing => {
      const buildingName = (housing.building && housing.building.name) || 'Autre';
      if (!groupedByBuilding[buildingName]) groupedByBuilding[buildingName] = [];
      groupedByBuilding[buildingName].push(housing);
    });

    Object.keys(groupedByBuilding).sort().forEach(buildingName => {
      const buildingHousings = groupedByBuilding[buildingName];

      buildingHousings.forEach(housing => {
        let bedConfig = [];
        try { bedConfig = JSON.parse(housing.bed_configuration || '[]'); } catch { bedConfig = []; }
         const nbRooms = housing.nb_rooms || 1;
         const roomNames = parseRoomNames(housing.room_names, nbRooms);
        if (bedConfig.length === 0) bedConfig = Array(nbRooms).fill('simple');

        bedConfig.forEach((bedType, roomIdx) => {
          const localName = housing.room?.name || housing.name || housing.room_name || 'Logement';
           const roomName = roomNames[roomIdx];
          const bedLabel = bedType === 'double' ? 'Lit double' : 'Lit simple';
          const roomLabel = `${localName} — ${roomName} — ${bedLabel}`;

          const occupancies = (housingOccupancies[housing.id] || []).filter(occ => {
            const occRoom = occ.room_index == null ? null : Number(occ.room_index);
            return occRoom == null ? roomIdx === 0 : occRoom === roomIdx;
          });

          const dayOccupancyMap = new Array(days.length).fill(null);

          occupancies.forEach(occ => {
            const occArrival = (occ.arrival_date || '').slice(0, 10);
            const occDeparture = (occ.departure_date || '').slice(0, 10);
            let startDayIdx = -1;
            let endDayIdx = -1;
            days.forEach((day, idx) => {
              const ds = formatDateISO(day);
              if (ds === occArrival && startDayIdx === -1) startDayIdx = idx;
              if (ds === occDeparture) endDayIdx = idx;
            });
            if (startDayIdx === -1) startDayIdx = 0;
            if (endDayIdx === -1) endDayIdx = days.length - 1;

            for (let i = startDayIdx; i <= endDayIdx; i++) {
              dayOccupancyMap[i] = { occ, startDayIdx, endDayIdx, isStart: i === startDayIdx };
            }
          });

          html += '<tr>';
          html += `<td class="planning-housing-cell" title="${roomLabel}"><span class="housing-name">${localName}</span><span class="housing-code">${roomName}</span><span class="housing-beds">${bedLabel}</span></td>`;

          let colIdx = 0;
          while (colIdx < days.length) {
            const day = days[colIdx];
            const dateStr = formatDateISO(day);
            const info = dayOccupancyMap[colIdx];

            if (info && info.isStart) {
              const { occ, startDayIdx, endDayIdx } = info;
              const span = endDayIdx - startDayIdx + 1;
              const statusClass = occ.status || 'pre_reserved';
              const occupants = occ.occupants || [];
              const names = occupants.map(o => getOccupantDisplayName(o)).filter(n => n);
              const displayName = names.length > 0 ? names.join(' / ') : '';
              const extraCount = occupants.length - 1;
              const extraLabel = extraCount > 0 ? ` +${extraCount}` : '';

              let cleaningHtml = '';
              if (occ.has_cleaning_planned) {
                cleaningHtml = `<span class="planning-cleaning-dot" style="background:${CLEANING_STATUS_COLORS[occ.cleaning_status] || '#9ca3af'}" title="Nettoyage: ${CLEANING_STATUS_LABELS[occ.cleaning_status] || 'Planifié'}"></span>`;
              } else if (occ.status === 'completed') {
                cleaningHtml = '<span class="planning-cleaning-warning" title="Nettoyage non planifié">⚠</span>';
              }

              html += `<td class="planning-cell planning-cell--block" colspan="${span}" data-housing-id="${housing.id}" data-room-index="${roomIdx}" data-date="${dateStr}" data-entry-id="${occ.occupancy_id}">`;
              html += `<span class="planning-block planning-block--${statusClass}" title="${displayName}${extraLabel} (${STATUS_LABELS[occ.status] || occ.status})">`;
              html += `<span class="planning-block-inner"><span class="planning-block-name">${displayName}${extraLabel}</span>${cleaningHtml}</span>`;
              html += '</span>';
              html += '</td>';
              colIdx += span;
            } else {
              html += `<td class="planning-cell" data-housing-id="${housing.id}" data-room-index="${roomIdx}" data-date="${dateStr}"></td>`;
              colIdx++;
            }
          }

          html += '</tr>';
        });
      });
    });

    html += '</tbody></table></div></div>';
    container.innerHTML = html;

    this._focusToday(container);
    this._bindGridEvents();
    this._bindTouchEvents();
  }

  _focusToday(container) {
    const today = container.querySelector('.planning-today');
    const wrapper = container.querySelector('.planning-wrapper');
    if (!today || !wrapper) return;
    requestAnimationFrame(() => {
      wrapper.scrollLeft = Math.max(0, today.offsetLeft - (wrapper.clientWidth - today.offsetWidth) / 2);
    });
  }

  _getOccupanciesByHousing() {
    const map = {};
    this.entries.forEach(entry => {
      if (!map[entry.housing_id]) map[entry.housing_id] = [];
      map[entry.housing_id].push(entry);
    });
    return map;
  }

  _getWeekNumber(date) {
    const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
    const dayNum = d.getUTCDay() || 7;
    d.setUTCDate(d.getUTCDate() + 4 - dayNum);
    const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
    return Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
  }

  _bindGridEvents() {
    if (!this.element) return;

    this.element.querySelectorAll('.planning-cell').forEach(cell => {
      cell.addEventListener('mousedown', (e) => {
        if (e.target.closest('.planning-block')) return;
        const housingId = parseInt(cell.dataset.housingId);
        const roomIndex = parseInt(cell.dataset.roomIndex) || 0;
        const date = cell.dataset.date;
        if (date < formatDateISO(new Date())) return;
        this.dragState = { housingId, roomIndex, startDate: date, endDate: date };
        cell.classList.add('planning-cell--selected');
      });

      cell.addEventListener('mouseenter', (e) => {
        if (!this.dragState) return;
        const housingId = parseInt(cell.dataset.housingId);
        const roomIndex = parseInt(cell.dataset.roomIndex) || 0;
        if (housingId !== this.dragState.housingId || roomIndex !== this.dragState.roomIndex) return;
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

    this.element.querySelectorAll('.planning-block').forEach(el => {
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        const td = el.closest('td[data-entry-id]');
        if (!td) return;
        const entryId = parseInt(td.dataset.entryId);
        const entry = this.entries.find(en => en.occupancy_id === entryId);
        if (entry) this._showEntryDetailModal(entry);
      });
    });
  }

  _bindTouchEvents() {
    if (!this.element) return;

    let touchStartCell = null;
    let touchCurrentCell = null;
    let longPressTimer = null;

    this.element.querySelectorAll('.planning-cell').forEach(cell => {
      cell.addEventListener('touchstart', (e) => {
        if (e.target.closest('.planning-block')) return;
        
        touchStartCell = cell;
        touchCurrentCell = cell;
        
        const housingId = parseInt(cell.dataset.housingId);
        const roomIndex = parseInt(cell.dataset.roomIndex) || 0;
        const date = cell.dataset.date;
        if (date < formatDateISO(new Date())) return;
        
        longPressTimer = setTimeout(() => {
          this.dragState = { housingId, roomIndex, startDate: date, endDate: date };
          cell.classList.add('planning-cell--selected');
          if (navigator.vibrate) navigator.vibrate(50);
        }, 500);
      }, { passive: true });

      cell.addEventListener('touchmove', (e) => {
        if (!touchStartCell) return;
        
        const touch = e.touches[0];
        const elementBelow = document.elementFromPoint(touch.clientX, touch.clientY);
        const cellBelow = elementBelow?.closest('.planning-cell');
        
        if (cellBelow && cellBelow !== touchCurrentCell) {
          clearTimeout(longPressTimer);
          touchCurrentCell = cellBelow;
          
          if (this.dragState) {
            if (parseInt(cellBelow.dataset.roomIndex) !== this.dragState.roomIndex) return;
            const date = cellBelow.dataset.date;
            this.dragState.endDate = date;
            this._highlightDragRange();
          }
        }
      }, { passive: true });

      cell.addEventListener('touchend', (e) => {
        clearTimeout(longPressTimer);
        
        if (this.dragState) {
          this._onDragEnd();
          this.dragState = null;
          this.element.querySelectorAll('.planning-cell--selected').forEach(c => c.classList.remove('planning-cell--selected'));
        } else if (touchStartCell === touchCurrentCell) {
          const housingId = parseInt(touchStartCell.dataset.housingId);
          const roomIndex = parseInt(touchStartCell.dataset.roomIndex) || 0;
          const date = touchStartCell.dataset.date;
          if (date < formatDateISO(new Date())) {
            touchStartCell = null;
            touchCurrentCell = null;
            return;
          }
          this.dragState = { housingId, roomIndex, startDate: date, endDate: date };
          this._onDragEnd();
          this.dragState = null;
        }
        
        touchStartCell = null;
        touchCurrentCell = null;
      }, { passive: true });
    });

    this.element.querySelectorAll('.planning-block').forEach(el => {
      el.addEventListener('touchend', (e) => {
        e.stopPropagation();
        const td = el.closest('td[data-entry-id]');
        if (!td) return;
        const entryId = parseInt(td.dataset.entryId);
        const entry = this.entries.find(en => en.occupancy_id === entryId);
        if (entry) this._showEntryDetailModal(entry);
      }, { passive: true });
    });
  }

  _highlightDragRange() {
    if (!this.dragState || !this.element) return;
    this.element.querySelectorAll('.planning-cell--drag').forEach(c => c.classList.remove('planning-cell--drag'));
    const { housingId, roomIndex, startDate, endDate } = this.dragState;
    const [start, end] = startDate <= endDate ? [startDate, endDate] : [endDate, startDate];
    this.element.querySelectorAll(`.planning-cell[data-housing-id="${housingId}"][data-room-index="${roomIndex}"]`).forEach(cell => {
      const d = cell.dataset.date;
      if (d && d >= start && d <= end && !cell.dataset.entryId) {
        cell.classList.add('planning-cell--drag');
      }
    });
  }

  _onDragEnd() {
    if (!this.dragState) return;
    let { startDate, endDate, housingId, roomIndex } = this.dragState;
    if (startDate > endDate) [startDate, endDate] = [endDate, startDate];
    const today = formatDateISO(new Date());
    if (startDate < today || endDate < today) {
      alert('Impossible de créer une réservation sur une date passée');
      return;
    }

    const overlaps = this.entries.some(entry => {
      if (entry.housing_id !== housingId) return false;
      const entryRoom = entry.room_index == null ? 0 : Number(entry.room_index);
      if (entryRoom !== roomIndex || !['pre_reserved', 'confirmed', 'in_progress'].includes(entry.status)) return false;
      return (entry.arrival_date || '').slice(0, 10) <= endDate
        && (entry.departure_date || '').slice(0, 10) >= startDate;
    });
    if (overlaps) {
      alert('Cette période chevauche déjà une réservation');
      return;
    }
    this._showNewOccupancyModal(housingId, startDate, endDate, roomIndex);
  }

  _showNewOccupancyModal(housingId, startDate, endDate, roomIndex = 0) {
    const housing = this.housings.find(h => h.id === housingId);
    if (!housing) return;
    this._modalHousingId = housingId;
    this._modalRoomIndex = roomIndex;
    this._openModal(this._buildOccupancyFormModal(housing, startDate, endDate, roomIndex));
  }

  _showEntryDetailModal(entry) {
    this.selectedEntry = entry;
    this._openModal(this._buildEntryDetailModal(entry));
  }

  _openModal(html) {
    this._closeModal();
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay open';
    overlay.style.cssText = 'position:fixed;inset:0;z-index:1000;display:flex;align-items:flex-end;justify-content:center;';
    
    const isMobile = window.innerWidth <= 640;
    const modalWidth = isMobile ? '100%' : '95%';
    const modalMaxWidth = isMobile ? '100%' : '640px';
    const modalBorderRadius = isMobile ? '16px 16px 0 0' : 'var(--radius-lg)';
    const modalMaxHeight = isMobile ? '85vh' : '90vh';
    
    overlay.innerHTML = `
      <div class="modal-content" style="
        max-width:${modalMaxWidth};
        width:${modalWidth};
        max-height:${modalMaxHeight};
        overflow-y:auto;
        border-radius:${modalBorderRadius};
        margin-bottom:${isMobile ? '0' : 'auto'};
        ${isMobile ? 'padding-bottom:env(safe-area-inset-bottom)' : ''}
      ">${html}</div>
    `;
    
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

  _showOccupantCreateModal(occupancyOverlay, index) {
    const modal = document.createElement('div');
    modal.className = 'modal-overlay open';
    modal.style.cssText = 'position:fixed;inset:0;z-index:1100;display:flex;align-items:center;justify-content:center;padding:16px;background:var(--color-overlay);';
    modal.innerHTML = `
      <div class="modal-content occupant-create-modal" style="width:min(520px,100%);max-height:90vh;">
        <div class="modal-header">
          <h2>Nouvel occupant</h2>
          <button class="modal-close" type="button" data-action="close">&times;</button>
        </div>
        <div class="modal-body">
          <form data-occupant-form>
            <div class="form-row">
              <label><span>Nom *</span><input name="last_name" required maxlength="100" style="text-transform:uppercase"></label>
              <label><span>Prénom *</span><input name="first_name" required maxlength="100"></label>
            </div>
            <div class="form-row">
              <label><span>Téléphone *</span><input name="phone" type="tel" required maxlength="50"></label>
              <label><span>E-mail *</span><input name="email" type="email" required maxlength="200"></label>
            </div>
          </form>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" type="button" data-action="close">Annuler</button>
          <button class="btn btn-primary" type="button" data-action="save">Créer</button>
        </div>
      </div>
    `;

    const close = () => modal.remove();
    modal.querySelectorAll('[data-action="close"]').forEach(button => button.addEventListener('click', close));
    modal.addEventListener('click', event => {
      if (event.target === modal) close();
    });
    modal.querySelector('[data-action="save"]')?.addEventListener('click', async () => {
      const form = modal.querySelector('[data-occupant-form]');
      const formData = new FormData(form);
      const data = Object.fromEntries(formData.entries());
      if (!data.last_name || !data.first_name || !data.phone || !data.email) {
        alert('Le nom, le prénom, le téléphone et l\'e-mail sont obligatoires');
        return;
      }

      try {
        const occupant = await createOccupant(data);
        const select = occupancyOverlay.querySelector(`.occ-occupant-select[data-index="${index}"]`);
        if (select) {
          const option = document.createElement('option');
          option.value = occupant.id;
          option.textContent = `${occupant.last_name || ''} ${occupant.first_name || ''}`.trim();
          select.appendChild(option);
          select.value = occupant.id;
        }
        close();
      } catch (error) {
        console.error('Erreur création occupant:', error);
        alert(error?.message || 'Erreur lors de la création de l\'occupant');
      }
    });

    document.body.appendChild(modal);
    modal.querySelector('input[name="last_name"]')?.focus();
  }

  _bindModalEvents(overlay) {
    overlay.querySelectorAll('[data-dismiss]').forEach(btn => {
      btn.addEventListener('click', () => this._closeModal());
    });
  }

  _buildOccupancyFormModal(housing, startDate, endDate, roomIndex = 0) {
    const isMobile = window.innerWidth <= 640;
    let bedConfig = [];
    try { bedConfig = JSON.parse(housing.bed_configuration || '[]'); } catch { bedConfig = []; }
    const nbRooms = housing.nb_rooms || 1;
    if (bedConfig.length === 0) bedConfig = Array(nbRooms).fill('simple');
    const bedType = bedConfig[roomIndex] || 'simple';
    const bedSymbols = bedType === 'double' ? '🛏️🛏️' : '🛏️';
    const housingName = housing.room?.name || housing.name || housing.room_name || 'Logement';
    const roomNames = parseRoomNames(housing.room_names, nbRooms);
    const roomLabel = `${housingName} — ${roomNames[roomIndex]} (${bedSymbols})`;

    return `
      <div class="modal-header" style="padding:${isMobile ? '12px 16px' : '16px 24px'};border-bottom:1px solid var(--color-border-light);">
        <h2 style="margin:0;font-size:${isMobile ? '16px' : '18px'};">Nouvelle réservation</h2>
        <button class="modal-close" data-dismiss style="font-size:24px;padding:4px;">&times;</button>
      </div>
      <div class="modal-body" style="padding:${isMobile ? '16px' : '24px'};">
        <div class="modal-form">
          <div class="form-group" style="margin-bottom:12px;">
            <label style="font-weight:600;font-size:11px;color:var(--color-text-tertiary);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:4px;">Chambre</label>
            <input type="text" value="${roomLabel}" disabled class="form-control" style="background:var(--color-gray-50);">
          </div>
          <div class="reservation-fields-row" style="display:flex;gap:12px;margin-bottom:12px;">
            <div class="form-group" style="flex:1;margin-bottom:0;">
              <label style="font-weight:600;font-size:11px;color:var(--color-text-tertiary);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:4px;">Arrivée</label>
              <input type="date" id="occ-arrival" value="${startDate}" class="form-control">
            </div>
            <div class="form-group" style="flex:1;margin-bottom:0;">
              <label style="font-weight:600;font-size:11px;color:var(--color-text-tertiary);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:4px;">Départ</label>
              <input type="date" id="occ-departure" value="${endDate}" class="form-control">
            </div>
          </div>
          <div class="reservation-fields-row" style="display:flex;gap:12px;margin-bottom:12px;">
            <div class="form-group" style="flex:1;margin-bottom:0;">
              <label style="font-weight:600;font-size:11px;color:var(--color-text-tertiary);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:4px;">Statut</label>
              <select id="occ-status" class="form-control">
                <option value="pre_reserved">Pré-réservé</option>
                <option value="confirmed">Confirmé</option>
              </select>
            </div>
            <div class="form-group" style="flex:1;margin-bottom:0;">
              <label style="font-weight:600;font-size:11px;color:var(--color-text-tertiary);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:4px;">Type</label>
              <div class="guest-type-toggle" role="group" aria-label="Type d'invité">
                <button type="button" class="btn btn-secondary guest-type-btn${bedType !== 'double' ? ' active' : ''}" data-guest-type="single" aria-pressed="${bedType !== 'double' ? 'true' : 'false'}">Célibataire</button>
                <button type="button" class="btn btn-secondary guest-type-btn${bedType === 'double' ? ' active' : ''}" data-guest-type="couple" aria-pressed="${bedType === 'double' ? 'true' : 'false'}"${bedType === 'simple' ? ' disabled' : ''}>Couple</button>
              </div>
              <select id="occ-guest-type" aria-hidden="true" tabindex="-1" style="display:none;">
                <option value="single"${bedType !== 'double' ? ' selected' : ''}>Célibataire</option>
                <option value="couple"${bedType === 'double' ? ' selected' : ''}>Couple</option>
              </select>
            </div>
          </div>
          <div class="form-group" style="margin-bottom:12px;">
            <label style="font-weight:600;font-size:11px;color:var(--color-text-tertiary);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:4px;">Occupants principaux</label>
            <div id="occ-occupant-list" class="occupant-list-container">
              <div class="occupant-entry" data-index="0">
                <select class="form-control occ-occupant-select" data-index="0">
                  <option value="">— Choisir ou créer —</option>
                </select>
                <button class="btn btn-sm btn-secondary occ-quick-create" data-index="0" title="Créer rapidement" style="padding:8px 12px;">+</button>
              </div>
            </div>
          </div>
          <div class="form-group" style="margin-bottom:16px;">
            <label style="font-weight:600;font-size:11px;color:var(--color-text-tertiary);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:4px;">Notes</label>
            <textarea id="occ-notes" class="form-control" rows="2" placeholder="Notes internes..."></textarea>
          </div>
          <div class="modal-footer reservation-modal-footer" style="display:flex;gap:8px;justify-content:flex-end;padding-top:16px;border-top:1px solid var(--color-border-light);">
            <button class="btn btn-secondary" data-dismiss style="flex:1;">Annuler</button>
            <button class="btn btn-primary" id="occ-save" style="flex:1;">Enregistrer</button>
          </div>
        </div>
      </div>
    `;
  }

  _buildEntryDetailModal(entry) {
    const statusClass = entry.status || 'pre_reserved';
    const primaryOccupant = (entry.occupants && entry.occupants[0]) || null;
    const housing = this.housings.find(h => h.id === entry.housing_id);
    const roomNames = parseRoomNames(housing?.room_names, housing?.nb_rooms || 1);
    const roomName = roomNames[entry.room_index || 0];
    const isMobile = window.innerWidth <= 640;

    let occupantsHtml = '';
    (entry.occupants || []).forEach((occ, i) => {
      if (isMobile && i > 0) return;
      occupantsHtml += `
        <div class="detail-occupant-row" style="display:flex;gap:8px;align-items:center;padding:6px 0;${i > 0 ? 'border-top:1px solid var(--color-border-light);' : ''}">
          <span style="flex:1;font-size:${isMobile ? '13px' : '14px'};">${getOccupantDisplayName(occ)}</span>
          ${!isMobile ? `<span style="color:var(--color-text-tertiary);font-size:12px;">${occ.email || ''}</span>` : ''}
        </div>`;
    });
    
    if (isMobile && (entry.occupants || []).length > 1) {
      occupantsHtml += `<div style="text-align:center;padding:4px;color:var(--color-text-tertiary);font-size:11px;">+${(entry.occupants || []).length - 1} autre(s)</div>`;
    }

    return `
      <div class="modal-header" style="padding:${isMobile ? '12px 16px' : '16px 24px'};border-bottom:1px solid var(--color-border-light);">
        <h2 style="margin:0;font-size:${isMobile ? '16px' : '18px'};">${getOccupantDisplayName(primaryOccupant) || 'Réservation'}</h2>
        <button class="modal-close" data-dismiss style="font-size:24px;padding:4px;">&times;</button>
      </div>
      <div class="modal-body" style="padding:${isMobile ? '16px' : '24px'};">
        <div class="reservation-detail-row" style="display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap;">
          <div style="flex:1;min-width:${isMobile ? '100px' : '120px'};">
            <label style="font-weight:600;font-size:11px;color:var(--color-text-tertiary);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:4px;">Statut</label>
            <div>
              <span class="planning-occupancy planning-occupancy--${statusClass}" style="display:inline-flex;pointer-events:none;">
                ${STATUS_LABELS[entry.status] || entry.status}
              </span>
            </div>
          </div>
          <div style="flex:1;min-width:${isMobile ? '100px' : '120px'};">
            <label style="font-weight:600;font-size:11px;color:var(--color-text-tertiary);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:4px;">Chambre</label>
           <div style="font-weight:500;">${housing?.room?.name || housing?.name || entry.housing_name || 'Logement'} — ${roomName}</div>
          </div>
        </div>
        <div class="reservation-detail-row" style="display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap;">
          <div style="flex:1;min-width:${isMobile ? '80px' : '100px'};">
            <label style="font-weight:600;font-size:11px;color:var(--color-text-tertiary);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:4px;">Arrivée</label>
            <div style="font-size:${isMobile ? '13px' : '14px'};">${formatDateShort(new Date(entry.arrival_date))}</div>
          </div>
          <div style="flex:1;min-width:${isMobile ? '80px' : '100px'};">
            <label style="font-weight:600;font-size:11px;color:var(--color-text-tertiary);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:4px;">Départ</label>
            <div style="font-size:${isMobile ? '13px' : '14px'};">${formatDateShort(new Date(entry.departure_date))}</div>
          </div>
          <div style="flex:1;min-width:${isMobile ? '60px' : '80px'};">
            <label style="font-weight:600;font-size:11px;color:var(--color-text-tertiary);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:4px;">Personnes</label>
            <div style="font-size:${isMobile ? '13px' : '14px'};">${entry.nb_persons || 1}</div>
          </div>
        </div>
        ${entry.has_cleaning_planned ? `
        <div style="margin-bottom:16px;padding:12px;background:var(--color-gray-50);border-radius:var(--radius-md);">
          <label style="font-weight:600;font-size:11px;color:var(--color-text-tertiary);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:6px;">Nettoyage</label>
          <div>
            <span class="badge" style="background:${CLEANING_STATUS_COLORS[entry.cleaning_status] || '#9ca3af'};color:white;">${CLEANING_STATUS_LABELS[entry.cleaning_status] || 'Planifié'}</span>
          </div>
        </div>` : ''}
        <div style="margin-bottom:16px;">
          <label style="font-weight:600;font-size:11px;color:var(--color-text-tertiary);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:8px;">Occupants</label>
          ${occupantsHtml || '<div style="color:var(--color-text-tertiary);font-style:italic;">Aucun occupant</div>'}
        </div>
        <div class="modal-footer reservation-modal-footer" style="display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap;padding-top:16px;border-top:1px solid var(--color-border-light);">
          ${entry.status === 'pre_reserved' ? `<button class="btn btn-primary" data-action="confirm" style="flex:1;min-width:${isMobile ? '100px' : 'auto'};">Confirmer la réservation</button>` : ''}
           ${entry.status !== 'cancelled' && entry.status !== 'pre_reserved' ? `<button class="btn btn-danger" data-action="cancel-occupancy" style="flex:1;min-width:${isMobile ? '100px' : 'auto'};">Annuler la réservation</button>` : ''}
            ${entry.status === 'pre_reserved' ? `<button class="btn btn-danger" data-action="delete-occupancy" style="flex:1;min-width:${isMobile ? '100px' : 'auto'};">Supprimer la réservation</button>` : ''}
              ${['not_planned', 'in_progress', 'planned'].includes(entry.cleaning_status) && entry.status !== 'pre_reserved' ? `<button class="btn btn-secondary" data-action="manage-cleaning" style="flex:1;min-width:${isMobile ? '100px' : 'auto'};">${entry.cleaning_status === 'planned' ? 'Voir le ménage' : 'Gérer les invitations'}</button>` : ''}
          <button class="btn btn-secondary" data-action="send-email" style="flex:1;min-width:${isMobile ? '100px' : 'auto'};">E-mail</button>
          <button class="btn btn-secondary" data-dismiss style="flex:1;min-width:${isMobile ? '100px' : 'auto'};">Fermer</button>
        </div>
      </div>
    `;
  }

  _buildEmailComposerModal(entry, requireTemplate = false, templateType = 'custom') {
    const primaryOccupant = (entry.occupants && entry.occupants[0]) || null;
    const usesConfiguredTemplate = ['confirmation', 'cancellation'].includes(templateType);
    return `
      <div class="modal-header" data-require-template="${requireTemplate ? 'true' : 'false'}" data-template-type="${templateType}">
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
          ${usesConfiguredTemplate ? `
          <div class="form-group">
            <label>Modèle d’e-mail</label>
            <div id="email-template-label" class="form-control" style="background:var(--color-gray-50);">Chargement du modèle configuré...</div>
            <input type="hidden" id="email-template" value="">
          </div>` : `
          <div class="form-group">
            <label>Modèle d’e-mail</label>
            <select id="email-template" class="form-control">
              <option value="">Chargement des modèles...</option>
            </select>
          </div>`}
          <div class="form-group">
            <label>Sujet</label>
            <input type="text" id="email-subject" class="form-control" placeholder="Objet de l'e-mail">
          </div>
          <div class="form-group">
            <label>Message</label>
            <input type="hidden" id="email-body" value="">
            <div style="border:1px solid var(--color-border);border-radius:6px;overflow:hidden;">
              <div style="display:flex;gap:4px;flex-wrap:wrap;padding:8px;background:var(--color-gray-50);border-bottom:1px solid var(--color-border);">
                <button type="button" class="btn btn-sm btn-secondary" data-email-command="bold"><strong>Gras</strong></button>
                <button type="button" class="btn btn-sm btn-secondary" data-email-command="italic"><em>Italique</em></button>
                <button type="button" class="btn btn-sm btn-secondary" data-email-command="underline"><u>Souligné</u></button>
                <select data-email-format-block class="form-control" style="width:auto;padding:4px 8px;">
                  <option value="p">Paragraphe</option>
                  <option value="h2">Titre</option>
                  <option value="h3">Sous-titre</option>
                </select>
                <button type="button" class="btn btn-sm btn-secondary" data-email-command="insertUnorderedList">Liste</button>
                <button type="button" class="btn btn-sm btn-secondary" data-email-command="insertOrderedList">Liste numérotée</button>
                <button type="button" class="btn btn-sm btn-secondary" data-email-command="justifyLeft">Gauche</button>
                <button type="button" class="btn btn-sm btn-secondary" data-email-command="justifyCenter">Centrer</button>
                <button type="button" class="btn btn-sm btn-secondary" data-email-command="justifyRight">Droite</button>
                <button type="button" class="btn btn-sm btn-secondary" data-email-action="link">Lien</button>
                <button type="button" class="btn btn-sm btn-secondary" data-email-command="removeFormat">Effacer le format</button>
              </div>
              <div id="email-body-editor" contenteditable="true" style="min-height:160px;padding:12px;outline:none;"></div>
            </div>
          </div>
          <div class="modal-footer" style="margin-top:1rem;display:flex;gap:8px;justify-content:flex-end;">
            <button class="btn btn-secondary" data-dismiss>Annuler</button>
            <button class="btn btn-primary" id="email-send">Envoyer</button>
          </div>
        </div>
      </div>
    `;
  }

  _buildCleaningModal(entry, invitationMode = false) {
    const departureDate = (entry.departure_date || '').slice(0, 10);
    const defaultCleaningDate = entry.cleaning_scheduled_date || getNextWeekdayAfter(departureDate);
    const hasCleaning = Boolean(entry.cleaning_id);
    const cleaningStatus = entry.cleaning_status || 'not_planned';
    const isPlanned = cleaningStatus === 'planned';
    const showInvitationDetails = !isPlanned && (cleaningStatus !== 'in_progress' || invitationMode);
    const cleaningStatusLabel = CLEANING_STATUS_LABELS[cleaningStatus] || 'Non planifié';
    const invitationStatus = entry.cleaning_invitation_status === 'sent' ? 'Invitation envoyée' : 'Invitation non envoyée';
    return `
      <div class="modal-header">
        <h2>${hasCleaning ? 'Planifier le ménage et gérer les volontaires' : 'Planifier un nettoyage'}</h2>
        <button class="modal-close" data-dismiss>&times;</button>
      </div>
      <div class="modal-body">
        <div class="modal-form">
          <div class="form-group">
            <label>Date prévue</label>
            <input type="date" id="cleaning-date" class="form-control" value="${defaultCleaningDate}"${['in_progress', 'planned'].includes(cleaningStatus) ? ' disabled' : ''}>
          </div>
          <div class="form-row">
             <div class="form-group">
              <label>Statut</label>
              <div class="form-control" style="background:var(--color-gray-50);">${cleaningStatusLabel}</div>
            </div>
          </div>
           ${isPlanned ? `<div class="form-group">
             <label>Volontaires retenus</label>
             <div data-cleaning-volunteers style="border:1px solid var(--color-border-light);padding:8px;">Chargement des volontaires...</div>
           </div>` : ''}
           ${showInvitationDetails ? `<div class="form-group">
            <label>Nombre de bénévoles nécessaires</label>
            <input type="number" id="cleaning-volunteers-needed" class="form-control" min="1" step="1" value="${entry.cleaning_volunteers_needed || 1}" required>
          </div>
          <div class="form-group">
            <label>Notes</label>
            <textarea id="cleaning-notes" class="form-control" rows="2" placeholder="Instructions de nettoyage..."></textarea>
          </div>
          <div style="margin-bottom:12px;color:var(--color-text-secondary);font-size:13px;">${invitationStatus}</div>
          <div class="form-group">
            <label style="display:flex;align-items:center;gap:8px;">
              <span>Volontaires ménage</span>
              <label style="margin-left:auto;font-weight:normal;"><input type="checkbox" data-cleaning-select-all> Sélectionner tout</label>
            </label>
            <div data-cleaning-volunteers style="max-height:180px;overflow-y:auto;border:1px solid var(--color-border-light);padding:8px;">Chargement des volontaires...</div>
          </div>` : ''}
          <div class="modal-footer" style="margin-top:1rem;display:flex;gap:8px;justify-content:flex-end;">
             ${hasCleaning
              ? isPlanned
                ? '<button class="btn btn-danger" id="cleaning-delete" type="button">Annuler le ménage</button><button class="btn btn-secondary" data-dismiss>Fermer</button>'
               : `${entry.cleaning_status === 'not_planned'
                ? '<button class="btn btn-primary" id="cleaning-invite">Inviter les volontaires</button>'
                : entry.cleaning_status === 'in_progress'
                  ? (invitationMode
                    ? '<button class="btn btn-primary" id="cleaning-invite">Envoyer les invitations</button>'
                    : '<button class="btn btn-primary" id="cleaning-manage-invitations">Gérer les invitations</button>')
                  : '<button class="btn btn-primary" id="cleaning-save">Enregistrer les modifications</button>'}
                 <button class="btn btn-danger" id="cleaning-delete" type="button">${['not_planned', 'in_progress'].includes(entry.cleaning_status) ? 'Annuler le ménage' : 'Supprimer le ménage'}</button>
                 ${entry.cleaning_status === 'not_planned' ? '<button class="btn btn-secondary" id="cleaning-save" type="button">Enregistrer</button>' : ''}
                 <button class="btn btn-secondary" data-dismiss>Fermer</button>`
              : `${cleaningStatus === 'not_planned' ? '<button class="btn btn-danger" id="cleaning-delete" type="button">Annuler le ménage</button>' : ''}
                 <button class="btn btn-primary" id="cleaning-invite">Inviter les volontaires</button>
                   <button class="btn btn-secondary" data-dismiss>Fermer</button>`}
          </div>
        </div>
      </div>
    `;
  }

  _buildCleaningInvitationTrackingModal(entry) {
    return `
      <div class="modal-header">
        <h2>Gérer les invitations</h2>
        <button class="modal-close" data-dismiss>&times;</button>
      </div>
      <div class="modal-body">
        <p style="margin-top:0;color:var(--color-text-secondary);">Sélectionnez exactement ${entry.cleaning_volunteers_needed || 1} volontaire(s) disponible(s) à retenir.</p>
        <div data-cleaning-invitation-tracking>Chargement des réponses...</div>
        <div class="modal-footer" style="margin-top:1rem;display:flex;gap:8px;justify-content:flex-end;">
          <button class="btn btn-primary" id="cleaning-confirm-selection">Valider les volontaires retenus</button>
          <button class="btn btn-secondary" data-dismiss>Fermer</button>
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
    const saveBtn = overlay.querySelector('#occ-save');
    const guestTypeSelect = overlay.querySelector('#occ-guest-type');
    const guestTypeButtons = overlay.querySelectorAll('.guest-type-btn');
    let bedConfig = [];
    try {
      const housing = this.housings.find(h => h.id === this._modalHousingId);
      bedConfig = JSON.parse(housing?.bed_configuration || '[]');
    } catch { bedConfig = []; }
    const bedType = bedConfig[this._modalRoomIndex] || 'simple';

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
      btn.addEventListener('click', () => {
        const index = parseInt(btn.dataset.index);
        this._showOccupantCreateModal(overlay, index);
      });
    });

    const addOccupantRow = () => {
        const container = overlay.querySelector('#occ-occupant-list');
        const entries = container.querySelectorAll('.occupant-entry');
        const guestType = guestTypeSelect?.value;
        
        if (!guestType) {
          alert('Veuillez choisir le type d\'invité');
          return;
        }

        const maxOccupants = guestType === 'couple' && bedType === 'double' ? 2 : 1;
        if (entries.length >= maxOccupants) {
          alert(maxOccupants === 2
            ? 'Un couple peut avoir au maximum deux occupants'
            : 'Un célibataire ou une chambre à lit simple ne peut avoir qu\'un seul occupant');
          return;
        }
        
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
        row.querySelector('.occ-quick-create').addEventListener('click', () => {
          this._showOccupantCreateModal(overlay, nextIndex);
        });
    };

    if (guestTypeSelect) {
      const updateGuestTypeButtons = () => {
        guestTypeButtons.forEach(button => {
          const active = button.dataset.guestType === guestTypeSelect.value;
          button.classList.toggle('active', active);
          button.setAttribute('aria-pressed', String(active));
        });
      };

      guestTypeButtons.forEach(button => {
        button.addEventListener('click', () => {
          if (button.disabled) return;
          guestTypeSelect.value = button.dataset.guestType;
          guestTypeSelect.dispatchEvent(new Event('change'));
        });
      });

      guestTypeSelect.addEventListener('change', () => {
        const container = overlay.querySelector('#occ-occupant-list');
        const entries = container.querySelectorAll('.occupant-entry');
        if (guestTypeSelect.value === 'single' && entries.length > 1) {
          while (container.querySelectorAll('.occupant-entry').length > 1) {
            const currentEntries = container.querySelectorAll('.occupant-entry');
            currentEntries[currentEntries.length - 1].remove();
          }
        } else if (guestTypeSelect.value === 'couple' && bedType === 'double' && entries.length === 1) {
          addOccupantRow();
        }
        updateGuestTypeButtons();
      });
      if (guestTypeSelect.value === 'couple' && bedType === 'double') {
        addOccupantRow();
      }
      updateGuestTypeButtons();
    }

    if (saveBtn) {
      saveBtn.addEventListener('click', async () => {
        const arrival = overlay.querySelector('#occ-arrival')?.value;
        const departure = overlay.querySelector('#occ-departure')?.value;
        const status = overlay.querySelector('#occ-status')?.value;
        const guestType = overlay.querySelector('#occ-guest-type')?.value || null;
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

        if (guestType === 'single' && occupantIds.length > 1) {
          alert('Un célibataire ne peut avoir qu\'un seul occupant');
          return;
        }

        if (guestType === 'couple' && occupantIds.length !== 2) {
          alert('Veuillez sélectionner les deux occupants du couple');
          return;
        }

        if (guestType === 'couple' && bedType === 'simple') {
          alert('Un couple ne peut pas être dans un lit simple');
          return;
        }

        const housingId = this._modalHousingId;

        try {
          const createdOccupancy = await createOccupancy({
            housing_id: housingId,
            room_index: this._modalRoomIndex,
            arrival_date: arrival,
            departure_date: departure,
            status,
            nb_persons: occupantIds.length || 1,
            occupant_ids: occupantIds,
            guest_type: guestType,
            observations: notes,
          });
          this._closeModal();
          await this.loadData();

          if (status === 'confirmed') {
            this.selectedEntry = { ...createdOccupancy, occupancy_id: createdOccupancy.id };
            this._openModal(this._buildEmailComposerModal(this.selectedEntry, true, 'confirmation'));
          }
        } catch (e) {
          console.error('Erreur création réservation:', e);
          const details = Array.isArray(e?.data?.detail)
            ? e.data.detail.map(error => error.msg).join('\n')
            : e?.data?.detail || e?.message;
          alert(details || 'Erreur lors de la création de la réservation');
        }
      });
    }

    const emailSendBtn = overlay.querySelector('#email-send');
    if (emailSendBtn) {
      const editor = overlay.querySelector('#email-body-editor');
      const templateType = overlay.querySelector('[data-template-type]')?.dataset.templateType || 'custom';
      const usesConfiguredTemplate = ['confirmation', 'cancellation'].includes(templateType);
      const applyTemplate = (template) => {
        if (!template) return;
        const occupant = overlay.querySelector('.email-recipient')?.value
          ? (this.selectedEntry.occupants || []).find(item => String(item.id) === overlay.querySelector('.email-recipient').value)
          : (this.selectedEntry.occupants || [])[0];
        const housing = this.housings.find(item => item.id === this.selectedEntry.housing_id);
        const contextEntry = {
          ...this.selectedEntry,
          housing_name: this.selectedEntry.housing_name || housing?.name || '',
          housing_reference: this.selectedEntry.housing_reference || housing?.reference || '',
           building_name: this.selectedEntry.building_name || housing?.building?.name || housing?.building || '',
           site_name: this.selectedEntry.site_name || housing?.site?.name || housing?.site || '',
        };
        const context = getEmailTemplateContext(contextEntry, occupant);
        overlay.querySelector('#email-template').value = template.id;
        overlay.querySelector('#email-subject').value = renderEmailTemplate(template.subject, context);
        const templateBody = template.body_html || `<p>${escapeHtml(template.body_text || '')}</p>`;
        editor.innerHTML = renderEmailTemplate(templateBody, context, true);
        const label = overlay.querySelector('#email-template-label');
        if (label) label.textContent = template.name;
      };

      try {
        const tplResp = await listEmailTemplates({ page_size: 100, template_type: templateType, is_active: true });
        const tplSel = overlay.querySelector('#email-template');
        const templates = tplResp.items || [];
        if (usesConfiguredTemplate) {
          const template = templates.find(item => item.is_default) || templates[0];
          if (template) applyTemplate(template);
          else overlay.querySelector('#email-template-label').textContent = `Aucun modèle ${templateType} actif`;
        } else {
          tplSel.innerHTML = '<option value="">— Sans modèle —</option>';
          templates.forEach(t => {
            const opt = document.createElement('option');
            opt.value = t.id;
            opt.textContent = t.name;
            tplSel.appendChild(opt);
          });
          tplSel.addEventListener('change', () => {
            const template = templates.find(t => String(t.id) === tplSel.value);
            if (template) applyTemplate(template);
          });
        }
      } catch (e) {
        console.error('Erreur chargement modèles d’e-mail:', e);
        const tplSel = overlay.querySelector('#email-template');
        if (usesConfiguredTemplate) {
          overlay.querySelector('#email-template-label').textContent = 'Modèles indisponibles';
        } else if (tplSel) {
          tplSel.innerHTML = '<option value="">Modèles indisponibles</option>';
        }
      }

      overlay.querySelectorAll('[data-email-command]').forEach(button => button.addEventListener('click', () => {
        editor.focus();
        document.execCommand(button.dataset.emailCommand, false, null);
      }));
      overlay.querySelector('[data-email-format-block]')?.addEventListener('change', event => {
        editor.focus();
        document.execCommand('formatBlock', false, event.target.value);
      });
      overlay.querySelector('[data-email-action="link"]')?.addEventListener('click', () => {
        const url = window.prompt('Adresse du lien :', 'https://');
        if (!url) return;
        editor.focus();
        document.execCommand('createLink', false, url);
      });

      emailSendBtn.addEventListener('click', async () => {
        const subject = overlay.querySelector('#email-subject')?.value;
        const bodyHtml = editor?.innerHTML || '';
        const body = editor?.innerText?.trim() || '';
        const recipientCheckboxes = overlay.querySelectorAll('.email-recipient:checked');
        const recipientIds = Array.from(recipientCheckboxes).map(cb => parseInt(cb.value));
        const templateId = overlay.querySelector('#email-template')?.value || null;

        if (overlay.querySelector('[data-require-template]')?.dataset.requireTemplate === 'true' && !templateId) {
          alert('Veuillez sélectionner un modèle d’e-mail');
          return;
        }

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
            templateId ? parseInt(templateId) : null,
            [],
            bodyHtml,
          );
          alert('E-mail envoyé avec succès');
          this._closeModal();
        } catch (e) {
          console.error('Erreur envoi e-mail:', e);
          alert(e?.data?.detail || e?.message || 'Erreur lors de l\'envoi');
        }
      });
    }

    const confirmBtn = overlay.querySelector('[data-action="confirm"]');
    if (confirmBtn) {
      confirmBtn.addEventListener('click', async () => {
        try {
          const confirmedEntry = await changeOccupancyStatus(this.selectedEntry.occupancy_id, 'confirmed');
          this._closeModal();
          await this.loadData();
          this.selectedEntry = { ...confirmedEntry, occupancy_id: confirmedEntry.id || confirmedEntry.occupancy_id };
          this._openModal(this._buildEmailComposerModal(this.selectedEntry, true, 'confirmation'));
        } catch (e) {
          const details = Array.isArray(e?.data?.detail)
            ? e.data.detail.map(error => error.msg).join('\n')
            : e?.data?.detail || e?.message;
          alert(details || 'Erreur lors de la confirmation');
        }
      });
    }

    const deleteOccupancyBtn = overlay.querySelector('[data-action="delete-occupancy"]');
    deleteOccupancyBtn?.addEventListener('click', async () => {
      if (!window.confirm('Supprimer définitivement cette réservation ?')) return;
      try {
        await deleteOccupancy(this.selectedEntry.occupancy_id);
        this._closeModal();
        await this.loadData();
      } catch (e) {
        alert(e?.data?.detail || e.message || 'Erreur lors de la suppression');
      }
    });

    const cancelOccupancyBtn = overlay.querySelector('[data-action="cancel-occupancy"]');
    cancelOccupancyBtn?.addEventListener('click', async () => {
      if (!window.confirm('Confirmer l’annulation de cette réservation ?')) return;
      try {
        const cancelledEntry = await changeOccupancyStatus(this.selectedEntry.occupancy_id, 'cancelled');
        this._closeModal();
        await this.loadData();
        this.selectedEntry = { ...this.selectedEntry, ...cancelledEntry, occupancy_id: cancelledEntry.id || cancelledEntry.occupancy_id };
        this._openModal(this._buildEmailComposerModal(this.selectedEntry, true, 'cancellation'));
      } catch (error) {
        alert(error?.data?.detail || error?.message || 'Erreur lors de l’annulation de la réservation');
      }
    });

    const manageCleaningBtn = overlay.querySelector('[data-action="manage-cleaning"]');
    if (manageCleaningBtn) {
      manageCleaningBtn.addEventListener('click', () => {
        this._closeModal();
        this._openModal(this._buildCleaningModal(this.selectedEntry));
        this._loadCleaningVolunteers(this._currentModal, this.selectedEntry);
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
    const cleaningInviteBtn = overlay.querySelector('#cleaning-invite');
    const cleaningDeleteBtn = overlay.querySelector('#cleaning-delete');
    if (cleaningDeleteBtn) {
      cleaningDeleteBtn.addEventListener('click', async () => {
        const sendsCancellation = ['in_progress', 'planned'].includes(this.selectedEntry.cleaning_status);
        const isNotPlanned = !this.selectedEntry.cleaning_status || this.selectedEntry.cleaning_status === 'not_planned';
        const question = sendsCancellation
          ? 'Annuler ce ménage et envoyer le message d’annulation ?'
          : 'Supprimer définitivement ce ménage ?';
        if (!window.confirm(question)) return;
        if (!this.selectedEntry.cleaning_id) {
          try {
            const created = await createCleaning({
              housing_id: this.selectedEntry.housing_id,
              occupancy_id: this.selectedEntry.occupancy_id,
              scheduled_date: this.selectedEntry.cleaning_scheduled_date || getNextWeekdayAfter((this.selectedEntry.departure_date || '').slice(0, 10)),
              type: 'exit',
              status: 'not_planned',
              volunteers_needed: 1,
              invitation_status: 'not_sent',
            });
            await cancelCleaning(created.id);
            this._closeModal();
            await this.loadData();
          } catch (error) {
            alert(error?.data?.detail || error?.message || 'Impossible d’annuler le ménage');
          }
          return;
        }
        try {
          const result = sendsCancellation || isNotPlanned
            ? await cancelCleaning(this.selectedEntry.cleaning_id)
            : await deleteCleaning(this.selectedEntry.cleaning_id);
          if (sendsCancellation && result.phones?.length) {
            result.phones.forEach(phone => window.open(`sms:${phone}?body=${encodeURIComponent(result.sms_message)}`, '_blank'));
          }
          alert(result.message || 'Ménage supprimé');
          this._closeModal();
          await this.loadData();
        } catch (error) {
          alert(error?.data?.detail || error?.message || 'Erreur lors de la suppression du ménage');
        }
      });
    }
    const saveCleaning = async () => {
        const scheduledDate = overlay.querySelector('#cleaning-date')?.value;
        const volunteersNeeded = Number(overlay.querySelector('#cleaning-volunteers-needed')?.value || 0);
        const notes = overlay.querySelector('#cleaning-notes')?.value || '';

        if (!scheduledDate) {
          alert('Veuillez sélectionner une date');
          return false;
        }
        if (volunteersNeeded < 1) {
          alert('Le nombre de bénévoles doit être au moins égal à 1');
          return false;
        }

        const cleaningData = {
          housing_id: this.selectedEntry.housing_id,
          occupancy_id: this.selectedEntry.occupancy_id,
          scheduled_date: scheduledDate,
          type: 'exit',
          volunteers_needed: volunteersNeeded,
          invitation_status: 'not_sent',
          notes,
        };
        if (this.selectedEntry.cleaning_id) {
          await updateCleaning(this.selectedEntry.cleaning_id, cleaningData);
        } else {
          cleaningData.status = 'not_planned';
          const createdCleaning = await createCleaning(cleaningData);
          this.selectedEntry = { ...this.selectedEntry, cleaning_id: createdCleaning.id };
        }
        await this.loadData();
        const refreshedEntry = this.entries.find(entry => entry.occupancy_id === this.selectedEntry.occupancy_id);
        if (refreshedEntry) this.selectedEntry = refreshedEntry;
        await this._loadCleaningVolunteers(overlay, this.selectedEntry);
        return true;
    };
    if (cleaningSaveBtn) {
      cleaningSaveBtn.addEventListener('click', async () => {
        try {
          if (await saveCleaning()) this._closeModal();
        } catch (e) {
          console.error('Erreur enregistrement nettoyage:', e);
          alert(e?.data?.detail || e?.message || 'Erreur lors de l’enregistrement du ménage');
        }
      });
    }
    if (cleaningInviteBtn) {
      cleaningInviteBtn.addEventListener('click', async () => {
        const volunteersNeeded = Number(overlay.querySelector('#cleaning-volunteers-needed')?.value || 0);
        const selectedIds = [...overlay.querySelectorAll('.cleaning-volunteer-checkbox:checked')]
          .map(checkbox => Number(checkbox.value));
        if (selectedIds.length < volunteersNeeded) {
          alert(`Sélectionnez au moins ${volunteersNeeded} volontaire(s) pour envoyer l’invitation`);
          return;
        }
        if (!window.confirm('Voulez-vous envoyer l’invitation aux volontaires sélectionnés ?')) return;
        try {
          if (!await saveCleaning()) return;
          const result = await sendCleaningVolunteerRequest(this.selectedEntry.cleaning_id, {
            volunteer_ids: selectedIds,
          });
          if (result.sms_messages?.length) {
            result.sms_messages.forEach(item => {
              window.open(`sms:${item.phone}?body=${encodeURIComponent(item.message)}`, '_blank');
            });
          }
          this.selectedEntry = {
            ...this.selectedEntry,
            cleaning_status: result.status || 'in_progress',
            cleaning_invitation_status: 'sent',
          };
          await this.loadData();
          alert(result.message);
          this._closeModal();
        } catch (e) {
          console.error('Erreur invitation nettoyage:', e);
          alert(e?.data?.detail || e?.message || 'Erreur lors de l’envoi des invitations');
        }
      });
    }
    const manageCleaningInvitationsBtn = overlay.querySelector('#cleaning-manage-invitations');
    if (manageCleaningInvitationsBtn) {
      manageCleaningInvitationsBtn.addEventListener('click', async () => {
        try {
          const details = await getCleaningInvitationDetails(this.selectedEntry.cleaning_id);
          this.selectedEntry = {
            ...this.selectedEntry,
            cleaning_status: details.status,
            cleaning_volunteers_needed: details.volunteers_needed,
            invitation_history: details.invitation_history || [],
            selected_volunteer_ids: details.selected_volunteer_ids || [],
          };
          this._closeModal();
          this._openModal(this._buildCleaningInvitationTrackingModal(this.selectedEntry));
          this._loadCleaningInvitationTracking(this._currentModal, this.selectedEntry);
        } catch (error) {
          alert(error?.data?.detail || error?.message || 'Impossible de charger les invitations');
        }
      });
    }
    const confirmSelectionBtn = overlay.querySelector('#cleaning-confirm-selection');
    if (confirmSelectionBtn) {
      confirmSelectionBtn.addEventListener('click', async () => {
        const selectedIds = [...overlay.querySelectorAll('.cleaning-selected-checkbox:checked')]
          .map(checkbox => Number(checkbox.value));
        const volunteersNeeded = Number(this.selectedEntry.cleaning_volunteers_needed || 1);
        if (selectedIds.length !== volunteersNeeded) {
          alert(`Sélectionnez exactement ${volunteersNeeded} volontaire(s)`);
          return;
        }
        if (!window.confirm('Valider les volontaires retenus et envoyer leur confirmation ?')) return;
        try {
          const result = await confirmCleaningVolunteers(this.selectedEntry.cleaning_id, selectedIds);
          result.sms_messages?.forEach(item => {
            window.open(`sms:${item.phone}?body=${encodeURIComponent(item.message)}`, '_blank');
          });
          alert(result.message || 'Volontaires retenus et confirmations envoyées');
          this._closeModal();
          await this.loadData();
        } catch (error) {
          alert(error?.data?.detail || error?.message || 'Erreur lors de la validation des volontaires');
        }
      });
    }
  }

  async _loadCleaningInvitationTracking(overlay, entry) {
    const container = overlay.querySelector('[data-cleaning-invitation-tracking]');
    if (!container) return;
    try {
      const [details, volunteers] = await Promise.all([
        getCleaningInvitationDetails(entry.cleaning_id),
        listVolunteers({ limit: 1000, usage_type: 'cleaning', is_active: true }),
      ]);
      const history = details.invitation_history || [];
      const latestByVolunteer = new Map();
      history.forEach(item => {
        const current = latestByVolunteer.get(item.volunteer_id);
        if (!current || new Date(item.sent_at || 0) > new Date(current.sent_at || 0)) {
          latestByVolunteer.set(item.volunteer_id, item);
        }
      });
      const responded = history
        .filter(item => item.response_at && item.availability_response)
        .sort((a, b) => new Date(a.response_at) - new Date(b.response_at));
      const fastestId = responded[0]?.volunteer_id;
      const selectedIds = details.selected_volunteer_ids || [];
      const volunteerById = new Map(volunteers.map(item => [item.id, item]));
      const invitations = history;
      const availableCount = invitations.filter(item => item.availability_response === 'available').length;
      const unavailableCount = invitations.filter(item => item.availability_response === 'unavailable').length;
      const noResponseCount = invitations.filter(item => !item.availability_response).length;
      const rows = invitations.map(invitation => {
        const volunteerId = invitation.volunteer_id;
        const volunteer = volunteerById.get(volunteerId);
        const name = volunteer
          ? `${volunteer.first_name || ''} ${volunteer.last_name || ''}`.trim()
          : invitation.volunteer_name;
        const responseLabel = invitation.availability_response === 'available'
          ? '<span style="color:#15803d;font-weight:600;">Disponible</span>'
          : invitation.availability_response === 'unavailable'
            ? '<span style="color:#b91c1c;font-weight:600;">Indisponible</span>'
            : '<span style="color:var(--color-text-tertiary);">Pas de réponse</span>';
        const fastestLabel = invitation.response_at && invitation.volunteer_id === fastestId
          ? '<small style="color:#2563eb;font-weight:600;">Réponse la plus rapide</small>'
          : '';
        const isLatestInvitation = latestByVolunteer.get(volunteerId)?.id === invitation.id;
        const available = isLatestInvitation && invitation.availability_response === 'available';
        return `<label style="display:grid;grid-template-columns:auto 1fr auto;gap:10px;align-items:center;padding:9px 0;border-bottom:1px solid var(--color-border-light);">
          <input type="checkbox" class="cleaning-selected-checkbox" value="${volunteerId}"${selectedIds.includes(volunteerId) && isLatestInvitation ? ' checked' : ''}${available ? '' : ' disabled'}>
          <span><strong>${escapeHtml(name || 'Volontaire')}</strong><br>${responseLabel} ${fastestLabel}</span>
          <small style="color:var(--color-text-tertiary);">${invitation.channel || ''}</small>
        </label>`;
      }).join('');
      container.innerHTML = `${rows
        ? `<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:10px;font-size:12px;">
             <span>Invités : <strong>${invitations.length}</strong></span>
             <span style="color:#15803d;">Disponibles : <strong>${availableCount}</strong></span>
             <span style="color:#b91c1c;">Indisponibles : <strong>${unavailableCount}</strong></span>
             <span style="color:var(--color-text-tertiary);">Sans réponse : <strong>${noResponseCount}</strong></span>
           </div>${rows}`
        : '<p style="color:var(--color-text-tertiary);">Aucune invitation trouvée.</p>'}`;
      const selectedCheckboxes = () => [...container.querySelectorAll('.cleaning-selected-checkbox:checked')];
      const refreshCheckboxAvailability = () => {
        const selectedCount = selectedCheckboxes().length;
        container.querySelectorAll('.cleaning-selected-checkbox:not(:checked)').forEach(checkbox => {
          checkbox.disabled = selectedCount >= Number(entry.volunteers_needed || details.volunteers_needed || 1);
        });
      };
      container.querySelectorAll('.cleaning-selected-checkbox').forEach(checkbox => {
        checkbox.addEventListener('change', () => {
          refreshCheckboxAvailability();
        });
      });
      refreshCheckboxAvailability();
    } catch (error) {
      container.innerHTML = '<p class="alert alert-danger">Impossible de charger les réponses.</p>';
      console.error('Erreur chargement réponses invitations:', error);
    }
  }

  async _loadCleaningVolunteers(overlay, entry) {
    const container = overlay.querySelector('[data-cleaning-volunteers]');
    if (!container) return;
    try {
      const volunteers = await listVolunteers({ limit: 1000, usage_type: 'cleaning', is_active: true });
      if (entry.cleaning_status === 'planned') {
        const selectedIds = new Set(entry.cleaning_volunteer_ids || []);
        const selectedVolunteers = volunteers.filter(volunteer => selectedIds.has(volunteer.id));
        container.innerHTML = selectedVolunteers.length
          ? selectedVolunteers.map(volunteer => `<div style="padding:6px 0;border-bottom:1px solid var(--color-border-light);">${volunteer.last_name} ${volunteer.first_name}</div>`).join('')
          : '<div style="color:var(--color-text-tertiary);font-style:italic;">Aucun volontaire retenu.</div>';
        return;
      }
      if (!volunteers.length) {
        container.innerHTML = '<div style="color:var(--color-text-tertiary);font-style:italic;">Aucun volontaire ménage actif.</div>';
        return;
      }
      container.innerHTML = volunteers.map(volunteer => `
        <label style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--color-border-light);">
          <input type="checkbox" class="cleaning-volunteer-checkbox" value="${volunteer.id}"${entry.cleaning_volunteer_ids?.includes(volunteer.id) ? ' checked' : ''}>
          <span style="flex:1;">${volunteer.last_name} ${volunteer.first_name}</span>
          <small style="color:var(--color-text-tertiary);">${volunteer.email || volunteer.phone || 'Aucun contact'}</small>
        </label>`).join('');
      overlay.querySelector('[data-cleaning-select-all]')?.addEventListener('change', (event) => {
        overlay.querySelectorAll('.cleaning-volunteer-checkbox').forEach(checkbox => {
          checkbox.checked = event.target.checked;
        });
      });
    } catch (error) {
      console.error('Erreur chargement volontaires ménage:', error);
      container.innerHTML = '<div style="color:var(--color-danger);">Impossible de charger les volontaires.</div>';
    }
  }

  _updateViewButtons() {
    if (!this.element) return;
    this.element.querySelectorAll('[data-view]').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.view === this.viewMode);
    });
  }

  _bindMonthSwipe(element) {
    if (!element) return;
    let startX = 0;
    let startY = 0;
    element.addEventListener('touchstart', event => {
      const touch = event.touches[0];
      startX = touch.clientX;
      startY = touch.clientY;
    }, { passive: true });
    element.addEventListener('touchend', event => {
      if (this.viewMode !== 'month') return;
      const touch = event.changedTouches[0];
      const deltaX = touch.clientX - startX;
      const deltaY = touch.clientY - startY;
      if (Math.abs(deltaX) < 50 || Math.abs(deltaX) < Math.abs(deltaY)) return;
      this.currentDate.setMonth(this.currentDate.getMonth() + (deltaX < 0 ? 1 : -1));
      this.loadData();
    }, { passive: true });
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
        <div class="page-header-right" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
          <div class="btn-group" style="display:flex;border:1px solid var(--border-color);border-radius:var(--radius-md);overflow:hidden;">
            <button class="btn btn-secondary btn-sm" data-view="day" style="border-radius:0;border:none;">Jour</button>
            <button class="btn btn-secondary btn-sm" data-view="week" style="border-radius:0;border:none;">Semaine</button>
            <button class="btn btn-secondary btn-sm active" data-view="month" style="border-radius:0;border:none;">Mois</button>
          </div>
          <select class="form-control" id="status-filter" style="width:auto;padding:4px 8px;font-size:13px;">
            <option value="">Tous les statuts</option>
            <option value="pre_reserved">Pré-réservé</option>
            <option value="confirmed">Confirmé</option>
          </select>
        </div>
      </div>
      <div class="calendar-nav" style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
        <button class="btn btn-secondary btn-sm" data-action="prev">◀</button>
        <h2 data-month-label style="margin:0;min-width:180px;text-align:center;font-size:var(--font-size-base);"></h2>
        <button class="btn btn-secondary btn-sm" data-action="next">▶</button>
        <button class="btn btn-secondary btn-sm" data-action="today">Aujourd'hui</button>
      </div>
      <div data-planning style="flex:1;min-height:0;"></div>
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
    this._bindMonthSwipe(this.element.querySelector('.calendar-nav'));

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
