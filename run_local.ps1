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
    return [Convert]::ToHexString($Buffer).ToLowerInvariant()
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
    $env:ADMIN_PASSWORD = New-SecureHex 12
}
if (-not $env:ENABLE_DEV_TOOLS) {
    $env:ENABLE_DEV_TOOLS = 'true'
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
Write-Host "Logo 評估：$($env:BASE_URL)/logo-review"
Write-Host "LINE 模擬器：$($env:BASE_URL)/dev/line"
Write-Host "管理後台：$($env:BASE_URL)/admin"
Write-Host "管理帳號：$($env:ADMIN_USERNAME)"
Write-Host "本次臨時密碼：$($env:ADMIN_PASSWORD)" -ForegroundColor Yellow
Write-Host '關閉視窗後，未自行設定的臨時密碼會失效。' -ForegroundColor DarkGray
Write-Host ''

python app.py
