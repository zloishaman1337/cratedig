# One-shot Windows build: venv -> deps -> icons -> onedir (PyInstaller) -> installer (Inno).
# Windows analog of packaging/macos/build_all.sh.
#
#   pwsh packaging/windows/build_all.ps1 [version]
#
# Output: dist\cratedig\               (onedir frozen app)
#         packaging\windows\Output\cratedig-setup-<version>.exe  (Inno installer)
#
# Version SSOT is pyproject.toml; pass [version] explicitly (UPDATE_RULES.md §2).
[CmdletBinding()]
param([string]$Version = "0.1.0")

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path "$PSScriptRoot\..\..").Path
Set-Location $Root

Write-Host "==> Python venv"
if (-not (Test-Path .venv)) { python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install -U pip
& .\.venv\Scripts\pip.exe install -e ".[gui,analysis,download,metadata,build]"

Write-Host "==> Bundled ffmpeg/ffplay check"
$bin = Join-Path $Root "packaging\bin\windows"
foreach ($tool in @("ffmpeg.exe", "ffplay.exe")) {
    if (-not (Test-Path (Join-Path $bin $tool))) {
        Write-Warning "Missing $bin\$tool — bundled playback/decoding will fall back to PATH. " +
            "Stage static Windows builds there before release (git-ignored)."
    }
}

Write-Host "==> Render icons (.ico)"
& .\.venv\Scripts\python.exe packaging\render_icons.py

Write-Host "==> PyInstaller (onedir)"
& .\.venv\Scripts\pyinstaller.exe packaging\cratedig.spec --noconfirm

Write-Host "==> Inno Setup installer (v$Version)"
$iscc = Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $iscc)) {
    throw "ISCC.exe not found at $iscc. Install Inno Setup 6 (winget install JRSoftware.InnoSetup)."
}
& $iscc "/DVersion=$Version" "packaging\windows\cratedig.iss"

Write-Host ""
Write-Host "Done:"
Write-Host "  dist\cratedig\"
Write-Host "  packaging\windows\Output\cratedig-setup-$Version.exe"
