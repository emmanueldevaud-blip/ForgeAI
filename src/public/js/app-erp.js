import { router, createAuthGuard, createNotFoundPage, createForbiddenPage } from './router/router.js';
import { authStore } from './stores/auth.js';
import { AppShell } from './components/AppShell.js?v=5';
import { createModulePlaceholderPage } from './pages/ModulePlaceholder.js?v=3';
import { createLoginPage } from './pages/LoginPage.js';
import { createRegisterPage } from './pages/RegisterPage.js';
import { createAdministrationPage } from './pages/AdministrationPage.js?v=4';
import { createBuildingsPage } from './pages/BuildingsPage.js?v=5';
import { createBuildingRefsPage } from './pages/BuildingRefsPage.js';
import { createEquipmentPage } from './pages/EquipmentPage.js?v=2';
import { createEquipmentRefsPage } from './pages/EquipmentRefsPage.js';
import { createDashboardPage } from './pages/DashboardPage.js?v=2';
import { createMaintenanceRequestsPage } from './pages/MaintenanceRequestsPage.js';
import { createMaintenanceWorkOrdersPage } from './pages/MaintenanceWorkOrdersPage.js';
import { createMaintenancePreventivePage } from './pages/MaintenancePreventivePage.js';
import { createMaintenanceProvidersPage } from './pages/MaintenanceProvidersPage.js';
import { createMaintenanceContractsPage } from './pages/MaintenanceContractsPage.js';
import { createMaintenanceRefsPage } from './pages/MaintenanceRefsPage.js';
import { createMaintenanceCalendarPage } from './pages/MaintenanceCalendarPage.js';
import { createAIAssistantPage } from './pages/AIAssistantPage.js?v=21';
import { createHousingPage } from './pages/HousingPage.js';
import { createProfilePage } from './pages/ProfilePage.js?v=2';
import { createCleaningVolunteersPage } from './pages/CleaningVolunteersPage.js?v=4';
import { createAdministrativeProgramsPage } from './pages/AdministrativeProgramsPage.js';
import { createSportDashboardPage } from './pages/SportDashboardPage.js?v=5';
import { createSportActivitiesPage } from './pages/SportActivitiesPage.js?v=4';
import { createSportGarminPage } from './pages/SportGarminPage.js?v=5';
import { createSportHealthPage } from './pages/SportHealthPage.js?v=1';
import { createSportAnalysesPage } from './pages/SportAnalysesPage.js?v=1';
import { createSportGoalsPage } from './pages/SportGoalsPage.js?v=1';
import { createAgendaPage } from './pages/AgendaPage.js?v=24';
import { createDomotiquePage } from './pages/DomotiquePage.js?v=8';
import { createDomotiqueConfigPage } from './pages/DomotiqueConfigPage.js?v=8';

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
  'administratif',
];

let appShell = null;
let dashboardPage = null;
let administrationPage = null;
let buildingsPage = null;
let buildingRefsPage = null;
let equipmentPage = null;
let equipmentRefsPage = null;
let maintenanceRequestsPage = null;
let maintenanceWorkOrdersPage = null;
let maintenancePreventivePage = null;
let maintenanceProvidersPage = null;
let maintenanceContractsPage = null;
let maintenanceRefsPage = null;
let maintenanceCalendarPage = null;
let aiAssistantPage = null;
let housingPage = null;
let volunteersPage = null;
let administrativeProgramsPage = null;
let sportDashboardPage = null;
let sportActivitiesPage = null;
let sportGarminPage = null;
let sportHealthPage = null;
let sportAnalysesPage = null;
let sportGoalsPage = null;
let agendaPage = null;
let domotiquePage = null;
let domotiqueConfigPage = null;

