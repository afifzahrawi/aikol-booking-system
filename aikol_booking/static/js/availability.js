/* Live availability on the booking form.

   PROGRESSIVE ENHANCEMENT, and the word matters here. This tells somebody the
   slot is taken before they fill in the rest of the form; it decides nothing.
   The server checks the same period again inside a transaction with a row lock,
   and the database has an exclusion constraint underneath that. If this file
   fails to load, is blocked, or lies, the booking is still refused correctly —
   the only thing lost is finding out sooner.

   Nothing is submitted from here and no state is changed: it is a GET against a
   read-only endpoint. */

(function () {
    'use strict';
    var form = document.getElementById('bookingForm');
    if (!form) return;
    var status = document.getElementById('slotStatus');
    var endpoint = form.dataset.availability;
    if (!status || !endpoint) return;

    var fields = ['start_date', 'start_time', 'end_date', 'end_time']
        .map(function (n) { return form.querySelector('[name="' + n + '"]'); })
        .filter(Boolean);

    var timer = null;
    var controller = null;

    function values() {
        var v = {};
        fields.forEach(function (f) { v[f.name] = f.value; });
        v.end_date = v.end_date || v.start_date;
        return v;
    }

    function say(text, kind) {
        status.textContent = text;
        status.className = 'notice notice-' + kind;
        status.hidden = false;
    }

    function check() {
        var v = values();
        if (!v.start_date || !v.start_time || !v.end_time) { status.hidden = true; return; }

        /* One request at a time: a fast typist would otherwise race several and
           render whichever happened to land last. */
        if (controller) controller.abort();
        controller = new AbortController();

        var query = new URLSearchParams({
            start_date: v.start_date, start_time: v.start_time,
            end_date: v.end_date, end_time: v.end_time
        });
        fetch(endpoint + '?' + query, {
            signal: controller.signal,
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (data) {
                if (!data) { status.hidden = true; return; }
                if (data.problems && data.problems.length) {
                    say(data.problems.join(' '), 'warn');
                } else if (data.free) {
                    say('That period looks free. The office still has to approve it.', 'info');
                } else {
                    say(data.message, 'warn');
                }
            })
            .catch(function (err) {
                /* An aborted request is the expected case, not a fault. Any
                   other failure is silent: the server is the authority and it
                   will answer on submit. */
                if (err.name !== 'AbortError') status.hidden = true;
            });
    }

    fields.forEach(function (f) {
        f.addEventListener('change', function () {
            clearTimeout(timer);
            timer = setTimeout(check, 250);
        });
    });
})();
