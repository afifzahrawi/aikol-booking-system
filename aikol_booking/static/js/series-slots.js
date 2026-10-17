(function () {
    'use strict';

    // Each weekday can hold up to three times. Without this script every slot
    // is shown; with it, the extra slots stay out of the way until "Add
    // another time" is pressed, and any slot already filled in stays visible.
    document.querySelectorAll('[data-dow-day]').forEach(function (day) {
        const tick = day.querySelector('input[type="checkbox"]');
        const add = day.querySelector('[data-dow-add]');
        const extras = Array.from(day.querySelectorAll('[data-dow-extra]'));
        if (!add || !extras.length) return;

        extras.forEach(function (row) {
            if (!row.hasAttribute('data-filled')) row.hidden = true;
        });

        function refresh() {
            const more = extras.some(function (row) { return row.hidden; });
            add.hidden = !(tick && tick.checked) || !more;
        }

        add.addEventListener('click', function () {
            const row = extras.find(function (r) { return r.hidden; });
            if (!row) return;
            row.hidden = false;
            const first = row.querySelector('select, input');
            if (first) first.focus();
            refresh();
        });
        if (tick) tick.addEventListener('change', refresh);
        refresh();
    });
})();
