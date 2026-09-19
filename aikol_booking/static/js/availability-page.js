(function () {
    'use strict';

    const form = document.querySelector('[data-auto-submit]');
    const date = form && form.querySelector('input[type="date"]');
    if (!form || !date) return;

    date.addEventListener('change', () => {
        if (date.value) form.requestSubmit();
    });
})();
