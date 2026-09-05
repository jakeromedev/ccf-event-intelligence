(() => {
    const modal = document.querySelector("[data-satellite-targets-modal]");
    if (!modal) return;

    const dialog = modal.querySelector(".satellite-target-dialog");
    const title = modal.querySelector("#satellite-target-modal-title");
    const form = modal.querySelector("[data-satellite-target-form]");
    let returnFocus = null;

    const open = (trigger) => {
        returnFocus = trigger;
        modal.hidden = false;
        document.body.classList.add("satellite-target-modal-open");
        requestAnimationFrame(() => title.focus());
    };

    const close = () => {
        modal.hidden = true;
        document.body.classList.remove("satellite-target-modal-open");
        returnFocus?.focus();
        returnFocus = null;
    };

    document.querySelectorAll("[data-satellite-targets-open]").forEach((trigger) => {
        trigger.addEventListener("click", () => open(trigger));
    });
    modal.querySelectorAll("[data-satellite-targets-close]").forEach((control) => {
        control.addEventListener("click", close);
    });
    modal.addEventListener("click", (event) => {
        if (event.target === dialog) return;
        if (event.target === modal) close();
    });
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && !modal.hidden) close();
    });
    form.addEventListener("submit", () => {
        const submit = form.querySelector('button[type="submit"]');
        submit.disabled = true;
        submit.textContent = submit.dataset.loadingLabel || "Saving…";
        form.setAttribute("aria-busy", "true");
    });
})();
