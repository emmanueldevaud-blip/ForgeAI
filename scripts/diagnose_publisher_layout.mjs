/**
 * Diagnostic visuel du parcours Publisher : sélection, ajustement et aperçu.
 * Usage : node scripts/diagnose_publisher_layout.mjs https://forgeai.example [storage-state.json]
 * Les captures sont écrites dans /tmp/forgeai-publisher-diagnostics.
 */
import fs from 'node:fs';
import path from 'node:path';
import { chromium } from 'playwright';

const [baseUrl, storageStatePath] = process.argv.slice(2);
if (!baseUrl) {
  console.error('Usage: node scripts/diagnose_publisher_layout.mjs <url-forgeai> [storage-state.json]');
  process.exit(2);
}

const formats = {
  post: 4 / 5,
  carousel: 4 / 5,
  reel: 9 / 16,
  story: 9 / 16,
};
const viewports = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'mobile', width: 390, height: 844 },
];
const outputDir = '/tmp/forgeai-publisher-diagnostics';
fs.mkdirSync(outputDir, { recursive: true });

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  ...(storageStatePath ? { storageState: path.resolve(storageStatePath) } : {}),
});
await context.addInitScript(() => localStorage.removeItem('forgeai_publisher_draft'));
let failures = 0;

try {
  for (const viewport of viewports) {
    for (const [format, expectedRatio] of Object.entries(formats)) {
      const page = await context.newPage();
      await page.setViewportSize(viewport);
      await page.goto(new URL(`/publisher/${format}`, baseUrl).href, { waitUntil: 'domcontentloaded' });

      const picker = page.locator('.publisher-media-picker');
      await picker.waitFor({ state: 'visible', timeout: 20000 });
      const firstPhoto = page.locator('.pmp-grid [data-photo-id]').first();
      await firstPhoto.waitFor({ state: 'visible', timeout: 20000 });
      await firstPhoto.click();
      if (format === 'carousel') await page.locator('.pmp-grid [data-photo-id]').nth(1).click();
      const previewStage = page.locator('.pmp-preview-stage');
      await previewStage.waitFor({ state: 'visible', timeout: 5000 });

      const pickerMetrics = await page.evaluate(() => {
        const rect = element => {
          const box = element.getBoundingClientRect();
          return { x: box.x, y: box.y, width: box.width, height: box.height, right: box.right, bottom: box.bottom };
        };
        const picker = document.querySelector('.publisher-media-picker');
        const stage = document.querySelector('.pmp-preview-stage');
        const sidebar = document.querySelector('#sidebar');
        const pickerRect = rect(picker);
        const sidebarRect = sidebar && getComputedStyle(sidebar).display !== 'none' ? rect(sidebar) : null;
        const stageRect = rect(stage);
        const publisherPage = document.querySelector('.publisher-page');
        const publisherMain = document.querySelector('.publisher-main');
        const appMain = document.querySelector('.main-content');
        return {
          picker: pickerRect,
          sidebar: sidebarRect,
          pickerOverlapsSidebar: !!sidebarRect && pickerRect.x < sidebarRect.right && pickerRect.right > sidebarRect.x,
          stage: stageRect,
          stageRatio: stageRect.width / stageRect.height,
          stageCssRatio: getComputedStyle(stage).aspectRatio,
          publisherScrolls: !!publisherPage && publisherPage.scrollHeight > publisherPage.clientHeight + 1,
          stepScrolls: !!publisherMain && publisherMain.scrollHeight > publisherMain.clientHeight + 1,
          appMainScrolls: !!appMain && appMain.scrollHeight > appMain.clientHeight + 1,
          viewportScrolls: document.documentElement.scrollHeight > document.documentElement.clientHeight + 1,
        };
      });
      await page.screenshot({ path: path.join(outputDir, `${viewport.name}-${format}-select.png`), fullPage: true });

      const complete = page.locator('.publisher-media-picker [data-action="complete"]');
      await complete.click();
      const adjustEditor = page.locator('.publisher-post-editor');
      await adjustEditor.waitFor({ state: 'visible', timeout: 10000 });
      const adjustMetrics = await page.evaluate(() => {
        const card = document.querySelector('.ppe-media-item');
        if (!card) return null;
        const rect = card.getBoundingClientRect();
        return {
          width: rect.width,
          height: rect.height,
          ratio: rect.width / rect.height,
          cssRatio: getComputedStyle(card).aspectRatio,
          editorClass: document.querySelector('.publisher-post-editor').className,
          publisherScrolls: document.querySelector('.publisher-page').scrollHeight > document.querySelector('.publisher-page').clientHeight + 1,
          stepScrolls: document.querySelector('.publisher-main').scrollHeight > document.querySelector('.publisher-main').clientHeight + 1,
          appMainScrolls: document.querySelector('.main-content').scrollHeight > document.querySelector('.main-content').clientHeight + 1,
          viewportScrolls: document.documentElement.scrollHeight > document.documentElement.clientHeight + 1,
        };
      });
      await page.screenshot({ path: path.join(outputDir, `${viewport.name}-${format}-adjust.png`), fullPage: true });

      await page.locator('[data-action="next-step"]').click();
      if (format === 'story') {
        await page.locator('.story-editor-root [data-action="save"]').waitFor({ state: 'visible', timeout: 10000 });
        await page.locator('.story-editor-root [data-action="save"]').click();
      } else if (format === 'reel') {
        await page.locator('.publisher-reel-editor').waitFor({ state: 'visible', timeout: 10000 });
        await page.locator('[data-action="next-step"]').click();
      }
      await page.locator('.publisher-caption-editor').waitFor({ state: 'visible', timeout: 10000 });
      await page.locator('[data-action="next-step"]').click();
      await page.locator('.publisher-preview').waitFor({ state: 'visible', timeout: 10000 });
      const previewMetrics = await page.evaluate((currentFormat) => {
        const rect = element => {
          const box = element.getBoundingClientRect();
          return { width: box.width, height: box.height, ratio: box.width / box.height };
        };
        const preview = document.querySelector('.publisher-preview');
        const stage = document.querySelector(currentFormat === 'story' ? '.pp-story'
          : currentFormat === 'reel' ? '.pp-reel-player'
            : '.pp-single-media, .pp-carousel');
        const image = stage?.querySelector('img') || stage;
        const publisherPage = document.querySelector('.publisher-page');
        const publisherMain = document.querySelector('.publisher-main');
        const appMain = document.querySelector('.main-content');
        return {
          preview: rect(preview),
          stage: stage ? rect(stage) : null,
          imageLoaded: currentFormat === 'story'
            ? image instanceof HTMLImageElement && image.complete && image.naturalWidth > 0
            : true,
          publisherScrolls: publisherPage.scrollHeight > publisherPage.clientHeight + 1,
          stepScrolls: publisherMain.scrollHeight > publisherMain.clientHeight + 1,
          appMainScrolls: appMain.scrollHeight > appMain.clientHeight + 1,
          viewportScrolls: document.documentElement.scrollHeight > document.documentElement.clientHeight + 1,
        };
      }, format);
      await page.screenshot({ path: path.join(outputDir, `${viewport.name}-${format}-preview.png`), fullPage: true });

      const stageOk = Math.abs(pickerMetrics.stageRatio - expectedRatio) < 0.035;
      const adjustOk = adjustMetrics && Math.abs(adjustMetrics.ratio - expectedRatio) < 0.035;
      const sidebarOk = !pickerMetrics.pickerOverlapsSidebar;
      const previewOk = previewMetrics.stage && Math.abs(previewMetrics.stage.ratio - expectedRatio) < 0.04
        && previewMetrics.imageLoaded;
      const noPageScroll = [pickerMetrics, adjustMetrics, previewMetrics].every(metrics => metrics
        && !metrics.publisherScrolls && !metrics.stepScrolls && !metrics.appMainScrolls && !metrics.viewportScrolls);
      const passed = stageOk && adjustOk && sidebarOk && previewOk && noPageScroll;
      if (!passed) failures++;
      console.log(JSON.stringify({ viewport: viewport.name, format, passed, picker: pickerMetrics, adjust: adjustMetrics, preview: previewMetrics }));
      await page.close();
    }
  }
} finally {
  await context.close();
  await browser.close();
}

console.log(`Captures: ${outputDir}`);
process.exitCode = failures ? 1 : 0;
