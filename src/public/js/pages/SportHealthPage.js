import { getSportHealth } from '../services/sportApi.js?v=6';

const PERIODS = [
  { value: 7, label: '7 jours' },
  { value: 14, label: '2 semaines' },
  { value: 28, label: '4 semaines' },
  { value: 90, label: '3 mois' },
];

const CARDS = [
  { key: 'sleep', eyebrow: 'RÉCUPÉRATION', title: 'Sommeil', field: 'total_minutes', format: value => value == null ? '—' : `${Math.floor(value / 60)}h ${String(Math.round(value % 60)).padStart(2, '0')}`, extra: item => item.score != null ? `Score ${Math.round(item.score)}` : '' },
  { key: 'heart_rate', eyebrow: 'CARDIO', title: 'Fréquence cardiaque', field: 'resting', format: value => value == null ? '—' : `${Math.round(value)} bpm`, extra: item => item.max != null ? `Max ${Math.round(item.max)} bpm` : '' },
  { key: 'hrv', eyebrow: 'ÉQUILIBRE', title: 'HRV', field: 'value', format: value => value == null ? '—' : `${Math.round(value)} ms`, extra: item => item.status != null ? String(item.status) : '' },
  { key: 'stress', eyebrow: 'TENSION', title: 'Stress', field: 'avg', format: value => value == null ? '—' : Math.round(value), extra: item => item.max != null ? `Max ${Math.round(item.max)}` : '' },
  { key: 'body_battery', eyebrow: 'ÉNERGIE', title: 'Body Battery', field: 'last', format: value => value == null ? '—' : `${Math.round(value)} %`, extra: item => item.min != null ? `Min ${Math.round(item.min)} %` : '' },
  { key: 'steps', eyebrow: 'ACTIVITÉ QUOTIDIENNE', title: 'Pas & calories', field: 'steps', format: value => value == null ? '—' : Math.round(value).toLocaleString('fr-FR'), extra: item => item.calories != null ? `${Math.round(item.calories)} kcal` : '' },
  { key: 'spo2', eyebrow: 'OXYGÈNE', title: 'SpO2', field: 'value', format: value => value == null ? '—' : `${Number(value).toFixed(1)} %`, extra: () => '' },
  { key: 'respiration', eyebrow: 'RESPIRATION', title: 'Respiration', field: 'value', format: value => value == null ? '—' : `${Math.round(value)} /min`, extra: () => '' },
  { key: 'readiness', eyebrow: 'PRÊT POUR L’EFFORT', title: 'Training Readiness', field: 'score', format: value => value == null ? '—' : Math.round(value), extra: item => item.status != null ? String(item.status) : '' },
];

