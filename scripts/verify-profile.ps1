# Local convenience wrapper: the real checks live in scripts/validate-assets.py (also run in CI).
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
python (Join-Path $PSScriptRoot 'validate-assets.py')
exit $LASTEXITCODE
