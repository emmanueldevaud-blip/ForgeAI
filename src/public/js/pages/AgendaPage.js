import { authStore } from '../stores/auth.js';
import {
  createExternalPresence,
  deletePresence,
  getAgendaPlanning,
  upsertMyPresence,
} from '../services/agendaApi.js';

const VIEW_LABELS = {
  week: 'Semaine',
  month: 'Mois',
};

const DAY_LABELS_SHORT = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim'];
const DAY_LABELS_LONG = ['dimanche', 'lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi'];
const MONTH_LABELS = [
  'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
  'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre',
];

const SOURCE_BADGES = {
  user: 'inscription',
  external: 'externe',
  cleaning: 'volontaire',
  occupant: 'occupation',
};

const PERIOD_LABELS = {
  full: 'Journée',
  morning: 'Matin',
  afternoon: 'Après-midi',
  week: 'Toute la semaine',
};

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

function periodsOverlap(left, right) {
  const a = left || 'full';
  const b = right || 'full';
  if (a === 'full' || b === 'full') return true;
  return a === b;
}

export class AgendaPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.view = 'week';
    this.anchor = new Date();
    this.data = null;
    this.error = null;
    this.openDay = null;
    this._authUnsubscribe = null;
  }

  async initialize() {
    await this.loadPlanning();
    if (!this._authUnsubscribe) {
      this._authUnsubscribe = authStore.subscribe(() => this.renderState());
    }
  }

  async loadPlanning() {
    this.error = null;
    try {
      this.data = await getAgendaPlanning(this.view, toISODate(this.anchor));
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
          <div class="page-header-left"><h1>Agenda</h1><p class="page-subtitle">Présences dans les locaux Bureau.</p></div>
        </div>
        <div class="card" role="alert">
          <div class="card-body agenda-empty">
            <h2>Impossible de charger l’agenda</h2>
            <p>${escapeHtml(this.error.message || 'Erreur inconnue')}</p>
            <button class="btn btn-primary" data-action="retry">Réessayer</button>
          </div>
        </div>`;
      this._bindCommon();
      return;
    }

    const data = this.data || {};
    const rooms = data.rooms || [];
    const days = data.days || [];
    const canManage = authStore.hasPermission('agenda.manage');
    const freeDate = this._defaultFreeDate(days);

    this.element.innerHTML = `
      <div class="page-header agenda-header">
        <div class="page-header-left">
          <h1>Agenda</h1>
          <p class="page-subtitle">Vos présences, le planning par bureau et les inscriptions libres.</p>
        </div>
        <div class="page-header-right agenda-toolbar">
          <div class="agenda-nav" role="group" aria-label="Navigation">
            <button class="btn btn-secondary btn-sm" data-nav="prev" aria-label="Période précédente">‹</button>
            <button class="btn btn-secondary btn-sm" data-nav="today">Aujourd’hui</button>
            <button class="btn btn-secondary btn-sm" data-nav="next" aria-label="Période suivante">›</button>
          </div>
          <div class="agenda-views" role="group" aria-label="Vue">
            ${Object.entries(VIEW_LABELS).map(([value, label]) => `
              <button class="btn btn-sm ${this.view === value ? 'btn-primary' : 'btn-secondary'}" data-view="${value}" aria-pressed="${this.view === value}">${label}</button>
            `).join('')}
          </div>
        </div>
      </div>

      ${rooms.length === 0 ? this._noRoomsHtml() : `
        <section class="card agenda-section agenda-section--mine" aria-labelledby="agenda-mine-title">
          <header class="agenda-section-header">
            <div>
              <h2 id="agenda-mine-title">Ma présence</h2>
            </div>
          </header>
          <div class="card-body agenda-section-body">
            ${this._mineGridHtml(rooms)}
          </div>
        </section>

        <section class="agenda-section agenda-section--planning" aria-labelledby="agenda-planning-title">
          <header class="agenda-section-header agenda-section-header--plain">
            <div>
              <h2 id="agenda-planning-title">Planning par bureau</h2>
              <p class="agenda-section-desc">Récapitulatif des inscrits local par local. Cliquez sur une case pour le détail du jour.</p>
            </div>
            <div class="agenda-period-label">${escapeHtml(this._periodLabel())}</div>
          </header>
          <section class="card agenda-card" aria-label="Planning des présences">
            ${this._planningBody(rooms, days)}
          </section>
          <section class="agenda-legend" aria-label="Légende">
            <span class="agenda-legend-item"><span class="agenda-dot agenda-dot--user"></span> inscription</span>
            <span class="agenda-legend-item"><span class="agenda-dot agenda-dot--external"></span> externe</span>
            <span class="agenda-legend-item"><span class="agenda-dot agenda-dot--cleaning"></span> volontaire</span>
            <span class="agenda-legend-item"><span class="agenda-dot agenda-dot--occupant"></span> occupation</span>
          </section>
        </section>

        <section class="card agenda-section agenda-section--free" aria-labelledby="agenda-free-title">
          <header class="agenda-section-header">
            <div>
              <h2 id="agenda-free-title">Inscriptions libres</h2>
              <p class="agenda-section-desc">${canManage
                ? 'Ajoutez une personne sans compte utilisateur (visiteur, intervenant…).'
                : 'Seules les personnes avec la permission « agenda.manage » peuvent ajouter des inscriptions libres.'}</p>
            </div>
          </header>
          <div class="card-body agenda-section-body">
            ${canManage ? this._freeFormHtml(rooms, freeDate) : ''}
          </div>
        </section>
      `}

      ${this.openDay ? this._dayPanelHtml(rooms) : ''}
    `;

    this._bindCommon();
    if (rooms.length) {
      this._bindMineForm();
      this._bindPlanning(rooms);
      if (canManage) this._bindFreeForm();
    }
    if (this.openDay) this._bindDayPanel();
  }

  _noRoomsHtml() {
    return `
      <div class="card">
        <div class="card-body agenda-empty">
          <h2>Aucun local Bureau</h2>
          <p>Définissez un local avec un type d’utilisation « Bureau » (ou « Bureaux ») dans le module Bâtiments pour l’afficher ici.</p>
        </div>
      </div>`;
  }

  _periodLabel() {
    const days = this.data?.days || [];
    if (!days.length) return '';
    const start = parseISODate(days[0].date);
    const end = parseISODate(days[days.length - 1].date);
    if (this.view === 'week') {
      return `Semaine du ${start.getDate()} ${MONTH_LABELS[start.getMonth()].toLowerCase()} au ${end.getDate()} ${MONTH_LABELS[end.getMonth()].toLowerCase()} ${end.getFullYear()}`;
    }
    return `${MONTH_LABELS[start.getMonth()]} ${start.getFullYear()}`;
  }

  _mineGridDates() {
    const days = this.data?.days || [];
    if (days.length) return days.map(day => day.date);
    return weekdaysOfAnchor(this.view === 'week' ? this.anchor : new Date());
  }

  _minePresenceForDate(iso, roomId = null) {
    const day = (this.data?.days || []).find(d => d.date === iso);
    if (!day) return null;
    if (roomId != null) {
      for (const room of day.rooms || []) {
        if (String(room.room_id) !== String(roomId)) continue;
        return (room.presences || []).find(p => p.is_mine && p.person_type === 'user') || null;
      }
      return null;
    }
    return this._myPresence(day);
  }

  _otherMineOnDay(iso, roomId) {
    const day = (this.data?.days || []).find(d => d.date === iso);
    if (!day) return [];
    const others = [];
    for (const room of day.rooms || []) {
      if (String(room.room_id) === String(roomId)) continue;
      const mine = (room.presences || []).find(p => p.is_mine && p.person_type === 'user');
      if (mine) others.push(mine);
    }
    return others;
  }

  _conflictMessage(iso, roomId, period, needsMeal) {
    for (const other of this._otherMineOnDay(iso, roomId)) {
      if (periodsOverlap(period, other.period || 'full')) {
        return 'Vous êtes déjà inscrit dans un autre local pour la même période';
      }
      if (needsMeal && other.needs_meal) {
        return 'Repas déjà sélectionné dans un autre local';
      }
    }
    return null;
  }

  _mineGridHtml(rooms) {
    const dates = this._mineGridDates();
    const today = toISODate(new Date());
    const hasMine = dates.some(iso => this._minePresenceForDate(iso));
    const rowDefs = [
      { field: 'morning', label: 'Matin', bulk: true },
      { field: 'afternoon', label: 'Après-midi', bulk: true },
      { field: 'meal', label: 'Repas', bulk: false, sectionBreak: true },
      { field: 'desk', label: 'Poste', bulk: false },
    ];

    const isMonth = this.view === 'month';
    return `
      <div class="agenda-mine-scroll">
        <div class="agenda-mine-matrix ${isMonth ? 'agenda-mine-matrix--month' : ''}" style="--mine-days: ${dates.length}">
          <div class="agenda-mine-matrix-head">
            <span class="agenda-mine-matrix-corner">Local</span>
            <span class="agenda-mine-matrix-option">Option</span>
            ${dates.map(iso => {
              const date = parseISODate(iso);
              return `
                <span class="agenda-mine-matrix-day ${iso === today ? 'is-today' : ''}">
                  <span class="agenda-mine-day-name">${DAY_LABELS_SHORT[date.getDay() === 0 ? 6 : date.getDay() - 1]}</span>
                  <span class="agenda-mine-day-num">${date.getDate()}</span>
                </span>`;
            }).join('')}
            <span class="agenda-mine-matrix-actions-head"></span>
          </div>
          ${rooms.map((room, roomIndex) => rowDefs.map((row, rowIndex) => `
            <div class="agenda-mine-matrix-row ${rowIndex === 0 ? 'is-room-start' : ''} ${rowIndex === rowDefs.length - 1 ? 'is-room-end' : ''} ${row.sectionBreak ? 'is-section-break' : ''} ${roomIndex > 0 && rowIndex === 0 ? 'is-room-separator' : ''}">
              ${rowIndex === 0
                ? `<span class="agenda-mine-matrix-room${roomIndex > 0 ? ' is-not-first' : ''}">${escapeHtml(room.name)}${room.building_name ? `<small>${escapeHtml(room.building_name)}</small>` : ''}</span>`
                : ''}
              <span class="agenda-mine-matrix-label">${row.label}</span>
              ${dates.map(iso => {
                const inMonth = (this.data?.days || []).some(d => d.date === iso);
                const mine = this._minePresenceForDate(iso, room.id);
                const inRoom = !!mine;
                const period = inRoom ? (mine.period || 'full') : null;
                let on = false;
                let enabled = inMonth;
                let title = row.label;
                if (!inMonth) {
                  title = 'Hors mois affiché';
                } else if (row.field === 'morning') on = period === 'morning' || period === 'full';
                else if (row.field === 'afternoon') on = period === 'afternoon' || period === 'full';
                else if (row.field === 'desk') {
                  on = inRoom && !!mine.needs_workstation;
                  enabled = inRoom;
                  title = enabled ? 'Poste de travail' : 'Sélectionnez d’abord une présence ce jour-là';
                } else {
                  on = inRoom && !!mine.needs_meal;
                  enabled = inRoom;
                  title = enabled ? 'Repas' : 'Sélectionnez d’abord une présence ce jour-là';
                }
                return `
                  <button type="button" class="agenda-mine-cell ${on ? 'is-on' : ''} ${row.field === 'desk' ? 'agenda-mine-cell--desk' : ''} ${row.field === 'meal' ? 'agenda-mine-cell--meal' : ''}"
                    data-mine-toggle="${row.field}" data-room-id="${room.id}" data-date="${iso}"
                    aria-pressed="${on}" ${enabled ? '' : 'disabled'}
                    aria-label="${row.label} — ${escapeHtml(formatDayLabel(iso))} — ${escapeHtml(room.name)}"
                    title="${escapeHtml(title)}"></button>`;
              }).join('')}
              ${row.bulk
                ? `<button type="button" class="btn btn-secondary btn-sm agenda-mine-bulk" data-mine-bulk="${row.field}" data-room-id="${room.id}">Tout</button>`
                : '<span class="agenda-mine-matrix-spacer"></span>'}
            </div>
          `).join('')).join('')}
        </div>
      </div>
      <div class="agenda-mine-footer">
        ${hasMine ? '<button class="btn btn-secondary" type="button" data-action="clear-mine">Annuler ma présence</button>' : ''}
      </div>`;
  }

  _freeFormHtml(rooms, freeDate) {
    return `
      <form class="agenda-free-form" data-agenda-free>
        <div class="agenda-free-grid">
          <label class="form-control-wrap">
            <span>Prénom</span>
            <input class="form-control" name="external_firstname" placeholder="Prénom" maxlength="100">
            <span>Nom</span>
            <input class="form-control" name="external_name" placeholder="Nom" maxlength="200">
          </label>
          <label class="form-control-wrap">
            <span>Local</span>
            <select class="form-control" name="room_id" required>
              <option value="">Choisir un local…</option>
              ${rooms.map(room => `<option value="${room.id}">${escapeHtml(room.name)}${room.building_name ? ` — ${escapeHtml(room.building_name)}` : ''}</option>`).join('')}
            </select>
          </label>
          <label class="form-control-wrap">
            <span>Date</span>
            <input class="form-control" type="date" name="presence_date" value="${freeDate}" required>
          </label>
          <label class="form-control-wrap">
            <span>Période</span>
            <select class="form-control" name="period">
              <option value="full">Journée</option>
              <option value="morning">Matin</option>
              <option value="afternoon">Après-midi</option>
            </select>
          </label>
          <label class="agenda-check agenda-free-desk">
            <input type="checkbox" name="needs_workstation">
            <span>Poste de travail</span>
          </label>
          <div class="agenda-free-actions">
            <button class="btn btn-primary" type="submit">Ajouter l’inscription</button>
          </div>
        </div>
      </form>`;
  }

  _defaultFreeDate(days) {
    const today = toISODate(new Date());
    if (days.some(d => d.date === today)) return today;
    if (days.length) {
      const todayDow = new Date().getDay();
      if (todayDow === 0 || todayDow === 6) return days[0].date;
      return days[0].date;
    }
    return today;
  }

  _planningBody(rooms, days) {
    if (this.view === 'week') return this._weekGrid(rooms, days);
    return this._monthGrid(rooms, days);
  }

_halfCellHtml(day, room, half, dayByIso) {
    const counters = (dayByIso.get(day.date)?.rooms || []).find(r => r.room_id === room.id);
    const people = (counters?.presences || [])
      .sort((a, b) => a.person_name.localeCompare(b.person_name))
      .filter(person => {
        const period = person.period || 'full';
        return period === 'full' || period === half.field;
      });
    const present = people.length;
    const desks = people.filter(person => person.needs_workstation).length;
    const capacity = counters?.capacity ?? room.workstation_capacity ?? 0;
    const namesHtml = people.length ? `
      <ul class="agenda-cell-names">
        ${people.map(person => `
          <li class="agenda-cell-name" title="${escapeHtml(person.person_name)} — ${escapeHtml(SOURCE_BADGES[person.person_type] || person.person_type)}">
            <span class="agenda-cell-name-text">${escapeHtml(person.person_name)}</span>
            <span class="agenda-dot agenda-dot--${person.person_type}" title="${escapeHtml(SOURCE_BADGES[person.person_type] || person.person_type)}"></span>
          </li>
        `).join('')}
      </ul>` : '';
    return `
      <td class="agenda-cell ${present ? 'has-presence' : ''}">
        <button class="agenda-cell-btn" data-day="${day.date}" data-room="${room.id}"
          aria-label="${escapeHtml(room.name)} le ${escapeHtml(formatDayLabel(day.date))} — ${half.label} : ${present} présent(s)">
          <span class="agenda-count agenda-count--people">${present}</span>
          ${capacity ? `<span class="agenda-count agenda-count--desk ${desks > capacity ? 'is-over' : ''}">${desks}/${capacity}</span>` : (desks ? `<span class="agenda-count agenda-count--desk">${desks}</span>` : '')}
          ${namesHtml}
        </button>
      </td>`;
  }

  _weekGrid(rooms, days) {
    const dayByIso = new Map(days.map(day => [day.date, day]));
    const halfRows = [
      { field: 'morning', label: 'Matin' },
      { field: 'afternoon', label: 'Après-midi' },
    ];

    const headers = days.map(day => {
      const date = parseISODate(day.date);
      const isToday = day.date === toISODate(new Date());
      return `<th class="agenda-day-head ${isToday ? 'is-today' : ''}" colspan="2" scope="col">
        <span class="agenda-day-name">${DAY_LABELS_SHORT[(date.getDay() + 6) % 7]}</span>
        <span class="agenda-day-num">${date.getDate()}</span>
      </th>`;
    }).join('');

    const subHeaders = days.map(() =>
      halfRows.map(half => `<th class="agenda-half-subhead" scope="col">${half.label}</th>`).join('')
    ).join('');

    const rows = rooms.map(room => halfRows.map((half, halfIndex) => {
      const lead = halfIndex === 0
        ? `<th class="agenda-room-head" rowspan="2" scope="rowgroup">
            <span class="agenda-room-name">${escapeHtml(room.name)}</span>
            <span class="agenda-room-meta">${escapeHtml(room.building_name || '')}${room.workstation_capacity ? ` · ${room.workstation_capacity} postes` : ''}</span>
          </th>
          <th class="agenda-half-head" scope="row">${half.label}</th>`
        : `<th class="agenda-half-head" scope="row">${half.label}</th>`;
      const cells = days.map(day => this._halfCellHtml(day, room, half, dayByIso)).join('');
      return `<tr>${lead}${cells}</tr>`;
    }).join('')).join('');

    return `
      <div class="agenda-scroll">
        <table class="agenda-table agenda-table--half" role="grid">
          <thead>
            <tr>
              <th class="agenda-room-head agenda-corner" rowspan="2" scope="col">Local</th>
              <th class="agenda-corner agenda-half-corner" rowspan="2" scope="col">Option</th>
              ${headers}
            </tr>
            <tr>${subHeaders}</tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
      ${this._integratedStrip(days)}`;
  }

  _monthGrid(rooms, days) {
    const first = parseISODate(days[0].date);
    const lead = (first.getDay() + 6) % 7;
    const cells = [];

    for (let i = 0; i < lead; i += 1) {
      cells.push('<td class="agenda-month-cell is-empty" aria-hidden="true"></td>');
    }

    days.forEach(day => {
      const date = parseISODate(day.date);
      const isToday = day.date === toISODate(new Date());
      const integrated = day.integrated?.length || 0;
      const isWeekend = date.getDay() === 0 || date.getDay() === 6;
      cells.push(`
        <td class="agenda-month-cell ${isToday ? 'is-today' : ''} ${day.total_present ? 'has-presence' : ''} ${isWeekend ? 'is-weekend' : ''}">
          <button class="agenda-month-btn" data-day="${day.date}" aria-label="${escapeHtml(formatDayLabel(day.date))}">
            <span class="agenda-month-num">${date.getDate()}</span>
            ${day.total_present ? `<span class="agenda-month-total">${day.total_present}</span>` : ''}
            ${integrated ? `<span class="agenda-month-integrated">+${integrated}</span>` : ''}
          </button>
        </td>`);
    });

    while (cells.length % 7 !== 0) {
      cells.push('<td class="agenda-month-cell is-empty" aria-hidden="true"></td>');
    }

    const weeks = [];
    for (let i = 0; i < cells.length; i += 7) {
      weeks.push(`<tr>${cells.slice(i, i + 7).join('')}</tr>`);
    }

    return `
      <div class="agenda-scroll">
        <table class="agenda-month" role="grid" aria-label="Vue mois">
          <thead><tr>${DAY_LABELS_SHORT.map(d => `<th scope="col">${d}</th>`).join('')}</tr></thead>
          <tbody>${weeks.join('')}</tbody>
        </table>
      </div>`;
  }

  _integratedStrip(days) {
    const withIntegrated = days.filter(day => (day.integrated || []).length);
    if (!withIntegrated.length) return '';
    return `
      <div class="agenda-integrated">
        <h3>Présences intégrées (ménage / occupants)</h3>
        <div class="agenda-integrated-list">
          ${withIntegrated.map(day => `
            <div class="agenda-integrated-day">
              <button class="agenda-integrated-day-btn" data-day="${day.date}">
                <strong>${escapeHtml(formatDayLabel(day.date))}</strong>
                <span>${day.integrated.length} personne${day.integrated.length > 1 ? 's' : ''}</span>
              </button>
            </div>
          `).join('')}
        </div>
      </div>`;
  }

  _dayPanelHtml(rooms) {
    const day = (this.data.days || []).find(d => d.date === this.openDay);
    if (!day) return '';
    const hasPeople = day.rooms.some(r => r.presences.length) || (day.integrated || []).length;

    return `
      <div class="modal-overlay open agenda-day-overlay" data-action="close-day">
        <div class="modal open agenda-day-modal" role="dialog" aria-modal="true" aria-label="Détail du jour">
          <div class="modal-content agenda-day-modal-content">
            <div class="modal-header agenda-day-header">
              <div class="agenda-day-header-text">
                <span class="agenda-eyebrow">DÉTAIL DU JOUR</span>
                <h2>${escapeHtml(formatDayLabel(day.date))}</h2>
                <p class="agenda-day-totals">${day.total_present} présent(s) · ${day.total_workstations} poste(s)</p>
              </div>
              <button type="button" class="modal-close" data-action="close-day" aria-label="Fermer">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
              </button>
            </div>
            <div class="modal-body agenda-day-body">
              ${!hasPeople ? '<p class="agenda-none">Aucune présence ce jour-là.</p>' : `
                <div class="agenda-day-rooms">
                  ${day.rooms.filter(counter => counter.presences.length || counter.present_count).map(counter => {
                    const room = rooms.find(r => r.id === counter.room_id);
                    return `
                      <section class="agenda-room-block">
                        <header>
                          <h3>${escapeHtml(room?.name || `Local #${counter.room_id}`)}</h3>
                          <span class="agenda-room-stats">
                            ${counter.present_count} présent(s)
                            ${counter.capacity ? ` · ${counter.workstation_count}/${counter.capacity} postes` : (counter.workstation_count ? ` · ${counter.workstation_count} poste(s)` : '')}
                          </span>
                        </header>
                        ${counter.presences.length ? `
                          <ul class="agenda-people">
                            ${counter.presences.map(person => this._personLi(person)).join('')}
                          </ul>` : '<p class="agenda-none">Aucune présence</p>'}
                      </section>`;
                  }).join('')}
                </div>

                ${(day.integrated || []).length ? `
                  <section class="agenda-room-block agenda-integrated-block">
                    <header>
                      <h3>Intégrées (ménage / occupants)</h3>
                      <span class="agenda-room-stats">${day.integrated.length}</span>
                    </header>
                    <ul class="agenda-people">
                      ${day.integrated.map(person => this._personLi(person)).join('')}
                    </ul>
                  </section>` : ''}
              `}
            </div>
            <div class="modal-footer agenda-day-footer">
              <button class="btn btn-secondary" type="button" data-action="close-day">Fermer</button>
            </div>
          </div>
        </div>
      </div>`;
  }

  _personLi(person) {
    const badge = SOURCE_BADGES[person.person_type];
    const periodBadge = person.period && person.period !== 'full'
      ? `<span class="agenda-badge agenda-badge--period">${escapeHtml(PERIOD_LABELS[person.period] || person.period)}</span>`
      : '';
    const canDelete = person.id && (
      person.is_mine || authStore.hasPermission('agenda.manage')
    );
    return `
      <li class="agenda-person ${person.is_mine ? 'is-mine' : ''}">
        <span class="agenda-person-name">${escapeHtml(person.person_name)}${person.is_mine ? ' (moi)' : ''}</span>
        ${person.needs_workstation ? '<span class="agenda-badge agenda-badge--desk">poste</span>' : ''}
        ${person.needs_meal ? '<span class="agenda-badge agenda-badge--meal">repas</span>' : ''}
        ${periodBadge}
        ${badge ? `<span class="agenda-dot agenda-dot--${person.person_type}" title="${escapeHtml(badge)}" aria-label="${escapeHtml(badge)}"></span>` : ''}
        ${canDelete ? `<button class="agenda-person-remove" data-remove-presence="${person.id}" aria-label="Retirer ${escapeHtml(person.person_name)}">×</button>` : ''}
      </li>`;
  }

  _myPresence(day) {
    for (const room of day.rooms || []) {
      const mine = (room.presences || []).find(p => p.is_mine && p.person_type === 'user');
      if (mine) return mine;
    }
    return null;
  }

  _collectMyPresenceIds() {
    const ids = [];
    (this.data?.days || []).forEach(day => {
      for (const room of day.rooms || []) {
        const mine = (room.presences || []).find(p => p.is_mine && p.person_type === 'user');
        if (mine?.id) ids.push(mine.id);
      }
    });
    return ids;
  }

  async _clearMyPresence() {
    const ids = this._collectMyPresenceIds();
    if (!ids.length) {
      this._toast('Aucune présence à annuler', 'info');
      return false;
    }
    try {
      for (const id of ids) {
        await deletePresence(id);
      }
      return true;
    } catch (error) {
      this._toast(error.message || 'Erreur', 'error');
      return false;
    }
  }

  async _toggleMineCell({ roomId, date, field }) {
    const mine = this._minePresenceForDate(date, roomId);

    let morning = false;
    let afternoon = false;
    let desk = false;
    let meal = false;

    if (mine) {
      const period = mine.period || 'full';
      morning = period === 'morning' || period === 'full';
      afternoon = period === 'afternoon' || period === 'full';
      desk = !!mine.needs_workstation;
      meal = !!mine.needs_meal;
    }

    const wasFull = morning && afternoon;

    if (field === 'desk' || field === 'meal') {
      if (!mine) {
        this._toast('Sélectionnez d’abord une présence ce jour-là', 'error');
        return false;
      }
      if (field === 'desk') desk = !desk;
      else meal = !meal;
    } else {
      if (field === 'morning') morning = !morning;
      if (field === 'afternoon') afternoon = !afternoon;
    }

    if ((field === 'morning' || field === 'afternoon') && morning && afternoon && !wasFull) {
      desk = true;
      meal = true;
    }

    const nextPeriod = morning && afternoon ? 'full' : (morning ? 'morning' : 'afternoon');
    if (morning || afternoon) {
      const conflict = this._conflictMessage(date, roomId, nextPeriod, meal);
      if (conflict) {
        this._toast(conflict, 'error');
        return false;
      }
    }

    try {
      if (!morning && !afternoon) {
        if (mine?.id) await deletePresence(mine.id);
      } else {
        await upsertMyPresence({
          presence_date: date,
          room_id: Number(roomId),
          is_present: true,
          needs_workstation: desk,
          needs_meal: meal,
          period: nextPeriod,
        });
      }
      await this.loadPlanning();
      this.renderState();
      return true;
    } catch (error) {
      this._toast(error.message || 'Erreur', 'error');
      return false;
    }
  }

  async _bulkMineHalf({ roomId, field }) {
    const dates = this._mineGridDates().filter((iso) => {
      const weekday = parseISODate(iso).getDay();
      return weekday >= 1 && weekday <= 5;
    });
    try {
      for (const date of dates) {
        const mine = this._minePresenceForDate(date, roomId);
        let morning = false;
        let afternoon = false;
        let desk = false;
        let meal = false;
        if (mine) {
          const period = mine.period || 'full';
          morning = period === 'morning' || period === 'full';
          afternoon = period === 'afternoon' || period === 'full';
          desk = !!mine.needs_workstation;
          meal = !!mine.needs_meal;
        }
        const wasFull = morning && afternoon;
        if (field === 'morning') morning = true;
        if (field === 'afternoon') afternoon = true;
        if (morning && afternoon && !wasFull) {
          desk = true;
          meal = true;
        }
        const period = morning && afternoon ? 'full' : (morning ? 'morning' : 'afternoon');
        const conflict = this._conflictMessage(date, roomId, period, meal);
        if (conflict) {
          this._toast(conflict, 'error');
          return false;
        }
      }
      for (const date of dates) {
        const mine = this._minePresenceForDate(date, roomId);
        let morning = false;
        let afternoon = false;
        let desk = false;
        let meal = false;
        if (mine) {
          const period = mine.period || 'full';
          morning = period === 'morning' || period === 'full';
          afternoon = period === 'afternoon' || period === 'full';
          desk = !!mine.needs_workstation;
          meal = !!mine.needs_meal;
        }
        const wasFull = morning && afternoon;
        if (field === 'morning') morning = true;
        if (field === 'afternoon') afternoon = true;
        if (morning && afternoon && !wasFull) {
          desk = true;
          meal = true;
        }
        const period = morning && afternoon ? 'full' : (morning ? 'morning' : 'afternoon');
        await upsertMyPresence({
          presence_date: date,
          room_id: Number(roomId),
          is_present: true,
          needs_workstation: desk,
          needs_meal: meal,
          period,
        });
      }
      await this.loadPlanning();
      this.renderState();
      this._toast(field === 'morning' ? 'Matin sélectionné' : 'Après-midi sélectionné', 'success');
      return true;
    } catch (error) {
      this._toast(error.message || 'Erreur', 'error');
      return false;
    }
  }

  _bindCommon() {
    this.element.querySelector('[data-action="retry"]')?.addEventListener('click', async () => {
      await this.loadPlanning();
      this.renderState();
    });

    this.element.querySelectorAll('[data-view]').forEach(btn => {
      btn.addEventListener('click', async () => {
        this.view = btn.dataset.view;
        if (this.view === 'week') this.anchor = startOfWeek(new Date());
        else this.anchor = startOfMonth(new Date());
        await this.loadPlanning();
        this.renderState();
      });
    });

    this.element.querySelectorAll('[data-nav]').forEach(btn => {
      btn.addEventListener('click', async () => {
        const step = btn.dataset.nav;
        if (step === 'today') {
          this.anchor = new Date();
        } else {
          const direction = step === 'next' ? 1 : -1;
          if (this.view === 'week') this.anchor = addDays(this.anchor, 7 * direction);
          else this.anchor = new Date(this.anchor.getFullYear(), this.anchor.getMonth() + direction, 1);
        }
        await this.loadPlanning();
        this.renderState();
      });
    });
  }

  _bindMineForm() {
    this.element.querySelectorAll('[data-mine-toggle]').forEach(btn => {
      btn.addEventListener('click', async () => {
        if (btn.disabled) return;
        btn.disabled = true;
        try {
          await this._toggleMineCell({
            roomId: Number(btn.dataset.roomId),
            date: btn.dataset.date,
            field: btn.dataset.mineToggle,
          });
        } finally {
          btn.disabled = false;
        }
      });
    });

    this.element.querySelectorAll('[data-mine-bulk]').forEach(btn => {
      btn.addEventListener('click', async () => {
        if (btn.disabled) return;
        btn.disabled = true;
        try {
          await this._bulkMineHalf({
            roomId: Number(btn.dataset.roomId),
            field: btn.dataset.mineBulk,
          });
        } finally {
          btn.disabled = false;
        }
      });
    });

    this.element.querySelector('[data-action="clear-mine"]')?.addEventListener('click', async () => {
      const ok = await this._clearMyPresence();
      if (!ok) return;
      await this.loadPlanning();
      this.renderState();
      this._toast('Présence annulée', 'success');
    });
  }

  _bindFreeForm() {
    const form = this.element.querySelector('[data-agenda-free]');
    if (!form) return;
    form.addEventListener('submit', async event => {
      event.preventDefault();
      try {
        await createExternalPresence({
          presence_date: form.elements.presence_date.value,
          room_id: Number(form.elements.room_id.value),
          external_name: form.elements.external_name.value.trim(),
          needs_workstation: form.elements.needs_workstation.checked,
          period: form.elements.period?.value || 'full',
        });
      } catch (error) {
        this._toast(error.message || 'Erreur', 'error');
        return;
      }
      form.elements.external_name.value = '';
      form.elements.needs_workstation.checked = false;
      await this.loadPlanning();
      this.renderState();
      this._toast('Inscription libre ajoutée', 'success');
    });
  }

  _bindPlanning() {
    this.element.querySelectorAll('[data-day]').forEach(btn => {
      btn.addEventListener('click', () => {
        this.openDay = btn.dataset.day;
        this.renderState();
      });
    });
  }

  _bindDayPanel() {
    const overlay = this.element.querySelector('.agenda-day-overlay');
    overlay?.querySelectorAll('[data-action="close-day"]').forEach(el => {
      el.addEventListener('click', event => {
        if (event.target === el || el.classList.contains('modal-close') || el.matches('button[data-action="close-day"]')) {
          this.openDay = null;
          this.renderState();
        }
      });
    });

    this.element.querySelectorAll('[data-remove-presence]').forEach(btn => {
      btn.addEventListener('click', async () => {
        try {
          await deletePresence(Number(btn.dataset.removePresence));
        } catch (error) {
          this._toast(error.message || 'Erreur', 'error');
          return;
        }
        await this.loadPlanning();
        this.renderState();
      });
    });
  }

  _toast(message, type = 'info') {
    const existing = document.querySelector('.agenda-toast');
    if (existing) existing.remove();
    const toast = document.createElement('div');
    toast.className = `agenda-toast agenda-toast--${type}`;
    toast.setAttribute('role', 'status');
    toast.textContent = message;
    document.body.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add('is-visible'));
    setTimeout(() => {
      toast.classList.remove('is-visible');
      setTimeout(() => toast.remove(), 300);
    }, 2600);
  }
}

export function createAgendaPage(router) {
  return new AgendaPage(router);
}
