const toastContainer = document.getElementById("toast-container");

function showToast(message, type = "success") {
    if (!toastContainer) return;

    const toast = document.createElement("div");
    toast.className = `toast toast--${type}`;
    toast.textContent = message;
    toastContainer.appendChild(toast);

    requestAnimationFrame(() => {
        toast.classList.add("is-visible");
    });

    window.setTimeout(() => {
        toast.classList.remove("is-visible");
        window.setTimeout(() => toast.remove(), 300);
    }, 2000);
}

function setupThemeToggle() {
    const toggle = document.getElementById("theme-toggle");
    if (!toggle) return;

    const storedTheme = localStorage.getItem("ziyodev-theme") || "dark";
    document.body.dataset.theme = storedTheme;

    toggle.addEventListener("click", () => {
        const nextTheme = document.body.dataset.theme === "dark" ? "light" : "dark";
        document.body.dataset.theme = nextTheme;
        localStorage.setItem("ziyodev-theme", nextTheme);
    });
}

function setupContactForm() {
    const contactForm = document.getElementById("contact-form");
    if (!contactForm) return;

    contactForm.addEventListener("submit", async (event) => {
        event.preventDefault();

        const submitButton = contactForm.querySelector("button[type='submit']");
        const formData = new FormData(contactForm);
        const payload = Object.fromEntries(formData.entries());
        const submitLabel = contactForm.dataset.submitLabel || "Send";
        const loadingLabel = contactForm.dataset.loadingLabel || "Sending...";
        const fallbackSuccess = contactForm.dataset.successMessage || "Xabar yuborildi";
        const fallbackError = contactForm.dataset.errorMessage || "Xatolik yuz berdi";

        submitButton.disabled = true;
        submitButton.textContent = loadingLabel;

        try {
            const response = await fetch("/api/send-contact", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(payload),
            });
            const result = await response.json();

            if (!response.ok || !result.success) {
                throw new Error(result.message || fallbackError);
            }

            contactForm.reset();
            showToast(result.message || fallbackSuccess, "success");
            if (result.warning_human) {
                window.setTimeout(() => showToast(result.warning_human, "error"), 300);
            }
        } catch (error) {
            showToast(error.message || fallbackError, "error");
        } finally {
            submitButton.disabled = false;
            submitButton.textContent = submitLabel;
        }
    });
}

function appendChatBubble(container, message, type) {
    const bubble = document.createElement("div");
    bubble.className = `chat-bubble ${type === "user" ? "chat-bubble--user" : "chat-bubble--ai"}`;
    bubble.textContent = message;
    container.appendChild(bubble);
    container.scrollTop = container.scrollHeight;
    return bubble;
}

function setupChatWidget() {
    const chatWidget = document.getElementById("chat-widget");
    const chatToggle = document.getElementById("chat-toggle");
    const chatClose = document.getElementById("chat-close");
    const chatPanel = document.getElementById("chat-panel");
    const chatForm = document.getElementById("chat-form");
    const chatInput = document.getElementById("chat-input");
    const chatMessages = document.getElementById("chat-messages");

    if (!chatWidget || !chatToggle || !chatClose || !chatPanel || !chatForm || !chatInput || !chatMessages) {
        return;
    }

    const typingLabel = chatWidget.dataset.chatTyping || "Typing...";
    const errorLabel = chatWidget.dataset.chatError || "Something went wrong.";

    const openPanel = () => {
        chatWidget.classList.add("is-open");
        chatPanel.hidden = false;
        chatPanel.setAttribute("aria-hidden", "false");
        chatInput.focus();
    };

    const closePanel = () => {
        chatWidget.classList.remove("is-open");
        chatPanel.hidden = true;
        chatPanel.setAttribute("aria-hidden", "true");
    };

    closePanel();

    chatToggle.addEventListener("click", () => {
        if (chatWidget.classList.contains("is-open")) {
            closePanel();
        } else {
            openPanel();
        }
    });

    chatClose.addEventListener("click", () => {
        closePanel();
    });

    chatForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const message = chatInput.value.trim();
        if (!message) return;

        appendChatBubble(chatMessages, message, "user");
        chatInput.value = "";
        chatInput.disabled = true;

        const loadingBubble = appendChatBubble(chatMessages, typingLabel, "ai");

        try {
            const response = await fetch("/api/chat", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ message }),
            });
            const result = await response.json();

            if (!response.ok || !result.success) {
                throw new Error(result.message || errorLabel);
            }

            loadingBubble.remove();
            appendChatBubble(chatMessages, result.reply, "ai");
        } catch (error) {
            loadingBubble.remove();
            appendChatBubble(chatMessages, error.message || errorLabel, "ai");
        } finally {
            chatInput.disabled = false;
            if (!chatPanel.hidden) {
                chatInput.focus();
            }
        }
    });
}

document.addEventListener("DOMContentLoaded", () => {
    setupThemeToggle();
    setupContactForm();
    setupChatWidget();
});
