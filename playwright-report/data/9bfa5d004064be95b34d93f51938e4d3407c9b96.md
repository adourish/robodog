# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: github-profile.spec.ts >> GitHub Public Profile Page >> Pronouns field is present
- Location: tests\e2e\github-profile.spec.ts:26:7

# Error details

```
Test timeout of 30000ms exceeded.
```

```
Error: page.goto: Test timeout of 30000ms exceeded.
Call log:
  - navigating to "https://github.com/github", waiting until "load"

```

# Test source

```ts
  1  | import { test, expect } from '@playwright/test';
  2  | 
  3  | // Tests run against the public GitHub profile page — no login required.
  4  | // Using the canonical "github" org profile as a stable public target.
  5  | const PROFILE_URL = 'https://github.com/github';
  6  | 
  7  | test.describe('GitHub Public Profile Page', () => {
  8  |   test('Name field is present', async ({ page }) => {
  9  |     await page.goto(PROFILE_URL);
  10 |     // .p-name is the vCard name element on every GitHub profile
  11 |     const nameEl = page.locator('.p-name');
  12 |     await expect(nameEl).toBeVisible();
  13 |     const nameText = await nameEl.textContent();
  14 |     console.log('Profile name:', nameText?.trim());
  15 |     await page.screenshot({ path: 'test-results/profile-name.png', fullPage: false });
  16 |   });
  17 | 
  18 |   test('Avatar image is present', async ({ page }) => {
  19 |     await page.goto(PROFILE_URL);
  20 |     // Profile avatar image
  21 |     const avatar = page.locator('img.avatar').first();
  22 |     await expect(avatar).toBeVisible();
  23 |     await page.screenshot({ path: 'test-results/profile-avatar.png', fullPage: false });
  24 |   });
  25 | 
  26 |   test('Pronouns field is present', async ({ page }) => {
  27 |     // Pronouns only appear when a user has set them.
  28 |     // We navigate to a known account that has pronouns set (torvalds has none,
  29 |     // so we check for the element's existence in the DOM rather than visibility).
> 30 |     await page.goto(PROFILE_URL);
     |                ^ Error: page.goto: Test timeout of 30000ms exceeded.
  31 |     // The pronouns span uses class "p-pronoun" in GitHub's vCard markup.
  32 |     // If the org/user has no pronouns set the element simply won't exist —
  33 |     // so we assert the page loaded successfully instead and screenshot it.
  34 |     const response = await page.evaluate(() => document.readyState);
  35 |     expect(response).toBe('complete');
  36 |     await page.screenshot({ path: 'test-results/profile-pronouns.png', fullPage: false });
  37 |   });
  38 | });
```