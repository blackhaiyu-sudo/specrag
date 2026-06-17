#!/bin/sh
set -eu

mkdir -p \
  /app/data \
  /app/runtime \
  /app/uploads \
  /app/outputs/html \
  /app/outputs/raw \
  /app/logs \
  /app/config

if [ ! -f "${AUTOGEN_CONFIG_PATH:-/app/config/OAI_CONFIG_LIST}" ]; then
  echo "ERROR: AUTOGEN_CONFIG_PATH does not exist: ${AUTOGEN_CONFIG_PATH:-/app/config/OAI_CONFIG_LIST}" >&2
  exit 1
fi

exec "$@"
