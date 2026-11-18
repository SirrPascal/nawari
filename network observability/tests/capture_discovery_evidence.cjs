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
    args: ['--no-sandbox', '--disable-gpu', '--ignore-certificate-errors', '--window-size=1440,920'],
  });

  const context = await browser.newContext({
    viewport: { width: 1440, height: 920 },
    ignoreHTTPSErrors: true,
  });

  const page = await context.newPage();

  await page.addInitScript((token) => {
    localStorage.setItem('nawari_auth_token', token);
    localStorage.setItem('auth_token', token);
    localStorage.setItem('nawari_token', token);
    localStorage.setItem('token', token);
  }, TOKEN);

  console.log(`[Playwright] Navigating directly to Discovery view...`);
  await page.goto(`${BASE_URL}/?section=devices&sub=discovery`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(3000);

  const shot1 = path.join(SCREENSHOTS_DIR, '87_cisco_network_discovery_swis_auth_updated.png');
  await page.screenshot({ path: shot1, fullPage: true });
  console.log(`[Playwright] Captured: ${shot1}`);

  // Click Evidence button on first candidate
  console.log('[Playwright] Opening Evidence Drilldown Modal...');
  const evidenceBtn = page.locator('button:has-text("Evidence")').first();
  await evidenceBtn.waitFor({ state: 'visible', timeout: 8000 });
  await evidenceBtn.click();
  await page.waitForTimeout(1500);
  const shot2 = path.join(SCREENSHOTS_DIR, '88_cisco_candidate_evidence_modal_updated.png');
  await page.screenshot({ path: shot2, fullPage: true });
  console.log(`[Playwright] Captured: ${shot2}`);

  await browser.close();
  console.log('[Playwright] Discovery verification complete!');
})();
