param(
    [string]$Spec = "llama.cpp.launcher.spec",
    [string]$PythonExe = ""
)

$ErrorActionPreference = "Stop"

function Invoke-Retry {
    param(
        [scriptblock]$Action,
        [string]$Label,
        [bool]$Fatal = $true
    )

    $lastError = $null
    for ($i = 1; $i -le 10; $i++) {
        try {
            & $Action
            return $true
        } catch {
            $lastError = $_
            Start-Sleep -Milliseconds (200 * $i)
        }
    }

    if ($Fatal) {
        throw "Failed to $Label`: $lastError"
    }

    Write-Warning "Skipped $Label`: $lastError"
    return $false
}

$Core = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $Core
$Dist = Join-Path $Root "dist"
$TempRoot = Join-Path ([System.IO.Path]::GetTempPath()) "llama-cpp-launcher-build"
$TempBuild = Join-Path $TempRoot "build"
$TempDist = Join-Path $TempRoot "dist"

if ([string]::IsNullOrWhiteSpace($PythonExe)) {
    $PythonExe = "python"
}

if ($PythonExe -ne "python" -and -not (Test-Path -LiteralPath $PythonExe)) {
    throw "Python executable not found: $PythonExe"
}

Set-Location $Root

$SpecFile = Get-Item -LiteralPath (Join-Path $Root $Spec)

$BuildStart = Get-Date

if (Test-Path -LiteralPath $TempRoot) {
    Remove-Item -LiteralPath $TempRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $TempBuild, $TempDist -Force | Out-Null

& $PythonExe -m PyInstaller --clean --noconfirm --workpath $TempBuild --distpath $TempDist $SpecFile.FullName
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

if (-not (Test-Path -LiteralPath $TempDist)) {
    throw "Expected dist directory was not generated: $TempDist"
}

$ExeSource = Get-ChildItem -LiteralPath $TempDist -Filter "*.exe" |
    Where-Object { $_.LastWriteTime -ge $BuildStart.AddSeconds(-10) } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if ($null -eq $ExeSource) {
    $ExeSource = Get-ChildItem -LiteralPath $TempDist -Filter "*.exe" |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
}

if ($null -eq $ExeSource) {
    throw "Expected executable was not generated under: $TempDist"
}

$RootExe = Join-Path $Root $ExeSource.Name
Invoke-Retry -Label "copy executable to project root" -Action {
    Copy-Item -LiteralPath $ExeSource.FullName -Destination $RootExe -Force
} | Out-Null

New-Item -ItemType Directory -Path $Dist -Force | Out-Null
$DistExe = Join-Path $Dist $ExeSource.Name
if (Test-Path -LiteralPath $DistExe) {
    Invoke-Retry -Label "remove old dist executable" -Fatal $false -Action {
        Remove-Item -LiteralPath $DistExe -Force
    } | Out-Null
}

if (-not (Test-Path -LiteralPath $DistExe)) {
    Invoke-Retry -Label "copy executable to dist" -Fatal $false -Action {
        Copy-Item -LiteralPath $ExeSource.FullName -Destination $DistExe -Force
    } | Out-Null
}

Write-Host "Root launcher executable:"
Write-Host $RootExe
