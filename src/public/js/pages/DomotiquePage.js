import { authStore } from '../stores/auth.js';
import {
  advanceDomotiqueCycle,
  createDomotiqueCycle,
  getDomotiqueHistory,
  getDomotiqueStatus,
  listDomotiqueEvents,
  listDomotiqueProfiles,
  pauseDomotiqueCycle,
  sendDomotiqueManual,
  setDomotiqueOutputMode,
  startDomotiqueCycle,
  stopDomotiqueCycle,
} from '../services/domotiqueApi.js?v=2';
import { DomotiqueConfigPage } from './DomotiqueConfigPage.js?v=5';

const VIEWS = [
  { key: 'details', label: 'Détails' },
  { key: 'history', label: 'Historique' },
  { key: 'cycle', label: 'Cycle' },
  { key: 'equipment', label: 'Équipements' },
];

const CYCLE_STATUS_LABELS = {
  preparing: 'Préparation',
  running: 'En cours',
  paused: 'Pause',
  completed: 'Terminé',
  stopped: 'Arrêté',
  error: 'Erreur',
};

const OUTPUT_ROLES = {
  heater: 'Chauffage',
  cooler: 'Refroidissement',
  fan: 'Ventilation',
  humidifier: 'Humidificateur',
  dehumidifier: 'Déshumidificateur',
  other: 'Autre',
};

const EXIT_CONDITION_LABELS = {
  time: 'Durée',
  weight: 'Perte de poids',
  manual: 'Manuelle',
};

const EVENT_ICONS = {
  cycle_started: '▶',
  cycle_resumed: '▶',
  cycle_paused: '⏸',
  cycle_stopped: '⏹',
  cycle_completed: '🏁',
  cycle_created: '＋',
  phase_change: '→',
  command: '⚡',
  manual_command: '⚡',
  output_mode: '⚙',
  command_error: '✕',
  alert_temperature: '🌡',
  alert_humidity: '💧',
  sensor_stale: '⚠',
  comm_connect: '🟢',
  comm_disconnect: '🔴',
  out_of_range_temperature: '🌡',
  in_range_temperature: '🌡',
  out_of_range_humidity: '💧',
  in_range_humidity: '💧',
};

const POLL_INTERVAL_MS = 30000;

