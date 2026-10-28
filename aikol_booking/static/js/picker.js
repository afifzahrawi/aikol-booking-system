/* The venue and vehicle picker.

   The filter form is an ordinary GET form and works without this script. With
   it, every change fetches the results only and swaps them in, so filtering
   feels immediate and the address bar always holds a link to what is shown.
   It also remembers Grid or List for this browser and opens collapsed
   building groups. */
(function () {
    'use strict';
    var form = document.querySelector('[data-picker-form]');
    var region = document.querySelector('[data-picker-results]');
    if (!form || !region) return;

    var STORE = 'aikol-picker-view';
    var typingTimer = null;
    var pending = null;

    function chosenView() {
        try { return localStorage.getItem(STORE); } catch (e) { return null; }
    }

    // Sets up whatever results are on the page: the view switch and the
    // Show all buttons. Called on load and after every swap.
    function prepare() {
        var results = region.querySelector('.picker-results');
        var switcher = region.querySelector('.picker-view');
        if (!results || !switcher) return;
        var view = chosenView() || switcher.getAttribute('data-default-view');
        results.setAttribute('data-view', view);
        switcher.hidden = false;
        switcher.querySelectorAll('[data-view]').forEach(function (button) {
            button.setAttribute('aria-pressed', String(button.getAttribute('data-view') === view));
        });
        region.querySelectorAll('[data-show-all]').forEach(function (button) {
            button.hidden = false;
        });
    }

    function load(url) {
        if (pending) pending.abort();
        pending = new AbortController();
        region.classList.add('is-loading');
        fetch(url, { headers: { 'X-Picker': 'results' }, signal: pending.signal, credentials: 'same-origin' })
            .then(function (response) {
                if (!response.ok) throw new Error(response.status);
                return response.text();
            })
            .then(function (html) {
                var swap = function () { region.innerHTML = html; prepare(); };
                if (document.startViewTransition && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
                    document.startViewTransition(swap);
                } else {
                    swap();
                }
                window.history.replaceState(null, '', url);
            })
            .catch(function (error) {
                // A newer request replaced this one; nothing to do.
                if (error.name === 'AbortError') return;
                // Anything else: fall back to an ordinary page load.
                window.location.href = url;
            })
            .finally(function () { region.classList.remove('is-loading'); });
    }

    function submit() {
        var params = new URLSearchParams(new FormData(form));
        // The checkbox sends nothing when off; say so, or the server reads a
        // first visit and turns it back on.
        if (!params.has('free')) params.set('free', '0');
        load(form.action.split('?')[0] + '?' + params.toString());
    }

    form.addEventListener('submit', function (event) {
        event.preventDefault();
        submit();
    });
    form.addEventListener('change', function (event) {
        if (event.target.matches('input[type="search"], input[type="number"]')) return;
        submit();
    });
    // Typing waits for a short pause, so each keystroke is not a request.
    form.addEventListener('input', function (event) {
        if (!event.target.matches('input[type="search"], input[type="number"]')) return;
        window.clearTimeout(typingTimer);
        typingTimer = window.setTimeout(submit, 280);
    });

    region.addEventListener('click', function (event) {
        var viewButton = event.target.closest('.picker-view [data-view]');
        if (viewButton) {
            try { localStorage.setItem(STORE, viewButton.getAttribute('data-view')); } catch (e) { /* storage blocked */ }
            prepare();
            return;
        }
        var more = event.target.closest('[data-show-all]');
        if (more) more.closest('.picker-group').classList.add('is-open');
    });

    prepare();
}());
