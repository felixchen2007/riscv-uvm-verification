param([Parameter(ValueFromRemainingArguments = $true)][string[]]$RunnerArgs)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = $env:IBEX_PYTHON
if (-not $taskPython) {
    $taskBundledPython = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
    if (Test-Path -LiteralPath $taskBundledPython) { $taskPython = $taskBundledPython }
    else { $taskPython = (Get-Command python -ErrorAction Stop).Source }
}
Push-Location -LiteralPath $taskRoot
try {
    & $taskPython (Join-Path $PSScriptRoot 'run_uvm_tests.py') @RunnerArgs
    exit $LASTEXITCODE
} finally { Pop-Location }
