#!/bin/bash
set -e
echo "Running migrations..."
alembic upgrade head
echo "Seeding database..."
python db/seed.py
echo "Done."
