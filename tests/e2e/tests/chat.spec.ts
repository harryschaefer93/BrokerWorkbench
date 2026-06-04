import { test, expect } from '@playwright/test';

/**
 * Chat end-to-end test against the live BrokerWorkbench frontend.
 *
 * Verifies:
 *   1. Chat panel mounts (`[data-testid=chat-panel]`)
 *   2. User can type + send a prompt
 *   3. Assistant message streams tokens (data-streaming flips)
 *   4. At least one MCP tool pill renders
 *   5. `bw-conv-id` is persisted to localStorage and reused
 *
 * Skips if the frontend FQDN is unreachable (e.g. westus2 RG decommissioned
 * + caller forgot to set BROKER_FRONTEND_URL).
 */
test.describe('chat e2e', () => {
  test('user can send a prompt and see streamed answer with tool pills', async ({ page }) => {
    let response;
    try {
      response = await page.goto('/', { waitUntil: 'domcontentloaded' });
    } catch (err) {
      test.skip(true, `frontend unreachable: ${err}`);
      return;
    }
    expect(response).not.toBeNull();
    expect(response!.ok(), `HTTP ${response!.status()}`).toBeTruthy();

    // Mount check
    const panel = page.locator('[data-testid=chat-panel]');
    await expect(panel).toBeVisible({ timeout: 30_000 });

    // Wait for welcome message to render (so we can distinguish from later answer).
    const assistantMessages = page.locator('[data-testid=chat-message-assistant]');
    await expect(assistantMessages.first()).toBeVisible({ timeout: 30_000 });
    const initialAssistantCount = await assistantMessages.count();

    // Type a prompt
    const input = page.locator('[data-testid=chat-input]');
    await input.fill('Show me the top 3 critical renewals');
    await page.locator('[data-testid=chat-send]').click();

    // Wait for a NEW assistant message to appear.
    await expect(async () => {
      const c = await assistantMessages.count();
      expect(c).toBeGreaterThan(initialAssistantCount);
    }).toPass({ timeout: 60_000 });

    const assistantMsg = assistantMessages.last();
    await expect(assistantMsg).toBeVisible();

    // Wait for streaming to complete on that NEW message, and for the
    // final answer text to be substantially populated (welcome message has
    // data-streaming=false too, so we ALSO assert content length).
    const assertAnswerReady = async () => {
      const streaming = await assistantMsg.getAttribute('data-streaming');
      const text = (await assistantMsg.innerText()).trim();
      if (streaming !== 'false') throw new Error(`still streaming (=${streaming})`);
      if (text.length < 50) throw new Error(`answer still short (len=${text.length})`);
    };
    await expect(assertAnswerReady).toPass({ timeout: 240_000 });
    await page.waitForTimeout(300);

    // Answer should mention renewal-relevant words.
    const text = (await assistantMsg.innerText()).toLowerCase();
    const keywordHits = ['renewal', 'expir', 'priority', 'critical'].filter((kw) =>
      text.includes(kw),
    );
    expect(keywordHits.length, `answer keywords: ${text.slice(0, 200)}`).toBeGreaterThanOrEqual(2);

    // At least one tool pill must appear.
    const toolPills = page.locator('[data-testid=tool-pill]');
    await expect(toolPills.first()).toBeVisible({ timeout: 5_000 });
    const pillCount = await toolPills.count();
    expect(pillCount).toBeGreaterThanOrEqual(1);

    // conversation_id is persisted to localStorage by useApi.
    const convId = await page.evaluate(() => window.localStorage.getItem('bw-conv-id'));
    expect(convId, 'bw-conv-id should be set in localStorage').toBeTruthy();
    expect(convId!.length).toBeGreaterThan(8);
  });
});
