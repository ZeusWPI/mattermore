#!/bin/sh
set -eo pipefail

if [ git status --porcelain=2 -uno | grep '' ]; then
    echo "You have unstaged changes."
    echo "This shouldn't happen in production."
    echo "Plsfix. Dank."
    exit 1
fi

echo "Pulling from remote."
git pull

echo "Updating dependencies."
~/env/bin/pip install requirements.txt

echo "Migrating database."
~/env/bin/flask db upgrade

echo "Restarting server using passenger."
passenger-config restart-app .
