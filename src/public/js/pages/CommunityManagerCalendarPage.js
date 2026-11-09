/**
 * Community Manager Calendar Page - Refonte
 * Calendrier éditorial mensuel/hebdomadaire, écran principal du CM.
 */
import { api } from '../services/api.js';
import { authStore } from '../stores/auth.js';
import {
  getMonthCalendar,
  getWeekCalendar,
  generateSuggestions,
  acceptSuggestion,
  refuseSuggestion,
  rescheduleSuggestion,
  getStudioDraft,
  publishStudioDraft,
  validateStudioDraft,
  regeneratePublicationContent,
} from '../services/sportApi.js?v=14';
import { createCommunityManagerStudioPage } from './CommunityManagerStudioPage.js?v=2';

const MONTHS = [
  'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
  'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre',
];
const WEEK_DAYS = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim'];

const CONTENT_TYPE_COLORS = {
  publication_sportive: '#2563eb', // bleu
  story_souvenir: '#7c3aed', // violet
  story_edito: '#0891b2', // cyan
  manuel: '#6b7280', // gris
};

const STATUS_COLORS = {
  brouillon: '#ef4444', // rouge
  pending: '#f59e0b', // orange
  accepted: '#3b82f6', // bleu
  refused: '#9ca3af', // gris
  planifié: '#10b981', // vert
  publié: '#059669', // vert foncé
  draft: '#ef4444',
  validated: '#3b82f6',
  shared: '#059669',
};

