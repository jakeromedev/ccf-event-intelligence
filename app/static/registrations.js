(() => {
    const root = document.querySelector("[data-registrations-table]");
    if (!root) return;

    const search = root.querySelector("[data-global-search]");
    const batchSelect = root.querySelector("[data-batch-select]");
    const pageSize = root.querySelector("[data-page-size]");
    const stateMessage = root.querySelector("[data-table-state]");
    const stateSkeleton = root.querySelector("[data-table-skeleton]");
    const stateTitle = root.querySelector("[data-table-state-title]");
    const stateDetail = root.querySelector("[data-table-state-detail]");
    const stateClear = root.querySelector("[data-table-clear]");
    const stateRetry = root.querySelector("[data-table-retry]");
    const tableWrap = root.querySelector("[data-table-wrap]");
    const tableHead = root.querySelector("[data-table-head]");
    const tableBody = root.querySelector("[data-table-body]");
    const tableFooter = root.querySelector("[data-table-footer]");
    const summary = root.querySelector("[data-table-summary]");
    const pagination = root.querySelector("[data-pagination]");
    const filterField = root.querySelector("[data-filter-field]");
    const filterOperator = root.querySelector("[data-filter-operator]");
    const valueLabel = root.querySelector(".admin-filter-value");
    const activeFilters = root.querySelector("[data-active-filters]");
    const filterChips = root.querySelector("[data-filter-chips]");
    const filterCount = root.querySelector("[data-filter-count]");
    const filterToggle = root.querySelector("[data-filter-toggle]");
    const filterDrawer = root.querySelector("[data-filter-drawer]");
    const filterDialog = filterDrawer.querySelector("[role='dialog']");
    const filterDraftList = root.querySelector("[data-filter-draft-list]");
    const filterDraftEmpty = root.querySelector("[data-filter-draft-empty]");
    const filterDraftCount = root.querySelector("[data-filter-draft-count]");
    const updateFeedback = root.querySelector("[data-update-feedback]");
    const columnsMenu = root.querySelector("[data-columns-menu]");
    const columnsToggle = root.querySelector("[data-columns-toggle]");
    const columnGroupControls = [...root.querySelectorAll("[data-column-group]")];
    const modal = document.querySelector("[data-attestation-modal]");
    const modalDialog = modal.querySelector("[role='dialog']");
    const modalCloseButton = modal.querySelector(".registrant-modal-close");
    const modalName = modal.querySelector("[data-attestation-name]");
    const modalSatellite = modal.querySelector("[data-attestation-satellite]");
    const modalPayment = modal.querySelector("[data-attestation-payment]");
    const modalCurrentStatus = modal.querySelector("[data-attestation-current-status]");
    const modalStatus = modal.querySelector("[data-attestation-status]");
    const modalSave = modal.querySelector("[data-attestation-save]");
    const modalFeedback = modal.querySelector("[data-attestation-feedback]");
    const previewViewer = modal.querySelector("[data-attestation-preview]");
    const previewState = modal.querySelector("[data-attestation-preview-state]");
    const previewUnavailable = modal.querySelector("[data-attestation-preview-unavailable]");
    const previewCanvas = modal.querySelector("[data-attestation-canvas]");
    const previewImage = modal.querySelector("[data-attestation-image]");
    const zoomOutButton = modal.querySelector("[data-attestation-zoom-out]");
    const zoomInButton = modal.querySelector("[data-attestation-zoom-in]");
    const fitButton = modal.querySelector("[data-attestation-fit]");
    const actualSizeButton = modal.querySelector("[data-attestation-actual-size]");
    const zoomLevel = modal.querySelector("[data-attestation-zoom-level]");
    const openOriginal = modal.querySelector("[data-attestation-original]");
    const canEditAttestation = root.dataset.canEditAttestation === "true";

    const columnGroupOrder = ["Attestation & Payment", "Registrant Details", "Logistics"];
    const groupPreferenceVersion = 1;
    const groupVisibility = Object.fromEntries(columnGroupOrder.map((group) => [group, true]));
    const allowedStatuses = ["pending", "verified", "invalid"];
    const statusLabels = {pending: "Pending", verified: "Verified", invalid: "Invalid"};
    const minimumZoom = 0.25;
    const maximumZoom = 3;
    const zoomStep = 0.25;

    let columns = [];
    let columnValues = {};
    let filters = [];
    let draftFilters = [];
    let page = 1;
    let sort = "";
    let direction = "asc";
    let defaultSort = "registration_code";
    let requestController = null;
    let searchTimer = null;
    let latestPayload = null;
    let activeRow = null;
    let returnFocus = null;
    let savePending = false;
    let previewSession = 0;
    let zoomMode = "fit";
    let zoomScale = 1;
    let fitScale = 1;
    let previewLoaded = false;
    let previewLoadTimer = null;
    let filterReturnFocus = null;

    const operatorLabels = {
        equals: "Equals", in: "Is Any Of", is_empty: "Is Empty",
        is_not_empty: "Is Not Empty",
    };

    const displayValue = (value) => value === null || value === undefined || value === ""
        ? "—"
        : String(value);

    const showTableState = ({title, detail = "", clear = false, retry = false, loading = false}) => {
        stateTitle.textContent = title;
        stateDetail.textContent = detail;
        stateDetail.hidden = !detail;
        stateClear.hidden = !clear;
        stateRetry.hidden = !retry;
        stateSkeleton.hidden = !loading;
        stateMessage.hidden = false;
    };

    const normalizeStatus = (value) => allowedStatuses.includes(value) ? value : "pending";

    const readUrl = () => {
        const params = new URLSearchParams(window.location.search);
        const requestedBatch = params.get("batch") || "active";
        batchSelect.value = [...batchSelect.options].some((option) => option.value === requestedBatch)
            ? requestedBatch
            : "active";
        search.value = params.get("search") || params.get("q") || "";
        page = Math.max(Number.parseInt(params.get("page") || "1", 10) || 1, 1);
        pageSize.value = ["25", "50", "100"].includes(params.get("per_page")) ? params.get("per_page") : "50";
        sort = params.get("sort") || "";
        direction = params.get("direction") === "desc" ? "desc" : "asc";
        const encodedFilters = params.get("filters");
        if (!encodedFilters) {
            filters = [];
            return;
        }
        try {
            const parsed = JSON.parse(encodedFilters);
            filters = Array.isArray(parsed) ? parsed : [];
        } catch (_error) {
            filters = [];
        }
    };

    const updateUrl = (mode = "replace") => {
        const params = new URLSearchParams(window.location.search);
        const values = {
            search: search.value.trim(),
            page: page > 1 ? String(page) : "",
            per_page: pageSize.value !== "50" ? pageSize.value : "",
            sort: sort && sort !== defaultSort ? sort : "",
            direction: sort && direction === "desc" ? "desc" : "",
            filters: filters.length ? JSON.stringify(filters) : "",
            batch: batchSelect.value === "active" ? "" : batchSelect.value,
        };
        Object.entries(values).forEach(([key, value]) => {
            if (value) params.set(key, value); else params.delete(key);
        });
        const nextUrl = `${window.location.pathname}${params.toString() ? `?${params}` : ""}`;
        const currentUrl = `${window.location.pathname}${window.location.search}`;
        if (nextUrl === currentUrl) return;
        const method = mode === "push" ? "pushState" : "replaceState";
        window.history[method]({}, "", nextUrl);
    };

    const loadGroupPreference = () => {
        try {
            const saved = JSON.parse(window.localStorage.getItem(root.dataset.columnPreferenceKey));
            if (!saved || saved.version !== groupPreferenceVersion || typeof saved.groups !== "object") return;
            columnGroupOrder.forEach((group) => {
                if (typeof saved.groups[group] === "boolean") groupVisibility[group] = saved.groups[group];
            });
        } catch (_error) {
            // Column visibility remains usable when local storage is unavailable.
        }
    };

    const saveGroupPreference = () => {
        try {
            window.localStorage.setItem(root.dataset.columnPreferenceKey, JSON.stringify({
                version: groupPreferenceVersion,
                groups: groupVisibility,
            }));
        } catch (_error) {
            // Column visibility remains usable when local storage is unavailable.
        }
    };

    const renderColumnGroupControls = () => {
        columnGroupControls.forEach((control) => {
            control.checked = groupVisibility[control.value] !== false;
        });
    };

    const visibleTableColumns = () => columns.filter((column) => groupVisibility[column.group] !== false);

    const setColumnsMenuOpen = (open) => {
        columnsMenu.hidden = !open;
        columnsToggle.setAttribute("aria-expanded", String(open));
        if (open) columnGroupControls[0]?.focus();
    };

    const filterableColumns = () => columns.filter((column) => column.filterable);

    const populateFilterFields = () => {
        const selected = filterField.value;
        filterField.replaceChildren();
        filterableColumns().forEach((column) => {
            const option = document.createElement("option");
            option.value = column.key;
            option.textContent = column.label;
            filterField.append(option);
        });
        if (filterableColumns().some((column) => column.key === selected)) filterField.value = selected;
        refreshFilterControls();
    };

    const refreshFilterControls = () => {
        const column = columns.find((item) => item.key === filterField.value);
        if (!column) return;
        filterOperator.replaceChildren();
        column.operators.forEach((operator) => {
            const option = document.createElement("option");
            option.value = operator;
            option.textContent = operatorLabels[operator] || operator;
            filterOperator.append(option);
        });
        refreshFilterValue();
    };

    const refreshFilterValue = () => {
        const noValue = ["is_empty", "is_not_empty"].includes(filterOperator.value);
        valueLabel.hidden = noValue;
        valueLabel.querySelectorAll("[data-filter-value], [data-filter-option-search]").forEach((item) => item.remove());
        if (noValue) return;
        const control = document.createElement("select");
        const options = columnValues[filterField.value] || [];
        if (filterOperator.value === "in") {
            control.multiple = true;
            control.size = Math.min(Math.max(options.length, 2), 5);
        }
        options.forEach((item) => {
            const option = document.createElement("option");
            option.value = item.value;
            option.textContent = item.label;
            control.append(option);
        });
        control.dataset.filterValue = "";
        if (filterField.value === "satellite" && options.length >= 8) {
            const optionSearch = document.createElement("input");
            optionSearch.type = "search";
            optionSearch.placeholder = "Search Satellite options";
            optionSearch.setAttribute("aria-label", "Search Satellite filter options");
            optionSearch.dataset.filterOptionSearch = "";
            optionSearch.addEventListener("input", () => {
                const query = optionSearch.value.trim().toLocaleLowerCase();
                [...control.options].forEach((option) => {
                    option.hidden = Boolean(query && !option.textContent.toLocaleLowerCase().includes(query));
                });
            });
            valueLabel.append(optionSearch);
        }
        valueLabel.append(control);
    };

    const cloneFilters = (items) => items.map((item) => ({
        ...item,
        value: Array.isArray(item.value) ? [...item.value] : item.value,
    }));

    const filterValueLabel = (filter) => {
        const values = Array.isArray(filter.value) ? filter.value : [filter.value];
        const options = columnValues[filter.field] || [];
        return values.map((value) => {
            const option = options.find((item) => String(item.value) === String(value));
            return option ? option.label : value;
        }).filter(Boolean).join(", ");
    };

    const filterDescription = (filter) => {
        const column = columns.find((item) => item.key === filter.field);
        const label = column ? column.label : filter.field;
        if (filter.operator === "is_empty") return `${label}: Is Empty`;
        if (filter.operator === "is_not_empty") return `${label}: Is Not Empty`;
        const value = filterValueLabel(filter);
        return `${label}: ${value}`;
    };

    const renderDraftFilters = () => {
        filterDraftList.replaceChildren();
        draftFilters.forEach((filter, index) => {
            const row = document.createElement("div");
            const description = document.createElement("span");
            description.textContent = filterDescription(filter);
            const remove = document.createElement("button");
            remove.type = "button";
            remove.setAttribute("aria-label", `Remove ${filterDescription(filter)} filter`);
            remove.textContent = "×";
            remove.addEventListener("click", () => {
                draftFilters.splice(index, 1);
                renderDraftFilters();
            });
            row.append(description, remove);
            filterDraftList.append(row);
        });
        filterDraftCount.textContent = String(draftFilters.length);
        filterDraftEmpty.hidden = draftFilters.length > 0;
    };

    const setFilterDrawerOpen = (open) => {
        filterDrawer.hidden = !open;
        filterToggle.setAttribute("aria-expanded", String(open));
        document.body.classList.toggle("registrations-filter-open", open);
        if (open) {
            filterReturnFocus = document.activeElement;
            draftFilters = cloneFilters(filters);
            renderDraftFilters();
            window.requestAnimationFrame(() => filterField.focus());
        } else {
            const focusTarget = filterReturnFocus;
            filterReturnFocus = null;
            if (focusTarget && typeof focusTarget.focus === "function") focusTarget.focus();
        }
    };

    const renderFilterChips = () => {
        filterChips.replaceChildren();
        filters.forEach((filter, index) => {
            const column = columns.find((item) => item.key === filter.field);
            if (!column) return;
            const chip = document.createElement("button");
            chip.type = "button";
            chip.textContent = `${filterDescription(filter)} ×`;
            chip.setAttribute("aria-label", `Remove ${filterDescription(filter)} filter`);
            chip.addEventListener("click", () => {
                filters.splice(index, 1);
                page = 1;
                loadData();
            });
            filterChips.append(chip);
        });
        activeFilters.hidden = filters.length === 0;
        filterCount.hidden = filters.length === 0;
        filterCount.textContent = String(filters.length);
        const statusFilters = filters.filter((item) => item.field === "attestation_status");
        const activeStatus = statusFilters.find((item) => item.operator === "equals");
        root.querySelectorAll("[data-attestation-quick]").forEach((button) => {
            const value = button.dataset.attestationQuick;
            const active = value === "all"
                ? statusFilters.length === 0
                : Boolean(activeStatus && activeStatus.value === value);
            button.classList.toggle("active", active);
            button.setAttribute("aria-pressed", String(active));
        });
    };

    const safeExternalUrl = (value) => {
        if (value === null || value === undefined) return null;
        const candidate = String(value).trim();
        if (!candidate) return null;
        try {
            const parsed = new URL(candidate);
            return ["http:", "https:"].includes(parsed.protocol) ? parsed.href : null;
        } catch (_error) {
            return null;
        }
    };

    const showUpdateFeedback = (message, isError = false) => {
        updateFeedback.hidden = !message;
        updateFeedback.textContent = message || "";
        updateFeedback.classList.toggle("is-error", isError);
    };

    const setModalFeedback = (message, isError = false) => {
        modalFeedback.hidden = !message;
        modalFeedback.textContent = message || "";
        modalFeedback.classList.toggle("is-error", isError);
    };

    const setStatusBadge = (badge, value) => {
        const status = normalizeStatus(value);
        badge.className = `registration-attestation-badge is-${status}`;
        badge.textContent = statusLabels[status];
    };

    const paymentBadge = (value) => {
        const badge = document.createElement("span");
        const normalized = displayValue(value).toLocaleLowerCase();
        badge.className = `registration-payment-badge${normalized.includes("validated") ? " is-validated" : normalized.includes("failed") || normalized.includes("cancel") ? " is-problem" : ""}`;
        badge.textContent = displayValue(value);
        return badge;
    };

    const setZoomControls = (enabled) => {
        const scale = zoomMode === "fit" ? fitScale : zoomScale;
        zoomOutButton.disabled = !enabled || scale <= minimumZoom;
        zoomInButton.disabled = !enabled || scale >= maximumZoom;
        fitButton.disabled = !enabled;
        actualSizeButton.disabled = !enabled;
        fitButton.setAttribute("aria-pressed", String(enabled && zoomMode === "fit"));
        actualSizeButton.setAttribute(
            "aria-pressed",
            String(enabled && zoomMode === "manual" && Math.abs(zoomScale - 1) < 0.001),
        );
    };

    const calculateFitScale = () => {
        if (!previewImage.naturalWidth || !previewImage.naturalHeight) return 1;
        const availableWidth = Math.max(previewViewer.clientWidth - 32, 1);
        const availableHeight = Math.max(previewViewer.clientHeight - 32, 1);
        return Math.min(
            availableWidth / previewImage.naturalWidth,
            availableHeight / previewImage.naturalHeight,
            1,
        );
    };

    const renderDocumentScale = (scale, mode, resetScroll = false) => {
        if (!previewLoaded || !previewImage.naturalWidth || !previewImage.naturalHeight) return;
        const oldWidth = Math.max(previewViewer.scrollWidth, 1);
        const oldHeight = Math.max(previewViewer.scrollHeight, 1);
        const centerX = (previewViewer.scrollLeft + previewViewer.clientWidth / 2) / oldWidth;
        const centerY = (previewViewer.scrollTop + previewViewer.clientHeight / 2) / oldHeight;
        const renderedWidth = Math.max(Math.round(previewImage.naturalWidth * scale), 1);
        const renderedHeight = Math.max(Math.round(previewImage.naturalHeight * scale), 1);
        const canvasWidth = Math.max(previewViewer.clientWidth, renderedWidth + 32);
        const canvasHeight = Math.max(previewViewer.clientHeight, renderedHeight + 32);

        zoomMode = mode;
        zoomScale = scale;
        previewCanvas.hidden = false;
        previewImage.hidden = false;
        previewImage.style.width = `${renderedWidth}px`;
        previewImage.style.height = "auto";
        previewCanvas.style.width = `${canvasWidth}px`;
        previewCanvas.style.height = `${canvasHeight}px`;
        previewImage.style.left = `${Math.max((canvasWidth - renderedWidth) / 2, 16)}px`;
        previewImage.style.top = `${Math.max((canvasHeight - renderedHeight) / 2, 16)}px`;
        zoomLevel.value = mode === "fit"
            ? `Fit · ${Math.round(scale * 100)}%`
            : `${Math.round(scale * 100)}%`;
        zoomLevel.textContent = zoomLevel.value;
        setZoomControls(true);

        if (resetScroll) {
            previewViewer.scrollLeft = 0;
            previewViewer.scrollTop = 0;
        } else {
            previewViewer.scrollLeft = centerX * previewViewer.scrollWidth - previewViewer.clientWidth / 2;
            previewViewer.scrollTop = centerY * previewViewer.scrollHeight - previewViewer.clientHeight / 2;
        }
    };

    const fitDocumentToView = (resetScroll = true) => {
        fitScale = calculateFitScale();
        renderDocumentScale(fitScale, "fit", resetScroll);
    };

    const setManualZoom = (scale) => {
        const bounded = Math.min(Math.max(scale, minimumZoom), maximumZoom);
        renderDocumentScale(bounded, "manual");
    };

    const changeZoom = (direction) => {
        const current = zoomMode === "fit" ? fitScale : zoomScale;
        const stepIndex = direction > 0
            ? Math.floor((current + 0.0001) / zoomStep) + 1
            : Math.ceil((current - 0.0001) / zoomStep) - 1;
        setManualZoom(stepIndex * zoomStep);
    };

    const resetPreview = () => {
        previewSession += 1;
        window.clearTimeout(previewLoadTimer);
        previewLoadTimer = null;
        previewImage.onload = null;
        previewImage.onerror = null;
        previewImage.removeAttribute("src");
        previewImage.removeAttribute("style");
        previewImage.hidden = true;
        previewCanvas.removeAttribute("style");
        previewCanvas.hidden = true;
        previewUnavailable.hidden = true;
        previewState.hidden = true;
        previewViewer.setAttribute("aria-busy", "false");
        previewViewer.scrollLeft = 0;
        previewViewer.scrollTop = 0;
        openOriginal.hidden = true;
        openOriginal.removeAttribute("href");
        zoomMode = "fit";
        zoomScale = 1;
        fitScale = 1;
        previewLoaded = false;
        zoomLevel.value = "—";
        zoomLevel.textContent = "—";
        setZoomControls(false);
        return previewSession;
    };

    const preparePreview = (registrantName) => {
        const session = resetPreview();
        previewImage.alt = `${registrantName || "Registrant"} submitted Attestation Form`;
        previewState.hidden = false;
        previewViewer.setAttribute("aria-busy", "true");
        return session;
    };

    const showPreviewFailure = (session) => {
        if (session !== previewSession) return;
        window.clearTimeout(previewLoadTimer);
        previewLoadTimer = null;
        previewImage.onload = null;
        previewImage.onerror = null;
        previewImage.removeAttribute("src");
        previewImage.hidden = true;
        previewCanvas.hidden = true;
        previewState.hidden = true;
        previewUnavailable.hidden = false;
        previewViewer.setAttribute("aria-busy", "false");
        previewLoaded = false;
        setZoomControls(false);
    };

    const loadPreview = (value, session) => {
        if (session !== previewSession) return;
        const url = safeExternalUrl(value);
        if (!url) {
            showPreviewFailure(session);
            return;
        }
        openOriginal.href = url;
        openOriginal.hidden = false;
        previewImage.onload = () => {
            if (session !== previewSession) return;
            window.clearTimeout(previewLoadTimer);
            previewLoadTimer = null;
            previewLoaded = true;
            previewState.hidden = true;
            previewUnavailable.hidden = true;
            previewCanvas.hidden = false;
            previewImage.hidden = false;
            previewViewer.setAttribute("aria-busy", "false");
            window.requestAnimationFrame(() => {
                if (session === previewSession) fitDocumentToView(true);
            });
        };
        previewImage.onerror = () => showPreviewFailure(session);
        previewLoadTimer = window.setTimeout(() => showPreviewFailure(session), 15000);
        previewImage.src = url;
    };

    const hasUnsavedModalChange = () => Boolean(
        canEditAttestation && activeRow && modalStatus
        && modalStatus.value !== normalizeStatus(activeRow.attestation_status)
    );

    const closeAttestationModal = (force = false) => {
        if (modal.hidden || savePending) return false;
        if (!force && hasUnsavedModalChange() && !window.confirm("Discard the unsaved Attestation Status change?")) return false;
        modal.hidden = true;
        document.body.classList.remove("registrant-modal-open");
        resetPreview();
        activeRow = null;
        const focusTarget = returnFocus;
        returnFocus = null;
        if (focusTarget && typeof focusTarget.focus === "function") focusTarget.focus();
        return true;
    };

    const openAttestationModal = (row, trigger) => {
        activeRow = row;
        returnFocus = trigger;
        const name = [row.first_name, row.last_name].filter(Boolean).join(" ");
        modalName.textContent = name || "Unnamed registrant";
        modalSatellite.textContent = displayValue(row.satellite);
        modalPayment.replaceChildren(paymentBadge(row.payment_status));
        setStatusBadge(modalCurrentStatus, row.attestation_status);
        if (modalStatus) modalStatus.value = normalizeStatus(row.attestation_status);
        setModalFeedback("");
        const session = preparePreview(name);
        modal.hidden = false;
        document.body.classList.add("registrant-modal-open");
        window.requestAnimationFrame(() => {
            modalCloseButton.focus();
            window.requestAnimationFrame(() => loadPreview(row.attestation_form, session));
        });
    };

    const saveAttestationStatus = () => {
        if (!canEditAttestation || !activeRow || !modalStatus || !modalSave) return;
        const status = modalStatus.value;
        if (status === normalizeStatus(activeRow.attestation_status)) {
            closeAttestationModal(true);
            return;
        }
        const updateUrl = root.dataset.updateUrl.replace("/0/attestation", `/${activeRow.id}/attestation`);
        const params = new URLSearchParams({batch: batchSelect.value});
        savePending = true;
        modalStatus.disabled = true;
        modalSave.disabled = true;
        modalSave.textContent = "Saving…";
        setModalFeedback("Saving Attestation Status…");
        fetch(`${updateUrl}?${params}`, {
            method: "PATCH",
            credentials: "same-origin",
            headers: {
                Accept: "application/json",
                "Content-Type": "application/json",
                "X-CSRFToken": root.dataset.csrfToken,
            },
            body: JSON.stringify({status}),
        })
            .then((response) => response.ok
                ? response.json()
                : response.json().catch(() => ({})).then((payload) => Promise.reject(
                    new Error(payload.error || "Attestation Status could not be updated."),
                )))
            .then((payload) => {
                activeRow.attestation_status = payload.status;
                activeRow.last_reviewed_by = payload.updated_by;
                activeRow.last_reviewed_at = payload.updated_at;
                showUpdateFeedback(`Attestation Status changed to ${payload.label}.`);
                savePending = false;
                closeAttestationModal(true);
                loadData();
            })
            .catch((error) => {
                setModalFeedback(error.message || "Attestation Status could not be updated.", true);
            })
            .finally(() => {
                savePending = false;
                modalStatus.disabled = false;
                modalSave.disabled = false;
                modalSave.textContent = "Save Status";
            });
    };

    const editIcon = () => {
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("viewBox", "0 0 24 24");
        svg.setAttribute("width", "14");
        svg.setAttribute("height", "14");
        svg.setAttribute("fill", "none");
        svg.setAttribute("stroke", "currentColor");
        svg.setAttribute("stroke-width", "1.8");
        svg.setAttribute("stroke-linecap", "round");
        svg.setAttribute("stroke-linejoin", "round");
        svg.setAttribute("aria-hidden", "true");
        const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
        path.setAttribute("d", "M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4Z");
        svg.append(path);
        return svg;
    };

    const renderCellValue = (cell, value, column, row) => {
        if (column.renderer === "attestation_review") {
            const button = document.createElement("button");
            const name = [row.first_name, row.last_name].filter(Boolean).join(" ") || "registrant";
            button.type = "button";
            button.className = "registration-form-button";
            button.setAttribute("aria-haspopup", "dialog");
            button.setAttribute("aria-label", `Review Attestation Form for ${name}`);
            const label = document.createElement("span");
            label.textContent = "Attestation Form";
            button.append(label, editIcon());
            button.addEventListener("click", () => openAttestationModal(row, button));
            cell.append(button);
            return;
        }
        if (column.renderer === "attestation_status") {
            const badge = document.createElement("span");
            setStatusBadge(badge, value);
            cell.append(badge);
            return;
        }
        if (column.renderer === "payment_status") {
            cell.append(paymentBadge(value));
            return;
        }
        const displayed = displayValue(value);
        cell.textContent = displayed;
        cell.title = displayed;
    };

    const renderHeaders = (visibleColumns) => {
        tableHead.replaceChildren();
        const headerRow = document.createElement("tr");
        let previousGroup = null;
        visibleColumns.forEach((column, index) => {
            const th = document.createElement("th");
            th.scope = "col";
            if (index === 0) th.classList.add("sticky-key");
            if (previousGroup !== null && previousGroup !== column.group) th.classList.add("registration-group-start");
            if (column.sortable) {
                const activeSort = sort === column.key;
                th.setAttribute("aria-sort", activeSort ? (direction === "asc" ? "ascending" : "descending") : "none");
                const button = document.createElement("button");
                button.type = "button";
                button.textContent = column.label;
                button.setAttribute(
                    "aria-label",
                    activeSort
                        ? `Sort by ${column.label}, currently ${direction === "asc" ? "ascending" : "descending"}`
                        : `Sort by ${column.label}`,
                );
                const indicator = document.createElement("span");
                indicator.textContent = sort === column.key ? (direction === "asc" ? " ↑" : " ↓") : " ↕";
                indicator.setAttribute("aria-hidden", "true");
                button.append(indicator);
                button.addEventListener("click", () => {
                    if (sort === column.key) direction = direction === "asc" ? "desc" : "asc";
                    else { sort = column.key; direction = "asc"; }
                    page = 1;
                    loadData();
                });
                th.append(button);
            } else {
                const label = document.createElement("span");
                label.className = "registration-column-label";
                label.textContent = column.label;
                th.append(label);
            }
            headerRow.append(th);
            previousGroup = column.group;
        });
        tableHead.append(headerRow);
    };

    const renderTable = (payload) => {
        latestPayload = payload;
        const visibleColumns = visibleTableColumns();
        renderHeaders(visibleColumns);
        tableBody.replaceChildren();
        payload.rows.forEach((row) => {
            const tr = document.createElement("tr");
            let previousGroup = null;
            visibleColumns.forEach((column, index) => {
                const td = document.createElement("td");
                if (index === 0) td.classList.add("sticky-key");
                if (previousGroup !== null && previousGroup !== column.group) td.classList.add("registration-group-start");
                renderCellValue(td, row[column.key], column, row);
                tr.append(td);
                previousGroup = column.group;
            });
            tableBody.append(tr);
        });

        const info = payload.pagination;
        summary.textContent = `Showing ${info.start.toLocaleString()}–${info.end.toLocaleString()} of ${info.total.toLocaleString()} registrations`;
        pagination.replaceChildren();
        const makePageButton = (label, target, disabled = false, current = false) => {
            const button = document.createElement("button");
            button.type = "button";
            button.textContent = label;
            button.disabled = disabled;
            const pageLabel = /^\d+$/.test(label) ? `Page ${label}` : `${label} page`;
            button.setAttribute("aria-label", current ? `${pageLabel}, current page` : pageLabel);
            if (current) {
                button.className = "current";
                button.setAttribute("aria-current", "page");
            }
            button.addEventListener("click", () => { page = target; loadData(); });
            return button;
        };
        pagination.append(makePageButton("Previous", info.page - 1, !info.has_previous));
        const startPage = Math.max(1, Math.min(info.page - 2, info.pages - 4));
        const endPage = Math.min(info.pages, startPage + 4);
        for (let number = startPage; number <= endPage; number += 1) {
            pagination.append(makePageButton(String(number), number, number === info.page, number === info.page));
        }
        pagination.append(makePageButton("Next", info.page + 1, !info.has_next));

        const hasRows = payload.rows.length > 0;
        const hasVisibleColumns = visibleColumns.length > 0;
        tableWrap.setAttribute("aria-busy", "false");
        tableWrap.querySelector("table").setAttribute("aria-rowcount", String(info.total + 1));
        tableWrap.hidden = !hasRows || !hasVisibleColumns;
        tableFooter.hidden = !hasRows;
        stateMessage.hidden = hasRows && hasVisibleColumns;
        if (hasRows && !hasVisibleColumns) {
            showTableState({
                title: "All column groups are hidden.",
                detail: "Use Columns to show at least one group.",
            });
        } else if (!hasRows) {
            const hasQuery = Boolean(filters.length || search.value.trim());
            const noActiveBatch = batchSelect.value === "active" && root.dataset.hasActiveBatch === "false";
            if (hasQuery) {
                showTableState({
                    title: "No registrations match your current search and filters.",
                    detail: "Clear the search and filters to return to all registrations in this Batch.",
                    clear: true,
                });
            } else if (noActiveBatch) {
                showTableState({
                    title: "No active batch is available for this Event.",
                    detail: "Select a specific batch or All Batches to review historical registrations.",
                });
            } else {
                showTableState({
                    title: "No registrations found for this batch.",
                    detail: "Registration records will appear here after a batch is imported.",
                });
            }
        }
        renderFilterChips();
    };

    const renderSummary = (values, quickFilterCounts) => {
        root.querySelectorAll("[data-summary]").forEach((element) => {
            const value = values && values[element.dataset.summary];
            element.textContent = Number(value || 0).toLocaleString();
        });
        root.querySelectorAll("[data-attestation-quick-count]").forEach((element) => {
            const value = quickFilterCounts && quickFilterCounts[element.dataset.attestationQuickCount];
            element.textContent = Number(value || 0).toLocaleString();
        });
    };

    const loadData = (syncUrl = true) => {
        if (syncUrl) updateUrl("push");
        if (requestController) requestController.abort();
        const controller = new AbortController();
        requestController = controller;
        root.classList.add("loading");
        root.setAttribute("aria-busy", "true");
        tableWrap.setAttribute("aria-busy", "true");
        if (!latestPayload || tableWrap.hidden) {
            showTableState({
                title: "Loading registrations…",
                detail: "Preparing the selected Event and Batch.",
                loading: true,
            });
        }
        const params = new URLSearchParams({
            batch: batchSelect.value,
            search: search.value.trim(),
            page: String(page),
            per_page: pageSize.value,
            direction,
        });
        if (sort) params.set("sort", sort);
        if (filters.length) params.set("filters", JSON.stringify(filters));
        return fetch(`${root.dataset.dataUrl}?${params}`, {
            headers: {Accept: "application/json"}, signal: controller.signal,
        })
            .then((response) => response.ok ? response.json() : response.json().then((payload) => Promise.reject(new Error(payload.error || "Registrations could not be loaded."))))
            .then((payload) => {
                const changed = columns.map((item) => item.key).join() !== payload.columns.map((item) => item.key).join();
                columns = payload.columns;
                columnValues = payload.column_options || {};
                sort = payload.query.sort;
                direction = payload.query.direction;
                defaultSort = payload.query.default_sort;
                page = payload.pagination.page;
                if (changed) populateFilterFields(); else refreshFilterControls();
                renderSummary(payload.summary, payload.quick_filter_counts);
                renderTable(payload);
                updateUrl("replace");
            })
            .catch((error) => {
                if (error.name === "AbortError") return;
                showTableState({
                    title: "Registrations could not be loaded.",
                    detail: "Check your connection and try again.",
                    retry: true,
                });
                tableWrap.hidden = true;
                tableFooter.hidden = true;
            })
            .finally(() => {
                if (requestController !== controller) return;
                root.classList.remove("loading");
                root.setAttribute("aria-busy", "false");
                tableWrap.setAttribute("aria-busy", "false");
            });
    };

    loadGroupPreference();
    renderColumnGroupControls();
    readUrl();
    loadData(false);

    search.addEventListener("input", () => {
        window.clearTimeout(searchTimer);
        searchTimer = window.setTimeout(() => { page = 1; loadData(); }, 300);
    });
    batchSelect.addEventListener("change", () => { page = 1; loadData(); });
    pageSize.addEventListener("change", () => { page = 1; loadData(); });
    stateRetry.addEventListener("click", () => loadData(false));
    stateClear.addEventListener("click", () => {
        window.clearTimeout(searchTimer);
        search.value = "";
        filters = [];
        draftFilters = [];
        page = 1;
        loadData();
        search.focus();
    });
    filterField.addEventListener("change", refreshFilterControls);
    filterOperator.addEventListener("change", refreshFilterValue);
    filterToggle.addEventListener("click", () => setFilterDrawerOpen(true));
    filterDrawer.querySelectorAll("[data-filter-close]").forEach((control) => {
        control.addEventListener("click", () => setFilterDrawerOpen(false));
    });
    root.querySelector("[data-add-filter]").addEventListener("click", () => {
        const valueControl = valueLabel.querySelector("[data-filter-value]");
        const operator = filterOperator.value;
        const value = ["is_empty", "is_not_empty"].includes(operator) ? "" : valueControl && valueControl.multiple
            ? [...valueControl.selectedOptions].map((option) => option.value)
            : (valueControl ? valueControl.value : "");
        if (!["is_empty", "is_not_empty"].includes(operator) && (!value || (Array.isArray(value) && !value.length))) return;
        draftFilters.push({field: filterField.value, operator, value});
        renderDraftFilters();
    });
    root.querySelector("[data-clear-filters]").addEventListener("click", () => { filters = []; page = 1; loadData(); });
    root.querySelector("[data-clear-filter-draft]").addEventListener("click", () => {
        draftFilters = [];
        renderDraftFilters();
    });
    root.querySelector("[data-apply-filters]").addEventListener("click", () => {
        filters = cloneFilters(draftFilters);
        page = 1;
        setFilterDrawerOpen(false);
        loadData();
    });
    root.querySelector("[data-reset-view]").addEventListener("click", () => {
        window.clearTimeout(searchTimer);
        search.value = "";
        batchSelect.value = "active";
        pageSize.value = "50";
        filters = [];
        draftFilters = [];
        sort = defaultSort;
        direction = "asc";
        page = 1;
        if (!filterDrawer.hidden) setFilterDrawerOpen(false);
        loadData();
    });
    root.querySelectorAll("[data-attestation-quick]").forEach((button) => {
        button.addEventListener("click", () => {
            filters = filters.filter((item) => item.field !== "attestation_status");
            if (button.dataset.attestationQuick !== "all") {
                filters.push({field: "attestation_status", operator: "equals", value: button.dataset.attestationQuick});
            }
            page = 1;
            loadData();
        });
    });

    columnsToggle.addEventListener("click", () => setColumnsMenuOpen(columnsMenu.hidden));
    root.querySelector("[data-columns-close]").addEventListener("click", () => {
        setColumnsMenuOpen(false);
        columnsToggle.focus();
    });
    columnGroupControls.forEach((control) => {
        control.addEventListener("change", () => {
            groupVisibility[control.value] = control.checked;
            saveGroupPreference();
            if (latestPayload) renderTable(latestPayload);
        });
    });
    root.querySelector("[data-reset-column-groups]").addEventListener("click", () => {
        columnGroupOrder.forEach((group) => { groupVisibility[group] = true; });
        saveGroupPreference();
        renderColumnGroupControls();
        if (latestPayload) renderTable(latestPayload);
    });

    modal.querySelectorAll("[data-attestation-close]").forEach((control) => {
        control.addEventListener("click", () => closeAttestationModal());
    });
    zoomOutButton.addEventListener("click", () => changeZoom(-1));
    zoomInButton.addEventListener("click", () => changeZoom(1));
    fitButton.addEventListener("click", () => fitDocumentToView(true));
    actualSizeButton.addEventListener("click", () => setManualZoom(1));
    modalSave?.addEventListener("click", saveAttestationStatus);
    modalStatus?.addEventListener("change", () => setModalFeedback(""));

    if (typeof window.ResizeObserver === "function") {
        const viewerResizeObserver = new window.ResizeObserver(() => {
            if (!modal.hidden && previewLoaded && zoomMode === "fit") {
                window.requestAnimationFrame(() => fitDocumentToView(false));
            }
        });
        viewerResizeObserver.observe(previewViewer);
    } else {
        window.addEventListener("resize", () => {
            if (!modal.hidden && previewLoaded && zoomMode === "fit") fitDocumentToView(false);
        });
    }

    document.addEventListener("click", (event) => {
        if (!columnsMenu.hidden && !event.target.closest(".admin-column-control")) setColumnsMenuOpen(false);
    });
    document.addEventListener("keydown", (event) => {
        if (!modal.hidden) {
            if (event.key === "Escape") {
                event.preventDefault();
                closeAttestationModal();
                return;
            }
            if (event.key !== "Tab") return;
            const focusable = [...modalDialog.querySelectorAll(
                "a[href], button:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex='-1'])",
            )].filter((element) => !element.hidden);
            if (!focusable.length) return;
            const first = focusable[0];
            const last = focusable[focusable.length - 1];
            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus();
            }
            return;
        }
        if (!filterDrawer.hidden) {
            if (event.key === "Escape") {
                event.preventDefault();
                setFilterDrawerOpen(false);
                return;
            }
            if (event.key !== "Tab") return;
            const focusable = [...filterDialog.querySelectorAll(
                "button:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex='-1'])",
            )].filter((element) => !element.hidden);
            if (!focusable.length) return;
            const first = focusable[0];
            const last = focusable[focusable.length - 1];
            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus();
            }
            return;
        }
        if (event.key === "Escape" && !columnsMenu.hidden) {
            setColumnsMenuOpen(false);
            columnsToggle.focus();
        }
    });
    window.addEventListener("popstate", () => { readUrl(); loadData(false); });
})();
