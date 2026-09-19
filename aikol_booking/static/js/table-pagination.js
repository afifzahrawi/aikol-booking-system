(function () {
    'use strict';

    const pageSize = 20;

    function visiblePages(current, total) {
        const pages = new Set([1, total, current - 1, current, current + 1]);
        return Array.from(pages).filter(page => page >= 1 && page <= total).sort((a, b) => a - b);
    }

    document.querySelectorAll('table[data-client-paginate]').forEach(table => {
        const rows = Array.from(table.tBodies[0] ? table.tBodies[0].rows : []);
        if (rows.length <= pageSize) return;

        const total = Math.ceil(rows.length / pageSize);
        const pager = document.createElement('nav');
        pager.className = 'pager pager-pages client-table-pager';
        pager.setAttribute('aria-label', table.dataset.paginationLabel || 'Table pagination');
        let current = 1;

        function button(label, page, className, active) {
            const control = document.createElement('button');
            control.type = 'button';
            control.className = className;
            control.textContent = label;
            control.disabled = active;
            if (active) control.setAttribute('aria-current', 'page');
            control.addEventListener('click', () => render(page));
            return control;
        }

        function render(page) {
            current = page;
            rows.forEach((row, index) => {
                row.hidden = index < (current - 1) * pageSize || index >= current * pageSize;
            });
            pager.replaceChildren();
            if (current > 1) pager.append(button('Previous', current - 1, 'pager-control', false));
            let previous = 0;
            visiblePages(current, total).forEach(number => {
                if (number - previous > 1) {
                    const ellipsis = document.createElement('span');
                    ellipsis.className = 'pager-ellipsis';
                    ellipsis.textContent = '…';
                    pager.append(ellipsis);
                }
                pager.append(button(String(number), number, 'pager-number', number === current));
                previous = number;
            });
            if (current < total) pager.append(button('Next', current + 1, 'pager-control', false));
        }

        (table.closest('.table-wrap') || table).insertAdjacentElement('afterend', pager);
        render(1);
    });
})();
