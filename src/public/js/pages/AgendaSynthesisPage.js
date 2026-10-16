import { authStore } from '../stores/auth.js';
import { getAgendaSynthesis } from '../services/agendaApi.js';

const DAY_LABELS_SHORT = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim'];
const DAY_LABELS_LONG = ['dimanche', 'lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi'];
const MONTH_LABELS = [
  'Janvier', 'Fevrier', 'Mars', 'Avril', 'Mai', 'Juin',
  'Juillet', 'Aout', 'Septembre', 'Octobre', 'Novembre', 'Decembre',
];

const VIEW_LABELS = { week: 'Semaine', month: 'Mois' };

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;',
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

const METRICS = [
  { key: 'person_count', totalKey: 'total_persons', grandKey: 'grand_total_persons', label: 'Personnes presentes', color: 'persons', showCapacity: false },
  { key: 'meal_count', totalKey: 'total_meals', grandKey: 'grand_total_meals', label: 'Repas', color: 'meals', showCapacity: false },
  { key: 'workstation_count', totalKey: 'total_workstations', grandKey: 'grand_total_workstations', label: 'Postes de travail', color: 'workstations', showCapacity: true },
];

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
    const isMonth = this.view === 'month';
    const dates = isMonth ? _monthDates(this.anchor) : weekdaysOfAnchor(this.anchor);
    const today = toISODate(new Date());
    const dayByIso = new Map((data.days || []).map(day => [day.date, day]));
    const rooms = this._collectRooms(data.days || []);

    this.element.innerHTML = `
      <div class="page-header agenda-header">
        <div class="page-header-left">
          <h1>Synthese agenda</h1>
          <p class="page-subtitle">Personnes / repas / postes par bureau.</p>
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

      ${rooms.length === 0 ? this._noRoomsHtml() : METRICS.map(metric => `
        <section class="card agenda-card" aria-label="${escapeHtml(metric.label)}">
          <header class="agenda-section-header">
            <h2>${escapeHtml(metric.label)}</h2>
          </header>
          <div class="card-body agenda-section-body" style="padding:0;overflow-x:auto;">
            <table class="agenda-table agenda-table--synthesis ${isMonth ? 'agenda-table--synthesis-month' : ''}" role="grid">
              ${this._tableHead(dates, today, metric.showCapacity, isMonth)}
              ${this._tableBody(dates, rooms, dayByIso, metric, isMonth)}
              ${this._tableFoot(dates, data, metric)}
            </table>
          </div>
        </section>
      `).join('')}
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

  _tableHead(dates, today, showCapacity, isMonth) {
    return `
      <thead>
        <tr>
          <th class="agenda-synthesis-corner" rowspan="2" scope="col">Local</th>
          ${showCapacity ? '<th class="agenda-synthesis-capacity-head" rowspan="2" scope="col">Capacite</th>' : ''}
          ${dates.map((iso, di) => {
            const d = parseISODate(iso);
            const weekStart = isMonth && di % 5 === 0 && di > 0 ? ' agenda-week-start' : '';
            return `<th class="agenda-synthesis-day-head${weekStart} ${iso === today ? 'is-today' : ''} ${di === 0 ? 'agenda-day-first' : ''} ${di === dates.length - 1 ? 'agenda-day-last' : ''}" scope="col" title="${escapeHtml(formatDayLabel(iso))}">
              <span class="agenda-day-name">${DAY_LABELS_SHORT[d.getDay() === 0 ? 6 : d.getDay() - 1]}</span>
              <span class="agenda-day-num">${d.getDate()}</span>
            </th>`;
          }).join('')}
          <th class="agenda-synthesis-total-head" rowspan="2" scope="col">Total</th>
        </tr>
      </thead>`;
  }

  _tableBody(dates, rooms, dayByIso, metric, isMonth) {
    const showCapacity = metric.showCapacity;
    return `
      <tbody>
        ${rooms.map(room => {
          let rowTotal = 0;
          const cells = dates.map((iso, di) => {
            const day = dayByIso.get(iso);
            const roomData = day?.rooms?.find(r => r.room_id === room.id);
            const value = roomData?.[metric.key] ?? 0;
            const capacity = room.capacity || 0;
            rowTotal += value;
            const isOver = showCapacity && value > capacity;
            const pct = capacity ? Math.round((value / capacity) * 100) : 0;
            const weekStart = isMonth && di % 5 === 0 && di > 0 ? ' agenda-week-start' : '';
            return `<td class="agenda-synthesis-cell agenda-synthesis-cell--${metric.color}${weekStart} ${isOver ? 'over-capacity' : ''}" title="${showCapacity ? `${value} / ${capacity} (${pct}%)` : `${value} ${metric.unit || ''}`}">${value}</td>`;
          }).join('');
          return `
            <tr>
              <td class="agenda-synthesis-room-name" title="${escapeHtml(room.building_name || '')}">${escapeHtml(room.name)}</td>
              ${showCapacity ? `<td class="agenda-synthesis-capacity">${room.capacity}</td>` : ''}
              ${cells}
              <td class="agenda-synthesis-total agenda-synthesis-total--${metric.color}">${rowTotal}</td>
            </tr>`;
        }).join('')}
      </tbody>`;
  }

  _tableFoot(dates, data, metric) {
    const dayTotals = dates.map(iso => {
      const day = data.days?.find(d => d.date === iso);
      return day?.[metric.totalKey] ?? 0;
    });

    return `
      <tfoot>
        <tr class="agenda-synthesis-grand-total">
          <th class="agenda-synthesis-corner" colspan="${metric.showCapacity ? 2 : 1}" scope="row">Total general</th>
          ${dayTotals.map(v => `<td class="agenda-synthesis-total agenda-synthesis-total--${metric.color}">${v}</td>`).join('')}
          <th class="agenda-synthesis-grand-total-cell agenda-synthesis-total--${metric.color}">${data[metric.grandKey] ?? 0}</th>
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
