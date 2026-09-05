(() => {
    const tools = document.querySelector("[data-satellite-settings-tools]");
    const search = tools?.querySelector("[data-settings-search]");
    const filter = tools?.querySelector("[data-settings-group-filter]");
    const results = tools?.querySelector("[data-settings-results]");
    const noResults = document.querySelector("[data-settings-no-results]");
    const groups = [...document.querySelectorAll("[data-hub-group]")];
    const createDialog = document.querySelector("[data-settings-record-modal]");
    const createForm = createDialog.querySelector("[data-settings-record-form]");
    const editDrawer = document.querySelector("[data-settings-edit-drawer]");
    const editForm = editDrawer.querySelector("[data-settings-edit-form]");
    let returnFocus = null;

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
            group.querySelectorAll("[data-hub-row]").forEach((row) => {
                const matches = allowed && (!query || groupMatches || row.dataset.searchText.includes(query));
                row.hidden = !matches;
                if (matches) {
                    groupHubMatches += 1;
                    visibleHubs += 1;
                    visibleSatellites += Number(row.cells[1]?.textContent || 0);
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

    search?.addEventListener("input", applyFilters);
    filter?.addEventListener("change", applyFilters);
    document.querySelector("[data-clear-search]")?.addEventListener("click", () => { search.value = ""; filter.querySelector("input[value='all']").checked = true; applyFilters(); search.focus(); });

    document.querySelectorAll("[data-settings-record-open]").forEach((trigger) => trigger.addEventListener("click", () => openCreateDialog(trigger)));
    createDialog.querySelectorAll("[data-settings-record-close]").forEach((button) => button.addEventListener("click", () => closeDialog(createDialog)));
    createDialog.addEventListener("click", (event) => { if (event.target === createDialog) closeDialog(createDialog); });
    createForm.querySelector("[data-record-values]").addEventListener("input", updateBulkCount);
    createForm.addEventListener("submit", () => setSubmitting(createForm));

    const openEditDrawer = (trigger) => {
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
    };
    document.querySelectorAll("[data-settings-edit-open]").forEach((trigger) => trigger.addEventListener("click", () => openEditDrawer(trigger)));
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

    const directory = document.querySelector("[data-settings-directory]");
    const explorer = document.querySelector("[data-satellite-explorer]");
    const explorerContent = explorer?.querySelector("[data-explorer-content]");
    const explorerTitle = explorer?.querySelector("[data-explorer-title]");
    const explorerBreadcrumb = explorer?.querySelector("[data-explorer-breadcrumb]");
    const assignmentDialog = document.querySelector("[data-registrant-assignment-dialog]");
    const assignmentForm = assignmentDialog?.querySelector("[data-registrant-assignment-form]");
    const assignmentSelect = assignmentDialog?.querySelector("[data-registrant-assignment-select]");
    const assignmentResetButton = assignmentDialog?.querySelector("[data-assignment-reset-open]");
    const resetDialog = document.querySelector("[data-assignment-reset-dialog]");
    const resetForm = resetDialog?.querySelector("[data-assignment-reset-form]");
    let assignmentReturnFocus = null;
    let currentAssignmentTrigger = null;
    const statusClass = (row) => row.needs_review ? "review" : (row.status === "Already Synced" || row.is_manual) ? "synced" : "ready";
    const makeCell = (value, tag = "td") => {
        const cell = document.createElement(tag);
        cell.textContent = value || "—";
        return cell;
    };
    const makeLocationCell = (name, hub) => {
        const cell = document.createElement("td");
        const strong = document.createElement("strong");
        const small = document.createElement("small");
        strong.textContent = name || "—";
        small.textContent = hub || "—";
        cell.append(strong, small);
        return cell;
    };
    const closeAssignmentDialog = () => {
        if (!assignmentDialog?.open) return;
        assignmentDialog.close();
        assignmentReturnFocus?.focus();
        assignmentReturnFocus = null;
    };
    const openAssignmentDialog = (trigger) => {
        if (!assignmentDialog || !assignmentForm || !assignmentSelect || !trigger.dataset.participantId) return;
        assignmentReturnFocus = trigger;
        currentAssignmentTrigger = trigger;
        assignmentForm.action = assignmentForm.dataset.actionTemplate.replace(
            /\/0\/satellite$/,
            `/${trigger.dataset.participantId}/satellite`,
        );
        assignmentDialog.querySelector("[data-assignment-participant]").textContent = trigger.dataset.participantName || "this registrant";
        assignmentDialog.querySelector("[data-assignment-imported]").textContent = trigger.dataset.importedSatellite || "—";
        assignmentDialog.querySelector("[data-assignment-effective]").textContent = trigger.dataset.effectiveSatellite || "Unassigned";
        const auditRow = assignmentDialog.querySelector("[data-assignment-audit-row]");
        const audit = assignmentDialog.querySelector("[data-assignment-audit]");
        const isManual = trigger.dataset.isManual === "true";
        assignmentResetButton.hidden = !isManual;
        auditRow.hidden = !isManual || !trigger.dataset.updatedBy;
        audit.textContent = trigger.dataset.updatedBy
            ? `${trigger.dataset.updatedBy}${trigger.dataset.updatedAt ? ` · ${trigger.dataset.updatedAt}` : ""}`
            : "—";
        assignmentSelect.value = trigger.dataset.directoryId || "";
        assignmentDialog.showModal();
        requestAnimationFrame(() => assignmentSelect.focus());
    };
    const bindAssignmentTriggers = (root) => root?.querySelectorAll("[data-registrant-assignment-open]").forEach((trigger) => {
        trigger.addEventListener("click", () => openAssignmentDialog(trigger));
    });
    bindAssignmentTriggers(document);
    assignmentDialog?.querySelectorAll("[data-registrant-assignment-close]").forEach((button) => {
        button.addEventListener("click", closeAssignmentDialog);
    });
    assignmentDialog?.addEventListener("click", (event) => {
        if (event.target === assignmentDialog) closeAssignmentDialog();
    });
    assignmentDialog?.addEventListener("cancel", (event) => {
        event.preventDefault();
        closeAssignmentDialog();
    });
    const closeResetDialog = () => {
        if (!resetDialog?.open) return;
        resetDialog.close();
        assignmentResetButton?.focus();
    };
    assignmentResetButton?.addEventListener("click", () => {
        if (!resetDialog || !resetForm || !currentAssignmentTrigger) return;
        resetForm.action = resetForm.dataset.actionTemplate.replace(
            /\/0\/satellite\/reset$/,
            `/${currentAssignmentTrigger.dataset.participantId}/satellite/reset`,
        );
        resetDialog.querySelector("[data-reset-participant]").textContent = currentAssignmentTrigger.dataset.participantName || "this registrant";
        resetDialog.showModal();
        requestAnimationFrame(() => resetDialog.querySelector("#registrant-satellite-reset-title").focus());
    });
    resetDialog?.querySelectorAll("[data-assignment-reset-close]").forEach((button) => {
        button.addEventListener("click", closeResetDialog);
    });
    resetDialog?.addEventListener("click", (event) => {
        if (event.target === resetDialog) closeResetDialog();
    });
    resetDialog?.addEventListener("cancel", (event) => {
        event.preventDefault();
        closeResetDialog();
    });
    const renderExplorerBreadcrumb = (state, registrantsOpen) => {
        explorerBreadcrumb.replaceChildren();
        const root = document.createElement("button");
        root.type = "button";
        root.textContent = "Hub Groups";
        root.addEventListener("click", () => closeDialog(explorer));
        explorerBreadcrumb.append(root);
        [state.groupName, state.hubName].forEach((label) => {
            const separator = document.createElement("span");
            separator.textContent = "/";
            separator.setAttribute("aria-hidden", "true");
            const crumb = document.createElement("span");
            crumb.textContent = label;
            explorerBreadcrumb.append(separator, crumb);
        });
        const separator = document.createElement("span");
        separator.textContent = "/";
        separator.setAttribute("aria-hidden", "true");
        if (!registrantsOpen) {
            const current = document.createElement("span");
            current.textContent = "Satellites";
            current.setAttribute("aria-current", "page");
            explorerBreadcrumb.append(separator, current);
            return;
        }
        const satellites = document.createElement("button");
        satellites.type = "button";
        satellites.textContent = "Satellites";
        satellites.addEventListener("click", () => showExplorerSatellites(state, false));
        explorerBreadcrumb.append(separator, satellites);
        [state.satelliteName, "Registrants"].forEach((label) => {
            const divider = document.createElement("span");
            divider.textContent = "/";
            divider.setAttribute("aria-hidden", "true");
            const crumb = document.createElement("span");
            crumb.textContent = label;
            explorerBreadcrumb.append(divider, crumb);
        });
    };
    const bindExplorerContent = (state) => {
        explorerContent.querySelectorAll("[data-settings-record-open]").forEach((trigger) => trigger.addEventListener("click", () => openCreateDialog(trigger)));
        explorerContent.querySelectorAll("[data-settings-edit-open]").forEach((trigger) => trigger.addEventListener("click", () => openEditDrawer(trigger)));
        explorerContent.querySelectorAll("[data-modal-view-registrants]").forEach((trigger) => trigger.addEventListener("click", () => loadDrilldown(explorerContent, {
            ...state,
            satelliteId: trigger.dataset.satelliteId,
            satelliteName: trigger.dataset.satelliteName,
            q: "",
            syncStatus: "all",
            page: 1,
        })));
    };
    const showExplorerSatellites = (state, moveFocus = true) => {
        const template = document.getElementById(state.templateId || `hub-satellites-${state.hubId}`);
        if (!template || !explorer) return;
        explorerContent.replaceChildren(template.content.cloneNode(true));
        explorerTitle.textContent = `${state.hubName} Satellites`;
        renderExplorerBreadcrumb(state, false);
        bindExplorerContent(state);
        if (!explorer.open) explorer.showModal();
        if (moveFocus) requestAnimationFrame(() => explorerTitle.focus());
    };
    const renderDrilldown = (panel, payload, state) => {
        panel.replaceChildren();
        const heading = document.createElement("div");
        heading.className = "satellite-explorer-heading";
        const headingText = document.createElement("div");
        const headingTitle = document.createElement("h3");
        headingTitle.textContent = state.satelliteName;
        const headingSummary = document.createElement("p");
        headingSummary.textContent = `${payload.pagination.total} ${payload.pagination.total === 1 ? "registrant" : "registrants"}`;
        headingText.append(headingTitle, headingSummary);
        heading.append(headingText);
        panel.append(heading);
        const controls = document.createElement("div");
        controls.className = "satellite-drilldown-controls";
        const searchInput = document.createElement("input");
        searchInput.type = "search";
        searchInput.placeholder = "Search participant or registration ID";
        searchInput.value = state.q;
        searchInput.setAttribute("aria-label", "Search registrants in this Satellite");
        const status = document.createElement("select");
        status.setAttribute("aria-label", "Filter registrants by sync status");
        [["all", "All statuses"], ["synced", "Synced"], ["manual_protected", "Manual Assignment — Protected"], ["needs_review", "Needs Review"], ["ready_to_sync", "Ready to Sync"]].forEach(([value, label]) => {
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
            ["Participant", "Registration", "Imported Satellite", "Effective Satellite", "Assignment Source", "Sync Status", "Action"].forEach((label) => headRow.append(makeCell(label, "th")));
            head.append(headRow);
            const body = document.createElement("tbody");
            payload.rows.forEach((row) => {
                const tr = document.createElement("tr");
                tr.append(
                    makeCell(row.participant),
                    makeCell(row.identifier),
                    makeLocationCell(row.imported_satellite, row.imported_hub),
                    makeLocationCell(row.effective_satellite, row.effective_hub),
                );
                const assignmentCell = document.createElement("td");
                const assignmentBadge = document.createElement("span");
                assignmentBadge.className = `satellite-assignment-source is-${row.assignment_source || "unassigned"}`;
                assignmentBadge.textContent = row.assignment_source_label;
                if (row.is_manual) assignmentBadge.title = "This manual assignment takes precedence over imported Satellite data.";
                assignmentCell.append(assignmentBadge);
                tr.append(assignmentCell);
                const statusCell = document.createElement("td");
                const badge = document.createElement("span");
                badge.className = `satellite-status is-${statusClass(row)}`;
                badge.textContent = row.status;
                statusCell.append(badge);
                tr.append(statusCell);
                const actionCell = document.createElement("td");
                if (row.attestation_participant_id) {
                    const edit = document.createElement("button");
                    edit.type = "button";
                    edit.className = "button secondary compact";
                    edit.textContent = "Edit Satellite";
                    edit.dataset.registrantAssignmentOpen = "";
                    edit.dataset.participantId = row.attestation_participant_id;
                    edit.dataset.participantName = row.participant;
                    edit.dataset.importedSatellite = row.imported_satellite;
                    edit.dataset.effectiveSatellite = row.effective_satellite;
                    edit.dataset.directoryId = row.satellite_id || "";
                    edit.dataset.isManual = row.is_manual ? "true" : "false";
                    edit.dataset.updatedBy = row.assignment_updated_by || "";
                    edit.dataset.updatedAt = row.assignment_updated_at || "";
                    edit.addEventListener("click", () => openAssignmentDialog(edit));
                    actionCell.append(edit);
                } else {
                    const unavailable = document.createElement("span");
                    unavailable.className = "satellite-unresolved";
                    unavailable.textContent = "Edit unavailable";
                    actionCell.append(unavailable);
                }
                tr.append(actionCell);
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
        panel.setAttribute("aria-busy", "true");
        panel.textContent = "Loading registrants…";
        explorerTitle.textContent = `${state.satelliteName} Registrants`;
        renderExplorerBreadcrumb(state, true);
        const url = new URL(directory.dataset.registrantsUrl, window.location.origin);
        url.searchParams.set("satellite_id", state.satelliteId);
        url.searchParams.set("search_scope", "registrant");
        url.searchParams.set("q", state.q || "");
        url.searchParams.set("sync_status", state.syncStatus || "all");
        url.searchParams.set("page", state.page || 1);
        url.searchParams.set("per_page", 10);
        try {
            const response = await fetch(url, {headers: {Accept: "application/json"}});
            if (!response.ok) throw new Error("Request failed");
            renderDrilldown(panel, await response.json(), state);
            requestAnimationFrame(() => explorerTitle.focus());
        } catch (_error) {
            panel.textContent = "Registrants could not be loaded. Try again.";
        } finally {
            panel.removeAttribute("aria-busy");
        }
    };
    document.querySelectorAll("[data-open-satellite-explorer]").forEach((trigger) => trigger.addEventListener("click", () => {
        returnFocus = trigger;
        showExplorerSatellites({
            templateId: trigger.dataset.templateId,
            groupName: trigger.dataset.groupName,
            hubName: trigger.dataset.hubName,
        });
    }));
    document.querySelectorAll("[data-open-registrants-from-search]").forEach((trigger) => trigger.addEventListener("click", () => {
        returnFocus = trigger;
        const state = {
            templateId: `hub-satellites-${trigger.dataset.hubId}`,
            hubId: trigger.dataset.hubId,
            groupName: trigger.dataset.groupName,
            hubName: trigger.dataset.hubName,
            satelliteId: trigger.dataset.satelliteId,
            satelliteName: trigger.dataset.satelliteName,
            q: "",
            syncStatus: "all",
            page: 1,
        };
        showExplorerSatellites(state, false);
        loadDrilldown(explorerContent, state);
    }));
    explorer?.querySelectorAll("[data-explorer-close]").forEach((button) => button.addEventListener("click", () => closeDialog(explorer)));
    explorer?.addEventListener("click", (event) => { if (event.target === explorer) closeDialog(explorer); });
    explorer?.addEventListener("cancel", (event) => { event.preventDefault(); closeDialog(explorer); });

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

    const targetSettings = document.querySelector("[data-target-category-settings]");
    if (targetSettings) {
        const targetRows = [...targetSettings.querySelectorAll("[data-target-option]")];
        const targetSearch = targetSettings.querySelector("[data-target-search]");
        const targetGroup = targetSettings.querySelector("[data-target-group]");
        const targetHub = targetSettings.querySelector("[data-target-hub]");
        const targetAvailability = targetSettings.querySelector("[data-target-availability]");
        const targetSelectVisible = targetSettings.querySelector("[data-target-select-visible]");
        const targetBulkCategory = targetSettings.querySelector("[data-target-bulk-category]");
        const targetVisibleCount = targetSettings.querySelector("[data-target-visible-count]");
        const targetEmpty = targetSettings.querySelector("[data-target-empty]");

        const updateTargetCounts = () => {
            const counts = new Map();
            targetSettings.querySelectorAll("[data-target-category-select]").forEach((select) => {
                const category = select.value.split(":", 2)[1];
                if (category) counts.set(category, (counts.get(category) || 0) + 1);
            });
            targetSettings.querySelectorAll("[data-target-selected-count]").forEach((element) => {
                element.textContent = String(counts.get(element.dataset.targetSelectedCount) || 0);
            });
        };

        const applyTargetFilters = () => {
            const query = targetSearch.value.trim().toLocaleLowerCase();
            const groupCode = targetGroup.value;
            [...targetHub.options].forEach((option, index) => {
                option.hidden = index > 0 && Boolean(groupCode) && option.dataset.groupCode !== groupCode;
            });
            if (targetHub.selectedOptions[0]?.hidden) targetHub.value = "";
            const hubId = targetHub.value;
            const availability = targetAvailability.value;
            let visible = 0;
            targetRows.forEach((row) => {
                const matches = (
                    (!query || row.dataset.searchText.includes(query))
                    && (!groupCode || row.dataset.groupCode === groupCode)
                    && (!hubId || row.dataset.hubId === hubId)
                    && (availability === "all" || (availability === "active") === (row.dataset.active === "true"))
                );
                row.hidden = !matches;
                if (!matches) row.querySelector("[data-target-row-check]").checked = false;
                if (matches) visible += 1;
            });
            targetSelectVisible.checked = false;
            targetSelectVisible.indeterminate = false;
            targetVisibleCount.textContent = `${visible} canonical ${visible === 1 ? "Satellite" : "Satellites"} visible`;
            if (targetEmpty) targetEmpty.hidden = visible !== 0;
        };

        targetSearch.addEventListener("input", applyTargetFilters);
        targetGroup.addEventListener("change", applyTargetFilters);
        targetHub.addEventListener("change", applyTargetFilters);
        targetAvailability.addEventListener("change", applyTargetFilters);
        targetSettings.querySelector("[data-target-clear-filters]").addEventListener("click", () => {
            targetSearch.value = "";
            targetGroup.value = "";
            targetHub.value = "";
            targetAvailability.value = "all";
            applyTargetFilters();
            targetSearch.focus();
        });
        targetSelectVisible.addEventListener("change", () => {
            targetRows.forEach((row) => {
                if (!row.hidden) row.querySelector("[data-target-row-check]").checked = targetSelectVisible.checked;
            });
        });
        targetSettings.querySelector("[data-target-apply-bulk]").addEventListener("click", () => {
            targetRows.forEach((row) => {
                const checkbox = row.querySelector("[data-target-row-check]");
                if (row.hidden || !checkbox.checked) return;
                const select = row.querySelector("[data-target-category-select]");
                select.value = `${select.dataset.directoryId}:${targetBulkCategory.value}`;
                checkbox.checked = false;
            });
            targetSelectVisible.checked = false;
            updateTargetCounts();
        });
        targetSettings.querySelectorAll("[data-target-category-select]").forEach((select) => {
            select.addEventListener("change", updateTargetCounts);
        });
        applyTargetFilters();
        updateTargetCounts();
    }

    applyFilters();
})();
