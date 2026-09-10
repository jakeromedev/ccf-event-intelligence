(() => {
    window.confirmAction = (options) => {
        if (Swal.isVisible()) return Promise.resolve({isDismissed: true});
        return Swal.fire({
            icon: "question",
            showCancelButton: true,
            cancelButtonText: "Cancel",
            confirmButtonColor: "#9f272b",
            denyButtonColor: "#475569",
            focusCancel: true,
            allowOutsideClick: false,
            keydownListenerCapture: true,
            ...options,
        });
    };
    document.addEventListener("submit", async (event) => {
        const form = event.target.closest("form[data-confirm-message]");
        if (!form || form.dataset.confirmed === "true") return;
        event.preventDefault();
        const result = await window.confirmAction({
            titleText: "Delete import batch?",
            text: form.dataset.confirmMessage,
            icon: "warning",
            confirmButtonText: "Delete batch",
        });
        if (result.isConfirmed && form.isConnected) {
            form.dataset.confirmed = "true";
            form.requestSubmit(event.submitter);
        }
    });
})();
