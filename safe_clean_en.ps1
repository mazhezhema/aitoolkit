# ============================================
# Safe Clean Script - Only removes cache and temp files
# No configuration or important data will be deleted
# ============================================

Write-Host "Starting safe cleanup operation..." -ForegroundColor Cyan
Write-Host "Only cleaning temporary files and cache, keeping all configurations" -ForegroundColor Gray
Write-Host ""

# ========== 1. System Temp Files ==========
Write-Host "1. Cleaning system temporary files..." -ForegroundColor Green

$tempPaths = @(
    "$env:TEMP",
    "$env:LOCALAPPDATA\Temp",
    "C:\Windows\Temp"
)

$totalTempCleaned = 0
foreach ($path in $tempPaths) {
    if (Test-Path $path) {
        try {
            $files = Get-ChildItem -Path $path -File -Recurse -ErrorAction SilentlyContinue
            $fileCount = $files.Count
            if ($fileCount -gt 0) {
                $totalTempCleaned += $fileCount
                $files | Remove-Item -Force -ErrorAction SilentlyContinue
                Write-Host "   [OK] Cleaned $path ($fileCount files)" -ForegroundColor Gray
            } else {
                Write-Host "   [INFO] $path directory is empty" -ForegroundColor DarkGray
            }
        } catch {
            Write-Host "   [WARN] Some files are in use: $path" -ForegroundColor DarkYellow
        }
    }
}

# ========== 2. Browser Cache ==========
Write-Host "`n2. Cleaning browser cache..." -ForegroundColor Green

# Chrome cache
$chromeCache = "$env:LOCALAPPDATA\Google\Chrome\User Data\Default\Cache"
if (Test-Path $chromeCache) {
    try {
        Remove-Item -Path "$chromeCache\*" -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "   [OK] Chrome cache cleaned" -ForegroundColor Gray
    } catch {
        Write-Host "   [WARN] Chrome cache files are in use" -ForegroundColor DarkYellow
    }
}

# ========== 3. Development Tool Cache ==========
Write-Host "`n3. Cleaning development tool cache..." -ForegroundColor Green

# Cursor cache (not deleting extensions)
$cursorCacheDirs = @(
    "$env:USERPROFILE\.cursor\Cache",
    "$env:USERPROFILE\.cursor\CacheStorage",
    "$env:USERPROFILE\.cursor\Code Cache",
    "$env:USERPROFILE\.cursor\GPUCache"
)

foreach ($dir in $cursorCacheDirs) {
    if (Test-Path $dir) {
        try {
            Remove-Item -Path "$dir\*" -Recurse -Force -ErrorAction SilentlyContinue
            Write-Host "   [OK] Cleaned Cursor cache: $($dir.Split('\')[-1])" -ForegroundColor Gray
        } catch {
            Write-Host "   [WARN] Cursor cache files are in use" -ForegroundColor DarkYellow
        }
    }
}

# VS Code cache
$vscodeCache = "$env:APPDATA\Code\Cache"
if (Test-Path $vscodeCache) {
    try {
        Remove-Item -Path "$vscodeCache\*" -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "   [OK] VS Code cache cleaned" -ForegroundColor Gray
    } catch {
        Write-Host "   [WARN] VS Code cache files are in use" -ForegroundColor DarkYellow
    }
}

# ========== 4. npm Cache (safe way) ==========
Write-Host "`n4. Cleaning npm cache (safe way)..." -ForegroundColor Green
Write-Host "   Using 'npm cache clean --force'..." -ForegroundColor Gray

try {
    $npmResult = npm cache clean --force 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "   [OK] npm cache cleaned" -ForegroundColor Gray
    } else {
        Write-Host "   [WARN] npm cache cleanup may have failed" -ForegroundColor DarkYellow
    }
} catch {
    Write-Host "   [WARN] Cannot execute npm command" -ForegroundColor DarkYellow
}

# ========== 5. Yarn Cache ==========
Write-Host "`n5. Cleaning Yarn cache..." -ForegroundColor Green

$yarnCache = "$env:LOCALAPPDATA\Yarn\cache"
if (Test-Path $yarnCache) {
    try {
        Remove-Item -Path "$yarnCache\*" -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "   [OK] Yarn cache cleaned" -ForegroundColor Gray
    } catch {
        Write-Host "   [WARN] Yarn cache files are in use" -ForegroundColor DarkYellow
    }
}

# ========== 6. Python pip Cache ==========
Write-Host "`n6. Cleaning Python pip cache..." -ForegroundColor Green

$pipCache = "$env:LOCALAPPDATA\pip\cache"
if (Test-Path $pipCache) {
    try {
        Remove-Item -Path "$pipCache\*" -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "   [OK] pip cache cleaned" -ForegroundColor Gray
    } catch {
        Write-Host "   [WARN] pip cache files are in use" -ForegroundColor DarkYellow
    }
}

# ========== 7. Windows Update Cache ==========
Write-Host "`n7. Cleaning Windows update cache..." -ForegroundColor Green
Write-Host "   This may take a few minutes..." -ForegroundColor Gray

try {
    dism /online /Cleanup-Image /StartComponentCleanup /ResetBase 2>&1 | Out-Null
    Write-Host "   [OK] Windows update cache cleaned" -ForegroundColor Gray
} catch {
    Write-Host "   [WARN] Cannot clean Windows update cache (may need admin rights)" -ForegroundColor DarkYellow
}

# ========== Cleanup Complete ==========
Write-Host "`n" + "="*50 -ForegroundColor Cyan
Write-Host "Safe cleanup completed!" -ForegroundColor Green
Write-Host "="*50 -ForegroundColor Cyan

Write-Host "`nCleaning summary:" -ForegroundColor White
Write-Host "   • System temporary files" -ForegroundColor Cyan
Write-Host "   • Browser cache (Chrome)" -ForegroundColor Cyan
Write-Host "   • Development tool cache (Cursor, VS Code)" -ForegroundColor Cyan
Write-Host "   • npm and Yarn package cache" -ForegroundColor Cyan
Write-Host "   • Python pip cache" -ForegroundColor Cyan
Write-Host "   • Windows update cache" -ForegroundColor Cyan

Write-Host "`nNotes:" -ForegroundColor Yellow
Write-Host "   • All configurations and personal data are preserved" -ForegroundColor Gray
Write-Host "   • Only cache files were cleaned, apps will regenerate them automatically" -ForegroundColor Gray
Write-Host "   • Recommend restarting development tools to ensure cache is rebuilt" -ForegroundColor Gray

Write-Host "`nOperation completed!" -ForegroundColor Green
Write-Host ""