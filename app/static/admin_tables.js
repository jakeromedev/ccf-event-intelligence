(() => {
    const root = document.querySelector("[data-admin-table]");
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
    const columnsMenu = root.querySelector("[data-columns-menu]");
    const columnsToggle = root.querySelector("[data-columns-toggle]");
    const columnOptions = root.querySelector("[data-column-options]");
    const columnSearch = root.querySelector("[data-column-search]");
    const drawer = document.querySelector("[data-source-drawer]");

    let columns = [];
    let columnValues = {};
    let filters = [];
    let page = 1;
    let sort = "";
    let direction = "asc";
    let defaultSort = "";
    let visibleColumns = new Set();
    let requestController = null;
    let searchTimer = null;
    let returnFocus = null;
    const columnPreferenceVersion = 2;

    const operatorLabels = {
        contains: "Contains", equals: "Equals", starts_with: "Starts With",
        ends_with: "Ends With", is_empty: "Is Empty", is_not_empty: "Is Not Empty",
        in: "Is Any Of", exact: "Exact Date", before: "Before", after: "After",
        between: "Between", greater_than: "Greater Than", less_than: "Less Than",
    };

    const readUrl = () => {
        const params = new URLSearchParams(window.location.search);
        search.value = params.get("search") || params.get("q") || "";
        page = Math.max(Number.parseInt(params.get("page") || "1", 10) || 1, 1);
        pageSize.value = ["25", "50", "100"].includes(params.get("per_page")) ? params.get("per_page") : "50";
        sort = params.get("sort") || "";
        direction = params.get("direction") === "desc" ? "desc" : "asc";
        const encodedFilters = params.get("filters");
        if (encodedFilters) {
            try {
                const parsed = JSON.parse(encodedFilters);
                filters = Array.isArray(parsed) ? parsed : [];
            } catch (_error) {
                filters = [];
            }
        } else {
            filters = [];
        }
    };

    const updateUrl = () => {
        const params = new URLSearchParams(window.location.search);
        const values = {
            search: search.value.trim(), page: page > 1 ? String(page) : "",
            per_page: pageSize.value !== "50" ? pageSize.value : "",
            sort, direction: sort && direction === "desc" ? "desc" : "",
            filters: filters.length ? JSON.stringify(filters) : "",
            batch: batchSelect.value === "active" ? "" : batchSelect.value,
        };
        Object.entries(values).forEach(([key, value]) => value ? params.set(key, value) : params.delete(key));
        window.history.replaceState({}, "", `${window.location.pathname}${params.toString() ? `?${params}` : ""}`);
    };

    const loadPreference = () => {
        try {
            const saved = JSON.parse(window.localStorage.getItem(root.dataset.preferenceKey));
            if (Array.isArray(saved)) return {visible: saved, legacy: true};
            if (saved && saved.version === columnPreferenceVersion && Array.isArray(saved.visible)) {
                return {visible: saved.visible, legacy: false};
            }
            return null;
        } catch (_error) {
            return null;
        }
    };

    const savePreference = () => {
        try {
            window.localStorage.setItem(root.dataset.preferenceKey, JSON.stringify({
                version: columnPreferenceVersion,
                visible: [...visibleColumns],
            }));
        } catch (_error) {
            // Local preferences are optional in restricted browser contexts.
        }
    };

    const setColumns = (incoming) => {
        columns = incoming;
        const available = new Set(columns.map((column) => column.key));
        const saved = loadPreference();
        visibleColumns = new Set(
            saved ? saved.visible.filter((key) => available.has(key)) : columns.filter((column) => column.default).map((column) => column.key)
        );
        if (saved && saved.legacy) {
            columns
                .filter((column) => column.default && column.renderer === "attestation_form_link")
                .forEach((column) => visibleColumns.add(column.key));
        }
        if (!visibleColumns.size) {
            columns.filter((column) => column.default).forEach((column) => visibleColumns.add(column.key));
        }
        if (saved && saved.legacy) savePreference();
        renderColumnMenu();
        populateFilterFields();
    };

    const renderColumnMenu = () => {
        const query = columnSearch.value.trim().toLocaleLowerCase();
        columnOptions.replaceChildren();
        const groups = new Map();
        columns.forEach((column) => {
            if (query && !column.label.toLocaleLowerCase().includes(query)) return;
            if (!groups.has(column.group)) groups.set(column.group, []);
            groups.get(column.group).push(column);
        });
        groups.forEach((items, groupName) => {
            const group = document.createElement("fieldset");
            const legend = document.createElement("legend");
            legend.textContent = groupName;
            group.append(legend);
            items.forEach((column) => {
                const label = document.createElement("label");
                const checkbox = document.createElement("input");
                checkbox.type = "checkbox";
                checkbox.checked = visibleColumns.has(column.key);
                checkbox.addEventListener("change", () => {
                    checkbox.checked ? visibleColumns.add(column.key) : visibleColumns.delete(column.key);
                    if (!visibleColumns.size) {
                        visibleColumns.add(column.key);
                        checkbox.checked = true;
                    }
                    savePreference();
                    loadData(false);
                });
                label.append(checkbox, document.createTextNode(column.label));
                group.append(label);
            });
            columnOptions.append(group);
        });
    };

    const populateFilterFields = () => {
        const selected = filterField.value;
        filterField.replaceChildren();
        const groups = new Map();
        columns.forEach((column) => {
            if (!groups.has(column.group)) groups.set(column.group, []);
            groups.get(column.group).push(column);
        });
        groups.forEach((items, label) => {
            const group = document.createElement("optgroup");
            group.label = label;
            items.forEach((column) => {
                const option = document.createElement("option");
                option.value = column.key;
                option.textContent = column.label;
                group.append(option);
            });
            filterField.append(group);
        });
        if (columns.some((column) => column.key === selected)) filterField.value = selected;
        refreshFilterControls();
    };

    const refreshFilterControls = () => {
        const column = columns.find((item) => item.key === filterField.value) || columns[0];
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
        const column = columns.find((item) => item.key === filterField.value);
        const noValue = ["is_empty", "is_not_empty"].includes(filterOperator.value);
        valueLabel.hidden = noValue;
        if (noValue || !column) return;
        const previous = valueLabel.querySelector("input, select");
        const options = columnValues[column.key] || [];
        let control;
        if (["select", "boolean"].includes(column.type)) {
            control = document.createElement("select");
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
        } else {
            control = document.createElement("input");
            control.type = column.type === "date" ? "date" : column.type === "number" ? "number" : "text";
            control.placeholder = filterOperator.value === "between" ? "Start, End" : "Enter a value";
            if (filterOperator.value === "between") control.type = "text";
        }
        control.dataset.filterValue = "";
        if (previous) previous.replaceWith(control); else valueLabel.append(control);
    };

    const renderFilterChips = () => {
        filterChips.replaceChildren();
        filters.forEach((filter, index) => {
            const column = columns.find((item) => item.key === filter.field);
            if (!column) return;
            const chip = document.createElement("button");
            chip.type = "button";
            const displayValue = Array.isArray(filter.value) ? filter.value.join(", ") : filter.value;
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
    };

    const displayValue = (value, column) => {
        if (value === null || value === undefined || value === "") return "—";
        if (column.type === "boolean") return Number(value) ? "Yes" : "No";
        return String(value);
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

    const paymentStatusBadge = (value, column) => {
        const displayed = displayValue(value, column);
        const normalized = String(value || "").trim().toLocaleLowerCase();
        const badge = document.createElement("span");
        badge.className = "admin-payment-status-badge";
        if (["validated", "successful", "success", "paid", "completed", "approved"].some((status) => normalized.includes(status))) {
            badge.classList.add("is-success");
        } else if (["failed", "declined", "rejected", "cancelled", "canceled"].some((status) => normalized.includes(status))) {
            badge.classList.add("is-failed");
        }
        badge.textContent = displayed;
        return badge;
    };

    const renderCellValue = (cell, value, column) => {
        if (column.renderer === "payment_status_badge") {
            cell.append(paymentStatusBadge(value, column));
            return;
        }
        if (column.renderer === "attestation_form_link") {
            const url = safeExternalUrl(value);
            if (!url) {
                cell.textContent = "—";
                cell.title = "—";
                return;
            }
            const link = document.createElement("a");
            link.className = "admin-cell-link";
            link.href = url;
            link.target = "_blank";
            link.rel = "noopener noreferrer";
            link.textContent = "View Attestation Form";
            link.setAttribute("aria-label", "View Attestation Form (opens in a new tab)");
            cell.append(link);
            return;
        }
        const displayed = displayValue(value, column);
        cell.textContent = displayed;
        cell.title = displayed;
    };

    const renderTable = (payload) => {
        const displayed = columns.filter((column) => visibleColumns.has(column.key));
        tableHead.replaceChildren();
        const headerRow = document.createElement("tr");
        displayed.forEach((column, index) => {
            const th = document.createElement("th");
            if (index === 0) th.className = "sticky-key";
            const button = document.createElement("button");
            button.type = "button";
            button.textContent = column.label;
            const indicator = document.createElement("span");
            indicator.textContent = sort === column.key ? (direction === "asc" ? " ↑" : " ↓") : " ↕";
            button.append(indicator);
            button.addEventListener("click", () => {
                if (sort === column.key) direction = direction === "asc" ? "desc" : "asc";
                else { sort = column.key; direction = "asc"; }
                page = 1;
                loadData();
            });
            th.append(button);
            headerRow.append(th);
        });
        if (root.dataset.dataset === "curated") {
            const actions = document.createElement("th");
            actions.textContent = "Sources";
            actions.className = "admin-actions-column";
            headerRow.append(actions);
        }
        tableHead.append(headerRow);

        tableBody.replaceChildren();
        payload.rows.forEach((row) => {
            const tr = document.createElement("tr");
            displayed.forEach((column, index) => {
                const td = document.createElement("td");
                if (index === 0) td.className = "sticky-key";
                renderCellValue(td, row[column.key], column);
                tr.append(td);
            });
            if (root.dataset.dataset === "curated") {
                const td = document.createElement("td");
                td.className = "admin-actions-column";
                const button = document.createElement("button");
                button.type = "button";
                button.className = "source-link";
                button.textContent = `Sources (${row.source_registrant_count || 0})`;
                button.addEventListener("click", () => openSources(row.id, button));
                td.append(button);
                tr.append(td);
            }
            tableBody.append(tr);
        });

        const info = payload.pagination;
        summary.textContent = `Showing ${info.start.toLocaleString()}–${info.end.toLocaleString()} of ${info.total.toLocaleString()} records`;
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
                ? `No ${payload.label.toLocaleLowerCase()} match the current filters.`
                : `No ${payload.label.toLocaleLowerCase()} are available for this Event and Batch.`;
        }
        renderFilterChips();
    };

    const loadData = (syncUrl = true) => {
        if (syncUrl) updateUrl();
        if (requestController) requestController.abort();
        requestController = new AbortController();
        root.classList.add("loading");
        if (!tableBody.children.length) {
            stateMessage.hidden = false;
            stateMessage.textContent = "Loading records…";
            tableWrap.hidden = true;
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
        fetch(`${root.dataset.dataUrl}?${params}`, {headers: {Accept: "application/json"}, signal: requestController.signal})
            .then((response) => response.ok ? response.json() : response.json().then((payload) => Promise.reject(new Error(payload.error || "Records could not be loaded."))))
            .then((payload) => {
                if (!columns.length || columns.map((item) => item.key).join() !== payload.columns.map((item) => item.key).join()) {
                    setColumns(payload.columns);
                }
                columnValues = payload.column_options || {};
                sort = payload.query.sort;
                direction = payload.query.direction;
                defaultSort = payload.query.default_sort;
                const resetSort = root.querySelector("[data-reset-sort]");
                resetSort.hidden = sort === defaultSort && direction === "asc";
                page = payload.pagination.page;
                renderTable(payload);
                refreshFilterControls();
                updateUrl();
            })
            .catch((error) => {
                if (error.name === "AbortError") return;
                stateMessage.hidden = false;
                tableWrap.hidden = true;
                tableFooter.hidden = true;
                stateMessage.textContent = "Administrative records could not be loaded. Please try again.";
            })
            .finally(() => root.classList.remove("loading"));
    };

    const detailRow = (label, value) => {
        const row = document.createElement("div");
        const term = document.createElement("dt");
        const detail = document.createElement("dd");
        term.textContent = label.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
        detail.textContent = value === null || value === undefined || value === "" ? "—" : String(value);
        row.append(term, detail);
        return row;
    };

    const openSources = (curatedId, trigger) => {
        if (!drawer) return;
        returnFocus = trigger;
        drawer.hidden = false;
        document.body.classList.add("admin-drawer-open");
        const content = drawer.querySelector("[data-drawer-content]");
        content.replaceChildren();
        const loading = document.createElement("p");
        loading.textContent = "Loading registration sources…";
        content.append(loading);
        const endpoint = root.dataset.sourcesUrl.replace("/0/sources", `/${curatedId}/sources`);
        fetch(`${endpoint}?batch=${encodeURIComponent(batchSelect.value)}`, {headers: {Accept: "application/json"}})
            .then((response) => { if (!response.ok) throw new Error(); return response.json(); })
            .then((payload) => {
                const curated = payload.curated_registrant;
                const name = [curated.representative_first_name, curated.last_name].filter(Boolean).join(" ") || "Name unavailable";
                drawer.querySelector("[data-drawer-title]").textContent = name;
                drawer.querySelector("[data-drawer-subtitle]").textContent = `Curated Registrant #${curated.id} · Batch #${curated.batch_id}`;
                drawer.querySelector("[data-drawer-lineage]").textContent = `${payload.sources.length} linked registration source${payload.sources.length === 1 ? "" : "s"}`;
                content.replaceChildren();
                if (!payload.sources.length) {
                    const empty = document.createElement("p");
                    empty.className = "admin-source-error";
                    empty.textContent = "No linked registration sources were found. This indicates a data integrity issue.";
                    content.append(empty);
                    return;
                }
                payload.sources.forEach((source, index) => {
                    const details = document.createElement("details");
                    details.className = "admin-source-record";
                    details.open = index === 0;
                    const heading = document.createElement("summary");
                    const headingCopy = document.createElement("span");
                    const strong = document.createElement("strong");
                    strong.textContent = `${source.event} · Registration ${source.registration_code || `#${source.id}`}`;
                    const small = document.createElement("small");
                    small.textContent = `Batch #${source.batch_id} · Imported ${source.import_date || "date unavailable"}`;
                    headingCopy.append(strong, small);
                    heading.append(headingCopy);
                    details.append(heading);
                    const sourceSection = document.createElement("section");
                    if (Object.keys(source.source_values || {}).length) {
                        const title = document.createElement("h3");
                        title.textContent = "Complete Source Record";
                        const list = document.createElement("dl");
                        Object.entries(source.source_values).forEach(([key, value]) => list.append(detailRow(key, value)));
                        sourceSection.append(title, list);
                    }
                    const normalizedTitle = document.createElement("h3");
                    normalizedTitle.textContent = "Imported & Normalized Metadata";
                    const normalizedList = document.createElement("dl");
                    Object.entries(source.normalized_values || {}).forEach(([key, value]) => normalizedList.append(detailRow(key, value)));
                    sourceSection.append(normalizedTitle, normalizedList);
                    details.append(sourceSection);
                    content.append(details);
                });
            })
            .catch(() => {
                content.replaceChildren();
                const error = document.createElement("p");
                error.className = "admin-source-error";
                error.textContent = "Registration sources could not be loaded or are no longer accessible.";
                content.append(error);
            });
    };

    const closeDrawer = () => {
        if (!drawer) return;
        drawer.hidden = true;
        document.body.classList.remove("admin-drawer-open");
        if (returnFocus) returnFocus.focus();
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
        const valueControl = valueLabel.querySelector("input, select");
        const operator = filterOperator.value;
        const value = ["is_empty", "is_not_empty"].includes(operator) ? "" : valueControl && valueControl.multiple
            ? [...valueControl.selectedOptions].map((option) => option.value)
            : (valueControl ? valueControl.value.trim() : "");
        if (!["is_empty", "is_not_empty"].includes(operator) && (!value || (Array.isArray(value) && !value.length))) return;
        filters.push({field: filterField.value, operator, value});
        if (valueControl) valueControl.value = "";
        page = 1;
        loadData();
    });
    root.querySelector("[data-clear-filters]").addEventListener("click", () => { filters = []; page = 1; loadData(); });
    root.querySelector("[data-reset-sort]").addEventListener("click", () => { sort = defaultSort; direction = "asc"; page = 1; loadData(); });
    columnsToggle.addEventListener("click", () => {
        columnsMenu.hidden = !columnsMenu.hidden;
        columnsToggle.setAttribute("aria-expanded", String(!columnsMenu.hidden));
    });
    root.querySelector("[data-columns-close]").addEventListener("click", () => { columnsMenu.hidden = true; columnsToggle.setAttribute("aria-expanded", "false"); });
    columnSearch.addEventListener("input", renderColumnMenu);
    root.querySelector("[data-show-all]").addEventListener("click", () => { visibleColumns = new Set(columns.map((column) => column.key)); savePreference(); renderColumnMenu(); loadData(false); });
    root.querySelector("[data-reset-columns]").addEventListener("click", () => { visibleColumns = new Set(columns.filter((column) => column.default).map((column) => column.key)); savePreference(); renderColumnMenu(); loadData(false); });
    if (drawer) drawer.querySelectorAll("[data-drawer-close]").forEach((button) => button.addEventListener("click", closeDrawer));
    document.addEventListener("keydown", (event) => { if (event.key === "Escape") { if (drawer && !drawer.hidden) closeDrawer(); else if (!columnsMenu.hidden) columnsMenu.hidden = true; } });
    window.addEventListener("popstate", () => { readUrl(); loadData(false); });
})();
