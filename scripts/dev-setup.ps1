<#
.SYNOPSIS
    One-command development environment orchestrator for whisper_transfer.

.DESCRIPTION
    Primary dev entry on Windows. Mirrors the Makefile targets used on
    macOS/Linux. All commands resolve the repository root from the script
    location, so they can be invoked from any working directory.

.PARAMETER Command
    setup  Install backend + frontend dependencies (idempotent).
    dev    Start backend (new window) and frontend (current window).
    test   Run backend pytest suite.
    lint   Run backend flake8 (CI scope) + frontend ESLint.
    check  lint + test -- local CI simulation (matches .dev/scripts/verify.sh).
    clean  Remove caches and build artifacts. Never touches outputs/ or uploads/.
    help   Show this help message.

.EXAMPLE
    .\scripts\dev-setup.ps1 setup
    .\scripts\dev-setup.ps1 dev
    .\scripts\dev-setup.ps1 check
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('setup', 'dev', 'test', 'lint', 'check', 'clean', 'help')]
    [string]$Command = 'help'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $RepoRoot

# Prefer the repo-local virtual environment if it exists (matches the
# convention used by .venv/). Falls back to whatever `python` is on PATH so
# CI and containerized environments still work.
function Resolve-PythonExe {
    $venvPython = Join-Path $RepoRoot '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $venvPython) { return $venvPython }
    $sys = Get-Command python -ErrorAction SilentlyContinue
    if ($sys) { return $sys.Source }
    return $null
}

$PythonExe = Resolve-PythonExe

function Write-Step {
    param([string]$Label)
    Write-Host ""
    Write-Host "--- $Label ---" -ForegroundColor Cyan
}

function Assert-Command {
    param(
        [string]$Name,
        [string]$Hint
    )
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        Write-Host "Missing required tool: $Name" -ForegroundColor Red
        if ($Hint) { Write-Host "  $Hint" -ForegroundColor Yellow }
        exit 1
    }
}

function Assert-Python {
    if (-not $PythonExe) {
        Write-Host "Missing required tool: python" -ForegroundColor Red
        Write-Host "  Install Python 3.12 (see .python-version) or create a .venv in the repo root." -ForegroundColor Yellow
        exit 1
    }
}

function Invoke-Native {
    # Run a native command and fail the script if it returns non-zero.
    $exe, $rest = $args
    & $exe @rest
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed (exit $LASTEXITCODE): $exe $($rest -join ' ')"
    }
}

function Get-PowerShellExe {
    if (Get-Command pwsh -ErrorAction SilentlyContinue) { return 'pwsh' }
    return 'powershell'
}

function Invoke-Setup {
    Write-Step 'Environment check'
    Assert-Python
    Assert-Command 'npm' 'Install Node 22 (see .nvmrc) from https://nodejs.org/'

    $pythonVersion = (& $PythonExe --version) 2>&1
    $nodeVersion   = (& node --version) 2>&1
    Write-Host "python: $pythonVersion  ($PythonExe)"
    Write-Host "node:   $nodeVersion"

    Write-Step '.env bootstrap'
    $envPath     = Join-Path $RepoRoot '.env'
    $envExample  = Join-Path $RepoRoot '.env.example'
    if (-not (Test-Path $envPath) -and (Test-Path $envExample)) {
        Copy-Item $envExample $envPath
        Write-Host "Created .env from .env.example (edit to fill secrets if needed)."
    }
    else {
        Write-Host ".env already present -- leaving as-is."
    }

    Write-Step 'Backend dependencies (pip)'
    Invoke-Native $PythonExe -m pip install --upgrade pip
    Invoke-Native $PythonExe -m pip install -r (Join-Path $RepoRoot 'backend\requirements.txt')
    Invoke-Native $PythonExe -m pip install -r (Join-Path $RepoRoot 'requirements-dev.txt')

    Write-Step 'Frontend dependencies (npm)'
    Invoke-Native npm --prefix (Join-Path $RepoRoot 'frontend-react') install

    Write-Host ""
    Write-Host "Setup complete. Next:" -ForegroundColor Green
    Write-Host "  .\scripts\dev-setup.ps1 dev     # start dev servers"
    Write-Host "  .\scripts\dev-setup.ps1 check   # run local CI simulation"
}

