// Run with Playwright on NODE_PATH and a rendered Failed Payments page as argv[2].
const {chromium} = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

(async () => {
    const browser = await chromium.launch({channel: 'chrome', headless: true});
    try {
        const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
        const errors = [];
        page.on('pageerror', (error) => errors.push(error.message));
        await page.setContent(fs.readFileSync(process.argv[2], 'utf8'));
        const staticDir = path.resolve(__dirname, '../app/static');
        for (const file of ['app.css', 'failed_payments.css']) await page.addStyleTag({path: path.join(staticDir, file)});
        await page.evaluate(() => {
            window.historyItems = [];
            window.savedRequests = [];
            window.failNext = false;
            window.fetch = async (url, options = {}) => {
                if (options.method === 'POST') {
                    await new Promise((resolve) => setTimeout(resolve, 100));
                    if (window.failNext) {
                        window.failNext = false;
                        return {ok: false, json: async () => ({error: 'Please try again.'})};
                    }
                    const input = JSON.parse(options.body);
                    window.savedRequests.push(input);
                    window.historyItems.unshift({...input, id: window.savedRequests.length,
                        created_by: 'Team member', created_at: '12 Sep 2026 · 10:30 AM'});
                }
                return {ok: true, json: async () => ({history: window.historyItems,
                    outreach_count: window.historyItems.filter((item) => item.kind === 'outreach').length})};
            };
        });
        await page.addScriptTag({path: path.join(staticDir, 'failed_payments.js')});
        const dialog = page.locator('[data-payment-dialog]');
        const save = page.locator('[data-payment-save]');
        await page.locator('[data-payment-open="outreach"]').click();
        await page.locator('[data-payment-remark]').fill('Asked for help. Will try payment again tomorrow.');
        await save.click();
        await page.getByRole('heading', {name: 'Save this follow-up?'}).waitFor();
        await page.getByRole('button', {name: 'Back', exact: true}).click();
        assert.equal(await page.locator('[data-payment-remark]').inputValue(), 'Asked for help. Will try payment again tomorrow.');
        await save.click();
        await page.getByRole('button', {name: 'Close', exact: true}).click();
        assert.equal(await page.evaluate(() => window.savedRequests.length), 0);
        for (const expected of [1, 2]) {
            await page.locator('[data-payment-open="outreach"]').click();
            await page.locator('[data-payment-remark]').fill('Sent a payment reminder.');
            await save.click();
            await save.click();
            await page.waitForFunction((count) => window.savedRequests.length === count, expected);
            await page.getByText('Follow-up saved. Thank you for reaching out.', {exact: true}).waitFor();
            await page.getByRole('button', {name: 'Close', exact: true}).click();
        }
        assert.equal(await page.locator('[data-payment-open="outreach"]').textContent(), 'Reached-out (2)');
        await page.locator('[data-payment-open="remark"]').click();
        await save.click();
        await page.getByText('Please enter a remark.', {exact: true}).waitFor();
        await page.locator('[data-payment-remark]').fill('<script>Keep this note as text</script>');
        await page.evaluate(() => { window.failNext = true; });
        await save.click();
        await page.getByText('Please try again.', {exact: true}).waitFor();
        assert.equal(await page.locator('[data-payment-remark]').inputValue(), '<script>Keep this note as text</script>');
        await save.click();
        await page.getByText('Remark saved for the team.', {exact: true}).waitFor();
        assert.equal(await page.locator('[data-payment-history] script').count(), 0);
        assert.equal(await page.locator('[data-payment-open="outreach"]').textContent(), 'Reached-out (2)');
        await page.keyboard.press('Escape');
        await dialog.waitFor({state: 'hidden'});
        await page.screenshot({path: '/tmp/failed-payments-table.png'});
        await page.locator('[data-payment-open="remark"]').click();
        await page.getByText('Remark added', {exact: true}).waitFor();
        await page.locator('[data-payment-history-filter="outreach"]').click();
        assert.equal(await page.locator('.payment-history-entry').count(), 2);
        assert.equal(await page.locator('.payment-history-entry.is-remark').count(), 0);
        await page.locator('[data-payment-history-filter="remark"]').click();
        assert.equal(await page.locator('.payment-history-entry').count(), 3);
        await page.locator('[data-payment-history-filter="all"]').click();
        await page.screenshot({path: '/tmp/failed-payments-dialog-desktop.png'});
        await page.setViewportSize({width: 390, height: 844});
        const saveBounds = await save.boundingBox();
        assert.ok(saveBounds && saveBounds.y >= 0 && saveBounds.y + saveBounds.height <= 844);
        await page.screenshot({path: '/tmp/failed-payments-dialog-mobile.png'});
        await page.locator('[data-payment-show-history]').click();
        await page.screenshot({path: '/tmp/failed-payments-history-mobile.png'});
        const historyBounds = await page.locator('.payment-history-entry').first().boundingBox();
        assert.ok(historyBounds && historyBounds.y >= 0 && historyBounds.y < 700);
        assert.equal(await page.evaluate(() => typeof window.Swal), 'undefined');
        assert.deepEqual(errors, []);
        console.log('PASS: cancellation, repeat outreach, remarks, safe text, failed-save retry, history and mobile layout without SweetAlert');
    } finally {
        await browser.close();
    }
})().catch((error) => {console.error(error); process.exitCode = 1;});
