(() => {
    const modal = document.querySelector("[data-quality-modal]");
    if (!modal) return;

    const cards = document.querySelectorAll("[data-quality-card]");
    const title = modal.querySelector("[data-quality-title]");
    const search = modal.querySelector("[data-quality-search]");
    const severity = modal.querySelector("[data-quality-severity]");
    const entity = modal.querySelector("[data-quality-entity]");
    const pageSize = modal.querySelector("[data-quality-page-size]");
    const state = modal.querySelector("[data-quality-state]");
    const tableWrap = modal.querySelector("[data-quality-table-wrap]");
    const rows = modal.querySelector("[data-quality-rows]");
    const summary = modal.querySelector("[data-quality-summary]");
    const pagination = modal.querySelector("[data-quality-pagination]");
    const closeButton = modal.querySelector(".registrant-modal-close");

    let category = "";
    let page = 1;
    let returnFocus = null;
    let requestController = null;
    let searchTimer = null;

    const cell = (value, className = "") => {
        const element = document.createElement("td");
        element.textContent = value === null || value === undefined || value === "" ? "—" : value;
        if (className) element.className = className;
        return element;
    };

    const labelForEntity = (value) => value
        .replaceAll("_", " ")
        .replace(/\b\w/g, (letter) => letter.toUpperCase());

    const setEntityOptions = (entities, selected) => {
        entity.replaceChildren();
        const all = document.createElement("option");
        all.value = "all";
        all.textContent = "All entities";
        entity.append(all);
        entities.forEach((value) => {
            const option = document.createElement("option");
            option.value = value;
            option.textContent = labelForEntity(value);
            entity.append(option);
        });
        entity.value = entities.includes(selected) ? selected : "all";
    };

    const pageButton = (label, target, disabled = false) => {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = label;
        button.disabled = disabled;
        button.addEventListener("click", () => {
            page = target;
            loadIssues();
        });
        return button;
    };

    const render = (payload) => {
        setEntityOptions(payload.entities || [], payload.filters.entity);
        rows.replaceChildren();

        (payload.issues || []).forEach((issue) => {
            const row = document.createElement("tr");
            const severityCell = document.createElement("td");
            const badge = document.createElement("span");
            badge.className = `severity ${issue.severity}`;
            badge.textContent = issue.severity;
            severityCell.append(badge);
            row.append(
                severityCell,
                cell(labelForEntity(issue.entity_type)),
                cell(issue.source_identifier, "quality-detail-identifier"),
                cell(issue.source_row, "numeric"),
                cell(issue.message, "quality-detail-message")
            );
            rows.append(row);
        });

        const info = payload.pagination;
        const hasRows = payload.issues && payload.issues.length > 0;
        state.hidden = hasRows;
        tableWrap.hidden = !hasRows;
        const filtersApplied = Boolean(payload.filters.query)
            || payload.filters.severity !== "all"
            || payload.filters.entity !== "all";
        state.textContent = filtersApplied
            ? "No issues match the current filters."
            : "No issues were recorded for this category.";
        summary.textContent = `Showing ${info.start.toLocaleString()}–${info.end.toLocaleString()} of ${info.total.toLocaleString()} issues`;

        pagination.replaceChildren();
        pagination.append(pageButton("Previous", info.page - 1, !info.has_previous));
        const pageLabel = document.createElement("span");
        pageLabel.className = "current-page";
        pageLabel.textContent = `${info.page} / ${info.pages}`;
        pageLabel.setAttribute("aria-label", `Page ${info.page} of ${info.pages}`);
        pagination.append(pageLabel);
        pagination.append(pageButton("Next", info.page + 1, !info.has_next));
    };

    const loadIssues = () => {
        if (!category) return;
        if (requestController) requestController.abort();
        requestController = new AbortController();
        state.hidden = false;
        state.textContent = "Loading issues…";
        tableWrap.hidden = true;
        summary.textContent = "Loading…";

        const parameters = new URLSearchParams({
            category,
            q: search.value.trim(),
            severity: severity.value,
            entity: entity.value,
            page: String(page),
            per_page: pageSize.value,
        });
        fetch(`${modal.dataset.endpoint}?${parameters.toString()}`, {
            headers: {Accept: "application/json"},
            signal: requestController.signal,
        })
            .then((response) => {
                if (!response.ok) throw new Error("Issue details could not be loaded.");
                return response.json();
            })
            .then(render)
            .catch((error) => {
                if (error.name === "AbortError") return;
                state.hidden = false;
                tableWrap.hidden = true;
                state.textContent = "Issue details could not be loaded. Close this window and try again.";
                summary.textContent = "Unable to load issue details";
                pagination.replaceChildren();
            });
    };

    const openModal = (card) => {
        returnFocus = card;
        category = card.dataset.category;
        title.textContent = card.dataset.title || "Data Quality Issues";
        search.value = "";
        severity.value = "all";
        setEntityOptions([], "all");
        pageSize.value = "10";
        page = 1;
        modal.hidden = false;
        document.body.classList.add("registrant-modal-open");
        closeButton.focus();
        loadIssues();
    };

    const closeModal = () => {
        if (requestController) requestController.abort();
        modal.hidden = true;
        document.body.classList.remove("registrant-modal-open");
        if (returnFocus && typeof returnFocus.focus === "function") returnFocus.focus();
    };

    cards.forEach((card) => card.addEventListener("click", () => openModal(card)));
    modal.querySelectorAll("[data-quality-close]").forEach((control) => {
        control.addEventListener("click", closeModal);
    });
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && !modal.hidden) closeModal();
    });

    [severity, entity, pageSize].forEach((control) => {
        control.addEventListener("change", () => {
            page = 1;
            loadIssues();
        });
    });
    search.addEventListener("input", () => {
        window.clearTimeout(searchTimer);
        searchTimer = window.setTimeout(() => {
            page = 1;
            loadIssues();
        }, 250);
    });
})();
