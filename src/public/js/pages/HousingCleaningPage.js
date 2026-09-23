import { authStore } from '../stores/auth.js';
import { createCleaning, getPlanning, listHousings, updateCleaning } from '../services/housingApi.js';
import { HousingPlanningPage } from './HousingPlanningPage.js';

const DAY_NAMES = ['Dim', 'Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam'];
const MONTH_NAMES = ['Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin', 'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'];
const CLEANING_STATUSES = {
  not_planned: { label: 'Non planifié', color: '#ef4444' },
  planned: { label: 'Planifié', color: '#22c55e' },
  in_progress: { label: 'Planification en cours', color: '#f59e0b' },
};

function formatDate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function nextWeekdayAfter(value) {
  const date = new Date(`${value.slice(0, 10)}T00:00:00`);
  date.setDate(date.getDate() + 1);
  while (date.getDay() === 0 || date.getDay() === 6) date.setDate(date.getDate() + 1);
  return formatDate(date);
}

function addDays(date, count) {
  const result = new Date(date);
  result.setDate(result.getDate() + count);
  return result;
}

function statusInfo(status) {
  return CLEANING_STATUSES[status] || CLEANING_STATUSES.not_planned;
}

export class HousingCleaningPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.currentDate = new Date();
    this.viewMode = 'month';
    this.housings = [];
    this.entries = [];
    this._planningModal = null;
    this._authUnsubscribe = null;
  }

  async initialize() {}

  _getDateRange() {
    const date = this.currentDate;
    if (this.viewMode === 'day') return { startDate: new Date(date), endDate: new Date(date) };
    if (this.viewMode === 'week') {
      const startDate = addDays(date, -date.getDay());
      return { startDate, endDate: addDays(startDate, 6) };
    }
    return {
      startDate: new Date(date.getFullYear(), date.getMonth(), 1),
      endDate: new Date(date.getFullYear(), date.getMonth() + 1, 0),
    };
  }

  _getDays() {
    const { startDate, endDate } = this._getDateRange();
    const days = [];
    for (let date = new Date(startDate); date <= endDate; date.setDate(date.getDate() + 1)) days.push(new Date(date));
    return days;
  }

  async loadData() {
    const { startDate, endDate } = this._getDateRange();
    const queryStart = addDays(startDate, -7);
    try {
      const housingsResponse = await listHousings({ page_size: 1000, is_active: true });
      const response = await getPlanning(formatDate(queryStart), formatDate(endDate), this.viewMode, null, 'confirmed', true);
      this.housings = housingsResponse.items || [];
      this.entries = response.entries || [];
      this._renderGrid();
    } catch (error) {
      console.error('Erreur chargement planning ménage:', error);
      if (this.element) this.element.querySelector('[data-cleaning-planning]').innerHTML = '<p class="alert alert-danger">Impossible de charger le planning des ménages.</p>';
    }
  }

  _cleaningForEntry(entry) {
    const scheduledDate = entry.cleaning_scheduled_date || nextWeekdayAfter((entry.departure_date || '').slice(0, 10));
    return {
      ...entry,
      scheduledDate,
      cleaningState: entry.has_cleaning_planned ? (entry.cleaning_status || 'not_planned') : 'not_planned',
    };
  }

  _renderGrid() {
    const container = this.element?.querySelector('[data-cleaning-planning]');
    if (!container) return;
    const days = this._getDays();
    const { startDate, endDate } = this._getDateRange();
    const label = this.element.querySelector('[data-month-label]');
    if (this.viewMode === 'day') label.textContent = `${DAY_NAMES[this.currentDate.getDay()]} ${this.currentDate.getDate()} ${MONTH_NAMES[this.currentDate.getMonth()]} ${this.currentDate.getFullYear()}`;
    else if (this.viewMode === 'week') label.textContent = `${startDate.getDate()} — ${endDate.getDate()} ${MONTH_NAMES[endDate.getMonth()]} ${endDate.getFullYear()}`;
    else label.textContent = `${MONTH_NAMES[this.currentDate.getMonth()]} ${this.currentDate.getFullYear()}`;

    const entries = this.entries.map(entry => this._cleaningForEntry(entry));
    const byHousing = new Map();
    entries.forEach(entry => {
      if (!byHousing.has(entry.housing_id)) byHousing.set(entry.housing_id, []);
      byHousing.get(entry.housing_id).push(entry);
    });
    const roomRows = [];
    const groupedByBuilding = {};
    this.housings.forEach(housing => {
      const buildingName = (housing.building && housing.building.name) || 'Autre';
      if (!groupedByBuilding[buildingName]) groupedByBuilding[buildingName] = [];
      groupedByBuilding[buildingName].push(housing);
    });
    Object.keys(groupedByBuilding).sort().forEach(buildingName => {
      groupedByBuilding[buildingName].forEach(housing => {
        const housingEntries = byHousing.get(housing.id) || [];
        let roomNames = [];
        try { roomNames = JSON.parse(housing.room_names || '[]'); } catch { roomNames = []; }
        const roomCount = housing.nb_rooms || Math.max(1, ...housingEntries.map(entry => entry.room_index == null ? 0 : Number(entry.room_index) + 1));
        for (let roomIndex = 0; roomIndex < roomCount; roomIndex++) {
          const roomEntries = housingEntries.filter(entry => entry.room_index == null ? roomIndex === 0 : Number(entry.room_index) === roomIndex);
          roomRows.push({ housing, roomIndex, roomName: roomNames[roomIndex] || `Chambre ${roomIndex + 1}`, entries: roomEntries });
        }
      });
    });
    let html = '<div class="planning-container"><div class="planning-wrapper"><table class="planning-table"><thead><tr><th class="planning-housing-col"><span class="housing-col-header">Chambre</span></th>';
    days.forEach(day => {
      const weekend = day.getDay() === 0 || day.getDay() === 6;
      const today = formatDate(day) === formatDate(new Date());
      html += `<th class="planning-day-col${weekend ? ' planning-weekend' : ''}${today ? ' planning-today' : ''}"><div><span class="day-name">${DAY_NAMES[day.getDay()]}</span><span class="day-num">${day.getDate()}</span></div></th>`;
    });
    html += '</tr></thead><tbody>';

    roomRows.forEach(({ housing, roomName, entries: roomEntries }) => {
      const housingEntries = roomEntries;
      const name = housing.room?.name || housing.name || housing.room_name || 'Logement';
      html += `<tr><td class="planning-housing-cell"><span class="housing-name">${name}</span><span class="housing-code">${roomName}</span></td>`;
      let dayIndex = 0;
      while (dayIndex < days.length) {
        const day = days[dayIndex];
        const date = formatDate(day);
         const entry = housingEntries.find(item => item.scheduledDate === date && !item.cleaning_cancelled);
        if (entry) {
          const info = statusInfo(entry.cleaningState);
          const occupant = (entry.occupants || []).map(item => `${item.first_name || ''} ${item.last_name || ''}`.trim()).filter(Boolean).join(' / ');
          const title = entry.cleaningState === 'not_planned'
            ? `Ménage à planifier après le départ du ${entry.departure_date.slice(0, 10)}`
            : `${info.label}${occupant ? ` · ${occupant}` : ''}`;
           const draggable = entry.cleaningState === 'not_planned' && !entry.cleaning_cancelled;
           html += `<td class="planning-cell planning-cell--block cleaning-cell cleaning-cell--${entry.cleaningState}" data-cleaning-entry="${entry.occupancy_id}" title="${title}"><span class="cleaning-block"${draggable ? ' draggable="true" data-cleaning-drag' : ''} style="display:flex;flex-direction:column;gap:2px;min-height:38px;padding:5px 6px;border-radius:4px;background:${info.color};color:white;font-size:11px;font-weight:600;${draggable ? 'cursor:grab;' : ''}"><span>${info.label}</span>${occupant ? `<small style="font-weight:400;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${occupant}</small>` : ''}</span></td>`;
          dayIndex++;
          continue;
        }
        const occupancy = housingEntries.find(item => {
          const arrival = (item.arrival_date || '').slice(0, 10);
          const departure = (item.departure_date || '').slice(0, 10);
          return date >= arrival && date <= departure;
        });
        if (occupancy) {
          let span = 1;
          while (dayIndex + span < days.length) {
            const nextDate = formatDate(days[dayIndex + span]);
             const hasCleaning = housingEntries.some(item => item.scheduledDate === nextDate && !item.cleaning_cancelled);
            const nextArrival = (occupancy.arrival_date || '').slice(0, 10);
            const nextDeparture = (occupancy.departure_date || '').slice(0, 10);
            if (hasCleaning || nextDate < nextArrival || nextDate > nextDeparture) break;
            span++;
          }
          html += `<td class="planning-cell planning-cell--block" colspan="${span}" title="Réservation d'occupation"><span style="display:flex;align-items:center;min-height:38px;padding:5px 6px;border-radius:4px;background:#9ca3af;color:white;font-size:11px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">Occupé</span></td>`;
          dayIndex += span;
          continue;
        }
        html += `<td class="planning-cell" data-date="${date}" data-housing-id="${housing.id}"></td>`;
        dayIndex++;
      }
      html += '</tr>';
    });
    if (!roomRows.length) html += `<tr><td colspan="${days.length + 1}" style="text-align:center;padding:2rem;color:var(--text-secondary);">Aucun ménage ou départ à afficher.</td></tr>`;
    html += '</tbody></table></div></div>';
    container.innerHTML = html;
    this._focusToday(container);
    let draggedEntry = null;
    container.querySelectorAll('[data-cleaning-drag]').forEach(block => {
      block.addEventListener('dragstart', event => {
        const entry = entries.find(item => String(item.occupancy_id) === block.closest('[data-cleaning-entry]')?.dataset.cleaningEntry);
        if (!entry || entry.cleaningState !== 'not_planned' || entry.cleaning_cancelled) {
          event.preventDefault();
          return;
        }
        draggedEntry = entry;
        event.dataTransfer.effectAllowed = 'move';
        event.dataTransfer.setData('text/plain', String(entry.cleaning_id));
      });
      block.addEventListener('dragend', () => { draggedEntry = null; });
    });
    container.querySelectorAll('[data-date]').forEach(cell => {
      cell.addEventListener('dragover', event => {
        if (draggedEntry) {
          event.preventDefault();
          event.dataTransfer.dropEffect = 'move';
        }
      });
      cell.addEventListener('drop', async event => {
        event.preventDefault();
        if (!draggedEntry) return;
        const targetDate = cell.dataset.date;
        const departureDate = (draggedEntry.departure_date || '').slice(0, 10);
        if (targetDate <= departureDate) {
          alert('Le ménage doit être planifié après le départ de l’occupation.');
          return;
        }
        try {
          if (draggedEntry.cleaning_id) {
            await updateCleaning(draggedEntry.cleaning_id, { scheduled_date: targetDate });
          } else {
            await createCleaning({
              housing_id: draggedEntry.housing_id,
              occupancy_id: draggedEntry.occupancy_id,
              scheduled_date: targetDate,
              type: 'exit',
              status: 'not_planned',
              volunteers_needed: 1,
              invitation_status: 'not_sent',
            });
          }
          await this.loadData();
        } catch (error) {
          alert(error?.data?.detail || error?.message || 'Impossible de déplacer le ménage');
        } finally {
          draggedEntry = null;
        }
      });
    });
    container.querySelectorAll('[data-cleaning-entry]').forEach(cell => cell.addEventListener('click', () => {
      const entry = entries.find(item => String(item.occupancy_id) === cell.dataset.cleaningEntry);
      if (entry) this._showCleaningModal(entry);
    }));
  }

  _focusToday(container) {
    const today = container.querySelector('.planning-today');
    const wrapper = container.querySelector('.planning-wrapper');
    if (!today || !wrapper) return;
    requestAnimationFrame(() => {
      wrapper.scrollLeft = Math.max(0, today.offsetLeft - (wrapper.clientWidth - today.offsetWidth) / 2);
    });
  }

  render() {
    this.element = document.createElement('div');
    this.element.className = 'page-content';
    this.element.innerHTML = `
      <div class="page-header"><div class="page-header-left"><h1>Planning des ménages</h1><p class="page-subtitle">Ménages attendus après les réservations</p></div><div class="page-header-right"><div class="btn-group" style="display:flex;"><button class="btn btn-secondary btn-sm" data-view="day">Jour</button><button class="btn btn-secondary btn-sm" data-view="week">Semaine</button><button class="btn btn-secondary btn-sm active" data-view="month">Mois</button></div></div></div>
      <div class="calendar-nav" style="display:flex;align-items:center;gap:8px;margin-bottom:8px;"><button class="btn btn-secondary btn-sm" data-nav="prev">◀</button><h2 data-month-label style="margin:0;min-width:220px;text-align:center;font-size:var(--font-size-base);"></h2><button class="btn btn-secondary btn-sm" data-nav="next">▶</button><button class="btn btn-secondary btn-sm" data-nav="today">Aujourd’hui</button></div>
      <div style="display:flex;gap:14px;flex-wrap:wrap;margin-bottom:12px;font-size:12px;">${Object.entries(CLEANING_STATUSES).map(([key, value]) => `<span><i style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${value.color};margin-right:4px;"></i>${value.label}</span>`).join('')}</div>
      <div data-cleaning-planning style="flex:1;min-height:0;"></div>
    `;
    this.element.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', () => { this.viewMode = button.dataset.view; this.loadData(); }));
    this.element.querySelector('[data-nav="prev"]').addEventListener('click', () => { this._move(-1); this.loadData(); });
    this.element.querySelector('[data-nav="next"]').addEventListener('click', () => { this._move(1); this.loadData(); });
    this.element.querySelector('[data-nav="today"]').addEventListener('click', () => { this.currentDate = new Date(); this.loadData(); });
    this._bindMonthSwipe(this.element.querySelector('.calendar-nav'));
    this._authUnsubscribe = authStore.subscribe(() => {});
    return this.element;
  }

  _move(direction) {
    if (this.viewMode === 'day') this.currentDate.setDate(this.currentDate.getDate() + direction);
    else if (this.viewMode === 'week') this.currentDate.setDate(this.currentDate.getDate() + (direction * 7));
    else this.currentDate.setMonth(this.currentDate.getMonth() + direction);
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
      this._move(deltaX < 0 ? 1 : -1);
      this.loadData();
    }, { passive: true });
  }

  _showCleaningModal(entry) {
    if (!this._planningModal) {
      this._planningModal = new HousingPlanningPage(this.router);
      this._planningModal.loadData = async () => this.loadData();
    }
    this._planningModal.selectedEntry = entry;
    this._planningModal.housings = this.housings;
    this._planningModal._openModal(this._planningModal._buildCleaningModal(entry));
    this._planningModal._loadCleaningVolunteers(this._planningModal._currentModal, entry);
  }

  destroy() {
    this._authUnsubscribe?.();
    this._planningModal?._closeModal();
    this.element?.remove();
    this.element = null;
  }
}

export function createHousingCleaningPage(router) {
  return new HousingCleaningPage(router);
}
