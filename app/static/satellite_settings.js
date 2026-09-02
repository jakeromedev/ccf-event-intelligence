(() => {
    const tools = document.querySelector("[data-satellite-settings-tools]");
    if (!tools) return;

    const search = tools.querySelector("[data-settings-search]");
    const filter = tools.querySelector("[data-settings-group-filter]");
    const results = tools.querySelector("[data-settings-results]");
    const noResults = document.querySelector("[data-settings-no-results]");
    const groups = [...document.querySelectorAll("[data-hub-group]")];
    const cards = [...document.querySelectorAll("[data-hub-card]")];
    const createDialog = document.querySelector("[data-settings-record-modal]");
    const createForm = createDialog.querySelector("[data-settings-record-form]");
    const editDrawer = document.querySelector("[data-settings-edit-drawer]");
    const editForm = editDrawer.querySelector("[data-settings-edit-form]");
    let returnFocus = null;

    const setHubExpanded = (card, expanded) => {
        const toggle = card.querySelector("[data-hub-toggle]");
        const body = card.querySelector("[data-hub-body]");
        if (!toggle || !body) return;
        toggle.setAttribute("aria-expanded", String(expanded));
        toggle.setAttribute("aria-label", `${expanded ? "Collapse" : "Expand"} ${card.querySelector("h3").textContent.trim()}`);
        body.hidden = !expanded;
    };

    const selectedGroup = () => filter.querySelector("input:checked")?.value || "all";

    const applyFilters = () => {
        const query = search.value.trim().toLocaleLowerCase();
        const groupCode = selectedGroup();
        let visibleGroups = 0;
        let visibleHubs = 0;
        let visibleSatellites = 0;

        groups.forEach((group) => {
            const allowed = groupCode === "all" || group.dataset.groupCode === groupCode;
            const groupMatches = Boolean(query) && group.dataset.groupName.includes(query);
            let groupHubMatches = 0;

            group.querySelectorAll("[data-hub-card]").forEach((card) => {
                const hubMatches = Boolean(query) && card.dataset.hubName.includes(query);
                let satelliteMatches = 0;
                card.querySelectorAll("[data-satellite-row]").forEach((row) => {
                    const matches = !query || row.dataset.satelliteName.includes(query);
                    row.hidden = !matches;
                    if (matches) satelliteMatches += 1;
                });
                card.querySelectorAll("[data-hub-empty]").forEach((empty) => { empty.hidden = Boolean(query) && !groupMatches && !hubMatches; });
                const matches = allowed && (!query || hubMatches || satelliteMatches > 0);
                card.hidden = !matches;
                if (matches) {
                    groupHubMatches += 1;
                    visibleHubs += 1;
                    visibleSatellites += satelliteMatches;
                    if (query) {
                        if (!("preSearchExpanded" in card.dataset)) card.dataset.preSearchExpanded = card.querySelector("[data-hub-toggle]").getAttribute("aria-expanded");
                        setHubExpanded(card, true);
                    } else if ("preSearchExpanded" in card.dataset) {
                        setHubExpanded(card, card.dataset.preSearchExpanded === "true");
                        delete card.dataset.preSearchExpanded;
                    }
                }
            });

            const visible = allowed && (!query || groupMatches || groupHubMatches > 0);
            group.hidden = !visible;
            if (visible) visibleGroups += 1;
        });

        const groupResult = query && visibleHubs === 0 && visibleSatellites === 0 ? `${visibleGroups} ${visibleGroups === 1 ? "Hub Group" : "Hub Groups"} · ` : "";
        results.textContent = `${groupResult}${visibleHubs} ${visibleHubs === 1 ? "Hub" : "Hubs"} · ${visibleSatellites} ${visibleSatellites === 1 ? "Satellite" : "Satellites"}`;
        noResults.hidden = visibleGroups !== 0;
    };

    const setFieldState = (field, visible) => {
        field.hidden = !visible;
        field.querySelectorAll("input, select, textarea").forEach((control) => {
            control.disabled = !visible;
            control.required = visible;
        });
    };

    const parseBulkValues = (value) => value.split(/[,\t\r\n]+/).map((entry) => entry.trim().replace(/\s+/g, " ")).filter(Boolean);

    const updateBulkCount = () => {
        const count = parseBulkValues(createForm.querySelector("[data-record-values]").value).length;
        const label = createForm.querySelector("[data-bulk-detected]");
        label.textContent = `${count} ${count === 1 ? "entry" : "entries"} detected`;
        const submit = createForm.querySelector("[data-record-submit]");
        const recordLabel = createForm.dataset.kind === "hub" ? "Hub" : "Satellite";
        submit.textContent = `Review ${count || ""} ${recordLabel}${count === 1 ? "" : "s"}`.replace("Review  ", "Review ");
    };

    const configureCreateForm = (kind, mode, parentId = "", parentName = "") => {
        createForm.reset();
        createForm.querySelectorAll("[data-record-parent-context]").forEach((context) => {
            context.hidden = true;
            context.textContent = "";
        });
        createForm.querySelectorAll("[data-record-hub-group], [data-record-hub]").forEach((select) => {
            delete select.dataset.contextLocked;
            select.removeAttribute("aria-readonly");
            select.removeAttribute("tabindex");
        });
        createForm.hidden = false;
        createForm.dataset.kind = kind;
        createForm.dataset.mode = mode;
        const bulk = mode === "bulk";
        const label = kind === "hub" ? "Hub" : "Satellite";
        const groupField = createForm.querySelector("[data-record-hub-group-field]");
        const hubField = createForm.querySelector("[data-record-hub-field]");
        const parentField = kind === "hub" ? groupField : hubField;
        const parentSelect = kind === "hub" ? createForm.querySelector("[data-record-hub-group]") : createForm.querySelector("[data-record-hub]");
        const name = createForm.querySelector("[data-record-name]");
        const values = createForm.querySelector("[data-record-values]");
        setFieldState(groupField, kind === "hub");
        setFieldState(hubField, kind === "satellite");
        setFieldState(createForm.querySelector("[data-record-name-field]"), !bulk);
        setFieldState(createForm.querySelector("[data-record-values-field]"), bulk);
        createForm.querySelector("[data-bulk-detected]").hidden = !bulk;
        name.maxLength = kind === "hub" ? 160 : 512;
        name.placeholder = `Enter ${label} Name`;
        values.placeholder = `Paste ${label} names, one per line or separated by commas or tabs`;
        createForm.querySelector("[data-record-name-label]").textContent = `${label} Name`;
        createForm.querySelector("[data-record-values-label]").textContent = `Paste ${label} Names`;
        if (parentId) {
            parentSelect.value = parentId;
            parentSelect.dataset.contextLocked = "true";
            parentSelect.setAttribute("aria-readonly", "true");
            parentSelect.setAttribute("tabindex", "-1");
            const context = parentField.querySelector("[data-record-parent-context]");
            context.textContent = `${parentName} is selected from the directory.`;
            context.hidden = false;
        }
        createForm.action = bulk
            ? createForm.dataset[kind === "hub" ? "bulkHubUrl" : "bulkSatelliteUrl"]
            : createForm.dataset[kind === "hub" ? "createHubUrl" : "createSatelliteUrl"];
        createDialog.querySelector("[data-record-dialog-mode]").textContent = bulk ? "Bulk Encoding" : "New Directory Record";
        createDialog.querySelector("[data-record-dialog-title]").textContent = `${bulk ? "Bulk Add" : "Add"} ${label}${bulk ? "s" : ""}`;
        createForm.querySelector("[data-record-submit]").textContent = bulk ? `Review ${label}s` : `Add ${label}`;
        createForm.querySelector("[data-record-submit]").dataset.loadingLabel = bulk ? "Reviewing Records…" : `Adding ${label}…`;
        updateBulkCount();
    };

    const openCreateDialog = (trigger) => {
        returnFocus = trigger;
        const menu = trigger.closest("[data-add-records-menu]");
        if (menu) menu.open = false;
        configureCreateForm(trigger.dataset.kind, trigger.dataset.mode, trigger.dataset.parentId, trigger.dataset.parentName);
        createDialog.showModal();
        requestAnimationFrame(() => createForm.querySelector(trigger.dataset.kind === "hub" ? "[data-record-hub-group]" : "[data-record-hub]").focus());
    };

    const closeDialog = (dialog) => {
        dialog.close();
        if (returnFocus?.isConnected) returnFocus.focus();
        returnFocus = null;
    };

    const setSubmitting = (form) => {
        form.setAttribute("aria-busy", "true");
        form.querySelectorAll("button[type='submit']").forEach((button) => {
            button.disabled = true;
            button.textContent = button.dataset.loadingLabel || "Saving Changes…";
        });
    };

    document.querySelectorAll("[data-hub-toggle]").forEach((toggle) => toggle.addEventListener("click", () => setHubExpanded(toggle.closest("[data-hub-card]"), toggle.getAttribute("aria-expanded") !== "true")));
    tools.querySelector("[data-expand-all]").addEventListener("click", () => cards.filter((card) => !card.hidden && !card.closest("[data-hub-group]").hidden).forEach((card) => setHubExpanded(card, true)));
    tools.querySelector("[data-collapse-all]").addEventListener("click", () => cards.filter((card) => !card.hidden && !card.closest("[data-hub-group]").hidden).forEach((card) => setHubExpanded(card, false)));
    search.addEventListener("input", applyFilters);
    filter.addEventListener("change", applyFilters);
    document.querySelector("[data-clear-search]").addEventListener("click", () => { search.value = ""; filter.querySelector("input[value='all']").checked = true; applyFilters(); search.focus(); });

    document.querySelectorAll("[data-settings-record-open]").forEach((trigger) => trigger.addEventListener("click", () => openCreateDialog(trigger)));
    createDialog.querySelectorAll("[data-settings-record-close]").forEach((button) => button.addEventListener("click", () => closeDialog(createDialog)));
    createDialog.addEventListener("click", (event) => { if (event.target === createDialog) closeDialog(createDialog); });
    createForm.querySelector("[data-record-values]").addEventListener("input", updateBulkCount);
    createForm.addEventListener("submit", () => setSubmitting(createForm));

    document.querySelectorAll("[data-settings-edit-open]").forEach((trigger) => trigger.addEventListener("click", () => {
        returnFocus = trigger;
        const kind = trigger.dataset.kind;
        editForm.action = trigger.dataset.action;
        editForm.dataset.kind = kind;
        editForm.dataset.initialParent = trigger.dataset.parentId;
        editForm.dataset.initialParentName = trigger.dataset.parentName;
        editForm.dataset.recordName = trigger.dataset.name;
        editForm.querySelector("[data-edit-name]").value = trigger.dataset.name;
        editForm.querySelector("[data-edit-name]").maxLength = kind === "hub" ? 160 : 512;
        editForm.querySelector("[data-edit-name-label]").textContent = `${kind === "hub" ? "Hub" : "Satellite"} Name`;
        editDrawer.querySelector("[data-edit-eyebrow]").textContent = `Edit ${kind === "hub" ? "Hub" : "Satellite"}`;
        editDrawer.querySelector("[data-edit-title]").textContent = trigger.dataset.name;
        setFieldState(editForm.querySelector("[data-edit-group-field]"), kind === "hub");
        setFieldState(editForm.querySelector("[data-edit-hub-field]"), kind === "satellite");
        editForm.querySelector(kind === "hub" ? "[data-edit-group]" : "[data-edit-hub]").value = trigger.dataset.parentId;
        editForm.querySelector("[data-move-notice]").hidden = true;
        editDrawer.showModal();
        requestAnimationFrame(() => editForm.querySelector("[data-edit-name]").focus());
    }));
    editDrawer.querySelectorAll("[data-settings-edit-close]").forEach((button) => button.addEventListener("click", () => closeDialog(editDrawer)));
    editDrawer.addEventListener("click", (event) => { if (event.target === editDrawer) closeDialog(editDrawer); });

    const updateMoveNotice = () => {
        const select = editForm.querySelector(editForm.dataset.kind === "hub" ? "[data-edit-group]" : "[data-edit-hub]");
        const notice = editForm.querySelector("[data-move-notice]");
        const moving = select.value !== editForm.dataset.initialParent;
        notice.hidden = !moving;
        if (moving) notice.textContent = `${editForm.dataset.recordName} will move from ${editForm.dataset.initialParentName} to ${select.options[select.selectedIndex].text}.`;
    };
    editForm.querySelector("[data-edit-group]").addEventListener("change", updateMoveNotice);
    editForm.querySelector("[data-edit-hub]").addEventListener("change", updateMoveNotice);
    editForm.addEventListener("submit", (event) => {
        const kind = editForm.dataset.kind;
        const select = editForm.querySelector(kind === "hub" ? "[data-edit-group]" : "[data-edit-hub]");
        if (select.value !== editForm.dataset.initialParent) {
            const destination = select.options[select.selectedIndex].text;
            const consequence = kind === "hub" ? "All Satellites assigned to this Hub will move with it." : "Its imported data and existing analytical relationships will be preserved.";
            if (!window.confirm(`Move ${kind === "hub" ? "Hub" : "Satellite"}?\n\n${editForm.dataset.recordName} will move from:\n${editForm.dataset.initialParentName}\n→ ${destination}\n\n${consequence}`)) {
                event.preventDefault();
                return;
            }
        }
        setSubmitting(editForm);
    });

    document.querySelectorAll("[data-settings-form]:not([data-settings-record-form]):not([data-settings-edit-form])").forEach((form) => form.addEventListener("submit", () => setSubmitting(form)));

    if (createDialog.dataset.bulkReviewKind) {
        returnFocus = document.querySelector("[data-add-records-menu] summary");
        createDialog.querySelector("[data-record-dialog-mode]").textContent = "Review Before Saving";
        createDialog.querySelector("[data-record-dialog-title]").textContent = `Review ${createDialog.dataset.bulkReviewKind === "hub" ? "Hubs" : "Satellites"}`;
        createDialog.showModal();
        const editPaste = createDialog.querySelector("[data-edit-paste]");
        editPaste.addEventListener("click", () => {
            const kind = createDialog.dataset.bulkReviewKind;
            configureCreateForm(kind, "bulk", createDialog.dataset.bulkReviewParent);
            createForm.querySelector("[data-record-values]").value = [...createDialog.querySelectorAll("input[name='values']")].map((input) => input.value).join("\n");
            updateBulkCount();
            createDialog.querySelector("[data-bulk-review]").hidden = true;
            createDialog.querySelector("[data-record-dialog-mode]").textContent = "Bulk Encoding";
            createDialog.querySelector("[data-record-dialog-title]").textContent = `Bulk Add ${kind === "hub" ? "Hubs" : "Satellites"}`;
            createForm.querySelector("[data-record-values]").focus();
        });
    }

    const syncDialog = document.querySelector("[data-sync-review-modal]");
    if (syncDialog) {
        returnFocus = document.querySelector("[data-sync-open]");
        const reasonFilter = syncDialog.querySelector("[data-sync-reason-filter]");
        const failureRows = [...syncDialog.querySelectorAll("[data-sync-failure-row]")];
        const filterResult = syncDialog.querySelector("[data-sync-filter-result]");
        const filterEmpty = syncDialog.querySelector("[data-sync-filter-empty]");

        const applyReasonFilter = () => {
            const reason = reasonFilter?.value || "all";
            let visible = 0;
            failureRows.forEach((row) => {
                const matches = reason === "all" || row.dataset.syncReason === reason;
                row.hidden = !matches;
                if (matches) visible += 1;
            });
            if (filterResult) {
                filterResult.textContent = reason === "all"
                    ? `Showing all ${visible} registrations requiring review.`
                    : `Showing ${visible} ${visible === 1 ? "registration" : "registrations"} with reason: ${reason}.`;
            }
            if (filterEmpty) filterEmpty.hidden = visible !== 0;
        };

        syncDialog.querySelectorAll("[data-sync-review-close]").forEach((button) => {
            button.addEventListener("click", () => closeDialog(syncDialog));
        });
        syncDialog.addEventListener("click", (event) => {
            if (event.target === syncDialog) closeDialog(syncDialog);
        });
        syncDialog.addEventListener("cancel", (event) => {
            event.preventDefault();
            closeDialog(syncDialog);
        });
        reasonFilter?.addEventListener("change", applyReasonFilter);
        syncDialog.querySelector("[data-sync-view-failures]")?.addEventListener("click", () => {
            const target = reasonFilter || syncDialog.querySelector(".satellite-sync-table-wrap");
            target?.scrollIntoView({ behavior: "smooth", block: "nearest" });
            target?.focus();
        });
        applyReasonFilter();
        syncDialog.showModal();
        requestAnimationFrame(() => syncDialog.querySelector("#satellite-sync-title").focus());
    }

    applyFilters();
})();
