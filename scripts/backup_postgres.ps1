param(
  [string]$OutputDirectory = (Join-Path $env:TEMP "TianWaiYiBi-Postgres-Backup"),
  [Parameter(Mandatory = $true)][string]$PublicKeyFile
)

$ErrorActionPreference = "Stop"
if (-not $env:DATABASE_URL) { throw "DATABASE_URL is not configured." }
if (-not (Test-Path -LiteralPath $PublicKeyFile -PathType Leaf)) { throw "Public key file does not exist." }

$resolvedOutput = [System.IO.Path]::GetFullPath($OutputDirectory)
if ($resolvedOutput -match "(?i)[\\/]OneDrive[\\/]") { throw "Backup output must stay outside OneDrive." }
New-Item -ItemType Directory -Path $resolvedOutput -Force | Out-Null

$pgDump = Get-Command pg_dump -ErrorAction Stop
$pgRestore = Get-Command pg_restore -ErrorAction Stop
$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$dumpPath = Join-Path $resolvedOutput "tianwai-yibi-$stamp.dump"
$encryptedPath = Join-Path $resolvedOutput "tianwai-yibi-$stamp.twybenc"

try {
  & $pgDump.Source --format=custom --no-owner --no-privileges --file=$dumpPath --dbname=$env:DATABASE_URL
  if ($LASTEXITCODE -ne 0) { throw "pg_dump failed." }
  & $pgRestore.Source --list $dumpPath | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "pg_restore validation failed." }
  python (Join-Path $PSScriptRoot "encrypt_backup.py") --input $dumpPath --output $encryptedPath --public-key-file $PublicKeyFile
  if ($LASTEXITCODE -ne 0) { throw "Backup encryption failed." }
  if ((Get-Item -LiteralPath $encryptedPath).Length -gt 25000000) { throw "Encrypted backup exceeds the 25 MB zero-cost guardrail." }
  Write-Host "Validated encrypted backup: $encryptedPath"
}
finally {
  if (Test-Path -LiteralPath $dumpPath) { Remove-Item -LiteralPath $dumpPath -Force }
}
