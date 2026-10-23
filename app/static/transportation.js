(() => {
  const dialog = document.querySelector('[data-transportation-dialog]');
  if (!dialog) return;
  const form = dialog.querySelector('form');
  const fields = dialog.querySelector('[data-transportation-fields]');
  const save = dialog.querySelector('[data-transportation-save]');
  const reload = dialog.querySelector('[data-transportation-reload]');
  const error = dialog.querySelector('[data-transportation-error]');
  const status = dialog.querySelector('[data-transportation-status]');
  const person = dialog.querySelector('[data-transportation-person]');
  const selects = [...dialog.querySelectorAll('[data-trip]')];
  const reason = form.elements.reason;
  let state = null;
  let url = '';
  let busy = false;
  let generation = 0;
  let opener = null;
  const labels = {bus: 'Bus', carpool: 'Carpool', public_transportation: 'Public Transportation', other: 'Other', unreported: 'Not reported', conflicting: 'Conflicting answers'};

  function showError(message) {
    error.textContent = message;
    error.hidden = false;
    error.focus();
  }
  function updateSave() {
    save.disabled = busy || !state || selects.every(select => select.value === 'keep');
  }
  async function responseJSON(response) {
    if (response.redirected || !response.headers.get('content-type')?.includes('application/json')) {
      throw new Error('Your session may have expired. Reload the page and sign in again.');
    }
    return response.json();
  }
  async function load() {
    const requestGeneration = ++generation;
    state = null;
    fields.disabled = true;
    updateSave();
    reload.hidden = true;
    error.hidden = true;
    status.textContent = 'Loading current travel arrangements…';
    reason.value = '';
    selects.forEach(select => { select.value = 'keep'; });
    try {
      const response = await fetch(url, {headers: {'Accept': 'application/json'}, cache: 'no-store'});
      const data = await responseJSON(response);
      if (requestGeneration !== generation || !dialog.open) return;
      if (!response.ok) throw new Error(data.error || 'This participant is no longer available. Reload the page.');
      state = data;
      person.textContent = `${data.name} · ${data.codes}`;
      selects.forEach(select => {
        const trip = data.trips[select.dataset.trip];
        select.options[0].textContent = `Keep current: ${labels[trip.mode]}`;
        dialog.querySelector(`[data-imported="${select.dataset.trip}"]`).textContent =
          `Imported: ${trip.imported_values.join(' / ') || 'Not reported'}. Current source: ${trip.source === 'manual' ? 'manual override' : 'imported'}.`;
      });
      fields.disabled = false;
      status.textContent = 'Choose a new mode for either trip. Unchanged trips will be kept.';
      selects[0].focus();
    } catch (err) {
      if (requestGeneration !== generation || !dialog.open) return;
      status.textContent = '';
      reload.hidden = false;
      showError(err.message || 'Unable to load transportation. Please try again.');
    }
  }
  document.querySelectorAll('[data-transportation-edit]').forEach(button => {
    button.addEventListener('click', () => {
      opener = button;
      url = button.dataset.url;
      person.textContent = '';
      dialog.showModal();
      load();
    });
  });
  dialog.querySelectorAll('[data-transportation-close]').forEach(button => {
    button.addEventListener('click', () => { if (!busy) dialog.close(); });
  });
  dialog.addEventListener('cancel', event => { if (busy) event.preventDefault(); });
  dialog.addEventListener('close', () => {
    generation++;
    state = null;
    opener?.focus();
  });
  reload.addEventListener('click', load);
  selects.forEach(select => select.addEventListener('change', updateSave));
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (busy || !state || save.disabled) return;
    const changes = {};
    const revisions = {};
    selects.forEach(select => {
      if (select.value === 'keep') return;
      const trip = select.dataset.trip;
      changes[trip] = select.value === 'reset' ? null : select.value;
      revisions[trip] = state.trips[trip].revision;
    });
    busy = true;
    fields.disabled = true;
    updateSave();
    error.hidden = true;
    reload.hidden = true;
    status.textContent = 'Saving travel arrangements…';
    try {
      const response = await fetch(url, {
        method: 'POST', headers: {'Content-Type': 'application/json', 'Accept': 'application/json', 'X-CSRFToken': form.elements.csrf_token.value},
        body: JSON.stringify({changes, expected_revisions: revisions, expected_batch_id: state.active_batch_id, reason: reason.value}),
      });
      const data = await responseJSON(response);
      if (!response.ok) {
        if (response.status === 409 || response.status >= 500) state = null;
        throw new Error(data.error || 'Unable to save transportation. Reload the page and try again.');
      }
      window.location.reload();
    } catch (err) {
      // A network failure may have occurred after the server committed. Require
      // fresh values before another save rather than retrying an uncertain edit.
      state = null;
      status.textContent = '';
      reload.hidden = false;
      showError(err.message || 'Connection lost. Reload current values before trying again.');
    } finally {
      busy = false;
      fields.disabled = !state;
      updateSave();
    }
  });
})();
