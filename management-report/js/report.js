/* ============================================================================
   AIKOL Room Booking System — Management Report behaviour

   Charts are drawn with plain HTML and CSS. No charting library is loaded, so
   the report opens and prints correctly with no internet connection and no
   third-party dependency to maintain. (Chart.js was considered; see section 15
   of the report for the reasoning behind this decision.)

   EVERY figure below is ILLUSTRATIVE. No actual AIKOL measurement is used.
   ========================================================================= */
(function () {
    'use strict';

    /* ---------- 1. Illustrative chart data -------------------------------- */

    // Number of distinct steps a requester and the office must complete.
    // Illustrative comparison, derived from the assumed manual workflow.
    const PROCESS_STEPS = {
        labels: ['Requester steps', 'Office steps', 'Hand-offs', 'Waiting points'],
        current: [7, 6, 4, 3],
        proposed: [4, 1, 1, 1]
    };

    // Example booking volume for a hypothetical academic year.
    const MONTHLY_VOLUME = [
        { label: 'Sep', value: 88 }, { label: 'Oct', value: 124 }, { label: 'Nov', value: 142 },
        { label: 'Dec', value: 61 }, { label: 'Jan', value: 118 }, { label: 'Feb', value: 136 },
        { label: 'Mar', value: 151 }, { label: 'Apr', value: 129 }, { label: 'May', value: 97 },
        { label: 'Jun', value: 54 }, { label: 'Jul', value: 72 }, { label: 'Aug', value: 83 }
    ];

    // Example distribution of bookings across venue types.
    const VENUE_UTILISATION = [
        { label: 'Moot Court Room', value: 218 },
        { label: 'Lecture Room 1', value: 186 },
        { label: 'Seminar Room 1', value: 154 },
        { label: 'Seminar Room 2', value: 131 },
        { label: 'Meeting Room A', value: 96 },
        { label: 'Discussion Room 1', value: 74 },
        { label: 'Meeting Room B', value: 58 }
    ];

    // Example growth of stored booking records, to illustrate the case for
    // indexing, pagination and a retention policy.
    const RECORD_GROWTH = [
        { label: 'Year 1', value: 1200 }, { label: 'Year 2', value: 2500 },
        { label: 'Year 3', value: 3900 }, { label: 'Year 4', value: 5400 },
        { label: 'Year 5', value: 7000 }
    ];

    // Proposed implementation roadmap, in weeks from project start.
    const ROADMAP = [
        { phase: 'Phase 1', name: 'Discovery and management review', start: 0, weeks: 2, cls: 'phase-1' },
        { phase: 'Phase 2', name: 'UI prototype and requirement confirmation', start: 1, weeks: 2, cls: 'phase-1' },
        { phase: 'Phase 3', name: 'Database and authentication', start: 3, weeks: 2, cls: '' },
        { phase: 'Phase 4', name: 'Venue management', start: 5, weeks: 2, cls: '' },
        { phase: 'Phase 5', name: 'Booking system and conflict prevention', start: 6, weeks: 3, cls: '' },
        { phase: 'Phase 6', name: 'Administrative features', start: 9, weeks: 2, cls: '' },
        { phase: 'Phase 7', name: 'Bulk data, reporting and retention', start: 11, weeks: 2, cls: '' },
        { phase: 'Phase 8', name: 'Testing and security review', start: 13, weeks: 2, cls: 'phase-2' },
        { phase: 'Phase 9', name: 'User acceptance testing', start: 15, weeks: 2, cls: 'phase-2' },
        { phase: 'Phase 10', name: 'Deployment and training', start: 17, weeks: 2, cls: 'phase-2' }
    ];

    /* ---------- 2. Chart renderers ---------------------------------------- */

    function groupedBars(host, cfg) {
        const max = Math.max.apply(null, cfg.current.concat(cfg.proposed)) || 1;
        host.classList.add('bars');
        host.innerHTML = cfg.labels.map((lab, i) =>
            '<div class="col" style="flex:2">' +
            '<div style="display:flex;gap:.25rem;align-items:flex-end;width:100%;height:100%">' +
            '<div class="bar alt" style="height:' + (cfg.current[i] / max * 100) + '%">' +
            '<span class="v">' + cfg.current[i] + '</span></div>' +
            '<div class="bar" style="height:' + (cfg.proposed[i] / max * 100) + '%">' +
            '<span class="v">' + cfg.proposed[i] + '</span></div>' +
            '</div><div class="lab">' + lab + '</div></div>').join('');
    }

    function bars(host, data) {
        const max = Math.max.apply(null, data.map(d => d.value)) || 1;
        host.classList.add('bars');
        host.innerHTML = data.map(d =>
            '<div class="col"><div class="bar" style="height:' + (d.value / max * 100) + '%">' +
            '<span class="v">' + d.value + '</span></div><div class="lab">' + d.label + '</div></div>').join('');
    }

    function hbars(host, data, suffix) {
        const max = Math.max.apply(null, data.map(d => d.value)) || 1;
        host.classList.add('hbars');
        host.innerHTML = data.map(d =>
            '<div class="hbar"><span>' + d.label + '</span>' +
            '<div class="track"><div class="fill" style="width:' + (d.value / max * 100) + '%"></div></div>' +
            '<span class="v">' + d.value + (suffix || '') + '</span></div>').join('');
    }

    function timeline(host, rows) {
        const total = rows.reduce((m, r) => Math.max(m, r.start + r.weeks), 0);
        host.classList.add('timeline');
        host.innerHTML = rows.map(r =>
            '<div class="tl-row"><span class="tl-name">' + r.phase + '<small>' + r.name + '</small></span>' +
            '<div class="tl-track"><div class="tl-bar ' + r.cls + '" style="left:' +
            (r.start / total * 100) + '%;width:' + (r.weeks / total * 100) + '%">' +
            r.weeks + ' wk</div></div></div>').join('') +
            '<div class="tl-scale"><span></span><div class="tl-ticks">' +
            [0, 4, 8, 12, 16].map(w => '<span>Week ' + w + '</span>').join('') +
            '</div></div>';
    }

    /* ---------- 3. Render everything present on the page ------------------ */
    function draw(id, fn) { const h = document.getElementById(id); if (h) fn(h); }

    draw('chartProcess', h => groupedBars(h, PROCESS_STEPS));
    draw('chartMonthly', h => bars(h, MONTHLY_VOLUME));
    draw('chartUtilisation', h => hbars(h, VENUE_UTILISATION));
    draw('chartGrowth', h => bars(h, RECORD_GROWTH));
    draw('chartRoadmap', h => timeline(h, ROADMAP));

    /* ---------- 4. Section numbering + table of contents ------------------ */
    const sections = Array.prototype.slice.call(document.querySelectorAll('.section[id]'));
    const tocList = document.getElementById('tocList');

    sections.forEach(function (sec, i) {
        const n = i + 1;
        const h2 = sec.querySelector('h2');
        if (h2 && !h2.querySelector('.num')) {
            h2.insertAdjacentHTML('afterbegin', '<span class="num">' + n + '.</span> ');
        }
        if (tocList) {
            const title = h2 ? h2.textContent.replace(/^\s*\d+\.\s*/, '').trim() : sec.id;
            tocList.insertAdjacentHTML('beforeend',
                '<li><a href="#' + sec.id + '"><span class="n">' + n + '.</span>' + title + '</a></li>');
        }
    });

    /* Scroll spy */
    const tocLinks = Array.prototype.slice.call(document.querySelectorAll('#tocList a'));
    function spy() {
        let activeIndex = 0;
        const y = window.scrollY + 120;
        sections.forEach(function (sec, i) { if (sec.offsetTop <= y) activeIndex = i; });
        tocLinks.forEach(function (a, i) { a.classList.toggle('active', i === activeIndex); });
    }
    if (tocLinks.length) {
        spy();
        let ticking = false;
        window.addEventListener('scroll', function () {
            if (ticking) return;
            ticking = true;
            window.requestAnimationFrame(function () { spy(); ticking = false; });
        }, { passive: true });
    }

    /* ---------- 5. Toolbar ------------------------------------------------- */
    const printBtn = document.getElementById('printBtn');
    if (printBtn) printBtn.addEventListener('click', function () { window.print(); });

    const tocToggle = document.getElementById('tocToggle');
    const toc = document.getElementById('toc');
    if (tocToggle && toc) {
        tocToggle.addEventListener('click', function () {
            const open = toc.classList.toggle('open');
            tocToggle.setAttribute('aria-expanded', String(open));
        });
        toc.addEventListener('click', function (e) {
            if (e.target.tagName === 'A') toc.classList.remove('open');
        });
    }

    /* ---------- 6. Document date ------------------------------------------ */
    const dateEl = document.getElementById('docDate');
    if (dateEl) {
        const d = new Date();
        const months = ['January', 'February', 'March', 'April', 'May', 'June',
            'July', 'August', 'September', 'October', 'November', 'December'];
        dateEl.textContent = d.getDate() + ' ' + months[d.getMonth()] + ' ' + d.getFullYear();
    }
})();