export class CommunityManagerCalendarPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.user = null;
    this.view = 'month'; // 'month' | 'week'
    this.currentDate = new Date();
    this.selectedEntry = null;
    this.studioPage = null;
    this.showStudio = false;
    this.loading = false;
    this.error = null;
    this.calendarData = {};
    this.weekData = {};
    this.canGenerate = false;
    this.canManage = false;
  }

  async initialize() {
    try {
      await authStore.loadCurrentUser();
    } catch (error) {
      console.error('Erreur chargement utilisateur:', error);
    }
    this.user = authStore.currentUser;
    this.canGenerate = !!authStore?.authenticated && authStore.hasPermission('community_manager.calendar_generate');
    this.canManage = !!authStore?.authenticated && authStore.hasPermission('community_manager.calendar_generate');
    await this._loadMonth();
  }

  _today() {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), now.getDate());
  }

  async _loadMonth() {
    const d = this.currentDate;
    this.loading = true;
    this.error = null;
    try {
      this.calendarData = await getMonthCalendar(d.getFullYear(), d.getMonth() + 1);
    } catch (error) {
      this.error = error?.data?.detail || error?.message || 'Erreur chargement calendrier';
      this.calendarData = {};
    } finally {
      this.loading = false;
    }
    this.render();
  }

  async _loadWeek() {
    const d = this.currentDate;
    // Calculer le lundi de la semaine courante
    const monday = new Date(d);
    monday.setDate(d.getDate() - d.getDay() + (d.getDay() === 0 ? -6 : 1));
    this.loading = true;
    this.error = null;
    try {
      this.weekData = await getWeekCalendar(monday.toISOString().split('T')[0]);
    } catch (error) {
      this.error = error?.data?.detail || error?.message || 'Erreur chargement semaine';
      this.weekData = {};
    } finally {
      this.loading = false;
    }
    this.render();
  }

  _prevMonth() {
    this.currentDate = new Date(this.currentDate.getFullYear(), this.currentDate.getMonth() - 1, 1);
    this._loadMonth();
  }

  _nextMonth() {
    this.currentDate = new Date(this.currentDate.getFullYear(), this.currentDate.getMonth() + 1, 1);
    this._loadMonth();
  }

  _prevWeek() {
    this.currentDate = new Date(this.currentDate.getFullYear(), this.currentDate.getMonth(), this.currentDate.getDate() - 7);
    this._loadWeek();
  }

  _nextWeek() {
    this.currentDate = new Date(this.currentDate.getFullYear(), this.currentDate.getMonth(), this.currentDate.getDate() + 7);
    this._loadWeek();
  }

  _todayBtn() {
    this.currentDate = this._today();
    if (this.view === 'month') this._loadMonth();
    else this._loadWeek();
  }

  async _generateSuggestions() {
    if (!this.canGenerate) return;
    try {
      await generateSuggestions();
      if (this.view === 'month') this._loadMonth();
      else this._loadWeek();
    } catch (error) {
      this.error = error?.data?.detail || error?.message || 'Erreur génération suggestions';
      this.render();
    }
  }

  async _acceptSuggestion(entryId) {
    try {
      const res = await acceptSuggestion(entryId);
      this.selectedEntry = null;
      if (this.view === 'month') this._loadMonth();
      else this._loadWeek();
      this._openStudio(res.pub_id || entryId);
    } catch (error) {
      this.error = error?.data?.detail || error?.message || 'Erreur acceptation';
      this.render();
    }
  }

  async _refuseSuggestion(entryId) {
    try {
      await refuseSuggestion(entryId);
      this.selectedEntry = null;
      if (this.view === 'month') this._loadMonth();
      else this._loadWeek();
    } catch (error) {
      this.error = error?.data?.detail || error?.message || 'Erreur refus';
      this.render();
    }
  }

  async _rescheduleSuggestion(entryId, newDateStr) {
    try {
      await rescheduleSuggestion(entryId, newDateStr);
      if (this.view === 'month') this._loadMonth();
      else this._loadWeek();
    } catch (error) {
      this.error = error?.data?.detail || error?.message || 'Erreur report';
      this.render();
    }
  }

  _openStudio(entryId) {
    this.selectedEntry = entryId;
    this.showStudio = true;
    this.studioPage = createCommunityManagerStudioPage(this.router, entryId, null, () => {
      this.showStudio = false;
      this.studioPage = null;
      this.selectedEntry = null;
      this.render();
    });
    this.studioPage.initialize().catch(() => {});
    this.render();
  }

  render() {
    this.element = document.createElement('div');
    this.element.className = 'page-content';

    if (this.showStudio && this.studioPage) {
      this.element.appendChild(this.studioPage.render());
      return this.element;
    }

    const now = this._today();
    const isCurrentMonth =
      this.currentDate.getFullYear() === now.getFullYear() &&
      this.currentDate.getMonth() === now.getMonth();

    const viewBtn = (label, value, active) => `
      <button class="view-btn ${active ? 'view-btn--active' : ''}" data-view="${value}">${label}</button>
    `;

    this.element.innerHTML = `
      <div class="page-header">
        <div>
          <h1>Calendrier éditorial</h1>
          <p class="page-subtitle">Publications sportives et suggestions de stories</p>
        </div>
        <div class="page-header-actions">
          ${this.canGenerate ? `<button class="btn btn-secondary" data-action="generate-suggestions">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
            Générer suggestions
          </button>` : ''}
          ${viewBtn('Mois', 'month', this.view === 'month')}
          ${viewBtn('Semaine', 'week', this.view === 'week')}
          <button class="btn btn-secondary" data-action="today">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
            </svg>
            Aujourd'hui
          </button>
        </div>
      </div>

      ${this.error ? `<div class="alert alert-error">${this.error}</div>` : ''}

      <div class="calendar-nav">
        <button class="btn btn-secondary" data-action="prev"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 18 9 12 15 6"/></svg></button>
        <div class="calendar-title">
          ${this.view === 'month'
            ? `${MONTHS[this.currentDate.getMonth()]} ${this.currentDate.getFullYear()}`
            : `Semaine du ${this.weekData.monday || ''} au ${this.weekData.sunday || ''}`}
        </div>
        <button class="btn btn-secondary" data-action="next"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg></button>
        <button class="btn btn-secondary" data-action="today">Aujourd'hui</button>
      </div>

      <div class="calendar-container">
        ${this.view === 'month' ? this._renderMonthGrid() : this._renderWeekGrid()}
      </div>

      ${this.loading ? `<div class="loading">Chargement…</div>` : ''}
    `;

    this._bindEvents();
    return this.element;
  }

  _renderMonthGrid() {
    const year = this.currentDate.getFullYear();
    const month = this.currentDate.getMonth();
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    const start = new Date(firstDay);
    start.setDate(firstDay.getDate() - firstDay.getDay() + (firstDay.getDay() === 0 ? -6 : 1));

    const days = [];
    let current = new Date(start);
    while (current <= lastDay || current.getDay() !== 1) {
      days.push(new Date(current));
      current = new Date(current.getFullYear(), current.getMonth(), current.getDate() + 1);
      if (current.getDay() === 1 && current > lastDay) break;
    }

    let html = '<table class="cal-month"><thead><tr>';
    for (const wd of WEEK_DAYS) html += `<th>${wd}</th>`;
    html += '</tr></thead><tbody>';

    for (let i = 0; i < days.length; i += 7) {
      const week = days.slice(i, i + 7);
      html += '<tr>';
      for (const day of week) {
        const isToday = day.toDateString() === this._today().toDateString();
        const isOtherMonth = day.getMonth() !== month;
        const dayKey = day.toISOString().split('T')[0];
        const entries = this.calendarData.days?.[dayKey] || [];
        const entriesHtml = entries.map(e => this._renderMonthEntry(e)).join('');
        html += `
          <td class="cal-day ${isToday ? 'cal-day--today' : ''} ${isOtherMonth ? 'cal-day--other' : ''}" data-day="${dayKey}">
            <div class="cal-day-number">${day.getDate()}</div>
            <div class="cal-day-entries">${entriesHtml}</div>
            ${entries.length > 3 ? `<div class="cal-day-more">+${entries.length - 3}</div>` : ''}
          </td>
        `;
      }
      html += '</tr>';
    }
    html += '</tbody></table>';
    return html;
  }

  _renderMonthEntry(entry) {
    const color = CONTENT_TYPE_COLORS[entry.content_type] || '#6b7280';
    const statusColor = STATUS_COLORS[entry.status] || '#6b7280';
    const isSuggestion = entry.source === 'suggestion';
    const hasPub = !!entry.pub_id;
    return `
      <div class="cal-entry" data-entry-id="${entry.id}" data-entry-pub-id="${entry.pub_id || ''}"
           style="--color: ${color}; --status-color: ${statusColor};">
        <div class="cal-entry-dot" style="background: var(--color)"></div>
        <div class="cal-entry-title">${this._escape(entry.topic || '')}</div>
        ${isSuggestion ? `
          <div class="cal-entry-actions">
            <button class="cal-entry-btn cal-entry-btn--accept" data-action="accept-suggestion" data-entry-id="${entry.id}" title="Accepter">✓</button>
            <button class="cal-entry-btn cal-entry-btn--refuse" data-action="refuse-suggestion" data-entry-id="${entry.id}" title="Refuser">✗</button>
          </div>` : ''}
        <div class="cal-entry-status" style="color: var(--status-color);">${entry.status}</div>
      </div>
    `;
  }

  _renderWeekGrid() {
    const days = [];
    const monday = this.weekData.monday ? new Date(this.weekData.monday) : this.currentDate;
    for (let i = 0; i < 7; i++) {
      days.push(new Date(monday.getFullYear(), monday.getMonth(), monday.getDate() + i));
    }

    let html = '<table class="cal-week"><thead><tr>';
    for (const day of days) {
      const isToday = day.toDateString() === this._today().toDateString();
      const dayKey = day.toISOString().split('T')[0];
      html += `<th class="${isToday ? 'cal-week-day--today' : ''}">${WEEK_DAYS[day.getDay()]}<br>${day.getDate()}</th>`;
    }
    html += '</tr></thead><tbody><tr>';
    for (const day of days) {
      const dayKey = day.toISOString().split('T')[0];
      const entries = this.weekData.days?.[dayKey] || [];
      const entriesHtml = entries.map(e => this._renderWeekEntry(e)).join('');
      html += `<td class="cal-week-day">${entriesHtml}</td>`;
    }
    html += '</tr></tbody></table>';
    return html;
  }

  _renderWeekEntry(entry) {
    const color = CONTENT_TYPE_COLORS[entry.content_type] || '#6b7280';
    const statusColor = STATUS_COLORS[entry.status] || '#6b7280';
    return `
      <div class="cal-entry" data-entry-id="${entry.id}" data-entry-pub-id="${entry.pub_id || ''}"
           style="--color: ${color}; --status-color: ${statusColor};">
        <div class="cal-entry-dot" style="background: var(--color)"></div>
        <div class="cal-entry-title">${this._escape(entry.topic || '')}</div>
        <div class="cal-entry-status" style="color: var(--status-color);">${entry.status}</div>
      </div>
    `;
  }

  _escape(text) {
    return text.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  _bindEvents() {
    // Navigation
    this.element.querySelectorAll('[data-action]').forEach(btn => {
      btn.addEventListener('click', () => {
        const action = btn.dataset.action;
        if (action === 'prev') { this.view === 'month' ? this._prevMonth() : this._prevWeek(); }
        else if (action === 'next') { this.view === 'month' ? this._nextMonth() : this._nextWeek(); }
        else if (action === 'today') { this._todayBtn(); }
        else if (action === 'generate-suggestions') { this._generateSuggestions(); }
      });
    });

    // Vue
    this.element.querySelectorAll('[data-view]').forEach(btn => {
      btn.addEventListener('click', () => {
        this.view = btn.dataset.view;
        if (this.view === 'month') this._loadMonth();
        else this._loadWeek();
      });
    });

    // Entrées calendrier
    this.element.querySelectorAll('.cal-entry').forEach(entryEl => {
      entryEl.addEventListener('click', (e) => {
        // Ignorer si clic sur un bouton d'action rapide
        if (e.target.closest('.cal-entry-btn')) return;
        const entryId = parseInt(entryEl.dataset.entryId, 10);
        const pubId = entryEl.dataset.entryPubId ? parseInt(entryEl.dataset.entryPubId, 10) : null;
        if (pubId) {
          this._openStudio(pubId);
        } else {
          this.selectedEntry = entryId;
          this._openStudio(entryId);
        }
      });

      // Boutons accept/refuse rapides
      const acceptBtn = entryEl.querySelector('[data-action="accept-suggestion"]');
      if (acceptBtn) {
        acceptBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          this._acceptSuggestion(parseInt(acceptBtn.dataset.entryId, 10));
        });
      }
      const refuseBtn = entryEl.querySelector('[data-action="refuse-suggestion"]');
      if (refuseBtn) {
        refuseBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          this._refuseSuggestion(parseInt(refuseBtn.dataset.entryId, 10));
        });
      }
    });
  }
}

export function createCommunityManagerCalendarPage(router) {
  return new CommunityManagerCalendarPage(router);
}