function Invoke-Dev {
    Assert-Python
    Assert-Command 'npm' 'Run setup first.'

    $backendCmd = "& '$PythonExe' -m uvicorn backend.app:app --host 0.0.0.0 --port 5000 --reload"
    $psExe = Get-PowerShellExe

    Write-Step 'Backend (new window)'
    Write-Host "Launching: $backendCmd"
    $launchCmd = "Set-Location -LiteralPath '$RepoRoot'; Write-Host 'Backend on http://localhost:5000' -ForegroundColor Green; $backendCmd"
    Start-Process -FilePath $psExe `
        -ArgumentList @('-NoExit', '-NoProfile', '-Command', $launchCmd) `
        -WorkingDirectory $RepoRoot | Out-Null

    Write-Step 'Frontend (this window -- Ctrl+C to stop)'
    Write-Host 'Frontend on http://localhost:5173 (Vite proxies /api, /tasks, /transcribe to :5000)'
    Push-Location (Join-Path $RepoRoot 'frontend-react')
    try {
        Invoke-Native npm run dev
    }
    finally {
        Pop-Location
    }
}

function Invoke-Test {
    Assert-Python
    Write-Step 'pytest'
    Invoke-Native $PythonExe -m pytest tests/ -q
}

function Invoke-Lint {
    Assert-Python
    Write-Step 'flake8 (CI scope)'
    Invoke-Native $PythonExe -m flake8 `
        tests backend/shared backend/services `
        backend/models.py backend/task_persistence.py

    Assert-Command 'npm' 'Run setup first.'
    Write-Step 'frontend ESLint'
    Invoke-Native npm --prefix (Join-Path $RepoRoot 'frontend-react') run lint
}

function Invoke-Check {
    Invoke-Lint
    Invoke-Test
    Write-Host ""
    Write-Host "--- check OK ---" -ForegroundColor Green
}

function Invoke-Clean {
    Write-Step 'Remove Python caches'
    Get-ChildItem -Path $RepoRoot -Recurse -Force -Directory `
        -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -in @('__pycache__', '.pytest_cache', '.ruff_cache') -and
            $_.FullName -notmatch '\\\.venv\\' -and
            $_.FullName -notmatch '\\node_modules\\'
        } |
        ForEach-Object {
            Write-Host "rm $($_.FullName)"
            Remove-Item -Recurse -Force -LiteralPath $_.FullName -ErrorAction SilentlyContinue
        }

    Write-Step 'Remove frontend build artifacts'
    $distPath = Join-Path $RepoRoot 'frontend-react\dist'
    if (Test-Path $distPath) {
        Write-Host "rm $distPath"
        Remove-Item -Recurse -Force -LiteralPath $distPath
    }

    Write-Step 'Remove temp/ contents'
    # NOTE: outputs/ and uploads/ are intentionally preserved (user artifacts).
    $tempPath = Join-Path $RepoRoot 'temp'
    if (Test-Path $tempPath) {
        Get-ChildItem -LiteralPath $tempPath -Force -ErrorAction SilentlyContinue |
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "Cleared temp/ contents"
    }

    Write-Host ""
    Write-Host "--- clean OK ---" -ForegroundColor Green
}

function Show-Help {
    Get-Help -Full $PSCommandPath
}

switch ($Command) {
    'setup' { Invoke-Setup }
    'dev'   { Invoke-Dev }
    'test'  { Invoke-Test }
    'lint'  { Invoke-Lint }
    'check' { Invoke-Check }
    'clean' { Invoke-Clean }
    default { Show-Help }
}
