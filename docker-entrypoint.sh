#!/bin/sh
set -eu
if [ ! -f /data/config.yml ]; then
    mkdir -p /data
    cp /app/config.web.example.yml /data/config.yml
    chmod 600 /data/config.yml
fi
exec python -m zhenxia "$@"
