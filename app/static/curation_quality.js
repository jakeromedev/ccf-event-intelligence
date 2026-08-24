(() => {
    const modal = document.querySelector("[data-curation-modal]");
    if (!modal) return;

    const title = modal.querySelector("[data-curation-title]");
    const subtitle = modal.querySelector("[data-curation-subtitle]");
    const body = modal.querySelector("[data-curation-body]");
    let trigger = null;

    const node = (tag, className, text) => {
        const element = document.createElement(tag);
        if (className) element.className = className;
        if (text !== undefined) element.textContent = text;
        return element;
    };

    const value = (input) => input === null || input === undefined || input === "" ? "—" : String(input);

    function detailsGrid(items) {
        const grid = node("dl", "curation-detail-grid");
        items.forEach(([label, content]) => {
            const row = node("div");
            row.append(node("dt", "", label), node("dd", "", value(content)));
            grid.append(row);
        });
        return grid;
    }

    function table(headers, rows) {
        const wrap = node("div", "table-wrap");
        const result = node("table", "curation-table");
        const head = node("thead");
        const heading = node("tr");
        headers.forEach((header) => heading.append(node("th", "", header)));
        head.append(heading);
        const tbody = node("tbody");
        rows.forEach((values) => {
            const row = node("tr");
            values.forEach((content) => row.append(node("td", "", value(content))));
            tbody.append(row);
        });
        result.append(head, tbody);
        wrap.append(result);
        return wrap;
    }

    function renderRegistrant(data) {
        const curated = data.curated_registrant;
        title.textContent = curated.last_name || "Curated Registrant";
        subtitle.textContent = `${curated.source_registrant_count} source registration${curated.source_registrant_count === 1 ? "" : "s"} linked to this unique person.`;
        body.replaceChildren(
            detailsGrid([
                ["Normalized last name", curated.normalized_last_name],
                ["Birth month", curated.normalized_birth_month],
                ["Birth year", curated.normalized_birth_year],
                ["Gender", curated.normalized_gender],
                ["Match key", curated.dedupe_key],
                ["Identity status", curated.dedupe_complete ? "Complete" : `Incomplete — ${curated.missing_identity_fields}`],
                ["Registration type", curated.registration_type_conflict ? `${curated.registration_type} (source conflict)` : curated.registration_type],
                ["Curated check-in", curated.checked_in ? "Checked in" : "Not checked in"],
                ["Satellites", curated.satellite_count],
            ]),
            node("h3", "curation-detail-section-title", "Source Registrations"),
            table(
                ["Registration Code", "Source ID", "Registrant", "Satellite", "Registration Type", "Check-In"],
                data.source_registrations.map((source) => [
                    source.registration_code,
                    source.source_id,
                    [source.first_name, source.last_name].filter(Boolean).join(" ") || "Name unavailable",
                    source.satellite_name || source.affiliation,
                    source.registration_type,
                    source.checked_in ? "Checked in" : "Not checked in",
                ])
            )
        );
    }

    function renderSatellite(data) {
        const satellite = data.satellite;
        title.textContent = satellite.name;
        subtitle.textContent = `${satellite.curated_registrants} unique registrant association${satellite.curated_registrants === 1 ? "" : "s"}.`;
        body.replaceChildren(
            detailsGrid([
                ["Normalized as", satellite.name],
                ["Normalized key", satellite.normalized_name],
                ["Affiliation", satellite.affiliation],
                ["Raw associations", satellite.source_record_count],
            ]),
            node("h3", "curation-detail-section-title", "Detected Source Values"),
            table(
                ["Source Value", "Normalized Source Value", "Affiliation", "Records"],
                data.source_variations.map((variation) => [
                    variation.source_value,
                    variation.normalized_source_value,
                    variation.affiliation,
                    variation.source_record_count,
                ])
            )
        );
    }

    async function openDetail(button) {
        trigger = button;
        modal.hidden = false;
        document.body.classList.add("registrant-modal-open");
        title.textContent = "Curation Details";
        subtitle.textContent = "Loading audit trail…";
        body.replaceChildren(node("div", "registrant-table-state", "Loading…"));
        modal.querySelector("[data-curation-close]").focus();
        try {
            const response = await fetch(button.dataset.curationUrl, {headers: {Accept: "application/json"}});
            if (!response.ok) throw new Error("Unable to load this active-batch record.");
            const data = await response.json();
            if (button.dataset.curationKind === "satellite") renderSatellite(data);
            else renderRegistrant(data);
        } catch (error) {
            subtitle.textContent = "The curation audit trail could not be loaded.";
            body.replaceChildren(node("div", "registrant-table-state", error.message));
        }
    }

    function closeDetail() {
        modal.hidden = true;
        document.body.classList.remove("registrant-modal-open");
        if (trigger) trigger.focus();
    }

    document.querySelectorAll("[data-curation-url]").forEach((button) => {
        button.addEventListener("click", () => openDetail(button));
    });
    modal.querySelectorAll("[data-curation-close]").forEach((button) => button.addEventListener("click", closeDetail));
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && !modal.hidden) closeDetail();
    });
})();
