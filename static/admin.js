const adminToastContainer = document.getElementById("toast-container");

function showAdminToast(message, type = "success") {
    if (!adminToastContainer) return;

    const toast = document.createElement("div");
    toast.className = `toast toast--${type}`;
    toast.textContent = message;
    adminToastContainer.appendChild(toast);

    requestAnimationFrame(() => toast.classList.add("is-visible"));

    window.setTimeout(() => {
        toast.classList.remove("is-visible");
        window.setTimeout(() => toast.remove(), 300);
    }, 2000);
}

async function submitSectionForm(form) {
    const formData = new FormData(form);
    const payload = Object.fromEntries(formData.entries());
    payload.is_active = formData.get("is_active") === "on";

    const submitButton = form.querySelector("button[type='submit']");
    const saveMessage = form.dataset.saveMessage || "Saved";
    const saveError = form.dataset.saveError || "Save error";

    submitButton.disabled = true;

    try {
        const response = await fetch("/api/update-content", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify(payload),
        });
        const result = await response.json();

        if (!response.ok || !result.success) {
            throw new Error(result.message || saveError);
        }

        showAdminToast(result.message || saveMessage, "success");
        window.setTimeout(() => {
            window.location.reload();
        }, 500);
    } catch (error) {
        showAdminToast(error.message || saveError, "error");
    } finally {
        submitButton.disabled = false;
    }
}

async function submitAdminSettingsForm(form) {
    const formData = new FormData(form);
    const payload = Object.fromEntries(formData.entries());
    const submitButton = form.querySelector("button[type='submit']");
    const saveMessage = form.dataset.saveMessage || "Saved";
    const saveError = form.dataset.saveError || "Save error";

    submitButton.disabled = true;

    try {
        const response = await fetch("/api/update-admin-settings", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify(payload),
        });
        const result = await response.json();

        if (!response.ok || !result.success) {
            throw new Error(result.message || saveError);
        }

        showAdminToast(result.message || saveMessage, "success");
        form.querySelectorAll("input[type='password']").forEach((input) => {
            input.value = "";
        });
    } catch (error) {
        showAdminToast(error.message || saveError, "error");
    } finally {
        submitButton.disabled = false;
    }
}

document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".admin-filter-button").forEach((button) => {
        button.addEventListener("click", () => {
            const filter = button.dataset.pageFilter;
            document.querySelectorAll(".admin-filter-button").forEach((item) => {
                item.classList.toggle("is-active", item === button);
            });

            document.querySelectorAll(".admin-edit-card").forEach((card) => {
                const matches = filter === "all" || card.dataset.pageName === filter;
                card.hidden = !matches;
            });
        });
    });

    document.querySelectorAll(".admin-section-form").forEach((form) => {
        form.addEventListener("submit", (event) => {
            event.preventDefault();
            submitSectionForm(form);
        });
    });

    const newSectionForm = document.getElementById("new-section-form");
    if (newSectionForm) {
        newSectionForm.addEventListener("submit", (event) => {
            event.preventDefault();
            submitSectionForm(newSectionForm);
        });
    }

    const adminSettingsForm = document.getElementById("admin-settings-form");
    if (adminSettingsForm) {
        adminSettingsForm.addEventListener("submit", (event) => {
            event.preventDefault();
            submitAdminSettingsForm(adminSettingsForm);
        });
    }
});
