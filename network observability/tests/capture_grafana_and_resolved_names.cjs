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

  // 1. Monitored Devices view with resolved names
  console.log('[Playwright] Navigating to Monitored Devices with resolved names...');
  await page.goto(`${BASE_URL}/?tenant=pilot&section=devices&sub=inventory`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(3000);
  const shot1 = path.join(SCREENSHOTS_DIR, '91_cisco_monitored_devices_resolved_names.png');
  await page.screenshot({ path: shot1, fullPage: true });
  console.log(`[Playwright] Captured: ${shot1}`);

  // 2. Nawari Dashboards Page with Grafana links
  console.log('[Playwright] Navigating to Nawari Dashboards page...');
  await page.goto(`${BASE_URL}/?tenant=pilot&section=observability&sub=dashboards`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(3000);
  const shot2 = path.join(SCREENSHOTS_DIR, '92_nawari_dashboards_hub_page.png');
  await page.screenshot({ path: shot2, fullPage: true });
  console.log(`[Playwright] Captured: ${shot2}`);

  // 3. Grafana Network Device Overview Dashboard
  console.log('[Playwright] Navigating to Grafana Network Device Overview...');
  await page.goto(`${BASE_URL}/grafana/d/nawari-net-overview/network-device-overview?orgId=1`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(4000);
  const shot3 = path.join(SCREENSHOTS_DIR, '93_grafana_network_device_overview.png');
  await page.screenshot({ path: shot3, fullPage: true });
  console.log(`[Playwright] Captured: ${shot3}`);

  // 4. Grafana SolarWinds Cisco Logs Dashboard
  console.log('[Playwright] Navigating to Grafana SolarWinds Cisco Logs & Events...');
  await page.goto(`${BASE_URL}/grafana/d/nawari-sw-cisco-logs/solarwinds-cisco-logs-events?orgId=1`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(4000);
  const shot4 = path.join(SCREENSHOTS_DIR, '94_grafana_solarwinds_cisco_logs.png');
  await page.screenshot({ path: shot4, fullPage: true });
  console.log(`[Playwright] Captured: ${shot4}`);

  // 5. Grafana Device Availability Dashboard
  console.log('[Playwright] Navigating to Grafana Device Availability & Loss...');
  await page.goto(`${BASE_URL}/grafana/d/nawari-net-avail/network-device-availability?orgId=1`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(4000);
  const shot5 = path.join(SCREENSHOTS_DIR, '95_grafana_device_availability.png');
  await page.screenshot({ path: shot5, fullPage: true });
  console.log(`[Playwright] Captured: ${shot5}`);

  await browser.close();
  console.log('[Playwright] Verification captures complete!');
})();
