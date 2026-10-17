(function () {
    'use strict';

    // Bookings calendar. Choosing a booking opens its details beside the
    // board instead of leaving the page; without this script each block is an
    // ordinary link to the booking. The filters apply as soon as they change.
    const panel = document.getElementById('cal-peek');
    let current = null;

    function open(id, trigger) {
        const source = document.getElementById('peek-' + id);
        if (!panel || !source) return false;
        document.querySelectorAll('.cal-ev.is-selected').forEach(el => el.classList.remove('is-selected'));
        document.querySelectorAll('[data-peek="' + id + '"]').forEach(el => el.classList.add('is-selected'));
        panel.replaceChildren(source.content.cloneNode(true));
        // Replaying the entrance makes a change of booking visible.
        panel.hidden = false;
        panel.style.animation = 'none';
        void panel.offsetWidth;
        panel.style.animation = '';
        current = trigger || null;
        const close = panel.querySelector('[data-peek-close]');
        if (close) close.focus({preventScroll: true});
        return true;
    }

    function close() {
        if (!panel) return;
        panel.hidden = true;
        panel.replaceChildren();
        document.querySelectorAll('.cal-ev.is-selected').forEach(el => el.classList.remove('is-selected'));
        if (current) current.focus();
        current = null;
    }

    document.addEventListener('click', event => {
        const block = event.target.closest('[data-peek]');
        if (block && !event.metaKey && !event.ctrlKey && !event.shiftKey) {
            if (open(block.dataset.peek, block)) event.preventDefault();
            return;
        }
        const listed = event.target.closest('[data-peek-open]');
        if (listed && document.getElementById('peek-' + listed.dataset.peekOpen)) {
            event.preventDefault();
            open(listed.dataset.peekOpen, listed);
            return;
        }
        if (event.target.closest('[data-peek-close]')) { close(); return; }
        // A click anywhere else on the page puts the drawer away, except in a
        // dialog the drawer itself opened (Decline).
        if (panel && !panel.hidden && !panel.contains(event.target) && !event.target.closest('dialog')) close();
    });
    if (panel) {
        panel.addEventListener('keydown', event => { if (event.key === 'Escape') close(); });
    }

    const initial = document.querySelector('[data-initial-peek]');
    if (initial && initial.dataset.initialPeek) open(initial.dataset.initialPeek, null);

    document.querySelectorAll('form[data-autosubmit]').forEach(form => {
        const button = form.querySelector('[data-autosubmit-button]');
        if (button) button.hidden = true;
        form.querySelectorAll('input[type="checkbox"]').forEach(box => {
            box.addEventListener('change', () => form.requestSubmit());
        });
    });
})();
