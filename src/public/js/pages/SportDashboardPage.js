import { askSportCoach, getSportAthleteProfile, getSportCoachConversation, getSportDashboard, listSportCoachConversations, updateSportHeartRateConfig } from '../services/sportApi.js?v=3';

const PERIODS = [
  { value: 7, label: '7 jours' },
  { value: 28, label: '4 semaines' },
  { value: 90, label: '3 mois' },
  { value: 365, label: 'Année' },
];

const SPORT_LABELS = {
  running: 'Course', trail: 'Trail', cycling: 'Vélo', hiking: 'Randonnée',
  swimming: 'Natation', walking: 'Marche', other: 'Autre',
};

export class SportDashboardPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.data = null;
    this.period = 28;
    this.metric = 'distance_m';
    this.error = null;
    this.conversationId = null;
    this.conversations = [];
    this.messages = [];
    this.profile = null;
  }

  async initialize() {
    this.error = null;
    try {
      this.data = await getSportDashboard(this.period);
    } catch (error) {
      this.error = error;
    }
    try {
      this.conversations = await listSportCoachConversations();
    } catch (error) {
      this.conversations = [];
    }
    try {
      this.profile = await getSportAthleteProfile();
    } catch (error) {
      this.profile = null;
    }
  }

  render() {
    this.element = document.createElement('div');
    this.element.className = 'page-content sport-dashboard';
    this._renderContent();
    return this.element;
  }

  _renderContent() {
    if (this.error) {
      this.element.innerHTML = '<div class="card" role="alert"><div class="card-body sport-empty"><h2>Impossible de charger le dashboard</h2><p>Les données sportives ne sont pas disponibles pour le moment.</p></div></div>';
      return;
    }
    const data = this.data || {};
    const summary = data.summary || {};
    this.element.innerHTML = `
      <div class="page-header sport-dashboard-header">
        <div class="page-header-left"><span class="sport-kicker">FORGEAI SPORT</span><h1>Ton entraînement</h1><p class="page-subtitle">Une vue claire de ton volume, de ta régularité et de ta progression.</p></div>
        <div class="sport-periods" role="group" aria-label="Période d'analyse">
          ${PERIODS.map(item => `<button class="btn btn-sm ${item.value === this.period ? 'btn-primary' : 'btn-secondary'}" data-period="${item.value}" aria-pressed="${item.value === this.period}">${item.label}</button>`).join('')}
        </div>
      </div>
      <section class="sport-summary-grid" aria-label="Résumé de la période">
        ${this._summaryCard('Distance', this._distance(summary.distance_m), this._trendFor(data, 'distance_m'), 'route')}
        ${this._summaryCard('Dénivelé positif', this._elevationValue(summary.elevation_gain_m), this._trendFor(data, 'elevation_gain_m'), 'mountain')}
        ${this._summaryCard('Temps d’entraînement', this._duration(summary.duration_seconds), this._trendFor(data, 'duration_seconds'), 'clock')}
        ${this._summaryCard('Activités', summary.activity_count ?? null, this._trendFor(data, 'activity_count'), 'activity')}
        ${summary.avg_pace_sec_km != null ? this._summaryCard('Allure moyenne', this._pace(summary.avg_pace_sec_km), this._trendFor(data, 'avg_pace_sec_km'), 'pace') : ''}
        ${summary.avg_heart_rate != null ? this._summaryCard('FC moyenne', `${Math.round(summary.avg_heart_rate)} bpm`, this._trendFor(data, 'avg_heart_rate'), 'heart') : ''}
      </section>
      ${this._trendStrip(data)}
      ${this._analysisFindings(data.analysis || {})}
      <section class="sport-dashboard-grid sport-dashboard-grid--main">
        <div class="card sport-card sport-card--wide">
          <div class="card-header sport-card-header"><div><span class="sport-eyebrow">CHARGE D’ENTRAÎNEMENT</span><h2>Volume dans le temps</h2></div><select class="form-control sport-metric-select" data-metric aria-label="Métrique du graphique"><option value="distance_m" ${this.metric === 'distance_m' ? 'selected' : ''}>Distance</option><option value="elevation_gain_m" ${this.metric === 'elevation_gain_m' ? 'selected' : ''}>Dénivelé</option><option value="duration_seconds" ${this.metric === 'duration_seconds' ? 'selected' : ''}>Durée</option></select></div>
          <div class="card-body">${this._dailyChart(data.daily || [])}</div>
        </div>
        <div class="card sport-card"><div class="card-header"><div><span class="sport-eyebrow">RÉGULARITÉ</span><h2>Calendrier</h2></div></div><div class="card-body">${this._calendar(data.calendar || [])}</div></div>
      </section>
      <section class="sport-dashboard-grid sport-dashboard-grid--main">
        <div class="card sport-card sport-card--wide"><div class="card-header"><div><span class="sport-eyebrow">TENDANCE</span><h2>Dernières semaines</h2></div></div><div class="card-body">${this._weeklyChart(data.weekly || [])}</div></div>
        <div class="card sport-card"><div class="card-header"><div><span class="sport-eyebrow">RÉPARTITION</span><h2>Sports pratiqués</h2></div></div><div class="card-body">${this._sports(data.sports || [])}</div></div>
      </section>
      <section class="sport-dashboard-grid sport-dashboard-grid--main">
        <div class="card sport-card sport-card--featured"><div class="card-header"><div><span class="sport-eyebrow">À RETENIR</span><h2>Dernière activité</h2></div></div><div class="card-body">${data.latest_activity ? this._featuredActivity(data.latest_activity) : this._empty('Aucune activité disponible', 'Importe une activité pour commencer à suivre ta progression.')}</div></div>
        <div class="card sport-card"><div class="card-header"><div><span class="sport-eyebrow">HISTORIQUE</span><h2>Activités récentes</h2></div><button class="btn btn-sm btn-secondary" data-action="activities">Tout voir</button></div><div class="card-body sport-recent-list">${this._recent(data.recent_activities || [])}</div></div>
      </section>
      <section class="sport-dashboard-grid sport-dashboard-grid--three">
         ${this._heartRate(data.heart_rate, this.profile)}
        ${this._elevation(data.elevation || {})}
         ${this._goal(data.goals || [], data.goal_analysis || [])}
      </section>
       <section class="card sport-ai-card"><div class="sport-ai-icon">✦</div><div class="sport-ai-content"><span class="sport-eyebrow">COACH SPORT</span><h2>Une question sur ton entraînement ?</h2><p>Les réponses utilisent uniquement les statistiques disponibles dans ton historique.</p><div class="sport-coach-toolbar"><select class="form-control" data-coach-conversation aria-label="Conversation Coach Sport"><option value="">Nouvelle conversation</option>${this._conversationOptions()}</select><button class="btn btn-secondary" type="button" data-new-conversation>Nouvelle</button></div><div class="sport-coach-history" aria-live="polite">${this._coachHistory()}</div><form class="sport-coach-form"><input class="form-control" name="question" maxlength="1000" placeholder="Comment s’est passée ma semaine ?" required><button class="btn btn-primary" type="submit">Analyser</button></form><div class="sport-coach-answer" aria-live="polite"></div></div><span class="sport-ai-badge">IA ForgeAI</span></section>
    `;
    this._bindEvents();
  }

  _bindEvents() {
    this.element.querySelectorAll('[data-period]').forEach(button => button.addEventListener('click', async () => {
      this.period = Number(button.dataset.period);
      await this.initialize();
      this._renderContent();
    }));
    this.element.querySelector('[data-metric]')?.addEventListener('change', event => {
      this.metric = event.target.value;
      this._renderContent();
    });
    this.element.querySelector('[data-action="activities"]')?.addEventListener('click', () => this.router.navigate('/sport/activities'));
    this.element.querySelector('.sport-heart-rate-form')?.addEventListener('submit', async event => {
      event.preventDefault();
      const form = event.currentTarget;
      const button = form.querySelector('button');
      const status = form.querySelector('[data-heart-rate-status]');
      button.disabled = true;
      status.textContent = 'Enregistrement...';
      try {
        const values = Object.fromEntries(new FormData(form).entries());
        const customZones = [...form.querySelectorAll('[name="zone"]')].map(input => input.value ? Number(input.value) : null);
        this.profile = await updateSportHeartRateConfig({ rest_hr: values.rest_hr ? Number(values.rest_hr) : null, max_hr: values.max_hr ? Number(values.max_hr) : null, custom_zones: customZones.every(value => value == null) ? null : customZones });
        status.textContent = 'Configuration enregistrée.';
      } catch (error) {
        status.textContent = 'Configuration invalide ou indisponible.';
      } finally {
        button.disabled = false;
      }
    });
    this.element.querySelector('[data-new-conversation]')?.addEventListener('click', () => {
      this.conversationId = null;
      this.messages = [];
      this.element.querySelector('[data-coach-conversation]').value = '';
      this._renderCoachHistory();
    });
    this.element.querySelector('[data-coach-conversation]')?.addEventListener('change', async event => {
      this.conversationId = event.target.value ? Number(event.target.value) : null;
      this.messages = [];
      if (this.conversationId) {
        try {
          const conversation = await getSportCoachConversation(this.conversationId);
          this.messages = conversation.messages || [];
        } catch (error) {
          this.conversationId = null;
        }
      }
      this._renderCoachHistory();
    });
    this.element.querySelector('.sport-coach-form')?.addEventListener('submit', async event => {
      event.preventDefault();
      const form = event.currentTarget;
      const answer = this.element.querySelector('.sport-coach-answer');
      const button = form.querySelector('button');
      button.disabled = true;
      answer.textContent = 'Analyse en cours...';
      try {
        const result = await askSportCoach(new FormData(form).get('question'), this.conversationId);
        this.conversationId = result.conversation_id || this.conversationId;
        answer.textContent = result.answer || 'Aucune analyse disponible.';
        this.messages.push({ role: 'user', content: new FormData(form).get('question') });
        this.messages.push({ role: 'assistant', content: result.answer || 'Aucune analyse disponible.', provider: result.provider });
        this._renderCoachHistory();
      } catch (error) {
        answer.textContent = 'Le coach est temporairement indisponible. Les statistiques du dashboard restent accessibles.';
      } finally {
        button.disabled = false;
      }
    });
  }

  _conversationOptions() {
    return this.conversations.map(item => `<option value="${item.id}" ${item.id === this.conversationId ? 'selected' : ''}>${this._escape(item.title || `Conversation ${item.id}`)}</option>`).join('');
  }

  _coachHistory() {
    if (!this.messages.length) return '<p class="text-muted">Aucun message dans cette conversation.</p>';
    return this.messages.map(message => `<div class="sport-coach-message sport-coach-message--${message.role === 'user' ? 'user' : 'assistant'}"><strong>${message.role === 'user' ? 'Toi' : 'Coach Sport'}</strong><p>${this._escape(message.content)}</p></div>`).join('');
  }

  _renderCoachHistory() {
    const history = this.element?.querySelector('.sport-coach-history');
    if (history) history.innerHTML = this._coachHistory();
  }

  _summaryCard(label, value, change, icon) {
    if (value == null) return '';
    const trend = change == null ? '' : `<span class="sport-change ${change >= 0 ? 'sport-change--up' : 'sport-change--down'}">${change >= 0 ? '↑' : '↓'} ${Math.abs(change)}%</span>`;
    return `<article class="sport-stat-card"><div class="sport-stat-top"><span>${label}</span><span class="sport-stat-icon sport-stat-icon--${icon}">${this._icon(icon)}</span></div><strong>${value}</strong>${trend ? `<div class="sport-stat-meta">${trend} <span>vs période précédente</span></div>` : '<div class="sport-stat-meta sport-stat-meta--muted">Données disponibles sur la période</div>'}</article>`;
  }

  _trendFor(data, key) { return (data.trends || []).find(item => item.key === key)?.change_percent; }

  _trendStrip(data) {
    const trends = (data.trends || []).filter(item => item.change_percent != null).slice(0, 4);
    if (!trends.length) return '';
    return `<div class="sport-trend-strip">${trends.map(item => `<div><span>${item.label}</span><strong class="${item.change_percent >= 0 ? 'is-positive' : 'is-negative'}">${item.change_percent >= 0 ? '+' : ''}${item.change_percent}%</strong></div>`).join('')}</div>`;
  }

  _analysisFindings(analysis) {
    const findings = analysis.findings || [];
    const load = analysis.training_load?.available ? `<p><strong>Charge calculée :</strong> ${analysis.training_load.score} points · ${analysis.training_load.activity_count} activité(s)</p>` : '';
    if (!findings.length && !load) return '';
    return `<section class="card sport-analysis-findings"><div class="card-header"><div><span class="sport-eyebrow">EXPLICABILITÉ</span><h2>Points calculés</h2></div></div><div class="card-body">${load}${findings.map(item => `<details class="sport-analysis-finding"><summary>${this._escape(item.message)}</summary><pre>${this._escape(JSON.stringify(item.evidence || {}, null, 2))}</pre></details>`).join('')}</div></section>`;
  }

  _dailyChart(items) {
    const values = items.map(item => Number(item[this.metric] || 0));
    if (!items.length || !values.some(Boolean)) return this._empty('Pas assez de données', 'Les volumes apparaîtront ici dès que des activités seront enregistrées.');
    const max = Math.max(...values, 1);
    const width = 760; const height = 210; const gap = Math.max(2, Math.min(8, width / items.length / 3));
    const barWidth = Math.max(2, (width - gap * items.length) / items.length);
    const bars = values.map((value, index) => { const x = index * (barWidth + gap); const h = value ? Math.max(3, value / max * 160) : 0; return `<rect x="${x.toFixed(1)}" y="${(height - h - 25).toFixed(1)}" width="${barWidth.toFixed(1)}" height="${h.toFixed(1)}" rx="3" class="sport-chart-bar"><title>${this._date(items[index].date)} · ${this._metricValue(value)}</title></rect>`; }).join('');
    return `<div class="sport-chart-wrap"><svg class="sport-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Volume quotidien">${bars}<line x1="0" y1="${height - 24}" x2="${width}" y2="${height - 24}" class="sport-chart-axis"/></svg><div class="sport-chart-labels"><span>${this._date(items[0].date, true)}</span><span>${this._date(items[Math.floor(items.length / 2)].date, true)}</span><span>${this._date(items[items.length - 1].date, true)}</span></div></div>`;
  }

  _weeklyChart(items) {
    if (!items.length || !items.some(item => item.activity_count)) return this._empty('Aucune semaine renseignée', 'Les comparaisons hebdomadaires nécessitent des activités enregistrées.');
    const max = Math.max(...items.map(item => item.distance_m || item.duration_seconds || item.elevation_gain_m || 0), 1);
    return `<div class="sport-weekly-list">${items.map((item, index) => { const value = item.distance_m || item.duration_seconds || item.elevation_gain_m || 0; const ratio = Math.max(4, value / max * 100); return `<div class="sport-week-row"><span class="sport-week-label">S-${items.length - index}</span><div class="sport-week-bar"><i style="width:${ratio}%"></i></div><strong>${this._distance(item.distance_m)}</strong><span>${this._elevationValue(item.elevation_gain_m)} · ${this._duration(item.duration_seconds)} · ${item.activity_count || 0} sortie${item.activity_count > 1 ? 's' : ''}</span></div>`; }).join('')}</div>`;
  }

  _calendar(items) {
    if (!items.some(item => item.activity_count)) return this._empty('Pas encore de régularité à afficher', 'Ton calendrier se remplira avec tes prochaines séances.');
    const max = Math.max(...items.map(item => item.duration_seconds || 0), 1);
    return `<div class="sport-calendar-weekdays"><span>L</span><span>M</span><span>M</span><span>J</span><span>V</span><span>S</span><span>D</span></div><div class="sport-calendar-grid">${items.map(item => { const level = item.activity_count ? Math.min(4, Math.ceil((item.duration_seconds || 1) / max * 4)) : 0; return `<span class="sport-calendar-cell level-${level}" title="${this._date(item.date)}${item.activity_count ? ` · ${item.activity_count} activité(s)` : ''}"></span>`; }).join('')}</div><div class="sport-calendar-legend"><span>Moins</span><i class="level-0"></i><i class="level-1"></i><i class="level-2"></i><i class="level-3"></i><i class="level-4"></i><span>Plus</span></div>`;
  }

  _sports(items) {
    if (!items.length) return this._empty('Aucune répartition disponible', 'Les sports apparaîtront après ta première activité.');
    const total = items.reduce((sum, item) => sum + item.activity_count, 0) || 1;
    return `<div class="sport-distribution">${items.map(item => `<div class="sport-distribution-row"><span class="sport-dot sport-dot--${item.sport_type}"></span><div><strong>${this._escape(SPORT_LABELS[item.sport_type] || item.sport_type)}</strong><small>${item.activity_count} activité${item.activity_count > 1 ? 's' : ''} · ${this._duration(item.duration_seconds)}</small></div><b>${Math.round(item.activity_count / total * 100)}%</b></div>`).join('')}</div>`;
  }

  _featuredActivity(item) {
    return `<div class="sport-featured-activity"><div class="sport-activity-symbol">${this._icon(item.sport_type)}</div><div class="sport-featured-title"><span class="sport-eyebrow">${this._escape(SPORT_LABELS[item.sport_type] || item.sport_type)}</span><h3>${this._escape(item.activity_name || 'Activité sportive')}</h3><p>${this._date(item.started_at)} · ${this._escape(item.source_type || 'source inconnue')}</p></div></div><div class="sport-activity-metrics"><div><span>Distance</span><strong>${this._distance(item.distance_m)}</strong></div><div><span>Durée</span><strong>${this._duration(item.duration_seconds)}</strong></div><div><span>D+</span><strong>${this._elevationValue(item.elevation_gain_m)}</strong></div>${item.avg_pace_sec_km != null ? `<div><span>Allure</span><strong>${this._pace(item.avg_pace_sec_km)}</strong></div>` : ''}${item.avg_heart_rate != null ? `<div><span>FC moy.</span><strong>${Math.round(item.avg_heart_rate)} bpm</strong></div>` : ''}</div>`;
  }

  _recent(items) {
    if (!items.length) return this._empty('Aucune activité disponible', 'Les séances récentes apparaîtront ici.');
    return items.map(item => `<button class="sport-recent-item" type="button" title="Ouvrir les activités"><span class="sport-recent-icon">${this._icon(item.sport_type)}</span><span class="sport-recent-main"><strong>${this._escape(item.activity_name || SPORT_LABELS[item.sport_type] || item.sport_type)}</strong><small>${this._date(item.started_at)} · ${this._distance(item.distance_m)} · ${this._duration(item.duration_seconds)}</small></span><span class="sport-recent-elevation">${this._elevationValue(item.elevation_gain_m)}</span></button>`).join('');
  }

  _heartRate(data, profile) {
    const config = profile?.heart_rate || {};
    const zones = config.custom_zones || [];
    const zoneInputs = [0, 1, 2, 3, 4].map(index => `<label>Z${index + 1} max<input class="form-control" name="zone" type="number" min="40" max="250" value="${zones[index] ?? ''}" placeholder="limite bpm"></label>`).join('');
    return `<div class="card sport-card"><div class="card-header"><div><span class="sport-eyebrow">RÉCUPÉRATION</span><h2>Fréquence cardiaque</h2></div></div><div class="card-body sport-health-card">${data ? `<div><span>FC moyenne</span><strong>${Math.round(data.avg_bpm)} <small>bpm</small></strong></div>${data.max_bpm != null ? `<div><span>FC max</span><strong>${Math.round(data.max_bpm)} <small>bpm</small></strong></div>` : ''}` : '<p class="text-muted">Aucune fréquence cardiaque disponible sur la période.</p>'}<form class="sport-heart-rate-form"><label>FC repos<input class="form-control" name="rest_hr" type="number" min="20" max="250" value="${config.rest_hr ?? ''}" placeholder="ex. 50"></label><label>FC max<input class="form-control" name="max_hr" type="number" min="80" max="250" value="${config.max_hr ?? ''}" placeholder="ex. 190"></label><div class="sport-zones-config"><span>Limites personnalisées (optionnel)</span>${zoneInputs}</div><button class="btn btn-secondary" type="submit">Enregistrer</button><small data-heart-rate-status class="text-muted">Les zones personnalisées doivent être croissantes.</small></form></div></div>`;
  }

  _elevation(data) {
    if (data.month_m == null && data.weekly_average_m == null) return '';
    return `<div class="card sport-card"><div class="card-header"><div><span class="sport-eyebrow">TRAIL</span><h2>Dénivelé</h2></div></div><div class="card-body sport-health-card"><div><span>D+ sur 4 semaines</span><strong>${this._elevationValue(data.month_m)}</strong></div><div><span>Moyenne hebdo.</span><strong>${this._elevationValue(data.weekly_average_m)}</strong></div><div class="sport-mini-bars">${(data.weekly || []).map(item => `<i style="height:${Math.max(4, Math.min(100, (item.elevation_gain_m || 0) / Math.max(...(data.weekly || []).map(value => value.elevation_gain_m || 1)) * 100))}%" title="${this._elevationValue(item.elevation_gain_m)}"></i>`).join('')}</div></div></div>`;
  }

  _goal(goals, analyses = []) {
    const goal = goals.find(item => item.status === 'active') || goals[0];
    if (!goal) return `<div class="card sport-card sport-goal-empty"><div class="card-header"><div><span class="sport-eyebrow">OBJECTIF</span><h2>Objectif sportif</h2></div></div><div class="card-body">${this._empty('Aucun objectif défini', 'Ajoute un objectif pour suivre ta progression ici.')}</div></div>`;
     const analysis = analyses.find(item => item.goal_id === goal.id);
     const context = analysis ? `${analysis.compatible_activity_count} activité(s) compatible(s) · ${analysis.recent_28_days.activity_count} sur les 28 derniers jours` : 'Aucune analyse compatible disponible';
     return `<div class="card sport-card"><div class="card-header"><div><span class="sport-eyebrow">OBJECTIF</span><h2>${this._escape(goal.name)}</h2></div></div><div class="card-body sport-goal"><strong>${goal.target_value != null ? `${goal.target_value} ${this._escape(goal.unit || '')}` : 'Objectif en préparation'}</strong>${goal.target_date ? `<span>Échéance · ${this._date(goal.target_date)}</span>` : ''}<div class="sport-goal-track"><i></i></div><small>${this._escape(context)}. Aucune prédiction de réussite n'est calculée.</small></div></div>`;
  }

  _metricValue(value) { return this.metric === 'distance_m' ? this._distance(value) : this.metric === 'elevation_gain_m' ? this._elevationValue(value) : this._duration(value); }
  _distance(value) { return value == null ? '—' : `${(value / 1000).toFixed(value >= 10000 ? 0 : 1)} km`; }
  _elevationValue(value) { return value == null ? '—' : `${Math.round(value)} m`; }
  _duration(value) { if (value == null) return '—'; const hours = Math.floor(value / 3600); return `${hours}h ${String(Math.floor((value % 3600) / 60)).padStart(2, '0')}`; }
  _pace(value) { return value == null ? '—' : `${Math.floor(value / 60)}’${String(Math.round(value % 60)).padStart(2, '0')} /km`; }
  _date(value, short = false) { return value ? new Date(value).toLocaleDateString('fr-FR', short ? { day: '2-digit', month: 'short' } : { day: 'numeric', month: 'long', year: 'numeric' }) : ''; }
  _empty(title, message) { return `<div class="sport-empty"><span class="sport-empty-mark">○</span><strong>${title}</strong><p>${message}</p></div>`; }
  _icon(type) { return ({ route: '↗', mountain: '⌁', clock: '◷', activity: '◉', pace: '≈', heart: '♥', running: '↗', trail: '⌁', cycling: '↻', hiking: '⌁', swimming: '≋', walking: '→' }[type] || '•'); }
  _escape(value) { const element = document.createElement('div'); element.textContent = value ?? ''; return element.innerHTML; }
}

export function createSportDashboardPage(router) { return new SportDashboardPage(router); }
