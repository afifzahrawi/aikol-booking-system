(function () {
    'use strict';

    // The room page's time picker. Tap a start time, then a later time to set
    // the end; the Request button carries the choice to the booking form,
    // which checks it again. Without this script the button still opens the
    // booking form, empty.
    const picker = document.querySelector('[data-picker]');
    if (!picker) return;
    const book = picker.querySelector('[data-picker-book]');
    const summary = picker.querySelector('[data-picker-summary]');
    const length = picker.querySelector('[data-picker-length]');
    const hint = picker.querySelector('[data-picker-hint]');
    const baseHref = book.getAttribute('href');
    let grid = picker.querySelector('[data-slots]:not([hidden])');
    let start = -1;
    let end = -1;
    let extending = false;

    function slots() { return Array.from(grid.querySelectorAll('button')); }

    function freeBetween(a, b) {
        return slots().slice(a, b).every(s => !s.disabled);
    }

    function paint() {
        slots().forEach((s, i) => {
            const inside = start >= 0 && i >= start && i < end;
            s.classList.toggle('in', inside);
            s.classList.toggle('edge', inside && (i === start || i === end - 1));
            s.setAttribute('aria-pressed', inside ? 'true' : 'false');
        });
        if (start < 0) {
            summary.textContent = 'Choose a free time';
            length.textContent = '';
            book.setAttribute('href', baseHref);
            book.setAttribute('aria-disabled', 'true');
            return;
        }
        const list = slots();
        const from = list[start].dataset.time;
        const to = list[end - 1].dataset.end;
        const date = grid.dataset.date;
        const day = picker.querySelector('[data-day][aria-pressed="true"]');
        const minutes = (end - start) * 30;
        summary.textContent = day.getAttribute('aria-label').split(',')[0] + ', ' + from + ' to ' + to;
        length.textContent = minutes >= 60 ? (minutes / 60) + (minutes === 60 ? ' hour' : ' hours') : minutes + ' minutes';
        book.setAttribute('href', baseHref + '?start_date=' + date + '&start_time=' + from + '&end_date=' + date + '&end_time=' + to);
        book.removeAttribute('aria-disabled');
        hint.textContent = extending ? 'Tap a later time to set when it ends.' : 'Tap a start time. Crossed out times are taken.';
    }

    picker.addEventListener('click', event => {
        const day = event.target.closest('[data-day]');
        if (day) {
            picker.querySelectorAll('[data-day]').forEach(d => d.setAttribute('aria-pressed', d === day ? 'true' : 'false'));
            picker.querySelectorAll('[data-slots]').forEach(g => { g.hidden = g.dataset.slots !== day.dataset.day; });
            grid = picker.querySelector('[data-slots="' + day.dataset.day + '"]');
            start = end = -1;
            extending = false;
            hint.textContent = 'Tap a start time. Crossed out times are taken.';
            paint();
            return;
        }
        const slot = event.target.closest('[data-slots] button');
        if (!slot || slot.disabled) return;
        const i = slots().indexOf(slot);
        if (extending && i >= start && freeBetween(start, i + 1)) {
            end = i + 1;
            extending = false;
        } else {
            // A first tap books an hour where the hour is free, so the common
            // case is one tap; a second tap stretches or shortens it.
            start = i;
            end = freeBetween(i, i + 2) && i + 2 <= slots().length ? i + 2 : i + 1;
            extending = true;
        }
        paint();
    });

    paint();
})();
