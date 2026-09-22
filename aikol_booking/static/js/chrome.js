/* The navigation toggle on narrow screens.

   The bar is a plain row of links without this file; the toggle only collapses
   it below the width where they stop fitting. Nothing here is required to
   navigate. */

(function () {
    'use strict';
    var nav = document.querySelector('.app-nav');
    if (!nav) return;
    var toggle = nav.querySelector('.nav-toggle');
    if (!toggle) return;
    var shell = document.querySelector('.docket-shell');
    var desktop = window.matchMedia('(min-width: 64rem)');
    var label = toggle.querySelector('.nav-toggle-label');
    var masthead = document.querySelector('.docket-masthead');

    function syncMastheadHeight() {
        if (!masthead) return;
        shell.style.setProperty('--masthead-h', masthead.getBoundingClientRect().height + 'px');
    }


    function setDesktopState(collapsed) {
        shell.classList.toggle('nav-collapsed', collapsed);
        nav.classList.remove('open');
        toggle.setAttribute('aria-expanded', String(!collapsed));
        toggle.setAttribute('aria-label', collapsed ? 'Expand navigation' : 'Collapse navigation');
        if (label) label.textContent = collapsed ? 'Expand' : 'Collapse';
    }

    function syncMode() {
        if (desktop.matches) {
            setDesktopState(sessionStorage.getItem('aikol-nav-collapsed') === 'true');
        } else {
            shell.classList.remove('nav-collapsed');
            nav.classList.remove('open');
            toggle.setAttribute('aria-expanded', 'false');
            toggle.setAttribute('aria-label', 'Open navigation menu');
            if (label) label.textContent = 'Menu';
        }
    }

    toggle.addEventListener('click', function () {
        if (desktop.matches) {
            var collapsed = !shell.classList.contains('nav-collapsed');
            sessionStorage.setItem('aikol-nav-collapsed', String(collapsed));
            setDesktopState(collapsed);
            return;
        }
        var open = nav.classList.toggle('open');
        toggle.setAttribute('aria-expanded', String(open));
        toggle.setAttribute('aria-label', open ? 'Close navigation menu' : 'Open navigation menu');
    });

    if (desktop.addEventListener) desktop.addEventListener('change', syncMode);
    else desktop.addListener(syncMode);
    if (window.ResizeObserver && masthead) {
        new ResizeObserver(syncMastheadHeight).observe(masthead);
    } else {
        window.addEventListener('resize', syncMastheadHeight);
    }
    syncMastheadHeight();
    syncMode();

    // A time field with a quarter-hour step still accepts a typed 13:16: the
    // step drives the arrows only. The value is rounded here as soon as it is
    // entered, so the form's own rule almost never has to refuse anything.
    document.addEventListener('change', function (event) {
        var field = event.target;
        if (!field.matches || !field.matches('input[type="time"][step="900"]')) return;
        var parts = /^(\d{1,2}):(\d{2})/.exec(field.value || '');
        if (!parts) return;
        var minutes = Number(parts[2]);
        var rounded = Math.round(minutes / 15) * 15;
        var hour = Number(parts[1]) + (rounded === 60 ? 1 : 0);
        if (hour > 23) { hour = 23; rounded = 45; }
        if (rounded === 60) rounded = 0;
        if (minutes === rounded) return;
        field.value = String(hour).padStart(2, '0') + ':' + String(rounded).padStart(2, '0');
    });

    document.querySelectorAll('[data-history-back]').forEach(function (link) {
        link.addEventListener('click', function (event) {
            // Going back one entry is right only when the entry behind is a
            // different page. A form that posts and redirects to itself, or a
            // dialog that reloads the page, leaves the same URL behind: Back
            // then appeared to do nothing and had to be pressed twice. In that
            // case the link's own href, the section this page belongs to, is
            // the honest destination.
            if (!document.referrer) return;
            var previous = new URL(document.referrer, window.location.href);
            if (previous.origin !== window.location.origin) return;
            var here = window.location.href.split('#')[0];
            if (previous.href.split('#')[0] === here) return;
            if (window.history.length > 1) {
                event.preventDefault();
                window.history.back();
            }
        });
    });

    var actionMenus = Array.prototype.slice.call(document.querySelectorAll('.action-menu'));

    function closeActionMenus(except) {
        actionMenus.forEach(function (details) {
            if (details !== except) details.open = false;
        });
    }

    function positionActionMenu(details) {
        var trigger = details.querySelector('summary');
        var menu = details.querySelector('.action-menu-list');
        if (!trigger || !menu) return;
        var rect = trigger.getBoundingClientRect();
        var gap = 6;
        var edge = 8;
        var width = menu.offsetWidth;
        var height = menu.offsetHeight;
        var left = Math.max(edge, Math.min(window.innerWidth - width - edge, rect.right - width));
        var top = rect.bottom + gap;
        if (top + height > window.innerHeight - edge) {
            top = Math.max(edge, rect.top - height - gap);
            menu.style.transformOrigin = 'bottom right';
        } else {
            menu.style.transformOrigin = 'top right';
        }
        menu.style.setProperty('--menu-left', left + 'px');
        menu.style.setProperty('--menu-top', top + 'px');
    }

    actionMenus.forEach(function (details) {
        details.addEventListener('toggle', function () {
            if (!details.open) return;
            closeActionMenus(details);
            window.requestAnimationFrame(function () { positionActionMenu(details); });
        });
    });

    document.addEventListener('click', function (event) {
        if (!event.target.closest('.action-menu')) closeActionMenus();
    });
    document.addEventListener('keydown', function (event) {
        if (event.key !== 'Escape') return;
        var openMenu = document.querySelector('.action-menu[open]');
        if (!openMenu) return;
        openMenu.open = false;
        openMenu.querySelector('summary').focus();
    });
    window.addEventListener('resize', function () { closeActionMenus(); });
    window.addEventListener('scroll', function () { closeActionMenus(); }, true);
})();

