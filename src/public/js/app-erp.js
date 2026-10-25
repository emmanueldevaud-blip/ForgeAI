import { router, createAuthGuard, createNotFoundPage, createForbiddenPage } from './router/router.js?v=2';
import { authStore } from './stores/auth.js';
import { modulesStore } from './stores/modules.js';
import { AppShell } from './components/AppShell.js?v=10';
import { createModulePlaceholderPage } from './pages/ModulePlaceholder.js?v=3';
import { createLoginPage } from './pages/LoginPage.js?v=1';
import { createRegisterPage } from './pages/RegisterPage.js';
import { createAdministrationPage } from './pages/AdministrationPage.js?v=6';
import { createBuildingsPage } from './pages/BuildingsPage.js?v=5';
import { createIntendanceExpensesPage } from './pages/IntendanceExpensesPage.js?v=3';
import { createBuildingRefsPage } from './pages/BuildingRefsPage.js';
import { createEquipmentPage } from './pages/EquipmentPage.js?v=2';
import { createEquipmentRefsPage } from './pages/EquipmentRefsPage.js';
import { createDashboardPage } from './pages/DashboardPage.js?v=2';
import { createMaintenanceRequestsPage } from './pages/MaintenanceRequestsPage.js';
import { createMaintenanceWorkOrdersPage } from './pages/MaintenanceWorkOrdersPage.js';
import { createMaintenancePreventivePage } from './pages/MaintenancePreventivePage.js';
import { createMaintenanceProvidersPage } from './pages/MaintenanceProvidersPage.js';
import { createMaintenanceContractsPage } from './pages/MaintenanceContractsPage.js?v=2';
import { createMaintenanceRefsPage } from './pages/MaintenanceRefsPage.js';
import { createMaintenanceCalendarPage } from './pages/MaintenanceCalendarPage.js';
import { createAIAssistantPage } from './pages/AIAssistantPage.js?v=31';
import { createHousingPage } from './pages/HousingPage.js';
import { createProfilePage } from './pages/ProfilePage.js?v=2';
import { createSettingsPage } from './pages/UserSettingsPage.js?v=1';
import { createCleaningVolunteersPage } from './pages/CleaningVolunteersPage.js?v=4';
import { createAdministrativeProgramsPage } from './pages/AdministrativeProgramsPage.js';
import { createSportDashboardPage } from './pages/SportDashboardPage.js?v=5';
import { createSportActivitiesPage } from './pages/SportActivitiesPage.js?v=4';
import { createSportGarminPage } from './pages/SportGarminPage.js?v=5';
import { createSportHealthPage } from './pages/SportHealthPage.js?v=1';
import { createSportAnalysesPage } from './pages/SportAnalysesPage.js?v=1';
import { createSportGoalsPage } from './pages/SportGoalsPage.js?v=1';
import { createAgendaPage } from './pages/AgendaPage.js?v=77';
import { createAgendaSettingsPage } from './pages/AgendaSettingsPage.js?v=4';
import { createAgendaImportPage } from './pages/AgendaImportPage.js';
import { createHousingImportPage } from './pages/HousingImportPage.js';
import { createDomotiquePage } from './pages/DomotiquePage.js?v=8';
import { createDomotiqueConfigPage } from './pages/DomotiqueConfigPage.js?v=8';
import { createSurveillancePage } from './pages/SurveillancePage.js?v=4';
import { createPhotosPage } from './pages/PhotosPage.js?v=9';
import { createSouvenirsPage } from './pages/SouvenirsPage.js?v=4';
import { createITAssetPage } from './pages/ITAssetPage.js?v=8';

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
  'photos',
  'it_assets',
];

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
  photos: ['photos.delete'],
  it_assets: ['it_asset.view'],
};

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
let housingImportPage = null;
let volunteersPage = null;
let administrativeProgramsPage = null;
let sportDashboardPage = null;
let sportActivitiesPage = null;
let sportGarminPage = null;
let sportHealthPage = null;
let sportAnalysesPage = null;
let sportGoalsPage = null;
let agendaPage = null;
let agendaSettingsPage = null;
let domotiquePage = null;
let domotiqueConfigPage = null;
let surveillancePage = null;
let photosPage = null;
let souvenirsPage = null;
let itAssetPage = null;

