# setup-keys.ps1 — reads your .env and wires up your keys.
#
# Your keys go from the .env file straight into the tool. They are never printed,
# never sent to the AI, and never written into a chat.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".env")) {
  Write-Host "No .env file found in this folder." -ForegroundColor Red
  Write-Host "   Copy .env.template to .env, paste your keys into it, and run this again."
  exit 1
}

# Load .env without printing anything.
Get-Content ".env" | ForEach-Object {
  if ($_ -match '^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$') {
    $v = $matches[2].Trim().Trim('"').Trim("'")
    if ($v) { Set-Item -Path ("Env:" + $matches[1]) -Value $v }
  }
}

$found = 0
function Need($name, $label) {
  if (-not (Test-Path ("Env:" + $name)) -or -not (Get-Item ("Env:" + $name)).Value) {
    Write-Host "  [ -- ] $label  ($name) blank, skipping" -ForegroundColor DarkGray
  } else { Write-Host "  [OK] $label" -ForegroundColor Green; $script:found = 1 }
}

Write-Host "Checking your .env..."

Need "PRICELABS_API_KEY" "PriceLabs"
Need "HOSPITABLE_API_KEY" "Hospitable"
Need "TURNO_API_TOKEN" "Turno — the long JWT (starts with eyJ)"
Need "TURNO_PARTNER_ID" "Turno — the partner UUID"
Need "AIRROI_API_KEY" "AirROI (free key)"

if ($found -eq 0) {
  Write-Host ""
  Write-Host "Nothing is filled in yet. Open the .env file, paste your key(s), save, and run this again." -ForegroundColor Red
  Write-Host "(See KEYS.md for where to get each one.)"
  exit 1
}
Write-Host ""


# Fan the root .env out to each MCP server folder that expects its own.
#
# This MERGES, it does not overwrite. An earlier version did
# `Copy-Item .env mcp-servers/$s/.env -Force`, which wiped every per-connector
# setting that has no line in the root template. The clearest casualty was
# TURNO_ENV: anyone who followed SETUP.md and set TURNO_ENV=production got
# silently reverted to sandbox, then read an empty sandbox account believing it
# was live data.
#
# Rules: only keys the connector's own .env.example declares are written (so the
# PriceLabs key never lands in Turno's .env), only non-blank root values are
# written, and no existing line is ever removed.
function Merge-Env($dir) {
  $ex  = Join-Path $dir ".env.example"
  $tgt = Join-Path $dir ".env"
  if (-not (Test-Path $ex)) { return $false }
  if (-not (Test-Path $tgt)) { Copy-Item $ex $tgt }

  $names = @(Get-Content $ex | ForEach-Object {
    if ($_ -match '^([A-Za-z_][A-Za-z0-9_]*)=') { $matches[1] }
  })

  $out = New-Object System.Collections.Generic.List[string]
  $written = @{}
  foreach ($line in (Get-Content $tgt)) {
    $done = $false
    if ($line -match '^([A-Za-z_][A-Za-z0-9_]*)=') {
      $key = $matches[1]
      if ($names -contains $key) {
        $val = [Environment]::GetEnvironmentVariable($key)
        if ($val) { $out.Add("$key=$val"); $written[$key] = $true; $done = $true }
        else { $written[$key] = $true }
      }
    }
    if (-not $done) { $out.Add($line) }
  }

  # Append any declared key we have a value for that the file no longer has a
  # line for (someone deleted it by hand).
  foreach ($key in $names) {
    if ($written.ContainsKey($key)) { continue }
    $val = [Environment]::GetEnvironmentVariable($key)
    if ($val) { $out.Add("$key=$val") }
  }

  # Note: Set-Content -Encoding UTF8 emits a BOM on Windows PowerShell 5.1, and a
  # BOM breaks the first key for most dotenv readers. WriteAllLines is BOM-free
  # on both 5.1 and 7.x. .NET does not follow Set-Location, so resolve the path.
  [IO.File]::WriteAllLines((Join-Path $PSScriptRoot $tgt), $out)
  return $true
}

foreach ($s in @("pricelabs","hospitable","turno","airroi","rankbreeze")) {
  if (-not (Test-Path "mcp-servers/$s")) { continue }
  if (Merge-Env "mcp-servers/$s") { Write-Host "  [OK] $s configured" -ForegroundColor Green }
}
if ($env:RANKBREEZE_SESSION -and (Test-Path "mcp-servers/rankbreeze")) {
  [IO.File]::WriteAllText((Join-Path $PSScriptRoot "mcp-servers/rankbreeze/session.txt"), $env:RANKBREEZE_SESSION)
}
Write-Host ""; Write-Host "Done. Now fully quit and reopen Claude Code so it picks up the connectors."
Write-Host "(Your keys are read by each connector at startup, not by Claude.)"
