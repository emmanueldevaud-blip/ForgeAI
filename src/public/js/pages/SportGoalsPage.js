import { createSportGoal, getSportGoalsAnalysis, listSportGoals } from '../services/sportApi.js?v=6';

const GOAL_TYPES = [
  { value: 'distance', label: 'Distance', unit: 'km' },
  { value: 'elevation', label: 'Dénivelé positif', unit: 'm' },
  { value: 'duration', label: 'Durée d’entraînement', unit: 'min' },
  { value: 'activities', label: 'Nombre d’activités', unit: 'activités' },
];

export class SportGoalsPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.goals = [];
    this.analysis = [];
    this.error = null;
    this.message = null;
    this.saving = false;
  }

  async initialize() {
    this.error = null;
    try {
      const [goals, analysis] = await Promise.all([listSportGoals(), getSportGoalsAnalysis()]);
      this.goals = Array.isArray(goals) ? goals : [];
      this.analysis = Array.isArray(analysis) ? analysis : [];
    } catch (error) {
      console.error('Erreur chargement objectifs:', error);
      this.error = error;
      this.goals = [];
      this.analysis = [];
    }
  }

  render() {
    this.element = document.createElement('div');
    this.element.className = 'page-content sport-goals';
    this._renderContent();
    return this.element;
  }

  _renderContent() {
    if (!this.element) return;
    this.element.innerHTML = `
      <div class="page-header sport-dashboard-header">
        <div class="page-header-left"><span class="sport-kicker">FORGEAI SPORT</span><h1>Objectifs</h1><p class="page-subtitle">Tes cibles d’entraînement et ce qui a été réalisé sur les 4 dernières semaines.</p></div>
      </div>
      ${this.error ? '<div class="card" role="alert"><div class="card-body">Impossible de charger les objectifs.</div></div>' : ''}
      <div class="card sport-card">
        <div class="card-header"><div><span class="sport-eyebrow">NOUVEL OBJECTIF</span><h2>Ajouter un objectif</h2></div></div>
        <div class="card-body">
          <form data-goal-form>
            <div class="form-row">
              <label><span>Nom</span><input class="form-control" name="name" maxlength="200" placeholder="Marathon d’automne" required></label>
              <label><span>Type</span>
                <select class="form-control" name="goal_type">${GOAL_TYPES.map(type => `<option value="${type.value}">${type.label}</option>`).join('')}</select>
              </label>
            </div>
            <div class="form-row">
              <label><span>Cible</span><input class="form-control" name="target_value" type="number" min="0" step="0.1" placeholder="50"></label>
              <label><span>Unité</span><input class="form-control" name="unit" maxlength="30" placeholder="km"></label>
            </div>
            <div class="form-row">
              <label><span>Date cible</span><input class="form-control" name="target_date" type="date"></label>
              <label></label>
            </div>
            <div class="form-actions">
              <button class="btn btn-primary" type="submit" ${this.saving ? 'disabled' : ''}>${this.saving ? 'Enregistrement…' : 'Créer l’objectif'}</button>
              <span data-goal-message role="status">${this._escape(this.message || '')}</span>
            </div>
          </form>
        </div>
      </div>
      <div class="sport-dashboard-grid sport-dashboard-grid--main">
        ${this.goals.length
          ? this.goals.map(goal => this._goalCard(goal)).join('')
          : `<div class="card sport-card"><div class="card-body">${this._empty('Aucun objectif', 'Crée ton premier objectif : distance, dénivelé, durée ou nombre d’activités.')}</div></div>`}
      </div>
    `;
    this._bindEvents();
  }

  _bindEvents() {
    const form = this.element.querySelector('[data-goal-form]');
    if (!form) return;

    const typeSelect = form.elements.goal_type;
    const unitInput = form.elements.unit;
    const syncUnit = () => {
      const type = GOAL_TYPES.find(item => item.value === typeSelect.value);
      const unitIsPreset = GOAL_TYPES.some(item => item.unit === unitInput.value.trim());
      if (type && (!unitInput.value.trim() || unitIsPreset)) {
        unitInput.value = type.unit;
      }
    };
    typeSelect.addEventListener('change', syncUnit);
    syncUnit();

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (this.saving) return;
      const data = Object.fromEntries(new FormData(form).entries());
      const payload = {
        name: (data.name || '').trim(),
        goal_type: data.goal_type,
        target_value: data.target_value ? Number(data.target_value) : null,
        unit: (data.unit || '').trim() || null,
        target_date: data.target_date || null,
      };
      if (!payload.name) return;
      this.saving = true;
      this.message = null;
      const button = form.querySelector('button[type="submit"]');
      if (button) {
        button.disabled = true;
        button.textContent = 'Enregistrement…';
      }
      try {
        await createSportGoal(payload);
        this.message = 'Objectif créé.';
      } catch (error) {
        this.message = error.data?.detail || error.message || 'Erreur lors de la création.';
      } finally {
        this.saving = false;
      }
      await this.initialize();
      this._renderContent();
    });
  }

  _goalCard(goal) {
    const analysis = this.analysis.find(item => item.goal_id === goal.id) || {};
    const recent = analysis.recent_28_days || {};
    const type = GOAL_TYPES.find(item => item.value === goal.goal_type);
    const target = goal.target_value != null
      ? `${goal.target_value} ${goal.unit || (type ? type.unit : '')}`.trim()
      : '—';
    const days = analysis.days_remaining;
    return `
      <article class="card sport-card">
        <div class="card-header"><div><span class="sport-eyebrow">${this._escape(type ? type.label : goal.goal_type || 'Objectif')}</span><h2>${this._escape(goal.name)}</h2></div></div>
        <div class="card-body">
          <div class="sport-goal-row"><span>Cible</span><strong>${this._escape(target)}</strong></div>
          <div class="sport-goal-row"><span>Réalisé sur 28 jours</span><strong>${this._done(goal.goal_type, recent)}</strong></div>
          ${goal.target_date ? `<div class="sport-goal-row"><span>Date cible</span><strong>${this._date(goal.target_date)}${days != null ? ` · ${days >= 0 ? `${days} jours restants` : `${Math.abs(days)} jours de retard`}` : ''}</strong></div>` : ''}
          <div class="sport-goal-row"><span>Activités compatibles</span><strong>${analysis.compatible_activity_count ?? '—'}</strong></div>
        </div>
      </article>
    `;
  }

  _done(goalType, recent) {
    if (!recent || recent.activity_count == null) return '—';
    if (goalType === 'distance' && recent.distance_m != null) return `${(recent.distance_m / 1000).toFixed(1)} km`;
    if (goalType === 'elevation' && recent.elevation_gain_m != null) return `${Math.round(recent.elevation_gain_m)} m`;
    if (goalType === 'duration' && recent.duration_seconds != null) return `${Math.round(recent.duration_seconds / 60)} min`;
    if (goalType === 'activities') return `${recent.activity_count}`;
    if (recent.distance_m != null) return `${(recent.distance_m / 1000).toFixed(1)} km`;
    return `${recent.activity_count} activités`;
  }

  _date(value) {
    return value ? new Date(value).toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' }) : '';
  }

  _empty(title, message) {
    return `<div class="sport-empty"><span class="sport-empty-mark">○</span><strong>${title}</strong><p>${message}</p></div>`;
  }

  _escape(value) {
    const element = document.createElement('div');
    element.textContent = value ?? '';
    return element.innerHTML;
  }

  destroy() {
    this.element = null;
  }
}

export function createSportGoalsPage(router) {
  return new SportGoalsPage(router);
}
