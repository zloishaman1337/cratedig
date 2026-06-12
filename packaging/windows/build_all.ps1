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
    [switch]$Publish,
    # Tier override: "auto" diffs the manifest (default); "full"/"delta" force it.
    # The online client still always fetches the FULL asset, so releases that must
    # auto-update existing installs have to ship "full" until delta-over-the-wire lands.
    [ValidateSet("auto", "full", "delta")]
    [string]$Tier = "auto"
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path "$PSScriptRoot\..\..").Path
Set-Location $Root

# Auto-load the minisign key password from a gitignored .env (KEY=VALUE lines) so
# signing never has to prompt. An already-set environment variable wins.
$envFile = Join-Path $Root ".env"
if (-not $env:MINISIGN_PASSWORD -and (Test-Path $envFile)) {
    foreach ($line in Get-Content $envFile) {
        if ($line -match '^\s*MINISIGN_PASSWORD\s*=\s*(.+?)\s*$') {
            $env:MINISIGN_PASSWORD = $Matches[1]
        }
    }
}

Write-Host "==> Python venv"
if (-not (Test-Path .venv)) { python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install -U pip
& .\.venv\Scripts\pip.exe install -e ".[gui,analysis,download,metadata,convert,build]"

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

# Auto-tier decides whether THIS release can also offer a delta. The full installer
# is ALWAYS built (fresh installs + the client's fallback); a delta is built ALONGSIDE
# it when the diff is code-only, so the client can pick it (delta-over-the-wire).
$tier = "full"
if ($prev) {
    $diff = & $py packaging\make_manifest.py diff $prev.FullName $newManifest
    $diff | ForEach-Object { Write-Host "    $_" }
    if ($diff -match 'tier=delta') { $tier = "delta" }
}
if ($Tier -ne "auto") {
    Write-Host "==> Tier override: auto=$tier -> $Tier"
    $tier = $Tier
}
$wantDelta = ($tier -eq "delta") -and $prev

# The full installer is always produced.
Write-Host "==> Windows FULL installer (v$Version)"
& $iscc "/DVersion=$Version" "packaging\windows\cratedig.iss"
$full = "packaging\windows\Output\cratedig-setup-$Version.exe"
$assets = @($full)

# When the diff is code-only, also produce the small delta update installer.
$delta = $null
if ($wantDelta) {
    Write-Host "==> Windows DELTA update installer (v$Version)"
    $include = Join-Path $Root "packaging\windows\update-files.iss"
    & $py packaging\make_manifest.py build-win-include $prev.FullName $newManifest $include
    & $iscc "/DVersion=$Version" "packaging\windows\cratedig-update.iss"
    $delta = "packaging\windows\Output\cratedig-update-$Version.exe"
    $assets += $delta
}

# Signed release-meta sidecar: tells the client which versions the delta applies onto
# (empty delta_from when there's no delta -> client always falls back to full).
Write-Host "==> Release meta (delta gate)"
$meta = "packaging\windows\Output\release-meta-$Version.json"
if ($wantDelta) {
    & $py packaging\make_manifest.py emit-release-meta $newManifest $meta --old $prev.FullName
} else {
    & $py packaging\make_manifest.py emit-release-meta $newManifest $meta
}
$assets += $meta

if ($Sign -or $Publish) {
    Write-Host "==> Sign assets (minisign)"
    if (-not $env:MINISIGN_PASSWORD) {
        throw "Set `$env:MINISIGN_PASSWORD before signing (the minisign.key password)."
    }
    $key = Join-Path $Root "minisign.key"
    if (-not (Test-Path $key)) { throw "minisign.key not found at $key." }
    foreach ($a in $assets) {
        # minisign reads the key password from stdin; -t stamps a trusted comment.
        $env:MINISIGN_PASSWORD | minisign -S -m $a -s $key -x "$a.minisig" `
            -c "cratedig $Version" -t "cratedig $Version"
        if ($LASTEXITCODE -ne 0) { throw "minisign signing failed for $a." }
        Write-Host "    signed: $a.minisig"
    }
}

if ($Publish) {
    Write-Host "==> Publish to GitHub Releases (gh)"
    $tag = $Version
    $title = "CRATEDIG $Version"
    gh release view $tag 2>$null
    if ($LASTEXITCODE -ne 0) {
        gh release create $tag --title $title --notes "cratedig $Version (online-update baseline)."
        if ($LASTEXITCODE -ne 0) { throw "gh release create failed." }
    }
    $uploads = @()
    foreach ($a in $assets) { $uploads += $a; $uploads += "$a.minisig" }
    gh release upload $tag @uploads --clobber
    if ($LASTEXITCODE -ne 0) { throw "gh release upload failed." }
    Write-Host "    published $tag"
}

Write-Host ""
Write-Host "Done (tier=$tier, delta=$([bool]$delta)):"
Write-Host "  dist\cratedig\"
Write-Host "  $newManifest"
foreach ($a in $assets) { Write-Host "  $a" }
