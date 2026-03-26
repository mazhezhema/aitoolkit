# AI-Clean: AI工程师专用Windows硬盘清理工具设计方案

**日期**: 2026-03-20
**状态**: 已批准
**版本**: 1.0
**目标**: 解决AI工程师C盘空间不足问题，安全清理ClaudeCode、Cursor等工具缓存

## 1. 项目概述

### 1.1 问题背景
- AI工程师使用ClaudeCode、Cursor等工具产生大量缓存文件
- Windows系统垃圾积累占用C盘空间
- C盘使用率达94%，仅剩6GB空间
- 需要安全、智能的清理方案，杜绝误删

### 1.2 项目目标
- 开发安全优先的CLI清理工具
- 智能识别AI开发工具中间文件
- 多层安全防护机制
- 支持备份和恢复功能

## 2. 技术栈选择

### 2.1 选择理由
- **Python 3.11+**: AI工程师生态匹配，丰富的文件处理库
- **Click框架**: CLI开发简单强大，参数解析完善
- **psutil**: 进程和磁盘信息获取
- **send2trash**: 安全删除（先到回收站）

### 2.2 核心依赖
```python
dependencies = [
    "click>=8.0.0",
    "psutil>=5.9.0",
    "send2trash>=1.8.0",
    "rich>=13.0.0",
    "humanize>=4.6.0",
    "python-dateutil>=2.8.0",
]
```

## 3. 安全架构设计

### 3.1 五层防护体系
```
扫描发现 → 智能分析 → 风险评估 → 用户确认 → 安全执行 → 恢复保障
```

### 3.2 安全机制
1. **智能分析防护**: 12维度文件安全评估
2. **模拟执行防护**: 强制dry-run预览
3. **分级确认防护**: SAFE/WARNING/DANGEROUS三级
4. **自动备份防护**: 删除前自动备份到`~/.aiclean/backup/`
5. **恢复撤销防护**: 一键恢复所有删除文件

### 3.3 绝对禁止清理的文件
```python
SYSTEM_CRITICAL_FILES = [
    r'C:\\Windows\\System32\\',
    r'C:\\Users\\[^\\]+\\Documents\\',
    r'C:\\Users\\[^\\]+\\Desktop\\',
    r'\.exe$', r'\.dll$', r'\.sys$',
    r'\.config$', r'\.json$', r'\.yaml$',
]
```

## 4. 核心功能设计

### 4.1 CLI命令设计
```bash
# 安全扫描
aiclean scan                    # 安全扫描
aiclean scan --detailed         # 详细报告

# 安全清理
aiclean clean                   # 安全清理（强制dry-run）
aiclean clean --confirm-all     # 批量确认
aiclean clean --safe-only       # 只清理安全级文件

# 恢复和撤销
aiclean undo                    # 撤销上次清理
aiclean restore --list          # 列出可恢复文件
aiclean backup --info           # 查看备份信息

# 安全配置
aiclean exclude add <path>      # 添加排除路径
aiclean whitelist add <pattern> # 添加白名单规则
```

### 4.2 清理目标优先级
1. **Cursor缓存** (3.4GB, 最紧急)
2. **Claude Code缓存** (94.7MB)
3. **Windows临时文件** (%TEMP%, C:\Windows\Temp)
4. **浏览器缓存** (Chrome/Edge)
5. **AI模型缓存** (HuggingFace, PyTorch)

### 4.3 具体工具清理规则

#### Cursor安全规则
```python
CURSOR_SAFE_TO_DELETE = [
    "~/.cursor/cache/",              # 缓存目录
    "~/.cursor/logs/old_*.log",      # 旧日志
    "~/.cursor/CachedData/",         # 缓存数据
]

CURSOR_KEEP = [
    "~/.cursor/User/settings.json",  # 用户设置
    "~/.cursor/User/keybindings.json", # 快捷键
    "~/.cursor/User/snippets/",      # 代码片段
]
```

#### Claude Code安全规则
```python
CLAUDECODE_SAFE_TO_DELETE = [
    "~/.claude/cache/",              # 缓存目录
    "~/.claude/logs/",               # 日志文件
    "~/.claude/temp/",               # 临时文件
]

CLAUDECODE_KEEP = [
    "~/.claude/config.json",         # 配置文件
    "~/.claude/projects/",           # 项目目录
    "~/.claude/memory/",             # 记忆文件
]
```

## 5. 智能分析系统

