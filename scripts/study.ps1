param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $StudyArgs
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
Set-Location -LiteralPath $repoRoot

if (-not (Test-Path -LiteralPath $python)) {
    Write-Host 'Preparing the local Python environment (first run only)...'
    py -m venv (Join-Path $repoRoot '.venv')
}

$null = & $python -c "import importlib.util, sys; sys.exit(any(importlib.util.find_spec(x) is None for x in ['study','fsrs','fastapi','uvicorn','filelock']))" 2>$null
if ($LASTEXITCODE -ne 0) {
    & $python -m pip install -e "$repoRoot[dev]"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

if ($StudyArgs.Count -eq 0) { $StudyArgs = @('app') }
if ($StudyArgs[0] -eq 'app') {
    $webIndex = Join-Path $repoRoot 'src\study\web\index.html'
    $sources = @(Get-ChildItem -LiteralPath (Join-Path $repoRoot 'frontend\src') -Recurse -File)
    $sources += Get-Item -LiteralPath (Join-Path $repoRoot 'frontend\index.html'), (Join-Path $repoRoot 'frontend\package-lock.json'), (Join-Path $repoRoot 'frontend\vite.config.ts')
    $latestSource = ($sources | Sort-Object LastWriteTime -Descending | Select-Object -First 1).LastWriteTime
    $buildNeeded = -not (Test-Path -LiteralPath $webIndex)
    if (-not $buildNeeded) { $buildNeeded = $latestSource -gt (Get-Item -LiteralPath $webIndex).LastWriteTime }
    if ($buildNeeded) {
        if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
            Write-Host 'Install Node.js LTS from nodejs.org, then reopen Start Study.'
            exit 1
        }
        Push-Location -LiteralPath (Join-Path $repoRoot 'frontend')
        try {
            & npm.cmd ci
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
            & npm.cmd run build
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        } finally { Pop-Location }
    }
}

if ($StudyArgs.Count -eq 1 -and $StudyArgs[0] -eq '_quality') {
    & $python -m pytest
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $python -m ruff check --no-cache .
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $python -m ruff format --check src tests
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Push-Location -LiteralPath (Join-Path $repoRoot 'frontend')
    try {
        & npm.cmd ci
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        foreach ($qualityStep in @('test', 'format:check', 'build')) {
            & npm.cmd run $qualityStep
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        }
        & npx.cmd playwright install chromium
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & npm.cmd run test:browser
        exit $LASTEXITCODE
    } finally { Pop-Location }
}

& $python -m study --root $repoRoot @StudyArgs
exit $LASTEXITCODE