// Force inclusion - side effect at module evaluation time
void (function() {
  const _refs = [
    createHousingPage, createHousingImportPage,
    createAgendaPage, createAgendaImportPage, createAgendaSettingsPage,
    createDomotiquePage, createDomotiqueConfigPage, createSurveillancePage,
    createPhotosPage, createSouvenirsPage, createITAssetPage,
    createSportDashboardPage, createSportActivitiesPage, createSportGarminPage,
    createSportHealthPage, createSportAnalysesPage, createSportGoalsPage,
    createBuildingsPage, createEquipmentPage, createEquipmentRefsPage,
    createDashboardPage, createMaintenanceRequestsPage, createMaintenanceWorkOrdersPage,
    createMaintenancePreventivePage, createMaintenanceProvidersPage, createMaintenanceContractsPage,
    createMaintenanceRefsPage, createMaintenanceCalendarPage,
    createAIAssistantPage, createIntendanceExpensesPage, createBuildingRefsPage,
    createAdministrationPage, createModulePlaceholderPage, createLoginPage, createRegisterPage,
    createProfilePage, createSettingsPage, createCleaningVolunteersPage,
    createAdministrativeProgramsPage,
    createPhotosPage, createSouvenirsPage, createITAssetPage,
  ];
  // Prevent dead code elimination
  if (typeof Symbol === 'function') {
    Object.defineProperty(globalThis, Symbol.for('forgeai.page.creators'), {
      value: _refs, configurable: true, writable: true
    });
  }
})();

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

  const authGuard = createAuthGuard(authStore, modulesStore);

  const initialPath = window.location.pathname;

  router
    .addRoute('/login', async () => {
      if (authStore.authenticated) {
        router.navigate('/dashboard', { replace: true });
        return;
      }
      const loginPage = createLoginPage(router);
      appShell.showContent(await loginPage.render());
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
    }, { requiresAuth: true, module: 'dashboard' })
    .addRoute('/profile', async () => {
      const profilePage = createProfilePage(router);
      appShell.showContent(profilePage.render());
    }, { requiresAuth: true })
    .addRoute('/settings', async () => {
      const settingsPage = createSettingsPage(router);
      await settingsPage.initialize();
      appShell.showContent(settingsPage.render());
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
    .addRoute('/administration/modules', async (route) => {
      await showAdministrationPage(route);
    }, { requiresAuth: true, permissions: ['module_view'] })
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
    }, { requiresAuth: true, permissions: ['administration.programs.view'], module: 'administratif' })
    .addRoute('/administratif', async (route) => {
      await showAdministrativeProgramsPage(route);
    }, { requiresAuth: true, permissions: ['administration.programs.view'], module: 'administratif' })
    .addRoute('/administratif/programs', async (route) => {
      await showAdministrativeProgramsPage(route);
    }, { requiresAuth: true, permissions: ['administration.programs.view'], module: 'administratif' })
    .addRoute('/buildings', async (route) => {
      await showBuildingsPage(route);
    }, { requiresAuth: true, permissions: ['building.view'], module: ['buildings', 'gestion_bureaux'] })
    .addRoute('/intendance/expenses', async () => {
      if (!appShell) return;
      const page = createIntendanceExpensesPage();
      appShell.showContent(page.render());
      await page.load();
    }, { requiresAuth: true, permissions: ['intendance.expenses.view'], module: 'gestion_bureaux' })
    .addRoute('/buildings/refs', async (route) => {
      await showBuildingRefsPage(route);
    }, { requiresAuth: true, permissions: ['building.view'], module: ['buildings', 'gestion_bureaux'] })
    .addRoute('/equipment', async (route) => {
      await showEquipmentPage(route);
    }, { requiresAuth: true, permissions: ['equipment.view'], module: ['equipment', 'gestion_bureaux'] })
    .addRoute('/equipment/refs', async (route) => {
      await showEquipmentRefsPage(route);
    }, { requiresAuth: true, permissions: ['equipment.view'], module: ['equipment', 'gestion_bureaux'] })
    .addRoute('/maintenance', async (route) => {
      await showMaintenanceRequestsPage(route);
    }, { requiresAuth: true, permissions: ['maintenance.view'], module: 'maintenance' })
    .addRoute('/maintenance/requests', async (route) => {
      await showMaintenanceRequestsPage(route);
    }, { requiresAuth: true, permissions: ['maintenance.view'], module: 'maintenance' })
    .addRoute('/maintenance/work-orders', async (route) => {
      await showMaintenanceWorkOrdersPage(route);
    }, { requiresAuth: true, permissions: ['maintenance.view'], module: 'maintenance' })
    .addRoute('/maintenance/preventive', async (route) => {
      await showMaintenancePreventivePage(route);
    }, { requiresAuth: true, permissions: ['maintenance.view'], module: 'maintenance' })
    .addRoute('/maintenance/providers', async (route) => {
      await showMaintenanceProvidersPage(route);
    }, { requiresAuth: true, permissions: ['maintenance.manage_providers'], module: 'maintenance' })
    .addRoute('/maintenance/contracts', async (route) => {
      await showMaintenanceContractsPage(route);
    }, { requiresAuth: true, permissions: ['maintenance.manage_contracts'], module: 'maintenance' })
    .addRoute('/maintenance/refs', async (route) => {
      await showMaintenanceRefsPage(route);
    }, { requiresAuth: true, permissions: ['maintenance.manage_referentials'], module: 'maintenance' })
    .addRoute('/maintenance/calendar', async (route) => {
      await showMaintenanceCalendarPage(route);
    }, { requiresAuth: true, permissions: ['maintenance.view'], module: 'maintenance' })
    .addRoute('/ai', async (route) => {
      await showAIAssistantPage(route);
    }, { requiresAuth: true, permissions: ['ai.use'], module: 'ai_assistant' })
    .addRoute('/housing', async (route) => {
      await showHousingPage(route);
    }, { requiresAuth: true, permissions: ['housing.view'], module: ['housing', 'gestion_bureaux'] })
    .addRoute('/housing/import-excel', async (route) => {
      await showHousingImportPage(route);
    }, { requiresAuth: true, permissions: ['housing.manage_occupancies'], module: ['housing', 'gestion_bureaux'] })
    .addRoute('/sport', async (route) => {
      await showSportDashboardPage(route);
    }, { requiresAuth: true, permissions: ['sport.access'], module: 'sport' })
    .addRoute('/sport/activities', async (route) => {
      await showSportActivitiesPage(route);
    }, { requiresAuth: true, permissions: ['sport.activities.read'], module: 'sport' })
    .addRoute('/sport/goals', async (route) => {
      await showSportGoalsPage(route);
    }, { requiresAuth: true, permissions: ['sport.goals.read'], module: 'sport' })
    .addRoute('/sport/garmin', async (route) => {
      await showSportGarminPage(route);
    }, { requiresAuth: true, permissions: ['sport.activities.write'], module: 'sport' })
    .addRoute('/sport/health', async (route) => {
      await showSportHealthPage(route);
    }, { requiresAuth: true, permissions: ['sport.access'], module: 'sport' })
    .addRoute('/sport/analyses', async (route) => {
      await showSportAnalysesPage(route);
    }, { requiresAuth: true, permissions: ['sport.analysis.read'], module: 'sport' })
    .addRoute('/domotique', async (route) => {
      await showDomotiquePage(route);
    }, { requiresAuth: true, permissions: ['domotique.view'], module: 'domotique' })
    .addRoute('/domotique/config', async (route) => {
      await showDomotiqueConfigPage(route);
    }, { requiresAuth: true, permissions: ['domotique.configure'], module: 'domotique' })
    .addRoute('/domotique/surveillance', async (route) => {
      await showSurveillancePage(route);
    }, { requiresAuth: true, permissions: ['domotique.view'], module: 'domotique' })
    .addRoute('/agenda', async (route) => {
      await showAgendaPage(route);
    }, { requiresAuth: true, permissions: ['agenda.access'], module: 'agenda' })
    .addRoute('/agenda/inscriptions', async (route) => {
      await showAgendaPage(route);
    }, { requiresAuth: true, permissions: ['agenda.access'], module: 'agenda' })
    .addRoute('/agenda/settings', async (route) => {
      await showAgendaSettingsPage(route);
    }, { requiresAuth: true, permissions: ['agenda.settings', 'agenda.manage'], module: 'agenda' })
    .addRoute('/agenda/synthese', async (route) => {
      await showAgendaSynthesisPage(route);
    }, { requiresAuth: true, permissions: ['agenda.access'], module: 'agenda' })
    .addRoute('/agenda/import-excel', async (route) => {
      await showAgendaImportPage(route);
    }, { requiresAuth: true, permissions: ['agenda.manage'], module: 'agenda' })
    .addRoute('/volunteers', async (route) => {
      await showVolunteersPage(route);
    }, { requiresAuth: true, permissions: ['volunteers.view'], module: ['volunteers', 'gestion_bureaux'] })
    .addRoute('/photos', async (route) => {
      await showPhotosPage(route);
    }, { requiresAuth: true, permissions: ['photos.view'], module: 'photos' })
    .addRoute('/photos/albums', async (route) => {
      await showPhotosPage(route);
    }, { requiresAuth: true, permissions: ['photos.view'], module: 'photos' })
    .addRoute('/photos/people', async (route) => {
      await showPhotosPage(route);
    }, { requiresAuth: true, permissions: ['photos.view'], module: 'photos' })
    .addRoute('/photos/places', async (route) => {
      await showPhotosPage(route);
    }, { requiresAuth: true, permissions: ['photos.view'], module: 'photos' })
    .addRoute('/photos/favorites', async (route) => {
      await showPhotosPage(route);
    }, { requiresAuth: true, permissions: ['photos.view'], module: 'photos' })
    .addRoute('/photos/trash', async (route) => {
      await showPhotosPage(route);
    }, { requiresAuth: true, permissions: ['photos.delete'], module: 'photos' })
    .addRoute('/photos/souvenirs', async (route) => {
      await showSouvenirsPage(route);
    }, { requiresAuth: true, permissions: ['photos.view'], module: 'photos' })
    .addRoute('/it-assets', async (route) => {
      await showITAssetPage(route);
    }, { requiresAuth: true, permissions: ['it_asset.view'], module: 'it_asset' })
    .addRoute('/it-assets/discovery', async (route) => {
      await showITAssetPage(route);
    }, { requiresAuth: true, permissions: ['it_asset.view'], module: 'it_asset' })
    .addRoute('/it-assets/alerts', async (route) => {
      await showITAssetPage(route);
    }, { requiresAuth: true, permissions: ['it_asset.view'], module: 'it_asset' })
    .addRoute('/it-assets/network-ranges', async (route) => {
      await showITAssetPage(route);
    }, { requiresAuth: true, permissions: ['it_asset.view'], module: 'it_asset' })

  // Modules with explicit routes (registered above) - skip in module loop
  const explicitModuleRoutes = ['dashboard', 'administration', 'administratif',
    'buildings', 'equipment', 'sport', 'housing', 'maintenance', 'it_assets', 'photos'];

  moduleRoutes.forEach(module => {
    if (module === 'dashboard' || module === 'administration' || module === 'administratif'
      || module === 'buildings' || module === 'equipment' || module === 'sport'
      || module === 'housing' || module === 'maintenance') return;
    if (explicitModuleRoutes.includes(module)) return;

  router.addRoute(`/${module}`, async (route) => {
      await showModulePage(route);
    }, { requiresAuth: true, permissions: moduleRoutePermissions[module] || [], module });
  });

  router
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
    await ensureITAssetPage();
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

