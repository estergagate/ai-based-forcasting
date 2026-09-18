(function () {
    const storageKey = "ai-sales-theme";
    const root = document.documentElement;

    function readTheme() {
        try {
            return localStorage.getItem(storageKey) === "dark"
                ? "dark"
                : "light";
        } catch {
            return "light";
        }
    }

    // Apply the saved colors before the page appears.
    root.dataset.theme = readTheme();

    function setupThemeButton() {
        const button = document.getElementById("theme-toggle");

        function updateButton() {
            if (!button) return;

            const darkEnabled = root.dataset.theme === "dark";

            button.setAttribute("aria-pressed", String(darkEnabled));
            button.title = darkEnabled
                ? "Turn dark mode off"
                : "Turn dark mode on";

                const label = button.querySelector(".theme-toggle-text");

if (label) {
    label.textContent = darkEnabled ? "Dark mode" : "Light mode";
}
        }

        if (button) {
            button.addEventListener("click", function () {
                root.dataset.theme = root.dataset.theme === "dark"
                    ? "light"
                    : "dark";

                try {
                    localStorage.setItem(storageKey, root.dataset.theme);
                } catch {
                    // Switching still works without browser storage.
                }

                updateButton();
            });
        }

        window.addEventListener("storage", function (event) {
            if (event.key === storageKey || event.key === null) {
                root.dataset.theme = readTheme();
                updateButton();
            }
        });

        window.addEventListener("pageshow", function (event) {
            if (event.persisted) {
                root.dataset.theme = readTheme();
                updateButton();
            }
        });

        updateButton();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", setupThemeButton, {
            once: true
        });
    } else {
        setupThemeButton();
    }
})();