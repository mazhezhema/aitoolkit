param(
    [switch]$Apply,
    [switch]$ConfirmAll
)

$isDryRun = -not $Apply

function Invoke-Clean {
    param(
        [string]$TargetPath,
        [string]$Label
    )

    if (-not (Test-Path $TargetPath)) {
        return
    }

    if ($isDryRun) {
        Write-Host "   [PREVIEW] Will clean: $Label" -ForegroundColor DarkCyan
        return
    }

    try {
        Remove-Item -Path $TargetPath -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "   [OK] $Label cleaned" -ForegroundColor Gray
    } catch {
        Write-Host "   [WARN] Some $Label files are in use" -ForegroundColor DarkYellow
    }
}

Write-Host "Starting safe cleanup..." -ForegroundColor Cyan
Write-Host "Only temporary/cache files are targeted. Config and personal data stay intact." -ForegroundColor Gray

if ($isDryRun) {
    Write-Host "Mode: PREVIEW (no files will be deleted)" -ForegroundColor Yellow
    Write-Host "To apply cleanup: .\safe_clean_en.ps1 -Apply" -ForegroundColor DarkYellow
} else {
    Write-Host "Mode: APPLY (cache files will be deleted)" -ForegroundColor Yellow
}
Write-Host ""

if (-not $isDryRun -and -not $ConfirmAll) {
    $answer = Read-Host "Confirm cleanup? Type YES to continue"
    if ($answer -ne "YES") {
        Write-Host "Cancelled." -ForegroundColor Yellow
        exit 0
    }
}

Write-Host "1) Cleaning system temp files..." -ForegroundColor Green
$tempPaths = @(
    "$env:TEMP",
    "$env:LOCALAPPDATA\Temp",
    "C:\Windows\Temp"
)
foreach ($path in $tempPaths) {
    if (-not (Test-Path $path)) { continue }
    if ($isDryRun) {
        Write-Host "   [PREVIEW] Will clean files in: $path" -ForegroundColor DarkCyan
        continue
    }
    try {
        $files = Get-ChildItem -Path $path -File -Recurse -ErrorAction SilentlyContinue
        $count = @($files).Count
        if ($count -gt 0) {
            $files | Remove-Item -Force -ErrorAction SilentlyContinue
            Write-Host "   [OK] $path ($count files)" -ForegroundColor Gray
        } else {
            Write-Host "   [INFO] $path is empty" -ForegroundColor DarkGray
        }
    } catch {
        Write-Host "   [WARN] Some files are in use: $path" -ForegroundColor DarkYellow
    }
}

Write-Host "`n2) Cleaning browser cache..." -ForegroundColor Green
$chromeCache = "$env:LOCALAPPDATA\Google\Chrome\User Data\Default\Cache"
Invoke-Clean -TargetPath "$chromeCache\*" -Label "Chrome cache"

Write-Host "`n3) Cleaning development tool cache..." -ForegroundColor Green
$cursorCacheDirs = @(
    "$env:USERPROFILE\.cursor\Cache",
    "$env:USERPROFILE\.cursor\CacheStorage",
    "$env:USERPROFILE\.cursor\Code Cache",
    "$env:USERPROFILE\.cursor\GPUCache"
)
foreach ($dir in $cursorCacheDirs) {
    Invoke-Clean -TargetPath "$dir\*" -Label "Cursor cache: $($dir.Split('\')[-1])"
}
$vscodeCache = "$env:APPDATA\Code\Cache"
Invoke-Clean -TargetPath "$vscodeCache\*" -Label "VS Code cache"

Write-Host "`n4) Cleaning npm cache..." -ForegroundColor Green
try {
    if ($isDryRun) {
        Write-Host "   [PREVIEW] Will run: npm cache clean --force" -ForegroundColor DarkCyan
    } else {
        $npmResult = npm cache clean --force 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "   [OK] npm cache cleaned" -ForegroundColor Gray
        } else {
            Write-Host "   [WARN] npm cleanup may have failed: $npmResult" -ForegroundColor DarkYellow
        }
    }
} catch {
    Write-Host "   [WARN] Cannot execute npm command" -ForegroundColor DarkYellow
}

Write-Host "`n5) Cleaning Yarn cache..." -ForegroundColor Green
$yarnCache = "$env:LOCALAPPDATA\Yarn\cache"
Invoke-Clean -TargetPath "$yarnCache\*" -Label "Yarn cache"

Write-Host "`n6) Cleaning pip cache..." -ForegroundColor Green
$pipCache = "$env:LOCALAPPDATA\pip\cache"
Invoke-Clean -TargetPath "$pipCache\*" -Label "pip cache"

Write-Host "`n7) Cleaning Windows update cache..." -ForegroundColor Green
try {
    if ($isDryRun) {
        Write-Host "   [PREVIEW] Will run: dism /online /Cleanup-Image /StartComponentCleanup /ResetBase" -ForegroundColor DarkCyan
    } else {
        dism /online /Cleanup-Image /StartComponentCleanup /ResetBase 2>&1 | Out-Null
        Write-Host "   [OK] Windows update cache cleaned" -ForegroundColor Gray
    }
} catch {
    Write-Host "   [WARN] Admin rights may be required" -ForegroundColor DarkYellow
}

Write-Host "`nSafe cleanup flow completed." -ForegroundColor Green
