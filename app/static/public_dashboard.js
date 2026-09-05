(() => {
    const navigation = document.querySelector("[data-public-dashboard-nav]");
    if (!navigation) return;

    const links = Array.from(
        navigation.querySelectorAll("[data-dashboard-nav-link]")
    );
    const sections = links
        .map((link) => document.querySelector(link.hash))
        .filter(Boolean);

    const selectLink = (sectionId) => {
        links.forEach((link) => {
            const selected = link.hash === `#${sectionId}`;
            link.classList.toggle("active", selected);
            if (selected) {
                link.setAttribute("aria-current", "location");
                link.scrollIntoView({ block: "nearest", inline: "center" });
            } else {
                link.removeAttribute("aria-current");
            }
        });
    };

    const reducedMotion = window.matchMedia(
        "(prefers-reduced-motion: reduce)"
    ).matches;
    links.forEach((link) => {
        link.addEventListener("click", (event) => {
            const target = document.getElementById(link.hash.slice(1));
            if (!target) return;
            event.preventDefault();
            target.scrollIntoView({
                behavior: reducedMotion ? "auto" : "smooth",
                block: "start",
            });
            window.history.replaceState(null, "", link.hash);
            selectLink(target.id);
        });
    });

    if (!("IntersectionObserver" in window) || !sections.length) {
        if (sections[0]) selectLink(sections[0].id);
        return;
    }

    const visibleSections = new Map();
    const observer = new IntersectionObserver(
        (entries) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) {
                    visibleSections.set(entry.target.id, entry.intersectionRatio);
                } else {
                    visibleSections.delete(entry.target.id);
                }
            });
            const active = sections
                .filter((section) => visibleSections.has(section.id))
                .sort(
                    (left, right) =>
                        Math.abs(left.getBoundingClientRect().top) -
                        Math.abs(right.getBoundingClientRect().top)
                )[0];
            if (active) selectLink(active.id);
        },
        { rootMargin: "-18% 0px -62% 0px", threshold: [0, 0.1, 0.5] }
    );
    sections.forEach((section) => observer.observe(section));
    const initialSection = sections.find(
        (section) => `#${section.id}` === window.location.hash
    );
    selectLink(initialSection ? initialSection.id : sections[0].id);
})();
