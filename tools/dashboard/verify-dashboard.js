// Browser Console Verification Script for Dashboard Layout
// Run this in the browser dev console after navigating to /dashboard

function inspectElement(selector, label) {
  const el = document.querySelector(selector);
  if (!el) {
    console.log(`❌ ${label}: NOT FOUND (${selector})`);
    return null;
  }
  
  const computed = window.getComputedStyle(el);
  const rect = el.getBoundingClientRect();
  
  const props = [
    'position', 'display', 'width', 'height', 'min-width', 'max-width',
    'margin', 'padding', 'left', 'top', 'transform', 
    'grid-template-columns', 'grid-area', 'flex', 'overflow', 'z-index',
    'box-sizing', 'min-height', 'max-height', 'grid-column', 'grid-row'
  ];
  
  console.log(`\n=== ${label} (${selector}) ===`);
  console.log(`  RECT: width=${rect.width.toFixed(1)} height=${rect.height.toFixed(1)} top=${rect.top.toFixed(1)} left=${rect.left.toFixed(1)}`);
  
  for (const prop of props) {
    const val = computed.getPropertyValue(prop);
    if (val && val !== 'auto' && val !== 'none' && val !== 'normal' && val !== '0px' && val !== 'visible') {
      console.log(`  ${prop}: ${val}`);
    }
  }
  
  // Show all grid-related properties
  const gridProps = ['gridColumn', 'gridRow', 'gridArea', 'gridTemplateColumns', 'gridTemplateRows', 'gridTemplateAreas'];
  for (const prop of gridProps) {
    const val = computed.getPropertyValue(prop.replace(/([A-Z])/g, '-$1').toLowerCase());
    if (val && val !== 'auto' && val !== 'none' && val !== 'normal') {
      console.log(`  ${prop}: ${val}`);
    }
  }
  
  return { element: el, computed, rect };
}

function verifyLayout() {
  console.clear();
  console.log('🔍 DASHBOARD LAYOUT VERIFICATION');
  console.log('==================================');
  console.log(`Viewport: ${window.innerWidth}x${window.innerHeight}`);
  
  // Check root structure
  inspectElement('#app', 'Root #app');
  inspectElement('.app-shell', 'AppShell (grid container)');
  inspectElement('.sidebar', 'Sidebar');
  inspectElement('.header', 'Header');
  inspectElement('.main-content', 'Main Content');
  inspectElement('.module-placeholder', 'Dashboard Placeholder');
  inspectElement('.module-placeholder-card', 'Dashboard Card');
  inspectElement('.module-placeholder-features', 'Features Grid');
  
  // Check parent chain of main-content
  console.log('\n=== PARENT CHAIN OF .main-content ===');
  let el = document.querySelector('.main-content');
  let depth = 0;
  while (el && el.parentElement) {
    el = el.parentElement;
    const computed = window.getComputedStyle(el);
    console.log(`  ${depth++}: ${el.tagName.toLowerCase()}${el.id ? '#'+el.id : ''}${el.className ? '.'+el.className.split(' ').join('.') : ''}`);
    console.log(`      display: ${computed.display}, position: ${computed.position}, gridArea: ${computed.gridArea}`);
    if (el.classList.contains('app-shell')) break;
  }
  
  // Check for overlapping elements
  console.log('\n=== OVERLAPPING ELEMENTS CHECK ===');
  const mainContent = document.querySelector('.main-content');
  if (mainContent) {
    const mainRect = mainContent.getBoundingClientRect();
    const allElements = document.querySelectorAll('*');
    let found = false;
    for (const el of allElements) {
      if (el === mainContent || el.contains(mainContent)) continue;
      const rect = el.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0 &&
          rect.left < mainRect.right && rect.right > mainRect.left &&
          rect.top < mainRect.bottom && rect.bottom > mainRect.top) {
        const style = window.getComputedStyle(el);
        if (style.zIndex !== 'auto' && parseInt(style.zIndex) > 0) {
          console.log(`  ⚠️ Overlap: ${el.tagName.toLowerCase()}${el.id ? '#'+el.id : ''}${el.className ? '.'+el.className.split(' ').join('.') : ''} z-index: ${style.zIndex} pos: ${style.position}`);
          found = true;
        }
      }
    }
    if (!found) console.log('  ✅ No overlapping elements with z-index > 0');
  }
  
  // Verify grid areas match
  console.log('\n=== GRID AREA VERIFICATION ===');
  const appShell = document.querySelector('.app-shell');
  if (appShell) {
    const computed = window.getComputedStyle(appShell);
    console.log(`  grid-template-areas: ${computed.gridTemplateAreas}`);
    console.log(`  grid-template-columns: ${computed.gridTemplateColumns}`);
    console.log(`  grid-template-rows: ${computed.gridTemplateRows}`);
  }
  
  const sidebar = document.querySelector('.sidebar');
  const header = document.querySelector('.header');
  const main = document.querySelector('.main-content');
  
  if (sidebar && header && main) {
    console.log(`  .sidebar grid-area: ${window.getComputedStyle(sidebar).gridArea}`);
    console.log(`  .header grid-area: ${window.getComputedStyle(header).gridArea}`);
    console.log(`  .main-content grid-area: ${window.getComputedStyle(main).gridArea}`);
    
    const sidebarRect = sidebar.getBoundingClientRect();
    const headerRect = header.getBoundingClientRect();
    const mainRect = main.getBoundingClientRect();
    
    console.log('\n=== POSITION VERIFICATION ===');
    console.log(`  Sidebar: left=${sidebarRect.left.toFixed(1)} width=${sidebarRect.width.toFixed(1)}`);
    console.log(`  Header: left=${headerRect.left.toFixed(1)} width=${headerRect.width.toFixed(1)} top=${headerRect.top.toFixed(1)}`);
    console.log(`  Main: left=${mainRect.left.toFixed(1)} width=${mainRect.width.toFixed(1)} top=${mainRect.top.toFixed(1)}`);
    
    // Check if header is to the right of sidebar
    if (Math.abs(headerRect.left - sidebarRect.right) < 2) {
      console.log('  ✅ Header correctly positioned to the right of sidebar');
    } else {
      console.log(`  ❌ Header NOT aligned with sidebar (gap: ${(headerRect.left - sidebarRect.right).toFixed(1)}px)`);
    }
    
    // Check if main is below header and to the right of sidebar
    if (Math.abs(mainRect.top - headerRect.bottom) < 2) {
      console.log('  ✅ Main correctly positioned below header');
    } else {
      console.log(`  ❌ Main NOT below header (gap: ${(mainRect.top - headerRect.bottom).toFixed(1)}px)`);
    }
    
    if (Math.abs(mainRect.left - sidebarRect.right) < 2) {
      console.log('  ✅ Main correctly aligned with sidebar right edge');
    } else {
      console.log(`  ❌ Main NOT aligned with sidebar (gap: ${(mainRect.left - sidebarRect.right).toFixed(1)}px)`);
    }
  }
  
  console.log('\n✅ Verification complete. Check for ❌ issues above.');
}

// Run verification
verifyLayout();

// Also expose for manual re-run at different viewport sizes
window.verifyDashboardLayout = verifyLayout;

console.log('\n💡 Run verifyDashboardLayout() again after resizing viewport');
console.log('💡 Test at: 1920px, 1440px, 1024px, 768px');