(() => {
    const dialogs = [...document.querySelectorAll("[data-user-management-dialog]")];
    if (!dialogs.length) return;

    let returnFocus = null;

    const closeDialog = (dialog) => {
        dialog.close();
        if (returnFocus?.isConnected) returnFocus.focus();
        returnFocus = null;
    };

    document.querySelectorAll("[data-user-management-open]").forEach((trigger) => {
        trigger.addEventListener("click", () => {
            const dialog = document.getElementById(trigger.dataset.userManagementOpen);
            if (!dialog) return;
            returnFocus = trigger;
            dialog.showModal();
            requestAnimationFrame(() => {
                dialog.querySelector("input:not([type='hidden']), select")?.focus();
            });
        });
    });

    dialogs.forEach((dialog) => {
        dialog.querySelectorAll("[data-user-management-close]").forEach((button) => {
            button.addEventListener("click", () => closeDialog(dialog));
        });
        dialog.addEventListener("click", (event) => {
            if (event.target === dialog) closeDialog(dialog);
        });
        dialog.addEventListener("close", () => {
            if (returnFocus?.isConnected) returnFocus.focus();
            returnFocus = null;
        });
    });
})();
