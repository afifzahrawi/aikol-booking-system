/* Insights: switch topics without reloading, print, and show a semester as
   soon as it is picked.

   The page works without this file: each topic is a link that reloads with
   ?tab=, and the semester form has its own Show button. */

(function () {
    'use strict';

    var tabs = document.querySelectorAll('.insight-tabs [data-pane]');
    tabs.forEach(function (tab) {
        tab.addEventListener('click', function (e) {
            if (e.metaKey || e.ctrlKey || e.shiftKey) return;
            e.preventDefault();
            var name = tab.getAttribute('data-pane');
            tabs.forEach(function (t) {
                if (t === tab) t.setAttribute('aria-current', 'page');
                else t.removeAttribute('aria-current');
            });
            document.querySelectorAll('[data-pane-body]').forEach(function (pane) {
                pane.hidden = pane.getAttribute('data-pane-body') !== name;
            });
            // Keep the address in step so a refresh or a shared link opens here.
            history.replaceState(null, '', tab.getAttribute('href'));
        });
    });

    document.querySelectorAll('[data-print]').forEach(function (button) {
        button.addEventListener('click', function () { window.print(); });
    });

    document.querySelectorAll('select[data-autosubmit]').forEach(function (select) {
        var form = select.form;
        var show = form.querySelector('[data-autosubmit-hide]');
        if (show) show.hidden = true;
        select.addEventListener('change', function () { form.submit(); });
    });
})();
