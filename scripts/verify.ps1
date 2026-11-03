param([string]$Output)

$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = $env:IBEX_PYTHON
if (-not $taskPython) {
    $taskPython = (Get-Command python -CommandType Application -ErrorAction Stop).Source
}
$taskArgs = @()
if ($Output) { $taskArgs += @('--output', $Output) }
Push-Location -LiteralPath $taskRoot
try {
    & $taskPython -S (Join-Path $PSScriptRoot 'run_release.py') @taskArgs
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
