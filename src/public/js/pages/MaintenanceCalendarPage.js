import { authStore } from '../stores/auth.js';
import { listPlans, listWorkOrders } from '../services/maintenanceApi.js';

function formatDate(d) { return d ? new Date(d).toLocaleDateString('fr-FR') : '-'; }

function getFrequencyLabel(f) {
  const labels = { daily: 'Quotidien', weekly: 'Hebdo', monthly: 'Mensuel', quarterly: 'Trimestriel', biannual: 'Semestriel', annual: 'Annuel', hours: 'Par heures' };
  return labels[f] || f;
}

function getPriorityColor(p) {
  return { low: '#10b981', medium: '#f59e0b', high: '#f97316', critical: '#ef4444' }[p] || '#6b7280';
}

function getStatusColor(s) {
  return { draft: '#6b7280', open: '#f59e0b', in_progress: '#3b82f6', completed: '#10b981', cancelled: '#ef4444' }[s] || '#6b7280';
}

function getStatusLabel(s) {
  return { draft: 'Brouillon', open: 'Ouvert', in_progress: 'En cours', completed: 'Clôturé', cancelled: 'Annulé' }[s] || s;
}

export class MaintenanceCalendarPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.currentDate = new Date();
    this.events = [];
  }

  async initialize() {}

  async loadData() {
    await this._loadEvents();
    this._renderCalendar();
  }

  async _loadEvents() {
    this.events = [];
    try {
      const plans = await listPlans({ page_size: 1000, is_active: true });
      (plans.items || []).forEach(p => {
        if (p.next_due_date) {
          this.events.push({
            date: p.next_due_date,
            title: p.name,
            type: 'preventive',
            equipment: p.equipment ? p.equipment.name : '',
            color: '#06b6d4',
          });
        }
      });
    } catch (e) { console.error('Erreur chargement plans:', e); }

    try {
      const wo = await listWorkOrders({ page_size: 1000, status: 'open,in_progress' });
      (wo.items || []).forEach(w => {
        if (w.planned_date) {
          this.events.push({
            date: w.planned_date,
            title: w.reference ? `${w.reference} - ${w.title}` : w.title,
            type: 'work_order',
            equipment: w.equipment ? w.equipment.name : '',
            priority: w.priority,
            color: getPriorityColor(w.priority),
          });
        }
      });
    } catch (e) { console.error('Erreur chargement OT:', e); }
  }

  _renderCalendar() {
    if (!this.element) return;
    const container = this.element.querySelector('[data-calendar]');
    if (!container) return;

    const year = this.currentDate.getFullYear();
    const month = this.currentDate.getMonth();
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    const startOffset = firstDay.getDay();
    const daysInMonth = lastDay.getDate();
    const monthNames = ['Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin', 'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'];

    const monthLabel = this.element.querySelector('[data-month-label]');
    if (monthLabel) monthLabel.textContent = `${monthNames[month]} ${year}`;

    let html = '<table class="calendar-table"><thead><tr>';
    ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim'].forEach(d => { html += `<th>${d}</th>`; });
    html += '</tr></thead><tbody><tr>';

    for (let i = 0; i < startOffset; i++) { html += '<td class="calendar-cell calendar-cell--empty"></td>'; }

    for (let day = 1; day <= daysInMonth; day++) {
      const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
      const dayEvents = this.events.filter(e => e.date === dateStr);
      const today = new Date();
      const isToday = today.getFullYear() === year && today.getMonth() === month && today.getDate() === day;

      html += `<td class="calendar-cell ${isToday ? 'calendar-cell--today' : ''}">`;
      html += `<div class="calendar-day">${day}</div>`;
      if (dayEvents.length > 0) {
        html += '<div class="calendar-events">';
        dayEvents.forEach(ev => {
          html += `<div class="calendar-event" style="border-left: 3px solid ${ev.color}" title="${ev.title}${ev.equipment ? ' (' + ev.equipment + ')' : ''}">${ev.title}</div>`;
        });
        html += '</div>';
      }
      html += '</td>';

      if ((startOffset + day) % 7 === 0 && day < daysInMonth) html += '</tr><tr>';
    }

    const endOffset = (startOffset + daysInMonth) % 7;
    if (endOffset > 0) {
      for (let i = endOffset; i < 7; i++) { html += '<td class="calendar-cell calendar-cell--empty"></td>'; }
    }
    html += '</tr></tbody></table>';
    container.innerHTML = html;
  }

  render() {
    this.element = document.createElement('div');
    this.element.className = 'page-content';
    this.element.innerHTML = `
      <div class="page-header">
        <div class="page-header-left">
          <h1>Calendrier de maintenance</h1>
          <p class="page-subtitle">Vue calendaire des interventions et maintenances préventives</p>
        </div>
      </div>
      <div class="calendar-nav">
        <button class="btn btn-secondary" data-action="prev-month">← Précédent</button>
        <h2 data-month-label></h2>
        <button class="btn btn-secondary" data-action="next-month">Suivant →</button>
        <button class="btn btn-secondary" data-action="today">Aujourd'hui</button>
      </div>
      <div data-calendar></div>
    `;

    this.element.querySelector('[data-action="prev-month"]')?.addEventListener('click', () => {
      this.currentDate.setMonth(this.currentDate.getMonth() - 1);
      this._renderCalendar();
    });
    this.element.querySelector('[data-action="next-month"]')?.addEventListener('click', () => {
      this.currentDate.setMonth(this.currentDate.getMonth() + 1);
      this._renderCalendar();
    });
    this.element.querySelector('[data-action="today"]')?.addEventListener('click', () => {
      this.currentDate = new Date();
      this._renderCalendar();
    });

    return this.element;
  }

  destroy() {
    if (this.element) this.element.remove();
    this.element = null;
  }
}

export function createMaintenanceCalendarPage(router) { return new MaintenanceCalendarPage(router); }
