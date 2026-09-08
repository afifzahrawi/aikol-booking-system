"""The database-level guarantees.

Two exclusion constraints, both PostgreSQL-only:

  - `booking_no_overlap` is what actually makes double booking impossible. The
    application checks for conflicts inside `transaction.atomic()` with
    `select_for_update()`, which is correct but is still application code; this
    constraint is the promise the database keeps regardless of what any view,
    management command, shell session or future developer does.

  - `academic_terms_no_overlap` keeps `AcademicTerm.for_date()` answerable. A
    date belonging to two semesters would make the recurrence generator's
    behaviour arbitrary.

They are skipped on SQLite, which has no equivalent. That is precisely why
SQLite is development-only and PostgreSQL is required in production: on SQLite
the no-double-booking promise rests on application code alone.
"""

from django.db import migrations

BTREE_GIST = "CREATE EXTENSION IF NOT EXISTS btree_gist;"

# Half-open range: 10:00-12:00 and 12:00-14:00 are adjacent, not overlapping,
# which is the same strict comparison the application uses.
ADD_BOOKING = """
ALTER TABLE bookings_booking
    ADD CONSTRAINT booking_no_overlap
    EXCLUDE USING gist (
        resource_id WITH =,
        tstzrange(start_at, end_at, '[)') WITH &&
    )
    WHERE (status IN ('PENDING', 'APPROVED'));
"""

DROP_BOOKING = "ALTER TABLE bookings_booking DROP CONSTRAINT IF EXISTS booking_no_overlap;"

# Inclusive: a semester ending on the 30th and the next starting on the 30th is
# a genuine collision, not adjacency.
ADD_TERM = """
ALTER TABLE bookings_academicterm
    ADD CONSTRAINT academic_terms_no_overlap
    EXCLUDE USING gist (daterange(start_date, end_date, '[]') WITH &&);
"""

DROP_TERM = "ALTER TABLE bookings_academicterm DROP CONSTRAINT IF EXISTS academic_terms_no_overlap;"


def _run(statements):
    def inner(apps, schema_editor):
        if schema_editor.connection.vendor != "postgresql":
            return
        with schema_editor.connection.cursor() as cursor:
            for sql in statements:
                cursor.execute(sql)

    return inner


class Migration(migrations.Migration):
    dependencies = [("bookings", "0001_initial")]

    operations = [
        migrations.RunPython(
            _run([BTREE_GIST, ADD_BOOKING, ADD_TERM]),
            _run([DROP_BOOKING, DROP_TERM]),
        )
    ]
