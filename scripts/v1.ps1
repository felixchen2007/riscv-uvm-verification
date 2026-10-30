param([string]$Output, [switch]$BuildSpike)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskRoot 'build/python-env/Scripts/python.exe'
Push-Location -LiteralPath $taskRoot
try {
    if (-not (Test-Path -LiteralPath $taskPython)) {
        $taskBootstrap = $env:IBEX_PYTHON
        if (-not $taskBootstrap) {
            $taskBootstrap = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
            if (-not (Test-Path -LiteralPath $taskBootstrap)) { $taskBootstrap = (Get-Command python -ErrorAction Stop).Source }
        }
        & $taskBootstrap -m venv (Join-Path $taskRoot 'build/python-env')
        if ($LASTEXITCODE) { throw 'Could not create the project Python environment' }
        & $taskPython -m pip install -r (Join-Path $taskRoot 'requirements-verification.txt')
        if ($LASTEXITCODE) { throw 'Could not install the pinned verification dependencies' }
    }
    if ($BuildSpike) {
        & $taskPython (Join-Path $PSScriptRoot 'build_spike.py')
        if ($LASTEXITCODE) { throw 'Pinned Spike build failed; inspect build/spike logs' }
    }
    $taskArgs = @()
    if ($Output) { $taskArgs += @('--output', $Output) }
    & $taskPython (Join-Path $PSScriptRoot 'run_v1.py') @taskArgs
    exit $LASTEXITCODE
} finally { Pop-Location }
