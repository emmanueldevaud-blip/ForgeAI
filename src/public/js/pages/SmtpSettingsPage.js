import { getSmtpSettings, updateSmtpSettings, testSmtpSettings } from '../services/adminApi.js';

export class SmtpSettingsPage {
  constructor() {
    this.element = null;
    this.settings = null;
  }

  async initialize() {
    this.settings = await getSmtpSettings();
  }

  render() {
    this.element = document.createElement('div');
    this.element.className = 'admin-settings-page';
    this.element.innerHTML = `
      <div class="card">
        <div class="card-header">
          <h2>Configuration SMTP</h2>
          <p class="text-muted">Paramètres utilisés pour l’envoi des e-mails de l’application.</p>
        </div>
        <form data-smtp-form class="card-body">
          <div class="form-row">
            <label><span>Serveur SMTP *</span><input name="host" required maxlength="255"></label>
            <label><span>Port *</span><input name="port" type="number" min="1" max="65535" required></label>
          </div>
          <div class="form-row">
            <label><span>Identifiant</span><input name="username" autocomplete="username" maxlength="255"></label>
            <label><span>Mot de passe</span><input name="password" type="password" autocomplete="new-password" placeholder="Laisser vide pour conserver"></label>
          </div>
          <div class="form-row">
            <label><span>Adresse d’envoi</span><input name="from_email" type="email" maxlength="255"></label>
            <label><span>Nom d’expéditeur</span><input name="from_name" maxlength="100"></label>
          </div>
          <div class="form-row">
            <label class="checkbox-label"><input name="use_tls" type="checkbox"> Utiliser STARTTLS</label>
            <label class="checkbox-label"><input name="use_ssl" type="checkbox"> Utiliser SSL</label>
          </div>
          <div class="form-actions">
            <button class="btn btn-primary" type="submit">Enregistrer</button>
            <span data-smtp-message role="status"></span>
          </div>
          <div class="form-row" style="margin-top:1.5rem;padding-top:1rem;border-top:1px solid var(--color-border-light);">
            <label><span>Destinataire du test</span><input name="test_recipient" type="email" required maxlength="255"></label>
            <div style="display:flex;align-items:end;"><button class="btn btn-secondary" type="button" data-smtp-test>Tester l’envoi</button></div>
          </div>
        </form>
      </div>
    `;

    const form = this.element.querySelector('[data-smtp-form]');
    const setValue = (name, value) => { form.elements[name].value = value ?? ''; };
    setValue('host', this.settings?.host);
    setValue('port', this.settings?.port || 587);
    setValue('username', this.settings?.username);
    setValue('from_email', this.settings?.from_email);
    setValue('from_name', this.settings?.from_name || 'ForgeAI');
    setValue('test_recipient', this.settings?.from_email);
    form.elements.use_tls.checked = this.settings?.use_tls !== false;
    form.elements.use_ssl.checked = this.settings?.use_ssl === true;

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(form).entries());
      data.port = Number(data.port);
      data.use_tls = form.elements.use_tls.checked;
      data.use_ssl = form.elements.use_ssl.checked;
      try {
        this.settings = await updateSmtpSettings(data);
        form.elements.password.value = '';
        this.element.querySelector('[data-smtp-message]').textContent = 'Paramètres enregistrés.';
      } catch (error) {
        this.element.querySelector('[data-smtp-message]').textContent = error.message || 'Erreur lors de l’enregistrement.';
      }
    });

    this.element.querySelector('[data-smtp-test]').addEventListener('click', async () => {
      const recipient = form.elements.test_recipient.value.trim();
      const message = this.element.querySelector('[data-smtp-message]');
      if (!form.elements.host.value || !form.elements.from_email.value) {
        message.textContent = 'Enregistrez d’abord la configuration SMTP.';
        return;
      }
      if (!form.elements.test_recipient.reportValidity()) return;
      message.textContent = 'Test en cours...';
      try {
        const result = await testSmtpSettings(recipient);
        message.textContent = result.message || 'E-mail de test envoyé.';
      } catch (error) {
        message.textContent = error.data?.detail || error.message || 'Échec du test SMTP.';
      }
    });
    return this.element;
  }

  onTabActivate() {}
  destroy() {}
}

export function createSmtpSettingsPage() {
  return new SmtpSettingsPage();
}
