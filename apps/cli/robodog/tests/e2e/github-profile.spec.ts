import { test, expect } from '@playwright/test';

/**
 * Playwright tests for GitHub Profile Settings Page
 * URL: https://github.com/settings/profile
 *
 * NOTE: These tests require you to be authenticated with GitHub.
 * Set the following environment variables before running:
 *   GITHUB_USERNAME - your GitHub username
 *   GITHUB_PASSWORD - your GitHub password
 *
 * Or use a saved auth state (see playwright.config.ts storageState).
 */

const PROFILE_URL = 'https://github.com/settings/profile';

// ---------------------------------------------------------------------------
// Helper: sign in once and reuse session across tests in this file
// ---------------------------------------------------------------------------
test.beforeEach(async ({ page }) => {
  // If already on a GitHub page with a session cookie this will be a no-op.
  await page.goto('https://github.com/login');

  // Only fill credentials when the login form is actually visible.
  const loginField = page.locator('#login_field');
  if (await loginField.isVisible()) {
    await loginField.fill(process.env.GITHUB_USERNAME ?? '');
    await page.locator('#password').fill(process.env.GITHUB_PASSWORD ?? '');
    await page.locator('[name="commit"]').click();
    await page.waitForURL('https://github.com/**');
  }

  await page.goto(PROFILE_URL);
  await page.waitForLoadState('networkidle');
});

// ---------------------------------------------------------------------------
// Page structure
// ---------------------------------------------------------------------------
test.describe('GitHub Profile Settings – Page Structure', () => {
  test('page has correct title', async ({ page }) => {
    await expect(page).toHaveTitle(/Public profile/i);
  });

  test('profile settings form is visible', async ({ page }) => {
    const form = page.locator('form.edit_user, form[action*="profile"]').first();
    await expect(form).toBeVisible();
  });

  test('Name field is present', async ({ page }) => {
    const nameInput = page.locator('input#user_profile_name');
    await expect(nameInput).toBeVisible();
  });

  test('Bio field is present', async ({ page }) => {
    const bioTextarea = page.locator('textarea#user_profile_bio');
    await expect(bioTextarea).toBeVisible();
  });

  test('URL field is present', async ({ page }) => {
    const urlInput = page.locator('input#user_profile_blog');
    await expect(urlInput).toBeVisible();
  });

  test('Company field is present', async ({ page }) => {
    const companyInput = page.locator('input#user_profile_company');
    await expect(companyInput).toBeVisible();
  });

  test('Location field is present', async ({ page }) => {
    const locationInput = page.locator('input#user_profile_location');
    await expect(locationInput).toBeVisible();
  });

  test('Save button is present', async ({ page }) => {
    const saveBtn = page.locator('button[type="submit"]').filter({ hasText: /update profile/i });
    await expect(saveBtn).toBeVisible();
  });

  test('profile picture / avatar section is visible', async ({ page }) => {
    const avatar = page.locator('.avatar, img[alt*="avatar"], img[alt*="Avatar"]').first();
    await expect(avatar).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Navigation & sidebar
// ---------------------------------------------------------------------------
test.describe('GitHub Profile Settings – Navigation', () => {
  test('Settings sidebar is visible', async ({ page }) => {
    const sidebar = page.locator('[aria-label="Account settings"], nav.settings-nav, .settings-sidebar').first();
    await expect(sidebar).toBeVisible();
  });

  test('sidebar contains "Profile" link', async ({ page }) => {
    const profileLink = page.locator('a[href="/settings/profile"]');
    await expect(profileLink.first()).toBeVisible();
  });

  test('sidebar contains "Account" link', async ({ page }) => {
    const accountLink = page.locator('a[href="/settings/admin"]');
    await expect(accountLink.first()).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Form interactions
// ---------------------------------------------------------------------------
test.describe('GitHub Profile Settings – Form Interactions', () => {
  test('Name field accepts text input', async ({ page }) => {
    const nameInput = page.locator('input#user_profile_name');
    await nameInput.click();
    await nameInput.fill('Test Name');
    await expect(nameInput).toHaveValue('Test Name');
    // Restore original value so we don't accidentally save
    await nameInput.fill('');
  });

  test('Bio field accepts multi-line text', async ({ page }) => {
    const bioTextarea = page.locator('textarea#user_profile_bio');
    await bioTextarea.click();
    await bioTextarea.fill('Line one\nLine two');
    await expect(bioTextarea).toHaveValue('Line one\nLine two');
    await bioTextarea.fill('');
  });

  test('Bio field enforces 160-character limit', async ({ page }) => {
    const bioTextarea = page.locator('textarea#user_profile_bio');
    const longText = 'A'.repeat(200);
    await bioTextarea.fill(longText);
    const value = await bioTextarea.inputValue();
    expect(value.length).toBeLessThanOrEqual(160);
    await bioTextarea.fill('');
  });

  test('URL field accepts a valid URL', async ({ page }) => {
    const urlInput = page.locator('input#user_profile_blog');
    await urlInput.fill('https://example.com');
    await expect(urlInput).toHaveValue('https://example.com');
    await urlInput.fill('');
  });

  test('Company field accepts text input', async ({ page }) => {
    const companyInput = page.locator('input#user_profile_company');
    await companyInput.fill('Acme Corp');
    await expect(companyInput).toHaveValue('Acme Corp');
    await companyInput.fill('');
  });

  test('Location field accepts text input', async ({ page }) => {
    const locationInput = page.locator('input#user_profile_location');
    await locationInput.fill('San Francisco, CA');
    await expect(locationInput).toHaveValue('San Francisco, CA');
    await locationInput.fill('');
  });
});

// ---------------------------------------------------------------------------
// Pronouns
// ---------------------------------------------------------------------------
test.describe('GitHub Profile Settings – Pronouns', () => {
  test('Pronouns dropdown or input is present', async ({ page }) => {
    const pronounsField = page.locator(
      'select#user_profile_pronouns, input#user_profile_pronouns_custom'
    ).first();
    await expect(pronounsField).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Accessibility
// ---------------------------------------------------------------------------
test.describe('GitHub Profile Settings – Accessibility', () => {
  test('all form inputs have associated labels', async ({ page }) => {
    const inputs = page.locator('form input[id], form textarea[id], form select[id]');
    const count = await inputs.count();
    expect(count).toBeGreaterThan(0);

    for (let i = 0; i < count; i++) {
      const input = inputs.nth(i);
      const id = await input.getAttribute('id');
      if (!id) continue;
      const label = page.locator(`label[for="${id}"]`);
      const labelCount = await label.count();
      if (await input.isVisible()) {
        expect(labelCount, `Missing label for input#${id}`).toBeGreaterThan(0);
      }
    }
  });

  test('Save button is keyboard-focusable', async ({ page }) => {
    const saveBtn = page.locator('button[type="submit"]').filter({ hasText: /update profile/i });
    await saveBtn.focus();
    await expect(saveBtn).toBeFocused();
  });
});

// ---------------------------------------------------------------------------
// Responsive / visual
// ---------------------------------------------------------------------------
test.describe('GitHub Profile Settings – Responsive Layout', () => {
  test('page renders correctly on mobile viewport', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto(PROFILE_URL);
    await page.waitForLoadState('networkidle');
    const form = page.locator('form.edit_user, form[action*="profile"]').first();
    await expect(form).toBeVisible();
  });

  test('page renders correctly on tablet viewport', async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.goto(PROFILE_URL);
    await page.waitForLoadState('networkidle');
    const form = page.locator('form.edit_user, form[action*="profile"]').first();
    await expect(form).toBeVisible();
  });
});