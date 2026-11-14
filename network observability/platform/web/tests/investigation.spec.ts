import { expect, test } from '@playwright/test';

test('investigates a controlled laptop service degradation', async ({ page }) => {
  await page.goto('/?service=fixture-portal&operation=page');
  await expect(page.getByText('Controlled local fixtures')).toBeVisible();
  await expect(page.getByRole('heading', {name: 'Service response timeline'})).toBeVisible();
  await expect(page.getByText('1007.0 ms').first()).toBeVisible();
  await expect(page.getByText('Regional comparison', {exact: true})).toBeVisible();
  await expect(page.getByRole('heading', {name: 'Network context at observation time'})).toBeVisible();
  await expect(page.getByText(/^(fixture|system)_network$/)).toBeVisible();
  await expect(page.getByText('inferred', {exact: true}).first()).toBeVisible();
  await page.getByRole('button', {name: /Inspect sample/}).first().click();
  await expect(page).toHaveURL(/sample=/);
  await expect(page.getByText('Selected observation')).toBeVisible();
});

test('discovers and drills into managed Netdata metrics', async ({ page }) => {
  await page.goto('/?device=fixture-endpoint&view=system');
  await expect(page.getByRole('heading', {name: 'Managed agent catalogue'})).toBeVisible();
  await expect(page.locator('.catalogue-stats strong').nth(2)).not.toHaveText('0');
  await expect(page.getByText('System metrics')).toBeVisible();
  await page.locator('.metric-link').first().click();
  await expect(page.getByText('Selected statistic')).toBeVisible();
  await expect(page.locator('.metric-detail .caption')).toContainText('returned samples');
  await page.getByRole('tab', {name:'Applications'}).click();
  await expect(page.getByRole('heading', {name:'Observed application connections'})).toBeVisible();
  await expect(page.getByText(/denied 412/)).toBeVisible();
});

test('keeps collaboration operations and media coverage distinct', async ({page}) => {
  await page.goto('/?device=fixture-endpoint&service=fixture-collaboration&operation=front-door&view=services');
  await expect(page.locator('select')).toHaveValue('fixture-collaboration|front-door');
  await expect(page.getByText('1007.0 ms').first()).toBeVisible();
  await expect(page.getByText('What this proves')).toBeVisible();
  await expect(page.getByRole('heading', {name:'Evidence-supported hypotheses'})).toBeVisible();
  await expect(page.getByText('service specific degradation suspected')).toBeVisible();
  await page.locator('select').selectOption('fixture-collaboration|media-coverage');
  await expect(page.getByText('unsupported', {exact:true}).first()).toBeVisible();
  await expect(page.getByText(/media quality/).first()).toBeVisible();
});

test('keeps silent assigned endpoints visible', async ({ page }) => {
  await page.goto('/');
  const silent = page.getByRole('button', {name: /fixture-silent/});
  await expect(silent).toContainText('unknown');
  await silent.click();
  await expect(page).toHaveURL(/device=fixture-silent/);
  await expect(page.getByText('No service observations in this window')).toBeVisible();
  await expect(page.getByText('unknown collection')).toBeVisible();
});

test('preserves the selected scope in the URL', async ({ page }) => {
  await page.goto('/?device=fixture-endpoint&service=fixture-portal');
  await page.reload();
  await expect(page.getByRole('heading', {name: 'fixture-endpoint'})).toBeVisible();
  await expect(page.locator('select')).toHaveValue('fixture-portal|page');
});
