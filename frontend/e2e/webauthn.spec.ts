import { test, expect } from '@playwright/test';

async function addVirtualAuthenticator(page: any) {
  // Playwright exposes CDP for Chromium-based browsers.
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('WebAuthn.enable');
  const { authenticatorId } = await cdp.send('WebAuthn.addVirtualAuthenticator', {
    options: {
      protocol: 'ctap2',
      transport: 'internal',
      hasResidentKey: true,
      hasUserVerification: true,
      isUserVerified: true,
      automaticPresenceSimulation: true,
    },
  });
  return { cdp, authenticatorId };
}

test('register + login with passkey (virtual authenticator)', async ({ page }) => {
  await addVirtualAuthenticator(page);

  await page.goto('/app/timeline', { waitUntil: 'domcontentloaded' });

  // Sign-in screen should be present.
  await expect(page.getByRole('heading', { name: 'Unlock your library' })).toBeVisible();

  // Register the first owner passkey.
  await page.getByRole('button', { name: 'Create passkey' }).click();
  await expect(page.getByRole('status')).toContainText('Passkey created');

  // Login using that passkey.
  await page.getByRole('button', { name: 'Sign in with passkey' }).click();

  // After login, we should see the owner shell.
  await expect(page.getByRole('heading', { name: 'Owner console' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Timeline' })).toBeVisible();
});
