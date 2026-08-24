(() => {
    const toggle = document.querySelector("[data-sidebar-toggle]");
    const sidebar = document.querySelector("#application-sidebar");
    if (!toggle || !sidebar) return;

    const mobile = () => window.matchMedia("(max-width: 780px)").matches;

    sidebar.querySelectorAll("[data-nav-group]").forEach((group) => {
        const groupToggle = group.querySelector("[data-nav-group-toggle]");
        const submenu = group.querySelector(".nav-submenu");
        if (!groupToggle || !submenu) return;

        const setExpanded = (expanded) => {
            group.classList.toggle("expanded", expanded);
            groupToggle.setAttribute("aria-expanded", String(expanded));
            submenu.setAttribute("aria-hidden", String(!expanded));
            submenu.querySelectorAll("a").forEach((link) => {
                if (expanded) link.removeAttribute("tabindex");
                else link.setAttribute("tabindex", "-1");
            });
        };

        setExpanded(group.classList.contains("expanded"));
        groupToggle.addEventListener("click", () => {
            if (!mobile() && document.body.classList.contains("sidebar-collapsed")) {
                document.body.classList.remove("sidebar-collapsed");
                toggle.setAttribute("aria-expanded", "true");
                setExpanded(true);
                return;
            }
            setExpanded(!group.classList.contains("expanded"));
        });
    });

    if (mobile()) toggle.setAttribute("aria-expanded", "false");

    function closeMobileNavigation() {
        document.body.classList.remove("sidebar-open");
        toggle.setAttribute("aria-expanded", "false");
    }

    toggle.addEventListener("click", () => {
        if (mobile()) {
            const open = document.body.classList.toggle("sidebar-open");
            toggle.setAttribute("aria-expanded", String(open));
            return;
        }
        const collapsed = document.body.classList.toggle("sidebar-collapsed");
        toggle.setAttribute("aria-expanded", String(!collapsed));
    });

    sidebar.querySelectorAll("a").forEach((link) => {
        link.addEventListener("click", () => {
            if (mobile()) closeMobileNavigation();
        });
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && document.body.classList.contains("sidebar-open")) {
            closeMobileNavigation();
            toggle.focus();
        }
    });

    window.addEventListener("resize", () => {
        if (!mobile()) document.body.classList.remove("sidebar-open");
        toggle.setAttribute(
            "aria-expanded",
            String(mobile() ? document.body.classList.contains("sidebar-open") : !document.body.classList.contains("sidebar-collapsed"))
        );
    });
})();
