[CmdletBinding()]
param(
    [ValidateSet('all', 'admin', 'print')]
    [string]$Target = 'all',
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$logRoot = Join-Path $repoRoot 'backend\var\startup'

function Resolve-Node {
    $nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
    if (-not $nodeCommand) {
        $fnmCommand = Get-Command fnm.exe -ErrorAction SilentlyContinue
        if ($fnmCommand) {
            (& $fnmCommand.Source env --shell powershell | Out-String) | Invoke-Expression
            $nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
        }
    }
    if (-not $nodeCommand) { throw 'Node.js is missing. Install Node.js 20 or later, then retry.' }
    return $nodeCommand.Source
}

function Test-Http([string]$Url) {
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -eq 200
    } catch { return $false }
}

function Test-Port([int]$Port) {
    return $null -ne (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
}

function Start-NodeService([string]$Name, [string]$Directory, [string]$Entry, [string[]]$ServiceArgs) {
    $entryPath = Join-Path $Directory $Entry
    if (-not (Test-Path -LiteralPath $entryPath)) {
        throw "Dependencies missing in $Directory. Run npm ci in that directory first."
    }
    $processArgs = @('"' + $entryPath + '"') + $ServiceArgs
    $process = Start-Process -FilePath $script:nodePath -ArgumentList $processArgs -WorkingDirectory $Directory -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logRoot "$Name.out.log") -RedirectStandardError (Join-Path $logRoot "$Name.err.log")
    return $process
}

function Wait-Ready([string]$Url, [System.Diagnostics.Process]$Process, [string]$Name) {
    $deadline = (Get-Date).AddSeconds(45)
    while ((Get-Date) -lt $deadline) {
        if (Test-Http $Url) { return }
        if ($Process.HasExited) { throw "$Name stopped. Check logs in $logRoot." }
        Start-Sleep -Milliseconds 500
    }
    throw "$Name did not become ready. Check logs in $logRoot."
}

try {
    $script:nodePath = Resolve-Node
    New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
    # Electron dev must launch its desktop app instead of running as Node.
    Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue
    Remove-Item Env:REMOTE_DEBUGGING_PORT -ErrorAction SilentlyContinue

    if (-not (Test-Http 'http://127.0.0.1:8000/openapi.json')) {
        Write-Warning 'Backend is offline (port 8000). Start the backend before logging in.'
    }

    if ($Target -in @('all', 'admin')) {
        if (Test-Http 'http://127.0.0.1:5173/src/main.ts') {
            Write-Host 'Admin frontend is already running.'
        } else {
            if (Test-Port 5173) { throw 'Port 5173 is occupied by another service.' }
            $adminProcess = Start-NodeService 'admin' (Join-Path $repoRoot 'admin-web') 'node_modules\vite\bin\vite.js' @('--host', '127.0.0.1', '--port', '5173', '--strictPort')
            Wait-Ready 'http://127.0.0.1:5173/src/main.ts' $adminProcess 'Admin frontend'
            Write-Host 'Admin frontend started.'
        }
        Write-Host 'Admin URL: http://127.0.0.1:5173'
        if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:5173' }
    }

    if ($Target -in @('all', 'print')) {
        $electronPath = Join-Path $repoRoot 'print-client\node_modules\electron\dist\electron.exe'
        $stationWindow = Get-Process electron -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 -and $_.Path -eq $electronPath } | Select-Object -First 1
        if ($stationWindow -and (Test-Http 'http://127.0.0.1:17650/health')) {
            Write-Host 'Print client is already running.'
        } else {
            if ((Test-Port 5174) -or (Test-Port 17650)) { throw 'Print ports (5174 or 17650) are occupied. Close the old preview or print client first.' }
            $printDirectory = Join-Path $repoRoot 'print-client'
            if (-not (Test-Path -LiteralPath (Join-Path $printDirectory 'node_modules\electron\dist\electron.exe'))) {
                throw 'Electron runtime is missing. In print-client, run: node node_modules/electron/install.js'
            }
            $printProcess = Start-NodeService 'print' $printDirectory 'node_modules\electron-vite\bin\electron-vite.js' @('dev')
            Wait-Ready 'http://127.0.0.1:17650/health' $printProcess 'Print client'
            Wait-Ready 'http://127.0.0.1:5174/main.ts' $printProcess 'Print client UI'
            Write-Host 'Print client started. Use the Electron desktop window.'
        }
    }
    Write-Host "Logs: $logRoot"
    exit 0
} catch {
    Write-Host "Startup failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
