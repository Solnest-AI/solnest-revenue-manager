#!/usr/bin/env bash
# setup-keys.sh — reads your .env and wires up your keys.
#
# Your keys go from the .env file straight into the tool. They are never printed,
# never sent to the AI, and never written into a chat. This script only ever
# reports OK or MISSING.
set -uo pipefail
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "❌ No .env file found in this folder."
  echo "   Copy .env.template to .env, paste your keys into it, and run this again."
  exit 1
fi

# Load the .env WITHOUT printing anything.
set -a; . ./.env; set +a

missing=0
found=0
need() {  # need VAR "Human name"
  if [ -z "${!1:-}" ]; then echo "  ⬜ $2 — blank in .env ($1), skipping"; missing=$((missing+1))
  else echo "  ✅ $2"; found=$((found+1)); fi
}

echo "Checking your .env..."

need PRICELABS_API_KEY "PriceLabs"
need HOSPITABLE_API_KEY "Hospitable"
need TURNO_API_TOKEN "Turno — the long JWT (starts with eyJ)"
need TURNO_PARTNER_ID "Turno — the partner UUID"
need AIRROI_API_KEY "AirROI (free key)"

if [ "$found" -eq 0 ]; then
  echo
  echo "❌ Nothing is filled in yet. Open the .env file, paste your key(s), save, and run this again."
  echo "   (See KEYS.md for where to get each one.)"
  exit 1
fi
echo


# Fan the root .env out to each MCP server folder that expects its own.
#
# This MERGES, it does not overwrite. An earlier version did `cp .env
# mcp-servers/$s/.env`, which wiped every per-connector setting that has no line
# in the root template. The clearest casualty was TURNO_ENV: anyone who followed
# SETUP.md and set TURNO_ENV=production got silently reverted to sandbox, then
# read an empty sandbox account believing it was live data.
#
# Rules: only keys the connector's own .env.example declares are written (so the
# PriceLabs key never lands in Turno's .env), only non-blank root values are
# written, and no existing line is ever removed.
merge_env() {  # merge_env <connector-dir>
  local dir="$1" ex="$1/.env.example" tgt="$1/.env" tmp key val names
  [ -f "$ex" ] || return 1
  [ -f "$tgt" ] || cp "$ex" "$tgt"
  names=$(grep -oE '^[A-Za-z_][A-Za-z0-9_]*=' "$ex" | tr -d '=')
  tmp=$(mktemp) || return 1

  # Rewrite the declared keys that we have a value for; pass everything else
  # through untouched (comments, defaults, keys we were not given).
  while IFS= read -r line || [ -n "$line" ]; do
    key=""
    case "$line" in
      [A-Za-z_]*=*) key="${line%%=*}" ;;
    esac
    if [ -n "$key" ] && printf '%s\n' "$names" | grep -qx -- "$key"; then
      val="${!key:-}"
      if [ -n "$val" ]; then printf '%s=%s\n' "$key" "$val" >> "$tmp"; continue; fi
    fi
    printf '%s\n' "$line" >> "$tmp"
  done < "$tgt"

  # Append any declared key we have a value for that the file no longer has a
  # line for (someone deleted it by hand).
  while IFS= read -r key; do
    [ -n "$key" ] || continue
    grep -qE "^${key}=" "$tmp" && continue
    val="${!key:-}"
    [ -n "$val" ] && printf '%s=%s\n' "$key" "$val" >> "$tmp"
  done <<< "$names"

  mv "$tmp" "$tgt"
  chmod 600 "$tgt" 2>/dev/null || true
}

for s in pricelabs hospitable turno airroi rankbreeze; do
  [ -d "mcp-servers/$s" ] || continue
  if merge_env "mcp-servers/$s"; then echo "  ✅ $s configured"; fi
done
if [ -n "${RANKBREEZE_SESSION:-}" ] && [ -d mcp-servers/rankbreeze ]; then
  printf '%s' "$RANKBREEZE_SESSION" > mcp-servers/rankbreeze/session.txt
  chmod 600 mcp-servers/rankbreeze/session.txt 2>/dev/null || true
fi
echo; echo "Done. Now fully quit and reopen Claude Code so it picks up the connectors."
echo "(Your keys are read by each connector at startup, not by Claude.)"
