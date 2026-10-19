#!/bin/bash
set -Eeuo pipefail
[[ -s /ca/ca.crt && -s /tls/ldap.crt ]] && exit 0
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cd "$work"
openssl req -x509 -newkey rsa:3072 -sha256 -nodes -days 825 \
  -subj "/CN=VENA test LDAP CA" -keyout ca.key -out ca.crt
openssl req -newkey rsa:3072 -sha256 -nodes -subj "/CN=ldap" -keyout ldap.key -out ldap.csr
cat > server.ext <<'EOF'
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=DNS:ldap
authorityKeyIdentifier=keyid
EOF
openssl x509 -req -sha256 -days 825 -in ldap.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -extfile server.ext -out ldap.crt
install -m 644 ca.crt ldap.crt /tls/
install -m 600 ldap.key /tls/
install -m 644 ca.crt /ca/
