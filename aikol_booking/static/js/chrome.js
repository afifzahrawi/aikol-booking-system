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
    toggle.addEventListener('click', function () {
        var open = nav.classList.toggle('open');
        toggle.setAttribute('aria-expanded', String(open));
    });
})();
