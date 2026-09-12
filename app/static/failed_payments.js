(() => {
    const root = document.querySelector('[data-payment-workspace]');
    const dialog = document.querySelector('[data-payment-dialog]');
    if (!root || !dialog) return;
    const find = (name) => dialog.querySelector(`[data-payment-${name}]`);
    const title = find('title');
    const feedback = find('feedback');
    const editor = find('editor');
    const confirmation = find('confirmation');
    const remark = find('remark');
    const save = find('save');
    const back = find('back');
    const retry = find('retry');
    const cards = [...dialog.querySelectorAll('[data-payment-action]')];
    let row = null;
    let action = 'outreach';
    let confirming = false;
    let saving = false;
    let ready = false;
    let loadVersion = 0;
    const message = (text, error = false) => {
        feedback.textContent = text;
        feedback.classList.toggle('is-error', error);
    };
    const renderEditor = () => {
        if (!save) return;
        editor.hidden = confirming;
        confirmation.hidden = !confirming;
        back.hidden = !confirming;
        title.textContent = confirming ? 'Confirm follow-up' : 'Keep in touch';
        save.textContent = saving ? 'Saving…' : confirming ? 'Yes, save follow-up' : action === 'outreach' ? 'Continue' : 'Save remark';
        save.disabled = saving || !ready;
        back.disabled = saving;
        remark.disabled = saving;
        find('remark-label').textContent = action === 'outreach' ? 'Remarks (optional)' : 'Remarks';
        cards.forEach((card) => {
            card.disabled = saving;
            card.setAttribute('aria-pressed', String(card.dataset.paymentAction === action));
        });
        dialog.querySelectorAll('[data-payment-close]').forEach((button) => { button.disabled = saving; });
    };
    const renderHistory = (payload) => {
        const count = payload.outreach_count;
        find('count').textContent = count ? `Reached out ${count} ${count === 1 ? 'time' : 'times'} so far` : 'No outreach yet';
        const history = find('history');
        history.replaceChildren();
        payload.history.forEach((entry) => {
            const item = document.createElement('article');
            item.className = 'payment-history-entry';
            const heading = document.createElement('strong');
            heading.textContent = entry.kind === 'outreach' ? 'Reached out' : 'Remark added';
            item.append(heading);
            if (entry.remark) {
                const note = document.createElement('p');
                note.textContent = entry.remark;
                item.append(note);
            }
            const meta = document.createElement('small');
            meta.textContent = `${entry.created_by || 'Former team member'} · ${entry.created_at}`;
            item.append(meta);
            history.append(item);
        });
        if (!payload.history.length) {
            const empty = document.createElement('p');
            empty.className = 'payment-history-empty';
            empty.textContent = 'No follow-ups yet. Start with a message or leave a note for the team.';
            history.append(empty);
        }
        const tag = row.querySelector('[data-payment-open="outreach"]');
        tag.textContent = count > 1 ? `Reached-out (${count})` : count ? 'Reached-out' : 'Not reached out';
        tag.classList.toggle('is-reached-out', count > 0);
        const notes = payload.history.filter((entry) => entry.remark);
        row.querySelector('[data-payment-remark-preview]').textContent = notes[0]?.remark || 'No remarks yet';
        row.querySelector('[data-payment-open="remark"]').textContent = notes.length ? `View remarks (${notes.length})` : dialog.dataset.canEdit === 'true' ? 'Add remark' : 'View remarks';
    };
    const readResponse = async (response) => {
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || !Array.isArray(payload.history)) {
            throw new Error(payload.error || 'Unable to load follow-ups. Refresh the page and try again.');
        }
        return payload;
    };
    const loadHistory = async () => {
        const version = ++loadVersion;
        ready = false;
        retry.hidden = true;
        message('Loading follow-ups…');
        renderEditor();
        try {
            const payload = await fetch(row.dataset.followupUrl, {headers: {Accept: 'application/json'}, credentials: 'same-origin'}).then(readResponse);
            if (version !== loadVersion || !dialog.open) return;
            renderHistory(payload);
            ready = true;
            message('');
        } catch (error) {
            if (version !== loadVersion || !dialog.open) return;
            message(error.message, true);
            retry.hidden = false;
        } finally {
            if (version === loadVersion) renderEditor();
        }
    };
    root.querySelectorAll('[data-payment-open]').forEach((button) => {
        button.addEventListener('click', () => {
            if (dialog.open) return;
            row = button.closest('[data-payment-row]');
            action = button.dataset.paymentOpen;
            confirming = false;
            saving = false;
            ready = false;
            if (remark) remark.value = '';
            title.textContent = 'Keep in touch';
            find('name').textContent = row.dataset.name;
            find('count').textContent = '';
            find('history').replaceChildren();
            renderEditor();
            dialog.showModal();
            title.focus();
            loadHistory();
        });
    });
    cards.forEach((card) => card.addEventListener('click', () => {
        action = card.dataset.paymentAction;
        renderEditor();
    }));
    back?.addEventListener('click', () => { confirming = false; renderEditor(); remark.focus(); });
    retry.addEventListener('click', loadHistory);
    dialog.querySelectorAll('[data-payment-close]').forEach((button) => button.addEventListener('click', () => {
        if (!saving) dialog.close();
    }));
    dialog.addEventListener('cancel', (event) => { if (saving) event.preventDefault(); });
    dialog.addEventListener('close', () => { loadVersion += 1; });
    save?.addEventListener('click', async () => {
        if (saving || !ready) return;
        if (action === 'remark' && !remark.value.trim()) {
            message('Please enter a remark.', true);
            remark.focus();
            return;
        }
        if (action === 'outreach' && !confirming) {
            confirming = true;
            message('');
            renderEditor();
            title.focus();
            return;
        }
        saving = true;
        message('');
        renderEditor();
        try {
            const payload = await fetch(row.dataset.followupUrl, {
                method: 'POST', credentials: 'same-origin',
                headers: {'Content-Type': 'application/json', Accept: 'application/json', 'X-CSRFToken': root.dataset.csrfToken},
                body: JSON.stringify({kind: action, remark: remark.value.trim(), confirmed: action === 'outreach'}),
            }).then(readResponse);
            renderHistory(payload);
            remark.value = '';
            confirming = false;
            message(action === 'outreach' ? 'Follow-up saved. Thank you for reaching out.' : 'Remark saved for the team.');
        } catch (error) {
            message(error.message || 'Unable to save. Please try again.', true);
        } finally {
            saving = false;
            renderEditor();
            title.focus();
        }
    });
})();
