(function () {
    const root = document.documentElement;
    const phone = window.matchMedia("(max-width: 760px)");
    const storageKey = "ai-sales-sidebar-collapsed";

    function readSavedState() {
        if (phone.matches) return true;

        try {
            return localStorage.getItem(storageKey) === "true";
        } catch {
            return false;
        }
    }

    let collapsed = readSavedState();

    // Apply layout immediately, before the page content is displayed.
    root.classList.add("has-sidebar");
    root.classList.toggle("sidebar-collapsed", collapsed);

    function setupSidebar() {
        const sidebar = document.getElementById("main-sidebar");
        const button = document.querySelector(".sidebar-toggle");

        if (!sidebar || !button) return;

        function updateMenu(savePreference = false) {
            root.classList.toggle("sidebar-collapsed", collapsed);

            const label = collapsed ? "Open sidebar" : "Close sidebar";

            button.setAttribute("aria-expanded", String(!collapsed));
            button.setAttribute("aria-label", label);
            button.title = label;

            if (savePreference && !phone.matches) {
                try {
                    localStorage.setItem(storageKey, String(collapsed));
                } catch {
                    // The button still works without browser storage.
                }
            }
        }

        button.addEventListener("click", function () {
            collapsed = !collapsed;
            updateMenu(true);
        });

        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape" && !collapsed) {
                collapsed = true;
                updateMenu(true);
                button.focus();
            }
        });

        document.addEventListener("click", function (event) {
            if (
                phone.matches &&
                !collapsed &&
                !sidebar.contains(event.target)
            ) {
                collapsed = true;
                updateMenu();
            }
        });

        phone.addEventListener("change", function () {
            collapsed = readSavedState();
            updateMenu();
        });

        // Restore the current preference when returning with Back/Forward.
        window.addEventListener("pageshow", function (event) {
            if (event.persisted) {
                collapsed = readSavedState();
                updateMenu();
            }
        });

        updateMenu();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", setupSidebar, {
            once: true
        });
    } else {
        setupSidebar();
    }
})();