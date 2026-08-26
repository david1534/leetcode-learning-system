param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $StudyArgs
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $python)) {
    Write-Host 'Preparing the local Python environment (first run only)...'
    py -m venv (Join-Path $repoRoot '.venv')
}

$null = & $python -c "import study, fsrs" 2>$null
if ($LASTEXITCODE -ne 0) {
    & $python -m pip install -e "$repoRoot[dev]"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

if ($StudyArgs.Count -eq 1 -and $StudyArgs[0] -eq '_quality') {
    & $python -m pytest
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $python -m ruff check --no-cache .
    exit $LASTEXITCODE
}

& $python -m study @StudyArgs
exit $LASTEXITCODE
