param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $StudyArgs
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
Set-Location -LiteralPath $repoRoot

if (-not (Test-Path -LiteralPath $python)) {
    Write-Host 'Preparing the Python environment (first run only)...'
    py -m venv (Join-Path $repoRoot '.venv')
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$projectHash = (Get-FileHash -LiteralPath (Join-Path $repoRoot 'pyproject.toml') -Algorithm SHA256).Hash
$pythonStamp = Join-Path $repoRoot '.venv\.study-project.sha256'
$probe = "import importlib.util,pathlib,sys; spec=importlib.util.find_spec('study'); missing=any(importlib.util.find_spec(name) is None for name in ('fsrs','fastapi','uvicorn','filelock')); correct=spec and pathlib.Path(spec.origin).resolve().parent == pathlib.Path(sys.argv[1]).resolve() / 'src/study'; sys.exit(missing or not correct)"
$null = & $python -I -c $probe $repoRoot 2>$null
$installNeeded = $LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $pythonStamp)
if (-not $installNeeded) { $installNeeded = (Get-Content -LiteralPath $pythonStamp -Raw).Trim() -ne $projectHash }
if ($installNeeded) {
    & $python -m pip install -e "$repoRoot[dev]"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    [System.IO.File]::WriteAllText($pythonStamp, $projectHash)
}

if ($StudyArgs.Count -eq 0) { $StudyArgs = @('app') }
if ($StudyArgs[0] -eq 'app') {
    $frontendRoot = Join-Path $repoRoot 'frontend'
    $webIndex = Join-Path $repoRoot 'src\study\web\index.html'
    $buildStamp = Join-Path $repoRoot 'src\study\web\.sources.sha256'
    $sources = @(Get-ChildItem -LiteralPath (Join-Path $frontendRoot 'src') -Recurse -File)
    $sources += Get-ChildItem -LiteralPath $frontendRoot -File | Where-Object { $_.Name -in @('index.html', 'package.json', 'package-lock.json', 'vite.config.ts') -or $_.Name -like 'tsconfig*.json' }
    $fingerprintText = ($sources | Sort-Object FullName | ForEach-Object { $_.FullName.Substring($frontendRoot.Length) + ':' + (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash }) -join "`n"
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try { $sourceHash = [System.BitConverter]::ToString($hasher.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($fingerprintText))) } finally { $hasher.Dispose() }
    $buildNeeded = -not (Test-Path -LiteralPath $webIndex) -or -not (Test-Path -LiteralPath $buildStamp)
    if (-not $buildNeeded) { $buildNeeded = (Get-Content -LiteralPath $buildStamp -Raw).Trim() -ne $sourceHash }
    if ($buildNeeded) {
        if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
            Write-Host 'Install Node.js LTS from nodejs.org, then reopen Start Study.'
            exit 1
        }
        Push-Location -LiteralPath $frontendRoot
        try {
            $lockHash = (Get-FileHash -LiteralPath 'package-lock.json' -Algorithm SHA256).Hash
            $dependencyStamp = Join-Path $frontendRoot 'node_modules\.study-lock.sha256'
            $dependenciesNeeded = -not (Test-Path -LiteralPath $dependencyStamp)
            if (-not $dependenciesNeeded) { $dependenciesNeeded = (Get-Content -LiteralPath $dependencyStamp -Raw).Trim() -ne $lockHash }
            if ($dependenciesNeeded) {
                & npm.cmd ci --no-audit --no-fund
                if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
                [System.IO.File]::WriteAllText($dependencyStamp, $lockHash)
            }
            & npm.cmd run build
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
            [System.IO.File]::WriteAllText($buildStamp, $sourceHash)
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
        & npm.cmd ci --no-audit --no-fund
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

& $python -I -m study --root $repoRoot @StudyArgs
exit $LASTEXITCODE