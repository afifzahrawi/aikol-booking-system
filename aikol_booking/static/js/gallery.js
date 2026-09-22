(function () {
    'use strict';

    // Thumbnails swap the photograph at the front. Left and right arrows move
    // between them once one has focus, so the gallery is usable without a
    // mouse; without this file every photograph is still on the page.
    document.querySelectorAll('[data-gallery]').forEach(function (gallery) {
        const main = gallery.querySelector('[data-gallery-main]');
        const caption = gallery.querySelector('[data-gallery-caption]');
        const thumbs = Array.from(gallery.querySelectorAll('[data-gallery-thumb]'));
        if (!main || thumbs.length < 2) return;

        function show(index, moveFocus) {
            const thumb = thumbs[index];
            if (!thumb) return;
            main.src = thumb.dataset.full;
            const picture = thumb.querySelector('img');
            main.alt = picture ? picture.alt : '';
            thumbs.forEach(function (other) {
                other.setAttribute('aria-current', other === thumb ? 'true' : 'false');
            });
            if (caption) {
                const words = thumb.dataset.caption;
                caption.textContent = (thumb.dataset.position || '') + (words ? '. ' + words : '');
            }
            if (moveFocus) thumb.focus();
        }

        thumbs.forEach(function (thumb, index) {
            thumb.addEventListener('click', function () { show(index, false); });
            thumb.addEventListener('keydown', function (event) {
                if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
                event.preventDefault();
                const step = event.key === 'ArrowRight' ? 1 : -1;
                show((index + step + thumbs.length) % thumbs.length, true);
            });
        });
    });
})();
