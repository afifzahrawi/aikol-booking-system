(function () {
    'use strict';

    // Venue photographs are all 4:3. Before upload, each chosen photograph is
    // shown in a 4:3 frame: drag it, or use the arrow keys, to choose what is
    // kept, and the slider to zoom. The server centre-crops anything that
    // arrives another shape, so skipping this step is safe, only less precise.
    const panel = document.querySelector('[data-crop-ratio]');
    if (!panel || !window.DataTransfer || !window.HTMLDialogElement) return;
    const input = panel.querySelector('input[type="file"]');
    if (!input) return;

    const OUT_W = 1600;
    const OUT_H = 1200;
    const VIEW_W = 800;
    const VIEW_H = 600;

    const dialog = document.createElement('dialog');
    dialog.className = 'crop-dialog';
    dialog.innerHTML =
        '<h2 class="crop-title">Crop the Photograph</h2>' +
        '<p class="help crop-help">Drag the photograph, or use the arrow keys, to choose what to keep. ' +
        'Venue photographs are always 4:3.</p>' +
        '<canvas class="crop-canvas" width="' + VIEW_W + '" height="' + VIEW_H + '" tabindex="0" ' +
        'aria-label="Crop area. Use the arrow keys to move the photograph."></canvas>' +
        '<label class="crop-zoom">Zoom <input type="range" min="1" max="3" step="0.01" value="1"></label>' +
        '<p class="help crop-count"></p>' +
        '<div class="btn-group">' +
        '<button type="button" class="btn" data-crop="skip">Use without cropping</button>' +
        '<button type="button" class="btn btn-primary" data-crop="use">Use this crop</button>' +
        '</div>';
    document.body.appendChild(dialog);

    const canvas = dialog.querySelector('canvas');
    const ctx = canvas.getContext('2d');
    const zoomInput = dialog.querySelector('input[type="range"]');
    const count = dialog.querySelector('.crop-count');

    let queue = [];
    let done = [];
    let total = 0;
    let image = null;
    let file = null;
    let zoom = 1;
    let offsetX = 0;
    let offsetY = 0;
    let busy = false;

    function baseScale() {
        // The smallest scale at which the photograph still fills the frame.
        return Math.max(VIEW_W / image.width, VIEW_H / image.height);
    }

    function clamp() {
        const scale = baseScale() * zoom;
        const w = image.width * scale;
        const h = image.height * scale;
        offsetX = Math.min(0, Math.max(VIEW_W - w, offsetX));
        offsetY = Math.min(0, Math.max(VIEW_H - h, offsetY));
    }

    function draw() {
        clamp();
        const scale = baseScale() * zoom;
        ctx.clearRect(0, 0, VIEW_W, VIEW_H);
        ctx.drawImage(image, offsetX, offsetY, image.width * scale, image.height * scale);
    }

    function centre() {
        const scale = baseScale() * zoom;
        offsetX = (VIEW_W - image.width * scale) / 2;
        offsetY = (VIEW_H - image.height * scale) / 2;
    }

    function next() {
        if (!queue.length) {
            dialog.close();
            const carrier = new DataTransfer();
            done.forEach(f => carrier.items.add(f));
            busy = true;
            input.files = carrier.files;
            busy = false;
            return;
        }
        file = queue.shift();
        count.textContent = total > 1 ? 'Photograph ' + (total - queue.length) + ' of ' + total : '';
        const url = URL.createObjectURL(file);
        const img = new Image();
        img.onload = function () {
            URL.revokeObjectURL(url);
            image = img;
            zoom = 1;
            zoomInput.value = '1';
            centre();
            draw();
            if (!dialog.open) dialog.showModal();
            canvas.focus();
        };
        img.onerror = function () {
            // Not readable here; let the server give the proper error.
            URL.revokeObjectURL(url);
            done.push(file);
            next();
        };
        img.src = url;
    }

    input.addEventListener('change', function () {
        if (busy || !input.files.length) return;
        queue = Array.from(input.files);
        done = [];
        total = queue.length;
        next();
    });

    zoomInput.addEventListener('input', function () {
        // Zoom about the centre of the frame, so the subject stays put.
        const before = baseScale() * zoom;
        const cx = (VIEW_W / 2 - offsetX) / before;
        const cy = (VIEW_H / 2 - offsetY) / before;
        zoom = parseFloat(zoomInput.value);
        const after = baseScale() * zoom;
        offsetX = VIEW_W / 2 - cx * after;
        offsetY = VIEW_H / 2 - cy * after;
        draw();
    });

    let dragging = null;
    canvas.addEventListener('pointerdown', function (event) {
        const ratio = VIEW_W / canvas.getBoundingClientRect().width;
        dragging = {x: event.clientX, y: event.clientY, ox: offsetX, oy: offsetY, ratio: ratio};
        canvas.setPointerCapture(event.pointerId);
    });
    canvas.addEventListener('pointermove', function (event) {
        if (!dragging) return;
        offsetX = dragging.ox + (event.clientX - dragging.x) * dragging.ratio;
        offsetY = dragging.oy + (event.clientY - dragging.y) * dragging.ratio;
        draw();
    });
    canvas.addEventListener('pointerup', function () { dragging = null; });
    canvas.addEventListener('keydown', function (event) {
        const step = event.shiftKey ? 40 : 10;
        const moves = {ArrowLeft: [step, 0], ArrowRight: [-step, 0], ArrowUp: [0, step], ArrowDown: [0, -step]};
        const move = moves[event.key];
        if (!move) return;
        event.preventDefault();
        offsetX += move[0];
        offsetY += move[1];
        draw();
    });

    dialog.addEventListener('click', function (event) {
        const choice = event.target.closest('[data-crop]');
        if (!choice) return;
        if (choice.dataset.crop === 'skip') {
            done.push(file);
            next();
            return;
        }
        const out = document.createElement('canvas');
        out.width = OUT_W;
        out.height = OUT_H;
        const factor = OUT_W / VIEW_W;
        const scale = baseScale() * zoom * factor;
        out.getContext('2d').drawImage(
            image, offsetX * factor, offsetY * factor, image.width * scale, image.height * scale
        );
        out.toBlob(function (blob) {
            const stem = file.name.replace(/\.[^.]+$/, '');
            done.push(new File([blob], stem + '.jpg', {type: 'image/jpeg'}));
            next();
        }, 'image/jpeg', 0.9);
    });

    // Escape keeps the photographs uncropped rather than losing the choice.
    dialog.addEventListener('cancel', function (event) {
        event.preventDefault();
        done.push(file);
        next();
    });
})();
