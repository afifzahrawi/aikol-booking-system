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

    document.querySelectorAll('[data-history-back]').forEach(function (link) {
        link.addEventListener('click', function (event) {
            var previousIsLocal = false;
            if (document.referrer) {
                previousIsLocal = new URL(document.referrer).origin === window.location.origin;
            }
            if (previousIsLocal && window.history.length > 1) {
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
