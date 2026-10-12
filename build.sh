#!/usr/bin/env bash
# Exit immediately if a command exits with a non-zero status
set -o errexit

# Install dependencies
pip install -r requirements.txt

# Collect static files with WhiteNoise compression
python manage.py collectstatic --noinput

# Apply database migrations
python manage.py migrate