async function initializeApp() {
  const app = document.getElementById('app');
  if (!app) return;

  /* Enregistrement des le demarrage (idempotent) : permet la mise a jour du
     cache statique apres un deploiement et prepare le push. Silencieux si
     non supporte (http hors localhost). */
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  }

  appShell = new AppShell(router);
  await appShell.initialize();

  const authGuard = createAuthGuard(authStore);

  const initialPath = window.location.pathname;

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
      await showDashboardPage(route);
    }, { requiresAuth: true })
    .addRoute('/profile', async () => {
      const profilePage = createProfilePage(router);
      appShell.showContent(profilePage.render());
    }, { requiresAuth: true })
    .addRoute('/administration', async (route) => {
      await showAdministrationPage(route);
    }, { requiresAuth: true, permissions: ['admin.access'] })
    .addRoute('/administration/users', async (route) => {
      await showAdministrationPage(route);
    }, { requiresAuth: true, permissions: ['admin.access'] })
    .addRoute('/administration/groups', async (route) => {
      await showAdministrationPage(route);
    }, { requiresAuth: true, permissions: ['group_view'] })
    .addRoute('/administration/roles', async (route) => {
      await showAdministrationPage(route);
    }, { requiresAuth: true, permissions: ['role_view'] })
    .addRoute('/administration/permissions', async (route) => {
      await showAdministrationPage(route);
    }, { requiresAuth: true, permissions: ['permission_view'] })
    .addRoute('/administration/audit', async (route) => {
      await showAdministrationPage(route);
    }, { requiresAuth: true, permissions: ['audit_log_view'] })
    .addRoute('/administration/active-directory', async (route) => {
      await showAdministrationPage(route);
    }, { requiresAuth: true, permissions: ['ad_config'] })
    .addRoute('/administration/smtp', async (route) => {
      await showAdministrationPage(route);
    }, { requiresAuth: true, permissions: ['settings_view'] })
    .addRoute('/administration/ai', async (route) => {
      await showAdministrationPage(route);
    }, { requiresAuth: true, permissions: ['settings_view'] })
    .addRoute('/administration/programs', async (route) => {
      await showAdministrativeProgramsPage(route);
    }, { requiresAuth: true, permissions: ['administration.programs.view'] })
    .addRoute('/administratif', async (route) => {
      await showAdministrativeProgramsPage(route);
    }, { requiresAuth: true, permissions: ['administration.programs.view'] })
    .addRoute('/administratif/programs', async (route) => {
      await showAdministrativeProgramsPage(route);
    }, { requiresAuth: true, permissions: ['administration.programs.view'] })
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
      await showMaintenanceRequestsPage(route);
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
    }, { requiresAuth: true, permissions: ['maintenance.manage_providers'] })
    .addRoute('/maintenance/contracts', async (route) => {
      await showMaintenanceContractsPage(route);
    }, { requiresAuth: true, permissions: ['maintenance.manage_contracts'] })
    .addRoute('/maintenance/refs', async (route) => {
      await showMaintenanceRefsPage(route);
    }, { requiresAuth: true, permissions: ['maintenance.manage_referentials'] })
    .addRoute('/maintenance/calendar', async (route) => {
      await showMaintenanceCalendarPage(route);
    }, { requiresAuth: true, permissions: ['maintenance.view'] })
    .addRoute('/ai', async (route) => {
      await showAIAssistantPage(route);
    }, { requiresAuth: true, permissions: ['ai.use'] })
    .addRoute('/housing', async (route) => {
      await showHousingPage(route);
    }, { requiresAuth: true, permissions: ['housing.view'] })
    .addRoute('/sport', async (route) => {
      await showSportDashboardPage(route);
    }, { requiresAuth: true, permissions: ['sport.access'] })
    .addRoute('/sport/activities', async (route) => {
      await showSportActivitiesPage(route);
    }, { requiresAuth: true, permissions: ['sport.activities.read'] })
    .addRoute('/sport/goals', async (route) => {
      await showSportGoalsPage(route);
    }, { requiresAuth: true, permissions: ['sport.goals.read'] })
    .addRoute('/sport/garmin', async (route) => {
      await showSportGarminPage(route);
    }, { requiresAuth: true, permissions: ['sport.activities.write'] })
    .addRoute('/sport/health', async (route) => {
      await showSportHealthPage(route);
    }, { requiresAuth: true, permissions: ['sport.access'] })
    .addRoute('/sport/analyses', async (route) => {
      await showSportAnalysesPage(route);
    }, { requiresAuth: true, permissions: ['sport.analysis.read'] })
    .addRoute('/domotique', async (route) => {
      await showDomotiquePage(route);
    }, { requiresAuth: true, permissions: ['domotique.view'] })
    .addRoute('/domotique/config', async (route) => {
      await showDomotiqueConfigPage(route);
    }, { requiresAuth: true, permissions: ['domotique.configure'] })
    .addRoute('/agenda', async (route) => {
      await showAgendaPage(route);
    }, { requiresAuth: true, permissions: ['agenda.access'] })
    .addRoute('/volunteers', async (route) => {
      await showVolunteersPage(route);
    }, { requiresAuth: true, permissions: ['volunteers.view'] });

  const moduleRoutePermissions = {
    cleaning: ['cleaning.view'],
    people: ['people.view'],
    studies: ['studies.view'],
    surveys: ['surveys.view'],
    quoting: ['quoting.view'],
    inventory: ['inventory.view'],
    purchasing: ['purchasing.view'],
    suppliers: ['suppliers.view'],
    documents: ['documents.view'],
    reports: ['reports.view'],
  };

  moduleRoutes.forEach(module => {
    if (module === 'dashboard' || module === 'administration' || module === 'administratif'
      || module === 'buildings' || module === 'equipment' || module === 'sport'
      || module === 'housing' || module === 'maintenance') return;
    router.addRoute(`/${module}`, async (route) => {
      await showModulePage(route);
    }, { requiresAuth: true, permissions: moduleRoutePermissions[module] || [] });
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
    if (initialPath === '/') {
      router.navigate('/dashboard', { replace: true });
    }
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

async function ensureDashboardPage() {
  if (!dashboardPage) {
    dashboardPage = createDashboardPage(router);
    await dashboardPage.initialize();
  }
  return dashboardPage;
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

async function ensureHousingPage() {
  if (!housingPage) {
    housingPage = createHousingPage(router);
    await housingPage.initialize();
  }
  return housingPage;
}

async function ensureVolunteersPage() {
  if (!volunteersPage) {
    volunteersPage = createCleaningVolunteersPage(router);
    await volunteersPage.initialize();
  }
  return volunteersPage;
}

async function ensureAdministrativeProgramsPage() {
  if (!administrativeProgramsPage) {
    administrativeProgramsPage = createAdministrativeProgramsPage(router);
    await administrativeProgramsPage.initialize();
  }
  return administrativeProgramsPage;
}

async function showAdministrativeProgramsPage(route) {
  if (!appShell) return;
  appShell.showLoading();
  try {
    const page = await ensureAdministrativeProgramsPage();
    appShell.showContent(page.render());
  } catch (error) {
    console.error('Erreur affichage programmes administratifs:', error);
    appShell.showError(error);
  }
}

async function ensureSportDashboardPage() {
  if (!sportDashboardPage) {
    sportDashboardPage = createSportDashboardPage(router);
    await sportDashboardPage.initialize();
  }
  return sportDashboardPage;
}

async function ensureSportActivitiesPage() {
  if (!sportActivitiesPage) {
    sportActivitiesPage = createSportActivitiesPage(router);
  }
  return sportActivitiesPage;
}

async function ensureSportGarminPage() {
  if (!sportGarminPage) {
    sportGarminPage = createSportGarminPage(router);
    await sportGarminPage.initialize();
  }
  return sportGarminPage;
}

async function ensureSportHealthPage() {
  if (!sportHealthPage) {
    sportHealthPage = createSportHealthPage(router);
    await sportHealthPage.initialize();
  }
  return sportHealthPage;
}

async function ensureSportAnalysesPage() {
  if (!sportAnalysesPage) {
    sportAnalysesPage = createSportAnalysesPage(router);
  }
  await sportAnalysesPage.initialize();
  return sportAnalysesPage;
}

async function ensureSportGoalsPage() {
  if (!sportGoalsPage) {
    sportGoalsPage = createSportGoalsPage(router);
  }
  await sportGoalsPage.initialize();
  return sportGoalsPage;
}

async function ensureAgendaPage() {
  if (!agendaPage) {
    agendaPage = createAgendaPage(router);
    await agendaPage.initialize();
  }
  return agendaPage;
}

async function showAgendaPage(route) {
  if (!appShell) return;
  appShell.showLoading();
  try {
    const page = await ensureAgendaPage();
    appShell.showContent(page.render());
  } catch (error) {
    console.error('Erreur affichage agenda:', error);
    appShell.showError(error);
  }
}

async function ensureDomotiquePage() {
  if (!domotiquePage) {
    domotiquePage = createDomotiquePage(router);
  }
  await domotiquePage.initialize();
  return domotiquePage;
}

async function ensureDomotiqueConfigPage() {
  if (!domotiqueConfigPage) {
    domotiqueConfigPage = createDomotiqueConfigPage(router);
  }
  await domotiqueConfigPage.initialize();
  return domotiqueConfigPage;
}

async function showDomotiquePage(route) {
  if (!appShell) return;
  appShell.showLoading();
  try {
    const page = await ensureDomotiquePage();
    appShell.showContent(page.render());
  } catch (error) {
    console.error('Erreur affichage Domotique:', error);
    appShell.showError(error);
  }
}

async function showDomotiqueConfigPage(route) {
  if (!appShell) return;
  appShell.showLoading();
  try {
    const page = await ensureDomotiqueConfigPage();
    appShell.showContent(page.render());
  } catch (error) {
    console.error('Erreur affichage configuration Domotique:', error);
    appShell.showError(error);
  }
}

async function showSportGarminPage(route) {
  if (!appShell) return;
  appShell.showLoading();
  try {
    const page = await ensureSportGarminPage();
    appShell.showContent(page.render());
  } catch (error) {
    console.error('Erreur affichage Garmin Sport:', error);
    appShell.showError(error);
  }
}

async function showSportHealthPage(route) {
  if (!appShell) return;
  appShell.showLoading();
  try {
    const page = await ensureSportHealthPage();
    appShell.showContent(page.render());
  } catch (error) {
    console.error('Erreur affichage Santé Sport:', error);
    appShell.showError(error);
  }
}

async function showSportAnalysesPage(route) {
  if (!appShell) return;
  appShell.showLoading();
  try {
    const page = await ensureSportAnalysesPage();
    appShell.showContent(page.render());
  } catch (error) {
    console.error('Erreur affichage Analyses Sport:', error);
    appShell.showError(error);
  }
}

async function showSportGoalsPage(route) {
  if (!appShell) return;
  appShell.showLoading();
  try {
    const page = await ensureSportGoalsPage();
    appShell.showContent(page.render());
  } catch (error) {
    console.error('Erreur affichage Objectifs Sport:', error);
    appShell.showError(error);
  }
}

async function showSportDashboardPage(route) {
  if (!appShell) return;
  appShell.showLoading();
  try {
    const page = await ensureSportDashboardPage();
    await page.initialize();
    if (router.getCurrentRoute()?.path !== '/sport') return;
    appShell.showContent(page.render());
  } catch (error) {
    console.error('Erreur affichage Sport:', error);
    appShell.showError(error);
  }
}

async function showSportActivitiesPage(route) {
  if (!appShell) return;
  appShell.showLoading();
  try {
    const page = await ensureSportActivitiesPage();
    appShell.showContent(page.render());
    await page.initialize();
    if (router.getCurrentRoute()?.path !== '/sport/activities') return;
    appShell.showContent(page.render());
  } catch (error) {
    console.error('Erreur affichage activités sportives:', error);
    appShell.showError(error);
  }
}

async function showVolunteersPage(route) {
  if (!appShell) return;
  appShell.showLoading();

  try {
    const page = await ensureVolunteersPage();
    const content = page.render();
    appShell.showContent(content);
    page.loadData();
  } catch (error) {
    console.error('Erreur affichage volontaires:', error);
    appShell.showError(error);
  }
}

async function showDashboardPage(route) {
  if (!appShell) return;
  appShell.showLoading();

  try {
    const page = await ensureDashboardPage();
    const content = page.render();
    appShell.showContent(content);
    page.loadData();
  } catch (error) {
    console.error('Erreur affichage tableau de bord:', error);
    appShell.showError(error);
  }
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

async function showHousingPage(route) {
  if (!appShell) return;
  appShell.showLoading();

  try {
    const page = await ensureHousingPage();
    const content = page.render();
    appShell.showContent(content);
  } catch (error) {
    console.error('Erreur affichage hébergements:', error);
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
