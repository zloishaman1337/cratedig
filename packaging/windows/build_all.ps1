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
param(
    [string]$Version = "0.1.0",
    # Sign the installer with minisign (requires $env:MINISIGN_PASSWORD + minisign.key in repo root).
    [switch]$Sign,
    # Publish the signed assets to GitHub Releases via `gh` (implies -Sign).
    [switch]$Publish
)

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

Write-Host "==> Bundled minisign (update verifier)"
$minisignDest = Join-Path $bin "minisign.exe"
if (-not (Test-Path $minisignDest)) {
    $src = (Get-Command minisign -ErrorAction SilentlyContinue).Source
    if ($src) {
        New-Item -ItemType Directory -Force $bin | Out-Null
        Copy-Item $src $minisignDest
        Write-Host "    staged minisign.exe from $src"
    } else {
        Write-Warning "minisign not found on PATH — online update verification won't work. " +
            "Install it (winget install jedisct1.minisign) before release."
    }
}

Write-Host "==> Render icons (.ico)"
& .\.venv\Scripts\python.exe packaging\render_icons.py

Write-Host "==> PyInstaller (onedir)"
& .\.venv\Scripts\pyinstaller.exe packaging\cratedig.spec --noconfirm

$iscc = Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $iscc)) {
    throw "ISCC.exe not found at $iscc. Install Inno Setup 6 (winget install JRSoftware.InnoSetup)."
}
$py = ".\.venv\Scripts\python.exe"

Write-Host "==> Release manifest (v$Version)"
$manifestDir = Join-Path $Root "packaging\release-manifests"
New-Item -ItemType Directory -Force $manifestDir | Out-Null
$newManifest = Join-Path $manifestDir "cratedig-$Version-win.json"
& $py packaging\make_manifest.py generate dist\cratedig $Version win $newManifest

# Pick the previous win manifest (newest version that isn't this one) to diff against.
$prev = Get-ChildItem $manifestDir -Filter "cratedig-*-win.json" |
    Where-Object { $_.FullName -ne $newManifest } |
    Sort-Object { [version]([regex]::Match($_.Name, 'cratedig-(.+)-win\.json').Groups[1].Value) } |
    Select-Object -Last 1

$tier = "full"
if ($prev) {
    $diff = & $py packaging\make_manifest.py diff $prev.FullName $newManifest
    $diff | ForEach-Object { Write-Host "    $_" }
    if ($diff -match 'tier=delta') { $tier = "delta" }
}

if ($tier -eq "delta") {
    Write-Host "==> Windows DELTA update installer (v$Version)"
    $include = Join-Path $Root "packaging\windows\update-files.iss"
    & $py packaging\make_manifest.py build-win-include $prev.FullName $newManifest $include
    & $iscc "/DVersion=$Version" "packaging\windows\cratedig-update.iss"
    $out = "packaging\windows\Output\cratedig-update-$Version.exe"
} else {
    Write-Host "==> Windows FULL installer (v$Version)"
    & $iscc "/DVersion=$Version" "packaging\windows\cratedig.iss"
    $out = "packaging\windows\Output\cratedig-setup-$Version.exe"
}

if ($Sign -or $Publish) {
    Write-Host "==> Sign installer (minisign)"
    if (-not $env:MINISIGN_PASSWORD) {
        throw "Set `$env:MINISIGN_PASSWORD before signing (the minisign.key password)."
    }
    $key = Join-Path $Root "minisign.key"
    if (-not (Test-Path $key)) { throw "minisign.key not found at $key." }
    $sig = "$out.minisig"
    # minisign reads the key password from stdin; -t stamps a trusted comment.
    $env:MINISIGN_PASSWORD | minisign -S -m $out -s $key -x $sig `
        -c "cratedig $Version installer" -t "cratedig $Version"
    if ($LASTEXITCODE -ne 0) { throw "minisign signing failed." }
    Write-Host "    signed: $sig"
}

if ($Publish) {
    Write-Host "==> Publish to GitHub Releases (gh)"
    $tag = $Version
    $title = "CRATEDIG $Version"
    # Create the release if absent, then upload the installer + signature.
    gh release view $tag 2>$null
    if ($LASTEXITCODE -ne 0) {
        gh release create $tag --title $title --notes "cratedig $Version (online-update baseline)."
        if ($LASTEXITCODE -ne 0) { throw "gh release create failed." }
    }
    gh release upload $tag $out "$out.minisig" --clobber
    if ($LASTEXITCODE -ne 0) { throw "gh release upload failed." }
    Write-Host "    published $tag"
}

Write-Host ""
Write-Host "Done ($tier):"
Write-Host "  dist\cratedig\"
Write-Host "  $newManifest"
Write-Host "  $out"
if ($Sign -or $Publish) { Write-Host "  $out.minisig" }
