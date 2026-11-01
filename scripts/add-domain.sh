#!/usr/bin/env bash
# Serve the panel on an extra domain, next to the one it already has.
#
#   bash <(curl -fsSL https://raw.githubusercontent.com/MHBehzadian/nexra-panel/main/scripts/add-domain.sh) weare.nexradns.site
#
# Second argument is the domain the panel already answers on
# (default panel.nexradns.site). Run it on the server where nginx serves
# the panel.
#
# The certificate is issued over DNS, not HTTP, because a domain that sits
# behind a TCP tunnel usually has no port 80 reaching this server. With an
# ArvanCloud API key in ARVAN_API_KEY it is fully automatic and renews itself;
# without it (the default) certbot shows a TXT record to add by hand.
set -euo pipefail

NEW="${1:-}"
OLD="${2:-panel.nexradns.site}"

say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*"; }
die() { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

[ -n "$NEW" ] || die "usage: add-domain.sh <new-domain> [existing-domain]"
[ "$(id -u)" -eq 0 ] || die "run as root"
command -v nginx >/dev/null || die "nginx is not installed on this server"

owner=$(ss -ltnpH 'sport = :443' || true)
echo "$owner" | grep -q nginx || die "port 443 is not served by nginx here:
${owner:-nothing is listening on 443}"

# --- find the panel's nginx config -------------------------------------------
re_old=${OLD//./\\.}
SRC=$(grep -RlE "server_name[^;]*[[:space:]]${re_old}([[:space:];]|$)" \
    /etc/nginx/sites-enabled /etc/nginx/conf.d 2>/dev/null | head -1 || true)
[ -n "$SRC" ] || die "no nginx config with server_name $OLD"
SRC=$(readlink -f "$SRC")
say "Panel config: $SRC"

others=$(grep -hoE 'server_name[^;]+' "$SRC" | sed 's/server_name//' | tr -s ' \t' '\n' \
    | grep -vxE "|_|${re_old}" | sort -u || true)
[ -z "$others" ] || die "$SRC also serves other domains ($(echo $others)); copy it by hand"

case "$SRC" in
/etc/nginx/conf.d/*) DST="/etc/nginx/conf.d/$NEW.conf" ;;
*) DST="/etc/nginx/sites-available/$NEW" ;;
esac
[ "$SRC" != "$DST" ] || die "$SRC is already the config for $NEW"

# --- certificate --------------------------------------------------------------
CERT_DIR="/etc/nginx/ssl/$NEW"
FULLCHAIN="$CERT_DIR/fullchain.pem"
KEY="$CERT_DIR/privkey.pem"
mkdir -p "$CERT_DIR"

if [ -s "$FULLCHAIN" ] && openssl x509 -checkend 2592000 -noout -in "$FULLCHAIN" >/dev/null 2>&1; then
    say "Certificate for $NEW already valid, keeping it"
else
    # Set ARVAN_API_KEY for a fully automatic, self-renewing certificate;
    # without it the TXT record is added by hand.
    key="${ARVAN_API_KEY:-}"
    issued=0
    if [ -n "$key" ]; then
        case "$key" in Apikey*) ;; *) key="Apikey $key" ;; esac
        ACME="$HOME/.acme.sh/acme.sh"
        if [ ! -x "$ACME" ]; then
            say "Installing acme.sh"
            curl -fsSL https://get.acme.sh | sh -s >/dev/null
        fi
        say "Issuing certificate for $NEW through the ArvanCloud API"
        rc=0
        Arvan_Token="$key" "$ACME" --issue --dns dns_arvan -d "$NEW" \
            --server letsencrypt --keylength ec-256 || rc=$?
        # 2 = already issued and not due for renewal
        if [ "$rc" -eq 0 ] || [ "$rc" -eq 2 ]; then
            "$ACME" --install-cert -d "$NEW" --ecc \
                --key-file "$KEY" --fullchain-file "$FULLCHAIN" \
                --reloadcmd "systemctl reload nginx"
            issued=1
        else
            warn "ArvanCloud API route failed, falling back to the manual DNS record"
        fi
    fi

    # While the domain still points straight at this server (before it is
    # moved behind the tunnel), port 80 reaches nginx and HTTP validation works.
    my_ip=$(curl -4 -fsS --max-time 8 https://api.ipify.org || true)
    dns_ip=$(getent ahostsv4 "$NEW" | awk 'NR==1{print $1}' || true)
    if [ "$issued" = 0 ] && [ -n "$my_ip" ] && [ "$dns_ip" = "$my_ip" ]; then
        say "$NEW points at this server ($my_ip), issuing over HTTP"
        python3 -c 'import certbot_nginx' 2>/dev/null \
            || { apt-get update -qq && apt-get install -y -qq certbot python3-certbot-nginx >/dev/null; }
        if certbot certonly --nginx -d "$NEW" --cert-name "$NEW" \
            --non-interactive --agree-tos --register-unsafely-without-email; then
            ln -sf "/etc/letsencrypt/live/$NEW/fullchain.pem" "$FULLCHAIN"
            ln -sf "/etc/letsencrypt/live/$NEW/privkey.pem" "$KEY"
            issued=1
            warn "Once $NEW is behind the tunnel this certificate cannot renew over HTTP: run this script again before $(date -d '+85 days' +%F) with the domain pointed back at $my_ip"
        else
            warn "HTTP validation failed, falling back to the manual DNS record"
        fi
    fi

    if [ "$issued" = 0 ]; then
        command -v certbot >/dev/null || { apt-get update -qq && apt-get install -y -qq certbot >/dev/null; }
        echo
        echo "certbot will show a TXT record. Add it in the ArvanCloud DNS panel,"
        echo "wait a minute, then press Enter in certbot."
        echo
        certbot certonly --manual --preferred-challenges dns -d "$NEW" --cert-name "$NEW" \
            --agree-tos --register-unsafely-without-email </dev/tty
        ln -sf "/etc/letsencrypt/live/$NEW/fullchain.pem" "$FULLCHAIN"
        ln -sf "/etc/letsencrypt/live/$NEW/privkey.pem" "$KEY"
        warn "Manual certificates do not renew on their own: run this script again before $(date -d '+85 days' +%F)"
    fi
fi

# --- nginx config for the new domain -----------------------------------------
say "Writing $DST"
re_new=${NEW//./\\.}
grep -RlE "server_name[^;]*[[:space:]]${re_new}([[:space:];]|$)" /etc/nginx/sites-enabled /etc/nginx/conf.d 2>/dev/null \
    | grep -vxF "$DST" | grep -vxF "/etc/nginx/sites-enabled/$NEW" \
    && die "$NEW is already in another nginx config (listed above)"

# Copy of the panel's config with the name swapped and our certificate in.
# Listen flags that may only appear once per address are stripped.
sed -E \
    -e "s#^([[:space:]]*)ssl_certificate_key[[:space:]].*#\1ssl_certificate_key $KEY;#" \
    -e "s#^([[:space:]]*)ssl_certificate[[:space:]].*#\1ssl_certificate $FULLCHAIN;#" \
    -e '/^[[:space:]]*ssl_trusted_certificate[[:space:]]/d' \
    -e '/^[[:space:]]*listen[[:space:]]/ s/[[:space:]]+(default_server|ipv6only=on|reuseport)//g' \
    -e "s/${re_old}/${NEW}/g" \
    "$SRC" >"$DST"

case "$DST" in
/etc/nginx/sites-available/*) ln -sf "$DST" "/etc/nginx/sites-enabled/$NEW" ;;
esac

if ! out=$(nginx -t 2>&1); then
    rm -f "$DST" "/etc/nginx/sites-enabled/$NEW"
    die "nginx rejected the new config, nothing changed:
$out"
fi
systemctl reload nginx

# --- check ----------------------------------------------------------------------
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 \
    --resolve "$NEW:443:127.0.0.1" "https://$NEW/" || true)
if [ "$code" = "000" ]; then
    warn "https://$NEW did not answer with a valid certificate on this server; check: nginx -T | grep -A3 $NEW"
else
    say "Done. https://$NEW answers on this server (HTTP $code)"
fi
echo "  DNS for $NEW must point at the tunnel's entry server (DNS only, no CDN proxy)."
