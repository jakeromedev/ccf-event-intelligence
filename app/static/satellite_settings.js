(() => {
    const tools = document.querySelector("[data-satellite-settings-tools]");
    const search = tools?.querySelector("[data-settings-search]");
    const filter = tools?.querySelector("[data-settings-group-filter]");
    const results = tools?.querySelector("[data-settings-results]");
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

    const selectedGroup = () => filter?.querySelector("input:checked")?.value || "all";

    const applyFilters = () => {
        if (!tools) return;
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
    document.querySelectorAll("[data-expand-all]").forEach((button) => button.addEventListener("click", () => cards.filter((card) => !card.hidden && !card.closest("[data-hub-group]").hidden).forEach((card) => setHubExpanded(card, true))));
    document.querySelectorAll("[data-collapse-all]").forEach((button) => button.addEventListener("click", () => cards.filter((card) => !card.hidden && !card.closest("[data-hub-group]").hidden).forEach((card) => setHubExpanded(card, false))));
    search?.addEventListener("input", applyFilters);
    filter?.addEventListener("change", applyFilters);
    document.querySelector("[data-clear-search]")?.addEventListener("click", () => { search.value = ""; filter.querySelector("input[value='all']").checked = true; applyFilters(); search.focus(); });

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

    document.querySelectorAll("[data-event-settings-filters]").forEach((eventFilters) => {
        const groupSelect = eventFilters.querySelector("[data-event-group]");
        const hubSelect = eventFilters.querySelector("[data-event-hub]");
        const satelliteSelect = eventFilters.querySelector("[data-event-satellite]");
        const cascade = (resetHub = false) => {
            if (resetHub) hubSelect.value = "";
            [...hubSelect.options].forEach((option, index) => {
                option.hidden = index > 0 && Boolean(groupSelect.value) && option.dataset.groupCode !== groupSelect.value;
            });
            if (hubSelect.selectedOptions[0]?.hidden) hubSelect.value = "";
            [...satelliteSelect.options].forEach((option, index) => {
                option.hidden = index > 0 && (
                    (Boolean(groupSelect.value) && option.dataset.groupCode !== groupSelect.value)
                    || (Boolean(hubSelect.value) && option.dataset.hubId !== hubSelect.value)
                );
            });
            if (satelliteSelect.selectedOptions[0]?.hidden) satelliteSelect.value = "";
        };
        groupSelect.addEventListener("change", () => { cascade(true); satelliteSelect.value = ""; });
        hubSelect.addEventListener("change", () => { satelliteSelect.value = ""; cascade(); });
        cascade();
    });

    const mobileFilterDialog = document.querySelector("[data-mobile-filter-dialog]");
    const mobileFilterOpen = document.querySelector("[data-mobile-filters-open]");
    if (mobileFilterDialog && mobileFilterOpen) {
        const closeMobileFilters = () => closeDialog(mobileFilterDialog);
        mobileFilterOpen.addEventListener("click", () => {
            returnFocus = mobileFilterOpen;
            mobileFilterDialog.showModal();
            requestAnimationFrame(() => mobileFilterDialog.querySelector("[data-event-group]").focus());
        });
        mobileFilterDialog.querySelectorAll("[data-mobile-filters-close]").forEach((button) => {
            button.addEventListener("click", closeMobileFilters);
        });
        mobileFilterDialog.addEventListener("click", (event) => {
            if (event.target === mobileFilterDialog) closeMobileFilters();
        });
        mobileFilterDialog.addEventListener("cancel", (event) => {
            event.preventDefault();
            closeMobileFilters();
        });
    }

    const directory = document.querySelector("[data-settings-directory][data-registrants-url]");
    const statusClass = (row) => row.needs_review ? "review" : row.status === "Already Synced" ? "synced" : "ready";
    const makeCell = (value, tag = "td") => {
        const cell = document.createElement(tag);
        cell.textContent = value || "—";
        return cell;
    };
    const renderDrilldown = (panel, payload, state) => {
        panel.replaceChildren();
        const controls = document.createElement("div");
        controls.className = "satellite-drilldown-controls";
        const searchInput = document.createElement("input");
        searchInput.type = "search";
        searchInput.placeholder = "Search participant or registration ID";
        searchInput.value = state.q;
        searchInput.setAttribute("aria-label", "Search registrants in this Satellite");
        const status = document.createElement("select");
        status.setAttribute("aria-label", "Filter registrants by sync status");
        [["all", "All statuses"], ["synced", "Synced"], ["needs_review", "Needs Review"], ["ready_to_sync", "Ready to Sync"]].forEach(([value, label]) => {
            const option = document.createElement("option");
            option.value = value;
            option.textContent = label;
            option.selected = state.syncStatus === value;
            status.append(option);
        });
        controls.append(searchInput, status);
        panel.append(controls);

        if (!payload.rows.length) {
            const empty = document.createElement("p");
            empty.className = "satellite-drilldown-empty";
            empty.textContent = "No registrants match these filters.";
            panel.append(empty);
        } else {
            const wrap = document.createElement("div");
            wrap.className = "satellite-drilldown-table";
            wrap.tabIndex = 0;
            wrap.setAttribute("role", "region");
            wrap.setAttribute("aria-label", "Satellite registrants");
            const table = document.createElement("table");
            const head = document.createElement("thead");
            const headRow = document.createElement("tr");
            ["Participant", "Registration", "Hub", "Satellite", "Status"].forEach((label) => headRow.append(makeCell(label, "th")));
            head.append(headRow);
            const body = document.createElement("tbody");
            payload.rows.forEach((row) => {
                const tr = document.createElement("tr");
                tr.append(makeCell(row.participant), makeCell(row.identifier), makeCell(row.hub), makeCell(row.satellite));
                const statusCell = document.createElement("td");
                const badge = document.createElement("span");
                badge.className = `satellite-status is-${statusClass(row)}`;
                badge.textContent = row.status;
                statusCell.append(badge);
                tr.append(statusCell);
                body.append(tr);
            });
            table.append(head, body);
            wrap.append(table);
            panel.append(wrap);
        }

        const footer = document.createElement("div");
        footer.className = "satellite-drilldown-pagination";
        const summary = document.createElement("span");
        summary.setAttribute("aria-live", "polite");
        summary.textContent = `Showing ${payload.pagination.start}–${payload.pagination.end} of ${payload.pagination.total}`;
        const actions = document.createElement("div");
        [["Previous", state.page - 1, !payload.pagination.has_previous], ["Next", state.page + 1, !payload.pagination.has_next]].forEach(([label, page, disabled]) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "button secondary compact";
            button.textContent = label;
            button.disabled = disabled;
            button.addEventListener("click", () => loadDrilldown(panel, {...state, page}));
            actions.append(button);
        });
        footer.append(summary, actions);
        panel.append(footer);

        let timer;
        searchInput.addEventListener("input", () => {
            window.clearTimeout(timer);
            timer = window.setTimeout(() => loadDrilldown(panel, {...state, q: searchInput.value.trim(), page: 1}), 300);
        });
        status.addEventListener("change", () => loadDrilldown(panel, {...state, syncStatus: status.value, page: 1}));
    };
    const loadDrilldown = async (panel, state) => {
        panel.hidden = false;
        panel.setAttribute("aria-busy", "true");
        if (!panel.childElementCount) panel.textContent = "Loading registrants…";
        const url = new URL(directory.dataset.registrantsUrl, window.location.origin);
        url.searchParams.set("satellite_id", state.satelliteId);
        url.searchParams.set("q", state.q || "");
        url.searchParams.set("sync_status", state.syncStatus || "all");
        url.searchParams.set("page", state.page || 1);
        url.searchParams.set("per_page", 10);
        try {
            const response = await fetch(url, {headers: {Accept: "application/json"}});
            if (!response.ok) throw new Error("Request failed");
            renderDrilldown(panel, await response.json(), state);
            if (state.focusPanel && document.activeElement === state.focusTrigger) panel.focus({preventScroll: true});
            state.focusPanel = false;
        } catch (_error) {
            panel.textContent = "Registrants could not be loaded. Try again.";
        } finally {
            panel.removeAttribute("aria-busy");
        }
    };
    directory?.querySelectorAll("[data-satellite-registrants-toggle]").forEach((toggle) => toggle.addEventListener("click", () => {
        const panel = document.getElementById(toggle.getAttribute("aria-controls"));
        const opening = toggle.getAttribute("aria-expanded") !== "true";
        toggle.closest("[data-hub-card]").querySelectorAll("[data-satellite-registrants-toggle][aria-expanded='true']").forEach((other) => {
            if (other === toggle) return;
            other.setAttribute("aria-expanded", "false");
            other.textContent = "View Registrants";
            document.getElementById(other.getAttribute("aria-controls")).hidden = true;
        });
        toggle.setAttribute("aria-expanded", String(opening));
        toggle.textContent = opening ? "Hide Registrants" : "View Registrants";
        panel.hidden = !opening;
        if (opening && !panel.dataset.loaded) {
            panel.dataset.loaded = "true";
            panel.tabIndex = -1;
            loadDrilldown(panel, {satelliteId: toggle.dataset.satelliteId, q: "", syncStatus: "all", page: 1, focusPanel: true, focusTrigger: toggle});
        }
    }));

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