export class SportHealthPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.data = null;
    this.period = 28;
    this.loading = false;
    this.error = false;
  }

  async initialize() {
    this.loading = true;
    this.error = false;
    try {
      this.data = await getSportHealth(this.period);
    } catch (error) {
      this.error = true;
      this.data = null;
      console.error('Erreur chargement santé:', error);
    } finally {
      this.loading = false;
    }
  }

  render() {
    this.element = document.createElement('div');
    this.element.className = 'page-content';
    this._renderContent();
    return this.element;
  }

  _renderContent() {
    if (!this.element) return;
    const data = this.data || {};
    const summary = data.summary || {};
    const series = data.series || {};
    const hasData = (data.days_available || 0) > 0;
    this.element.innerHTML = `
      <div class="page-header sport-dashboard-header">
        <div class="page-header-left"><span class="sport-kicker">FORGEAI SPORT</span><h1>Santé</h1><p class="page-subtitle">Récupération, sommeil et données de santé synchronisées depuis Garmin.</p></div>
        <div class="sport-periods" role="group" aria-label="Période d'analyse">
          ${PERIODS.map(item => `<button class="btn btn-sm ${item.value === this.period ? 'btn-primary' : 'btn-secondary'}" data-period="${item.value}" aria-pressed="${item.value === this.period}">${item.label}</button>`).join('')}
        </div>
      </div>
      ${this.error ? '<div class="card" role="alert"><div class="card-body">Impossible de charger les données de santé.</div></div>' : ''}
      ${!this.error && this.loading && !this.data ? '<div class="card"><div class="card-body">Chargement…</div></div>' : ''}
      ${!this.error && hasData ? `
        <section class="sport-summary-grid" aria-label="Résumé de la période">
          ${this._statCard('FC repos (moy.)', this._format('heart_rate', summary.resting_hr_avg))}
          ${this._statCard('Sommeil (moy.)', this._formatMinutes(summary.sleep_total_avg_minutes))}
          ${this._statCard('Score sommeil', this._round(summary.sleep_score_avg))}
          ${this._statCard('HRV (moy.)', summary.hrv_avg == null ? null : `${Math.round(summary.hrv_avg)} ms`)}
          ${this._statCard('Stress (moy.)', this._round(summary.stress_avg))}
          ${this._statCard('Body Battery', summary.body_battery_last == null ? null : `${Math.round(summary.body_battery_last)} %`)}
          ${this._statCard('Pas (moy.)', summary.steps_avg == null ? null : Math.round(summary.steps_avg).toLocaleString('fr-FR'))}
          ${summary.readiness_last == null ? '' : this._statCard('Readiness', Math.round(summary.readiness_last))}
        </section>
        <section class="sport-dashboard-grid sport-dashboard-grid--main" aria-label="Séries de santé">
          ${CARDS.map(card => this._card(card, series[card.key] || [])).join('')}
        </section>
      ` : ''}
      ${!this.error && !this.loading && !hasData ? `
        <div class="card sport-card">
          <div class="card-body">${this._empty('Aucune donnée de santé', 'Connecte Garmin Connect et lance une synchronisation : le sommeil, la FC, le HRV, le stress et le Body Battery apparaîtront ici.')}<div style="text-align:center;margin-top:var(--spacing-3)"><button class="btn btn-primary" data-action="garmin">Ouvrir Garmin Connect</button></div></div>
        </div>
      ` : ''}
    `;
    this._bindEvents();
  }

  _bindEvents() {
    this.element.querySelectorAll('[data-period]').forEach(button => button.addEventListener('click', async () => {
      this.period = Number(button.dataset.period);
      await this.initialize();
      this._renderContent();
    }));
    this.element.querySelector('[data-action="garmin"]')?.addEventListener('click', () => this.router.navigate('/sport/garmin'));
  }

  _statCard(label, value) {
    if (value == null) return '';
    return `<article class="sport-stat-card"><div class="sport-stat-top"><span>${label}</span></div><strong>${value}</strong><div class="sport-stat-meta sport-stat-meta--muted">Sur la période sélectionnée</div></article>`;
  }

  _card(card, items) {
    if (!items.length) return '';
    const latest = items[items.length - 1];
    const currentValue = this._format(card.key, latest[card.field]);
    const extra = card.extra(latest) || '';
    return `
      <div class="card sport-card">
        <div class="card-header"><div><span class="sport-eyebrow">${card.eyebrow}</span><h2>${card.title}</h2></div><strong class="sport-health-value">${currentValue}</strong></div>
        <div class="card-body">
          ${this._chart(items, card.field, card.format)}
          ${extra ? `<p class="text-muted sport-health-caption">${this._escape(extra)} · dernière donnée le ${this._date(latest.date)}</p>` : `<p class="text-muted sport-health-caption">Dernière donnée le ${this._date(latest.date)}</p>`}
        </div>
      </div>`;
  }

  _chart(items, field, format) {
    const values = items.map(item => Number(item[field] || 0));
    if (!values.some(Boolean)) return this._empty('Pas encore de données', 'Les mesures apparaîtront après une synchronisation Garmin.');
    const max = Math.max(...values, 1);
    const width = 760; const height = 190; const gap = Math.max(2, Math.min(8, width / items.length / 3));
    const barWidth = Math.max(2, (width - gap * items.length) / items.length);
    const bars = values.map((value, index) => {
      const x = index * (barWidth + gap);
      const h = value ? Math.max(3, value / max * 145) : 0;
      return `<rect x="${x.toFixed(1)}" y="${(height - h - 25).toFixed(1)}" width="${barWidth.toFixed(1)}" height="${h.toFixed(1)}" rx="3" class="sport-chart-bar"><title>${this._date(items[index].date)} · ${format(values[index])}</title></rect>`;
    }).join('');
    return `<div class="sport-chart-wrap"><svg class="sport-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Série quotidienne">${bars}<line x1="0" y1="${height - 24}" x2="${width}" y2="${height - 24}" class="sport-chart-axis"/></svg><div class="sport-chart-labels"><span>${this._date(items[0].date, true)}</span><span>${this._date(items[Math.floor(items.length / 2)].date, true)}</span><span>${this._date(items[items.length - 1].date, true)}</span></div></div>`;
  }

  _format(key, value) {
    const card = CARDS.find(item => item.key === key);
    return card ? card.format(value) : (value == null ? '—' : value);
  }

  _formatMinutes(value) {
    return value == null ? '—' : `${Math.floor(value / 60)}h ${String(Math.round(value % 60)).padStart(2, '0')}`;
  }

  _round(value) { return value == null ? '—' : Math.round(value); }
  _date(value, short = false) { return value ? new Date(value).toLocaleDateString('fr-FR', short ? { day: '2-digit', month: 'short' } : { day: 'numeric', month: 'long', year: 'numeric' }) : ''; }
  _empty(title, message) { return `<div class="sport-empty"><span class="sport-empty-mark">○</span><strong>${title}</strong><p>${message}</p></div>`; }
  _escape(value) { const element = document.createElement('div'); element.textContent = value ?? ''; return element.innerHTML; }

  destroy() {
    this.element = null;
  }
}

export function createSportHealthPage(router) { return new SportHealthPage(router); }