/* A print button. Inline handlers are refused by the Content-Security-Policy,
   so the one page that offers printing marks its button with data-print. */
(function () {
    'use strict';
    document.querySelectorAll('[data-print]').forEach(function (button) {
        button.addEventListener('click', function () { window.print(); });
    });
})();

/* Bars sized by data. A style attribute is refused by the Content-Security-
   Policy, so the template writes the measurement as data and this applies it
   through the CSSOM, which the policy allows. Applied after first paint, the
   bars grow into place instead of appearing already drawn. */
(function () {
    'use strict';
    function apply() {
        document.querySelectorAll('[data-width]').forEach(function (el) { el.style.width = el.getAttribute('data-width') + '%'; });
        document.querySelectorAll('[data-height]').forEach(function (el) { el.style.height = el.getAttribute('data-height') + '%'; });
        document.querySelectorAll('[data-left]').forEach(function (el) { el.style.left = el.getAttribute('data-left') + '%'; });
    }
    if (window.requestAnimationFrame) requestAnimationFrame(function () { requestAnimationFrame(apply); });
    else apply();
})();

/* Data tables become stacked records below the desktop width (redesign.css).
   Each cell is labelled with its column heading, copied here so no template
   has to repeat its own headers, and the table's roles are stated explicitly
   because display: block would otherwise take them away. */
(function () {
    'use strict';
    document.querySelectorAll('table.data').forEach(function (table) {
        var headers = Array.prototype.map.call(table.querySelectorAll('thead th'), function (th) {
            return th.textContent.replace(/\s+/g, ' ').trim();
        });
        if (!headers.length) return;
        table.setAttribute('role', 'table');
        table.querySelectorAll('thead, tbody').forEach(function (g) { g.setAttribute('role', 'rowgroup'); });
        table.querySelectorAll('tr').forEach(function (tr) { tr.setAttribute('role', 'row'); });
        table.querySelectorAll('thead th').forEach(function (th) { th.setAttribute('role', 'columnheader'); });
        table.querySelectorAll('tbody tr').forEach(function (tr) {
            var column = 0;
            Array.prototype.forEach.call(tr.children, function (td) {
                td.setAttribute('role', 'cell');
                var span = parseInt(td.getAttribute('colspan') || '1', 10);
                if (span === 1 && headers[column] && !td.hasAttribute('data-label')) {
                    td.setAttribute('data-label', headers[column]);
                }
                column += span;
            });
        });
    });
})();

/* An error summary is announced and focused, so the first thing a keyboard or
   screen-reader user meets after a failed submit is the list of what to fix. */
(function () {
    'use strict';
    var summary = document.querySelector('.form-error-summary');
    if (summary) summary.focus({ preventScroll: false });
})();
