(() => {
    const form = document.querySelector("[data-satellite-filters]");
    if (!form) return;

    const group = form.querySelector("[data-group-filter]");
    const hub = form.querySelector("[data-hub-filter]");
    const satellite = form.querySelector("[data-satellite-filter]");
    const status = form.querySelector("[data-link-status-filter]");

    const constrain = (select, predicate) => {
        Array.from(select.options).forEach((option, index) => {
            option.hidden = index > 0 && !predicate(option);
            option.disabled = option.hidden;
        });
        if (select.selectedOptions[0]?.disabled) select.value = "";
    };

    const updateOptions = () => {
        constrain(hub, (option) => !group.value || option.dataset.groupId === group.value);
        constrain(
            satellite,
            (option) =>
                (!group.value || option.dataset.groupId === group.value) &&
                (!hub.value || option.dataset.hubId === hub.value)
        );
    };

    group.addEventListener("change", () => {
        hub.value = "";
        satellite.value = "";
        updateOptions();
    });
    hub.addEventListener("change", () => {
        satellite.value = "";
        updateOptions();
    });
    status.addEventListener("change", () => {
        if (status.value === "needs_mapping") {
            group.value = "";
            hub.value = "";
            satellite.value = "";
        }
        form.requestSubmit();
    });
    satellite.addEventListener("change", () => form.requestSubmit());
    updateOptions();

    document.querySelectorAll("[data-satellite-hierarchy] details").forEach((item) => {
        const summary = item.querySelector(":scope > summary");
        if (!summary) return;
        const syncExpanded = () => summary.setAttribute("aria-expanded", String(item.open));
        item.addEventListener("toggle", syncExpanded);
        syncExpanded();
    });
})();
