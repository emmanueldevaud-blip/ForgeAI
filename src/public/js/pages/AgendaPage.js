import { authStore } from '../stores/auth.js';
import {
  autoAssignMyPresences,
  createExternalPresence,
  deletePresence,
  getAgendaPlanning,
  updatePresence,
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
    this.openRoom = null;
    this.editCell = null;
    this.addPersonOpen = false;
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
      await this._maybeAutoAssign();
    } catch (error) {
      this.error = error;
    }
  }

  async _maybeAutoAssign() {
    if (!this.data?.start_date || !this.data?.end_date) return;
    const key = `agenda:auto-assign:2:${this.view}:${toISODate(this.anchor)}`;
    if (sessionStorage.getItem(key)) return;
    try {
      const result = await autoAssignMyPresences(this.data.start_date, this.data.end_date);
      if (result && (result.created > 0 || result.skipped > 0)) {
        sessionStorage.setItem(key, '1');
      }
      if (result?.created > 0) {
        this.data = await getAgendaPlanning(this.view, toISODate(this.anchor));
      }
    } catch {
      // auto-assign best effort: sera retenté au prochain chargement
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
          <p class="page-subtitle">Vos présences, le planning par bureau${canManage ? ' et les inscriptions libres' : ''}.</p>
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
              <p class="agenda-section-desc">Une ligne par personne, colonne par jour et par demi-journée. Cliquez sur une case pour gérer l’inscription, sur un jour pour voir le détail.</p>
            </div>
            <div class="agenda-planning-toolbar">
              <div class="agenda-period-label">${escapeHtml(this._periodLabel())}</div>
              ${canManage ? `
                <button type="button" class="btn btn-primary btn-sm" data-action="add-person-to-planning" aria-label="Ajouter une personne au planning">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
                  Ajouter une personne
                </button>` : ''}
          </header>
          <section class="card agenda-card" aria-label="Planning des présences">
            ${this._planningBody(days)}
          </section>
          <section class="agenda-legend" aria-label="Légende">
            <span class="agenda-legend-item"><span class="agenda-dot agenda-dot--user"></span> inscription</span>
            <span class="agenda-legend-item"><span class="agenda-dot agenda-dot--external"></span> externe</span>
            <span class="agenda-legend-item"><span class="agenda-dot agenda-dot--cleaning"></span> volontaire</span>
            <span class="agenda-legend-item"><span class="agenda-dot agenda-dot--occupant"></span> occupation</span>
          </section>
        </section>

        ${canManage ? `
        <section class="card agenda-section agenda-section--free" aria-labelledby="agenda-free-title">
          <header class="agenda-section-header">
            <div>
              <h2 id="agenda-free-title">Inscriptions libres</h2>
              <p class="agenda-section-desc">Ajoutez une personne sans compte utilisateur (visiteur, intervenant…).</p>
            </div>
          </header>
          <div class="card-body agenda-section-body">
            ${this._freeFormHtml(rooms, freeDate)}
          </div>
        </section>` : ''}
      `}

      ${this.openDay ? this._dayPanelHtml(rooms) : ''}
      ${this.editCell ? this._cellEditorHtml(rooms) : ''}
      ${this.addPersonOpen ? this._addPersonModalHtml() : ''}
    `;

    this._bindCommon();
    if (rooms.length) {
      this._bindMineForm();
      this._bindPlanning();
      if (canManage) this._bindFreeForm();
    }
    if (this.openDay) this._bindDayPanel();
    if (this.editCell) this._bindCellEditor();
    if (this.addPersonOpen) this._bindAddPersonModal();
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

  _planningBody(days) {
    const dates = this._mineGridDates();
    const people = this._peopleList();
    const dayByIso = new Map(days.map(day => [day.date, day]));
    const today = toISODate(new Date());
    const isMonth = this.view === 'month';
    const canManage = authStore.hasPermission('agenda.manage');

    if (!people.length) {
      return '<div class="card-body agenda-empty"><p class="agenda-none">Aucune inscription sur cette période.</p></div>';
    }

    const head = `
      <thead>
        <tr>
          <th class="agenda-room-head agenda-corner" rowspan="2" scope="col">Personne</th>
          ${dates.map(iso => {
            const dayDate = parseISODate(iso);
            const known = dayByIso.has(iso);
            return `<th class="agenda-day-head ${iso === today ? 'is-today' : ''}" colspan="2" scope="col" ${known ? `data-day="${iso}"` : ''} title="${escapeHtml(formatDayLabel(iso))}">
              <span class="agenda-day-name">${DAY_LABELS_SHORT[(dayDate.getDay() + 6) % 7]}</span>
              <span class="agenda-day-num">${dayDate.getDate()}</span>
            </th>`;
          }).join('')}
        </tr>
        <tr>
          ${dates.map(() => '<th class="agenda-half-subhead" scope="col">Matin</th><th class="agenda-half-subhead" scope="col">Après-midi</th>').join('')}
        </tr>
      </thead>`;

    const rows = people.map(person => `
      <tr>
        <th class="agenda-room-head agenda-person-head" scope="row" title="${escapeHtml(SOURCE_BADGES[person.type] || person.type)}">
          <span class="agenda-room-name">${escapeHtml(person.name)}${person.isMine ? ' (moi)' : ''}</span>
          <span class="agenda-room-meta">${escapeHtml(SOURCE_BADGES[person.type] || person.type)}</span>
        </th>
        ${dates.map(iso => ['morning', 'afternoon']
          .map(half => this._personCellHtml(person, iso, half, canManage, isMonth))
          .join('')).join('')}
      </tr>`).join('');

    return `
      <div class="agenda-scroll">
        <table class="agenda-table agenda-table--people ${isMonth ? 'agenda-table--people-month' : ''}" role="grid" aria-label="Planning des inscrits">
          ${head}
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  _personCellHtml(person, iso, half, canManage, isMonth) {
    const inPeriod = (this.data?.days || []).some(day => day.date === iso);
    const editable = inPeriod && this._canEditPerson(person, canManage);
    const entry = this._presenceCovering(person, iso, half);
    const halfLabel = half === 'morning' ? 'Matin' : 'Après-midi';
    const details = [];
    let label = '';
    if (entry) {
      const room = this._roomById(entry.roomId);
      label = room ? room.name : (SOURCE_BADGES[person.type] || '');
      details.push(`${person.name} — ${formatDayLabel(iso)} · ${halfLabel}`);
      details.push(`Local : ${label}`);
      if (entry.presence.needs_workstation) details.push('Poste');
      if (entry.presence.needs_meal) details.push('Repas');
    } else if (editable) {
      details.push(`Inscrire ${person.name} — ${formatDayLabel(iso)} · ${halfLabel}`);
    }
    return `
      <td class="agenda-cell ${entry ? 'has-presence' : ''}">
        <button type="button" class="agenda-cell-btn agenda-people-cell ${entry ? 'has-presence' : 'is-empty'} ${isMonth ? 'is-compact' : ''}"
          ${editable ? '' : 'disabled'}
          data-cell-person="${escapeHtml(person.key)}" data-cell-date="${iso}" data-cell-half="${half}"
          title="${escapeHtml(details.join(' · '))}"
          aria-label="${escapeHtml(details.join(' · ') || `${person.name} — ${formatDayLabel(iso)} · ${halfLabel}`)}">
          ${entry
            ? `<span class="agenda-people-cell-room">${escapeHtml(label)}</span>${entry.presence.needs_meal ? '<span class="agenda-people-cell-flag">repas</span>' : ''}${entry.presence.needs_workstation ? '<span class="agenda-people-cell-flag">poste</span>' : ''}`
            : (editable ? '<span class="agenda-people-cell-flag is-add">+</span>' : '')}
        </button>
      </td>`;
  }

  _peopleList() {
    const byNormName = new Map();
    const ensure = (type, personId, name, isMine, date, roomId, period, presence) => {
      const norm = this._normalizePersonName(name);
      const existing = byNormName.get(norm);
      if (existing) {
        existing.presences.push({ date, roomId, period, presence });
        if (isMine) existing.isMine = true;
        existing.sourceTypes.add(type);
        return;
      }
      byNormName.set(norm, {
        normName: norm,
        displayName: name,
        type: type === 'user' ? 'user' : type,
        personId: personId ?? null,
        isMine: isMine || false,
        sourceTypes: new Set([type]),
        presences: [{ date, roomId, period, presence }],
      });
    };
    for (const day of this.data?.days || []) {
      for (const counter of day.rooms || []) {
        for (const presence of counter.presences || []) {
          ensure(presence.person_type, presence.person_id, presence.person_name, presence.is_mine,
            day.date, counter.room_id ?? presence.room_id ?? null, presence.period || 'full', presence);
        }
      }
      for (const presence of day.integrated || []) {
        ensure(presence.person_type, presence.person_id, presence.person_name, false,
          day.date, presence.room_id ?? null, presence.period || 'full', presence);
      }
    }
    const people = [...byNormName.values()]
      .sort((a, b) => a.displayName.localeCompare(b.displayName, 'fr'))
      .map(p => ({
        key: `${p.type}:${p.personId ?? p.displayName}`,
        name: p.displayName,
        type: p.type,
        personId: p.personId,
        isMine: p.isMine,
        sourceTypes: p.sourceTypes,
        presences: p.presences,
      }));
    return people;
  }

  _normalizePersonName(name) {
    return String(name ?? '').toLowerCase().trim().replace(/\s+/g, ' ');
  }

  _presenceCovering(person, iso, half) {
    return person.presences.find(entry => entry.date === iso && (entry.period === 'full' || entry.period === half)) || null;
  }

  _canEditPerson(person, canManage = authStore.hasPermission('agenda.manage')) {
    if (person.type === 'external') return canManage;
    if (person.type !== 'user') return false;
    return canManage || person.isMine;
  }

  _roomById(roomId) {
    if (roomId == null) return null;
    return (this.data?.rooms || []).find(room => String(room.id) === String(roomId)) || null;
  }

  _cellEditorHtml(rooms) {
    const person = this._peopleList().find(item => item.key === this.editCell.key);
    if (!person) return '';
    const { date, half } = this.editCell;
    const halfLabel = half === 'morning' ? 'Matin' : 'Après-midi';
    const entry = this._presenceCovering(person, date, half);
    const editable = this._canEditPerson(person);
    const selectedRoomId = entry?.roomId ?? rooms[0]?.id ?? null;
    const entryRoom = entry ? this._roomById(entry.roomId) : null;
    const entryLabel = entry ? (entryRoom ? entryRoom.name : (SOURCE_BADGES[person.type] || '')) : '';

    return `
      <div class="modal-overlay open agenda-cell-overlay" data-action="close-cell">
        <div class="modal open agenda-day-modal" role="dialog" aria-modal="true" aria-label="Inscription">
          <div class="modal-content agenda-day-modal-content">
            <div class="modal-header agenda-day-header">
              <div class="agenda-day-header-text">
                <span class="agenda-eyebrow">INSCRIPTION</span>
                <h2>${escapeHtml(person.name)} · ${halfLabel}</h2>
                <p class="agenda-day-totals">${escapeHtml(formatDayLabel(date))}${entry ? ` — ${escapeHtml(entryLabel)}` : ' — aucune inscription'}</p>
              </div>
              <button type="button" class="modal-close" data-action="close-cell" aria-label="Fermer">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
              </button>
            </div>
            <div class="modal-body agenda-day-body">
              ${editable ? `
                <form data-agenda-cell-form>
                  <div class="agenda-cell-form-grid">
                    <label class="form-control-wrap">
                      <span>Local</span>
                      <select class="form-control" name="room_id" required>
                        ${rooms.map(room => `
                          <option value="${room.id}" ${String(selectedRoomId) === String(room.id) ? 'selected' : ''}>
                            ${escapeHtml(room.name)}${room.building_name ? ` — ${escapeHtml(room.building_name)}` : ''}
                          </option>`).join('')}
                      </select>
                    </label>
                    <label class="agenda-check">
                      <input type="checkbox" name="needs_workstation" ${entry?.presence.needs_workstation ? 'checked' : ''}>
                      <span>Poste de travail</span>
                    </label>
                    <label class="agenda-check">
                      <input type="checkbox" name="needs_meal" ${entry?.presence.needs_meal ? 'checked' : ''}>
                      <span>Repas</span>
                    </label>
                  </div>
                  ${entry?.presence.period === 'full'
                    ? '<p class="agenda-field-help">Cette personne est inscrite toute la journée : le changement de local s’applique à la journée entière, sinon seule la période affichée est retirée.</p>'
                    : ''}
                </form>`
              : `
                <p class="agenda-none">${entry ? `Inscription : ${escapeHtml(entryLabel)}` : 'Aucune inscription sur ce créneau.'}</p>
                <p class="agenda-field-help">Lecture seule : seuls les gestionnaires de l’agenda peuvent modifier cette ligne.</p>
              `}
            </div>
            <div class="modal-footer agenda-day-footer">
              ${editable && entry ? '<button class="btn btn-danger" type="button" data-action="remove-cell">Retirer</button>' : ''}
              <button class="btn btn-secondary" type="button" data-action="close-cell">Annuler</button>
              ${editable ? '<button class="btn btn-primary" type="button" data-action="save-cell">Enregistrer</button>' : ''}
            </div>
          </div>
        </div>
      </div>`;
  }

  _addPersonModalHtml() {
    const canManage = authStore.hasPermission('agenda.manage');
    if (!canManage) return '';
    const today = toISODate(new Date());
    const futureDays = (this.data?.days || [])
      .filter(d => d.date >= today)
      .map(d => d.date);
    if (!futureDays.length) return '';
    const userOptions = (authStore.currentUser?.permissions || [])
      .includes('agenda.access')
      ? '' : '';
    return `
      <div class="modal-overlay open agenda-add-person-overlay" data-action="close-add-person">
        <div class="modal open agenda-day-modal" role="dialog" aria-modal="true" aria-label="Ajouter une personne">
          <div class="modal-content agenda-day-modal-content">
            <div class="modal-header agenda-day-header">
              <div class="agenda-day-header-text">
                <span class="agenda-eyebrow">AJOUTER UNE PERSONNE</span>
                <h2>Inscrire au planning</h2>
              </div>
              <button type="button" class="modal-close" data-action="close-add-person" aria-label="Fermer">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
              </button>
            </div>
            <div class="modal-body agenda-day-body">
              <form data-agenda-add-person-form>
                <div class="agenda-add-person-grid">
                  <label class="form-control-wrap">
                    <span>Personne</span>
                    <select class="form-control" name="user_id" required>
                      <option value="">Choisir un utilisateur…</option>
                    </select>
                  </label>
                  <label class="form-control-wrap">
                    <span>Date</span>
                    <input class="form-control" type="date" name="presence_date" value="${futureDays[0]}" min="${today}" required>
                  </label>
                  <label class="form-control-wrap">
                    <span>Période</span>
                    <select class="form-control" name="period" required>
                      <option value="morning">Matin</option>
                      <option value="afternoon">Après-midi</option>
                      <option value="full">Journée</option>
                    </select>
                  </label>
                  <label class="form-control-wrap">
                    <span>Local</span>
                    <select class="form-control" name="room_id" required>
                      <option value="">Choisir un local…</option>
                      ${(this.data?.rooms || []).map(room => `
                        <option value="${room.id}">${escapeHtml(room.name)}${room.building_name ? ` — ${escapeHtml(room.building_name)}` : ''}</option>`).join('')}
                    </select>
                  </label>
                  <label class="agenda-check">
                    <input type="checkbox" name="needs_workstation">
                    <span>Poste de travail</span>
                  </label>
                  <label class="agenda-check">
                    <input type="checkbox" name="needs_meal">
                    <span>Repas</span>
                  </label>
                </div>
              </form>
            </div>
            <div class="modal-footer agenda-day-footer">
              <button class="btn btn-secondary" type="button" data-action="close-add-person">Annuler</button>
              <button class="btn btn-primary" type="button" data-action="save-add-person">Ajouter l'inscription</button>
            </div>
          </div>
        </div>
      </div>`;
  }

  _bindCellEditor() {
    const overlay = this.element.querySelector('.agenda-cell-overlay');
    overlay?.addEventListener('click', event => {
      if (event.target === overlay) {
        this.editCell = null;
        this.renderState();
      }
    });
    this.element.querySelectorAll('[data-action="close-cell"]').forEach(el => {
      el.addEventListener('click', () => {
        this.editCell = null;
        this.renderState();
      });
    });
    this.element.querySelector('[data-action="save-cell"]')?.addEventListener('click', () => this._saveCellEditor());
    this.element.querySelector('[data-action="remove-cell"]')?.addEventListener('click', () => this._removeCellEditor());
  }

  _bindAddPersonModal() {
    const overlay = this.element.querySelector('.agenda-add-person-overlay');
    overlay?.addEventListener('click', event => {
      if (event.target === overlay) {
        this.addPersonOpen = false;
        this.renderState();
      }
    });
    this.element.querySelectorAll('[data-action="close-add-person"]').forEach(el => {
      el.addEventListener('click', () => {
        this.addPersonOpen = false;
        this.renderState();
      });
    });
    this.element.querySelector('[data-action="save-add-person"]')?.addEventListener('click', () => this._saveAddPersonModal());
    this._populateAddPersonUsers();
  }

  async _populateAddPersonUsers() {
    const select = this.element.querySelector('[data-agenda-add-person-form] select[name="user_id"]');
    if (!select) return;
    try {
      const token = document.cookie.match(/access_token=([^;]+)/)?.[1] || '';
      const response = await fetch('/agenda/users', {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (!response.ok) throw new Error('Impossible de charger les utilisateurs');
      const data = await response.json();
      const users = (data.users || []).filter(u => u.is_active);
      select.innerHTML = '<option value="">Choisir un utilisateur…</option>' +
        users.map(u => `<option value="${u.id}">${escapeHtml(u.full_name || u.username)}${u.email ? ` <${u.email}>` : ''}</option>`).join('');
    } catch (error) {
      select.innerHTML = '<option value="">Erreur de chargement</option>';
      console.error(error);
    }
  }

  async _saveAddPersonModal() {
    const form = this.element.querySelector('[data-agenda-add-person-form]');
    if (!form) return;
    const userId = Number(form.elements.user_id.value);
    const date = form.elements.presence_date.value;
    const roomId = Number(form.elements.room_id.value);
    const period = form.elements.period.value;
    const needsWorkstation = form.elements.needs_workstation.checked;
    const needsMeal = form.elements.needs_meal.checked;
    if (!userId || !date || !roomId) {
      this._toast('Champs obligatoires manquants', 'error');
      return;
    }
    try {
      await upsertMyPresence({
        presence_date: date,
        room_id: roomId,
        is_present: true,
        needs_workstation: needsWorkstation,
        needs_meal: needsMeal,
        period: period,
        user_id: userId,
      });
      await this.loadPlanning();
      this.addPersonOpen = false;
      this.renderState();
      this._toast('Inscription ajoutée', 'success');
    } catch (error) {
      this._toast(error.message || 'Erreur', 'error');
    }
  }

  _cellEditorContext() {
    const person = this._peopleList().find(item => item.key === this.editCell?.key);
    if (!person || !this.editCell) return null;
    const { date, half } = this.editCell;
    return { person, date, half, entry: this._presenceCovering(person, date, half) };
  }

  async _createPersonPresence(person, { date, roomId, half, needsWorkstation, needsMeal }) {
    if (person.type === 'external') {
      await createExternalPresence({
        presence_date: date,
        room_id: roomId,
        external_name: person.name,
        needs_workstation: needsWorkstation,
        needs_meal: needsMeal,
        period: half,
      });
      return;
    }
    await upsertMyPresence({
      presence_date: date,
      room_id: roomId,
      is_present: true,
      needs_workstation: needsWorkstation,
      needs_meal: needsMeal,
      period: half,
      user_id: person.personId,
    });
  }

  async _saveCellEditor() {
    const form = this.element.querySelector('[data-agenda-cell-form]');
    const context = this._cellEditorContext();
    if (!form || !context) return;
    const { person, date, half, entry } = context;
    const roomId = Number(form.elements.room_id.value);
    const needsWorkstation = form.elements.needs_workstation.checked;
    const needsMeal = form.elements.needs_meal.checked;
    const otherHalf = half === 'morning' ? 'afternoon' : 'morning';
    try {
      if (!entry) {
        await this._createPersonPresence(person, { date, roomId, half, needsWorkstation, needsMeal });
      } else if (entry.roomId === roomId) {
        await updatePresence(entry.presence.id, {
          needs_workstation: needsWorkstation,
          needs_meal: needsMeal,
        });
      } else if (entry.period === half) {
        await updatePresence(entry.presence.id, {
          room_id: roomId,
          needs_workstation: needsWorkstation,
          needs_meal: needsMeal,
        });
      } else {
        await updatePresence(entry.presence.id, { period: otherHalf });
        await this._createPersonPresence(person, { date, roomId, half, needsWorkstation, needsMeal });
      }
      await this.loadPlanning();
      this.editCell = null;
      this.renderState();
      this._toast('Inscription enregistrée', 'success');
    } catch (error) {
      this._toast(error.message || 'Erreur', 'error');
    }
  }

  async _removeCellEditor() {
    const context = this._cellEditorContext();
    if (!context || !context.entry) return;
    const { person, date, half, entry } = context;
    try {
      if (entry.period === 'full') {
        const otherHalf = half === 'morning' ? 'afternoon' : 'morning';
        await updatePresence(entry.presence.id, { period: otherHalf });
      } else if (person.type === 'user' && person.isMine) {
        await upsertMyPresence({
          presence_date: date,
          room_id: entry.roomId,
          is_present: false,
        });
      } else {
        await deletePresence(entry.presence.id);
      }
      await this.loadPlanning();
      this.editCell = null;
      this.renderState();
      this._toast('Inscription retirée', 'success');
    } catch (error) {
      this._toast(error.message || 'Erreur', 'error');
    }
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
                  ${(() => {
                    const counters = day.rooms.filter(counter => counter.presences.length || counter.present_count);
                    if (this.openRoom != null) {
                      counters.sort((a, b) =>
                        (String(b.room_id) === String(this.openRoom) ? 1 : 0) -
                        (String(a.room_id) === String(this.openRoom) ? 1 : 0));
                    }
                    return counters.map(counter => {
                    const room = rooms.find(r => r.id === counter.room_id);
                    return `
                      <section class="agenda-room-block${this.openRoom != null && String(counter.room_id) === String(this.openRoom) ? ' is-selected' : ''}">
                        <header>
                          <h3>${escapeHtml(room?.name || `Local #${counter.room_id}`)}${room?.building_name ? `<small class="agenda-room-building">${escapeHtml(room.building_name)}</small>` : ''}</h3>
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
                    }).join('');
                  })()}
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
        ${canDelete ? `<button class="agenda-person-remove" data-remove-presence="${person.id}"${person.is_mine ? ' data-mine="1"' : ''} aria-label="Retirer ${escapeHtml(person.person_name)}">×</button>` : ''}
      </li>`;
  }

  _myPresence(day) {
    for (const room of day.rooms || []) {
      const mine = (room.presences || []).find(p => p.is_mine && p.person_type === 'user');
      if (mine) return mine;
    }
    return null;
  }

  _collectMyPresences() {
    const list = [];
    (this.data?.days || []).forEach(day => {
      for (const room of day.rooms || []) {
        const mine = (room.presences || []).find(p => p.is_mine && p.person_type === 'user');
        if (mine?.id) list.push({ presence_date: day.date, room_id: room.room_id });
      }
    });
    return list;
  }

  _findMyPresenceLocation(presenceId) {
    for (const day of this.data?.days || []) {
      for (const room of day.rooms || []) {
        const mine = (room.presences || []).find(
          p => p.id === presenceId && p.is_mine && p.person_type === 'user'
        );
        if (mine) return { presence_date: day.date, room_id: room.room_id };
      }
    }
    return null;
  }

  async _clearMyPresence() {
    const mine = this._collectMyPresences();
    if (!mine.length) {
      this._toast('Aucune présence à annuler', 'info');
      return false;
    }
    try {
      for (const presence of mine) {
        await upsertMyPresence({ ...presence, is_present: false });
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
        if (mine?.id) {
          await upsertMyPresence({
            presence_date: date,
            room_id: Number(roomId),
            is_present: false,
          });
        }
      } else {
        if (date < toISODate(new Date())) {
          this._toast('Impossible de vous inscrire pour une date passée', 'error');
          return false;
        }
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
    const todayIso = toISODate(new Date());
    const dates = this._mineGridDates().filter((iso) => {
      if (iso < todayIso) return false;
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
    this.element.querySelectorAll('th[data-day]').forEach(head => {
      head.addEventListener('click', () => {
        this.openDay = head.dataset.day;
        this.openRoom = null;
        this.renderState();
      });
    });
    this.element.querySelectorAll('[data-cell-person]').forEach(btn => {
      btn.addEventListener('click', () => {
        if (btn.disabled) return;
        this.editCell = {
          key: btn.dataset.cellPerson,
          date: btn.dataset.cellDate,
          half: btn.dataset.cellHalf,
        };
        this.renderState();
      });
    });
    this.element.querySelector('[data-action="add-person-to-planning"]')?.addEventListener('click', () => {
      this.addPersonOpen = true;
      this.renderState();
    });
  }

  _bindDayPanel() {
    const overlay = this.element.querySelector('.agenda-day-overlay');
    overlay?.querySelectorAll('[data-action="close-day"]').forEach(el => {
      el.addEventListener('click', event => {
        if (event.target === el || el.classList.contains('modal-close') || el.matches('button[data-action="close-day"]')) {
          this.openDay = null;
          this.openRoom = null;
          this.renderState();
        }
      });
    });

    this.element.querySelectorAll('[data-remove-presence]').forEach(btn => {
      btn.addEventListener('click', async () => {
        try {
          const presenceId = Number(btn.dataset.removePresence);
          if (btn.dataset.mine === '1') {
            const location = this._findMyPresenceLocation(presenceId);
            if (location) {
              await upsertMyPresence({ ...location, is_present: false });
            } else {
              await deletePresence(presenceId);
            }
          } else {
            await deletePresence(presenceId);
          }
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
