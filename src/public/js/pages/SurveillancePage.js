import { authStore } from '../stores/auth.js';
import { createSurveillanceCamera, deleteSurveillanceCamera, listSurveillanceCameras, listSurveillanceEvents, listSurveillanceRecordings, startSurveillanceCapture, stopSurveillanceCapture, testSurveillanceCamera, updateSurveillanceCamera } from '../services/domotiqueApi.js?v=4';

export class SurveillancePage {
  constructor() { this.element = null; this.cameras = []; this.events = []; this.recordings = []; this.error = ''; this.message = ''; }
  async initialize() {
    try {
      const [cameras, events, recordings] = await Promise.all([listSurveillanceCameras(), listSurveillanceEvents(20), listSurveillanceRecordings(20)]);
      this.cameras = cameras.items || []; this.events = events.items || []; this.recordings = recordings.items || [];
    } catch (error) { this.error = error?.data?.detail || error.message || 'Chargement impossible'; }
  }
  render() {
    const previousElement = this.element;
    this.element = document.createElement('div'); this.element.className = 'page-content surveillance-page';
    this.element.innerHTML = `<div class="page-header"><div class="page-header-left"><span class="domo-kicker">DOMOTIQUE</span><h1>Surveillance</h1><p class="page-subtitle">Caméras, événements et enregistrements</p></div><button class="btn btn-primary" data-action="add">Ajouter une caméra</button></div>
      ${this.error ? `<div class="card" role="alert"><div class="card-body">${this._esc(this.error)}</div></div>` : ''}
      ${this.message ? `<div class="domo-flash">${this._esc(this.message)}</div>` : ''}
      <div class="surveillance-kpis"><div><strong>${this.cameras.length}</strong><span>Caméras</span></div><div><strong>${this.cameras.filter(c => c.status === 'online').length}</strong><span>En ligne</span></div><div><strong>${this.cameras.filter(c => c.status === 'offline').length}</strong><span>Hors ligne</span></div><div><strong>${this.events.length}</strong><span>Événements récents</span></div></div>
      <section class="card surveillance-card"><div class="card-header"><h2>Caméras</h2></div><div class="card-body"><div class="surveillance-grid">${this.cameras.length ? this.cameras.map(c => this._camera(c)).join('') : '<p class="empty-message">Aucune caméra configurée.</p>'}</div></div></section>
      <section class="card surveillance-card"><div class="card-header"><h2>Événements récents</h2></div><div class="card-body">${this.events.length ? `<div class="table-container"><table class="users-table"><thead><tr><th>Date</th><th>Caméra</th><th>Type</th></tr></thead><tbody>${this.events.map(e => `<tr><td>${this._date(e.created_at)}</td><td>${this._cameraName(e.camera_id)}</td><td>${this._esc(e.event_type)}</td></tr>`).join('')}</tbody></table></div>` : '<p class="empty-message">Aucun événement enregistré.</p>'}</div></section>`;
    this._bind();
    if (previousElement?.isConnected) previousElement.replaceWith(this.element);
    return this.element;
  }
  _camera(camera) { const active = camera.capture_status === 'active'; const stream = `/domotique/surveillance/cameras/${camera.id}/stream/index.m3u8`; return `<article class="surveillance-camera"><div class="surveillance-preview">${active ? `<video class="surveillance-video" data-video="${camera.id}" controls muted playsinline preload="none" src="${stream}"></video>` : '<span>Capture arrêtée</span>'}</div><div class="surveillance-camera-head"><div><h3>${this._esc(camera.name)}</h3><p>${this._esc(camera.location || 'Emplacement non défini')}</p></div><span class="surveillance-status is-${this._esc(camera.status)}">${this._esc(camera.status)}</span></div><p class="text-muted">${this._esc(camera.source_type)}${camera.protocol ? ` · ${this._esc(camera.protocol)}` : ''}</p><div class="surveillance-actions">${camera.protocol === 'rtsp' ? `<button class="btn btn-secondary btn-sm" data-capture="${camera.id}" data-capture-action="${active ? 'stop' : 'start'}">${active ? 'Arrêter' : 'Démarrer'}</button>` : ''}<button class="btn btn-secondary btn-sm" data-test="${camera.id}">Tester</button><button class="btn btn-secondary btn-sm" data-edit="${camera.id}">Modifier</button><button class="btn btn-danger btn-sm" data-delete="${camera.id}">Supprimer</button></div></article>`; }
  _bind() {
    this.element.querySelector('[data-action="add"]')?.addEventListener('click', () => this._edit());
    this.element.querySelectorAll('[data-video]').forEach(video => {
      video.addEventListener('error', () => { video.replaceWith(Object.assign(document.createElement('span'), { className: 'text-muted', textContent: 'Flux indisponible ou navigateur non compatible HLS' })); }, { once: true });
    });
    this.element.querySelectorAll('[data-capture]').forEach(b => b.addEventListener('click', async () => { try { const fn = b.dataset.captureAction === 'start' ? startSurveillanceCapture : stopSurveillanceCapture; await fn(b.dataset.capture); await this.initialize(); this.render(); } catch (e) { this.message = e?.data?.detail || e.message; this.render(); } }));
    this.element.querySelectorAll('[data-test]').forEach(b => b.addEventListener('click', async () => { try { const r = await testSurveillanceCamera(b.dataset.test); this.message = r.message; await this.initialize(); this.render(); } catch (e) { this.message = e?.data?.detail || e.message; this.render(); } }));
    this.element.querySelectorAll('[data-edit]').forEach(b => b.addEventListener('click', () => this._edit(this.cameras.find(c => c.id === Number(b.dataset.edit)))));
    this.element.querySelectorAll('[data-delete]').forEach(b => b.addEventListener('click', async () => { if (!confirm('Supprimer cette caméra ? Les enregistrements historiques doivent être conservés.')) return; try { await deleteSurveillanceCamera(b.dataset.delete); await this.initialize(); this.render(); } catch (e) { this.message = e?.data?.detail || e.message; this.render(); } }));
  }
  _edit(camera = null) {
    const config = camera?.config_json || {};
    const detection = config.detection || {};
    const recording = config.recording || {};
    const modal = document.createElement('div');
    modal.className = 'modal-overlay open';
    modal.innerHTML = `<div class="modal-content surveillance-camera-modal" role="dialog" aria-modal="true" aria-labelledby="surveillance-modal-title">
      <div class="modal-header"><h2 id="surveillance-modal-title">${camera ? 'Modifier la caméra' : 'Ajouter une caméra'}</h2><button type="button" class="modal-close" data-close aria-label="Fermer">&times;</button></div>
      <form class="modal-body" data-camera-form>
        <div class="asset-modal-tabs surveillance-tabs" role="tablist">
          <button type="button" class="admin-tab active" data-tab="camera" role="tab" aria-selected="true">Caméra</button>
          <button type="button" class="admin-tab" data-tab="detection" role="tab" aria-selected="false">Détection</button>
          <button type="button" class="admin-tab" data-tab="recording" role="tab" aria-selected="false">Enregistrement</button>
        </div>
        <section class="surveillance-modal-panel active" data-panel="camera">
          <div class="form-row"><label><span>Nom *</span><input name="name" required maxlength="120" value="${this._attr(camera?.name || '')}"></label><label><span>Emplacement</span><input name="location" maxlength="160" value="${this._attr(camera?.location || '')}"></label></div>
          <div class="form-row"><label><span>Type de source</span><select name="source_type"><option value="ip" ${camera?.source_type === 'ip' || !camera ? 'selected' : ''}>Caméra IP</option><option value="usb" ${camera?.source_type === 'usb' ? 'selected' : ''}>USB</option><option value="integrated" ${camera?.source_type === 'integrated' ? 'selected' : ''}>Intégrée</option><option value="remote_agent" ${camera?.source_type === 'remote_agent' ? 'selected' : ''}>Agent distant</option></select></label><label><span>Protocole</span><select name="protocol"><option value="http" ${camera?.protocol === 'http' || !camera ? 'selected' : ''}>HTTP</option><option value="https" ${camera?.protocol === 'https' ? 'selected' : ''}>HTTPS</option><option value="rtsp" ${camera?.protocol === 'rtsp' ? 'selected' : ''}>RTSP</option><option value="onvif" ${camera?.protocol === 'onvif' ? 'selected' : ''}>ONVIF</option></select></label></div>
          <div class="form-row"><label><span>Hôte / adresse IP</span><input name="host" value="${this._attr(camera?.host || '')}" placeholder="192.168.1.20"></label><label><span>Port</span><input name="port" type="number" min="1" max="65535" value="${camera?.port || 80}"></label></div>
          <label><span>URL du flux (optionnelle)</span><input name="stream_url" type="url" value="${this._attr(camera?.stream_url || '')}" placeholder="rtsp://…"></label>
          <div class="form-row"><label><span>Utilisateur</span><input name="username" value="${this._attr(camera?.username || '')}"></label><label><span>Mot de passe${camera?.has_password ? ' (laisser vide pour conserver)' : ''}</span><input name="password" type="password" autocomplete="new-password"></label></div>
          <label class="checkbox-label"><input name="enabled" type="checkbox" ${camera?.enabled ? 'checked' : ''}> Activer cette caméra</label>
        </section>
        <section class="surveillance-modal-panel" data-panel="detection" hidden>
          <label class="checkbox-label"><input name="detection_enabled" type="checkbox" ${camera?.detection_enabled ? 'checked' : ''}> Activer la détection</label>
          <div class="form-row"><label><span>Type d’événement</span><select name="detection_event"><option value="motion" ${detection.event_type !== 'person' ? 'selected' : ''}>Mouvement</option><option value="person" ${detection.event_type === 'person' ? 'selected' : ''}>Personne</option></select></label><label><span>Confiance minimale (%)</span><input name="detection_confidence" type="number" min="0" max="100" value="${detection.confidence ?? 60}"></label></div>
        </section>
        <section class="surveillance-modal-panel" data-panel="recording" hidden>
          <label class="checkbox-label"><input name="recording_enabled" type="checkbox" ${recording.enabled ? 'checked' : ''}> Enregistrer les événements détectés</label>
          <div class="form-row"><label><span>Durée de conservation (jours)</span><input name="retention_days" type="number" min="1" max="3650" value="${recording.retention_days ?? 30}"></label><label><span>Secondes avant événement</span><input name="pre_event_seconds" type="number" min="0" max="300" value="${recording.pre_event_seconds ?? 5}"></label></div>
          <label><span>Secondes après événement</span><input name="post_event_seconds" type="number" min="0" max="600" value="${recording.post_event_seconds ?? 30}"></label>
        </section>
        <div class="modal-footer"><button type="button" class="btn btn-secondary" data-close>Annuler</button><button type="submit" class="btn btn-primary">Enregistrer</button></div>
      </form>
    </div>`;
    document.body.appendChild(modal);
    const close = () => modal.remove();
    modal.querySelectorAll('[data-close]').forEach(button => button.addEventListener('click', close));
    modal.addEventListener('click', event => { if (event.target === modal) close(); });
    modal.querySelectorAll('[data-tab]').forEach(tab => tab.addEventListener('click', () => {
      modal.querySelectorAll('[data-tab]').forEach(item => { item.classList.toggle('active', item === tab); item.setAttribute('aria-selected', item === tab ? 'true' : 'false'); });
      modal.querySelectorAll('[data-panel]').forEach(panel => { panel.hidden = panel.dataset.panel !== tab.dataset.tab; panel.classList.toggle('active', panel.dataset.panel === tab.dataset.tab); });
    }));
    modal.querySelector('[data-camera-form]').addEventListener('submit', async event => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      const payload = {
        name: form.get('name').trim(), location: form.get('location') || null, source_type: form.get('source_type'), protocol: form.get('protocol'),
        host: form.get('host') || null, port: Number(form.get('port')) || null, stream_url: form.get('stream_url') || null,
        username: form.get('username') || null, password: form.get('password') || null, enabled: form.has('enabled'), detection_enabled: form.has('detection_enabled'),
        config_json: { ...config, detection: { event_type: form.get('detection_event'), confidence: Number(form.get('detection_confidence')) || 0 }, recording: { enabled: form.has('recording_enabled'), retention_days: Number(form.get('retention_days')) || 30, pre_event_seconds: Number(form.get('pre_event_seconds')) || 0, post_event_seconds: Number(form.get('post_event_seconds')) || 0 } }
      };
      try { if (camera) await updateSurveillanceCamera(camera.id, payload); else await createSurveillanceCamera(payload); close(); await this.initialize(); this.render(); }
      catch (error) { this.message = error?.data?.detail || error.message; close(); this.render(); }
    });
    modal.querySelector('[name="name"]').focus();
  }
  _cameraName(id) { return this.cameras.find(c => c.id === id)?.name || `Caméra #${id}`; }
  _date(value) { return value ? new Date(value).toLocaleString('fr-FR') : '—'; }
  _esc(value) { return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c])); }
  _attr(value) { return this._esc(value); }
}
export function createSurveillancePage() { return new SurveillancePage(); }
