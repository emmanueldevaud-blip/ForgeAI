class ApiError extends Error {
  constructor(message, status, data, response) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
    this.response = response;
  }
}

class ApiClient {
  constructor(baseUrl = '') {
    this.baseUrl = baseUrl;
    this.defaultHeaders = {
      'Content-Type': 'application/json',
    };
  }

  async request(endpoint, options = {}) {
    const url = `${this.baseUrl}${endpoint}`;
    const config = {
      headers: { ...this.defaultHeaders, ...options.headers },
      credentials: 'include',
      ...options,
    };

    if (config.body && typeof config.body === 'object' && !(config.body instanceof FormData)) {
      config.body = JSON.stringify(config.body);
    }

    let response;
    try {
      response = await fetch(url, config);
    } catch (error) {
      throw new ApiError(
        'Erreur de connexion au serveur',
        0,
        null,
        null
      );
    }

    let data;
    const contentType = response.headers.get('content-type');
    if (contentType && contentType.includes('application/json')) {
      try {
        data = await response.json();
      } catch {
        data = null;
      }
    } else if (response.status !== 204) {
      try {
        data = await response.text();
      } catch {
        data = null;
      }
    }

    if (!response.ok) {
      let message = data?.detail || data?.message || `Erreur ${response.status}`;

      if (response.status === 401) {
        message = 'Session expirée. Veuillez vous reconnecter.';
      } else if (response.status === 403) {
        message = 'Accès refusé. Permissions insuffisantes.';
      } else if (response.status === 404) {
        message = 'Ressource non trouvée.';
      } else if (response.status >= 500) {
        message = 'Erreur serveur. Veuillez réessayer plus tard.';
      }

      throw new ApiError(message, response.status, data, response);
    }

    return data;
  }

  get(endpoint, options = {}) {
    return this.request(endpoint, { ...options, method: 'GET' });
  }

  post(endpoint, body, options = {}) {
    return this.request(endpoint, { ...options, method: 'POST', body });
  }

  put(endpoint, body, options = {}) {
    return this.request(endpoint, { ...options, method: 'PUT', body });
  }

  patch(endpoint, body, options = {}) {
    return this.request(endpoint, { ...options, method: 'PATCH', body });
  }

  delete(endpoint, options = {}) {
    return this.request(endpoint, { ...options, method: 'DELETE' });
  }

  setAuthToken(token) {
    if (token) {
      this.defaultHeaders['Authorization'] = `Bearer ${token}`;
    } else {
      delete this.defaultHeaders['Authorization'];
    }
  }

  clearAuthToken() {
    delete this.defaultHeaders['Authorization'];
  }
}

const api = new ApiClient('/auth');
const todoApi = new ApiClient('/api');
const modulesApi = new ApiClient('/modules');

export { ApiClient, ApiError, api, todoApi, modulesApi };