import { test, expect } from '@playwright/test';

async function addVirtualAuthenticator(page: any) {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('WebAuthn.enable');
  await cdp.send('WebAuthn.addVirtualAuthenticator', {
    options: {
      protocol: 'ctap2',
      transport: 'internal',
      hasResidentKey: true,
      hasUserVerification: true,
      isUserVerified: true,
      automaticPresenceSimulation: true,
    },
  });
}

test('register + login then navigate owner shell', async ({ page }) => {
  await addVirtualAuthenticator(page);

  await page.goto('/app/timeline', { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: 'Unlock your library' })).toBeVisible();

  // Register the first owner passkey.
  await page.getByRole('button', { name: 'Create passkey' }).click();
  await expect(page.getByRole('status')).toContainText('Passkey created');

  // Login using that passkey.
  await page.getByRole('button', { name: 'Sign in with passkey' }).click();

  // Owner layout.
  await expect(page.getByRole('heading', { name: 'Owner console' })).toBeVisible();

  // Timeline route.
  await page.getByRole('link', { name: 'Timeline' }).click();
  await expect(page).toHaveURL(/\/app\/timeline$/);

  // Albums route.
  await page.getByRole('link', { name: 'Albums' }).click();
  await expect(page).toHaveURL(/\/app\/albums$/);

  // Viewer route.
  await page.getByRole('link', { name: 'Viewer' }).click();
  await expect(page).toHaveURL(/\/app\/viewer$/);
});