export class DomotiquePage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.view = 'details';
    this.period = '24h';
    this.status = null;
    this.history = null;
    this.events = [];
    this.profiles = [];
    this.error = null;
    this.actionMessage = '';
    this.timer = null;
    this.configPage = null;
    this.configInitialized = false;
  }

  get canControl() {
    return authStore.hasPermission('domotique.control');
  }

  get canConfigure() {
    return authStore.hasPermission('domotique.configure');
  }

  async initialize() {
    await this._loadAll();
    this._startPolling();
  }

  async _loadAll() {
    this.error = null;
    try {
      this.status = await getDomotiqueStatus();
    } catch (error) {
      this.error = error;
      return;
    }
    try {
      this.events = (await listDomotiqueEvents(50)).events || [];
    } catch (error) {
      this.events = [];
    }
    try {
      this.profiles = (await listDomotiqueProfiles()).profiles || [];
    } catch (error) {
      this.profiles = [];
    }
    await this._loadHistory();
  }

  async _loadHistory() {
    try {
      this.history = await getDomotiqueHistory(this.period);
    } catch (error) {
      this.history = null;
    }
  }

  _startPolling() {
    this._stopPolling();
    this.timer = setInterval(async () => {
      if (document.visibilityState !== 'visible' || this._formFocused()) return;
      const previousPhase = this.status?.cycle?.current_phase_id;
      const previousStatus = this.status?.cycle?.status;
      try {
        this.status = await getDomotiqueStatus();
      } catch (error) {
        return;
      }
      if (this.view === 'config') return;
      const phaseChanged =
        previousPhase !== this.status?.cycle?.current_phase_id ||
        previousStatus !== this.status?.cycle?.status;
      if (phaseChanged || this.view === 'history' || this.view === 'cycle') {
        if (this.view === 'history' || phaseChanged) await this._loadHistory();
        if (phaseChanged) this.events = (await listDomotiqueEvents(50)).events || [];
      }
      if (!phaseChanged && this.view === 'details' && this._subtreeExists()) {
        this._updateLiveValues();
        return;
      }
      this.render();
    }, POLL_INTERVAL_MS);
  }

  _stopPolling() {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  _subtreeExists() {
    return Boolean(this.element && this.element.isConnected);
  }

  _formFocused() {
    const active = document.activeElement;
    if (!active) return false;
    const tag = active.tagName;
    return tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA';
  }

  render() {
    this._stopPolling();
    const previous = this.element;
    this.element = document.createElement('div');
    this.element.className = 'page-content domo-page';
    this._renderContent();
    this._bindEvents();
    if (previous && previous.isConnected) previous.replaceWith(this.element);
    this._startPolling();
    return this.element;
  }

  _renderContent() {
    if (this.error) {
      this.element.innerHTML = `
        <div class="page-header"><div class="page-header-left"><span class="domo-kicker">DOMOTIQUE</span><h1>La Cave</h1></div></div>
        <div class="card" role="alert"><div class="card-body"><p>Impossible de charger l'état de la cave : ${this._escape(this.error.message || 'erreur inconnue')}</p><button class="btn btn-secondary" data-action="retry" type="button">Réessayer</button></div></div>`;
      return;
    }
    const status = this.status || {};
    const views = this.canConfigure ? [...VIEWS, { key: 'config', label: 'Configuration' }] : VIEWS;
    this.element.innerHTML = `
      <div class="page-header domo-header">
        <div class="page-header-left">
          <span class="domo-kicker">DOMOTIQUE</span>
          <h1>La Cave</h1>
        </div>
        <div class="domo-views" role="tablist" aria-label="Vues de la cave">
          ${views.map((view) => `
            <button class="btn btn-sm ${this.view === view.key ? 'btn-primary' : 'btn-secondary'}" type="button" data-view="${view.key}" role="tab" aria-selected="${this.view === view.key}">${view.label}</button>
          `).join('')}
        </div>
      </div>
      <div class="domo-status-strip" role="status">
        ${this._statusStrip(status)}
      </div>
      ${this.actionMessage ? `<div class="domo-flash">${this._escape(this.actionMessage)}</div>` : ''}
      <div data-domo-view>${this._viewContent(status)}</div>`;
    if (this.view === 'config' && this.configPage) {
      const host = this.element.querySelector('[data-domo-config]');
      if (host) host.appendChild(this.configPage.render({ embedded: true }));
    }
  }

  _viewContent(status) {
    switch (this.view) {
      case 'history':
        return this._historyView();
      case 'cycle':
        return this._cycleView(status);
      case 'equipment':
        return this._equipmentView(status);
      case 'config':
        return '<div class="domo-config-host" data-domo-config></div>';
      default:
        return this._detailsView(status);
    }
  }

  // ------------------------------------------------------------------ #
  // Indicateurs d'entete
  // ------------------------------------------------------------------ #

  _statusStrip(status) {
    const conn = this._connectionBadge(status);
    const cycle = status.cycle;
    const running = cycle && (cycle.status === 'running' || cycle.status === 'paused');
    const phase = cycle && cycle.current_phase_name ? cycle.current_phase_name : '—';
    const since = running && cycle.started_at ? this._duration(cycle.started_at) : '—';
    const lastData = this._lastDataTime(status);
    return `
      <div class="domo-strip-item"><span class="domo-strip-label">Raspberry</span><strong>${conn}</strong></div>
      <div class="domo-strip-item"><span class="domo-strip-label">Cycle</span><strong>${cycle ? this._escape(CYCLE_STATUS_LABELS[cycle.status] || cycle.status) : 'Aucun'}</strong></div>
      <div class="domo-strip-item"><span class="domo-strip-label">Phase</span><strong>${this._escape(phase)}</strong></div>
      <div class="domo-strip-item"><span class="domo-strip-label">Depuis</span><strong>${since}</strong></div>
      <div class="domo-strip-item"><span class="domo-strip-label">Dernière donnée</span><strong>${lastData}</strong></div>`;
  }

  _connectionBadge(status) {
    if (status.stale && status.status === 'online') {
      return '<span class="domo-dot domo-dot--warn"></span> Données obsolètes';
    }
    if (status.status === 'online') return '<span class="domo-dot domo-dot--ok"></span> Connecté';
    if (status.status === 'offline') return '<span class="domo-dot domo-dot--ko"></span> Déconnecté';
    if (status.status === 'error') return '<span class="domo-dot domo-dot--warn"></span> En erreur';
    return '<span class="domo-dot domo-dot--idle"></span> Inconnu';
  }

  _lastDataTime(status) {
    const times = (status.sensors || [])
      .filter((sensor) => sensor.enabled && sensor.current_at)
      .map((sensor) => new Date(sensor.current_at).getTime())
      .filter((value) => !Number.isNaN(value));
    if (!times.length) return '—';
    return this._relativeTime(Math.max(...times));
  }

  // ------------------------------------------------------------------ #
  // Vue Détails (dashboard)
  // ------------------------------------------------------------------ #

  _detailsView(status) {
    const sensors = status.sensors || [];
    const temp = sensors.find((sensor) => sensor.key === 'temperature');
    const hum = sensors.find((sensor) => sensor.key === 'humidity');
    const weight = sensors.find((sensor) => sensor.key === 'weight');
    const cycle = status.cycle;
    const cards = [
      this._metricCard('Température', 'domo-temp', temp, '°C',
        cycle && cycle.current_phase_name ? this._phaseTarget(status, 'temperature') : null),
      this._metricCard('Humidité', 'domo-hum', hum, '% HR',
        cycle && cycle.current_phase_name ? this._phaseTarget(status, 'humidity') : null),
    ];
    if (weight && weight.current_value != null) {
      cards.push(this._weightCard(cycle, weight));
    }
    return `
      <div class="domo-cards">${cards.join('')}</div>
      <div class="domo-charts">
        ${this._chartCard('Température — historique', this._lineChart(this.history?.series?.temperature, this.history?.target_temperature, 'domo-line--temp'))}
        ${this._chartCard('Humidité — historique', this._lineChart(this.history?.series?.humidity, this.history?.target_humidity, 'domo-line--hum'))}
      </div>
      ${this._periodSelector()}`;
  }

  _phaseTarget(status, kind) {
    // Les cibles de phase sont exposees via l'historique (consigne superposee).
    if (!this.history) return null;
    if (kind === 'temperature') return this.history.target_temperature;
    return this.history.target_humidity;
  }

  _metricCard(title, cssClass, sensor, unit, target) {
    const corrected = sensor && sensor.corrected_value != null ? sensor.corrected_value : null;
    const raw = sensor && sensor.current_value != null ? sensor.current_value : null;
    const shown = corrected ?? raw;
    const value = shown != null ? this._num(shown) : '—';
    const min = this.history?.min?.[sensor?.key];
    const max = this.history?.max?.[sensor?.key];
    const trend = this.history?.trend?.[sensor?.key];
    const targetLabel = target != null ? `Cible ${this._num(target)} ${unit}` : 'Aucune consigne active';
    const trendLabel = trend == null || Math.abs(trend) < 0.05
      ? 'stable'
      : trend > 0 ? `↗ +${this._num(trend)}` : `↘ ${this._num(trend)}`;
    return `
      <section class="card domo-card ${cssClass}">
        <div class="card-header"><div><span class="domo-eyebrow">MESURE</span><h2>${title}</h2></div></div>
        <div class="card-body">
          <div class="domo-big">${value}<small>${unit}</small></div>
          <div class="domo-target">${this._escape(targetLabel)}</div>
          <div class="domo-range">
            <span>Min <strong>${min != null ? this._num(min) : '—'}</strong></span>
            <span>Max <strong>${max != null ? this._num(max) : '—'}</strong></span>
            <span>Tendance <strong>${trendLabel}</strong></span>
          </div>
          ${this._metricMeta(sensor)}
        </div>
      </section>`;
  }

  _metricMeta(sensor) {
    if (!sensor || !sensor.current_at) return '<small class="text-muted">Aucune donnée</small>';
    let text = `Relevé ${this._relativeTime(new Date(sensor.current_at).getTime())}`;
    const corrected = sensor.corrected_value != null ? sensor.corrected_value : null;
    const raw = sensor.current_value != null ? sensor.current_value : null;
    if (corrected != null && raw != null && Math.abs(corrected - raw) >= 0.05) {
      text += ` · Mesure brute ${this._num(raw)} ${sensor.unit}`;
    }
    return `<small class="text-muted" data-live-meta>${text}</small>`;
  }

  _weightCard(cycle, weight) {
    const initial = cycle?.initial_weight ?? null;
    const current = weight.current_value;
    const loss = cycle?.weight_loss_pct;
    const target = cycle?.target_weight_loss_pct;
    let progress = '';
    if (loss != null && target) {
      const ratio = Math.max(0, Math.min(100, (loss / target) * 100));
      progress = `
        <div class="domo-progress" role="progressbar" aria-valuenow="${Math.round(ratio)}" aria-valuemin="0" aria-valuemax="100">
          <i style="width:${ratio.toFixed(1)}%"></i>
        </div>
        <div class="domo-progress-label">Objectif ${this._num(target)} % — ${ratio >= 100 ? 'atteint' : `${Math.round(ratio)} %`}</div>`;
    }
    const lossLine = loss != null
      ? `<div class="domo-big domo-loss">−${this._num(loss)}<small>%</small></div>`
      : '<div class="domo-big">—<small>%</small></div>';
    return `
      <section class="card domo-card domo-weight">
        <div class="card-header"><div><span class="domo-eyebrow">BALANCE</span><h2>Poids</h2></div></div>
        <div class="card-body">
          ${lossLine}
          <div class="domo-weight-detail">
            <span>Initial <strong>${initial != null ? `${this._num(initial)} g` : '—'}</strong></span>
            <span>Actuel <strong>${current != null ? `${this._num(current)} g` : '—'}</strong></span>
            <span>Perte <strong>${loss != null && initial != null ? `${this._num(initial - current)} g` : '—'}</strong></span>
          </div>
          ${progress}
          ${weight.current_at ? `<small class="text-muted">Relevé ${this._relativeTime(new Date(weight.current_at).getTime())}</small>` : ''}
        </div>
      </section>`;
  }

  _chartCard(title, body) {
    return `
      <section class="card domo-card domo-chart-card">
        <div class="card-header"><div><span class="domo-eyebrow">COURBES</span><h2>${title}</h2></div></div>
        <div class="card-body">${body}</div>
      </section>`;
  }

  _periodSelector() {
    const periods = [
      { value: '24h', label: '24 h' },
      { value: '3d', label: '3 jours' },
      { value: '7d', label: '7 jours' },
      { value: 'cycle', label: 'Cycle complet' },
    ];
    return `<div class="domo-periods" role="group" aria-label="Période des courbes">
      ${periods.map((item) => `<button class="btn btn-sm ${this.period === item.value ? 'btn-primary' : 'btn-secondary'}" type="button" data-period="${item.value}">${item.label}</button>`).join('')}
    </div>`;
  }

  _lineChart(points, target, cssClass) {
    if (!points || points.length < 2) {
      return '<p class="text-muted">Pas encore de mesures pour cette période.</p>';
    }
    const width = 720;
    const height = 220;
    const padX = 8;
    const padTop = 12;
    const padBottom = 24;
    const values = points.map((point) => point.v);
    let min = Math.min(...values);
    let max = Math.max(...values);
    if (target != null) {
      min = Math.min(min, target);
      max = Math.max(max, target);
    }
    if (min === max) {
      min -= 1;
      max += 1;
    }
    const span = max - min;
    const times = points.map((point) => new Date(point.t).getTime());
    const t0 = times[0];
    const t1 = times[times.length - 1] || t0 + 1;
    const tSpan = Math.max(1, t1 - t0);
    const x = (t) => padX + ((t - t0) / tSpan) * (width - padX * 2);
    const y = (v) => padTop + (1 - (v - min) / span) * (height - padTop - padBottom);
    const path = points.map((point, index) => `${index ? 'L' : 'M'}${x(times[index]).toFixed(1)},${y(point.v).toFixed(1)}`).join(' ');
    const targetLine = target != null
      ? `<line x1="${padX}" y1="${y(target).toFixed(1)}" x2="${width - padX}" y2="${y(target).toFixed(1)}" class="domo-line-target" />
         <text x="${width - padX - 4}" y="${(y(target) - 4).toFixed(1)}" class="domo-line-target-label" text-anchor="end">cible ${this._num(target)}</text>`
      : '';
    const firstLabel = new Date(t0).toLocaleString('fr-FR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
    const lastLabel = new Date(t1).toLocaleString('fr-FR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
    return `
      <div class="domo-chart-wrap">
        <svg class="domo-chart ${cssClass}" viewBox="0 0 ${width} ${height}" role="img" aria-label="Courbe">
          ${targetLine}
          <path d="${path}" class="domo-line" fill="none" />
        </svg>
        <div class="domo-chart-labels"><span>${firstLabel}</span><span>${this._num(min)} — ${this._num(max)}</span><span>${lastLabel}</span></div>
      </div>`;
  }

  // ------------------------------------------------------------------ #
  // Vue Historique
  // ------------------------------------------------------------------ //

  _outputsChart(seriesList) {
    const usable = (seriesList || []).filter((item) => item.points && item.points.length);
    if (!usable.length) {
      return '<p class="text-muted">Aucun historique de sorties pour cette période.</p>';
    }
    const width = 720;
    const labelW = 150;
    const laneH = 34;
    const padTop = 10;
    const padBottom = 20;
    const height = padTop + usable.length * laneH + padBottom;
    const t0 = this.history?.start ? new Date(this.history.start).getTime() : Date.now() - 86400000;
    const t1 = Math.max(this.history?.end ? new Date(this.history.end).getTime() : Date.now(), t0 + 1000);
    const x = (t) => labelW + ((t - t0) / Math.max(1, t1 - t0)) * (width - labelW - 8);
    const colors = ['#2e7d32', '#c62828', '#1565c0', '#6a1b9a', '#ef6c00', '#00838f', '#5d4037', '#455a64'];
    const lanes = usable.map((item, laneIndex) => {
      const top = padTop + laneIndex * laneH + 4;
      const bottom = top + laneH - 14;
      let path = '';
      let prevY = null;
      item.points.forEach((point, i) => {
        const px = Math.min(width - 8, Math.max(labelW, x(new Date(point.t).getTime())));
        const py = point.v ? top : bottom;
        if (i === 0) path += `M${px.toFixed(1)},${py.toFixed(1)}`;
        else path += ` L${px.toFixed(1)},${prevY.toFixed(1)} L${px.toFixed(1)},${py.toFixed(1)}`;
        prevY = py;
      });
      path += ` L${(width - 8).toFixed(1)},${prevY.toFixed(1)}`;
      const color = colors[item.index % colors.length];
      const middle = (top + bottom) / 2 + 4;
      return `
        <text x="0" y="${middle.toFixed(1)}" class="domo-lane-label">${this._escape(item.name)}</text>
        <line x1="${labelW}" y1="${bottom.toFixed(1)}" x2="${width - 8}" y2="${bottom.toFixed(1)}" class="domo-lane-base" />
        <path d="${path}" fill="none" stroke="${color}" stroke-width="2" />`;
    });
    const firstLabel = new Date(t0).toLocaleString('fr-FR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
    const lastLabel = new Date(t1).toLocaleString('fr-FR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
    return `
      <div class="domo-chart-wrap">
        <svg class="domo-chart domo-chart--outputs" viewBox="0 0 ${width} ${height}" role="img" aria-label="État des sorties">${lanes.join('')}</svg>
        <div class="domo-chart-labels"><span>${firstLabel}</span><span>haut = ON · bas = OFF</span><span>${lastLabel}</span></div>
      </div>`;
  }

  _historyView() {
    const events = this.events || [];
    const rows = events.length
      ? events.map((event) => `
          <li class="domo-event">
            <span class="domo-event-icon">${EVENT_ICONS[event.type] || '•'}</span>
            <span class="domo-event-time">${this._eventDate(event.created_at)}</span>
            <span class="domo-event-message">${this._escape(event.message)}</span>
          </li>`).join('')
      : '<li class="text-muted">Aucun événement pour le moment.</li>';
    return `
      <div class="domo-charts">
        ${this._chartCard('Température — historique', this._lineChart(this.history?.series?.temperature, this.history?.target_temperature, 'domo-line--temp'))}
        ${this._chartCard('Humidité — historique', this._lineChart(this.history?.series?.humidity, this.history?.target_humidity, 'domo-line--hum'))}
        ${this._chartCard('Poids — historique', this._lineChart(this.history?.series?.weight, null, 'domo-line--weight'))}
        ${this._chartCard('Sorties — historique', this._outputsChart(this.history?.outputs))}
      </div>
      ${this._periodSelector()}
      <section class="card domo-card">
        <div class="card-header"><div><span class="domo-eyebrow">JOURNAL</span><h2>Historique de la cave</h2></div></div>
        <div class="card-body"><ul class="domo-events">${rows}</ul></div>
      </section>`;
  }

  // ------------------------------------------------------------------ #
  // Vue Cycle
  // ------------------------------------------------------------------ //

  _cycleView(status) {
    const cycle = status.cycle;
    const active = cycle && (cycle.status === 'running' || cycle.status === 'paused');
    return `
      ${cycle ? this._cycleCard(cycle, active) : ''}
      ${active ? '' : this._newCycleForm(status)}`;
  }

  _cycleCard(cycle, active) {
    const phases = [];
    if (cycle.phases_total && cycle.current_phase_order) {
      for (let order = 1; order <= cycle.phases_total; order += 1) {
        const state = order < cycle.current_phase_order ? 'done' : order === cycle.current_phase_order ? 'current' : 'todo';
        phases.push(`<span class="domo-phase domo-phase--${state}">${order}</span>`);
      }
    }
    const started = cycle.started_at
      ? new Date(cycle.started_at).toLocaleString('fr-FR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
      : '—';
    const weightBlock = cycle.initial_weight != null ? `
      <div class="domo-weight-detail">
        <span>Initial <strong>${this._num(cycle.initial_weight)} g</strong></span>
        <span>Actuel <strong>${cycle.current_weight != null ? `${this._num(cycle.current_weight)} g` : '—'}</strong></span>
        <span>Perte <strong>${cycle.weight_loss_pct != null ? `${this._num(cycle.weight_loss_pct)} %` : '—'}</strong></span>
        <span>Objectif <strong>${cycle.target_weight_loss_pct != null ? `${this._num(cycle.target_weight_loss_pct)} %` : '—'}</strong></span>
      </div>` : '';
    return `
      <section class="card domo-card">
        <div class="card-header">
          <div><span class="domo-eyebrow">CYCLE ${active ? 'EN COURS' : ''}</span><h2>${this._escape(cycle.name || 'Cycle')}</h2></div>
          <span class="domo-badge domo-badge--${cycle.status}">${this._escape(cycle.status_label || CYCLE_STATUS_LABELS[cycle.status] || cycle.status)}</span>
        </div>
        <div class="card-body">
          <div class="domo-cycle-grid">
            <div><span>Profil</span><strong>${this._escape(cycle.profile_name || '—')}</strong></div>
            <div><span>Produit</span><strong>${this._escape(cycle.product || '—')}</strong></div>
            <div><span>Boyau</span><strong>${this._escape(cycle.casing_size || '—')}</strong></div>
            <div><span>Démarré le</span><strong>${started}</strong></div>
            <div><span>Phase</span><strong>${this._escape(cycle.current_phase_name || '—')}</strong></div>
            <div><span>En phase depuis</span><strong>${cycle.phase_started_at ? this._duration(cycle.phase_started_at) : '—'}</strong></div>
          </div>
          ${phases.length ? `<div class="domo-phase-track">${phases.join('')}</div>` : ''}
          ${weightBlock}
          ${this.canControl ? `
            <div class="domo-actions">
              ${cycle.status === 'preparing' ? '<button class="btn btn-primary" type="button" data-cycle-action="start">Démarrer</button>' : ''}
              ${cycle.status === 'running' ? '<button class="btn btn-secondary" type="button" data-cycle-action="pause">Pause</button>' : ''}
              ${cycle.status === 'paused' ? '<button class="btn btn-primary" type="button" data-cycle-action="start">Reprendre</button>' : ''}
              ${active ? '<button class="btn btn-secondary" type="button" data-cycle-action="advance">Phase suivante</button>' : ''}
              ${active ? '<button class="btn btn-danger" type="button" data-cycle-action="stop">Arrêter</button>' : ''}
            </div>` : ''}
        </div>
      </section>`;
  }

  _newCycleForm(status) {
    const options = (this.profiles || []).map((profile) => `
      <option value="${profile.id}">${this._escape(profile.name)}</option>`).join('');
    const selected = (this.profiles || [])[0];
    const now = new Date(Date.now() - new Date().getTimezoneOffset() * 60000);
    const startValue = now.toISOString().slice(0, 16);
    return `
      <section class="card domo-card">
        <div class="card-header"><div><span class="domo-eyebrow">NOUVEAU</span><h2>Démarrer un cycle</h2></div></div>
        <div class="card-body">
          ${this.canControl ? `
          <form class="domo-form" data-new-cycle-form>
            <label>Profil
              <select class="form-control" name="profile_id" required>${options}</select>
            </label>
            <div class="domo-profile-preview" data-profile-preview>${this._profilePreview(selected)}</div>
            <label>Produit
              <input class="form-control" name="product" type="text" value="Saucisson" maxlength="100">
            </label>
            <label>Poids initial (g)
              <input class="form-control" name="initial_weight" type="number" min="0" step="1" placeholder="ex. 1200">
            </label>
            <label>Diamètre / boyau
              <input class="form-control" name="casing_size" type="text" value="40 mm" maxlength="50">
            </label>
            <label>Date de début
              <input class="form-control" name="started_at" type="datetime-local" value="${startValue}">
            </label>
            <div class="domo-actions">
              <button class="btn btn-primary" type="submit">Démarrer</button>
            </div>
            <small class="text-muted">Les phases du profil sélectionné sont affichées ci-dessus ; modifiables depuis Domotique → Configuration.</small>
          </form>` : '<p class="text-muted">Permission « domotique.control » requise pour créer un cycle.</p>'}
        </div>
      </section>`;
  }

  _durationLabel(minHours, maxHours) {
    const fmt = (hours) => {
      if (hours % 24 === 0) return `${this._num(hours / 24)} j`;
      if (hours > 24) {
        const days = Math.floor(hours / 24);
        const rest = hours % 24;
        return rest ? `${days} j ${rest} h` : `${days} j`;
      }
      return `${this._num(hours)} h`;
    };
    if (minHours != null && maxHours != null) {
      return minHours === maxHours ? fmt(minHours) : `${fmt(minHours)} – ${fmt(maxHours)}`;
    }
    if (minHours != null) return `dès ${fmt(minHours)}`;
    return `jusqu’à ${fmt(maxHours)}`;
  }

  _profilePreview(profile) {
    if (!profile) return '<p class="text-muted">Aucun profil disponible.</p>';
    const phases = [...(profile.phases || [])].sort((a, b) => a.order - b.order);
    const targets = [];
    if (profile.target_weight_loss_pct != null) {
      const range = profile.weight_loss_min_pct != null && profile.weight_loss_max_pct != null
        ? ` (plage ${this._num(profile.weight_loss_min_pct)} – ${this._num(profile.weight_loss_max_pct)} %)`
        : '';
      targets.push(`<span>Objectif de perte <strong>${this._num(profile.target_weight_loss_pct)} %${range}</strong></span>`);
    }
    targets.push(`<span>Phases <strong>${phases.length}</strong></span>`);
    const rows = phases.map((phase, index) => {
      const details = [];
      if (phase.target_temperature != null) {
        details.push(`${this._num(phase.target_temperature)} °C ± ${this._num(phase.tolerance_temperature ?? 0)} °C`);
      }
      if (phase.target_humidity != null) {
        details.push(`${this._num(phase.target_humidity)} %HR ± ${this._num(phase.tolerance_humidity ?? 0)} %`);
      }
      if (phase.min_duration_hours != null || phase.max_duration_hours != null) {
        details.push(this._durationLabel(phase.min_duration_hours, phase.max_duration_hours));
      }
      if (phase.weight_loss_target_pct != null) {
        details.push(`perte cible ${this._num(phase.weight_loss_target_pct)} %`);
      }
      details.push(`transition ${EXIT_CONDITION_LABELS[phase.exit_condition] || phase.exit_condition}`);
      return `
        <div class="domo-preview-phase">
          <span class="domo-preview-phase-num">${index + 1}</span>
          <strong>${this._escape(phase.name)}</strong>
          <span class="domo-preview-phase-detail">${this._escape(details.join(' · '))}</span>
        </div>`;
    }).join('');
    return `
      ${profile.description ? `<p class="domo-preview-description">${this._escape(profile.description)}</p>` : ''}
      <div class="domo-preview-targets">${targets.join('')}</div>
      <div class="domo-preview-phases">${rows || '<span class="text-muted">Aucune phase.</span>'}</div>`;
  }

  // ------------------------------------------------------------------ #
  // Vue Équipements
  // ------------------------------------------------------------------ //

  _equipmentView(status) {
    const outputs = status.outputs || [];
    const rows = outputs.map((output) => {
      const manual = output.mode === 'manual';
      return `
        <div class="domo-output ${output.state ? 'is-on' : ''}">
          <div class="domo-output-main">
            <strong>${this._escape(output.name)}</strong>
            <span class="text-muted">${this._escape(OUTPUT_ROLES[output.role] || output.role)} · GPIO ${output.index}</span>
          </div>
          <span class="domo-badge ${output.state ? 'domo-badge--on' : 'domo-badge--off'}">${output.state ? 'ON' : 'OFF'}</span>
          <span class="domo-badge ${manual ? 'domo-badge--manual' : 'domo-badge--auto'}">${manual ? 'Manuel' : 'Auto'}</span>
          ${this.canControl ? `
            <div class="domo-output-actions">
              <button class="btn btn-sm ${output.state ? 'btn-secondary' : 'btn-primary'}" type="button" data-output="${output.index}" data-output-state="off" ${output.state ? '' : 'disabled'}>OFF</button>
              <button class="btn btn-sm ${output.state ? 'btn-primary' : 'btn-secondary'}" type="button" data-output="${output.index}" data-output-state="on" ${output.state ? 'disabled' : ''}>ON</button>
              <button class="btn btn-sm btn-secondary" type="button" data-output-mode="${output.index}" data-output-mode-value="${manual ? 'auto' : 'manual'}">${manual ? 'Passer auto' : 'Passer manuel'}</button>
            </div>` : ''}
        </div>`;
    }).join('');
    return `
      <section class="card domo-card">
        <div class="card-header"><div><span class="domo-eyebrow">SORTIES RASPBERRY</span><h2>Équipements</h2></div></div>
        <div class="card-body">
          <p class="text-muted">Les sorties en mode automatique sont pilotées par le cycle actif. Les commandes manuelles sont possibles après bascule en mode manuel.</p>
          <div class="domo-outputs">${rows || '<p class="text-muted">Aucune sortie configurée.</p>'}</div>
        </div>
      </section>`;
  }

  // ------------------------------------------------------------------ #
  // Mises a jour ciblees (polling sans re-render complet)
  // ------------------------------------------------------------------ //

  _updateLiveValues() {
    const status = this.status || {};
    const strip = this.element.querySelector('.domo-status-strip');
    if (strip) strip.innerHTML = this._statusStrip(status);
    const temp = (status.sensors || []).find((sensor) => sensor.key === 'temperature');
    const hum = (status.sensors || []).find((sensor) => sensor.key === 'humidity');
    const tempCard = this.element.querySelector('.domo-temp .domo-big');
    const humCard = this.element.querySelector('.domo-hum .domo-big');
    if (tempCard && temp && temp.current_value != null) {
      tempCard.innerHTML = `${this._num(temp.current_value)}<small>°C</small>`;
    }
    if (humCard && hum) {
      const shown = hum.corrected_value != null ? hum.corrected_value : hum.current_value;
      if (shown != null) {
        humCard.innerHTML = `${this._num(shown)}<small>% HR</small>`;
      }
    }
    this.element.querySelectorAll('.domo-temp [data-live-meta], .domo-hum [data-live-meta]')
      .forEach((node) => {
        const sensor = node.closest('.domo-hum') ? hum : temp;
        if (sensor) node.outerHTML = this._metricMeta(sensor);
      });
  }

  // ------------------------------------------------------------------ #
  // Actions
  // ------------------------------------------------------------------ //

  _bindEvents() {
    if (!this.element) return;

    this.element.querySelectorAll('[data-view]').forEach((button) => {
      button.addEventListener('click', async () => {
        const view = button.dataset.view;
        if (view === 'config' && this.canConfigure) {
          if (!this.configPage) this.configPage = new DomotiqueConfigPage(this.router);
          if (!this.configInitialized) {
            await this.configPage.initialize();
            this.configInitialized = true;
          }
        }
        this.view = view;
        this.actionMessage = '';
        if (this.view === 'history' || this.view === 'details') await this._loadHistory();
        this.render();
      });
    });

    this.element.querySelectorAll('[data-period]').forEach((button) => {
      button.addEventListener('click', async () => {
        this.period = button.dataset.period;
        await this._loadHistory();
        this.render();
      });
    });

    const retry = this.element.querySelector('[data-action="retry"]');
    if (retry) {
      retry.addEventListener('click', async () => {
        await this._loadAll();
        this.render();
      });
    }

    this.element.querySelectorAll('[data-cycle-action]').forEach((button) => {
      button.addEventListener('click', async () => {
        const action = button.dataset.cycleAction;
        button.disabled = true;
        try {
          if (action === 'start') await startDomotiqueCycle({});
          else if (action === 'pause') await pauseDomotiqueCycle({});
          else if (action === 'stop') await stopDomotiqueCycle({});
          else if (action === 'advance') await advanceDomotiqueCycle({});
          this.actionMessage = 'Commande envoyée.';
        } catch (error) {
          this.actionMessage = error.message || 'Échec de la commande.';
        }
        await this._loadAll();
        this.render();
      });
    });

    const newCycleForm = this.element.querySelector('[data-new-cycle-form]');
    if (newCycleForm) {
      const profileSelect = newCycleForm.querySelector('select[name="profile_id"]');
      const profilePreview = newCycleForm.querySelector('[data-profile-preview]');
      if (profileSelect && profilePreview) {
        profileSelect.addEventListener('change', () => {
          const profile = (this.profiles || []).find((item) => item.id === Number(profileSelect.value));
          profilePreview.innerHTML = this._profilePreview(profile);
        });
      }
      newCycleForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        const data = new FormData(newCycleForm);
        const profileId = Number(data.get('profile_id'));
        const weight = data.get('initial_weight');
        const startedAt = data.get('started_at');
        const submit = newCycleForm.querySelector('button[type="submit"]');
        submit.disabled = true;
        try {
          await createDomotiqueCycle({
            profile_id: profileId,
            product: data.get('product') || null,
            casing_size: data.get('casing_size') || null,
            initial_weight: weight ? Number(weight) : null,
            started_at: startedAt ? new Date(startedAt).toISOString() : null,
            start_now: true,
            name: null,
            device_code: 'sechoir-saucisson',
            target_weight_loss_pct: null,
          });
          this.actionMessage = 'Cycle créé et démarré.';
          this.view = 'details';
        } catch (error) {
          this.actionMessage = error.message || 'Impossible de créer le cycle.';
        }
        await this._loadAll();
        this.render();
      });
    }

    this.element.querySelectorAll('[data-output][data-output-state]').forEach((button) => {
      button.addEventListener('click', async () => {
        const index = Number(button.dataset.output);
        const state = button.dataset.outputState === 'on';
        button.disabled = true;
        try {
          await sendDomotiqueManual({ output_index: index, state });
          this.actionMessage = `Sortie ${index + 1} → ${state ? 'ON' : 'OFF'}`;
        } catch (error) {
          this.actionMessage = error.message || 'Commande refusée.';
        }
        await this._loadAll();
        this.render();
      });
    });

    this.element.querySelectorAll('[data-output-mode]').forEach((button) => {
      button.addEventListener('click', async () => {
        const index = Number(button.dataset.outputMode);
        const mode = button.dataset.outputModeValue;
        try {
          await setDomotiqueOutputMode(index, mode);
          this.actionMessage = `Sortie ${index + 1} → mode ${mode}`;
        } catch (error) {
          this.actionMessage = error.message || 'Changement de mode refusé.';
        }
        await this._loadAll();
        this.render();
      });
    });
  }

  // ------------------------------------------------------------------ #
  // Helpers
  // ------------------------------------------------------------------ //

  _escape(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  _num(value) {
    if (value == null || Number.isNaN(Number(value))) return '—';
    const number = Number(value);
    return number.toLocaleString('fr-FR', { maximumFractionDigits: 1 });
  }

  _duration(iso) {
    const start = new Date(iso).getTime();
    if (Number.isNaN(start)) return '—';
    let seconds = Math.max(0, Math.floor((Date.now() - start) / 1000));
    const days = Math.floor(seconds / 86400);
    seconds -= days * 86400;
    const hours = Math.floor(seconds / 3600);
    seconds -= hours * 3600;
    const minutes = Math.floor(seconds / 60);
    if (days > 0) return `${days} j ${hours} h`;
    if (hours > 0) return `${hours} h ${minutes} min`;
    return `${minutes} min`;
  }

  _relativeTime(timestamp) {
    const delta = Math.max(0, Math.floor((Date.now() - timestamp) / 1000));
    if (delta < 60) return 'à l’instant';
    if (delta < 3600) return `il y a ${Math.floor(delta / 60)} min`;
    if (delta < 86400) return `il y a ${Math.floor(delta / 3600)} h`;
    return `il y a ${Math.floor(delta / 86400)} j`;
  }

  _eventDate(iso) {
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return '—';
    return date.toLocaleString('fr-FR', {
      day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
    });
  }
}

export function createDomotiquePage(router) {
  return new DomotiquePage(router);
}
