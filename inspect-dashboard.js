const { chromium } = require('playwright');

async function inspectDashboard() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 }
  });
  const page = await context.newPage();
  
  // Enable console logging
  page.on('console', msg => console.log('BROWSER:', msg.text()));
  page.on('pageerror', err => console.log('ERROR:', err.message));
  
  try {
    // Navigate to login
    await page.goto('http://localhost:8000/login');
    await page.waitForLoadState('networkidle');
    
    // Login - check if there's a login form
    const usernameInput = await page.$('input[name="username"], input[type="email"], input#username');
    const passwordInput = await page.$('input[name="password"], input[type="password"], input#password');
    const submitBtn = await page.$('button[type="submit"], .btn-primary');
    
    if (usernameInput && passwordInput) {
      await usernameInput.fill('admin');
      await passwordInput.fill('admin123');
      if (submitBtn) await submitBtn.click();
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(1000);
    }
    
    // Navigate to dashboard
    await page.goto('http://localhost:8000/dashboard');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    
    // Take screenshot for reference
    await page.screenshot({ path: 'dashboard-1920.png', fullPage: true });
    
    // Function to get computed styles
    const getComputedStyles = async (selector, label) => {
      const element = await page.$(selector);
      if (!element) {
        console.log(`${label}: NOT FOUND (${selector})`);
        return null;
      }
      
      const styles = await element.evaluate(el => {
        const computed = window.getComputedStyle(el);
        const props = [
          'position', 'display', 'width', 'height', 'min-width', 'max-width',
          'margin', 'padding', 'left', 'top', 'transform', 
          'grid-template-columns', 'grid-area', 'flex', 'overflow', 'z-index',
          'box-sizing', 'min-height', 'max-height'
        ];
        const result = {};
        for (const prop of props) {
          result[prop] = computed.getPropertyValue(prop);
        }
        // Also get bounding rect
        const rect = el.getBoundingClientRect();
        result.rect = {
          width: rect.width,
          height: rect.height,
          top: rect.top,
          left: rect.left,
          right: rect.right,
          bottom: rect.bottom
        };
        return result;
      });
      
      console.log(`\n=== ${label} (${selector}) ===`);
      for (const [key, value] of Object.entries(styles)) {
        if (key !== 'rect') console.log(`  ${key}: ${value}`);
      }
      if (styles.rect) {
        console.log(`  RECT: ${JSON.stringify(styles.rect, null, 2)}`);
      }
      return styles;
    };
    
    // Inspect all key elements
    await getComputedStyles('#app', 'Root app element');
    await getComputedStyles('.app-shell', 'AppShell');
    await getComputedStyles('.sidebar', 'Sidebar');
    await getComputedStyles('.header', 'Header');
    await getComputedStyles('.app-main', 'App Main (parent of header/main)');
    await getComputedStyles('.main-content', 'Main Content');
    await getComputedStyles('.module-placeholder', 'Dashboard placeholder');
    await getComputedStyles('.module-placeholder-card', 'Dashboard card');
    await getComputedStyles('.module-placeholder-header', 'Dashboard header');
    await getComputedStyles('.module-placeholder-body', 'Dashboard body');
    await getComputedStyles('.module-placeholder-features', 'Dashboard features grid');
    
    // Check for any elements overlapping
    console.log('\n=== CHECKING FOR OVERLAPPING ELEMENTS ===');
    const overlapping = await page.evaluate(() => {
      const mainContent = document.querySelector('.main-content');
      if (!mainContent) return [];
      const rect = mainContent.getBoundingClientRect();
      const elements = document.querySelectorAll('*');
      const overlapping = [];
      for (const el of elements) {
        if (el === mainContent || el.contains(mainContent)) continue;
        const elRect = el.getBoundingClientRect();
        if (elRect.width > 0 && elRect.height > 0 &&
            elRect.left < rect.right && elRect.right > rect.left &&
            elRect.top < rect.bottom && elRect.bottom > rect.top) {
          const style = window.getComputedStyle(el);
          if (style.zIndex !== 'auto' && parseInt(style.zIndex) > 0) {
            overlapping.push({
              tag: el.tagName,
              class: el.className,
              id: el.id,
              zIndex: style.zIndex,
              position: style.position,
              rect: { ...elRect }
            });
          }
        }
      }
      return overlapping;
    });
    console.log('Overlapping elements with z-index:', JSON.stringify(overlapping, null, 2));
    
    // Check CSS rules applied to key elements
    console.log('\n=== CSS RULES FOR .app-shell ===');
    const appShellRules = await page.evaluate(() => {
      const el = document.querySelector('.app-shell');
      if (!el) return [];
      const sheets = document.styleSheets;
      const rules = [];
      for (const sheet of sheets) {
        try {
          for (const rule of sheet.cssRules || []) {
            if (rule.selectorText && rule.selectorText.includes('app-shell')) {
              rules.push({
                selector: rule.selectorText,
                cssText: rule.cssText,
                href: sheet.href
              });
            }
          }
        } catch (e) {
          // Cross-origin stylesheet
        }
      }
      return rules;
    });
    console.log(JSON.stringify(appShellRules, null, 2));
    
    console.log('\n=== CSS RULES FOR .main-content ===');
    const mainContentRules = await page.evaluate(() => {
      const el = document.querySelector('.main-content');
      if (!el) return [];
      const sheets = document.styleSheets;
      const rules = [];
      for (const sheet of sheets) {
        try {
          for (const rule of sheet.cssRules || []) {
            if (rule.selectorText && rule.selectorText.includes('main-content')) {
              rules.push({
                selector: rule.selectorText,
                cssText: rule.cssText,
                href: sheet.href
              });
            }
          }
        } catch (e) {}
      }
      return rules;
    });
    console.log(JSON.stringify(mainContentRules, null, 2));
    
    // Check the parent chain
    console.log('\n=== PARENT CHAIN OF .main-content ===');
    const parentChain = await page.evaluate(() => {
      const el = document.querySelector('.main-content');
      if (!el) return [];
      const chain = [];
      let current = el.parentElement;
      while (current) {
        const style = window.getComputedStyle(current);
        chain.push({
          tag: current.tagName,
          class: current.className,
          id: current.id,
          position: style.position,
          display: style.display,
          width: style.width,
          height: style.height,
          minHeight: style.minHeight,
          overflow: style.overflow,
          gridArea: style.gridArea,
          gridTemplateColumns: style.gridTemplateColumns
        });
        current = current.parentElement;
      }
      return chain;
    });
    console.log(JSON.stringify(parentChain, null, 2));
    
  } catch (err) {
    console.error('Error:', err);
  } finally {
    await browser.close();
  }
}

inspectDashboard().catch(console.error);