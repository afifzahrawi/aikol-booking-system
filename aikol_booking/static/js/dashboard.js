(function () {
    'use strict';

    // The Venue and Vehicle switch on the home search. It sets the hidden
    // `kind` field and swaps the fields that differ: a car goes out one day
    // and may come back another, a room is booked within a day.
    var kind = document.querySelector('#resourceKind');
    if (!kind) return;

    var dateLabel = document.querySelector('[data-search-label="date"]');
    var fromLabel = document.querySelector('[data-search-label="from"]');
    var toLabel = document.querySelector('[data-search-label="to"]');
    var venueField = document.querySelector('[data-venue-search-field]');
    var vehicleField = document.querySelector('[data-vehicle-search-field]');
    var buttons = document.querySelectorAll('[data-kind]');

    function sync() {
        var vehicle = kind.value === 'VEHICLE';
        dateLabel.textContent = vehicle ? 'Leaving' : 'Date';
        fromLabel.textContent = vehicle ? 'At' : 'From';
        toLabel.textContent = vehicle ? 'Back by' : 'Until';
        venueField.hidden = vehicle;
        vehicleField.hidden = !vehicle;
        buttons.forEach(function (b) {
            b.setAttribute('aria-pressed', b.getAttribute('data-kind') === kind.value ? 'true' : 'false');
        });
    }

    buttons.forEach(function (b) {
        b.addEventListener('click', function () {
            kind.value = b.getAttribute('data-kind');
            sync();
        });
    });
    sync();
})();
