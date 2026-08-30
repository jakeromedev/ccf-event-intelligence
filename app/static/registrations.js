(() => {
    const root = document.querySelector("[data-registrations-table]");
    if (!root) return;

    const search = root.querySelector("[data-global-search]");
    const batchSelect = root.querySelector("[data-batch-select]");
    const pageSize = root.querySelector("[data-page-size]");
    const stateMessage = root.querySelector("[data-table-state]");
    const tableWrap = root.querySelector("[data-table-wrap]");
    const tableHead = root.querySelector("[data-table-head]");
    const tableBody = root.querySelector("[data-table-body]");
    const tableFooter = root.querySelector("[data-table-footer]");
    const summary = root.querySelector("[data-table-summary]");
    const pagination = root.querySelector("[data-pagination]");
    const filterBuilder = root.querySelector("[data-filter-builder]");
    const filterField = root.querySelector("[data-filter-field]");
    const filterOperator = root.querySelector("[data-filter-operator]");
    const valueLabel = root.querySelector(".admin-filter-value");
    const activeFilters = root.querySelector("[data-active-filters]");
    const filterChips = root.querySelector("[data-filter-chips]");
    const filterCount = root.querySelector("[data-filter-count]");
    const updateFeedback = root.querySelector("[data-update-feedback]");
    const canEditAttestation = root.dataset.canEditAttestation === "true";

    let columns = [];
    let columnValues = {};
    let filters = [];
    let page = 1;
    let sort = "";
    let direction = "asc";
    let defaultSort = "registration_code";
    let requestController = null;
    let searchTimer = null;

    const operatorLabels = {
        equals: "Equals", in: "Is Any Of", is_empty: "Is Empty",
        is_not_empty: "Is Not Empty",
    };

    const readUrl = () => {
        const params = new URLSearchParams(window.location.search);
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

    const updateUrl = () => {
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
        window.history.replaceState({}, "", `${window.location.pathname}${params.toString() ? `?${params}` : ""}`);
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
        if (filterableColumns().some((column) => column.key === selected)) {
            filterField.value = selected;
        }
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
        if (noValue) return;
        const previous = valueLabel.querySelector("input, select");
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
        if (previous) previous.replaceWith(control); else valueLabel.append(control);
    };

    const renderFilterChips = () => {
        filterChips.replaceChildren();
        filters.forEach((filter, index) => {
            const column = columns.find((item) => item.key === filter.field);
            if (!column) return;
            const displayValue = Array.isArray(filter.value) ? filter.value.join(", ") : filter.value;
            const chip = document.createElement("button");
            chip.type = "button";
            chip.textContent = `${column.label}: ${operatorLabels[filter.operator] || filter.operator}${displayValue ? ` ${displayValue}` : ""} ×`;
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
            button.classList.toggle(
                "active",
                value === "all" ? statusFilters.length === 0 : activeStatus && activeStatus.value === value,
            );
            button.setAttribute(
                "aria-pressed",
                String(value === "all" ? statusFilters.length === 0 : Boolean(activeStatus && activeStatus.value === value)),
            );
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

    const saveAttestationStatus = (select, row) => {
        const previous = select.dataset.previousValue;
        const status = select.value;
        const updateUrl = root.dataset.updateUrl.replace(
            "/0/attestation", `/${row.id}/attestation`,
        );
        const params = new URLSearchParams({batch: batchSelect.value});
        select.disabled = true;
        select.classList.add("is-saving");
        showUpdateFeedback("Saving attestation status…");
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
                    new Error(payload.error || "Attestation status could not be updated."),
                )))
            .then((payload) => {
                select.dataset.previousValue = payload.status;
                showUpdateFeedback(`Attestation status changed to ${payload.label}.`);
                loadData();
            })
            .catch((error) => {
                select.value = previous;
                showUpdateFeedback(error.message || "Attestation status could not be updated.", true);
            })
            .finally(() => {
                select.disabled = false;
                select.classList.remove("is-saving");
            });
    };

    const renderCellValue = (cell, value, column, row) => {
        if (column.renderer === "attestation_form_link") {
            const url = safeExternalUrl(value);
            if (!url) {
                cell.textContent = "—";
                return;
            }
            const link = document.createElement("a");
            link.className = "registration-form-link";
            link.href = url;
            link.target = "_blank";
            link.rel = "noopener noreferrer";
            link.textContent = "View Form";
            link.setAttribute("aria-label", "View Attestation Form (opens in a new tab)");
            cell.append(link);
            return;
        }
        if (column.renderer === "attestation_status") {
            const status = ["pending", "verified", "invalid"].includes(value) ? value : "pending";
            if (!canEditAttestation) {
                const badge = document.createElement("span");
                badge.className = `registration-attestation-badge is-${status}`;
                badge.textContent = status.charAt(0).toLocaleUpperCase() + status.slice(1);
                cell.append(badge);
                return;
            }
            const control = document.createElement("select");
            control.className = `registration-attestation-select is-${status}`;
            control.setAttribute("aria-label", `Attestation status for registration ${row.registration_code}`);
            [["pending", "Pending"], ["verified", "Verified"], ["invalid", "Invalid"]]
                .forEach(([optionValue, label]) => {
                    const option = document.createElement("option");
                    option.value = optionValue;
                    option.textContent = label;
                    option.selected = optionValue === status;
                    control.append(option);
                });
            control.dataset.previousValue = status;
            control.addEventListener("change", () => saveAttestationStatus(control, row));
            cell.append(control);
            return;
        }
        if (column.renderer === "payment_status") {
            if (value === null || value === undefined || value === "") {
                cell.textContent = "—";
                return;
            }
            const badge = document.createElement("span");
            const normalized = String(value).toLocaleLowerCase();
            badge.className = `registration-payment-badge${normalized.includes("validated") ? " is-validated" : normalized.includes("failed") || normalized.includes("cancel") ? " is-problem" : ""}`;
            badge.textContent = String(value);
            cell.append(badge);
            return;
        }
        const displayed = value === null || value === undefined || value === "" ? "—" : String(value);
        cell.textContent = displayed;
        cell.title = displayed;
    };

    const renderHeaders = () => {
        tableHead.replaceChildren();
        const groupRow = document.createElement("tr");
        groupRow.className = "registrations-group-row";
        const groups = [];
        columns.forEach((column) => {
            const last = groups[groups.length - 1];
            if (last && last.name === column.group) last.count += 1;
            else groups.push({name: column.group, count: 1});
        });
        groups.forEach((group) => {
            const th = document.createElement("th");
            th.colSpan = group.count;
            th.textContent = group.name;
            th.className = `registration-group-${group.name.toLocaleLowerCase()}`;
            groupRow.append(th);
        });
        tableHead.append(groupRow);

        const headerRow = document.createElement("tr");
        let previousGroup = null;
        columns.forEach((column, index) => {
            const th = document.createElement("th");
            if (index === 0) th.classList.add("sticky-key");
            if (previousGroup !== null && previousGroup !== column.group) th.classList.add("registration-group-start");
            if (column.group === "Requirements") th.classList.add("registration-requirement-cell");
            const button = document.createElement("button");
            button.type = "button";
            button.disabled = !column.sortable;
            button.textContent = column.label;
            if (column.sortable) {
                const indicator = document.createElement("span");
                indicator.textContent = sort === column.key ? (direction === "asc" ? " ↑" : " ↓") : " ↕";
                button.append(indicator);
                button.addEventListener("click", () => {
                    if (sort === column.key) direction = direction === "asc" ? "desc" : "asc";
                    else { sort = column.key; direction = "asc"; }
                    page = 1;
                    loadData();
                });
            }
            th.append(button);
            headerRow.append(th);
            previousGroup = column.group;
        });
        tableHead.append(headerRow);
    };

    const renderTable = (payload) => {
        renderHeaders();
        tableBody.replaceChildren();
        payload.rows.forEach((row) => {
            const tr = document.createElement("tr");
            let previousGroup = null;
            columns.forEach((column, index) => {
                const td = document.createElement("td");
                if (index === 0) td.classList.add("sticky-key");
                if (previousGroup !== null && previousGroup !== column.group) td.classList.add("registration-group-start");
                if (column.group === "Requirements") td.classList.add("registration-requirement-cell");
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
            if (current) button.className = "current";
            button.addEventListener("click", () => { page = target; loadData(); });
            return button;
        };
        pagination.append(makePageButton("Previous", info.page - 1, !info.has_previous));
        const startPage = Math.max(1, info.page - 2);
        const endPage = Math.min(info.pages, startPage + 4);
        for (let number = startPage; number <= endPage; number += 1) {
            pagination.append(makePageButton(String(number), number, number === info.page, number === info.page));
        }
        pagination.append(makePageButton("Next", info.page + 1, !info.has_next));

        const hasRows = payload.rows.length > 0;
        tableWrap.hidden = !hasRows;
        tableFooter.hidden = false;
        stateMessage.hidden = hasRows;
        if (!hasRows) {
            stateMessage.textContent = (filters.length || search.value.trim())
                ? "No registrations match the current search and filters."
                : "No registrations are available for this Event and Batch.";
        }
        renderFilterChips();
    };

    const renderSummary = (values) => {
        root.querySelectorAll("[data-summary]").forEach((element) => {
            const value = values && values[element.dataset.summary];
            element.textContent = Number(value || 0).toLocaleString();
        });
    };

    const loadData = (syncUrl = true) => {
        if (syncUrl) updateUrl();
        if (requestController) requestController.abort();
        requestController = new AbortController();
        root.classList.add("loading");
        const params = new URLSearchParams({
            batch: batchSelect.value,
            search: search.value.trim(),
            page: String(page),
            per_page: pageSize.value,
            direction,
        });
        if (sort) params.set("sort", sort);
        if (filters.length) params.set("filters", JSON.stringify(filters));
        fetch(`${root.dataset.dataUrl}?${params}`, {
            headers: {Accept: "application/json"}, signal: requestController.signal,
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
                root.querySelector("[data-reset-sort]").hidden = sort === defaultSort && direction === "asc";
                if (changed) populateFilterFields(); else refreshFilterControls();
                renderSummary(payload.summary);
                renderTable(payload);
                updateUrl();
            })
            .catch((error) => {
                if (error.name === "AbortError") return;
                stateMessage.hidden = false;
                stateMessage.textContent = "Registrations could not be loaded. Please try again.";
                tableWrap.hidden = true;
                tableFooter.hidden = true;
            })
            .finally(() => root.classList.remove("loading"));
    };

    readUrl();
    batchSelect.value = new URLSearchParams(window.location.search).get("batch") || "active";
    loadData(false);

    search.addEventListener("input", () => {
        window.clearTimeout(searchTimer);
        searchTimer = window.setTimeout(() => { page = 1; loadData(); }, 300);
    });
    batchSelect.addEventListener("change", () => { page = 1; loadData(); });
    pageSize.addEventListener("change", () => { page = 1; loadData(); });
    filterField.addEventListener("change", refreshFilterControls);
    filterOperator.addEventListener("change", refreshFilterValue);
    root.querySelector("[data-filter-toggle]").addEventListener("click", () => { filterBuilder.hidden = !filterBuilder.hidden; });
    root.querySelector("[data-add-filter]").addEventListener("click", () => {
        const valueControl = valueLabel.querySelector("select");
        const operator = filterOperator.value;
        const value = ["is_empty", "is_not_empty"].includes(operator) ? "" : valueControl && valueControl.multiple
            ? [...valueControl.selectedOptions].map((option) => option.value)
            : (valueControl ? valueControl.value : "");
        if (!["is_empty", "is_not_empty"].includes(operator) && (!value || (Array.isArray(value) && !value.length))) return;
        filters.push({field: filterField.value, operator, value});
        page = 1;
        loadData();
    });
    root.querySelector("[data-clear-filters]").addEventListener("click", () => { filters = []; page = 1; loadData(); });
    root.querySelector("[data-reset-sort]").addEventListener("click", () => { sort = defaultSort; direction = "asc"; page = 1; loadData(); });
    root.querySelectorAll("[data-attestation-quick]").forEach((button) => {
        button.addEventListener("click", () => {
            filters = filters.filter((item) => item.field !== "attestation_status");
            if (button.dataset.attestationQuick !== "all") {
                filters.push({
                    field: "attestation_status",
                    operator: "equals",
                    value: button.dataset.attestationQuick,
                });
            }
            page = 1;
            loadData();
        });
    });
    window.addEventListener("popstate", () => { readUrl(); loadData(false); });
})();
