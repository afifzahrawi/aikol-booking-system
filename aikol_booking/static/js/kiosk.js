(function () {
    'use strict';

    // The kiosk's number pad types into the booking number field, so the PC
    // works with a touch screen as well as a keyboard. Without this script the
    // pad stays hidden and the field is typed into as usual.
    const pad = document.querySelector('[data-keypad]');
    const form = document.querySelector('[data-kiosk-form]');
    if (pad && form) {
        const input = form.querySelector('input[name="reference"]');
        pad.hidden = false;
        pad.addEventListener('click', event => {
            const key = event.target.closest('[data-key]');
            if (!key) return;
            const value = key.dataset.key;
            if (value === 'clear') input.value = '';
            else if (value === 'back') input.value = input.value.slice(0, -1);
            else if (input.value.length < 20) input.value += value;
            // Four digits is a whole short number: go straight on.
            if (/^\d{4}$/.test(input.value) && value !== 'back' && value !== 'clear') form.requestSubmit();
        });
    }

    // After a record, the thank-you screen returns to the start by itself so
    // the next person finds the kiosk ready.
    if (document.querySelector('[data-kiosk-reset]')) {
        setTimeout(() => { window.location.replace(window.location.pathname); }, 6000);
    }
})();
