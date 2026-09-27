import { getAiSettings, updateAiSettings } from '../services/adminApi.js?v=2';

export class AiSettingsPage {
  constructor() {
    this.element = null;
    this.settings = null;
  }

  async initialize() {
    this.settings = await getAiSettings();
  }

  // ------------------------------------------------------------------ #
  // Paramètres (formulaire existant)
  // ------------------------------------------------------------------ #

  _providerCard(prefix, title) {
    return `
      <div class="card" style="margin-top:1rem;">
        <div class="card-header">
          <h2>${title}</h2>
        </div>
        <div class="card-body">
          <div class="form-row">
            <label class="checkbox-label"><input name="${prefix}_enabled" type="checkbox"> Fournisseur activé</label>
            <label></label>
          </div>
          <div class="form-row">
            <label><span>Clé API</span><input name="${prefix}_api_key" type="password" autocomplete="new-password" placeholder="Non configurée"></label>
            <label><span>Modèle</span><input name="${prefix}_model" maxlength="100" placeholder="Catalogue par défaut"></label>
          </div>
          <div class="form-row">
            <label><span>Statut de la clé</span><span class="text-muted" data-key-status="${prefix}"></span></label>
            <label><span>URL de base</span><input name="${prefix}_base_url" maxlength="255"></label>
          </div>
        </div>
      </div>
    `;
  }

  _updateKeyStatuses() {
    const form = this.element.querySelector('[data-ai-form]');
    if (!form) return;
    ['groq', 'gemini', 'openrouter'].forEach((prefix) => {
      const configured = !!this.settings?.[prefix]?.api_key_configured;
      const input = form.elements[`${prefix}_api_key`];
      const status = this.element.querySelector(`[data-key-status="${prefix}"]`);
      if (input) {
        input.placeholder = configured
          ? 'Clé configurée — laisser vide pour conserver'
          : 'Non configurée';
      }
      if (status) {
        status.textContent = configured
          ? '✓ Clé enregistrée (masquée pour sécurité)'
          : 'Aucune clé enregistrée';
        status.style.color = configured ? 'var(--color-success)' : '';
      }
    });
  }

  _setMessage(text) {
    this.element.querySelectorAll('[data-ai-message]').forEach((el) => {
      el.textContent = text;
    });
  }

  _bindSettingsForm() {
    const form = this.element.querySelector('[data-ai-form]');
    if (!form) return;
    const s = this.settings || {};

    const setValue = (name, value) => { form.elements[name].value = value ?? ''; };
    form.elements.enabled.checked = s.enabled !== false;
    form.elements.default_provider.value = s.default_provider || 'auto';
    setValue('default_model', s.default_model || 'auto');
    setValue('provider_order', s.provider_order || 'groq,gemini,openrouter');
    setValue('timeout_seconds', s.timeout_seconds ?? 30);
    setValue('max_retries', s.max_retries ?? 2);
    setValue('retry_backoff_seconds', s.retry_backoff_seconds ?? 1);
    ['groq', 'gemini', 'openrouter'].forEach((prefix) => {
      form.elements[`${prefix}_enabled`].checked = s[prefix]?.enabled !== false;
      setValue(`${prefix}_model`, s[prefix]?.model);
      setValue(`${prefix}_base_url`, s[prefix]?.base_url);
    });
    this._updateKeyStatuses();

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const providerPayload = (prefix) => ({
        enabled: form.elements[`${prefix}_enabled`].checked,
        api_key: form.elements[`${prefix}_api_key`].value,
        base_url: form.elements[`${prefix}_base_url`].value,
        model: form.elements[`${prefix}_model`].value,
      });
      const payload = {
        enabled: form.elements.enabled.checked,
        default_provider: form.elements.default_provider.value,
        default_model: form.elements.default_model.value || 'auto',
        provider_order: form.elements.provider_order.value || 'groq,gemini,openrouter',
        timeout_seconds: Number(form.elements.timeout_seconds.value),
        max_retries: Number(form.elements.max_retries.value),
        retry_backoff_seconds: Number(form.elements.retry_backoff_seconds.value),
        groq: providerPayload('groq'),
        gemini: providerPayload('gemini'),
        openrouter: providerPayload('openrouter'),
      };
      try {
        this.settings = await updateAiSettings(payload);
        ['groq', 'gemini', 'openrouter'].forEach((prefix) => {
          form.elements[`${prefix}_api_key`].value = '';
        });
        this._updateKeyStatuses();
        this._setMessage('Paramètres enregistrés. Les clés saisies sont conservées (masquées).');
      } catch (error) {
        const detail = error.data?.detail;
        const detailText = Array.isArray(detail)
          ? detail.map((item) => item?.msg || JSON.stringify(item)).join(' — ')
          : detail;
        this._setMessage(detailText || error.message || 'Erreur lors de l\'enregistrement.');
      }
    });
  }

  // ------------------------------------------------------------------ #
  // Rendu
  // ------------------------------------------------------------------ #

  render() {
    this.element = document.createElement('div');
    this.element.className = 'admin-settings-page';
    this.element.innerHTML = `
      <section>
        <form data-ai-form>
          <div class="card">
            <div class="card-header">
              <h2>Paramètres de l’assistant IA</h2>
              <p class="text-muted">Passerelle IA centralisée : fournisseurs, modèles et limites d’appels.</p>
            </div>
            <div class="card-body">
              <div class="form-row">
                <label class="checkbox-label"><input name="enabled" type="checkbox"> Passerelle IA activée</label>
                <label></label>
              </div>
              <div class="form-row">
                <label><span>Fournisseur par défaut</span>
                  <select name="default_provider">
                    <option value="auto">Automatique (selon l’ordre)</option>
                    <option value="groq">Groq</option>
                    <option value="gemini">Google Gemini</option>
                    <option value="openrouter">OpenRouter</option>
                  </select>
                </label>
                <label><span>Modèle par défaut</span><input name="default_model" maxlength="100" placeholder="auto"></label>
              </div>
              <div class="form-row">
                <label><span>Ordre de repli (fallback)</span><input name="provider_order" maxlength="100" placeholder="groq,gemini,openrouter"></label>
                <label></label>
              </div>
              <div class="form-row">
                <label><span>Timeout (secondes)</span><input name="timeout_seconds" type="number" min="1" max="300" step="1"></label>
                <label><span>Retries</span><input name="max_retries" type="number" min="0" max="5" step="1"></label>
              </div>
              <div class="form-row">
                <label><span>Backoff entre retries (secondes)</span><input name="retry_backoff_seconds" type="number" min="0" max="30" step="0.5"></label>
                <label></label>
              </div>
              <div class="form-actions">
                <button class="btn btn-primary" type="submit">Enregistrer</button>
                <span data-ai-message role="status"></span>
              </div>
            </div>
          </div>
          ${this._providerCard('groq', 'Groq')}
          ${this._providerCard('gemini', 'Google Gemini')}
          ${this._providerCard('openrouter', 'OpenRouter')}
          <div class="form-actions" style="margin-top:1rem;">
            <button class="btn btn-primary" type="submit">Enregistrer</button>
            <span data-ai-message role="status"></span>
          </div>
        </form>
      </section>
    `;

    this._bindSettingsForm();
    return this.element;
  }

  onTabActivate() {}

  destroy() {}
}

export function createAiSettingsPage() {
  return new AiSettingsPage();
}
