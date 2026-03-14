# Poketeer - Build APK without Android Studio
# Run from the project root: .\build-apk.ps1

$ErrorActionPreference = "Stop"
$SDK = "$env:USERPROFILE\android-sdk"
$TOOLS = "$SDK\cmdline-tools\latest"

Write-Host ""
Write-Host "=== Poketeer APK Builder ===" -ForegroundColor Cyan
Write-Host ""

# 1. Download Android command-line tools if not present
if (-not (Test-Path "$TOOLS\bin\sdkmanager.bat")) {
    Write-Host "[1/5] Downloading Android command-line tools..." -ForegroundColor Yellow
    $zip = "$env:TEMP\android-cmdtools.zip"
    $url = "https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip"
    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
    Write-Host "      Extracting..." -ForegroundColor Gray
    $tmp = "$env:TEMP\android-cmdtools"
    Expand-Archive -Path $zip -DestinationPath $tmp -Force
    New-Item -ItemType Directory -Path "$SDK\cmdline-tools\latest" -Force | Out-Null
    Copy-Item "$tmp\cmdline-tools\*" "$TOOLS\" -Recurse -Force
    Remove-Item $zip, $tmp -Recurse -Force
    Write-Host "      Done." -ForegroundColor Green
} else {
    Write-Host "[1/5] Android command-line tools already present." -ForegroundColor Green
}

# 2. Accept licences and install SDK packages
$env:ANDROID_HOME = $SDK
$env:Path = "$TOOLS\bin;$SDK\platform-tools;$env:Path"

Write-Host "[2/5] Installing Android SDK packages (may take a few minutes)..." -ForegroundColor Yellow
"y`ny`ny`ny`ny`ny`ny`ny" | & "$TOOLS\bin\sdkmanager.bat" "platforms;android-36" "build-tools;35.0.0" "platform-tools" 2>&1 | Where-Object { $_ -match "^(Downloading|Installing|done)" }
Write-Host "      Done." -ForegroundColor Green

# 3. Build the web bundle
Write-Host "[3/5] Building web bundle..." -ForegroundColor Yellow
Set-Location $PSScriptRoot
npm run build
Write-Host "      Done." -ForegroundColor Green

# 4. Sync Capacitor
Write-Host "[4/5] Syncing Capacitor..." -ForegroundColor Yellow
npx cap sync android 2>&1 | Out-Null
Write-Host "      Done." -ForegroundColor Green

# 5. Build APK
Write-Host "[5/5] Building APK with Gradle..." -ForegroundColor Yellow
Set-Location "$PSScriptRoot\android"

$sdkDir = $SDK -replace "\\","/"
Set-Content "local.properties" "sdk.dir=$sdkDir"

$env:JAVA_HOME = (java -XshowSettings:property -version 2>&1 | Select-String "java.home").ToString().Split("=")[1].Trim()

.\gradlew.bat assembleDebug --no-daemon 2>&1

$apk = "app\build\outputs\apk\debug\app-debug.apk"
if (Test-Path $apk) {
    $dest = "$PSScriptRoot\Poketeer.apk"
    Copy-Item $apk $dest -Force
    Write-Host ""
    Write-Host "==========================================" -ForegroundColor Green
    Write-Host " APK ready: $dest" -ForegroundColor Green
    Write-Host "==========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "To install on your Samsung:" -ForegroundColor Cyan
    Write-Host "  1. Copy Poketeer.apk to your phone" -ForegroundColor White
    Write-Host "  2. Open it in Files app (allow Unknown Sources if prompted)" -ForegroundColor White
    Write-Host ""
} else {
    Write-Host "Build failed - check the output above." -ForegroundColor Red
    exit 1
}