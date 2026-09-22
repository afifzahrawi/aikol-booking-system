(function () {
    'use strict';

    // No standing dashed box: the page shows where to drop only while
    // something is being dragged over it. Dropping anywhere on the page fills
    // the upload field, which is what people try first.
    const panel = document.querySelector('[data-image-drop]');
    if (!panel) return;
    const input = panel.querySelector('input[type="file"]');
    if (!input || !window.DataTransfer) return;

    const overlay = document.createElement('div');
    overlay.className = 'image-drop-overlay';
    overlay.hidden = true;
    overlay.innerHTML = '<span>Drop the photographs to add them</span>';
    document.body.appendChild(overlay);

    let depth = 0;

    function carriesFiles(event) {
        return Array.from(event.dataTransfer && event.dataTransfer.types || []).includes('Files');
    }

    function show(on) {
        overlay.hidden = !on;
        if (!on) depth = 0;
    }

    window.addEventListener('dragenter', event => {
        if (!carriesFiles(event)) return;
        depth += 1;
        show(true);
    });
    window.addEventListener('dragover', event => {
        if (carriesFiles(event)) event.preventDefault();
    });
    window.addEventListener('dragleave', () => {
        depth -= 1;
        if (depth <= 0) show(false);
    });
    window.addEventListener('drop', event => {
        if (!carriesFiles(event)) return;
        event.preventDefault();
        show(false);
        const images = Array.from(event.dataTransfer.files).filter(file => file.type.startsWith('image/'));
        if (!images.length) return;
        const carrier = new DataTransfer();
        images.forEach(file => carrier.items.add(file));
        input.files = carrier.files;
        input.dispatchEvent(new Event('change', {bubbles: true}));
        panel.scrollIntoView({behavior: 'smooth', block: 'center'});
    });
})();
