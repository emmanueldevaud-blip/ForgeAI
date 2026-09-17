import { authStore } from '../stores/auth.js';
import { getPlanning, listHousings } from '../services/housingApi.js';

function formatDateISO(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function formatDayShort(d) {
  return d.toLocaleDateString('fr-FR', { day: 'numeric' });
}

const DAY_LABELS = ['Dim', 'Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam'];
const MONTH_NAMES = ['Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin', 'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'];

const STATUS_COLORS = {
  occupied: '#3b82f6',
  reserved: '#f59e0b',
  maintenance: '#6b7280',
};

export class HousingPlanningPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.currentDate = new Date();
    this.housings = [];
    this.planningData = [];
    this.days = [];
  }

  async initialize() {}

  async loadData() {
    try {
      const resp = await listHousings({ page_size: 1000, is_active: true });
      this.housings = resp.items || [];
    } catch (e) {
      console.error('Erreur chargement logements:', e);
      this.housings = [];
    }
    await this._loadPlanning();
    this._renderPlanning();
  }

  async _loadPlanning() {
    const year = this.currentDate.getFullYear();
    const month = this.currentDate.getMonth();
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);

    this.days = [];
    for (let d = new Date(firstDay); d <= lastDay; d.setDate(d.getDate() + 1)) {
      this.days.push(new Date(d));
    }

    const startDate = formatDateISO(firstDay);
    const endDate = formatDateISO(lastDay);

    try {
      const resp = await getPlanning(startDate, endDate);
      this.planningData = resp.items || resp || [];
    } catch (e) {
      console.error('Erreur chargement planning:', e);
      this.planningData = [];
    }
  }

  _renderPlanning() {
    if (!this.element) return;
    const container = this.element.querySelector('[data-planning]');
    if (!container) return;

    const year = this.currentDate.getFullYear();
    const month = this.currentDate.getMonth();
    const monthLabel = this.element.querySelector('[data-month-label]');
    if (monthLabel) monthLabel.textContent = `${MONTH_NAMES[month]} ${year}`;

    let html = '<div class="planning-grid">';

    html += '<table class="planning-table"><thead><tr>';
    html += '<th class="planning-housing-col">Logement</th>';
    this.days.forEach(day => {
      const dayNum = day.getDay();
      const isWeekend = dayNum === 0 || dayNum === 6;
      const isToday = formatDateISO(day) === formatDateISO(new Date());
      const cls = ['planning-day-col'];
      if (isWeekend) cls.push('planning-weekend');
      if (isToday) cls.push('planning-today');
      html += `<th class="${cls.join(' ')}"><div class="planning-day-header"><span class="planning-day-name">${DAY_LABELS[dayNum]}</span><span class="planning-day-num">${formatDayShort(day)}</span></div></th>`;
    });
    html += '</tr></thead><tbody>';

    this.housings.forEach(housing => {
      html += '<tr>';
      html += `<td class="planning-housing-name" title="${housing.name || ''}">${housing.name || '-'}</td>`;

      this.days.forEach(day => {
        const dateStr = formatDateISO(day);
        const entries = this._getEntriesForDate(housing.id, dateStr);
        html += '<td class="planning-cell">';
        entries.forEach(entry => {
          const color = STATUS_COLORS[entry.status] || '#6b7280';
          const bgColor = color + '22';
          html += `<span class="planning-entry" style="background:${bgColor};border-left:3px solid ${color}" title="${entry.occupant || ''} (${entry.status})">`;
          if (entry.is_arrival) html += '<span class="planning-marker">&#9654;</span>';
          if (entry.is_departure) html += '<span class="planning-marker">&#9664;</span>';
          html += `<span class="planning-entry-text">${entry.occupant || ''}</span>`;
          html += '</span>';
        });
        html += '</td>';
      });

      html += '</tr>';
    });

    if (this.housings.length === 0) {
      html += `<tr><td colspan="${this.days.length + 1}" style="text-align:center;padding:2rem;">Aucun logement trouvé</td></tr>`;
    }

    html += '</tbody></table></div>';
    container.innerHTML = html;
  }

  _getEntriesForDate(housingId, dateStr) {
    const entries = [];
    const data = Array.isArray(this.planningData) ? this.planningData : [];
    data.forEach(item => {
      if (item.housing_id !== housingId) return;
      const start = item.start_date || item.arrival_date;
      const end = item.end_date || item.departure_date;
      if (!start || !end) return;
      if (dateStr >= start && dateStr <= end) {
        entries.push({
          occupant: item.occupant_name || item.occupant?.last_name || '',
          status: item.status || 'occupied',
          is_arrival: dateStr === start,
          is_departure: dateStr === end,
        });
      }
    });
    return entries;
  }

  render() {
    this.element = document.createElement('div');
    this.element.className = 'page-content';
    this.element.innerHTML = `
      <div class="page-header">
        <div class="page-header-left">
          <h1>Planning d'occupation</h1>
          <p class="page-subtitle">Vue mensuelle des occupations</p>
        </div>
      </div>
      <div class="calendar-nav">
        <button class="btn btn-secondary" data-action="prev-month">&larr; Précédent</button>
        <h2 data-month-label></h2>
        <button class="btn btn-secondary" data-action="next-month">Suivant &rarr;</button>
        <button class="btn btn-secondary" data-action="today">Aujourd'hui</button>
      </div>
      <div data-planning></div>
    `;

    this.element.querySelector('[data-action="prev-month"]')?.addEventListener('click', () => {
      this.currentDate.setMonth(this.currentDate.getMonth() - 1);
      this.loadData();
    });
    this.element.querySelector('[data-action="next-month"]')?.addEventListener('click', () => {
      this.currentDate.setMonth(this.currentDate.getMonth() + 1);
      this.loadData();
    });
    this.element.querySelector('[data-action="today"]')?.addEventListener('click', () => {
      this.currentDate = new Date();
      this.loadData();
    });

    return this.element;
  }

  destroy() {
    if (this.element) this.element.remove();
    this.element = null;
  }
}

export function createHousingPlanningPage(router) {
  return new HousingPlanningPage(router);
}
