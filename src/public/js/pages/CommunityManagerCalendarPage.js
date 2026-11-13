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
  updateCommunityManagerCalendarEntry,
  createStudioDraftFromCalendar,
  getStudioDraft,
  publishStudioDraft,
  regeneratePublicationContent,
} from '../services/sportApi.js?v=14';
import { createCommunityManagerStudioPage } from './CommunityManagerStudioPage.js?v=4';

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

  _dateKey(d) {
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${d.getFullYear()}-${m}-${day}`;
  }

  _parseDate(str) {
    const [y, m, d] = str.split('-').map(Number);
    return new Date(y, m - 1, d);
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
      this.weekData = await getWeekCalendar(this._dateKey(monday));
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
    this.studioPage.initialize().then(() => this.render()).catch(() => {});
    this.render();
  }

  _notifyError(message) {
    this.error = message;
    this.render();
    const alert = this.element?.querySelector?.('.alert');
    if (alert && typeof alert.scrollIntoView === 'function') {
      alert.scrollIntoView({ block: 'nearest' });
    }
  }

  // Ouvre l'événement dans le Studio : publication existante, sinon création du brouillon.
  async _openEntry(entryEl) {
    if (this.loading) return;
    const entryId = parseInt(entryEl.dataset.entryId, 10);
    const pubId = entryEl.dataset.entryPubId ? parseInt(entryEl.dataset.entryPubId, 10) : null;
    const status = entryEl.dataset.entryStatus || '';
    const source = entryEl.dataset.entrySource || '';

    if (pubId) {
      this._openStudio(pubId);
      return;
    }
    if (source === 'suggestion' && status === 'refused') {
      this._notifyError('Cette suggestion a été refusée.');
      return;
    }

    this.loading = true;
    this.error = null;
    this.render();
    try {
      let effectiveStatus = status;
      if (source === 'suggestion' && status === 'pending') {
        await acceptSuggestion(entryId);
        effectiveStatus = 'accepted';
      }
      if (effectiveStatus !== 'planifié' && effectiveStatus !== 'accepted') {
        await updateCommunityManagerCalendarEntry(entryId, { status: 'planifié' });
        effectiveStatus = 'planifié';
      }
      const res = await createStudioDraftFromCalendar({
        calendar_entry_id: entryId,
        styles: ['stats'],
        visual_type: 'photo',
      });
      this.loading = false;
      if (!res?.publication_id) {
        throw new Error(res?.detail || 'Création du brouillon impossible.');
      }
      this._openStudio(res.publication_id);
      this._loadMonth();
    } catch (error) {
      this.loading = false;
      this._notifyError(error?.data?.detail || error?.message || "Impossible d'ouvrir l'événement.");
    }
  }

  render() {
    if (!this.element) {
      this.element = document.createElement('div');
      this.element.className = 'page-content';
    }

    if (this.showStudio && this.studioPage) {
      this.element.replaceChildren(this.studioPage.render());
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
        <div class="page-header-left">
          <h1>Calendrier éditorial</h1>
          <p class="page-subtitle">Publications sportives et suggestions de stories</p>
        </div>
        <div class="page-header-right">
          ${this.canGenerate ? `<button class="btn btn-secondary" data-action="generate-suggestions">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
            Générer suggestions
          </button>` : ''}
          <div class="view-toggle">
            ${viewBtn('Mois', 'month', this.view === 'month')}
            ${viewBtn('Semaine', 'week', this.view === 'week')}
          </div>
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
        const dayKey = this._dateKey(day);
        const entries = (this.calendarData.days?.[dayKey] || []).slice(0, 3);
        const totalEntries = (this.calendarData.days?.[dayKey] || []).length;
        const entriesHtml = entries.map(e => this._renderMonthEntry(e)).join('');
        html += `
          <td class="cal-day ${isToday ? 'cal-day--today' : ''} ${isOtherMonth ? 'cal-day--other' : ''}" data-day="${dayKey}">
            <div class="cal-day-number">${day.getDate()}</div>
            <div class="cal-day-entries">${entriesHtml}</div>
            ${totalEntries > 3 ? `<div class="cal-day-more">+${totalEntries - 3}</div>` : ''}
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
    const topic = this._escape(entry.topic || '');
    return `
      <div class="cal-entry" data-entry-id="${entry.entry_id}" data-entry-pub-id="${entry.pub_id || ''}"
           data-entry-status="${this._escape(entry.status || '')}" data-entry-source="${this._escape(entry.source || 'manuel')}"
           title="${topic}"
           style="--color: ${color}; --status-color: ${statusColor};">
        <div class="cal-entry-head">
          <span class="cal-entry-dot"></span>
          <div class="cal-entry-title">${topic}</div>
        </div>
        <div class="cal-entry-foot">
          <span class="cal-entry-status">${entry.status}</span>
          ${isSuggestion ? `
            <div class="cal-entry-actions">
              <button class="cal-entry-btn cal-entry-btn--accept" data-action="accept-suggestion" data-entry-id="${entry.entry_id}" title="Accepter">✓</button>
              <button class="cal-entry-btn cal-entry-btn--refuse" data-action="refuse-suggestion" data-entry-id="${entry.entry_id}" title="Refuser">✗</button>
            </div>` : ''}
        </div>
      </div>
    `;
  }

  _renderWeekGrid() {
    const days = [];
    const monday = this.weekData.monday ? this._parseDate(this.weekData.monday) : this.currentDate;
    for (let i = 0; i < 7; i++) {
      days.push(new Date(monday.getFullYear(), monday.getMonth(), monday.getDate() + i));
    }

    let html = '<table class="cal-week"><thead><tr>';
    for (const day of days) {
      const isToday = day.toDateString() === this._today().toDateString();
      html += `<th class="${isToday ? 'cal-week-day--today' : ''}">${WEEK_DAYS[(day.getDay() + 6) % 7]}<br>${day.getDate()}</th>`;
    }
    html += '</tr></thead><tbody><tr>';
    for (const day of days) {
      const dayKey = this._dateKey(day);
      const entries = this.weekData.days?.[dayKey] || [];
      const entriesHtml = entries.map(e => this._renderMonthEntry(e)).join('');
      html += `<td class="cal-week-day">${entriesHtml}</td>`;
    }
    html += '</tr></tbody></table>';
    return html;
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
        this._openEntry(entryEl);
      });

      // Boutons accept/refuse rapides
      const acceptBtn = entryEl.querySelector('[data-action="accept-suggestion"]');
      if (acceptBtn) {
        acceptBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          this._openEntry(entryEl);
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
