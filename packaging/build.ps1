# Builds the Windows app.  Run from the project folder:   powershell -ExecutionPolicy Bypass -File packaging\build.ps1
#
# Makes:
#   dist\ApplyAndPray\ApplyAndPray.exe        the app (a folder: keep all its files together)
#   dist\ApplyAndPray-windows.zip             the same folder zipped: upload this to GitHub Releases
#   dist\ApplyAndPray-Setup.exe               an installer, only if Inno Setup 6 is installed (free: https://jrsoftware.org/isdl.php)

$ErrorActionPreference = "Continue"   # Tools print warnings on stderr: success is checked with $LASTEXITCODE below
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = Join-Path $root "venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "No venv found. Create it first: py -3.11 -m venv venv; venv\Scripts\pip install -r requirements.txt" }

Write-Host "1/3 Installing the build tool..."
& $python -m pip install --quiet "pyinstaller>=6.10"
if ($LASTEXITCODE -ne 0) { throw "pip failed" }

Write-Host "2/3 Building the app (takes a few minutes)..."
& $python -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging\ApplyAndPray.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

Write-Host "3/3 Packing..."
$zip = Join-Path $root "dist\ApplyAndPray-windows.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path (Join-Path $root "dist\ApplyAndPray") -DestinationPath $zip -CompressionLevel Optimal

$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe", "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($iscc) {
    & $iscc /Qp packaging\installer.iss
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
    Write-Host "Installer: dist\ApplyAndPray-Setup.exe"
} else {
    Write-Host "Inno Setup not found: skipped the installer (the zip works on its own)."
}
Write-Host "Done: $zip"
