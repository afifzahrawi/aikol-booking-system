(function () {
    'use strict';

    // The chart reloads when the date or either time changes; the times ride
    // along in the query string and reach every Book link on the page.
    const form = document.querySelector('[data-auto-submit]');
    if (!form) return;
    form.querySelectorAll('input[type="date"], input[type="time"]').forEach(function (input) {
        input.addEventListener('change', function () {
            if (input.type === 'time' || input.value) form.requestSubmit();
        });
    });
})();
