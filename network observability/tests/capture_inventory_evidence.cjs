const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const CHROME_PATH = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const SCREENSHOTS_DIR = '/Users/madeira/.gemini/antigravity/brain/de11aa28-fc65-4fe4-b924-89a6cec0669c/browser_verification';
const BASE_URL = 'https://10.2.1.58:18443';
const TOKEN = '6000qUmkV9sm1QNgbPcrn2GTnVim1Qkv9XlLAgo6GvLjwHLSOm8HvQ';

(async () => {
  if (!fs.existsSync(SCREENSHOTS_DIR)) {
    fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });
  }

  console.log('[Playwright] Launching Chrome...');
  const browser = await chromium.launch({
    executablePath: CHROME_PATH,
    headless: true,
    args: ['--no-sandbox', '--disable-gpu', '--ignore-certificate-errors', '--window-size=1440,1100'],
  });

  const context = await browser.newContext({
    viewport: { width: 1440, height: 1100 },
    ignoreHTTPSErrors: true,
  });

  const page = await context.newPage();

  await page.addInitScript((token) => {
    localStorage.setItem('nawari_auth_token', token);
    localStorage.setItem('auth_token', token);
    localStorage.setItem('nawari_token', token);
    localStorage.setItem('token', token);
    localStorage.setItem('nawari_tenant', 'pilot');
  }, TOKEN);

  console.log('[Playwright] Navigating to Monitored Devices Inventory view...');
  await page.goto(`${BASE_URL}/?tenant=pilot&section=devices&sub=inventory`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(3000);

  // Wait for table to load
  await page.waitForSelector('table.data-table tbody tr', { timeout: 10000 });
  const rows = await page.locator('table.data-table tbody tr').count();
  console.log(`[Playwright] Loaded ${rows} device rows in inventory view.`);

  const shot1 = path.join(SCREENSHOTS_DIR, '89_cisco_monitored_devices_34_hosts.png');
  await page.screenshot({ path: shot1, fullPage: true });
  console.log(`[Playwright] Captured: ${shot1}`);

  // Navigate to or click Inspect on the first device to show Device Detail
  console.log('[Playwright] Navigating to Device Detail view for cisco-core-10-20-1-220...');
  await page.goto(`${BASE_URL}/?tenant=pilot&section=devices&sub=inventory&id=cisco-core-10-20-1-220`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(3000);

  // Ensure Monitoring Coverage Breakdown is visible
  await page.waitForSelector('.detail-cards-grid', { timeout: 10000 });

  const shot2 = path.join(SCREENSHOTS_DIR, '90_cisco_device_detail_coverage.png');
  await page.screenshot({ path: shot2, fullPage: true });
  console.log(`[Playwright] Captured: ${shot2}`);

  await browser.close();
  console.log('[Playwright] Monitored Devices & Coverage verification complete!');
})();
