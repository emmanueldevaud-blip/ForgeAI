import { authStore } from '../stores/auth.js';
import { getAgendaSynthesis } from '../services/agendaApi.js';

const DAY_LABELS_SHORT = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim'];
const DAY_LABELS_LONG = ['dimanche', 'lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi'];
const MONTH_LABELS = [
  'Janvier', 'Fevrier', 'Mars', 'Avril', 'Mai', 'Juin',
  'Juillet', 'Aout', 'Septembre', 'Octobre', 'Novembre', 'Decembre',
];

const VIEW_LABELS = {
  week: 'Semaine',
  month: 'Mois',
};

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, char => ({
    '&': '&', '<': '<', '>': '>', "'": ''', '"': '"',
  }[char]));
}

function toISODate(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function parseISODate(value) {
  const [y, m, d] = String(value).split('-').map(Number);
  return new Date(y, m - 1, d);
}

function addDays(date, days) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function startOfWeek(date) {
  const next = new Date(date);
  const weekday = next.getDay() === 0 ? 6 : next.getDay() - 1;
  next.setDate(next.getDate() - weekday);
  return next;
}

function startOfMonth(date) {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function formatDayLabel(iso) {
  const date = parseISODate(iso);
  return `${DAY_LABELS_LONG[date.getDay()]} ${date.getDate()} ${MONTH_LABELS[date.getMonth()].toLowerCase()} ${date.getFullYear()}`;
}

function weekdaysOfAnchor(anchor) {
  const monday = startOfWeek(anchor);
  const days = [];
  for (let i = 0; i < 5; i += 1) days.push(toISODate(addDays(monday, i)));
  return days;
}

function _monthDates(anchor) {
  const start = startOfMonth(anchor);
  const end = new Date(start.getFullYear(), start.getMonth() + 1, 0);
  const days = [];
  for (let d = new Date(start); d <= end; d = addDays(d, 1)) {
    const dow = d.getDay();
    if (dow >= 1 && dow <= 5) days.push(toISODate(d));
  }
  return days;
}

export class AgendaSynthesisPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.view = 'week';
    this.anchor = new Date();
    this.data = null;
    this.error = null;
    this._authUnsubscribe = null;
  }

  async initialize() {
    await this.loadSynthesis();
    if (!this._authUnsubscribe) {
      this._authUnsubscribe = authStore.subscribe(() => this.renderState());
    }
  }

  async loadSynthesis() {
    this.error = null;
    try {
      this.data = await getAgendaSynthesis(this.view, toISODate(this.anchor));
    } catch (error) {
      this.error = error;
    }
  }

  render() {
    this.element = document.createElement('div');
    this.element.className = 'page-content agenda-page';
    this.renderState();
    return this.element;
  }

  destroy() {
    this._authUnsubscribe?.();
    this._authUnsubscribe = null;
    if (this.element) this.element.remove();
    this.element = null;
  }

  renderState() {
    if (!this.element) return;

    if (this.error) {
      this.element.innerHTML = `
        <div class="page-header">
          <div class="page-header-left"><h1>Synthese agenda</h1><p class="page-subtitle">Compteurs par bureau.</p></div>
        </div>
        <div class="card" role="alert">
          <div class="card-body agenda-empty">
            <h2>Impossible de charger la synthese</h2>
            <p>${escapeHtml(this.error.message || 'Erreur inconnue')}</p>
            <button class="btn btn-primary" data-action="retry">Reessayer</button>
          </div>
        </div>`;
      this._bindCommon();
      return;
    }

    const data = this.data || {};
    const days = data.days || [];
    const isMonth = this.view === 'month';
    const dates = isMonth ? _monthDates(this.anchor) : weekdaysOfAnchor(this.anchor);
    const today = toISODate(new Date());

    const dayByIso = new Map(days.map(day => [day.date, day]));
    const rooms = this._collectRooms(days);

    this.element.innerHTML = `
      <div class="page-header agenda-header">
        <div class="page-header-left">
          <h1>Synthese agenda</h1>
          <p class="page-subtitle">Compteurs personnes / repas / postes par bureau.</p>
        </div>
        <div class="page-header-right agenda-toolbar">
          <div class="agenda-nav" role="group" aria-label="Navigation">
            <button class="btn btn-secondary btn-sm" data-nav="prev" aria-label="Periode precedente">&lsaquo;</button>
            <button class="btn btn-secondary btn-sm" data-nav="today">Aujourd'hui</button>
            <button class="btn btn-secondary btn-sm" data-nav="next" aria-label="Periode suivante">&rsaquo;</button>
          </div>
          <span class="agenda-period-label" aria-live="polite">${escapeHtml(this._periodLabel(dates))}</span>
          <div class="agenda-views" role="group" aria-label="Vue">
            ${Object.entries(VIEW_LABELS).map(([value, label]) => `
              <button class="btn btn-sm ${this.view === value ? 'btn-primary' : 'btn-secondary'}" data-view="${value}" aria-pressed="${this.view === value}">${label}</button>
            `).join('')}
          </div>
        </div>
      </div>

      ${rooms.length === 0 ? this._noRoomsHtml() : `
        <div class="agenda-scroll">
          <table class="agenda-table agenda-table--synthesis ${isMonth ? 'agenda-table--synthesis-month' : ''}" role="grid" aria-label="Synthese des presences par bureau">
            ${this._tableHead(dates, today, rooms)}
            ${this._tableBody(dates, today, rooms, dayByIso)}
            ${this._tableFoot(dates, rooms, data)}
          </table>
        </div>
      `}

      <div class="agenda-synthesis-summary">
        <div class="summary-card">
          <span class="summary-label">Total personnes</span>
          <span class="summary-value">${data.grand_total_persons ?? 0}</span>
        </div>
        <div class="summary-card">
          <span class="summary-label">Total repas</span>
          <span class="summary-value">${data.grand_total_meals ?? 0}</span>
        </div>
        <div class="summary-card">
          <span class="summary-label">Total postes</span>
          <span class="summary-value">${data.grand_total_workstations ?? 0}</span>
        </div>
      </div>
    `;

    this._bindCommon();
  }

  _collectRooms(days) {
    const roomMap = new Map();
    for (const day of days) {
      for (const room of day.rooms || []) {
        if (!roomMap.has(room.room_id)) {
          roomMap.set(room.room_id, {
            id: room.room_id,
            name: room.room_name,
            building_name: room.building_name,
            capacity: room.capacity,
          });
        }
      }
    }
    return [...roomMap.values()].sort((a, b) => {
      const order = ['CEBAZAT', 'RIOM', 'PUTEAUX'];
      const aIdx = order.findIndex(o => a.name?.toUpperCase().includes(o) || a.building_name?.toUpperCase().includes(o));
      const bIdx = order.findIndex(o => b.name?.toUpperCase().includes(o) || b.building_name?.toUpperCase().includes(o));
      if (aIdx !== -1 && bIdx !== -1) return aIdx - bIdx;
      if (aIdx !== -1) return -1;
      if (bIdx !== -1) return 1;
      return (a.name || '').localeCompare(b.name || '');
    });
  }

  _periodLabel(dates) {
    if (!dates.length) return '';
    const start = parseISODate(dates[0]);
    const end = parseISODate(dates[dates.length - 1]);
    if (this.view === 'week') {
      return `Semaine du ${start.getDate()} ${MONTH_LABELS[start.getMonth()].toLowerCase()} au ${end.getDate()} ${MONTH_LABELS[end.getMonth()].toLowerCase()} ${end.getFullYear()}`;
    }
    return `${MONTH_LABELS[start.getMonth()]} ${start.getFullYear()}`;
  }

  _noRoomsHtml() {
    return `
      <div class="card">
        <div class="card-body agenda-empty">
          <h2>Aucun local Bureau</h2>
          <p>Definissez un local avec un type d'utilisation "Bureau" (ou "Bureaux") dans le module Batiments pour l'afficher ici.</p>
        </div>
      </div>`;
  }

  _tableHead(dates, today, rooms) {
    return `
      <thead>
        <tr>
          <th class="agenda-synthesis-corner" rowspan="2" scope="col" colspan="2">
            <span>Local</span>
            <span class="agenda-synthesis-capacity-label">Capacite</span>
          </th>
          ${dates.map((iso, di) => `
            <th class="agenda-synthesis-day-head ${iso === today ? 'is-today' : ''} ${di === 0 ? 'agenda-day-first' : ''} ${di === dates.length - 1 ? 'agenda-day-last' : ''}" colspan="3" scope="colgroup" title="${escapeHtml(formatDayLabel(iso))}">
              <span class="agenda-day-name">${DAY_LABELS_SHORT[parseISODate(iso).getDay() === 0 ? 6 : parseISODate(iso).getDay() - 1]}</span>
              <span class="agenda-day-num">${parseISODate(iso).getDate()}</span>
            </th>
          `).join('')}
          <th class="agenda-synthesis-total-head" rowspan="2" scope="col" colspan="3">Total</th>
        </tr>
        <tr>
          ${dates.map(() => `
            <th class="agenda-synthesis-subhead" scope="col">Pers.</th>
            <th class="agenda-synthesis-subhead" scope="col">Repas</th>
            <th class="agenda-synthesis-subhead" scope="col">Postes</th>
          `).join('')}
          <th class="agenda-synthesis-subhead" scope="col">Pers.</th>
          <th class="agenda-synthesis-subhead" scope="col">Repas</th>
          <th class="agenda-synthesis-subhead" scope="col">Postes</th>
        </tr>
      </thead>`;
  }

  _tableBody(dates, today, rooms, dayByIso) {
    return `
      <tbody>
        ${rooms.map(room => {
          let totalPersons = 0;
          let totalMeals = 0;
          let totalWorkstations = 0;
          const cells = dates.map(iso => {
            const day = dayByIso.get(iso);
            const roomData = day?.rooms?.find(r => r.room_id === room.id);
            const persons = roomData?.person_count ?? 0;
            const meals = roomData?.meal_count ?? 0;
            const workstations = roomData?.workstation_count ?? 0;
            const capacity = room.capacity || 0;
            totalPersons += persons;
            totalMeals += meals;
            totalWorkstations += workstations;
            const personPct = capacity ? Math.round((persons / capacity) * 100) : 0;
            const workstationPct = capacity ? Math.round((workstations / capacity) * 100) : 0;
            return `
              <td class="agenda-synthesis-cell agenda-synthesis-cell--persons ${persons > capacity ? 'over-capacity' : ''}" title="${persons} / ${capacity} (${personPct}%)">${persons}</td>
              <td class="agenda-synthesis-cell agenda-synthesis-cell--meals" title="${meals} repas">${meals}</td>
              <td class="agenda-synthesis-cell agenda-synthesis-cell--workstations ${workstations > capacity ? 'over-capacity' : ''}" title="${workstations} / ${capacity} (${workstationPct}%)">${workstations}</td>
            `;
          }).join('');
          return `
            <tr>
              <td class="agenda-synthesis-room-name" title="${escapeHtml(room.building_name || '')}">${escapeHtml(room.name)}</td>
              <td class="agenda-synthesis-capacity">${room.capacity}</td>
              ${cells}
              <td class="agenda-synthesis-total agenda-synthesis-total--persons">${totalPersons}</td>
              <td class="agenda-synthesis-total agenda-synthesis-total--meals">${totalMeals}</td>
              <td class="agenda-synthesis-total agenda-synthesis-total--workstations">${totalWorkstations}</td>
            </tr>`;
        }).join('')}
      </tbody>`;
  }

  _tableFoot(dates, rooms, data) {
    const dayTotals = dates.map(iso => {
      const day = data.days?.find(d => d.date === iso);
      return day ? {
        persons: day.total_persons ?? 0,
        meals: day.total_meals ?? 0,
        workstations: day.total_workstations ?? 0,
      } : { persons: 0, meals: 0, workstations: 0 };
    });

    return `
      <tfoot>
        <tr class="agenda-synthesis-grand-total">
          <th class="agenda-synthesis-corner" colspan="2" scope="row">Total general</th>
          ${dayTotals.map(t => `
            <td class="agenda-synthesis-total agenda-synthesis-total--persons">${t.persons}</td>
            <td class="agenda-synthesis-total agenda-synthesis-total--meals">${t.meals}</td>
            <td class="agenda-synthesis-total agenda-synthesis-total--workstations">${t.workstations}</td>
          `).join('')}
          <th class="agenda-synthesis-grand-total-cell agenda-synthesis-total--persons">${data.grand_total_persons ?? 0}</th>
          <th class="agenda-synthesis-grand-total-cell agenda-synthesis-total--meals">${data.grand_total_meals ?? 0}</th>
          <th class="agenda-synthesis-grand-total-cell agenda-synthesis-total--workstations">${data.grand_total_workstations ?? 0}</th>
        </tr>
      </tfoot>`;
  }

  _bindCommon() {
    this.element.querySelector('[data-action="retry"]')?.addEventListener('click', () => this.loadSynthesis().then(() => this.renderState()));
    this.element.querySelector('[data-nav="prev"]')?.addEventListener('click', () => {
      const days = this.view === 'week' ? 7 : (this.anchor.getMonth() === 11 ? 31 : new Date(this.anchor.getFullYear(), this.anchor.getMonth() + 1, 0).getDate());
      this.anchor = addDays(this.anchor, -days);
      this.loadSynthesis().then(() => this.renderState());
    });
    this.element.querySelector('[data-nav="next"]')?.addEventListener('click', () => {
      const days = this.view === 'week' ? 7 : (this.anchor.getMonth() === 11 ? 31 : new Date(this.anchor.getFullYear(), this.anchor.getMonth() + 1, 0).getDate());
      this.anchor = addDays(this.anchor, days);
      this.loadSynthesis().then(() => this.renderState());
    });
    this.element.querySelector('[data-nav="today"]')?.addEventListener('click', () => {
      this.anchor = new Date();
      this.loadSynthesis().then(() => this.renderState());
    });
    this.element.querySelectorAll('[data-view]').forEach(btn => {
      btn.addEventListener('click', () => {
        this.view = btn.dataset.view;
        this.loadSynthesis().then(() => this.renderState());
      });
    });
  }
}