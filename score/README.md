# score — 卡拉OK娱乐打分 SDK

纯 C99、纯整数算术、零第三方依赖。  
给播放器 player 内嵌，提供逐字（segment）+ 逐行（line）两级实时打分与 combo。

## 目录结构

```
score/
├── lrctxt_parse.h/c   歌词解析（KRC 格式 [mm:ss.mmm] + <dur,sp>）
├── score_core.h/c     打分引擎
├── Makefile           → libscore.a
├── PLATFORM_CALLING.md 三平台集成指南
└── examples/
    ├── demo_linux.c       Linux 可执行示例
    ├── rtos_score_stub.c  RTOS 封装示例
    ├── smoke_lrctxt.c     歌词解析冒烟测试
    ├── smoke_score_core.c 打分引擎冒烟测试
    ├── Makefile           示例 + 测试构建
    └── android/           JNI + Java 示例
```

## 快速编译

```bash
cd aitoolkit/score

# 产出 libscore.a
make

# 构建并运行冒烟测试
make -f examples/Makefile smoke        # lrctxt 解析
make -f examples/Makefile smoke-score  # 打分引擎

# 构建 Linux demo
make -f examples/Makefile
./examples/demo_linux path/to/song.lrctxt loud
```

交叉编译只需替换 `CC`：

```bash
CC=arm-linux-gnueabihf-gcc make
```

## 集成步骤

1. 将 `lrctxt_parse.h/c` + `score_core.h/c` 加入工程，指定 `-std=c99`
2. 按 `PLATFORM_CALLING.md` 的调用顺序接入：
   - `lrc_parse()` 解析歌词
   - `score_init()` → 校准 → 按时间轴 `score_feed()` → 收分
3. Android 参考 `examples/android/`；RTOS 参考 `examples/rtos_score_stub.c`

## 版本

头文件中定义了 `SCORE_VERSION_MAJOR/MINOR/PATCH` 和 `LRC_VERSION_MAJOR/MINOR/PATCH`，  
player 侧可在编译时或日志中打印版本用于问题排查。

## 文档

| 文档 | 内容 |
|------|------|
| **[API.md](API.md)** | **完整 API 使用手册**：输入/输出/异常/调用流程/分数说明/常见错误 |
| [PLATFORM_CALLING.md](PLATFORM_CALLING.md) | 三平台（Android/Linux/RTOS）集成细节 |
| [examples/README.md](examples/README.md) | 示例索引与构建说明 |

## RTOS 注意

- `score_core` 不调用 malloc，`ScoreCtx` 由调用方静态分配
- `lrctxt_parse` 默认用 `malloc/free`，可在 `#include` 前定义 `LRC_MALLOC` / `LRC_FREE` 替换
