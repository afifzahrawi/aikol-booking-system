/* The heatmap's hover and focus readout.

   `title` alone is not enough: it never appears on touch, it takes a second to
   appear on desktop, and a keyboard user never sees it at all. The value is
   announced here in a live region under the grid instead, and every cell is
   focusable so the grid can be read by tabbing as well as by pointing.

   The page is complete without this file. Colour still encodes the value, each
   cell still carries visually-hidden text for a screen reader, and the title
   attribute still works — this only makes the reading quicker. */

(function () {
    'use strict';
    var table = document.getElementById('heat');
    var readout = document.getElementById('heatRead');
    if (!table || !readout) return;

    var resting = readout.textContent;

    function describe(cell) {
        var row = cell.closest('tr');
        var day = row.querySelector('th').textContent.trim();
        var hour = cell.dataset.hour;
        var value = Number(cell.dataset.value);
        readout.textContent = day + ' ' + hour + ':00\u2013' + (Number(hour) + 1) + ':00 \u00b7 ' +
            (value > 0 ? value + ' room-hours booked' : 'nothing booked');
    }

    table.addEventListener('mouseover', function (e) {
        var cell = e.target.closest('td[data-hour]');
        if (cell) describe(cell);
    });
    table.addEventListener('focusin', function (e) {
        var cell = e.target.closest('td[data-hour]');
        if (cell) describe(cell);
    });
    table.addEventListener('mouseleave', function () { readout.textContent = resting; });
})();
