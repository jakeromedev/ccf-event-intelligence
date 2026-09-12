// Run with Node and Playwright available on NODE_PATH.
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

(async () => {
    const browser = await chromium.launch({channel: 'chrome', headless: true});
    try {
        const page = await browser.newPage();
        const staticDir = path.resolve(__dirname, '../app/static');
        const template = fs.readFileSync(path.resolve(__dirname, '../app/templates/registrations.html'), 'utf8');
        const dialog = template.match(/<dialog class="facebook-status-dialog"[\s\S]*?<\/dialog>/)[0];
        await page.setContent('<button id="tag">Not Joined</button>' + dialog);
        await page.addStyleTag({path: path.join(staticDir, 'app.css')});
        const source = fs.readFileSync(path.join(staticDir, 'registrations.js'), 'utf8');
        const flow = source.slice(source.indexOf('    const facebookGroupLabel ='),
            source.indexOf('    const setZoomControls ='));
        await page.evaluate((flow) => {
            const canEditFacebookGroup = true;
            const facebookGroupUpdates = new Set();
            const batchSelect = {value: 'active'};
            const root = {dataset: {facebookGroupUrl: '/events/3/registrations/0/facebook-group', csrfToken: 'test'}};
            const row = {id: 1, first_name: 'Test', last_name: 'Participant', facebook_group_status: 'not_joined'};
            const button = document.querySelector('#tag');
            window.requests = [];
            window.fetch = async (url, options) => {
                window.requests.push(JSON.parse(options.body));
                return {ok: true, json: async () => ({status: JSON.parse(options.body).status,
                    outreach_count: window.requests.length, label: 'Reached-out'})};
            };
            const loadData = async () => {button.disabled = false;};
            const showUpdateFeedback = () => {};
            eval(flow + '\nbutton.onclick = () => updateFacebookGroupTag(row, button);');
        }, flow);
        let expectedRequests = 0;
        for (const confirm of [false, true, true]) {
            await page.locator('#tag').click();
            await page.locator('[data-facebook-status="reached_out"]').click();
            await page.getByRole('button', {name: 'Continue', exact: true}).click();
            await page.getByRole('heading', {name: 'Save this follow-up?'}).waitFor();
            await page.getByRole('button', {name: confirm ? 'Yes, save follow-up' : 'Cancel', exact: true}).click();
            await page.locator('[data-facebook-dialog]').waitFor({state: 'hidden'});
            if (confirm) {
                expectedRequests += 1;
                await page.waitForFunction((count) => window.requests.length === count, expectedRequests);
                await page.waitForFunction(() => !document.querySelector('#tag').disabled);
            }
            if (!confirm) assert.equal(await page.evaluate(() => window.requests.length), 0);
        }
        assert.deepEqual(await page.evaluate(() => window.requests), [
            {status: 'reached_out', record_outreach: true},
            {status: 'reached_out', record_outreach: true},
        ]);
        await page.locator('#tag').click();
        await page.getByRole('button', {name: 'Continue', exact: true}).click();
        await page.getByRole('button', {name: 'Back', exact: true}).click();
        await page.locator('[data-facebook-status="joined"]').click();
        await page.getByRole('button', {name: 'Save status', exact: true}).click();
        await page.locator('[data-facebook-dialog]').waitFor({state: 'hidden'});
        await page.waitForFunction(() => window.requests.length === 3 && !document.querySelector('#tag').disabled);
        assert.deepEqual(await page.evaluate(() => window.requests.at(-1)), {status: 'joined', record_outreach: false});
        await page.locator('#tag').click();
        await page.keyboard.press('Escape');
        await page.locator('[data-facebook-dialog]').waitFor({state: 'hidden'});
        assert.equal(await page.evaluate(() => window.requests.length), 3);
        assert.equal(await page.evaluate(() => document.activeElement.id), 'tag');
        await page.locator('#tag').click();
        await page.screenshot({path: '/tmp/facebook-status-desktop.png'});
        await page.setViewportSize({width: 375, height: 700});
        await page.screenshot({path: '/tmp/facebook-status-mobile.png'});
        await page.locator('[data-facebook-status="reached_out"]').click();
        await page.getByRole('button', {name: 'Continue', exact: true}).click();
        await page.screenshot({path: '/tmp/facebook-followup-mobile.png'});
        assert.equal(await page.evaluate(() => typeof window.Swal), 'undefined');
        console.log('PASS: custom modal, cancellation, repeated outreach, back, Joined, Escape, and focus restoration without SweetAlert');
    } finally {
        await browser.close();
    }
})().catch((error) => {console.error(error); process.exitCode = 1;});
