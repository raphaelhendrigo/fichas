#!/bin/sh
set -eu

SERVER_NAME="${SERVER_NAME:-lab.engenhodigitalweb.com.br}"
APP_UPSTREAM="${APP_UPSTREAM:-http://app:8080}"
CLIENT_MAX_BODY_SIZE="${CLIENT_MAX_BODY_SIZE:-50m}"
ENABLE_HTTPS="${ENABLE_HTTPS:-true}"
ENABLE_BASIC_AUTH="${ENABLE_BASIC_AUTH:-false}"
BASIC_AUTH_FILE="${BASIC_AUTH_FILE:-/etc/nginx/htpasswd/htpasswd}"

BASIC_AUTH_ENABLED="off"
if [ "$ENABLE_BASIC_AUTH" = "true" ] || [ "$ENABLE_BASIC_AUTH" = "1" ]; then
  BASIC_AUTH_ENABLED="Restricted"
  if [ ! -f "$BASIC_AUTH_FILE" ]; then
    echo "Basic auth enabled but htpasswd not found at $BASIC_AUTH_FILE" >&2
    exit 1
  fi
fi

template="/etc/nginx/templates/lab-http.conf.template"
if [ "$ENABLE_HTTPS" = "true" ] || [ "$ENABLE_HTTPS" = "1" ]; then
  template="/etc/nginx/templates/lab-https.conf.template"
  le_cert="/etc/letsencrypt/live/$SERVER_NAME/fullchain.pem"
  le_key="/etc/letsencrypt/live/$SERVER_NAME/privkey.pem"
  if [ -f "$le_cert" ] && [ -f "$le_key" ]; then
    TLS_CERT_PATH="$le_cert"
    TLS_KEY_PATH="$le_key"
  else
    self_dir="/etc/nginx/selfsigned/$SERVER_NAME"
    mkdir -p "$self_dir"
    TLS_CERT_PATH="$self_dir/fullchain.pem"
    TLS_KEY_PATH="$self_dir/privkey.pem"
    if [ ! -f "$TLS_CERT_PATH" ] || [ ! -f "$TLS_KEY_PATH" ]; then
      openssl req -x509 -nodes -newkey rsa:2048 -days 2 \
        -keyout "$TLS_KEY_PATH" \
        -out "$TLS_CERT_PATH" \
        -subj "/CN=$SERVER_NAME"
    fi
  fi
else
  TLS_CERT_PATH=""
  TLS_KEY_PATH=""
fi

export SERVER_NAME APP_UPSTREAM CLIENT_MAX_BODY_SIZE BASIC_AUTH_ENABLED BASIC_AUTH_FILE TLS_CERT_PATH TLS_KEY_PATH

envsubst '${SERVER_NAME} ${APP_UPSTREAM} ${CLIENT_MAX_BODY_SIZE} ${BASIC_AUTH_ENABLED} ${BASIC_AUTH_FILE} ${TLS_CERT_PATH} ${TLS_KEY_PATH}' \
  < "$template" > /etc/nginx/conf.d/lab.conf

exec "$@"
