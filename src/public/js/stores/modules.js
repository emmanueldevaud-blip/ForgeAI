import { modulesApi } from '../services/api.js';

class ModulesStore {
  constructor() {
    this.activeModules = null;
    this._loading = null;
  }

  async load() {
    const response = await modulesApi.get('/enabled');
    this.activeModules = Array.isArray(response?.modules) ? response.modules : [];
    return this.activeModules;
  }

  async ensureLoaded() {
    if (this.activeModules !== null) return this.activeModules;
    if (!this._loading) {
      this._loading = this.load()
        .catch(() => {
          // Echec reseau : on laisse passer (le backend protege de toute facon).
          this.activeModules = null;
          return null;
        })
        .finally(() => {
          this._loading = null;
        });
    }
    return this._loading;
  }

  isModuleActive(code) {
    if (!code) return true;
    if (this.activeModules === null) return true;
    return this.activeModules.includes(code);
  }

  areModulesActive(codes) {
    return (codes || []).every((code) => this.isModuleActive(code));
  }

  invalidate() {
    this.activeModules = null;
  }
}

const modulesStore = new ModulesStore();

export { modulesStore };
