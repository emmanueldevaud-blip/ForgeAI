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
  quarter: 'Trimestre',
};

const DAY_LABELS_SHORT = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim'];
const DAY_LABELS_LONG = ['dimanche', 'lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi'];
const MONTH_LABELS = [
  'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
  'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre',
];

const SOURCE_BADGES = {
  user: '',
  external: 'externe',
  cleaning: 'ménage',
  occupant: 'occupant',
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

function startOfQuarter(date) {
  const month = Math.floor(date.getMonth() / 3) * 3;
  return new Date(date.getFullYear(), month, 1);
}

function formatDayLabel(iso) {
  const date = parseISODate(iso);
  return `${DAY_LABELS_LONG[date.getDay()]} ${date.getDate()} ${MONTH_LABELS[date.getMonth()].toLowerCase()} ${date.getFullYear()}`;
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

    this.element.innerHTML = `
      <div class="page-header agenda-header">
        <div class="page-header-left">
          <h1>Agenda</h1>
          <p class="page-subtitle">Présences et occupation des postes de travail par local Bureau.</p>
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
      ${rooms.length === 0 ? this._noRoomsHtml() : this._planningHtml(rooms, days)}
      ${this.openDay ? this._dayPanelHtml(rooms) : ''}
    `;

    this._bindCommon();
    if (rooms.length) this._bindPlanning(rooms);
    if (this.openDay) this._bindDayPanel(rooms);
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
    if (this.view === 'month') {
      return `${MONTH_LABELS[start.getMonth()]} ${start.getFullYear()}`;
    }
    const quarter = Math.floor(start.getMonth() / 3) + 1;
    return `T${quarter} ${start.getFullYear()}`;
  }

  _planningHtml(rooms, days) {
    const period = escapeHtml(this._periodLabel());
    let body;
    if (this.view === 'week') body = this._weekGrid(rooms, days);
    else if (this.view === 'month') body = this._monthGrid(rooms, days);
    else body = this._quarterGrid(rooms, days);

    return `
      <div class="agenda-period-label">${period}</div>
      <section class="card agenda-card" aria-label="Planning des présences">
        ${body}
      </section>
      <section class="agenda-legend" aria-label="Légende">
        <span class="agenda-legend-item"><span class="agenda-dot agenda-dot--people"></span> Présents</span>
        <span class="agenda-legend-item"><span class="agenda-dot agenda-dot--desk"></span> Postes de travail</span>
        <span class="agenda-legend-item"><span class="agenda-badge agenda-badge--cleaning">ménage</span></span>
        <span class="agenda-legend-item"><span class="agenda-badge agenda-badge--occupant">occupant</span></span>
      </section>`;
  }

  _weekGrid(rooms, days) {
    const dayByIso = new Map(days.map(day => [day.date, day]));
    const headers = days.map(day => {
      const date = parseISODate(day.date);
      const isToday = day.date === toISODate(new Date());
      return `<th class="agenda-day-head ${isToday ? 'is-today' : ''}" scope="col">
        <span class="agenda-day-name">${DAY_LABELS_SHORT[(date.getDay() + 6) % 7]}</span>
        <span class="agenda-day-num">${date.getDate()}</span>
      </th>`;
    }).join('');

    const rows = rooms.map(room => {
      const cells = days.map(day => {
        const counters = (dayByIso.get(day.date)?.rooms || []).find(r => r.room_id === room.id);
        const present = counters?.present_count ?? 0;
        const desks = counters?.workstation_count ?? 0;
        const capacity = counters?.capacity ?? room.workstation_capacity ?? 0;
        return `
          <td class="agenda-cell ${present ? 'has-presence' : ''}">
            <button class="agenda-cell-btn" data-day="${day.date}" data-room="${room.id}"
              aria-label="${escapeHtml(room.name)} le ${escapeHtml(formatDayLabel(day.date))} : ${present} présent(s)">
              <span class="agenda-count agenda-count--people">${present}</span>
              ${capacity ? `<span class="agenda-count agenda-count--desk ${desks > capacity ? 'is-over' : ''}">${desks}/${capacity}</span>` : (desks ? `<span class="agenda-count agenda-count--desk">${desks}</span>` : '')}
            </button>
          </td>`;
      }).join('');
      return `
        <tr>
          <th class="agenda-room-head" scope="row">
            <span class="agenda-room-name">${escapeHtml(room.name)}</span>
            <span class="agenda-room-meta">${escapeHtml(room.building_name || '')}${room.workstation_capacity ? ` · ${room.workstation_capacity} postes` : ''}</span>
          </th>
          ${cells}
        </tr>`;
    }).join('');

    return `
      <div class="agenda-scroll">
        <table class="agenda-table" role="grid">
          <thead>
            <tr>
              <th class="agenda-room-head agenda-corner" scope="col">Local</th>
              ${headers}
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
      ${this._integratedStrip(days)}`;
  }

  _monthGrid(rooms, days) {
    const dayByIso = new Map(days.map(day => [day.date, day]));
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
      cells.push(`
        <td class="agenda-month-cell ${isToday ? 'is-today' : ''} ${day.total_present ? 'has-presence' : ''}">
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

  _quarterGrid(rooms, days) {
    const months = [[], [], []];
    days.forEach(day => months[parseISODate(day.date).getMonth() % 3].push(day));

    const panels = days.length ? [months[0], months[1], months[2]].map(monthDays => {
      if (!monthDays.length) return '';
      const first = parseISODate(monthDays[0].date);
      const lead = (first.getDay() + 6) % 7;
      const cells = [];
      for (let i = 0; i < lead; i += 1) cells.push('<td class="is-empty"></td>');
      monthDays.forEach(day => {
        const date = parseISODate(day.date);
        const isToday = day.date === toISODate(new Date());
        cells.push(`
          <td class="${isToday ? 'is-today' : ''} ${day.total_present ? 'has-presence' : ''}">
            <button class="agenda-month-btn" data-day="${day.date}" aria-label="${escapeHtml(formatDayLabel(day.date))}">
              <span class="agenda-month-num">${date.getDate()}</span>
              ${day.total_present ? `<span class="agenda-month-total">${day.total_present}</span>` : ''}
            </button>
          </td>`);
      });
      while (cells.length % 7 !== 0) cells.push('<td class="is-empty"></td>');
      const weeks = [];
      for (let i = 0; i < cells.length; i += 7) weeks.push(`<tr>${cells.slice(i, i + 7).join('')}</tr>`);
      return `
        <div class="agenda-quarter-month">
          <h3>${MONTH_LABELS[first.getMonth()]} ${first.getFullYear()}</h3>
          <table class="agenda-month agenda-month--compact" role="grid">
            <thead><tr>${DAY_LABELS_SHORT.map(d => `<th scope="col">${d[0]}</th>`).join('')}</tr></thead>
            <tbody>${weeks.join('')}</tbody>
          </table>
        </div>`;
    }).join('') : '<div class="agenda-empty"><p>Aucune journée dans la période.</p></div>';

    return `<div class="agenda-quarter">${panels}</div>`;
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
    const canManage = authStore.hasPermission('agenda.manage');
    const myRoomId = this._myPresence(day)?.room_id ?? null;
    const myNeedsDesk = this._myPresence(day)?.needs_workstation ?? false;

    return `
      <div class="modal-overlay open agenda-day-overlay" data-action="close-day">
        <div class="modal open agenda-day-modal" role="dialog" aria-modal="true" aria-label="Présences du jour">
          <div class="modal-content">
            <div class="modal-header">
              <div>
                <span class="agenda-eyebrow">JOURNÉE</span>
                <h2>${escapeHtml(formatDayLabel(day.date))}</h2>
                <p class="agenda-day-totals">${day.total_present} présent(s) · ${day.total_workstations} poste(s) de travail</p>
              </div>
              <button type="button" class="modal-close" data-action="close-day" aria-label="Fermer">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
              </button>
            </div>
            <div class="modal-body agenda-day-body">
              <form class="agenda-declare" data-agenda-declare>
                <h3>Ma présence</h3>
                <div class="agenda-declare-row">
                  <label class="agenda-check">
                    <input type="checkbox" name="is_present" ${myRoomId !== null ? 'checked' : ''}>
                    <span>Présent(e)</span>
                  </label>
                  <label class="form-control-wrap">
                    <span class="visually-hidden">Local Bureau</span>
                    <select class="form-control" name="room_id" required>
                      <option value="">Choisir un local…</option>
                      ${rooms.map(room => `<option value="${room.id}" ${myRoomId === room.id ? 'selected' : ''}>${escapeHtml(room.name)}${room.building_name ? ` — ${escapeHtml(room.building_name)}` : ''}</option>`).join('')}
                    </select>
                  </label>
                  <label class="agenda-check">
                    <input type="checkbox" name="needs_workstation" ${myNeedsDesk ? 'checked' : ''}>
                    <span>Poste de travail</span>
                  </label>
                  <button class="btn btn-primary" type="submit">Enregistrer</button>
                </div>
              </form>

              ${canManage ? `
                <form class="agenda-external" data-agenda-external>
                  <h3>Ajouter une personne externe</h3>
                  <div class="agenda-declare-row">
                    <input class="form-control" name="external_name" placeholder="Nom de la personne" maxlength="200" required>
                    <select class="form-control" name="room_id" required>
                      <option value="">Local…</option>
                      ${rooms.map(room => `<option value="${room.id}">${escapeHtml(room.name)}</option>`).join('')}
                    </select>
                    <label class="agenda-check">
                      <input type="checkbox" name="needs_workstation">
                      <span>Poste</span>
                    </label>
                    <button class="btn btn-secondary" type="submit">Ajouter</button>
                  </div>
                </form>` : ''}

              <div class="agenda-day-rooms">
                ${day.rooms.map(counter => {
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
            </div>
          </div>
        </div>
      </div>`;
  }

  _personLi(person) {
    const badge = SOURCE_BADGES[person.person_type];
    const canDelete = person.id && (
      person.is_mine || authStore.hasPermission('agenda.manage')
    );
    return `
      <li class="agenda-person ${person.is_mine ? 'is-mine' : ''}">
        <span class="agenda-person-name">${escapeHtml(person.person_name)}${person.is_mine ? ' (moi)' : ''}</span>
        ${person.needs_workstation ? '<span class="agenda-badge agenda-badge--desk">poste</span>' : ''}
        ${badge ? `<span class="agenda-badge agenda-badge--${person.person_type}">${badge}</span>` : ''}
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

  _bindCommon() {
    this.element.querySelector('[data-action="retry"]')?.addEventListener('click', async () => {
      await this.loadPlanning();
      this.renderState();
    });

    this.element.querySelectorAll('[data-view]').forEach(btn => {
      btn.addEventListener('click', async () => {
        this.view = btn.dataset.view;
        if (this.view === 'week') this.anchor = startOfWeek(new Date());
        else if (this.view === 'month') this.anchor = startOfMonth(new Date());
        else this.anchor = startOfQuarter(new Date());
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
          else if (this.view === 'month') this.anchor = new Date(this.anchor.getFullYear(), this.anchor.getMonth() + direction, 1);
          else this.anchor = new Date(this.anchor.getFullYear(), this.anchor.getMonth() + 3 * direction, 1);
        }
        await this.loadPlanning();
        this.renderState();
      });
    });
  }

  _bindPlanning(rooms) {
    this.element.querySelectorAll('[data-day]').forEach(btn => {
      btn.addEventListener('click', () => {
        this.openDay = btn.dataset.day;
        this.renderState();
      });
    });
  }

  _bindDayPanel(rooms) {
    const overlay = this.element.querySelector('.agenda-day-overlay');
    overlay?.querySelectorAll('[data-action="close-day"]').forEach(el => {
      el.addEventListener('click', event => {
        if (event.target === el || el.classList.contains('modal-close')) {
          this.openDay = null;
          this.renderState();
        }
      });
    });

    this.element.querySelector('[data-agenda-declare]')?.addEventListener('submit', async event => {
      event.preventDefault();
      const form = event.currentTarget;
      const roomId = form.elements.room_id.value;
      const isPresent = form.elements.is_present.checked;
      if (isPresent && !roomId) {
        this._toast('Choisissez un local', 'error');
        return;
      }
      if (!isPresent) {
        const day = (this.data.days || []).find(d => d.date === this.openDay);
        const mine = day ? this._myPresence(day) : null;
        if (mine?.id) {
          try {
            await deletePresence(mine.id);
          } catch (error) {
            this._toast(error.message || 'Erreur', 'error');
            return;
          }
        } else {
          this._toast('Aucune présence à annuler', 'info');
          return;
        }
      } else {
        try {
          await upsertMyPresence({
            presence_date: this.openDay,
            room_id: Number(roomId),
            is_present: true,
            needs_workstation: form.elements.needs_workstation.checked,
          });
        } catch (error) {
          this._toast(error.message || 'Erreur', 'error');
          return;
        }
      }
      await this.loadPlanning();
      this.renderState();
      this._toast('Présence enregistrée', 'success');
    });

    this.element.querySelector('[data-agenda-external]')?.addEventListener('submit', async event => {
      event.preventDefault();
      const form = event.currentTarget;
      try {
        await createExternalPresence({
          presence_date: this.openDay,
          room_id: Number(form.elements.room_id.value),
          external_name: form.elements.external_name.value.trim(),
          needs_workstation: form.elements.needs_workstation.checked,
        });
      } catch (error) {
        this._toast(error.message || 'Erreur', 'error');
        return;
      }
      form.reset();
      await this.loadPlanning();
      this.renderState();
      this._toast('Personne externe ajoutée', 'success');
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
