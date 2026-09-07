/* ============================================================================
   AIKOL Room and Vehicle Booking System — Prototype behaviour + sample data
   ----------------------------------------------------------------------------
   IMPORTANT: This is a front-end prototype only. There is no backend, no
   database and no authentication. All data below is FICTIONAL DEMONSTRATION
   DATA created for design review. It does not represent actual AIKOL venues,
   vehicles, staff, students or booking records.

   Demonstration accounts use @demo.aikol.test addresses, per the repository
   convention that sample data must be obviously fictional. The live system
   restricts registration to @iium.edu.my and @live.iium.edu.my — register.html
   demonstrates that rule against typed input.

   Data model mirrors the production schema in docs/technical/database-schema.md:
     - one `resources` collection, extended by venue and vehicle attributes
     - bookings carry `startAt` / `endAt` timestamps, not a date plus two times
     - facilities are a table, not a hard-coded map
   ========================================================================= */
(function (global) {
    'use strict';

    /* ---------- Deterministic pseudo-random (so demo data is stable) ------- */
    function seeded(seed) {
        let s = seed >>> 0;
        return function () {
            s = (s * 1664525 + 1013904223) >>> 0;
            return s / 4294967296;
        };
    }
    const rnd = seeded(20260826);
    const pick = (arr) => arr[Math.floor(rnd() * arr.length)];

    /* ---------- Confirmed business rules (see CLAUDE.md section 5) --------- */
    const SETTINGS = {
        advanceBookingLimitDays: 90,      // decision 7
        maxBookingMinutes: 540,           // decision 8 — 9 hours, venues
        windowStart: '08:00',             // decision 9
        windowEnd: '22:00',               // decision 9
        cancellationCutoffHours: 72,      // decisions 12 and 13
        cancellationReasonRequired: true,
        maxVehicleTripDays: 7,
        maxSeriesOccurrences: 60,
        retentionYears: 7,                // decision 19
        disposalAction: 'Export',         // decision 20
        allowedEmailDomains: ['iium.edu.my', 'live.iium.edu.my']
    };

    /* ---------- Date and time helpers ------------------------------------- */
    const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
    const today = new Date(); today.setHours(0, 0, 0, 0);

    function addDays(base, n) { const d = new Date(base); d.setDate(d.getDate() + n); return d; }
    function iso(d) {
        return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
    }
    function fmtDate(d) {
        const x = (d instanceof Date) ? d : new Date(String(d).slice(0, 10) + 'T00:00:00');
        return String(x.getDate()).padStart(2, '0') + ' ' + MONTHS[x.getMonth()] + ' ' + x.getFullYear();
    }
    function fmtTime(t) { // "14:00" -> "2:00 PM"
        const [h, m] = t.split(':').map(Number);
        const ampm = h >= 12 ? 'PM' : 'AM';
        const hh = h % 12 === 0 ? 12 : h % 12;
        return hh + ':' + String(m).padStart(2, '0') + ' ' + ampm;
    }
    function fmtRange(a, b) { return fmtTime(a) + ' – ' + fmtTime(b); }
    function toMin(t) { const [h, m] = t.split(':').map(Number); return h * 60 + m; }

    /* Timestamps are stored as "YYYY-MM-DDTHH:MM" local strings. */
    function stamp(dateObj, time) { return iso(dateObj) + 'T' + time; }
    function dPart(ts) { return ts.slice(0, 10); }
    function tPart(ts) { return ts.slice(11, 16); }
    function toDate(ts) { return new Date(ts.slice(0, 10) + 'T' + ts.slice(11, 16) + ':00'); }
    function minutesBetween(a, b) { return Math.round((toDate(b) - toDate(a)) / 60000); }
    function fmtStamp(ts) { return fmtDate(dPart(ts)) + ', ' + fmtTime(tPart(ts)); }

    /** Human-readable period. Same-day bookings read as a time range; a trip
        that spans days spells out both dates, because "8:00 AM – 5:00 PM" over
        three days would be actively misleading. */
    function fmtPeriod(startAt, endAt) {
        return dPart(startAt) === dPart(endAt)
            ? fmtDate(dPart(startAt)) + ', ' + fmtRange(tPart(startAt), tPart(endAt))
            : fmtStamp(startAt) + ' → ' + fmtStamp(endAt);
    }
    function durationLabel(startAt, endAt) {
        const mins = minutesBetween(startAt, endAt);
        if (mins < 60) return mins + ' min';
        const h = Math.floor(mins / 60), m = mins % 60;
        if (h < 24) return h + ' h' + (m ? ' ' + m + ' min' : '');
        const days = Math.round(mins / 1440 * 10) / 10;
        return days + ' days';
    }

    /* ---------- Facilities (a table, maintained by administrators) --------- */
    /* Nine seeded values match the data migration described in the schema doc.
       The rest demonstrate facilities an administrator has since created.     */
    const facilities = [
        { id: 1, code: 'projector', name: 'Projector', appliesTo: 'Venue', order: 1, status: 'Active', seeded: true },
        { id: 2, code: 'microphone', name: 'Microphone', appliesTo: 'Venue', order: 2, status: 'Active', seeded: true },
        { id: 3, code: 'smart_tv', name: 'Smart Television', appliesTo: 'Venue', order: 3, status: 'Active', seeded: true },
        { id: 4, code: 'whiteboard', name: 'Whiteboard', appliesTo: 'Venue', order: 4, status: 'Active', seeded: true },
        { id: 5, code: 'computer', name: 'Computer', appliesTo: 'Venue', order: 5, status: 'Active', seeded: true },
        { id: 6, code: 'internet', name: 'Internet Access', appliesTo: 'Both', order: 6, status: 'Active', seeded: true },
        { id: 7, code: 'aircond', name: 'Air Conditioning', appliesTo: 'Both', order: 7, status: 'Active', seeded: true },
        { id: 8, code: 'sound', name: 'Sound System', appliesTo: 'Venue', order: 8, status: 'Active', seeded: true },
        { id: 9, code: 'video_conf', name: 'Video Conferencing', appliesTo: 'Venue', order: 9, status: 'Active', seeded: true },
        { id: 10, code: 'prayer_space', name: 'Prayer Space', appliesTo: 'Venue', order: 10, status: 'Active', seeded: false },
        { id: 11, code: 'gps', name: 'GPS Navigation', appliesTo: 'Vehicle', order: 11, status: 'Active', seeded: false },
        { id: 12, code: 'dashcam', name: 'Dashcam', appliesTo: 'Vehicle', order: 12, status: 'Active', seeded: false },
        { id: 13, code: 'child_seat', name: 'Child Seat', appliesTo: 'Vehicle', order: 13, status: 'Active', seeded: false },
        { id: 14, code: 'overhead_proj', name: 'Overhead Projector', appliesTo: 'Venue', order: 14, status: 'Inactive', seeded: false }
    ];
    const facilityByCode = (code) => facilities.find(f => f.code === code);
    const facilityName = (code) => { const f = facilityByCode(code); return f ? f.name : code; };
    function facilitiesFor(kind) {
        return facilities.filter(f => f.status === 'Active' && (f.appliesTo === kind || f.appliesTo === 'Both'))
            .sort((a, b) => a.order - b.order);
    }

    /* ---------- Venues (FICTIONAL demonstration data) --------------------- */
    /* Decision 4: every resource requires approval. Decision 9: 08:00–22:00.  */
    const venues = [
        {
            id: 1, code: 'AIKOL-MC-01', type: 'Venue', name: 'Moot Court Room', venueType: 'Moot Court',
            building: 'AIKOL Main Building', floor: 'Level 2', location: 'Level 2, AIKOL Main Building',
            capacity: 80, status: 'Active', open: '08:00', close: '22:00',
            approval: true, image: 'moot-court',
            facilities: ['projector', 'microphone', 'aircond', 'internet', 'sound', 'computer'],
            description: 'A formal moot court chamber arranged for mock trial sessions, advocacy training and moot competitions. The room includes a raised bench, counsel tables, a witness stand and public gallery seating.',
            rules: [
                'Reserved primarily for mooting, advocacy training and Kulliyyah-level academic events.',
                'All bookings require administrative approval.',
                'Court furniture and fittings must not be rearranged without permission.',
                'Food and drinks are not permitted inside the chamber.',
                'The room must be left in its original arrangement after use.'
            ]
        },
        {
            id: 2, code: 'AIKOL-SR-01', type: 'Venue', name: 'Seminar Room 1', venueType: 'Seminar Room',
            building: 'AIKOL Main Building', floor: 'Level 1', location: 'Level 1, AIKOL Main Building',
            capacity: 45, status: 'Active', open: '08:00', close: '22:00',
            approval: true, image: 'seminar-a',
            facilities: ['projector', 'whiteboard', 'aircond', 'internet', 'smart_tv'],
            description: 'A flexible seminar room suitable for postgraduate seminars, workshops, guest lectures and departmental discussions. Seating may be arranged in classroom or U-shape configuration.',
            rules: [
                'Booking must be made at least one working day in advance.',
                'Please switch off all equipment before leaving the room.',
                'Report any equipment fault to the Kulliyyah office immediately.'
            ]
        },
        {
            id: 3, code: 'AIKOL-SR-02', type: 'Venue', name: 'Seminar Room 2', venueType: 'Seminar Room',
            building: 'AIKOL Main Building', floor: 'Level 1', location: 'Level 1, AIKOL Main Building',
            capacity: 40, status: 'Active', open: '08:00', close: '22:00',
            approval: true, image: 'seminar-b',
            facilities: ['projector', 'whiteboard', 'aircond', 'internet'],
            description: 'A standard seminar room for teaching, tutorials and small academic sessions, located adjacent to Seminar Room 1.',
            rules: [
                'Booking must be made at least one working day in advance.',
                'A single booking may not exceed nine hours; book a second period to continue.'
            ]
        },
        {
            id: 4, code: 'AIKOL-MR-01', type: 'Venue', name: 'Meeting Room A', venueType: 'Meeting Room',
            building: 'AIKOL Main Building', floor: 'Level 3', location: 'Level 3, AIKOL Main Building',
            capacity: 16, status: 'Active', open: '08:00', close: '22:00',
            approval: true, image: 'meeting-a',
            facilities: ['smart_tv', 'whiteboard', 'aircond', 'internet', 'video_conf'],
            description: 'A boardroom-style meeting room for departmental meetings, supervisory discussions and small committee sessions. Equipped for video conferencing.',
            rules: [
                'Intended for staff and postgraduate supervisory meetings.',
                'Please vacate the room promptly at the end of the booked period.'
            ]
        },
        {
            id: 5, code: 'AIKOL-MR-02', type: 'Venue', name: 'Meeting Room B', venueType: 'Meeting Room',
            building: 'AIKOL Annex', floor: 'Level 1', location: 'Level 1, AIKOL Annex',
            capacity: 10, status: 'Active', open: '08:00', close: '22:00',
            approval: true, image: 'meeting-b',
            facilities: ['smart_tv', 'whiteboard', 'aircond', 'internet'],
            description: 'A compact discussion room suitable for small group meetings, research consultations and student project discussions.',
            rules: ['Maximum ten occupants at any time.']
        },
        {
            id: 6, code: 'AIKOL-LR-01', type: 'Venue', name: 'Lecture Room 1', venueType: 'Lecture Room',
            building: 'AIKOL Main Building', floor: 'Level 2', location: 'Level 2, AIKOL Main Building',
            capacity: 120, status: 'Active', open: '08:00', close: '22:00',
            approval: true, image: 'lecture',
            facilities: ['projector', 'microphone', 'aircond', 'internet', 'sound', 'computer', 'whiteboard'],
            description: 'A tiered lecture theatre used for undergraduate lectures, public talks and Kulliyyah assemblies. The largest teaching space covered by this system.',
            rules: [
                'Timetabled teaching takes priority over ad-hoc bookings.',
                'All bookings require administrative approval.',
                'The public address system must be switched off after use.'
            ]
        },
        {
            id: 7, code: 'AIKOL-DR-01', type: 'Venue', name: 'Discussion Room 1', venueType: 'Discussion Room',
            building: 'AIKOL Library Wing', floor: 'Level 1', location: 'Level 1, AIKOL Library Wing',
            capacity: 8, status: 'Active', open: '08:00', close: '22:00',
            approval: true, image: 'discussion',
            facilities: ['whiteboard', 'aircond', 'internet'],
            description: 'A small study and discussion room in the library wing, intended for student group work and revision sessions.',
            rules: [
                'Maximum booking duration of two hours per group per day.',
                'Please keep noise to a minimum out of respect for library users.'
            ]
        },
        {
            id: 8, code: 'AIKOL-CR-01', type: 'Venue', name: 'Conference Room', venueType: 'Conference Room',
            building: 'AIKOL Main Building', floor: 'Level 3', location: 'Level 3, AIKOL Main Building',
            capacity: 60, status: 'Under Maintenance', open: '08:00', close: '22:00',
            approval: true, image: 'conference',
            facilities: ['projector', 'microphone', 'aircond', 'internet', 'sound', 'video_conf', 'prayer_space'],
            description: 'A conference room used for academic conferences, external visits and Kulliyyah-level official functions.',
            rules: [
                'Bookings for external events require prior written approval.',
                'Currently unavailable pending scheduled maintenance works.'
            ]
        }
    ];

    /* ---------- Vehicles (FICTIONAL demonstration data) ------------------- */
    /* Cars only in the first release. Bookable by lecturers and staff.        */
    const vehicles = [
        {
            id: 101, code: 'AIKOL-CAR-01', type: 'Vehicle', name: 'Kulliyyah Car 1',
            registration: 'WXY 1234', vehicleClass: 'Car', make: 'Proton', model: 'Saga', year: 2022,
            seats: 5, transmission: 'Auto', fuelType: 'Petrol RON95',
            roadTaxExpiry: iso(addDays(today, 210)), insuranceExpiry: iso(addDays(today, 210)),
            mileage: 48250, status: 'Active', open: '08:00', close: '22:00',
            approval: true, image: 'car-saga',
            facilities: ['aircond', 'gps', 'dashcam'],
            description: 'A compact sedan for local official travel within Gombak and the Klang Valley — meetings, courier runs and short official visits.',
            rules: [
                'Bookable by any Kulliyyah account; a student’s trip goes out with a Vehicle Management Unit driver.',
                'The requester is the driver. A valid driving licence must be on file.',
                'Refuel to the level recorded at collection before returning the vehicle.',
                'Record mileage at collection and at return.'
            ]
        },
        {
            id: 102, code: 'AIKOL-CAR-02', type: 'Vehicle', name: 'Kulliyyah Car 2',
            registration: 'WXY 5678', vehicleClass: 'Car', make: 'Perodua', model: 'Bezza', year: 2021,
            seats: 5, transmission: 'Auto', fuelType: 'Petrol RON95',
            roadTaxExpiry: iso(addDays(today, 96)), insuranceExpiry: iso(addDays(today, 96)),
            mileage: 71180, status: 'Active', open: '08:00', close: '22:00',
            approval: true, image: 'car-bezza',
            facilities: ['aircond', 'gps'],
            description: 'A fuel-efficient sedan for routine local travel and errands on behalf of the Kulliyyah office.',
            rules: [
                'Bookable by any Kulliyyah account; a student’s trip goes out with a Vehicle Management Unit driver.',
                'The requester is the driver. A valid driving licence must be on file.',
                'Report any damage or fault at the time of return.'
            ]
        },
        {
            id: 103, code: 'AIKOL-CAR-03', type: 'Vehicle', name: 'Kulliyyah MPV',
            registration: 'WXY 9012', vehicleClass: 'Car', make: 'Toyota', model: 'Innova', year: 2023,
            seats: 7, transmission: 'Auto', fuelType: 'Petrol RON95',
            roadTaxExpiry: iso(addDays(today, 320)), insuranceExpiry: iso(addDays(today, 320)),
            mileage: 26400, status: 'Active', open: '08:00', close: '22:00',
            approval: true, image: 'car-innova',
            facilities: ['aircond', 'gps', 'dashcam', 'child_seat'],
            description: 'A seven-seat multi-purpose vehicle for outstation travel, conference attendance and group transport of Kulliyyah delegations.',
            rules: [
                'Bookable by any Kulliyyah account; a student’s trip goes out with a Vehicle Management Unit driver.',
                'Preferred vehicle for outstation and multi-day trips.',
                'The requester is the driver. A valid driving licence must be on file.',
                'Passenger count must not exceed seven.'
            ]
        },
        {
            id: 104, code: 'AIKOL-CAR-04', type: 'Vehicle', name: 'Kulliyyah Car 3',
            registration: 'WXY 3456', vehicleClass: 'Car', make: 'Proton', model: 'Exora', year: 2019,
            seats: 7, transmission: 'Manual', fuelType: 'Petrol RON95',
            roadTaxExpiry: iso(addDays(today, -12)), insuranceExpiry: iso(addDays(today, 40)),
            mileage: 132900, status: 'Under Maintenance', open: '08:00', close: '22:00',
            approval: true, image: 'car-exora',
            facilities: ['aircond'],
            description: 'An older seven-seat vehicle held for overflow demand. Manual transmission.',
            rules: [
                'Bookable by any Kulliyyah account; a student’s trip goes out with a Vehicle Management Unit driver.',
                'Manual transmission — confirm you are able to drive manual before requesting.',
                'Currently unavailable: road tax renewal in progress.'
            ]
        }
    ];

    /* One collection, exactly as `resources` is one table in production. */
    const resources = venues.concat(vehicles);

    /* ---------- Users (FICTIONAL demonstration data) ---------------------- */
    /* `affiliation` is who the person is; `role` is what they may do. The two
       are separate fields, matching the production schema.                    */
    const FIRST = ['Ahmad', 'Farhan', 'Muhammad', 'Siti', 'Aisyah', 'Hafiz', 'Farah', 'Zainab', 'Ibrahim', 'Khadijah',
        'Amirul', 'Nadia', 'Yusuf', 'Sofia', 'Danial', 'Hannah', 'Umar', 'Balqis', 'Iskandar', 'Maryam'];
    const LAST = ['bin Abdullah', 'binti Ismail', 'bin Rahman', 'binti Yusof', 'bin Hassan', 'binti Omar',
        'bin Salleh', 'binti Karim', 'bin Mansor', 'binti Zulkifli'];

    const users = [];
    (function buildUsers() {
        const seeds = [
            { name: 'Farhan bin Helmy', email: 'farhan@demo.aikol.test', idNo: 'A21EC0001', phone: '011-2000 0001', affiliation: 'Student', role: 'User', status: 'Active' },
            { name: 'Dr. Ahmad Faiz bin Abdullah', email: 'ahmad.faiz@demo.aikol.test', idNo: 'S1042', phone: '011-2000 0002', affiliation: 'Lecturer', role: 'User', status: 'Active', licenceNo: 'D-8841 2276', licenceExpiry: iso(addDays(today, 480)) },
            { name: 'Siti Rohani binti Yusof', email: 'siti.rohani@demo.aikol.test', idNo: 'S1088', phone: '011-2000 0003', affiliation: 'Staff', role: 'Approver', status: 'Active', licenceNo: 'D-6612 0934', licenceExpiry: iso(addDays(today, 260)) },
            { name: 'Mohd Hafiz bin Rahman', email: 'hafiz.rahman@demo.aikol.test', idNo: 'S1001', phone: '011-2000 0004', affiliation: 'Staff', role: 'Administrator', status: 'Active', licenceNo: 'D-3390 7715', licenceExpiry: iso(addDays(today, 610)) },
            { name: 'Prof. Ibrahim bin Hassan', email: 'ibrahim.hassan@demo.aikol.test', idNo: 'S1015', phone: '011-2000 0005', affiliation: 'Lecturer', role: 'User', status: 'Active', licenceNo: 'D-1120 4468', licenceExpiry: iso(addDays(today, -30)) },
            { name: 'Farah Adilah binti Omar', email: 'farah.adilah@demo.aikol.test', idNo: 'A20EC0117', phone: '011-2000 0006', affiliation: 'Student', role: 'User', status: 'Inactive' }
        ];
        seeds.forEach((s, i) => users.push(Object.assign({
            id: i + 1, created: iso(addDays(today, -420 + i * 17)), emailVerified: true,
            isIIUM: true
        }, s)));
        /* Registration is open to the public, so the account list is not all
           IIUM. A public account has no matriculation number — it is identified
           by name, email and telephone. */
        [
            { name: 'Encik Rahim bin Daud', email: 'rahim.daud@demo.aikol.test', org: 'Bar Council Malaysia' },
            { name: 'Ms Chong Wei Ling', email: 'chong.wl@demo.aikol.test', org: 'Legal Aid Centre' }
        ].forEach((x, i) => users.push({
            id: 100 + i, name: x.name, email: x.email, idNo: '', organisation: x.org,
            phone: '012-3' + (400 + i) + ' 88' + (10 + i), affiliation: 'Public', role: 'User',
            status: 'Active', emailVerified: true, isIIUM: false,
            licenceNo: '', licenceExpiry: '', created: iso(addDays(today, -40 - i * 9))
        }));
        for (let i = seeds.length; i < 46; i++) {
            const name = pick(FIRST) + ' ' + pick(LAST);
            const affiliation = rnd() < 0.72 ? 'Student' : (rnd() < 0.6 ? 'Lecturer' : 'Staff');
            const staffNo = 'S' + (1100 + i);
            const matric = 'A2' + (1 + (i % 4)) + 'EC' + String(1000 + i).padStart(4, '0');
            users.push({
                id: i + 1,
                name: name,
                email: name.split(' ')[0].toLowerCase() + '.' + (i + 1) + '@demo.aikol.test',
                idNo: affiliation === 'Student' ? matric : staffNo,
                phone: '011-2' + String(100 + i).padStart(3, '0') + ' ' + String(1000 + i * 7).slice(0, 4),
                affiliation: affiliation,
                isIIUM: true,
                role: 'User',
                status: rnd() < 0.9 ? 'Active' : 'Inactive',
                emailVerified: rnd() < 0.94,
                licenceNo: affiliation === 'Student' ? '' : 'D-' + String(1000 + i * 13).slice(0, 4) + ' ' + String(2000 + i * 29).slice(0, 4),
                licenceExpiry: affiliation === 'Student' ? '' : iso(addDays(today, 120 + Math.floor(rnd() * 700))),
                created: iso(addDays(today, -Math.floor(rnd() * 700)))
            });
        }
    })();

    /* Booking a car, driving one, and being allowed to drive THIS trip are three
       different things.

       AIKOL revised this after review, superseding the earlier arrangement:
         - the Kulliyyah provides NO driver of its own;
         - any member of staff may drive, but only once approved;
         - the requester may NOT nominate a driver — an ADMINISTRATOR assigns
           one, which is a second decision after the booking itself;
         - students cannot request a Kulliyyah car at all. Transport for a
           student activity is arranged through the Vehicle Management Unit via
           STADD, outside this system. */
    const canBookVehicle = (u) =>
        u.status === 'Active' && (u.affiliation === 'Lecturer' || u.affiliation === 'Staff');

    /* Eligible to be ASSIGNED as a driver: Kulliyyah staff or lecturers holding
       an unexpired licence. Being eligible is not the same as being assigned. */
    function canDrive(u) {
        if (!u || u.status !== 'Active') return false;
        if (u.affiliation !== 'Lecturer' && u.affiliation !== 'Staff') return false;
        return !!u.licenceNo && !!u.licenceExpiry;
    }
    function eligibleDrivers(endAt) {
        const until = endAt ? dPart(endAt) : iso(today);
        return users.filter(u => canDrive(u) && u.licenceExpiry >= until);
    }

    const canApprove = (u) => u.role === 'Approver' || u.role === 'Administrator';
    /* Assigning a driver is an administrator action, not an approver one. */
    const canAssignDriver = (u) => u.role === 'Administrator';

    const HOME_BASE = 'AIKOL Main Building, IIUM Gombak';

    /* Where a student activity goes instead. Shown wherever a student meets the
       vehicle path, so nobody is left guessing. */
    const STUDENT_TRANSPORT = {
        unit: 'Vehicle Management Unit (VMU)',
        via: 'STADD',
        note: 'Transport for a student activity is arranged through the Vehicle Management Unit, ' +
              'requested via STADD. It is not booked here — this system covers Kulliyyah rooms, and ' +
              'Kulliyyah cars for lecturers and staff.'
    };

    /* ---------- Recurring series (FICTIONAL) ------------------------------ */
    const series = [
        {
            id: 1, resourceId: 2, userId: 2, createdById: 2, frequency: 'Weekly', interval: 1,
            weekdays: [2], startDate: iso(addDays(today, -14)), endDate: iso(addDays(today, 70)),
            startTime: '14:00', endTime: '16:00', purpose: 'Semester 1 tutorial — Law of Contract',
            occurrences: 13, clashes: 1
        }
    ];

    /* ---------- Bookings (FICTIONAL demonstration data) ------------------- */
    const PURPOSES = [
        'Moot court practice session', 'Postgraduate research seminar', 'Departmental meeting',
        'Guest lecture on Islamic jurisprudence', 'Student society meeting', 'Final year project discussion',
        'Legal clinic briefing', 'Examination moderation meeting', 'Workshop on legal research methods',
        'Mock trial rehearsal', 'Academic advisory session', 'Curriculum review meeting',
        'Debate club training', 'Journal editorial meeting', 'Industrial visit briefing'
    ];
    const TRIP_PURPOSES = [
        'Official visit to IIUM Kuantan campus', 'Conference attendance', 'Court observation visit',
        'Meeting with external partner', 'Document delivery to main campus', 'Moot team transport',
        'Guest speaker airport transfer', 'Legal clinic outreach visit'
    ];
    const DESTINATIONS = [
        'IIUM Kuantan Campus', 'Palace of Justice, Putrajaya', 'Kuala Lumpur Court Complex',
        'IIUM Gombak Main Campus', 'KLIA', 'Shah Alam High Court', 'Bar Council, Kuala Lumpur'
    ];
    const TIME_SLOTS = [
        ['08:00', '10:00'], ['09:00', '11:00'], ['10:00', '12:00'], ['11:00', '13:00'],
        ['14:00', '16:00'], ['14:00', '17:00'], ['15:00', '17:00'], ['16:00', '18:00'],
        ['09:00', '12:00'], ['18:00', '21:00'], ['08:00', '17:00']
    ];

    const bookings = [];
    (function buildBookings() {
        let ref = 1;
        const mkRef = (d) => 'BK-' + d.getFullYear() + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(ref++).padStart(4, '0');

        function push(o) {
            o.id = bookings.length + 1;
            // Derived display fields — same information, read from the timestamps.
            o.date = dPart(o.startAt);
            o.start = tPart(o.startAt);
            o.end = tPart(o.endAt);
            o.multiDay = dPart(o.startAt) !== dPart(o.endAt);
            o.resource = resourceById(o.resourceId);
            o.kind = o.resource.type;
            if (o.createdById === undefined) o.createdById = o.userId;
            bookings.push(o);
            return o;
        }

        /* Fixed bookings belonging to the demo user (id 1) so "My Bookings"
           shows every status. */
        const mine = [
            { off: 3, res: 1, slot: ['14:00', '16:00'], status: 'Approved', purpose: 'Moot court practice session', att: 24 },
            { off: 6, res: 2, slot: ['10:00', '12:00'], status: 'Pending', purpose: 'Student society meeting', att: 18 },
            { off: 9, res: 7, slot: ['16:00', '18:00'], status: 'Approved', purpose: 'Final year project discussion', att: 6 },
            { off: 1, res: 5, slot: ['09:00', '10:00'], status: 'Approved', purpose: 'Supervisory meeting', att: 4 },
            { off: -4, res: 3, slot: ['09:00', '11:00'], status: 'Completed', purpose: 'Legal research workshop', att: 30 },
            { off: -11, res: 5, slot: ['14:00', '15:00'], status: 'Cancelled', purpose: 'Group study session', att: 8, cancelReason: 'Members unavailable — rescheduled to the following week.' },
            { off: -18, res: 6, slot: ['11:00', '13:00'], status: 'Rejected', purpose: 'Society recruitment drive', att: 90, rejectReason: 'Venue reserved for timetabled teaching at the requested time.' },
            { off: -25, res: 1, slot: ['09:00', '12:00'], status: 'Completed', purpose: 'Mock trial rehearsal', att: 35 }
        ];
        mine.forEach(m => {
            const d = addDays(today, m.off);
            push({
                ref: mkRef(d), userId: 1, resourceId: m.res,
                startAt: stamp(d, m.slot[0]), endAt: stamp(d, m.slot[1]),
                purpose: m.purpose, attendees: m.att, status: m.status,
                rejectReason: m.rejectReason || '', cancelReason: m.cancelReason || '',
                created: iso(addDays(d, -5))
            });
        });

        /* Vehicle bookings, including multi-day trips — the case a date plus
           two times could not express. */
        const trips = [
            { off: 4, res: 103, from: '07:00', days: 2, to: '19:00', status: 'Approved', userId: 2, purpose: 'Official visit to IIUM Kuantan campus', dest: 'IIUM Kuantan Campus', pax: 5 },
            { off: 2, res: 101, from: '09:00', days: 0, to: '17:00', status: 'Approved', userId: 3, purpose: 'Meeting with external partner', dest: 'Bar Council, Kuala Lumpur', pax: 3 },
            { off: 8, res: 102, from: '08:30', days: 0, to: '13:00', status: 'Pending', userId: 5, purpose: 'Court observation visit', dest: 'Palace of Justice, Putrajaya', pax: 4 },
            { off: 12, res: 103, from: '06:00', days: 3, to: '20:00', status: 'Pending', userId: 2, purpose: 'Conference attendance', dest: 'IIUM Kuantan Campus', pax: 6 },
            { off: -6, res: 101, from: '08:00', days: 1, to: '18:00', status: 'Completed', userId: 3, purpose: 'Legal clinic outreach visit', dest: 'Shah Alam High Court', pax: 4 },
            { off: -13, res: 102, from: '10:00', days: 0, to: '16:00', status: 'Completed', userId: 2, purpose: 'Guest speaker airport transfer', dest: 'KLIA', pax: 2 },
            { off: -20, res: 103, from: '07:30', days: 2, to: '17:30', status: 'Completed', userId: 4, purpose: 'Moot team transport', dest: 'IIUM Kuantan Campus', pax: 7 },
            { off: -3, res: 102, from: '09:00', days: 0, to: '12:00', status: 'Cancelled', userId: 5, purpose: 'Document delivery to main campus', dest: 'IIUM Gombak Main Campus', pax: 1, cancelReason: 'Documents sent by internal courier instead.' }
        ];
        trips.forEach(t => {
            const d = addDays(today, t.off);
            push(Object.assign({
                ref: mkRef(d), userId: t.userId, resourceId: t.res,
                startAt: stamp(d, t.from), endAt: stamp(addDays(d, t.days), t.to),
                purpose: t.purpose, origin: HOME_BASE, destination: t.dest,
                passengers: t.pax, status: t.status,
                rejectReason: '', cancelReason: t.cancelReason || '',
                created: iso(addDays(d, -6))
            }, { driverId: null, driverAssignedBy: null }));
        });

        /* A recurring series: every occurrence is a real row carrying seriesId. */
        (function buildSeries() {
            const s = series[0];
            let d = new Date(s.startDate + 'T00:00:00');
            while (iso(d) <= s.endDate) {
                if (d.getDay() === s.weekdays[0]) {
                    const past = d < today;
                    push({
                        ref: mkRef(d), userId: s.userId, createdById: s.createdById, resourceId: s.resourceId,
                        seriesId: s.id,
                        startAt: stamp(d, s.startTime), endAt: stamp(d, s.endTime),
                        purpose: s.purpose, attendees: 32,
                        status: past ? 'Completed' : 'Approved',
                        rejectReason: '', cancelReason: '',
                        created: iso(addDays(new Date(s.startDate + 'T00:00:00'), -10))
                    });
                }
                d = addDays(d, 1);
            }
        })();

        /* An administrator booking on behalf of a student (decision 14). */
        (function onBehalf() {
            const d = addDays(today, 5);
            push({
                ref: mkRef(d), userId: 6, createdById: 4, resourceId: 4,
                startAt: stamp(d, '11:00'), endAt: stamp(d, '13:00'),
                purpose: 'Viva preparation — booked by the Kulliyyah office on the student’s behalf',
                attendees: 5, status: 'Approved', rejectReason: '', cancelReason: '',
                created: iso(addDays(d, -2))
            });
        })();

        /* Broader institutional data set across a rolling window. */
        for (let i = 0; i < 230; i++) {
            const off = Math.floor(rnd() * 300) - 270; // mostly past, some future
            const d = addDays(today, off);
            const dow = d.getDay();
            if (dow === 6 && rnd() < 0.8) continue;   // few Saturday bookings
            if (dow === 0 && rnd() < 0.6) continue;   // fewer Sunday bookings
            const isVehicle = rnd() < 0.18;
            const pool = isVehicle ? vehicles : venues;
            const r = pool[Math.floor(rnd() * pool.length)];
            let status;
            if (off < 0) status = rnd() < 0.86 ? 'Completed' : (rnd() < 0.5 ? 'Cancelled' : 'Rejected');
            else status = rnd() < 0.55 ? 'Approved' : (rnd() < 0.75 ? 'Pending' : (rnd() < 0.6 ? 'Cancelled' : 'Rejected'));

            // Vehicles may only be requested by lecturers and staff.
            const eligible = isVehicle ? users.filter(canBookVehicle) : users;
            const u = eligible[Math.floor(rnd() * eligible.length)];

            if (isVehicle) {
                const spanDays = rnd() < 0.3 ? 1 + Math.floor(rnd() * 3) : 0;
                push(Object.assign({
                    ref: mkRef(d), userId: u.id, resourceId: r.id,
                    startAt: stamp(d, '08:00'), endAt: stamp(addDays(d, spanDays), spanDays ? '18:00' : '17:00'),
                    purpose: pick(TRIP_PURPOSES), origin: HOME_BASE, destination: pick(DESTINATIONS),
                    passengers: 1 + Math.floor(rnd() * r.seats), status: status,
                    rejectReason: status === 'Rejected' ? 'Vehicle already committed to a Kulliyyah engagement for that period.' : '',
                    cancelReason: status === 'Cancelled' ? 'Trip postponed by the requester.' : '',
                    created: iso(addDays(d, -Math.ceil(rnd() * 10)))
                }, { driverId: null, driverAssignedBy: null }));
            } else {
                const slot = pick(TIME_SLOTS);
                push({
                    ref: mkRef(d), userId: u.id, resourceId: r.id,
                    startAt: stamp(d, slot[0]), endAt: stamp(d, slot[1]),
                    purpose: pick(PURPOSES),
                    attendees: Math.max(2, Math.min(r.capacity, Math.round(r.capacity * (0.25 + rnd() * 0.7)))),
                    status: status,
                    rejectReason: status === 'Rejected' ? 'Clashes with a Kulliyyah event scheduled for the same period.' : '',
                    cancelReason: status === 'Cancelled' ? 'Cancelled by requester.' : '',
                    created: iso(addDays(d, -Math.ceil(rnd() * 10)))
                });
            }
        }
        bookings.sort((a, b) => (a.startAt < b.startAt ? 1 : a.startAt > b.startAt ? -1 : 0));
    })();

    /* An administrator has assigned drivers to the trips already approved. The
       pending ones are deliberately left unassigned — that is the state the
       approvals queue exists to clear. */
    (function assignDrivers() {
        const pool = users.filter(canDrive);
        if (!pool.length) return;
        let n = 0;
        bookings.forEach(b => {
            if (b.kind !== 'Vehicle') return;
            if (b.status !== 'Approved' && b.status !== 'Completed') return;
            b.driverId = pool[n++ % pool.length].id;
            b.driverAssignedBy = 4;              // the administrator
        });
    })();

    /* ---------- Key handovers (decision 17) ------------------------------- */
    const keyHandovers = [];
    (function buildKeys() {
        let id = 1;
        bookings.forEach(b => {
            if (b.status !== 'Approved' && b.status !== 'Completed') return;
            const startD = toDate(b.startAt);
            if (startD > new Date()) return;                 // not yet collected
            if (rnd() < 0.15) return;                        // some keys never collected
            const outstanding = rnd() < 0.12;                 // a few still out
            /* Four people, not two. The person who collects the key is often
               not the person who booked — a colleague, a society member, a
               driver — and the person who brings it back may be someone else
               again. Recording only the booker loses the chain of custody,
               which is the whole point of the register. */
            const booker = userById(b.userId);
            const proxy = rnd() < 0.3;                        // collected on someone's behalf
            const returnProxy = !outstanding && rnd() < 0.25; // returned by yet another person
            const other = users[(b.id * 7) % users.length];
            const other2 = users[(b.id * 13 + 3) % users.length];

            keyHandovers.push({
                id: id++, bookingId: b.id,

                /* Out */
                issuedAt: b.startAt,
                issuedBy: 4,                                  // the officer who handed it over
                collectedById: proxy ? other.id : b.userId,   // who physically took it
                collectedByName: proxy ? other.name : booker.name,
                collectedByNote: proxy ? 'On behalf of ' + booker.name : '',

                /* Back */
                returnedAt: outstanding ? '' : b.endAt,
                receivedBy: outstanding ? null : 4,           // the officer who took it back
                returnedById: outstanding ? null : (returnProxy ? other2.id : (proxy ? other.id : b.userId)),
                returnedByName: outstanding ? '' :
                    (returnProxy ? other2.name : (proxy ? other.name : booker.name)),

                mileageOut: b.kind === 'Vehicle' ? b.resource.mileage - 400 + Math.floor(rnd() * 200) : null,
                mileageIn: (b.kind === 'Vehicle' && !outstanding) ? b.resource.mileage - 100 + Math.floor(rnd() * 90) : null,
                notes: outstanding ? '' : (rnd() < 0.12 ? 'Minor scuff noted on return.' : '')
            });
        });
    })();
    const keyForBooking = (bookingId) => keyHandovers.find(k => k.bookingId === bookingId) || null;

    /* Renders the custody chain for a booking in one line per event, so the
       register, the bookings tab and any future report cannot phrase it
       differently. Returns '' when no key has been issued. */
    function keyCustody(b) {
        const k = keyForBooking(b && b.id);
        if (!k) return '';
        const officerOut = userById(k.issuedBy);
        const rows = [
            ['Key given out', fmtStamp(k.issuedAt),
             esc(k.collectedByName) + (k.collectedByNote ? ' · ' + esc(k.collectedByNote) : ''),
             'issued by ' + esc(officerOut.name)]
        ];
        if (k.returnedAt) {
            rows.push(['Key returned', fmtStamp(k.returnedAt), esc(k.returnedByName),
                       'received by ' + esc(userById(k.receivedBy).name)]);
        }
        return rows;
    }

    /* One place that answers "where is this booking's key?", so the register,
       the booking list and the user's own screen cannot disagree.
         Not required  — the booking never reserves a key (not yet approved)
         Awaiting      — approved, key not yet given out
         Given out     — the holder has it, the period has not ended
         Overdue       — the holder has it and the period HAS ended
         Collected     — returned to the office */
    function keyState(b) {
        if (!b) return 'Not required';
        if (b.status !== 'Approved' && b.status !== 'Completed') return 'Not required';
        const k = keyForBooking(b.id);
        if (!k) return 'Awaiting collection';
        if (k.returnedAt) return 'Collected';
        return toDate(b.endAt) < new Date() ? 'Overdue' : 'Given out';
    }
    /* Maps to the badge classes the stylesheet already colours. */
    const KEY_BADGE = {
        'Not required': 'badge-muted',
        'Awaiting collection': 'badge-pending',
        'Given out': 'badge-approved',
        'Overdue': 'badge-rejected',
        'Collected': 'badge-completed'
    };
    function keyBadge(b) {
        const st = keyState(b);
        return '<span class="badge ' + KEY_BADGE[st] + '">' + st + '</span>';
    }
    function outstandingKeys() {
        const now = new Date();
        return keyHandovers.filter(k => !k.returnedAt && toDate(bookingById(k.bookingId).endAt) < now);
    }

    /* ---------- Email outbox (FICTIONAL) ---------------------------------- */
    /* Mirrors the production `email_outbox` table: written with the booking,
       delivered afterwards by cron. */
    const emailOutbox = [];
    (function buildOutbox() {
        const TPL = {
            Pending: 'BOOKING_SUBMITTED', Approved: 'BOOKING_APPROVED',
            Rejected: 'BOOKING_REJECTED', Cancelled: 'BOOKING_CANCELLED'
        };
        let id = 1;
        bookings.slice(0, 40).forEach(b => {
            const tpl = TPL[b.status];
            if (!tpl) return;
            const u = userById(b.userId);
            emailOutbox.push({
                id: id++, to: u.email, template: tpl, bookingRef: b.ref,
                subject: 'AIKOL booking ' + b.ref + ' — ' + b.status.toLowerCase(),
                status: id % 17 === 0 ? 'Failed' : (id % 5 === 0 ? 'Pending' : 'Sent'),
                attempts: id % 17 === 0 ? 3 : 1,
                lastError: id % 17 === 0 ? 'SMTP timeout after 30s' : '',
                createdAt: b.created
            });
        });
    })();

    /* ---------- Audit log (FICTIONAL) ------------------------------------- */
    const auditLog = [
        { when: '2 minutes ago', who: 'Mohd Hafiz bin Rahman', action: 'Booking approved', detail: 'Moot Court Room — reference BK-2026-0031' },
        { when: '18 minutes ago', who: 'Mohd Hafiz bin Rahman', action: 'Key issued', detail: 'Kulliyyah MPV — mileage out 26,410' },
        { when: '25 minutes ago', who: 'Siti Rohani binti Yusof', action: 'Booking rejected', detail: 'Lecture Room 1 — clashes with timetabled teaching' },
        { when: '1 hour ago', who: 'Siti Rohani binti Yusof', action: 'Resource updated', detail: 'Conference Room set to Under Maintenance' },
        { when: '2 hours ago', who: 'Mohd Hafiz bin Rahman', action: 'Facility created', detail: 'Prayer Space added to the facility list' },
        { when: '3 hours ago', who: 'Mohd Hafiz bin Rahman', action: 'Bulk import performed', detail: '58 user records imported from CSV' },
        { when: 'Yesterday, 4:12 PM', who: 'Siti Rohani binti Yusof', action: 'User deactivated', detail: 'Graduated student account' },
        { when: 'Yesterday, 2:40 PM', who: 'Mohd Hafiz bin Rahman', action: 'Key returned', detail: 'Kulliyyah Car 1 — mileage in 48,392' },
        { when: 'Yesterday, 9:03 AM', who: 'Mohd Hafiz bin Rahman', action: 'Resource created', detail: 'Kulliyyah MPV added to the vehicle list' }
    ];

    /* ---------- Lookups ---------------------------------------------------- */
    function resourceById(id) { return resources.find(r => r.id === id) || resources[0]; }
    function venueById(id) { return venues.find(v => v.id === id) || venues[0]; }
    function vehicleById(id) { return vehicles.find(v => v.id === id) || vehicles[0]; }
    function userById(id) { return users.find(u => u.id === id) || users[0]; }
    function bookingById(id) { return bookings.find(b => b.id === id) || bookings[0]; }
    const CURRENT_USER = users[0];        // student — used by the user-mode screens
    const ADMIN_USER = users[3];

    /* ---------- Small DOM helpers ------------------------------------------ */
    function el(html) { const t = document.createElement('template'); t.innerHTML = html.trim(); return t.content.firstElementChild; }
    function esc(s) { return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
    function badge(status) { return '<span class="badge badge-' + status.toLowerCase().replace(/\s+/g, '-') + '">' + esc(status) + '</span>'; }
    function resourceImg(r, variant) { return 'assets/images/' + r.image + (variant ? '-v' + variant : '') + '.svg'; }

    /* ---------- Editable site content ------------------------------------- */
    /* Header and footer wording is CONTENT, not code. An administrator changes
       the Kulliyyah's address or telephone number without a software release,
       exactly as they change a booking limit. Production stores each of these
       as a `system_settings` row — see docs/technical/database-schema.md. */
    const siteContent = {
        logo:        'assets/images/aikol_logo.png',
        logoAlt:     'Ahmad Ibrahim Kulliyyah of Laws, International Islamic University Malaysia',
        name:        'Room and Vehicle Booking',
        subtitle:    'Ahmad Ibrahim Kulliyyah of Laws · IIUM',
        org:         'Ahmad Ibrahim Kulliyyah of Laws',
        address:     'Kulliyyah Office, Level 1, AIKOL Main Building\n' +
                     'International Islamic University Malaysia, 53100 Gombak, Selangor',
        contactHead: 'Booking enquiries',
        phone:       '03-6196 4000',
        email:       'booking-aikol@iium.edu.my',
        hours:       'Mon–Fri, 08:30–17:00',
        linksHead:   'IIUM',
        links: [
            { label: 'iium.edu.my', url: 'https://www.iium.edu.my' },
            { label: 'AIKOL Kulliyyah site', url: '#' },
            { label: 'Booking rules and policy', url: '#' }
        ]
    };

    /* Newlines in an address are meaningful; everything is escaped first so a
       typed value can never inject markup into the chrome. */
    function contentLines(text) {
        return String(text).split('\n').map(esc).join('<br>');
    }

    /* ---------- Chrome: brand bar, navigation, footer ---------------------- */
    /* Matches the confirmed design: a white brand bar over a green navigation
       bar. The old left sidebar is gone — navigation is horizontal, and the
       admin and user sets are the five and five items the design specifies. */
    const NAV_USER = [
        { href: 'dashboard.html', label: 'Dashboard' },
        { href: 'availability.html', label: 'Availability' },
        { href: 'venues.html', label: 'Rooms' },
        { href: 'vehicles.html', label: 'Vehicles' },
        { href: 'my-bookings.html', label: 'My bookings' }
    ];
    const NAV_ADMIN = [
        { href: 'admin-approvals.html', label: 'Approvals', badge: 'pending' },
        { href: 'admin-bookings.html', label: 'Bookings' },
        { href: 'admin-venues.html', label: 'Resources' },
        { href: 'admin-users.html', label: 'Users' },
        { href: 'admin-reports.html', label: 'Reports' },
        { href: 'admin-site-content.html', label: 'Site content' }
    ];

    /* Kept for screens that still draw their own inline icons. The navigation
       itself is text-only, as the design specifies. */
    const ICONS = {
        grid: '<path d="M2 2h5v5H2zM9 2h5v5H9zM2 9h5v5H2zM9 9h5v5H9z"/>',
        building: '<path d="M3 14V3h7v11M10 6h3v8h-3M5 5h3M5 8h3M5 11h3"/>',
        car: '<path d="M2 10h12M3.5 10V7.5l1.2-2.6h6.6L12.5 7.5V10M3.5 10v1.8M12.5 10v1.8M5 8h6"/>',
        key: '<path d="M9.5 3a3.5 3.5 0 100 7 3.5 3.5 0 000-7zM7 8.5L2.5 13M4 11l1.5 1.5"/>',
        tag: '<path d="M2 2h5l7 7-5 5-7-7V2zM4.5 4.5h.01"/>',
        plus: '<path d="M8 3v10M3 8h10"/>',
        list: '<path d="M3 4h10M3 8h10M3 12h10"/>',
        user: '<path d="M8 8a3 3 0 100-6 3 3 0 000 6zM2 14c0-3 2.7-4.5 6-4.5S14 11 14 14"/>',
        database: '<path d="M8 5c3.3 0 6-1 6-1.7S11.3 1 8 1 2 2.3 2 3.3 4.7 5 8 5zM2 3.3v9.4C2 13.7 4.7 15 8 15s6-1.3 6-2.3V3.3M2 8c0 1 2.7 2.3 6 2.3S14 9 14 8"/>'
    };
    function icon(name) {
        return '<svg class="ico" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" ' +
            'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + (ICONS[name] || '') + '</svg>';
    }

    function pendingCount() { return bookings.filter(b => b.status === 'Pending').length; }

    /* The design calls for Amiri and IBM Plex Sans. Injected here so all
       nineteen screens pick them up from one place. Production must vendor
       these under static/ — CLAUDE.md forbids CDN assets. */
    function loadFonts() {
        if (document.getElementById('aikol-fonts')) return;
        const pre = document.createElement('link');
        pre.rel = 'preconnect'; pre.href = 'https://fonts.googleapis.com';
        const link = document.createElement('link');
        link.id = 'aikol-fonts';
        link.rel = 'stylesheet';
        link.href = 'https://fonts.googleapis.com/css2?family=Amiri:wght@400;700' +
                    '&family=IBM+Plex+Sans:wght@400;500;600&display=swap';
        document.head.appendChild(pre);
        document.head.appendChild(link);
    }

    /* Built from siteContent so the edit screen can render a live preview with
       exactly the markup the real footer uses. */
    function buildFooterHtml() {
        const links = siteContent.links.length
            ? siteContent.links.map(l =>
                '<a href="' + esc(l.url || '#') + '">' + esc(l.label) + '</a>').join('<br>')
            : '<span style="opacity:.6">No links configured</span>';
        return '<footer class="app-footer">' +
            '<div><h4>' + esc(siteContent.org) + '</h4>' +
            contentLines(siteContent.address) + '</div>' +
            '<div><div class="foot-label">' + esc(siteContent.contactHead) + '</div>' +
            [siteContent.phone, siteContent.email, siteContent.hours]
                .filter(Boolean).map(esc).join('<br>') + '</div>' +
            '<div><div class="foot-label">' + esc(siteContent.linksHead) + '</div>' +
            links + '</div>' +
            '</footer>';
    }

    function buildChrome(opts) {
        loadFonts();

        const admin = opts.mode === 'admin';
        const nav = admin ? NAV_ADMIN : NAV_USER;
        const user = admin ? ADMIN_USER : CURRENT_USER;
        const initials = user.name.replace(/^(Dr\.|Prof\.)\s+/, '').split(' ').slice(0, 2)
            .map(w => w[0]).join('').toUpperCase();

        const ribbon = el('<div class="demo-ribbon">Interactive prototype — fictional demonstration data. ' +
            'Not connected to any live AIKOL system.</div>');

        const header = el(
            '<header class="app-header">' +
            '<a class="brand" href="' + (admin ? 'admin-approvals.html' : 'dashboard.html') + '">' +
            '<img src="' + esc(siteContent.logo) + '" alt="' + esc(siteContent.logoAlt) + '">' +
            '<span class="brand-rule"></span>' +
            '<span class="brand-text">' +
            '<span class="brand-name">' + esc(siteContent.name) + '</span>' +
            '<span class="brand-sub">' + esc(siteContent.subtitle) + '</span>' +
            '</span></a>' +
            '<span class="header-spacer"></span>' +
            '<a class="link-plain" href="' + (admin ? 'dashboard.html' : 'admin-approvals.html') + '">' +
            (admin ? 'User view' : 'Administrator view') + '</a>' +
            '<div class="header-user"><span class="avatar" aria-hidden="true">' + initials + '</span>' +
            '<span class="who"><span>' + esc(user.name) + '</span>' +
            '<span class="role">' + esc(admin ? 'Administrator' : user.affiliation) + '</span></span></div>' +
            '<a class="link-plain" href="login.html">Sign out</a>' +
            '</header>');

        const links = nav.map(n => {
            const cur = n.href === opts.active ? ' aria-current="page"' : '';
            const bdg = n.badge === 'pending'
                ? '<span class="nav-badge">' + pendingCount() + '</span>' : '';
            return '<a href="' + n.href + '"' + cur + '>' + n.label + bdg + '</a>';
        }).join('');

        const navbar = el(
            '<nav class="app-nav" aria-label="Main navigation">' +
            '<button class="nav-toggle" type="button" aria-label="Toggle navigation" aria-expanded="false">☰</button>' +
            links +
            '<span class="header-spacer"></span>' +
            '<div class="nav-search"><span class="ring"></span>' +
            (admin ? 'Search bookings, users or resources' : 'Search rooms, cars or bookings') +
            '</div></nav>');

        const footer = el(buildFooterHtml());

        const app = document.querySelector('.app');
        const body = app.querySelector('.app-body');
        app.insertBefore(ribbon, body);
        app.insertBefore(header, body);
        app.insertBefore(navbar, body);
        app.appendChild(footer);

        navbar.querySelector('.nav-toggle').addEventListener('click', function () {
            const open = navbar.classList.toggle('open');
            this.setAttribute('aria-expanded', String(open));
        });

        /* Screens build their tables after calling buildChrome, so this runs
           once their synchronous rendering has finished. */
        setTimeout(tintAllTables, 0);
    }

    /* ---------- Row status tinting ---------------------------------------- */
    /* Reads the status straight off the badge a row already renders, so no
       screen has to pass anything extra and no two places can disagree about
       what a row's status is. The stylesheet turns it into a coloured edge. */
    function tintRows(tbody) {
        if (!tbody) return;
        Array.prototype.forEach.call(tbody.rows, function (tr) {
            /* A row may state its own status — the approvals queue does, because
               its rows carry action buttons rather than a badge. */
            if (tr.dataset.status) return;
            /* Otherwise take the LAST badge in the row. Rows often carry more
               than one (a role, a licence expiry, a road tax date); the status
               column sits at the right, so the last one is the row's status. */
            const badges = tr.querySelectorAll('.badge');
            if (!badges.length) return;
            const cls = Array.prototype.find.call(badges[badges.length - 1].classList, function (c) {
                return c.indexOf('badge-') === 0;
            });
            if (cls) tr.dataset.status = cls.slice(6);
        });
    }

    /* Tables rendered once, outside the table controller, still get tinted. */
    function tintAllTables() {
        document.querySelectorAll('table.data tbody').forEach(tintRows);
    }

    /* ---------- Generic table controller ---------------------------------- */
    /* Mirrors the intended production behaviour: filter and paginate on the
       server, never load the whole table into the browser.                   */
    function tableController(cfg) {
        const state = { page: 1, size: cfg.pageSize || 10, filters: {} };

        function apply() {
            let rows = cfg.rows().filter(r => cfg.match(r, state.filters));
            const total = rows.length;
            const pages = Math.max(1, Math.ceil(total / state.size));
            if (state.page > pages) state.page = pages;
            const start = (state.page - 1) * state.size;
            const slice = rows.slice(start, start + state.size);

            const tbody = cfg.tbody;
            tbody.innerHTML = slice.length
                ? slice.map(cfg.render).join('')
                : '<tr><td colspan="' + cfg.cols + '"><div class="empty-state">No records match the current filters.</div></td></tr>';
            tintRows(tbody);

            if (cfg.info) {
                cfg.info.textContent = total === 0 ? 'No records'
                    : 'Showing ' + (start + 1) + '–' + Math.min(start + state.size, total) + ' of ' + total.toLocaleString() + ' records';
            }
            if (cfg.pager) renderPager(cfg.pager, state.page, pages, p => { state.page = p; apply(); });
            if (cfg.onRender) cfg.onRender(slice, total);
        }

        (cfg.controls || []).forEach(c => {
            c.input.addEventListener(c.event || 'input', () => {
                state.filters[c.key] = c.input.value;
                state.page = 1;
                apply();
            });
        });

        apply();
        return { refresh: apply, state: state };
    }

    function renderPager(host, page, pages, go) {
        const nums = [];
        const push = (p) => nums.push('<button type="button" data-p="' + p + '"' + (p === page ? ' aria-current="true"' : '') + '>' + p + '</button>');
        push(1);
        if (page > 3) nums.push('<button type="button" disabled>…</button>');
        for (let p = Math.max(2, page - 1); p <= Math.min(pages - 1, page + 1); p++) push(p);
        if (page < pages - 2) nums.push('<button type="button" disabled>…</button>');
        if (pages > 1) push(pages);

        host.innerHTML =
            '<button type="button" data-p="' + (page - 1) + '"' + (page === 1 ? ' disabled' : '') + ' aria-label="Previous page">‹</button>' +
            nums.join('') +
            '<button type="button" data-p="' + (page + 1) + '"' + (page === pages ? ' disabled' : '') + ' aria-label="Next page">›</button>';

        host.querySelectorAll('button[data-p]').forEach(b => {
            b.addEventListener('click', () => { const p = Number(b.dataset.p); if (p >= 1 && p <= pages) go(p); });
        });
    }

    /* ---------- Modal ------------------------------------------------------ */
    function modal(opts) {
        const back = el('<div class="modal-backdrop"><div class="modal" role="dialog" aria-modal="true" aria-labelledby="mt">' +
            '<div class="modal-head"><h2 id="mt">' + esc(opts.title) + '</h2></div>' +
            '<div class="modal-body">' + opts.body + '</div>' +
            '<div class="modal-foot"></div></div></div>');
        const foot = back.querySelector('.modal-foot');
        (opts.buttons || [{ label: 'Close' }]).forEach(b => {
            const btn = el('<button type="button" class="btn ' + (b.cls || '') + '">' + esc(b.label) + '</button>');
            btn.addEventListener('click', () => { if (!b.onClick || b.onClick(back) !== false) close(); });
            foot.appendChild(btn);
        });
        function close() { back.remove(); document.removeEventListener('keydown', onKey); }
        function onKey(e) { if (e.key === 'Escape') close(); }
        back.addEventListener('click', e => { if (e.target === back) close(); });
        document.addEventListener('keydown', onKey);
        document.body.appendChild(back);
        const focusable = back.querySelector('input, select, textarea, button');
        if (focusable) focusable.focus();
        return { close: close, root: back };
    }

    function toast(message, kind) {
        modal({ title: kind === 'danger' ? 'Action blocked' : 'Prototype action', body: '<p>' + esc(message) + '</p>' +
            '<p class="help">No data is changed — this prototype has no backend.</p>' });
    }

    /** Confirmation-email notice. Every booking status change queues a message
        in production; the prototype says so rather than pretending to send. */
    function emailNotice(address, what) {
        return '<p class="help" style="margin-top:.75rem">✉ In the live system a <strong>' + esc(what) +
            '</strong> confirmation would be queued for <span class="mono">' + esc(address) + '</span> ' +
            'and delivered by the mail sender. Nothing is sent from this prototype.</p>';
    }

    /* ---------- Conflict check (mirrors the production rule) --------------- */
    /* Overlap when: new_start < existing_end AND new_end > existing_start,
       counting only bookings in an active status (Pending, Approved).
       Timestamps, so one rule covers a 2-hour room slot and a 3-day trip.    */
    const BLOCKING = ['Pending', 'Approved'];
    function findConflicts(resourceId, startAt, endAt, ignoreId) {
        return bookings.filter(b =>
            b.resourceId === resourceId && b.id !== ignoreId &&
            BLOCKING.indexOf(b.status) !== -1 &&
            startAt < b.endAt && endAt > b.startAt);
    }

    /* ---------- Availability strip ---------------------------------------- */
    function availabilityStrip(host, resource, date, days) {
        const openM = toMin(resource.open), closeM = toMin(resource.close), span = closeM - openM;
        let html = '';
        for (let i = 0; i < days; i++) {
            const d = addDays(new Date(date + 'T00:00:00'), i);
            const key = iso(d);
            const dayStart = key + 'T00:00', dayEnd = key + 'T23:59';
            const blocks = bookings
                .filter(b => b.resourceId === resource.id && BLOCKING.indexOf(b.status) !== -1 &&
                             b.startAt <= dayEnd && b.endAt >= dayStart)
                .map(b => {
                    // Clamp a multi-day trip to this day's window so the bar reads correctly.
                    const sMin = dPart(b.startAt) < key ? openM : Math.max(openM, toMin(tPart(b.startAt)));
                    const eMin = dPart(b.endAt) > key ? closeM : Math.min(closeM, toMin(tPart(b.endAt)));
                    if (eMin <= sMin) return '';
                    const left = ((sMin - openM) / span) * 100;
                    const width = ((eMin - sMin) / span) * 100;
                    const label = b.multiDay ? 'All day' : fmtTime(tPart(b.startAt));
                    return '<span class="avail-block' + (b.status === 'Pending' ? ' pending' : '') + '" ' +
                        'style="left:' + Math.max(0, left) + '%;width:' + Math.min(100, width) + '%" ' +
                        'title="' + esc(fmtPeriod(b.startAt, b.endAt) + ' — ' + b.status) + '">' + label + '</span>';
                }).join('');
            html += '<div class="avail-row"><span>' + fmtDate(d) + '</span><div class="avail-bar">' + blocks + '</div></div>';
        }
        html += '<div class="avail-scale"><span></span><div class="ticks"><span>' + fmtTime(resource.open) +
            '</span><span>' + fmtTime(resource.close) + '</span></div></div>';
        host.innerHTML = html;
    }

    /* ---------- Simple charts (no external library) ------------------------ */
    function barChart(host, data, opts) {
        const max = Math.max.apply(null, data.map(d => d.value)) || 1;
        host.classList.add('bars');
        host.innerHTML = data.map(d =>
            '<div class="bar-col"><div class="bar" style="height:' + Math.round((d.value / max) * 100) + '%">' +
            '<span>' + d.value + '</span></div><div class="bar-label">' + esc(d.label) + '</div></div>').join('');
        if (opts && opts.caption) host.setAttribute('aria-label', opts.caption);
    }

    /* A single measure over time, so: a line, one hue, no legend — the heading
       names the series. Values sit on the line because six months is few enough
       to label every point without crowding; a denser series would label only
       the ends and the extremes. */
    function lineChart(host, data, opts) {
        opts = opts || {};
        const W = 640, H = 210;
        const padT = 30, padB = 26, padL = 10, padR = 10;
        const plotW = W - padL - padR, plotH = H - padT - padB;
        const max = Math.max.apply(null, data.map(d => d.value)) || 1;
        const stroke = opts.color || '#14675b';

        const x = i => padL + (data.length === 1 ? plotW / 2 : (i / (data.length - 1)) * plotW);
        const y = v => padT + (1 - v / max) * plotH;

        /* Recessive grid — three rules, no axis box. */
        let grid = '';
        for (let g = 0; g <= 2; g++) {
            const gy = padT + (g / 2) * plotH;
            grid += '<line x1="' + padL + '" y1="' + gy.toFixed(1) + '" x2="' + (W - padR) +
                    '" y2="' + gy.toFixed(1) + '" stroke="#ebe3d1" stroke-width="1"/>';
        }

        const pts = data.map((d, i) => x(i).toFixed(1) + ',' + y(d.value).toFixed(1)).join(' ');

        /* A soft fill under the line reads as volume without competing with it. */
        const area = '<polygon points="' + padL + ',' + (padT + plotH) + ' ' + pts + ' ' +
                     (W - padR) + ',' + (padT + plotH) + '" fill="' + stroke + '" fill-opacity=".07"/>';

        const marks = data.map((d, i) => {
            const cx = x(i), cy = y(d.value);
            return '<g>' +
                '<title>' + esc(d.label) + ': ' + d.value + (opts.noun ? ' ' + esc(opts.noun) : '') + '</title>' +
                /* 2px surface ring keeps the marker readable where it meets the line */
                '<circle cx="' + cx.toFixed(1) + '" cy="' + cy.toFixed(1) + '" r="6" fill="#fffdf8"/>' +
                '<circle cx="' + cx.toFixed(1) + '" cy="' + cy.toFixed(1) + '" r="4" fill="' + stroke + '"/>' +
                '<text x="' + cx.toFixed(1) + '" y="' + (cy - 12).toFixed(1) + '" text-anchor="middle" ' +
                'font-size="12" font-weight="600" fill="#1a2420" ' +
                'style="font-variant-numeric: tabular-nums">' + d.value + '</text>' +
                '<text x="' + cx.toFixed(1) + '" y="' + (H - 8) + '" text-anchor="middle" ' +
                'font-size="11" fill="#8a7f66">' + esc(d.label) + '</text>' +
                '</g>';
        }).join('');

        const total = data.reduce((t, d) => t + d.value, 0);
        host.innerHTML =
            '<svg viewBox="0 0 ' + W + ' ' + H + '" width="100%" role="img" ' +
            'aria-label="' + esc(opts.caption || 'Bookings per month') + '. ' +
            data.map(d => esc(d.label) + ': ' + d.value).join(', ') + '. Total ' + total + '." ' +
            'style="display:block;overflow:visible">' +
            grid + area +
            '<polyline points="' + pts + '" fill="none" stroke="' + stroke +
            '" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>' +
            marks +
            '</svg>';
    }

    function hBarChart(host, data, suffix) {
        const max = Math.max.apply(null, data.map(d => d.value)) || 1;
        host.classList.add('hbars');
        host.innerHTML = data.map(d =>
            '<div class="hbar"><span>' + esc(d.label) + '</span>' +
            '<div class="track"><div class="fill" style="width:' + Math.round((d.value / max) * 100) + '%"></div></div>' +
            '<span class="val">' + d.value + (suffix || '') + '</span></div>').join('');
    }

    /* ---------- Derived statistics ---------------------------------------- */
    function monthlyVolume(months) {
        const out = [];
        for (let i = months - 1; i >= 0; i--) {
            const d = new Date(today.getFullYear(), today.getMonth() - i, 1);
            const prefix = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0');
            out.push({ label: MONTHS[d.getMonth()], value: bookings.filter(b => b.startAt.indexOf(prefix) === 0).length });
        }
        return out;
    }
    function resourceUtilisation(kind) {
        const pool = kind === 'Vehicle' ? vehicles : (kind === 'Venue' ? venues : resources);
        return pool.map(r => ({ label: r.name, value: bookings.filter(b => b.resourceId === r.id).length }))
            .sort((a, b) => b.value - a.value);
    }

    /* ---------- Export ----------------------------------------------------- */
    global.AIKOL = {
        // data
        SETTINGS, siteContent, buildFooterHtml, contentLines,
        facilities, resources, venues, vehicles, users, bookings, series,
        keyHandovers, emailOutbox, auditLog, CURRENT_USER, ADMIN_USER,
        // date helpers
        today, DAYS, MONTHS, addDays, iso, fmtDate, fmtTime, fmtRange, toMin,
        stamp, dPart, tPart, toDate, minutesBetween, fmtStamp, fmtPeriod, durationLabel,
        // lookups
        resourceById, venueById, vehicleById, userById, bookingById,
        facilityByCode, facilityName, facilitiesFor, keyForBooking, outstandingKeys,
        canBookVehicle, canDrive, eligibleDrivers, canApprove, canAssignDriver,
        keyState, keyBadge, keyCustody, HOME_BASE, STUDENT_TRANSPORT,
        // DOM
        el, esc, badge, resourceImg, icon, buildChrome, tableController, renderPager,
        tintRows, tintAllTables,
        modal, toast, emailNotice,
        // rules
        findConflicts, BLOCKING, availabilityStrip,
        // charts and stats
        barChart, lineChart, hBarChart, monthlyVolume, resourceUtilisation, pendingCount,

        /* Deprecated aliases kept so older screens keep working while they are
           migrated. New screens must use the names above. */
        venueImg: resourceImg,
        venueUtilisation: function () { return resourceUtilisation('Venue'); },
        FACILITIES: facilities.reduce((m, f) => { m[f.code] = f.name; return m; }, {}),
        ALL_FAC: facilities.filter(f => f.status === 'Active').map(f => f.code)
    };
})(window);
