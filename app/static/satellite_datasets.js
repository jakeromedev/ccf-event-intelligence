(() => {
    const modal = document.querySelector("[data-satellite-dataset-modal]");
    if (!modal) return;

    const form = modal.querySelector("[data-satellite-dataset-form]");
    const deleteForm = modal.querySelector("[data-satellite-dataset-delete-form]");
    const deleteButton = modal.querySelector("[data-satellite-dataset-delete-trigger]");
    const nameInput = modal.querySelector("[data-satellite-dataset-name]");
    const targetInput = modal.querySelector("[data-satellite-dataset-target]");
    const modeLabel = modal.querySelector("[data-satellite-dataset-mode]");
    const formTitle = modal.querySelector("[data-satellite-dataset-form-title]");
    const search = modal.querySelector("[data-satellite-search]");
    const selectionNote = modal.querySelector("[data-satellite-selection-note]");
    const checkboxes = [...modal.querySelectorAll("[data-satellite-option] input[type='checkbox']")];
    const optionRows = [...modal.querySelectorAll("[data-satellite-option]")];
    const listButtons = [...modal.querySelectorAll("[data-satellite-dataset-select]")];
    const emptySearch = modal.querySelector("[data-satellite-search-empty]");
    const json = modal.querySelector("[data-satellite-dataset-json]");
    const datasets = JSON.parse(json?.textContent || "[]");
    const createUrl = modal.dataset.createUrl;
    let activeDataset = null;
    let returnFocus = null;

    const datasetById = (identifier) => datasets.find((item) => String(item.id) === String(identifier));

    const setSelections = (dataset) => {
        const selected = new Set((dataset?.satellite_ids || []).map(String));
        checkboxes.forEach((checkbox) => {
            checkbox.checked = selected.has(checkbox.value);
            checkbox.setCustomValidity("");
        });
        const unavailable = (dataset?.satellites || []).filter((satellite) => !satellite.available_in_active_batch);
        if (selectionNote) {
            selectionNote.hidden = unavailable.length === 0;
            selectionNote.textContent = unavailable.length
                ? `${unavailable.length} configured ${unavailable.length === 1 ? "satellite is" : "satellites are"} absent from the active import and currently count as zero.`
                : "";
        }
    };

    const selectDataset = (dataset) => {
        activeDataset = dataset || null;
        listButtons.forEach((button) => {
            button.classList.toggle("selected", Boolean(dataset) && String(dataset.id) === button.dataset.satelliteDatasetSelect);
        });
        if (dataset) {
            modeLabel.textContent = "Edit dataset";
            formTitle.textContent = dataset.name;
            nameInput.value = dataset.name;
            targetInput.value = dataset.participant_target;
            form.action = `${createUrl}/${dataset.id}`;
            deleteForm.action = `${createUrl}/${dataset.id}/delete`;
            deleteButton.hidden = false;
        } else {
            modeLabel.textContent = "New dataset";
            formTitle.textContent = "Create Satellite Dataset";
            nameInput.value = "";
            targetInput.value = "";
            form.action = createUrl;
            deleteForm.removeAttribute("action");
            deleteButton.hidden = true;
        }
        if (search) {
            search.value = "";
            optionRows.forEach((row) => { row.hidden = false; });
            if (emptySearch) emptySearch.hidden = true;
        }
        setSelections(dataset);
    };

    const openModal = (datasetId = null, trigger = null) => {
        returnFocus = trigger || document.activeElement;
        selectDataset(datasetId ? datasetById(datasetId) : null);
        modal.hidden = false;
        document.body.classList.add("satellite-dataset-modal-open");
        requestAnimationFrame(() => nameInput.focus());
    };

    const closeModal = () => {
        modal.hidden = true;
        document.body.classList.remove("satellite-dataset-modal-open");
        if (returnFocus && typeof returnFocus.focus === "function") returnFocus.focus();
    };

    document.querySelectorAll("[data-satellite-dataset-open]").forEach((button) => {
        button.addEventListener("click", () => openModal(null, button));
    });
    modal.querySelectorAll("[data-satellite-dataset-close]").forEach((button) => {
        button.addEventListener("click", closeModal);
    });
    modal.querySelector("[data-satellite-dataset-new]")?.addEventListener("click", () => {
        selectDataset(null);
        nameInput.focus();
    });
    listButtons.forEach((button) => {
        button.addEventListener("click", () => {
            selectDataset(datasetById(button.dataset.satelliteDatasetSelect));
            nameInput.focus();
        });
    });

    search?.addEventListener("input", () => {
        const query = search.value.trim().toLocaleLowerCase();
        let visible = 0;
        optionRows.forEach((row) => {
            row.hidden = Boolean(query) && !row.dataset.searchValue.includes(query);
            if (!row.hidden) visible += 1;
        });
        if (emptySearch) emptySearch.hidden = visible !== 0;
    });

    checkboxes.forEach((checkbox) => {
        checkbox.addEventListener("change", () => {
            checkboxes.forEach((item) => item.setCustomValidity(""));
        });
    });
    form.addEventListener("submit", (event) => {
        if (checkboxes.length && !checkboxes.some((checkbox) => checkbox.checked)) {
            event.preventDefault();
            checkboxes[0].setCustomValidity("Select at least one satellite.");
            checkboxes[0].reportValidity();
        }
    });

    deleteButton.addEventListener("click", () => {
        if (!activeDataset) return;
        const confirmed = window.confirm(
            `Delete “${activeDataset.name}”? Its satellite mappings will be removed, but imported satellites and registrants will remain unchanged.`
        );
        if (confirmed) deleteForm.submit();
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && !modal.hidden) closeModal();
    });

    const parameters = new URLSearchParams(window.location.search);
    if (parameters.get("satellite_targets") === "1") {
        openModal(parameters.get("edit_dataset"));
    }
})();
