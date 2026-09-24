/* Restores the collapsed navigation rail before the page is first painted.

   Loaded without defer in <head>, so it runs before the body exists: it only
   sets a class on <html>. chrome.js, deferred, owns the toggle itself. Doing
   this after paint drew the rail open and then animated it shut on every page. */
(function () {
    'use strict';
    try {
        if (window.matchMedia('(min-width: 64rem)').matches
                && sessionStorage.getItem('aikol-nav-collapsed') === 'true') {
            document.documentElement.classList.add('nav-collapsed');
        }
    } catch (e) { /* storage blocked: the rail simply starts open */ }
}());
