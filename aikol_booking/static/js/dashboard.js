(function () {
    'use strict';

    var kind = document.querySelector('#resourceKind');
    if (!kind) return;

    var dateLabel = document.querySelector('[data-search-label="date"]');
    var fromLabel = document.querySelector('[data-search-label="from"]');
    var toLabel = document.querySelector('[data-search-label="to"]');
    var venueField = document.querySelector('[data-venue-search-field]');
    var vehicleField = document.querySelector('[data-vehicle-search-field]');

    function syncSearchFields() {
        var vehicle = kind.value === 'VEHICLE';
        dateLabel.textContent = vehicle ? 'Collection date' : 'Date';
        fromLabel.textContent = vehicle ? 'Collection time' : 'From';
        toLabel.textContent = vehicle ? 'Return time' : 'To';
        venueField.hidden = vehicle;
        vehicleField.hidden = !vehicle;
    }

    kind.addEventListener('change', syncSearchFields);
    syncSearchFields();
})();
