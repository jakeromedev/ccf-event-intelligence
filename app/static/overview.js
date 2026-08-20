(() => {
    const modal = document.querySelector("[data-registrant-modal]");
    if (!modal) return;

    const title = modal.querySelector("#registrant-modal-title");
    const search = modal.querySelector("[data-filter-search]");
    const origin = modal.querySelector("[data-filter-origin]");
    const gender = modal.querySelector("[data-filter-gender]");
    const age = modal.querySelector("[data-filter-age]");
    const checkin = modal.querySelector("[data-filter-checkin]");
    const pageSize = modal.querySelector("[data-page-size]");
    const tableState = modal.querySelector("[data-table-state]");
    const tableWrap = modal.querySelector("[data-table-wrap]");
    const tableBody = modal.querySelector("[data-registrant-rows]");
    const summary = modal.querySelector("[data-result-summary]");
    const pagination = modal.querySelector("[data-pagination]");
    const closeButton = modal.querySelector(".registrant-modal-close");

    let registrants = [];
    let loadPromise = null;
    let currentPage = 1;
    let returnFocus = null;

    const cell = (value, className = "") => {
        const element = document.createElement("td");
        element.textContent = value;
        if (className) element.className = className;
        return element;
    };

    const matchesOrigin = (row, value) => {
        if (value === "all") return true;
        if (value === "satellites") {
            return row.origin === "Local Satellite" || row.origin === "International Satellite";
        }
        return row.origin === value;
    };

    const filteredRegistrants = () => {
        const query = search.value.trim().toLocaleLowerCase();
        return registrants.filter((row) => {
            if (!matchesOrigin(row, origin.value)) return false;
            if (gender.value !== "all" && row.gender_key !== gender.value) return false;
            if (age.value !== "all" && row.age_group !== age.value) return false;
            if (checkin.value === "checked" && !row.checked_in) return false;
            if (checkin.value === "not-checked" && row.checked_in) return false;
            if (!query) return true;
            return [
                row.name,
                row.registration_code,
                row.ticket_code,
                row.origin,
                row.satellite,
                row.gender,
                row.age_group,
                row.ticket_status,
                row.checked_in ? "checked in" : "not checked in",
            ].join(" ").toLocaleLowerCase().includes(query);
        });
    };

    const paginationButton = (label, targetPage, disabled = false, className = "") => {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = label;
        button.disabled = disabled;
        if (className) button.className = className;
        button.addEventListener("click", () => {
            currentPage = targetPage;
            render();
            tableWrap.scrollTop = 0;
        });
        return button;
    };

    const render = () => {
        const filtered = filteredRegistrants();
        const size = Number(pageSize.value) || 25;
        const pageCount = Math.max(1, Math.ceil(filtered.length / size));
        currentPage = Math.min(Math.max(currentPage, 1), pageCount);
        const start = (currentPage - 1) * size;
        const visible = filtered.slice(start, start + size);

        tableBody.replaceChildren();
        visible.forEach((row) => {
            const tableRow = document.createElement("tr");
            tableRow.append(
                cell(row.name),
                cell(row.registration_code),
                cell(row.ticket_code),
                cell(row.origin),
                cell(row.satellite),
                cell(row.gender),
                cell(row.age_group),
                cell(row.ticket_status)
            );
            const checkinCell = document.createElement("td");
            const badge = document.createElement("span");
            badge.className = `checkin-badge${row.checked_in ? " checked" : ""}`;
            badge.textContent = row.checked_in ? "Checked In" : "Not Checked In";
            checkinCell.append(badge);
            tableRow.append(checkinCell);
            tableBody.append(tableRow);
        });

        tableState.hidden = visible.length > 0;
        tableWrap.hidden = visible.length === 0;
        tableState.textContent = "No registrants match the current search and filters.";

        const first = filtered.length ? start + 1 : 0;
        const last = Math.min(start + size, filtered.length);
        summary.textContent = `Showing ${first.toLocaleString()}–${last.toLocaleString()} of ${filtered.length.toLocaleString()} registrants`;

        pagination.replaceChildren();
        pagination.append(paginationButton("Previous", currentPage - 1, currentPage === 1));
        const pageLabel = document.createElement("span");
        pageLabel.className = "current-page";
        pageLabel.textContent = `${currentPage} / ${pageCount}`;
        pageLabel.setAttribute("aria-label", `Page ${currentPage} of ${pageCount}`);
        pagination.append(pageLabel);
        pagination.append(paginationButton("Next", currentPage + 1, currentPage === pageCount));
    };

    const loadRegistrants = () => {
        if (loadPromise) return loadPromise;
        tableState.hidden = false;
        tableState.textContent = "Loading registrants…";
        tableWrap.hidden = true;
        summary.textContent = "Loading…";
        loadPromise = fetch(modal.dataset.endpoint, {headers: {Accept: "application/json"}})
            .then((response) => {
                if (!response.ok) throw new Error("Registrant data could not be loaded.");
                return response.json();
            })
            .then((payload) => {
                registrants = payload.registrants || [];
                render();
            })
            .catch(() => {
                loadPromise = null;
                tableState.hidden = false;
                tableWrap.hidden = true;
                tableState.textContent = "Registrant data could not be loaded. Close this window and try again.";
                summary.textContent = "Unable to load registrants";
            });
        return loadPromise;
    };

    const openModal = (trigger, focusTarget = trigger) => {
        returnFocus = focusTarget;
        title.textContent = trigger.dataset.modalTitle || "All registrants";
        search.value = "";
        origin.value = trigger.dataset.filterOrigin || "all";
        gender.value = trigger.dataset.filterGender || "all";
        age.value = trigger.dataset.filterAge || "all";
        checkin.value = "all";
        currentPage = 1;
        modal.hidden = false;
        document.body.classList.add("registrant-modal-open");
        closeButton.focus();
        if (registrants.length) render();
        else loadRegistrants();
    };

    const closeModal = () => {
        modal.hidden = true;
        document.body.classList.remove("registrant-modal-open");
        if (returnFocus && typeof returnFocus.focus === "function") returnFocus.focus();
    };

    document.querySelectorAll("[data-registrant-trigger]").forEach((trigger) => {
        trigger.addEventListener("click", () => openModal(trigger));
    });

    document.querySelectorAll("[data-gender-chart]").forEach((chart) => {
        chart.addEventListener("click", (event) => {
            const rect = chart.getBoundingClientRect();
            const x = event.clientX - rect.left - rect.width / 2;
            const y = event.clientY - rect.top - rect.height / 2;
            const distance = Math.sqrt(x * x + y * y);
            let selected = null;
            if (event.detail && distance > rect.width * .28) {
                const angle = (Math.atan2(x, -y) * 180 / Math.PI + 360) % 360;
                const percentage = angle / 3.6;
                const segments = JSON.parse(chart.dataset.genderSegments || "[]");
                selected = segments.find((segment) => segment.count && percentage >= segment.start && percentage < segment.end);
            }
            openModal({dataset: selected ? {
                filterGender: selected.key,
                modalTitle: `${selected.label} registrants`,
            } : {modalTitle: "All registrants"}}, chart);
        });
    });

    modal.querySelectorAll("[data-modal-close]").forEach((control) => {
        control.addEventListener("click", closeModal);
    });
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && !modal.hidden) closeModal();
    });

    [origin, gender, age, checkin, pageSize].forEach((control) => {
        control.addEventListener("change", () => {
            currentPage = 1;
            render();
        });
    });
    search.addEventListener("input", () => {
        currentPage = 1;
        render();
    });

    if (new URLSearchParams(window.location.search).get("people") === "1") {
        const allRegistrantsTrigger = document.querySelector("[data-registrant-trigger]");
        if (allRegistrantsTrigger) openModal(allRegistrantsTrigger);
    }
})();
