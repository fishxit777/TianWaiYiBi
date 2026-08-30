$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectRoot

function New-SecureHex([int]$ByteCount) {
    $Buffer = New-Object byte[] $ByteCount
    $Generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $Generator.GetBytes($Buffer)
    }
    finally {
        $Generator.Dispose()
    }
    # Windows PowerShell 5.1 does not provide Convert.ToHexString().
    return [BitConverter]::ToString($Buffer).Replace('-', '').ToLowerInvariant()
}

function New-SecureBase64Url([int]$ByteCount) {
    $Buffer = New-Object byte[] $ByteCount
    $Generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $Generator.GetBytes($Buffer)
    }
    finally {
        $Generator.Dispose()
    }
    return [Convert]::ToBase64String($Buffer).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

if (-not $env:APP_SECRET_KEY) {
    $env:APP_SECRET_KEY = New-SecureHex 32
}
if (-not $env:PAYMENT_WEBHOOK_SECRET) {
    $env:PAYMENT_WEBHOOK_SECRET = New-SecureHex 32
}
if (-not $env:ADMIN_USERNAME) {
    $env:ADMIN_USERNAME = 'keeper'
}
if (-not $env:ADMIN_PASSWORD) {
    $env:ADMIN_PASSWORD = New-SecureBase64Url 32
}
if (-not $env:BASE_URL) {
    $env:BASE_URL = 'http://127.0.0.1:5088'
}
if (-not $env:PORT) {
    $env:PORT = '5088'
}
if (-not $env:ADMIN_SESSION_BIND_IP) {
    $env:ADMIN_SESSION_BIND_IP = 'true'
}

Write-Host ''
Write-Host '天外一筆・仙策閣本機初版' -ForegroundColor Cyan
Write-Host "官網：$($env:BASE_URL)"
Write-Host "管理後台：$($env:BASE_URL)/admin"
Write-Host "管理帳號：$($env:ADMIN_USERNAME)"
Write-Host "本次臨時密碼：$($env:ADMIN_PASSWORD)" -ForegroundColor Yellow
Write-Host '關閉視窗後，未自行設定的臨時密碼會失效。' -ForegroundColor DarkGray
Write-Host ''

python app.py
