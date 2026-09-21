(() => {
    const controls = document.querySelector("[data-trend-controls]");
    if (!controls) return;

    const charts = Array.from(document.querySelectorAll("[data-trend-chart]"));
    const buttons = Array.from(controls.querySelectorAll("[data-trend-period]"));
    const heading = document.querySelector("[data-trend-title]");
    const tooltip = document.querySelector("[data-trend-tooltip]");
    const periods = { daily: "day", weekly: "week", monthly: "month" };

    const resizeChart = (chart) => {
        const width = Math.round(chart.getBoundingClientRect().width);
        if (!width) return;
        const svg = chart.querySelector("svg");
        const points = Array.from(chart.querySelectorAll("[data-trend-point]"));
        const plotLeft = 56;
        const plotWidth = Math.max(1, width - plotLeft - 18);
        svg.setAttribute("viewBox", `0 0 ${width} 250`);
        svg.setAttribute("width", width);
        chart.querySelectorAll("[data-trend-grid]").forEach((grid) => {
            grid.setAttribute("x2", width - 18);
        });
        const coordinates = points.map((point, index) => {
            const x = points.length === 1 ? plotLeft + plotWidth / 2 :
                plotLeft + index * plotWidth / (points.length - 1);
            point.setAttribute("cx", x);
            return `${x},${point.getAttribute("cy")}`;
        });
        chart.querySelector("[data-trend-line]").setAttribute("points", coordinates.join(" "));

        const availableLabels = Math.max(2, Math.floor(plotWidth / 75));
        let labelStep = Math.ceil(points.length / availableLabels);
        if (chart.dataset.trendChart === "daily") {
            labelStep = Math.max(7, Math.ceil(labelStep / 7) * 7);
        }
        chart.querySelectorAll("[data-trend-label]").forEach((label) => {
            const index = Number(label.dataset.index);
            const visible = index === 0 || index === points.length - 1 || index % labelStep === 0;
            label.style.display = visible ? "" : "none";
            if (visible) label.setAttribute("x", points[index].getAttribute("cx"));
        });
    };

    const hideTooltip = () => { tooltip.hidden = true; };
    const positionTooltip = (x, y) => {
        const bounds = tooltip.getBoundingClientRect();
        tooltip.style.left = `${Math.max(8, Math.min(x + 12, window.innerWidth - bounds.width - 8))}px`;
        tooltip.style.top = `${Math.max(8, y - bounds.height - 12)}px`;
    };
    const showTooltip = (point, x, y) => {
        const count = Number(point.dataset.count);
        const label = point.dataset.period === "weekly" ? "Week of " :
            point.dataset.period === "monthly" ? "Month of " : "";
        const date = new Date(`${point.dataset.date}T00:00:00`).toLocaleDateString("en-US", {
            month: "short", day: "2-digit", year: "numeric",
        });
        tooltip.textContent = `${label}${date} · ${count.toLocaleString()} registration${count === 1 ? "" : "s"}`;
        tooltip.hidden = false;
        positionTooltip(x, y);
    };

    buttons.forEach((button) => {
        button.addEventListener("click", () => {
            const selected = button.dataset.trendPeriod;
            buttons.forEach((item) => item.setAttribute("aria-pressed", String(item === button)));
            charts.forEach((chart) => {
                chart.hidden = chart.dataset.trendChart !== selected;
                if (!chart.hidden) resizeChart(chart);
            });
            heading.textContent = `Registrations per ${periods[selected]}`;
            hideTooltip();
        });
    });

    document.querySelectorAll("[data-trend-point]").forEach((point) => {
        point.querySelector("title")?.remove();
        point.addEventListener("pointerenter", (event) => showTooltip(point, event.clientX, event.clientY));
        point.addEventListener("pointermove", (event) => positionTooltip(event.clientX, event.clientY));
        point.addEventListener("pointerleave", hideTooltip);
        point.addEventListener("focus", () => {
            const bounds = point.getBoundingClientRect();
            showTooltip(point, bounds.left + bounds.width / 2, bounds.top);
        });
        point.addEventListener("blur", hideTooltip);
    });

    const resizeVisibleChart = () => charts.forEach((chart) => {
        if (!chart.hidden) resizeChart(chart);
    });
    resizeVisibleChart();
    if ("ResizeObserver" in window) {
        new ResizeObserver(resizeVisibleChart).observe(controls.closest(".phase1-weekly"));
    } else {
        window.addEventListener("resize", resizeVisibleChart);
    }
})();
