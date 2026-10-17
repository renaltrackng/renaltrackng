$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$localPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
$bundledPython = 'C:/Users/USER/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
if (Test-Path -LiteralPath (Join-Path $PSScriptRoot '.runtime/django')) {
    $runtimePython = $bundledPython
} elseif (Test-Path -LiteralPath $localPython) {
    $runtimePython = $localPython
} else {
    $runtimePython = 'python'
}
& $runtimePython manage.py migrate
if ($LASTEXITCODE -ne 0) { throw 'Database setup failed.' }
& $runtimePython manage.py runserver 127.0.0.1:8018 --noreload
