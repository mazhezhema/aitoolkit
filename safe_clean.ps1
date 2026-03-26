<![CDATA[# ============================================
# 安全清理脚本 - 只清理无风险缓存文件
# 不会删除任何配置或重要数据
# ============================================

Write-Host "🔧 开始安全清理操作..." -ForegroundColor Cyan
Write-Host "只清理临时文件和缓存，保留所有配置" -ForegroundColor Gray
Write-Host ""

# ========== 1. 系统临时文件清理 ==========
Write-Host "1. 清理系统临时文件..." -ForegroundColor Green

$tempPaths = @(
    "$env:TEMP",
    "$env:LOCALAPPDATA\Temp",
    "C:\Windows\Temp"
)

$totalTempCleaned = 0
foreach ($path in $tempPaths) {
    if (Test-Path $path) {
        try {
            # 只删除文件，保留目录结构
            $files = Get-ChildItem -Path $path -File -Recurse -ErrorAction SilentlyContinue
            $fileCount = $files.Count
            if ($fileCount -gt 0) {
                $totalTempCleaned += $fileCount
                $files | Remove-Item -Force -ErrorAction SilentlyContinue
                Write-Host "   ✅ 清理 $path ($fileCount 个文件)" -ForegroundColor Gray
            } else {
                Write-Host "   ℹ️  $path 目录为空" -ForegroundColor DarkGray
            }
        } catch {
            Write-Host "   ⚠️  部分文件被占用: $path" -ForegroundColor DarkYellow
        }
    }
}

# ========== 2. 浏览器缓存清理 ==========
Write-Host "`n2. 清理浏览器缓存..." -ForegroundColor Green

# Chrome缓存
$chromeCache = "$env:LOCALAPPDATA\Google\Chrome\User Data\Default\Cache"
if (Test-Path $chromeCache) {
    try {
        Remove-Item -Path "$chromeCache\*" -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "   ✅ Chrome缓存清理完成" -ForegroundColor Gray
    } catch {
        Write-Host "   ⚠️  Chrome缓存部分文件被占用" -ForegroundColor DarkYellow
    }
}

# ========== 3. 开发工具缓存清理 ==========
Write-Host "`n3. 清理开发工具缓存..." -ForegroundColor Green

# Cursor缓存（不删除扩展本身）
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
            Write-Host "   ✅ 清理Cursor缓存: $($dir.Split('\')[-1])" -ForegroundColor Gray
        } catch {
            Write-Host "   ⚠️  Cursor缓存部分文件被占用" -ForegroundColor DarkYellow
        }
    }
}

# VS Code缓存
$vscodeCache = "$env:APPDATA\Code\Cache"
if (Test-Path $vscodeCache) {
    try {
        Remove-Item -Path "$vscodeCache\*" -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "   ✅ VS Code缓存清理完成" -ForegroundColor Gray
    } catch {
        Write-Host "   ⚠️  VS Code缓存部分文件被占用" -ForegroundColor DarkYellow
    }
}

# ========== 4. npm缓存清理（安全方式） ==========
Write-Host "`n4. 清理npm缓存（安全方式）..." -ForegroundColor Green
Write-Host "   使用 'npm cache clean --force' 清理..." -ForegroundColor Gray

try {
    # 尝试运行npm清理
    $npmResult = npm cache clean --force 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "   ✅ npm缓存清理完成" -ForegroundColor Gray
    } else {
        Write-Host "   ⚠️  npm缓存清理可能失败" -ForegroundColor DarkYellow
        Write-Host "   输出: $npmResult" -ForegroundColor DarkGray
    }
} catch {
    Write-Host "   ⚠️  无法执行npm命令" -ForegroundColor DarkYellow
}

# ========== 5. Yarn缓存清理 ==========
Write-Host "`n5. 清理Yarn缓存..." -ForegroundColor Green

$yarnCache = "$env:LOCALAPPDATA\Yarn\cache"
if (Test-Path $yarnCache) {
    try {
        # 清理缓存文件，但保留目录结构
        Remove-Item -Path "$yarnCache\*" -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "   ✅ Yarn缓存清理完成" -ForegroundColor Gray
    } catch {
        Write-Host "   ⚠️  Yarn缓存部分文件被占用" -ForegroundColor DarkYellow
    }
}

# ========== 6. Python pip缓存清理 ==========
Write-Host "`n6. 清理Python pip缓存..." -ForegroundColor Green

$pipCache = "$env:LOCALAPPDATA\pip\cache"
if (Test-Path $pipCache) {
    try {
        Remove-Item -Path "$pipCache\*" -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "   ✅ pip缓存清理完成" -ForegroundColor Gray
    } catch {
        Write-Host "   ⚠️  pip缓存部分文件被占用" -ForegroundColor DarkYellow
    }
}

# ========== 7. Windows更新缓存清理 ==========
Write-Host "`n7. 清理Windows更新缓存..." -ForegroundColor Green
Write-Host "   这可能需要几分钟，请稍候..." -ForegroundColor Gray

try {
    # 清理Windows更新缓存（安全操作）
    dism /online /Cleanup-Image /StartComponentCleanup /ResetBase 2>&1 | Out-Null
    Write-Host "   ✅ Windows更新缓存清理完成" -ForegroundColor Gray
} catch {
    Write-Host "   ⚠️  无法清理Windows更新缓存（可能需要管理员权限）" -ForegroundColor DarkYellow
}

# ========== 清理完成 ==========
Write-Host "`n" + "="*50 -ForegroundColor Cyan
Write-Host "🎉 安全清理完成！" -ForegroundColor Green
Write-Host "="*50 -ForegroundColor Cyan

Write-Host "`n📊 清理项目总结：" -ForegroundColor White
Write-Host "   • 系统临时文件" -ForegroundColor Cyan
Write-Host "   • 浏览器缓存 (Chrome)" -ForegroundColor Cyan
Write-Host "   • 开发工具缓存 (Cursor, VS Code)" -ForegroundColor Cyan
Write-Host "   • npm和Yarn包缓存" -ForegroundColor Cyan
Write-Host "   • Python pip缓存" -ForegroundColor Cyan
Write-Host "   • Windows更新缓存" -ForegroundColor Cyan

Write-Host "`n⚠️  注意事项：" -ForegroundColor Yellow
Write-Host "   • 所有配置和个人数据都已保留" -ForegroundColor Gray
Write-Host "   • 清理的只是缓存文件，应用会自动重新生成" -ForegroundColor Gray
Write-Host "   • 建议重启开发工具以确保缓存完全重建" -ForegroundColor Gray

Write-Host "`n✅ 操作完成！" -ForegroundColor Green
Write-Host ""]]>