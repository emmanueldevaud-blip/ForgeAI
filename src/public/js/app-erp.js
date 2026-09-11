import { router, createAuthGuard, createNotFoundPage, createForbiddenPage } from './router/router.js';
import { authStore } from './stores/auth.js';
import { AppShell } from './components/AppShell.js';
import { createModulePlaceholderPage } from './pages/ModulePlaceholder.js';
import { createLoginPage } from './pages/LoginPage.js';
import { createRegisterPage } from './pages/RegisterPage.js';
import { createAdministrationPage } from './pages/AdministrationPage.js';
import { createBuildingsPage } from './pages/BuildingsPage.js';
import { createBuildingRefsPage } from './pages/BuildingRefsPage.js';

const moduleRoutes = [
  'dashboard',
  'buildings',
  'housing',
  'maintenance',
  'cleaning',
  'people',
  'studies',
  'surveys',
  'quoting',
  'inventory',
  'purchasing',
  'suppliers',
  'documents',
  'reports',
  'administration',
  'todos',
];

let appShell = null;
let administrationPage = null;
let buildingsPage = null;
let buildingRefsPage = null;

async function initializeApp() {
  const app = document.getElementById('app');
  if (!app) return;

  appShell = new AppShell(router);
  await appShell.initialize();

  const authGuard = createAuthGuard(authStore);

  router
    .addRoute('/login', async () => {
      if (authStore.authenticated) {
        router.navigate('/dashboard', { replace: true });
        return;
      }
      const loginPage = createLoginPage(router);
      appShell.showContent(loginPage.render());
    })
    .addRoute('/register', async () => {
      if (authStore.authenticated) {
        router.navigate('/dashboard', { replace: true });
        return;
      }
      const registerPage = createRegisterPage(router);
      appShell.showContent(registerPage.render());
    })
    .addRoute('/dashboard', async (route) => {
      await showModulePage(route);
    }, { requiresAuth: true })
    .addRoute('/administration', async (route) => {
      await showAdministrationPage(route);
    }, { requiresAuth: true, permissions: ['admin.access'] })
    .addRoute('/administration/users', async (route) => {
      await showAdministrationPage(route);
    }, { requiresAuth: true, permissions: ['user_view'] })
    .addRoute('/administration/groups', async (route) => {
      await showAdministrationPage(route);
    }, { requiresAuth: true, permissions: ['group_view'] })
    .addRoute('/administration/roles', async (route) => {
      await showAdministrationPage(route);
    }, { requiresAuth: true, permissions: ['role_view'] })
    .addRoute('/administration/permissions', async (route) => {
      await showAdministrationPage(route);
    }, { requiresAuth: true, permissions: ['permission_view'] })
    .addRoute('/administration/active-directory', async (route) => {
      await showAdministrationPage(route);
    }, { requiresAuth: true, permissions: ['ad_config'] })
    .addRoute('/buildings', async (route) => {
      await showBuildingsPage(route);
    }, { requiresAuth: true, permissions: ['building.view'] })
    .addRoute('/buildings/refs', async (route) => {
      await showBuildingRefsPage(route);
    }, { requiresAuth: true, permissions: ['building.view'] });

  moduleRoutes.forEach(module => {
    if (module === 'dashboard' || module === 'administration' || module === 'buildings') return;
    router.addRoute(`/${module}`, async (route) => {
      await showModulePage(route);
    }, { requiresAuth: true });
  });

  router
    .addRoute('/403', () => {
      showForbiddenPage();
    })
    .addRoute('/404', () => {
      showNotFoundPage();
    })
    .onNotFound((pathname) => {
      router.navigate('/404', { replace: true });
    })
    .onError((error) => {
      console.error('Router error:', error);
      if (appShell) appShell.showError(error);
    })
    .beforeEach(authGuard)
    .start();

  await authStore.loadCurrentUser();

  if (authStore.authenticated) {
    administrationPage = createAdministrationPage(router);
    await administrationPage.initialize();

    buildingsPage = createBuildingsPage(router);
    await buildingsPage.initialize();

    buildingRefsPage = createBuildingRefsPage(router);
    await buildingRefsPage.initialize();

    router.navigate('/dashboard', { replace: true });
  } else {
    router.navigate('/login', { replace: true });
  }
}

async function showModulePage(route) {
  if (!appShell) return;
  appShell.showLoading();

  try {
    const placeholder = createModulePlaceholderPage(route.path);
    const content = placeholder.render();
    appShell.showContent(content);
  } catch (error) {
    console.error('Erreur affichage module:', error);
    appShell.showError(error);
  }
}

async function showAdministrationPage(route) {
  if (!appShell || !administrationPage) return;
  appShell.showLoading();

  try {
    const content = administrationPage.render();
    appShell.showContent(content);
  } catch (error) {
    console.error('Erreur affichage administration:', error);
    appShell.showError(error);
  }
}

async function showBuildingsPage(route) {
  if (!appShell || !buildingsPage) return;
  appShell.showLoading();

  try {
    const content = buildingsPage.render();
    appShell.showContent(content);
    buildingsPage.loadData();
  } catch (error) {
    console.error('Erreur affichage bâtiments:', error);
    appShell.showError(error);
  }
}

async function showBuildingRefsPage(route) {
  if (!appShell || !buildingRefsPage) return;
  appShell.showLoading();

  try {
    const content = buildingRefsPage.render();
    appShell.showContent(content);
  } catch (error) {
    console.error('Erreur affichage référentiels:', error);
    appShell.showError(error);
  }
}

function showNotFoundPage() {
  if (!appShell) return;
  const page = createNotFoundPage();
  appShell.showContent(page);
}

function showForbiddenPage() {
  if (!appShell) return;
  const page = createForbiddenPage();
  appShell.showContent(page);
}

document.addEventListener('DOMContentLoaded', initializeApp);

export { router, appShell, initializeApp };