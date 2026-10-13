#!/usr/bin/env bash
# Exit immediately if a command exits with a non-zero status
set -o errexit

# Install dependencies
pip install -r requirements.txt

# Collect static files with WhiteNoise compression
python manage.py collectstatic --noinput

# Run migrations if database is accessible in the current environment
# (On Render, migrations are reliably handled by preDeployCommand)
if [ -n "$DATABASE_URL" ]; then
  echo "Applying database migrations..."
  python manage.py migrate --noinput || echo "Notice: Migration skipped during build step; will run in preDeployCommand."
else
  echo "DATABASE_URL not present during build. Migrations will run in preDeployCommand."
fi
