$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectRoot

python -m py_compile app.py tianwai\__init__.py tianwai\db.py tianwai\public.py tianwai\payments.py tianwai\line_bot.py tianwai\security.py tianwai\admin.py
node --check static\app.js
node --check static\admin.js
python -m pytest -q

