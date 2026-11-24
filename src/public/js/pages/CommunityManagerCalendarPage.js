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
  deleteCommunityManagerCalendarEntry,
  regenerateCommunityManagerHashtags,
  createStudioDraftFromCalendar,
  getStudioDraft,
  publishStudioDraft,
  regeneratePublicationContent,
  createStoryDraft,
  getSuggestedPhotos,
} from '../services/sportApi.js?v=16';
import { createStoryStudioPage } from './StoryStudioPage.js?v=1';
import { createCommunityPublisherPage } from './CommunityPublisherPage.js?v=1';

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
    this.view = (typeof window !== 'undefined' && window.matchMedia && window.matchMedia('(max-width: 767px)').matches) ? 'week' : 'month'; // 'month' | 'week'
    this.currentDate = new Date();
    this.selectedEntry = null;
    this.publisherPage = null;
    this.storyStudioPage = null;
    this.showPublisher = false;
    this.showStoryStudio = false;
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
    if (this.view === 'week') await this._loadWeek();
    else await this._loadMonth();
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

  async _deleteEntry(entryId) {
    if (!confirm('Supprimer cet élément du calendrier ?')) return;
    try {
      await deleteCommunityManagerCalendarEntry(entryId);
      this.selectedEntry = null;
      if (this.view === 'month') this._loadMonth();
      else this._loadWeek();
    } catch (error) {
      this.error = error?.data?.detail || error?.message || 'Erreur suppression';
      this.render();
    }
  }

  async _regenerateHashtags(entryId) {
    try {
      await regenerateCommunityManagerHashtags(entryId);
      if (this.view === 'month') this._loadMonth();
      else this._loadWeek();
    } catch (error) {
      this.error = error?.data?.detail || error?.message || 'Erreur regeneration hashtags';
      this.render();
    }
  }

  _openPublisher({ entryId = null, draftId = null, pubId = null, format = 'post', garminActivityId = null, freshDraft = false } = {}) {
    if (draftId) {
      // Ouvre un brouillon Story existant
      this.showStoryStudio = true;
      this.storyStudioPage = createStoryStudioPage(this.router, draftId, () => {
        this.showStoryStudio = false;
        this.storyStudioPage?.destroy();
        this.storyStudioPage = null;
        this.selectedEntry = null;
        this._loadMonth();
      });
      this.storyStudioPage.initialize().catch(() => {});
      this.render();
      return;
    }

    if (pubId) {
      // Charge une publication existante (SportPublication)
      this.showPublisher = true;
      this.publisherPage = createCommunityPublisherPage(this.router, {
        entryId: pubId,  // Pour compatibilité, mais on va charger la pub existante
        format,
        isExistingPublication: true,
        onBack: () => {
          this.showPublisher = false;
          this.publisherPage?.destroy();
          this.publisherPage = null;
          this.selectedEntry = null;
          this._loadMonth();
        },
      });
      // Charger la publication existante après l'initialisation
      this.publisherPage.initialize().then(() => {
        if (this.publisherPage) {
          this.publisherPage._loadExistingPublication(pubId);
        }
      }).catch(() => {});
      this.render();
      return;
    }

    // Ouvre le nouveau Publisher unifié pour créer un nouveau brouillon
    this.showPublisher = true;
    this.publisherPage = createCommunityPublisherPage(this.router, {
      entryId,
      format,
      garminActivityId,
      freshDraft,
      onBack: () => {
        this.showPublisher = false;
        this.publisherPage?.destroy();
        this.publisherPage = null;
        this.selectedEntry = null;
        this._loadMonth();
      },
    });
    this.publisherPage.initialize().catch(() => {});
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
    const storyDraftId = entryEl.dataset.entryStoryDraftId ? parseInt(entryEl.dataset.entryStoryDraftId, 10) : null;
    const sourceActivityId = entryEl.dataset.entrySourceActivityId ? parseInt(entryEl.dataset.entrySourceActivityId, 10) : null;
    const status = entryEl.dataset.entryStatus || '';
    const source = entryEl.dataset.entrySource || '';

    // Si un brouillon Story existe, l'ouvrir directement
    if (storyDraftId) {
      this._openPublisher({ draftId: storyDraftId });
      return;
    }

    if (pubId) {
      // Publication existante : déterminer le format depuis le type de contenu
      const format = source === 'garmin' ? 'story' : 'post';
      this._openPublisher({ pubId, format });
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

      // Pour les activités Garmin, créer un StoryDraft (via Story Studio)
      // Pour les autres, créer un brouillon Studio (Post/Reel)
      if (source === 'garmin') {
        if (!sourceActivityId) {
          throw new Error('Activité Garmin non liée à cette entrée de calendrier');
        }
        // Récupérer les photos suggérées pour cette activité
        const photoRes = await getSuggestedPhotos(null, 20);
        const photoIds = (photoRes.items || []).map(p => p.id);
        if (photoIds.length === 0) {
          throw new Error('Aucune photo disponible pour cette activité Garmin');
        }
        const res = await createStoryDraft({
          activity_id: sourceActivityId,
          photo_ids: photoIds,
          calendar_entry_id: entryId,
        });
        this.loading = false;
        if (!res?.id) {
          throw new Error(res?.detail || 'Création du brouillon Story impossible.');
        }
        this._openPublisher({ draftId: res.id });
      } else {
        const res = await createStudioDraftFromCalendar({
          calendar_entry_id: entryId,
          styles: ['stats'],
          visual_type: 'photo',
        });
        if (!res?.publication_id) {
          throw new Error(res?.detail || 'Création du brouillon impossible.');
        }
        this._openPublisher({ entryId: res.publication_id, format: 'post' });
      }
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

    if (this.showStoryStudio && this.storyStudioPage) {
      this.element.replaceChildren(this.storyStudioPage.render());
      return this.element;
    }
    if (this.showPublisher && this.publisherPage) {
      this.element.replaceChildren(this.publisherPage.render());
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
          <div class="calendar-create-actions" aria-label="Créer une publication">
            <button class="btn btn-primary btn-sm" data-action="create-format" data-format="post">＋ Publication</button>
            <button class="btn btn-secondary btn-sm" data-action="create-format" data-format="carousel">＋ Carrousel</button>
            <button class="btn btn-secondary btn-sm" data-action="create-format" data-format="reel">＋ Reel</button>
            <button class="btn btn-secondary btn-sm" data-action="create-format" data-format="story">＋ Story</button>
          </div>
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
    const topic = this._escape(entry.pub_title || entry.topic || '');
    const isShared = entry.pub_status === 'shared';
    const publishedClass = isShared ? ' cal-entry--published' : '';
    const storyDraftId = entry.story_draft_id || entry.pub_story_draft_id || null;
    const sourceActivityId = entry.source_activity_id || null;
    const deleteBtn = !isShared ? `
      <button class="cal-entry-btn cal-entry-btn--delete" data-action="delete-entry" data-entry-id="${entry.entry_id}" title="Supprimer">🗑</button>
    ` : '';
    return `
      <div class="cal-entry${publishedClass}" data-entry-id="${entry.entry_id}" data-entry-pub-id="${entry.pub_id || ''}"
           data-entry-story-draft-id="${storyDraftId || ''}"
           data-entry-source-activity-id="${sourceActivityId || ''}"
           data-entry-status="${this._escape(entry.status || '')}" data-entry-source="${this._escape(entry.source || 'manuel')}"
           data-entry-pub-status="${this._escape(entry.pub_status || '')}"
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
          ${deleteBtn ? `<div class="cal-entry-actions">${deleteBtn}</div>` : ''}
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

    const isMobile = (typeof window !== 'undefined' && window.matchMedia && window.matchMedia('(max-width: 767px)').matches);

    if (isMobile) {
      let html = '<div class="cal-week-mobile">';
      for (const day of days) {
        const isToday = day.toDateString() === this._today().toDateString();
        const dayKey = this._dateKey(day);
        const entries = this.weekData.days?.[dayKey] || [];
        const entriesHtml = entries.map(e => this._renderMonthEntry(e)).join('');
        html += `<div class="cal-week-day-card ${isToday ? 'cal-week-day--today' : ''}">
          <div class="cal-week-day-header">${WEEK_DAYS[(day.getDay() + 6) % 7]} ${day.getDate()}</div>
          <div class="cal-week-day-body">${entriesHtml || '<span class="cal-empty">—</span>'}</div>
        </div>`;
      }
      html += '</div>';
      return html;
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
        else if (action === 'create-format') { this._openPublisher({ format: btn.dataset.format, freshDraft: true }); }
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

      // Bouton suppression rapide
      const deleteBtn = entryEl.querySelector('[data-action="delete-entry"]');
      if (deleteBtn) {
        deleteBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          this._deleteEntry(parseInt(deleteBtn.dataset.entryId, 10));
        });
      }

      const regenerateBtn = entryEl.querySelector('[data-action="regenerate-hashtags"]');
      if (regenerateBtn) {
        regenerateBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          this._regenerateHashtags(parseInt(regenerateBtn.dataset.entryId, 10));
        });
      }
    });
  }
}

export function createCommunityManagerCalendarPage(router) {
  return new CommunityManagerCalendarPage(router);
}
