FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production

WORKDIR /app

# apt has no terminal during a build, so it prints several lines about
# frontends it cannot use before falling back to the noninteractive one.
# Naming that frontend outright keeps the build log readable. pip's root
# warning is about machines with system packages to damage; this has none.
RUN DEBIAN_FRONTEND=noninteractive apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends --yes ca-certificates curl gnupg \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl --fail --silent --show-error https://www.postgresql.org/media/keys/ACCC4CF8.asc \
       | gpg --dearmor --output /usr/share/postgresql-common/pgdg/apt.postgresql.org.gpg \
    && . /etc/os-release \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.gpg] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
       > /etc/apt/sources.list.d/pgdg.list \
    && DEBIAN_FRONTEND=noninteractive apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends --yes postgresql-client-18 \
    && DEBIAN_FRONTEND=noninteractive apt-get purge --auto-remove --yes curl gnupg \
    && rm -rf /var/lib/apt/lists/*

COPY aikol_booking/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --root-user-action=ignore --upgrade pip \
    && pip install --no-cache-dir --root-user-action=ignore -r requirements.txt

COPY aikol_booking/ ./

# Static assets are part of the immutable image.  Production secrets and a
# database connection must never be required while an image is being built.
RUN DJANGO_SETTINGS_MODULE=config.settings.build python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["sh", "-c", "gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8080} --workers ${WEB_CONCURRENCY:-1} --threads ${GUNICORN_THREADS:-4} --timeout 60"]