async function ensureITAssetPage() {
  if (!itAssetPage) {
    itAssetPage = createITAssetPage(router);
    await itAssetPage.initialize();
  }
  return itAssetPage;
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

async function ensureHousingImportPage() {
  if (!housingImportPage) {
    housingImportPage = createHousingImportPage(router);
    await housingImportPage.initialize();
  }
  return housingImportPage;
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

async function ensureAgendaSettingsPage() {
  if (!agendaSettingsPage) {
    agendaSettingsPage = createAgendaSettingsPage(router);
  }
  await agendaSettingsPage.initialize();
  return agendaSettingsPage;
}

async function showAgendaSettingsPage(route) {
  if (!appShell) return;
  appShell.showLoading();
  try {
    const page = await ensureAgendaSettingsPage();
    appShell.showContent(page.render());
  } catch (error) {
    console.error('Erreur affichage paramètres agenda:', error);
    appShell.showError(error);
  }
}

let agendaSynthesisPage = null;

async function ensureAgendaSynthesisPage() {
  if (!agendaSynthesisPage) {
    const { AgendaSynthesisPage } = await import('./pages/AgendaSynthesisPage.js');
    agendaSynthesisPage = new AgendaSynthesisPage(router);
  }
  await agendaSynthesisPage.initialize();
  return agendaSynthesisPage;
}

async function showAgendaSynthesisPage(route) {
  if (!appShell) return;
  appShell.showLoading();
  try {
    const page = await ensureAgendaSynthesisPage();
    appShell.showContent(page.render());
  } catch (error) {
    console.error('Erreur affichage synthèse agenda:', error);
    appShell.showError(error);
  }
}

let agendaImportPage = null;

async function ensureAgendaImportPage() {
  if (!agendaImportPage) {
    agendaImportPage = createAgendaImportPage(router);
  }
  await agendaImportPage.initialize();
  return agendaImportPage;
}

async function showAgendaImportPage(route) {
  if (!appShell) return;
  appShell.showLoading();
  try {
    const page = await ensureAgendaImportPage();
    appShell.showContent(await page.render());
  } catch (error) {
    console.error('Erreur affichage import agenda:', error);
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

async function showSurveillancePage(route) {
  if (!appShell) return;
  appShell.showLoading();
  try {
    if (!surveillancePage) surveillancePage = createSurveillancePage(router);
    await surveillancePage.initialize();
    appShell.showContent(surveillancePage.render());
  } catch (error) {
    console.error('Erreur affichage Surveillance:', error);
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

async function showHousingImportPage(route) {
  if (!appShell) return;
  appShell.showLoading();

  try {
    const page = await ensureHousingImportPage();
    const content = page.render();
    appShell.showContent(content);
  } catch (error) {
    console.error('Erreur affichage import hébergement:', error);
    appShell.showError(error);
  }
}

async function ensurePhotosPage() {
  if (!photosPage) {
    photosPage = createPhotosPage(router);
    await photosPage.initialize();
  }
  return photosPage;
}

const PHOTO_VIEWS = {
  '/photos': 'all',
  '/photos/albums': 'albums',
  '/photos/people': 'people',
  '/photos/places': 'places',
  '/photos/favorites': 'favorites',
  '/photos/trash': 'trash',
};

async function showPhotosPage(route) {
  if (!appShell) return;
  appShell.showLoading();
  try {
    const page = await ensurePhotosPage();
    page.setView(PHOTO_VIEWS[route.path] || 'all');
    const content = page.render();
    appShell.showContent(content);
    page.loadData();
  } catch (error) {
    console.error('Erreur affichage photos:', error);
    appShell.showError(error);
  }
}

async function ensureSouvenirsPage() {
  if (!souvenirsPage) {
    souvenirsPage = createSouvenirsPage(router);
    await souvenirsPage.initialize();
  }
  return souvenirsPage;
}

async function showSouvenirsPage(route) {
  if (!appShell) return;
  appShell.showLoading();
  try {
    const page = await ensureSouvenirsPage();
    const content = page.render();
    appShell.showContent(content);
    page.load({ autoplay: false });
  } catch (error) {
    console.error('Erreur affichage souvenirs:', error);
    appShell.showError(error);
  }
}

const IT_SECTION_BY_PATH = {
  '/it-assets': 'list',
  '/it-assets/discovery': 'discovery',
  '/it-assets/alerts': 'alerts',
  '/it-assets/network-ranges': 'network-ranges',
};

async function showITAssetPage(route) {
  if (!appShell) return;
  appShell.showLoading();
  try {
    const page = await ensureITAssetPage();
    page.setSection(IT_SECTION_BY_PATH[route.path] || 'list');
    const content = page.render();
    appShell.showContent(content);
    page.loadData();
  } catch (error) {
    console.error('Erreur affichage parc informatique:', error);
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