### 5.1 12维度安全分析
```python
SAFETY_DIMENSIONS = [
    "file_extension",      # 文件扩展名风险
    "file_location",       # 文件位置风险
    "process_lock",        # 进程锁定状态
    "last_access_time",    # 最后访问时间
    "file_size",           # 文件大小
    "file_permissions",    # 文件权限
    "system_dependency",   # 系统依赖关系
    "user_importance",     # 用户重要性评估
    "backup_existence",    # 备份存在性
    "recent_modification", # 最近修改时间
    "known_pattern",       # 已知模式匹配
    "user_feedback",       # 用户历史反馈
]
```

### 5.2 安全评分系统
```python
class SafetyScorer:
    """文件安全评分系统"""

    def score_file_safety(self, file_path: Path) -> SafetyScore:
        score = 100  # 初始100分

        # 扣分项（高风险）
        if self._is_system_file(file_path):
            score -= 50  # 系统文件高风险

        if self._is_locked(file_path):
            score -= 40  # 进程锁定中

        # 加分项（较安全）
        if self._is_temp_file(file_path):
            score += 30  # 临时文件较安全

        if self._old_and_large(file_path):
            score += 20  # 老旧大文件较安全

        return self._score_to_level(score)
```

## 6. 备份和恢复系统

### 6.1 备份策略
- **所有删除操作前强制备份**
- 备份保留30天（可配置）
- 自动压缩节省空间
- 备份元数据记录（路径、时间、大小、校验和）

### 6.2 恢复机制
```bash
# 恢复操作示例
aiclean restore --list          # 列出所有备份
aiclean restore <backup_id>     # 恢复特定备份
aiclean restore --all --dry-run # 模拟恢复所有
aiclean backup purge            # 清理过期备份
```

## 7. 项目架构

### 7.1 目录结构
```
aiclean-cli/
├── src/
│   ├── scanners/                 # 文件扫描器
│   │   ├── ai_scanners/          # AI开发扫描器
│   │   │   ├── claudecode_scanner.py
│   │   │   ├── cursor_scanner.py
│   │   │   └── huggingface_scanner.py
│   │   └── windows_scanners/     # Windows扫描器
│   ├── analyzers/                # 智能分析模块
│   │   ├── rule_based_analyzer.py
│   │   ├── decision_maker.py
│   │   └── risk_assessor.py
│   ├── cleaners/                 # 清理策略
│   │   ├── safe_delete.py
│   │   ├── backup_manager.py
│   │   └── report_generator.py
│   ├── cli.py                    # CLI入口
│   ├── config.py                 # 配置管理
│   └── const.py                  # 常量定义
├── tests/                        # 测试目录
├── pyproject.toml               # 项目配置
└── README.md                    # 项目说明
```

## 8. 开发计划

### Phase 1: 安全核心框架 (3-4天)
- 安全扫描引擎
- 危险文件识别
- 备份恢复系统
- 基础CLI框架

### Phase 2: 智能分析安全增强 (2-3天)
- 12维度安全分析
- 三级确认机制
- 安全评分系统
- 进程锁定检测

### Phase 3: 具体工具安全规则 (2-3天)
- ClaudeCode安全清理规则
- Cursor安全清理规则
- ClashVerge安全规则
- CCSwitch安全规则

### Phase 4: Windows系统安全处理 (2-3天)
- 系统文件保护
- 权限安全处理
- 管理员权限提示
- 系统恢复点创建

### Phase 5: 用户体验优化 (1-2天)
- 友好交互界面
- 详细报告生成
- 性能优化
- 最终测试

## 9. 风险控制

### 9.1 绝对安全承诺
1. **系统核心文件**: 绝对不删除
2. **用户重要数据**: 绝对不删除
3. **进程锁定文件**: 绝对不删除
4. **配置文件**: 绝对不删除
5. **白名单文件**: 绝对不删除

### 9.2 清理前强制措施
1. **预览模式**: 所有清理先dry-run
2. **用户确认**: 高危文件逐项确认
3. **自动备份**: 所有删除前备份
4. **恢复测试**: 备份文件可恢复验证

## 10. 成功标准

### 技术指标
- **误删率**: < 0.1% (重要文件)
- **空间回收率**: 70-90% (临时文件)
- **分析准确率**: > 95% (文件用途识别)
- **恢复成功率**: 100% (备份文件)

### 用户体验
- **操作透明**: 清理过程清晰可见
- **控制感强**: 用户完全控制清理决策
- **恢复便捷**: 一键恢复所有删除
- **性能良好**: 扫描快速，清理高效

## 11. 扩展规划

### 短期扩展
1. 更多AI工具支持 (VSCode, PyCharm等)
2. 云端备份支持
3. 定期自动清理

### 长期愿景
1. 机器学习优化清理策略
2. 跨平台支持 (macOS, Linux)
3. 企业级部署和管理

---

**设计批准**: 2026-03-20
**设计者**: Claude Code
**用户确认**: 已批准完整安全优先方案