(function () {
    'use strict';

    // Refuse an oversized file here, where the person can still do something
    // about it. The server refuses it too, but only after the whole file has
    // travelled, and a request larger than the platform's ceiling never gets
    // an answer at all, which looks like the screen doing nothing.
    function megabytes(bytes) {
        return (bytes / 1024 / 1024).toFixed(1);
    }

    function check(input) {
        const limit = Number(input.dataset.maxBytes || 0);
        if (!limit || !input.files || !input.files.length) return true;
        const field = input.closest('.field') || input.parentElement;
        const existing = field.querySelector('.upload-limit-error');
        const tooBig = Array.from(input.files).filter(file => file.size > limit);
        if (!tooBig.length) {
            if (existing) existing.remove();
            return true;
        }
        const notice = existing || document.createElement('p');
        notice.className = 'notice notice-error upload-limit-error';
        notice.setAttribute('role', 'alert');
        const named = tooBig.map(file => `${file.name} is ${megabytes(file.size)} MB`).join(', ');
        notice.textContent =
            `${named}. The limit is ${megabytes(limit)} MB per file, so nothing was attached. ` +
            'Choose a smaller file, or reduce this one and try again.';
        if (!existing) field.appendChild(notice);
        input.value = '';
        return false;
    }

    function wire(root) {
        root.querySelectorAll('input[type="file"][data-max-bytes]').forEach(input => {
            if (input.dataset.limitWired) return;
            input.dataset.limitWired = '1';
            input.addEventListener('change', () => check(input));
            const form = input.form;
            if (form && !form.dataset.limitWired) {
                form.dataset.limitWired = '1';
                form.addEventListener('submit', event => {
                    const inputs = Array.from(form.querySelectorAll('input[type="file"][data-max-bytes]'));
                    if (!inputs.every(check)) event.preventDefault();
                });
            }
        });
    }

    wire(document);
    document.addEventListener('aikol:modal-content', event => wire(event.detail.root));
})();
