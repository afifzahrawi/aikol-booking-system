/* Reorderable table rows.

   The handle is a real <button>, so the order can be changed from the keyboard
   as well as by pointer — dragging alone would leave the feature unusable
   without a mouse. Every move posts the WHOLE visible order, and the server
   rewrites display_order as 1..n, so there are never gaps or ties.

   The page works without this file: the rows read and edit normally, and only
   the reordering shortcut is missing. */

(function () {
    'use strict';
    const tbody = document.getElementById('rows');
    const form = document.getElementById('reorderForm');
    const field = document.getElementById('orderField');
    if (!tbody || !form || !field) return;

    let draggingId = null;

    const rows = () => Array.from(tbody.querySelectorAll('tr[data-id]'));
    const ids = () => rows().map(r => r.dataset.id);

    function clearMarks() {
        rows().forEach(r => r.classList.remove('drop-above', 'drop-below'));
    }

    function commit() {
        field.value = ids().join(',');
        form.submit();
    }

    tbody.addEventListener('dragstart', e => {
        const tr = e.target.closest('tr[data-id]');
        if (!tr || tr.querySelector('.draghandle').disabled) { e.preventDefault(); return; }
        draggingId = tr.dataset.id;
        tr.classList.add('dragging');
        tbody.classList.add('reordering');
        e.dataTransfer.effectAllowed = 'move';
        /* Firefox refuses to start a drag without a payload. */
        e.dataTransfer.setData('text/plain', draggingId);
    });

    tbody.addEventListener('dragover', e => {
        if (draggingId === null) return;
        const tr = e.target.closest('tr[data-id]');
        if (!tr || tr.dataset.id === draggingId) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        const box = tr.getBoundingClientRect();
        clearMarks();
        tr.classList.add((e.clientY - box.top) < box.height / 2 ? 'drop-above' : 'drop-below');
    });

    tbody.addEventListener('drop', e => {
        if (draggingId === null) return;
        const target = e.target.closest('tr[data-id]');
        if (!target) return;
        e.preventDefault();
        const moved = tbody.querySelector('tr[data-id="' + draggingId + '"]');
        const above = target.classList.contains('drop-above');
        clearMarks();
        tbody.classList.remove('reordering');
        target.parentNode.insertBefore(moved, above ? target : target.nextSibling);
        draggingId = null;
        commit();
    });

    tbody.addEventListener('dragend', () => {
        clearMarks();
        tbody.classList.remove('reordering');
        rows().forEach(r => r.classList.remove('dragging'));
        draggingId = null;
    });

    /* The keyboard equivalent. Dragging is the quick way; this is the one that
       has to exist. */
    tbody.addEventListener('keydown', e => {
        if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return;
        const handle = e.target.closest('.draghandle');
        if (!handle || handle.disabled) return;
        e.preventDefault();
        const tr = handle.closest('tr');
        const sibling = e.key === 'ArrowUp' ? tr.previousElementSibling : tr.nextElementSibling;
        if (!sibling || !sibling.dataset.id) return;
        if (e.key === 'ArrowUp') tr.parentNode.insertBefore(tr, sibling);
        else tr.parentNode.insertBefore(sibling, tr);
        commit();
    });
})();
