(() => {
    const dialog = document.querySelector("[data-dashboard-config-dialog]");
    let returnFocus = null;

    const copyText = async (value) => {
        if (navigator.clipboard && window.isSecureContext) {
            await navigator.clipboard.writeText(value);
            return;
        }

        const input = document.createElement("textarea");
        input.value = value;
        input.setAttribute("readonly", "");
        input.style.position = "fixed";
        input.style.opacity = "0";
        document.body.appendChild(input);
        input.select();
        document.execCommand("copy");
        input.remove();
    };

    document.querySelectorAll("[data-dashboard-copy-link]").forEach((button) => {
        const originalLabel = button.textContent.trim();
        button.addEventListener("click", async () => {
            try {
                await copyText(button.dataset.copyValue);
                button.textContent = "Copied";
            } catch (_error) {
                button.textContent = "Copy failed";
            }
            window.setTimeout(() => {
                button.textContent = originalLabel;
            }, 1800);
        });
    });

    if (!dialog) return;

    const form = dialog.querySelector("form");
    const firstField = dialog.querySelector("[data-dashboard-config-first]");
    const password = dialog.querySelector("[data-dashboard-password]");
    const confirmation = dialog.querySelector("[data-dashboard-password-confirmation]");
    const disablePublic = dialog.querySelector("[data-dashboard-disable-public]");
    const passwordFields = dialog.querySelector("[data-dashboard-password-fields]");

    const openDialog = (trigger = null) => {
        returnFocus = trigger || document.activeElement;
        if (!dialog.open) dialog.showModal();
        window.requestAnimationFrame(() => firstField?.focus());
    };

    const closeDialog = () => {
        if (dialog.open) dialog.close();
    };

    document.querySelectorAll("[data-dashboard-config-open]").forEach((button) => {
        button.addEventListener("click", () => openDialog(button));
    });
    dialog.querySelectorAll("[data-dashboard-config-close]").forEach((button) => {
        button.addEventListener("click", closeDialog);
    });
    dialog.addEventListener("click", (event) => {
        if (event.target === dialog) closeDialog();
    });
    dialog.addEventListener("close", () => {
        if (returnFocus instanceof HTMLElement && returnFocus.isConnected) returnFocus.focus();
    });

    dialog.querySelectorAll("[data-password-toggle]").forEach((button) => {
        const input = button.closest(".dashboard-config-password")?.querySelector("input");
        if (!input) return;
        button.addEventListener("click", () => {
            const showing = input.type === "text";
            input.type = showing ? "password" : "text";
            button.textContent = showing ? "Show" : "Hide";
            button.setAttribute("aria-label", `${showing ? "Show" : "Hide"} password`);
        });
    });

    const validatePasswordConfirmation = () => {
        if (!confirmation || !password) return;
        const mismatched = confirmation.value !== password.value && confirmation.value.length > 0;
        confirmation.setCustomValidity(mismatched ? "Passwords must match." : "");
    };
    password?.addEventListener("input", validatePasswordConfirmation);
    confirmation?.addEventListener("input", validatePasswordConfirmation);

    const syncDisabledState = () => {
        if (!disablePublic || !passwordFields) return;
        const disabled = disablePublic.checked;
        passwordFields.classList.toggle("is-disabled", disabled);
        passwordFields.querySelectorAll("input, button").forEach((control) => {
            control.disabled = disabled;
        });
        if (disabled) confirmation?.setCustomValidity("");
        else validatePasswordConfirmation();
    };
    disablePublic?.addEventListener("change", syncDisabledState);
    syncDisabledState();

    form?.addEventListener("submit", () => {
        form.setAttribute("aria-busy", "true");
        const submit = form.querySelector('[type="submit"]');
        if (submit) {
            submit.disabled = true;
            submit.textContent = submit.dataset.loadingLabel || "Saving…";
        }
    });

    if (dialog.dataset.openOnLoad === "true") openDialog();
})();
