import { router, createAuthGuard, createNotFoundPage, createForbiddenPage } from './router/router.js';
import { authStore } from './stores/auth.js';
import { AppShell } from './components/AppShell.js';
import { createModulePlaceholderPage } from './pages/ModulePlaceholder.js';
import { createLoginPage } from './pages/LoginPage.js';
import { createRegisterPage } from './pages/RegisterPage.js';
import { createAdministrationPage } from './pages/AdministrationPage.js';
import { createBuildingsPage } from './pages/BuildingsPage.js';
import { createBuildingRefsPage } from './pages/BuildingRefsPage.js';
import { createEquipmentPage } from './pages/EquipmentPage.js';
import { createEquipmentRefsPage } from './pages/EquipmentRefsPage.js';
import { createMaintenanceDashboardPage } from './pages/MaintenanceDashboardPage.js';
import { createMaintenanceRequestsPage } from './pages/MaintenanceRequestsPage.js';
import { createMaintenanceWorkOrdersPage } from './pages/MaintenanceWorkOrdersPage.js';
import { createMaintenancePreventivePage } from './pages/MaintenancePreventivePage.js';
import { createMaintenanceProvidersPage } from './pages/MaintenanceProvidersPage.js';
import { createMaintenanceContractsPage } from './pages/MaintenanceContractsPage.js';
import { createMaintenanceRefsPage } from './pages/MaintenanceRefsPage.js';
import { createMaintenanceCalendarPage } from './pages/MaintenanceCalendarPage.js';
import { createAIAssistantPage } from './pages/AIAssistantPage.js';

const moduleRoutes = [
  'dashboard',
  'buildings',
  'equipment',
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
];

