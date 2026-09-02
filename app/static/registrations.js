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
    const modalStatusChanged = modal.querySelector("[data-attestation-status-changed]");
    const previousButton = modal.querySelector("[data-attestation-previous]");
    const nextButton = modal.querySelector("[data-attestation-next]");
    const queuePosition = modal.querySelector("[data-attestation-position]");
    const previewViewer = modal.querySelector("[data-attestation-preview]");
    const previewState = modal.querySelector("[data-attestation-preview-state]");
    const previewUnavailable = modal.querySelector("[data-attestation-preview-unavailable]");
    const previewCanvas = modal.querySelector("[data-attestation-canvas]");
    const previewImage = modal.querySelector("[data-attestation-image]");
    const zoomOutButton = modal.querySelector("[data-attestation-zoom-out]");
    const zoomInButton = modal.querySelector("[data-attestation-zoom-in]");
    const fitWidthButton = modal.querySelector("[data-attestation-fit-width]");
    const fitPageButton = modal.querySelector("[data-attestation-fit-page]");
    const actualSizeButton = modal.querySelector("[data-attestation-actual-size]");
    const zoomLevel = modal.querySelector("[data-attestation-zoom-level]");
    const openOriginal = modal.querySelector("[data-attestation-original]");
    const unavailableOriginal = modal.querySelector("[data-attestation-unavailable-original]");
    const retryPreviewButton = modal.querySelector("[data-attestation-retry]");
    const canEditAttestation = root.dataset.canEditAttestation === "true";
    const remarksModal = document.querySelector("[data-remarks-modal]");
    const remarksDialog = remarksModal?.querySelector("[role='dialog']");
    const remarksCloseButton = remarksModal?.querySelector(".registrant-modal-close");
    const remarksName = remarksModal?.querySelector("[data-remarks-name]");
    const remarksForm = remarksModal?.querySelector("[data-remarks-form]");
    const remarksText = remarksModal?.querySelector("[data-remarks-text]");
    const remarksSave = remarksModal?.querySelector("[data-remarks-save]");
    const remarksCharacterCount = remarksModal?.querySelector("[data-remarks-character-count]");
    const remarksFeedback = remarksModal?.querySelector("[data-remarks-feedback]");
    const remarksLoading = remarksModal?.querySelector("[data-remarks-loading]");
    const remarksContent = remarksModal?.querySelector("[data-remarks-content]");
    const pendingRemarksList = remarksModal?.querySelector("[data-pending-remarks-list]");
    const resolvedRemarksList = remarksModal?.querySelector("[data-resolved-remarks-list]");
    const pendingRemarksEmpty = remarksModal?.querySelector("[data-pending-remarks-empty]");
    const resolvedRemarksEmpty = remarksModal?.querySelector("[data-resolved-remarks-empty]");
    const pendingRemarksCount = remarksModal?.querySelector("[data-pending-remarks-count]");
    const resolvedRemarksCount = remarksModal?.querySelector("[data-resolved-remarks-count]");
    const hasRemarksUi = Boolean(
        remarksModal && remarksDialog && remarksCloseButton && remarksName && remarksFeedback
        && remarksLoading && remarksContent && pendingRemarksList && resolvedRemarksList
        && pendingRemarksEmpty && resolvedRemarksEmpty && pendingRemarksCount && resolvedRemarksCount,
    );
    const canEditRemarks = root.dataset.canEditRemarks === "true";

    const columnGroupOrder = ["Attestation & Payment", "Registrant Details", "Logistics"];
    const groupPreferenceVersion = 1;
    const groupVisibility = Object.fromEntries(columnGroupOrder.map((group) => [group, true]));
    const allowedStatuses = ["pending", "verified", "invalid"];
    const statusLabels = {pending: "Pending", verified: "Verified", invalid: "Invalid"};
    const minimumZoom = 0.25;
    const maximumZoom = 3;
    const zoomStep = 0.25;
    const zoomPreferenceStorageKey = "ccf.attestationReview.zoom.v1";

    const loadZoomPreference = () => {
        try {
            const preference = JSON.parse(window.localStorage.getItem(zoomPreferenceStorageKey));
            if (preference?.mode === "manual" && Number.isFinite(preference.scale)) {
                return {
                    mode: "manual",
                    scale: Math.min(Math.max(preference.scale, minimumZoom), maximumZoom),
                };
            }
            if (["fit-width", "fit-page"].includes(preference?.mode)) {
                return {mode: preference.mode, scale: 1};
            }
            if (preference?.mode === "fit") return {mode: "fit-width", scale: 1};
        } catch (_error) {
            // Browser storage may be unavailable or contain an older invalid value.
        }
        return {mode: "fit-width", scale: 1};
    };

    const saveZoomPreference = (mode, scale) => {
        try {
            window.localStorage.setItem(
                zoomPreferenceStorageKey,
                JSON.stringify({mode, scale}),
            );
        } catch (_error) {
            // Keep the viewer usable when browser storage is unavailable.
        }
    };

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
    let zoomMode = "fit-width";
    let zoomScale = 1;
    let fitScale = 1;
    let zoomPreference = loadZoomPreference();
    let previewLoaded = false;
    let previewLoadTimer = null;
    let previewSourceUrl = null;
    let activeQueuePosition = -1;
    let queuePageNumber = 1;
    let queuePageRows = [];
    let queueRequestSession = 0;
    let filterReturnFocus = null;
    let activeRemarksRow = null;
    let remarksReturnFocus = null;
    let remarksMutationPending = false;
    let remarksRequestSession = 0;
    let actionsMenu = null;
    let actionsMenuTrigger = null;
    let actionsMenuRow = null;
    let actionsAttestationItem = null;
    let actionsRemarksItem = null;
    let actionsRemarksLabel = null;

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

    const visibleTableColumns = () => columns.filter((column) => (
        column.renderer !== "remarks" && groupVisibility[column.group] !== false
    ));

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
        if (!badge) return;
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
        const scale = ["fit-width", "fit-page"].includes(zoomMode) ? fitScale : zoomScale;
        zoomOutButton.disabled = !enabled || scale <= minimumZoom;
        zoomInButton.disabled = !enabled || scale >= maximumZoom;
        fitWidthButton.disabled = !enabled;
        fitPageButton.disabled = !enabled;
        actualSizeButton.disabled = !enabled;
        fitWidthButton.setAttribute("aria-pressed", String(enabled && zoomMode === "fit-width"));
        fitPageButton.setAttribute("aria-pressed", String(enabled && zoomMode === "fit-page"));
        actualSizeButton.setAttribute(
            "aria-pressed",
            String(enabled && zoomMode === "manual" && Math.abs(zoomScale - 1) < 0.001),
        );
    };

    const calculateFitScale = (mode) => {
        if (!previewImage.naturalWidth || !previewImage.naturalHeight) return 1;
        const availableWidth = Math.max(previewViewer.clientWidth - 32, 1);
        if (mode === "fit-width") {
            return Math.min(availableWidth / previewImage.naturalWidth, maximumZoom);
        }
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
        zoomLevel.value = `${Math.round(scale * 100)}%`;
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

    const fitDocumentToView = (mode = "fit-width", resetScroll = true) => {
        fitScale = calculateFitScale(mode);
        renderDocumentScale(fitScale, mode, resetScroll);
    };

    const setManualZoom = (scale, resetScroll = false, persist = true) => {
        const bounded = Math.min(Math.max(scale, minimumZoom), maximumZoom);
        renderDocumentScale(bounded, "manual", resetScroll);
        if (persist) {
            zoomPreference = {mode: "manual", scale: bounded};
            saveZoomPreference(zoomPreference.mode, zoomPreference.scale);
        }
    };

    const selectFitZoom = (mode) => {
        zoomPreference = {mode, scale: 1};
        saveZoomPreference(zoomPreference.mode, zoomPreference.scale);
        fitDocumentToView(mode, true);
    };

    const applyZoomPreference = () => {
        if (zoomPreference.mode === "manual") {
            setManualZoom(zoomPreference.scale, true, false);
            return;
        }
        fitDocumentToView(zoomPreference.mode, true);
    };

    const changeZoom = (direction) => {
        const current = ["fit-width", "fit-page"].includes(zoomMode) ? fitScale : zoomScale;
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
        unavailableOriginal.hidden = true;
        unavailableOriginal.removeAttribute("href");
        retryPreviewButton.hidden = true;
        previewSourceUrl = null;
        zoomMode = "fit-width";
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
        previewSourceUrl = url;
        openOriginal.href = url;
        openOriginal.hidden = false;
        unavailableOriginal.href = url;
        unavailableOriginal.hidden = false;
        retryPreviewButton.hidden = false;
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
                if (session === previewSession) applyZoomPreference();
            });
        };
        previewImage.onerror = () => showPreviewFailure(session);
        previewLoadTimer = window.setTimeout(() => showPreviewFailure(session), 15000);
        previewImage.src = url;
    };

    const retryPreview = () => {
        if (!activeRow || !previewSourceUrl) return;
        const name = [activeRow.first_name, activeRow.last_name].filter(Boolean).join(" ");
        const source = previewSourceUrl;
        const session = preparePreview(name);
        window.requestAnimationFrame(() => loadPreview(source, session));
    };

    const hasUnsavedModalChange = () => Boolean(
        canEditAttestation && activeRow && modalStatus
        && modalStatus.value !== normalizeStatus(activeRow.attestation_status)
    );

    const updateStatusEditor = () => {
        if (!modalStatus) return;
        const selected = normalizeStatus(modalStatus.value);
        const persisted = normalizeStatus(activeRow?.attestation_status);
        const changed = Boolean(activeRow && selected !== persisted);
        modalStatus.parentElement.dataset.status = selected;
        modalSave.disabled = savePending || !changed;
        modalStatusChanged.hidden = !changed;
        modalStatusChanged.textContent = changed ? `Changed from ${statusLabels[persisted]}` : "";
        updateQueueNavigation();
    };

    const updateQueueNavigation = () => {
        const total = Number(latestPayload?.pagination?.total || 0);
        const hasPosition = activeQueuePosition >= 0 && activeQueuePosition < total;
        queuePosition.value = hasPosition ? `${activeQueuePosition + 1} of ${total}` : "— of —";
        queuePosition.textContent = queuePosition.value;
        previousButton.disabled = savePending || !hasPosition || activeQueuePosition === 0;
        nextButton.disabled = savePending || !hasPosition || activeQueuePosition >= total - 1;
    };

    const registrationsQueryParams = (requestedPage = page) => {
        const params = new URLSearchParams({
            batch: batchSelect.value,
            search: search.value.trim(),
            page: String(requestedPage),
            per_page: pageSize.value,
            direction,
        });
        if (sort) params.set("sort", sort);
        if (filters.length) params.set("filters", JSON.stringify(filters));
        return params;
    };

    const showAttestationRow = (row, {focusNavigation = false} = {}) => {
        activeRow = row;
        const name = [row.first_name, row.last_name].filter(Boolean).join(" ");
        modalName.textContent = name || "Unnamed registrant";
        modalSatellite.textContent = displayValue(row.satellite);
        modalPayment.replaceChildren(paymentBadge(row.payment_status));
        setStatusBadge(modalCurrentStatus, row.attestation_status);
        if (modalStatus) modalStatus.value = normalizeStatus(row.attestation_status);
        setModalFeedback("");
        const session = preparePreview(name);
        updateStatusEditor();
        updateQueueNavigation();
        window.requestAnimationFrame(() => {
            if (focusNavigation) queuePosition.focus?.();
            window.requestAnimationFrame(() => loadPreview(row.attestation_form, session));
        });
    };

    const navigateAttestationQueue = (directionToMove) => {
        if (savePending || activeQueuePosition < 0) return;
        if (hasUnsavedModalChange()
            && !window.confirm("Discard the unsaved Attestation Status change?")) return;
        const targetPosition = activeQueuePosition + directionToMove;
        const total = Number(latestPayload?.pagination?.total || 0);
        if (targetPosition < 0 || targetPosition >= total) return;
        const perPage = Number.parseInt(pageSize.value, 10);
        const targetPage = Math.floor(targetPosition / perPage) + 1;
        const targetIndex = targetPosition % perPage;
        const applyTarget = (rows) => {
            const row = rows[targetIndex];
            if (!row) return;
            activeQueuePosition = targetPosition;
            showAttestationRow(row, {focusNavigation: true});
        };
        if (targetPage === queuePageNumber) {
            applyTarget(queuePageRows);
            return;
        }
        const currentRow = activeRow;
        const currentName = [currentRow.first_name, currentRow.last_name].filter(Boolean).join(" ");
        preparePreview(currentName);
        const requestSession = ++queueRequestSession;
        previousButton.disabled = true;
        nextButton.disabled = true;
        queuePosition.value = "Loading…";
        queuePosition.textContent = queuePosition.value;
        fetch(`${root.dataset.dataUrl}?${registrationsQueryParams(targetPage)}`, {
            credentials: "same-origin",
            headers: {Accept: "application/json"},
        })
            .then((response) => responsePayload(response, "The next registration could not be loaded."))
            .then((payload) => {
                if (requestSession !== queueRequestSession || modal.hidden) return;
                queuePageNumber = payload.pagination.page;
                queuePageRows = payload.rows;
                applyTarget(queuePageRows);
            })
            .catch((error) => {
                if (requestSession !== queueRequestSession || modal.hidden) return;
                showAttestationRow(currentRow);
                setModalFeedback(error.message || "The registration could not be loaded.", true);
                updateQueueNavigation();
            });
    };

    const closeAttestationModal = (force = false) => {
        if (modal.hidden || savePending) return false;
        if (!force && hasUnsavedModalChange() && !window.confirm("Discard the unsaved Attestation Status change?")) return false;
        modal.hidden = true;
        document.body.classList.remove("registrant-modal-open");
        resetPreview();
        queueRequestSession += 1;
        activeRow = null;
        activeQueuePosition = -1;
        queuePageRows = [];
        updateQueueNavigation();
        const focusTarget = returnFocus;
        returnFocus = null;
        if (focusTarget && typeof focusTarget.focus === "function") focusTarget.focus();
        return true;
    };

    const openAttestationModal = (row, trigger) => {
        returnFocus = trigger;
        queuePageNumber = Number(latestPayload?.pagination?.page || page);
        queuePageRows = latestPayload?.rows || [row];
        const rowIndex = queuePageRows.findIndex((item) => item.id === row.id);
        activeQueuePosition = Number(latestPayload?.pagination?.start || 1) - 1 + Math.max(rowIndex, 0);
        modal.hidden = false;
        document.body.classList.add("registrant-modal-open");
        showAttestationRow(row);
        window.requestAnimationFrame(() => {
            modalCloseButton.focus();
        });
    };

    const updateVisibleAttestationRow = (row) => {
        const visibleRow = latestPayload?.rows?.find((item) => item.id === row.id);
        if (visibleRow && visibleRow !== row) Object.assign(visibleRow, row);
        const tableRow = tableBody.querySelector(`tr[data-registration-id="${row.id}"]`);
        const statusCell = tableRow?.querySelector('[data-column-key="attestation_status"]');
        if (statusCell) {
            const badge = document.createElement("span");
            setStatusBadge(badge, row.attestation_status);
            statusCell.replaceChildren(badge);
        }
        ["last_reviewed_by", "last_reviewed_at"].forEach((key) => {
            const cell = tableRow?.querySelector(`[data-column-key="${key}"]`);
            if (cell) {
                cell.textContent = displayValue(row[key]);
                cell.title = displayValue(row[key]);
            }
        });
    };

    const refreshAttestationCounts = () => fetch(
        `${root.dataset.dataUrl}?${registrationsQueryParams(page)}`,
        {credentials: "same-origin", headers: {Accept: "application/json"}},
    )
        .then((response) => response.ok ? response.json() : Promise.reject())
        .then((payload) => renderSummary(payload.summary, payload.quick_filter_counts))
        .catch(() => {});

    const saveAttestationStatus = () => {
        if (!canEditAttestation || !activeRow || !modalStatus || !modalSave) return;
        const status = modalStatus.value;
        if (status === normalizeStatus(activeRow.attestation_status)) {
            updateStatusEditor();
            return;
        }
        const updateUrl = root.dataset.updateUrl.replace("/0/attestation", `/${activeRow.id}/attestation`);
        const params = new URLSearchParams({batch: batchSelect.value});
        savePending = true;
        modalStatus.disabled = true;
        modalSave.disabled = true;
        modalSave.textContent = "Saving…";
        setModalFeedback("Saving Attestation Status…");
        updateQueueNavigation();
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
                setStatusBadge(modalCurrentStatus, payload.status);
                updateVisibleAttestationRow(activeRow);
                showUpdateFeedback(`Attestation Status changed to ${payload.label}.`);
                setModalFeedback(`Attestation Status saved as ${payload.label}.`);
                refreshAttestationCounts();
            })
            .catch((error) => {
                setModalFeedback(error.message || "Attestation Status could not be updated.", true);
            })
            .finally(() => {
                savePending = false;
                modalStatus.disabled = false;
                modalSave.textContent = "Save Status";
                updateStatusEditor();
                updateQueueNavigation();
            });
    };

    const setRemarksFeedback = (message, isError = false) => {
        remarksFeedback.hidden = !message;
        remarksFeedback.textContent = message || "";
        remarksFeedback.classList.toggle("is-error", isError);
        remarksFeedback.setAttribute("role", isError ? "alert" : "status");
    };

    const remarksCollectionUrl = (row) => root.dataset.remarksUrl.replace(
        "/0/remarks", `/${row.id}/remarks`,
    );

    const remarksRequestUrl = (row, remarkId = null) => {
        const base = remarksCollectionUrl(row);
        const path = remarkId === null ? base : `${base}/${remarkId}`;
        return `${path}?${new URLSearchParams({batch: batchSelect.value})}`;
    };

    const responsePayload = (response, fallback) => response.json()
        .catch(() => ({}))
        .then((payload) => {
            if (!response.ok) throw new Error(payload.error || fallback);
            return payload;
        });

    const remarkMetadata = (label, user, timestamp) => {
        const metadata = document.createElement("p");
        metadata.className = "remark-metadata";
        metadata.textContent = `${label} ${user || "Former operator"} · ${displayValue(timestamp)}`;
        return metadata;
    };

    const resolveRemark = (remark, button) => {
        if (!canEditRemarks || !activeRemarksRow || remarksMutationPending) return;
        remarksMutationPending = true;
        button.disabled = true;
        button.textContent = "Resolving…";
        setRemarksFeedback("Resolving remark…");
        fetch(remarksRequestUrl(activeRemarksRow, remark.id), {
            method: "PATCH",
            credentials: "same-origin",
            headers: {
                Accept: "application/json",
                "Content-Type": "application/json",
                "X-CSRFToken": root.dataset.csrfToken,
            },
            body: JSON.stringify({status: "resolved"}),
        })
            .then((response) => responsePayload(response, "Remark could not be resolved."))
            .then(() => {
                setRemarksFeedback("Remark marked Resolved.");
                return loadRemarks(true);
            })
            .catch((error) => {
                setRemarksFeedback(error.message || "Remark could not be resolved.", true);
                button.disabled = false;
                button.textContent = "Mark Resolved";
            })
            .finally(() => { remarksMutationPending = false; });
    };

    const renderRemark = (remark) => {
        const article = document.createElement("article");
        article.className = `remark-card is-${remark.status}`;
        const text = document.createElement("p");
        text.className = "remark-text";
        text.textContent = remark.remark;
        article.append(text, remarkMetadata("Created by", remark.created_by, remark.created_at));
        if (remark.status === "resolved") {
            article.append(remarkMetadata("Resolved by", remark.resolved_by, remark.resolved_at));
        } else if (canEditRemarks) {
            const resolveButton = document.createElement("button");
            resolveButton.type = "button";
            resolveButton.className = "button secondary remark-resolve-button";
            resolveButton.textContent = "Mark Resolved";
            resolveButton.addEventListener("click", () => resolveRemark(remark, resolveButton));
            article.append(resolveButton);
        }
        return article;
    };

    const renderRemarks = (remarks) => {
        const pending = remarks.filter((remark) => remark.status === "pending");
        const resolved = remarks.filter((remark) => remark.status === "resolved");
        pendingRemarksList.replaceChildren(...pending.map(renderRemark));
        resolvedRemarksList.replaceChildren(...resolved.map(renderRemark));
        pendingRemarksCount.textContent = String(pending.length);
        resolvedRemarksCount.textContent = String(resolved.length);
        pendingRemarksEmpty.hidden = pending.length > 0;
        resolvedRemarksEmpty.hidden = resolved.length > 0;
        remarksLoading.hidden = true;
        remarksContent.hidden = false;
    };

    const loadRemarks = (refreshTable = false) => {
        if (!activeRemarksRow) return Promise.resolve();
        const row = activeRemarksRow;
        const session = ++remarksRequestSession;
        remarksLoading.hidden = false;
        remarksContent.hidden = true;
        return fetch(remarksRequestUrl(row), {
            credentials: "same-origin",
            headers: {Accept: "application/json"},
        })
            .then((response) => responsePayload(response, "Remarks could not be loaded."))
            .then((payload) => {
                if (session !== remarksRequestSession || row !== activeRemarksRow) return;
                renderRemarks(payload.remarks || []);
                if (refreshTable) loadData(false);
            })
            .catch((error) => {
                if (session !== remarksRequestSession || row !== activeRemarksRow) return;
                remarksLoading.hidden = true;
                remarksContent.hidden = true;
                setRemarksFeedback(error.message || "Remarks could not be loaded.", true);
            });
    };

    const closeRemarksModal = () => {
        if (remarksModal.hidden || remarksMutationPending) return false;
        remarksRequestSession += 1;
        remarksModal.hidden = true;
        document.body.classList.remove("registrant-modal-open");
        activeRemarksRow = null;
        if (remarksText) remarksText.value = "";
        if (remarksCharacterCount) remarksCharacterCount.textContent = "0";
        setRemarksFeedback("");
        const focusTarget = remarksReturnFocus;
        remarksReturnFocus = null;
        if (focusTarget && typeof focusTarget.focus === "function") focusTarget.focus();
        return true;
    };

    const openRemarksModal = (row, trigger) => {
        activeRemarksRow = row;
        remarksReturnFocus = trigger;
        remarksName.textContent = [row.first_name, row.last_name].filter(Boolean).join(" ") || "Unnamed registrant";
        if (remarksText) remarksText.value = "";
        if (remarksCharacterCount) remarksCharacterCount.textContent = "0";
        setRemarksFeedback("");
        remarksModal.hidden = false;
        document.body.classList.add("registrant-modal-open");
        window.requestAnimationFrame(() => remarksCloseButton.focus());
        loadRemarks();
    };

    const saveRemark = (event) => {
        event.preventDefault();
        if (!canEditRemarks || !activeRemarksRow || !remarksText || remarksMutationPending) return;
        const remark = remarksText.value.trim();
        if (!remark) {
            setRemarksFeedback("Enter a remark before saving.", true);
            remarksText.focus();
            return;
        }
        remarksMutationPending = true;
        remarksText.disabled = true;
        remarksSave.disabled = true;
        remarksSave.textContent = "Saving…";
        setRemarksFeedback("Saving remark…");
        fetch(remarksRequestUrl(activeRemarksRow), {
            method: "POST",
            credentials: "same-origin",
            headers: {
                Accept: "application/json",
                "Content-Type": "application/json",
                "X-CSRFToken": root.dataset.csrfToken,
            },
            body: JSON.stringify({remark}),
        })
            .then((response) => responsePayload(response, "Remark could not be saved."))
            .then(() => {
                remarksText.value = "";
                remarksCharacterCount.textContent = "0";
                setRemarksFeedback("Remark saved as Pending.");
                return loadRemarks(true);
            })
            .catch((error) => {
                setRemarksFeedback(error.message || "Remark could not be saved.", true);
            })
            .finally(() => {
                remarksMutationPending = false;
                remarksText.disabled = false;
                remarksSave.disabled = false;
                remarksSave.textContent = "Save Remark";
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

    const commentIcon = () => {
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("viewBox", "0 0 24 24");
        svg.setAttribute("fill", "none");
        svg.setAttribute("stroke", "currentColor");
        svg.setAttribute("stroke-width", "1.8");
        svg.setAttribute("stroke-linecap", "round");
        svg.setAttribute("stroke-linejoin", "round");
        svg.setAttribute("aria-hidden", "true");
        const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
        path.setAttribute("d", "M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4Z");
        svg.append(path);
        return svg;
    };

    const closeActionsMenu = (restoreFocus = false) => {
        if (!actionsMenu || actionsMenu.hidden) return;
        const trigger = actionsMenuTrigger;
        actionsMenu.hidden = true;
        actionsMenu.classList.remove("opens-upward");
        if (trigger) trigger.setAttribute("aria-expanded", "false");
        actionsMenuTrigger = null;
        actionsMenuRow = null;
        if (restoreFocus) trigger?.focus();
    };

    const positionActionsMenu = () => {
        if (!actionsMenu || actionsMenu.hidden || !actionsMenuTrigger) return;
        const triggerRect = actionsMenuTrigger.getBoundingClientRect();
        const menuRect = actionsMenu.getBoundingClientRect();
        const viewportGap = 8;
        const menuGap = 5;
        const spaceBelow = window.innerHeight - triggerRect.bottom;
        const opensUpward = spaceBelow < menuRect.height + menuGap + viewportGap
            && triggerRect.top > spaceBelow;
        const top = opensUpward
            ? triggerRect.top - menuRect.height - menuGap
            : triggerRect.bottom + menuGap;
        const left = Math.min(
            Math.max(viewportGap, triggerRect.right - menuRect.width),
            window.innerWidth - menuRect.width - viewportGap,
        );
        actionsMenu.style.top = `${Math.max(viewportGap, top)}px`;
        actionsMenu.style.left = `${left}px`;
        actionsMenu.classList.toggle("opens-upward", opensUpward);
    };

    const ensureActionsMenu = () => {
        if (actionsMenu) return;
        actionsMenu = document.createElement("div");
        actionsMenu.className = "registration-actions-menu";
        actionsMenu.setAttribute("role", "menu");
        actionsMenu.setAttribute("aria-label", "Registrant actions");
        actionsMenu.hidden = true;

        actionsAttestationItem = document.createElement("button");
        actionsAttestationItem.type = "button";
        actionsAttestationItem.setAttribute("role", "menuitem");
        const attestationLabel = document.createElement("span");
        attestationLabel.textContent = "Attestation Form";
        actionsAttestationItem.append(editIcon(), attestationLabel);

        actionsRemarksItem = document.createElement("button");
        actionsRemarksItem.type = "button";
        actionsRemarksItem.setAttribute("role", "menuitem");
        actionsRemarksLabel = document.createElement("span");
        actionsRemarksLabel.textContent = "Remarks";
        actionsRemarksItem.append(commentIcon(), actionsRemarksLabel);

        actionsAttestationItem.addEventListener("click", () => {
            const row = actionsMenuRow;
            const trigger = actionsMenuTrigger;
            closeActionsMenu();
            if (row && trigger) openAttestationModal(row, trigger);
        });
        actionsRemarksItem.addEventListener("click", () => {
            const row = actionsMenuRow;
            const trigger = actionsMenuTrigger;
            closeActionsMenu();
            if (row && trigger && hasRemarksUi) openRemarksModal(row, trigger);
        });
        actionsMenu.addEventListener("keydown", (event) => {
            const items = [actionsAttestationItem, actionsRemarksItem].filter((item) => !item.disabled);
            const index = items.indexOf(document.activeElement);
            if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
                event.preventDefault();
                const nextIndex = event.key === "Home" ? 0
                    : event.key === "End" ? items.length - 1
                        : (index + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
                items[nextIndex]?.focus();
            } else if (event.key === "Escape") {
                event.preventDefault();
                event.stopPropagation();
                closeActionsMenu(true);
            } else if (event.key === "Tab") {
                closeActionsMenu();
            }
        });
        actionsMenu.append(actionsAttestationItem, actionsRemarksItem);
        document.body.append(actionsMenu);
    };

    const openActionsMenu = (row, trigger, focusLast = false) => {
        ensureActionsMenu();
        if (actionsMenuTrigger === trigger && !actionsMenu.hidden) {
            closeActionsMenu(true);
            return;
        }
        closeActionsMenu();
        actionsMenuRow = row;
        actionsMenuTrigger = trigger;
        const pending = Number(row.pending_remark_count || 0);
        actionsRemarksLabel.textContent = pending ? `Remarks (${pending})` : "Remarks";
        actionsRemarksItem.disabled = !hasRemarksUi;
        actionsRemarksItem.title = hasRemarksUi ? "" : "Remarks are temporarily unavailable. Refresh the page.";
        trigger.setAttribute("aria-expanded", "true");
        actionsMenu.hidden = false;
        positionActionsMenu();
        const items = [actionsAttestationItem, actionsRemarksItem].filter((item) => !item.disabled);
        (focusLast ? items[items.length - 1] : items[0])?.focus();
    };

    const renderCellValue = (cell, value, column, row) => {
        if (column.renderer === "actions") {
            const button = document.createElement("button");
            const name = [row.first_name, row.last_name].filter(Boolean).join(" ") || "registrant";
            button.type = "button";
            button.className = "registration-actions-trigger";
            button.setAttribute("aria-haspopup", "menu");
            button.setAttribute("aria-expanded", "false");
            button.setAttribute("aria-label", `Actions for ${name}`);
            const label = document.createElement("span");
            label.textContent = "Actions";
            const chevron = document.createElement("span");
            chevron.className = "registration-actions-chevron";
            chevron.setAttribute("aria-hidden", "true");
            chevron.textContent = "▾";
            button.append(label, chevron);
            button.addEventListener("click", () => openActionsMenu(row, button));
            button.addEventListener("keydown", (event) => {
                if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                    event.preventDefault();
                    openActionsMenu(row, button, event.key === "ArrowUp");
                }
            });
            cell.classList.add("registration-actions-cell");
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
            if (column.renderer === "actions") th.classList.add("registration-actions-column");
            if (index < 3) th.classList.add("registration-sticky-column", `registration-sticky-${index + 1}`);
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
        closeActionsMenu();
        latestPayload = payload;
        const visibleColumns = visibleTableColumns();
        renderHeaders(visibleColumns);
        tableBody.replaceChildren();
        payload.rows.forEach((row) => {
            const tr = document.createElement("tr");
            tr.dataset.registrationId = String(row.id);
            if (Number(row.pending_remark_count || 0) > 0) {
                tr.classList.add("has-pending-remarks");
            }
            let previousGroup = null;
            visibleColumns.forEach((column, index) => {
                const td = document.createElement("td");
                td.dataset.columnKey = column.key;
                if (column.renderer === "actions") td.classList.add("registration-actions-column");
                if (index < 3) td.classList.add("registration-sticky-column", `registration-sticky-${index + 1}`);
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
        const params = registrationsQueryParams(page);
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
    fitWidthButton.addEventListener("click", () => selectFitZoom("fit-width"));
    fitPageButton.addEventListener("click", () => selectFitZoom("fit-page"));
    actualSizeButton.addEventListener("click", () => setManualZoom(1));
    retryPreviewButton.addEventListener("click", retryPreview);
    previousButton.addEventListener("click", () => navigateAttestationQueue(-1));
    nextButton.addEventListener("click", () => navigateAttestationQueue(1));
    modalSave?.addEventListener("click", saveAttestationStatus);
    modalStatus?.addEventListener("change", () => {
        setModalFeedback("");
        updateStatusEditor();
    });
    remarksModal?.querySelectorAll("[data-remarks-close]").forEach((control) => {
        control.addEventListener("click", closeRemarksModal);
    });
    remarksForm?.addEventListener("submit", saveRemark);
    remarksText?.addEventListener("input", () => {
        remarksCharacterCount.textContent = String(remarksText.value.length);
        setRemarksFeedback("");
    });

    if (typeof window.ResizeObserver === "function") {
        const viewerResizeObserver = new window.ResizeObserver(() => {
            if (!modal.hidden && previewLoaded && ["fit-width", "fit-page"].includes(zoomMode)) {
                window.requestAnimationFrame(() => fitDocumentToView(zoomMode, false));
            }
        });
        viewerResizeObserver.observe(previewViewer);
    } else {
        window.addEventListener("resize", () => {
            if (!modal.hidden && previewLoaded && ["fit-width", "fit-page"].includes(zoomMode)) {
                fitDocumentToView(zoomMode, false);
            }
        });
    }

    document.addEventListener("click", (event) => {
        if (actionsMenu && !actionsMenu.hidden
            && !actionsMenu.contains(event.target)
            && !event.target.closest(".registration-actions-trigger")) {
            closeActionsMenu();
        }
        if (!columnsMenu.hidden && !event.target.closest(".admin-column-control")) setColumnsMenuOpen(false);
    });
    document.addEventListener("keydown", (event) => {
        if (actionsMenu && !actionsMenu.hidden && event.key === "Escape") {
            event.preventDefault();
            closeActionsMenu(true);
            return;
        }
        if (hasRemarksUi && !remarksModal.hidden) {
            if (event.key === "Escape") {
                event.preventDefault();
                closeRemarksModal();
                return;
            }
            if (event.key !== "Tab") return;
            const focusable = [...remarksDialog.querySelectorAll(
                "button:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])",
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
    window.addEventListener("resize", () => closeActionsMenu());
    window.addEventListener("scroll", () => closeActionsMenu(), true);
    window.addEventListener("popstate", () => { readUrl(); loadData(false); });
})();
