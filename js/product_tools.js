(() => {
    const start = () => {
        if (window.foodcastProductToolsReady) return;
        window.foodcastProductToolsReady = true;
        const confirm = document.getElementById('action-confirm');
        const no = document.getElementById('confirm-no');
        const yes = document.getElementById('confirm-yes');
        const manager = document.getElementById('unit-manager');
        const picker = document.getElementById('unit-picker');
        let pending = null;
        let origin = null;

        function ask(message, action) {
            if (!confirm || confirm.open) return;
            origin = document.activeElement;
            pending = action;
            document.getElementById('confirm-message').textContent = message;
            confirm.showModal();
            no.focus();
        }
        no?.addEventListener('click', () => confirm.close());
        yes?.addEventListener('click', () => {
            const action = pending;
            pending = null;
            confirm.close();
            action?.();
        });
        confirm?.addEventListener('close', () => {
            pending = null;
            if (origin?.isConnected) origin.focus();
        });

        // Confirm every existing sign-out form without changing its CSRF protection.
        document.addEventListener('submit', event => {
            const form = event.target;
            if (!(form instanceof HTMLFormElement)) return;
            if (form.dataset.confirmed === 'yes') {
                delete form.dataset.confirmed;
                return;
            }
            const path = new URL(form.action, location.href).pathname;
            if (path.endsWith('/logout')) {
                event.preventDefault();
                const submitter = event.submitter;
                ask('Do you want to sign out?', () => {
                    form.dataset.confirmed = 'yes';
                    submitter ? form.requestSubmit(submitter) : form.requestSubmit();
                });
            }
        });

        document.addEventListener('click', event => {
            const pick = event.target.closest('[data-pick-unit]');
            if (pick) {
                document.getElementById('chosen-unit').value = pick.dataset.pickUnit;
                document.getElementById('unit-choice').textContent = pick.dataset.pickUnit;
                picker.open = false;
                picker.querySelector('summary').focus();
            }
            const remove = event.target.closest('[data-delete-unit]');
            if (remove) {
                ask(`Delete the unit “${remove.dataset.unitName}”?`, () => {
                    const form = document.getElementById('delete-unit-form');
                    form.elements.unit_id.value = remove.dataset.deleteUnit;
                    form.requestSubmit();
                });
            }
            if (event.target.closest('[data-open-units]')) {
                if (picker) picker.open = false;
                manager?.showModal();
                document.getElementById('new-unit')?.focus();
            }
            if (event.target.closest('[data-close-units]')) manager?.close();
            if (picker && !picker.contains(event.target)) picker.open = false;
        });
        document.addEventListener('keydown', event => {
            if (event.key === 'Escape' && picker?.open) {
                picker.open = false;
                picker.querySelector('summary').focus();
            }
        });
    };
    document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', start) : start();
})();