let appShell = null;
let administrationPage = null;
let buildingsPage = null;
let buildingRefsPage = null;
let equipmentPage = null;
let equipmentRefsPage = null;
let maintenanceDashboardPage = null;
let maintenanceRequestsPage = null;
let maintenanceWorkOrdersPage = null;
let maintenancePreventivePage = null;
let maintenanceProvidersPage = null;
let maintenanceContractsPage = null;
let maintenanceRefsPage = null;
let maintenanceCalendarPage = null;
let aiAssistantPage = null;

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
    }, { requiresAuth: true, permissions: ['building.view'] })
    .addRoute('/equipment', async (route) => {
      await showEquipmentPage(route);
    }, { requiresAuth: true, permissions: ['equipment.view'] })
    .addRoute('/equipment/refs', async (route) => {
      await showEquipmentRefsPage(route);
    }, { requiresAuth: true, permissions: ['equipment.view'] })
    .addRoute('/maintenance', async (route) => {
      await showMaintenanceDashboardPage(route);
    }, { requiresAuth: true, permissions: ['maintenance.view'] })
    .addRoute('/maintenance/requests', async (route) => {
      await showMaintenanceRequestsPage(route);
    }, { requiresAuth: true, permissions: ['maintenance.view'] })
    .addRoute('/maintenance/work-orders', async (route) => {
      await showMaintenanceWorkOrdersPage(route);
    }, { requiresAuth: true, permissions: ['maintenance.view'] })
    .addRoute('/maintenance/preventive', async (route) => {
      await showMaintenancePreventivePage(route);
    }, { requiresAuth: true, permissions: ['maintenance.view'] })
    .addRoute('/maintenance/providers', async (route) => {
      await showMaintenanceProvidersPage(route);
    }, { requiresAuth: true, permissions: ['maintenance.view'] })
    .addRoute('/maintenance/contracts', async (route) => {
      await showMaintenanceContractsPage(route);
    }, { requiresAuth: true, permissions: ['maintenance.view'] })
    .addRoute('/maintenance/refs', async (route) => {
      await showMaintenanceRefsPage(route);
    }, { requiresAuth: true, permissions: ['maintenance.view'] })
    .addRoute('/maintenance/calendar', async (route) => {
      await showMaintenanceCalendarPage(route);
    }, { requiresAuth: true, permissions: ['maintenance.view'] })
    .addRoute('/ai', async (route) => {
      await showAIAssistantPage(route);
    }, { requiresAuth: true, permissions: ['ai.use'] });

  moduleRoutes.forEach(module => {
    if (module === 'dashboard' || module === 'administration' || module === 'buildings' || module === 'equipment') return;
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
    await ensureAdministrationPage();
    await ensureBuildingsPage();
    await ensureBuildingRefsPage();
    await ensureEquipmentPage();
    await ensureEquipmentRefsPage();
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

async function ensureAdministrationPage() {
  if (!administrationPage) {
    administrationPage = createAdministrationPage(router);
    await administrationPage.initialize();
  }
  return administrationPage;
}

async function ensureBuildingsPage() {
  if (!buildingsPage) {
    buildingsPage = createBuildingsPage(router);
    await buildingsPage.initialize();
  }
  return buildingsPage;
}

async function ensureBuildingRefsPage() {
  if (!buildingRefsPage) {
    buildingRefsPage = createBuildingRefsPage(router);
    await buildingRefsPage.initialize();
  }
  return buildingRefsPage;
}

async function ensureEquipmentPage() {
  if (!equipmentPage) {
    equipmentPage = createEquipmentPage(router);
    await equipmentPage.initialize();
  }
  return equipmentPage;
}

async function ensureEquipmentRefsPage() {
  if (!equipmentRefsPage) {
    equipmentRefsPage = createEquipmentRefsPage(router);
    await equipmentRefsPage.initialize();
  }
  return equipmentRefsPage;
}

async function ensureMaintenanceDashboardPage() {
  if (!maintenanceDashboardPage) {
    maintenanceDashboardPage = createMaintenanceDashboardPage(router);
    await maintenanceDashboardPage.initialize();
  }
  return maintenanceDashboardPage;
}

async function ensureMaintenanceRequestsPage() {
  if (!maintenanceRequestsPage) {
    maintenanceRequestsPage = createMaintenanceRequestsPage(router);
    await maintenanceRequestsPage.initialize();
  }
  return maintenanceRequestsPage;
}

async function ensureMaintenanceWorkOrdersPage() {
  if (!maintenanceWorkOrdersPage) {
    maintenanceWorkOrdersPage = createMaintenanceWorkOrdersPage(router);
    await maintenanceWorkOrdersPage.initialize();
  }
  return maintenanceWorkOrdersPage;
}

async function ensureMaintenancePreventivePage() {
  if (!maintenancePreventivePage) {
    maintenancePreventivePage = createMaintenancePreventivePage(router);
    await maintenancePreventivePage.initialize();
  }
  return maintenancePreventivePage;
}

async function ensureMaintenanceProvidersPage() {
  if (!maintenanceProvidersPage) {
    maintenanceProvidersPage = createMaintenanceProvidersPage(router);
    await maintenanceProvidersPage.initialize();
  }
  return maintenanceProvidersPage;
}

async function ensureMaintenanceContractsPage() {
  if (!maintenanceContractsPage) {
    maintenanceContractsPage = createMaintenanceContractsPage(router);
    await maintenanceContractsPage.initialize();
  }
  return maintenanceContractsPage;
}

async function ensureMaintenanceRefsPage() {
  if (!maintenanceRefsPage) {
    maintenanceRefsPage = createMaintenanceRefsPage(router);
    await maintenanceRefsPage.initialize();
  }
  return maintenanceRefsPage;
}

async function ensureMaintenanceCalendarPage() {
  if (!maintenanceCalendarPage) {
    maintenanceCalendarPage = createMaintenanceCalendarPage(router);
    await maintenanceCalendarPage.initialize();
  }
  return maintenanceCalendarPage;
}

async function ensureAIAssistantPage() {
  if (!aiAssistantPage) {
    aiAssistantPage = createAIAssistantPage(router);
    await aiAssistantPage.initialize();
  }
  return aiAssistantPage;
}

async function showAdministrationPage(route) {
  if (!appShell) return;
  appShell.showLoading();

  try {
    const page = await ensureAdministrationPage();
    const content = page.render();
    appShell.showContent(content);
  } catch (error) {
    console.error('Erreur affichage administration:', error);
    appShell.showError(error);
  }
}

async function showBuildingsPage(route) {
  if (!appShell) return;
  appShell.showLoading();

  try {
    const page = await ensureBuildingsPage();
    const content = page.render();
    appShell.showContent(content);
    page.loadData();
  } catch (error) {
    console.error('Erreur affichage bâtiments:', error);
    appShell.showError(error);
  }
}

async function showBuildingRefsPage(route) {
  if (!appShell) return;
  appShell.showLoading();

  try {
    const page = await ensureBuildingRefsPage();
    const content = page.render();
    appShell.showContent(content);
  } catch (error) {
    console.error('Erreur affichage référentiels:', error);
    appShell.showError(error);
  }
}

async function showEquipmentPage(route) {
  if (!appShell) return;
  appShell.showLoading();

  try {
    const page = await ensureEquipmentPage();
    const content = page.render();
    appShell.showContent(content);
    page.loadData();
  } catch (error) {
    console.error('Erreur affichage équipements:', error);
    appShell.showError(error);
  }
}

async function showEquipmentRefsPage(route) {
  if (!appShell) return;
  appShell.showLoading();

  try {
    const page = await ensureEquipmentRefsPage();
    const content = page.render();
    appShell.showContent(content);
  } catch (error) {
    console.error('Erreur affichage référentiels équipement:', error);
    appShell.showError(error);
  }
}

async function showMaintenanceDashboardPage(route) {
  if (!appShell) return;
  appShell.showLoading();

  try {
    const page = await ensureMaintenanceDashboardPage();
    const content = page.render();
    appShell.showContent(content);
    page.loadData();
  } catch (error) {
    console.error('Erreur affichage tableau de bord maintenance:', error);
    appShell.showError(error);
  }
}

async function showMaintenanceRequestsPage(route) {
  if (!appShell) return;
  appShell.showLoading();

  try {
    const page = await ensureMaintenanceRequestsPage();
    const content = page.render();
    appShell.showContent(content);
    page.loadData();
  } catch (error) {
    console.error('Erreur affichage demandes maintenance:', error);
    appShell.showError(error);
  }
}

async function showMaintenanceWorkOrdersPage(route) {
  if (!appShell) return;
  appShell.showLoading();

  try {
    const page = await ensureMaintenanceWorkOrdersPage();
    const content = page.render();
    appShell.showContent(content);
    page.loadData();
  } catch (error) {
    console.error('Erreur affichage ordres de travail:', error);
    appShell.showError(error);
  }
}

async function showMaintenancePreventivePage(route) {
  if (!appShell) return;
  appShell.showLoading();

  try {
    const page = await ensureMaintenancePreventivePage();
    const content = page.render();
    appShell.showContent(content);
    page.loadData();
  } catch (error) {
    console.error('Erreur affichage maintenance préventive:', error);
    appShell.showError(error);
  }
}

async function showMaintenanceProvidersPage(route) {
  if (!appShell) return;
  appShell.showLoading();

  try {
    const page = await ensureMaintenanceProvidersPage();
    const content = page.render();
    appShell.showContent(content);
    page.loadData();
  } catch (error) {
    console.error('Erreur affichage prestataires:', error);
    appShell.showError(error);
  }
}

async function showMaintenanceContractsPage(route) {
  if (!appShell) return;
  appShell.showLoading();

  try {
    const page = await ensureMaintenanceContractsPage();
    const content = page.render();
    appShell.showContent(content);
    page.loadData();
  } catch (error) {
    console.error('Erreur affichage contrats:', error);
    appShell.showError(error);
  }
}

async function showMaintenanceRefsPage(route) {
  if (!appShell) return;
  appShell.showLoading();

  try {
    const page = await ensureMaintenanceRefsPage();
    const content = page.render();
    appShell.showContent(content);
    page.loadData();
  } catch (error) {
    console.error('Erreur affichage referentiels maintenance:', error);
    appShell.showError(error);
  }
}

async function showMaintenanceCalendarPage(route) {
  if (!appShell) return;
  appShell.showLoading();

  try {
    const page = await ensureMaintenanceCalendarPage();
    const content = page.render();
    appShell.showContent(content);
    page.loadData();
  } catch (error) {
    console.error('Erreur affichage calendrier maintenance:', error);
    appShell.showError(error);
  }
}

async function showAIAssistantPage(route) {
  if (!appShell) return;
  appShell.showLoading();

  try {
    const page = await ensureAIAssistantPage();
    const content = page.render();
    appShell.showContent(content);
    page.loadData();
  } catch (error) {
    console.error('Erreur affichage assistant IA:', error);
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