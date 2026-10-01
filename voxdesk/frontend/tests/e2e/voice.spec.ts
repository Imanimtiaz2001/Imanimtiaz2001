import { test, expect } from '@playwright/test';

test('text, knowledge upload, history and export form a complete browser workflow', async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  await expect(page.getByRole('heading', { name: /Good ideas start/ })).toBeVisible();
  await expect(page.getByText('Test fixtures', { exact: true })).toBeVisible();
  await page.screenshot({
    path: `../.runtime/${testInfo.project.name}-welcome.png`,
    fullPage: true,
  });
  await page.getByLabel('Your question').fill('Why choose PostgreSQL?');
  await page.getByLabel('Send question').click();
  await expect(
    page.getByText(
      'PostgreSQL provides transactions, relational constraints and vector search in one database.',
      { exact: true },
    ),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Listen', exact: true }).click();
  await page.getByRole('button', { name: 'Knowledge & settings' }).click();
  await page
    .getByLabel('Note file')
    .setInputFiles({
      name: 'database.md',
      mimeType: 'text/markdown',
      buffer: Buffer.from(
        'PostgreSQL provides ACID transactions and pgvector for semantic search.',
      ),
    });
  await expect(page.getByRole('button', { name: /My notes/ })).toHaveClass(/active/);
  await page.getByRole('button', { name: 'Close settings' }).click();
  await page.getByLabel('Your question').fill('What does PostgreSQL provide?');
  await page.getByLabel('Send question').click();
  await expect(page.getByText('Grounded in your notes', { exact: true })).toBeVisible();
  await page.locator('.sources summary').filter({ hasText: 'database.md' }).click();
  await expect(page.locator('.sources p')).toContainText('ACID transactions');
  await page.screenshot({
    path: `../.runtime/${testInfo.project.name}-conversation.png`,
    fullPage: true,
  });
  const downloaded = page.waitForEvent('download');
  await page.getByLabel('Export conversation').click();
  expect((await downloaded).suggestedFilename()).toBe('voxdesk-conversation.json');
  await page.reload();
  if (testInfo.project.name === 'mobile')
    await page.getByRole('button', { name: 'Open history' }).click();
  await page.locator('.history-row>button:first-child').first().click();
  await expect(page.getByText('Grounded in your notes', { exact: true })).toBeVisible();
  expect(errors).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
});

test('microphone recording decodes and reaches the voice answer', async ({ page, context }) => {
  await context.grantPermissions(['microphone']);
  await page.goto('/');
  await expect(page.getByText('Test fixtures', { exact: true })).toBeVisible();
  await page.getByLabel('Start recording').click();
  await expect(page.getByLabel('Stop recording and send')).toBeVisible();
  await page.waitForTimeout(1100);
  await page.getByLabel('Stop recording and send').click();
  await expect(page.locator('.user-message')).toContainText('Why choose PostgreSQL?');
  await expect(page.getByRole('button', { name: /Listen|Stop/, exact: true })).toBeVisible();
});
