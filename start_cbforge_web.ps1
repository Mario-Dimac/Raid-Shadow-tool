param(
    [switch]$SkipStartupRefresh,
    [switch]$CheckOnly,
    [string]$PythonPath = ""
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

function Get-PyLauncherPath {
    param([string]$Version)
    try {
        $resolved = & py "-$Version" -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $resolved) {
            $candidate = ($resolved | Select-Object -First 1).Trim()
            if ($candidate -and (Test-Path $candidate)) {
                return $candidate
            }
        }
    } catch {
        return ""
    }
    return ""
}

function Resolve-PythonPath {
    param([string]$RequestedPath)

    $candidates = @()
    if ($RequestedPath) {
        $candidates += $RequestedPath
    }
    if ($env:CBFORGE_PYTHON) {
        $candidates += $env:CBFORGE_PYTHON
    }

    $py311 = Get-PyLauncherPath "3.11"
    if ($py311) {
        $candidates += $py311
    }

    try {
        $commandPython = (Get-Command python -ErrorAction Stop).Source
        if ($commandPython) {
            $candidates += $commandPython
        }
    } catch {
    }

    $candidates += @(
        "C:\Program Files\Python311\python.exe",
        "C:\Users\acdad\AppData\Local\Programs\Python\Python312\python.exe",
        "C:\Users\acdad\AppData\Local\Programs\Python\Python311\python.exe"
    )

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) {
            return (Resolve-Path $candidate).Path
        }
    }

    throw "Python non trovato. Imposta CBFORGE_PYTHON oppure passa -PythonPath."
}

function Get-MissingModules {
    param([string]$Executable)

    $script = "import importlib.util; modules=['lz4','msgpack','numpy','pandas','sklearn']; missing=[name for name in modules if importlib.util.find_spec(name) is None]; print(*missing, sep='\\n')"
    $output = & $Executable -c $script
    if ($LASTEXITCODE -ne 0) {
        throw "Verifica dipendenze fallita per $Executable."
    }
    return @($output | Where-Object { $_ -and $_.Trim() })
}

$pythonExe = Resolve-PythonPath -RequestedPath $PythonPath
Set-Location $ProjectRoot

Write-Host "CB Forge launcher"
Write-Host "Progetto: $ProjectRoot"
Write-Host "Python:  $pythonExe"

$missingModules = Get-MissingModules -Executable $pythonExe
if ($missingModules.Count -gt 0) {
    Write-Host "Dipendenze mancanti rilevate: $($missingModules -join ', ')"
    & $pythonExe -m pip install -r (Join-Path $ProjectRoot "requirements.txt") -r (Join-Path $ProjectRoot "requirements-ai.txt")
    if ($LASTEXITCODE -ne 0) {
        throw "Installazione dipendenze fallita."
    }
} else {
    Write-Host "Dipendenze base e AI gia' presenti."
}

if ($CheckOnly) {
    Write-Host "Controllo completato. Nessun server avviato perche' hai usato -CheckOnly."
    exit 0
}

$serverArgs = @("cbforge_web.py")
if ($SkipStartupRefresh) {
    $serverArgs += "--skip-startup-refresh"
}

Write-Host "Avvio server web..."
& $pythonExe @serverArgs
exit $LASTEXITCODE
