import { test, expect, type ConsoleMessage } from '@playwright/test';

const BASE_URL = 'http://localhost:8080';

/**
 * Smoke test: the React workbench must load at /, render the SPA mount point,
 * and not throw any console errors. If the dev server / nginx is unreachable
 * (developer hasn't started the stack), the test self-skips with a clear reason
 * rather than reporting a hard failure.
 */
test.describe('frontend smoke', () => {
  test('home page loads with no console errors', async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on('console', (msg: ConsoleMessage) => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });
    page.on('pageerror', (err) => {
      consoleErrors.push(`pageerror: ${err.message}`);
    });

    let response;
    try {
      response = await page.goto('/', { waitUntil: 'domcontentloaded' });
    } catch (err) {
      test.skip(
        true,
        `Frontend at ${BASE_URL} is unreachable — start it with ` +
          '\`cd frontend-react && npm run dev\` or run docker-compose up.',
      );
      return;
    }

    expect(response, 'navigation produced no response').not.toBeNull();
    expect(response!.ok(), `expected HTTP 2xx, got ${response!.status()}`).toBeTruthy();

    // SPA mount point must exist.
    await expect(page.locator('#root')).toBeAttached();

    // Tolerant title check — either contains BrokerHub-flavored copy, or the
    // SPA has at least populated the root div with content.
    const title = await page.title();
    const rootHtml = await page.locator('#root').innerHTML();
    expect(
      /broker/i.test(title) || rootHtml.trim().length > 0,
      `title=${JSON.stringify(title)}, root populated=${rootHtml.trim().length > 0}`,
    ).toBeTruthy();

    // No error-level console messages from the page itself.
    expect(consoleErrors, `unexpected console errors:\n${consoleErrors.join('\n')}`).toEqual([]);
  });
});
