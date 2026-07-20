
const { chromium } = require('@playwright/test');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.goto('https://github.com/github');
  
  // Get page title and some key elements
  const title = await page.title();
  console.log('Title:', title);
  
  // Look for name/bio elements
  const elements = await page.evaluate(() => {
    const selectors = [
      'h1.vcard-names',
      '.p-name',
      '.p-org',
      '.p-note',
      'span.p-name',
      '.vcard-fullname',
      'img.avatar',
      '.js-profile-editable-area',
    ];
    return selectors.map(sel => {
      const el = document.querySelector(sel);
      return { selector: sel, found: !!el, text: el ? el.textContent.trim().substring(0, 80) : null };
    });
  });
  
  console.log(JSON.stringify(elements, null, 2));
  await browser.close();
})();
