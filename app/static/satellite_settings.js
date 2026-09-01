(() => {
    const tools = document.querySelector("[data-satellite-settings-tools]");
    if (!tools) return;

    const search = tools.querySelector("[data-settings-search]");
    const groupFilter = tools.querySelector("[data-settings-group-filter]");
    const results = tools.querySelector("[data-settings-results]");
    const noResults = document.querySelector("[data-settings-no-results]");
    const groups = [...document.querySelectorAll("[data-hub-group]")];
    const cards = [...document.querySelectorAll("[data-hub-card]")];
    const unassigned = document.querySelector("[data-unassigned-directory]");
    const unassignedRows = [...document.querySelectorAll("[data-unassigned-row]")];

    const setHubExpanded = (card, expanded) => {
        const toggle = card.querySelector("[data-hub-toggle]");
        const body = card.querySelector("[data-hub-body]");
        if (!toggle || !body) return;
        toggle.setAttribute("aria-expanded", String(expanded));
        toggle.querySelector("span").textContent = expanded ? "Collapse" : "Expand";
        body.hidden = !expanded;
    };

    const applyFilters = () => {
        const query = search.value.trim().toLocaleLowerCase();
        const selectedGroup = groupFilter.value;
        let visibleHubs = 0;
        let visibleSatellites = 0;

        groups.forEach((group) => {
            const groupAllowed = selectedGroup === "all" || selectedGroup === group.dataset.hubGroup;
            let groupMatches = 0;
            group.querySelectorAll("[data-hub-card]").forEach((card) => {
                const hubMatches = !query || card.dataset.hubName.includes(query);
                let matchingSatellites = 0;
                card.querySelectorAll("[data-satellite-row]").forEach((row) => {
                    const matches = !query || hubMatches || row.dataset.satelliteName.includes(query);
                    row.hidden = !matches;
                    if (matches) matchingSatellites += 1;
                });
                const cardMatches = groupAllowed && (!query || hubMatches || matchingSatellites > 0);
                card.hidden = !cardMatches;
                card.querySelectorAll("[data-hub-empty]").forEach((row) => {
                    row.hidden = Boolean(query);
                });
                if (cardMatches) {
                    groupMatches += 1;
                    visibleHubs += 1;
                    visibleSatellites += matchingSatellites;
                    if (query) setHubExpanded(card, true);
                }
            });
            group.hidden = !groupAllowed || (Boolean(query) && groupMatches === 0);
        });

        let visibleUnassigned = 0;
        unassignedRows.forEach((row) => {
            const matches = selectedGroup === "all" && (!query || row.dataset.satelliteName.includes(query));
            row.hidden = !matches;
            if (matches) visibleUnassigned += 1;
        });
        if (unassigned) {
            unassigned.hidden = selectedGroup !== "all" || (Boolean(query) && visibleUnassigned === 0);
        }
        visibleSatellites += visibleUnassigned;

        results.textContent = `Showing ${visibleHubs} ${visibleHubs === 1 ? "Hub" : "Hubs"} and ${visibleSatellites} ${visibleSatellites === 1 ? "Satellite" : "Satellites"}`;
        noResults.hidden = visibleHubs + visibleSatellites !== 0;
    };

    document.querySelectorAll("[data-hub-toggle]").forEach((toggle) => {
        toggle.addEventListener("click", () => {
            const card = toggle.closest("[data-hub-card]");
            setHubExpanded(card, toggle.getAttribute("aria-expanded") !== "true");
        });
    });
    tools.querySelector("[data-settings-expand]")?.addEventListener("click", () => {
        cards.filter((card) => !card.hidden).forEach((card) => setHubExpanded(card, true));
    });
    tools.querySelector("[data-settings-collapse]")?.addEventListener("click", () => {
        cards.filter((card) => !card.hidden).forEach((card) => setHubExpanded(card, false));
    });
    search.addEventListener("input", applyFilters);
    groupFilter.addEventListener("change", applyFilters);

    document.querySelectorAll("[data-settings-form]").forEach((form) => {
        const original = new FormData(form);
        const originalName = original.get("name");
        const originalParent = original.get("hub_id") || original.get("hub_group_id");
        form.addEventListener("submit", (event) => {
            const kind = form.dataset.confirmUpdate;
            if (kind) {
                const current = new FormData(form);
                const nameChanged = current.get("name") !== originalName;
                const parentChanged = (current.get("hub_id") || current.get("hub_group_id")) !== originalParent;
                if ((nameChanged || parentChanged) && !window.confirm(
                    `Save changes to this ${kind}? Existing directory relationships and future imports will use the updated setting.`
                )) {
                    event.preventDefault();
                    return;
                }
            }
            if (event.defaultPrevented) return;
            form.setAttribute("aria-busy", "true");
            form.querySelectorAll("button[type='submit']").forEach((button) => {
                button.disabled = true;
                button.dataset.originalLabel = button.textContent;
                button.textContent = form.hasAttribute("data-bulk-confirm") ? "Saving Records…" : "Working…";
            });
        });
    });

    applyFilters();
})();
