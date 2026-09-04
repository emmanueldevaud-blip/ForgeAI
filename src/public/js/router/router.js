class RouterError extends Error {
  constructor(message, code, redirectTo) {
    super(message);
    this.name = 'RouterError';
    this.code = code;
    this.redirectTo = redirectTo;
  }
}

class Router {
  constructor(options = {}) {
    this.routes = new Map();
    this.notFoundHandler = null;
    this.errorHandler = null;
    this.beforeEachGuards = [];
    this.afterEachHooks = [];
    this.currentRoute = null;
    this.basePath = options.basePath || '';
    this.mode = options.mode || 'history';
    this._started = false;
  }

  addRoute(path, handler, meta = {}) {
    const route = {
      path,
      handler,
      meta: {
        requiresAuth: false,
        permissions: [],
        roles: [],
        ...meta,
      },
    };
    this.routes.set(this._normalizePath(path), route);
    return this;
  }

  _normalizePath(path) {
    if (!path.startsWith('/')) path = '/' + path;
    return path.replace(/\/+/g, '/');
  }

  _matchPath(pathname) {
    const normalized = this._normalizePath(pathname);
    for (const [routePath, route] of this.routes) {
      const regex = this._pathToRegex(routePath);
      const match = normalized.match(regex);
      if (match) {
        const params = {};
        const paramNames = this._getParamNames(routePath);
        paramNames.forEach((name, index) => {
          params[name] = match[index + 1];
        });
        return { route, params };
      }
    }
    return null;
  }

  _pathToRegex(path) {
    const regexPath = path
      .replace(/:([^/]+)/g, '([^/]+)')
      .replace(/\*/g, '.*');
    return new RegExp(`^${regexPath}$`);
  }

  _getParamNames(path) {
    const matches = path.match(/:([^/]+)/g);
    return matches ? matches.map(m => m.slice(1)) : [];
  }

  beforeEach(guard) {
    this.beforeEachGuards.push(guard);
    return this;
  }

  afterEach(hook) {
    this.afterEachHooks.push(hook);
    return this;
  }

  onNotFound(handler) {
    this.notFoundHandler = handler;
    return this;
  }

  onError(handler) {
    this.errorHandler = handler;
    return this;
  }

  async navigate(to, options = {}) {
    const url = this.basePath + to;
    if (options.replace) {
      history.replaceState({}, '', url);
    } else {
      history.pushState({}, '', url);
    }
    await this._handleRouteChange();
  }

  async _handleRouteChange() {
    const pathname = window.location.pathname.slice(this.basePath.length) || '/';

    const match = this._matchPath(pathname);
    if (!match) {
      await this._handleNotFound(pathname);
      return;
    }

    const { route, params } = match;

    for (const guard of this.beforeEachGuards) {
      const result = await guard(route, params);
      if (result === false) {
        return;
      }
      if (result instanceof RouterError) {
        await this._handleRouterError(result);
        return;
      }
      if (result && typeof result === 'string') {
        await this.navigate(result, { replace: true });
        return;
      }
    }

    this.currentRoute = { ...route, params, path: pathname };

    try {
      await route.handler(this.currentRoute);
    } catch (error) {
      await this._handleError(error);
    }

    for (const hook of this.afterEachHooks) {
      await hook(this.currentRoute);
    }
  }

  async _handleNotFound(pathname) {
    if (this.notFoundHandler) {
      await this.notFoundHandler(pathname);
    } else {
      console.warn(`Route non trouvée: ${pathname}`);
    }
  }

  async _handleRouterError(error) {
    if (error.code === 401 && error.redirectTo) {
      await this.navigate(error.redirectTo, { replace: true });
    } else if (error.code === 403 && error.redirectTo) {
      await this.navigate(error.redirectTo, { replace: true });
    } else if (this.errorHandler) {
      await this.errorHandler(error);
    } else {
      console.error('Erreur de navigation:', error);
    }
  }

  async _handleError(error) {
    if (this.errorHandler) {
      await this.errorHandler(error);
    } else {
      console.error('Erreur dans le handler de route:', error);
    }
  }

  start() {
    if (this._started) return;

    window.addEventListener('popstate', () => this._handleRouteChange());

    document.addEventListener('click', (e) => {
      const link = e.target.closest('a[data-link]');
      if (link) {
        e.preventDefault();
        const href = link.getAttribute('href');
        if (href) this.navigate(href);
      }
    });

    this._handleRouteChange();
    this._started = true;
  }

  getCurrentRoute() {
    return this.currentRoute;
  }

  getPath() {
    return this.currentRoute?.path || '/';
  }
}

function createAuthGuard(authStore) {
  return async (route) => {
    if (!route.meta.requiresAuth) return true;

    if (!authStore.authenticated) {
      if (authStore.loading) {
        await new Promise(resolve => {
          const unsubscribe = authStore.subscribe(state => {
            if (!state.loading) {
              unsubscribe();
              resolve();
            }
          });
        });
      }

      if (!authStore.authenticated) {
        return new RouterError('Non authentifié', 401, '/login');
      }
    }

    if (route.meta.permissions.length > 0) {
      const hasPerm = authStore.hasAnyPermission(route.meta.permissions);
      if (!hasPerm) {
        return new RouterError('Permissions insuffisantes', 403, '/403');
      }
    }

    if (route.meta.roles.length > 0) {
      const hasRole = route.meta.roles.some(r => authStore.hasRole(r));
      if (!hasRole) {
        return new RouterError('Rôle requis', 403, '/403');
      }
    }

    return true;
  };
}

function createNotFoundPage() {
  return `
    <div class="error-page error-page--404">
      <div class="error-page-content">
        <h1>404</h1>
        <p>Page non trouvée</p>
        <a href="/dashboard" data-link class="btn btn-primary">Retour au tableau de bord</a>
      </div>
    </div>
  `;
}

function createForbiddenPage() {
  return `
    <div class="error-page error-page--403">
      <div class="error-page-content">
        <h1>403</h1>
        <p>Accès refusé</p>
        <p class="error-page-description">Vous n'avez pas les permissions nécessaires pour accéder à cette page.</p>
        <a href="/dashboard" data-link class="btn btn-primary">Retour au tableau de bord</a>
      </div>
    </div>
  `;
}

const router = new Router({
  basePath: '',
  mode: 'history',
});

export { Router, router, createAuthGuard, createNotFoundPage, createForbiddenPage, RouterError };