# score SDK — API 使用文档

> 版本：`SCORE_VERSION 1.0.0` / `LRC_VERSION 1.0.0`  
> 语言：C99 | 算术：纯整数 | 依赖：无（lrctxt_parse 需要 malloc，可替换）

---

## 目录

1. [概述](#1-概述)
2. [编译与集成](#2-编译与集成)
3. [歌词解析模块 lrctxt_parse](#3-歌词解析模块-lrctxt_parse)
4. [打分引擎模块 score_core](#4-打分引擎模块-score_core)
5. [完整调用流程](#5-完整调用流程)
6. [分数说明](#6-分数说明)
7. [异常处理一览](#7-异常处理一览)
8. [线程安全与生命周期](#8-线程安全与生命周期)
9. [常见集成错误](#9-常见集成错误)
10. [平台特殊注意](#10-平台特殊注意)
11. [附录：数据结构速查](#11-附录数据结构速查)

---

## 1. 概述

score SDK 为播放器 player 提供卡拉OK实时打分能力，分为两个独立模块：

| 模块 | 头文件 | 职责 |
|------|--------|------|
| **lrctxt_parse** | `lrctxt_parse.h` | 将 KRC 格式歌词文本解析为时间轴结构体 |
| **score_core** | `score_core.h` | 接收 PCM 音频帧，按歌词时间轴实时打分 |

两个模块可独立使用，也可组合使用。

---

## 2. 编译与集成

### 2.1 源文件

只需 4 个文件：

```
lrctxt_parse.h
lrctxt_parse.c
score_core.h
score_core.c
```

### 2.2 编译要求

- C99 标准（`-std=c99`）
- 无第三方库依赖
- 无浮点运算（`-msoft-float` 安全）

### 2.3 典型编译

```bash
# 静态库
gcc -std=c99 -O2 -Wall -c lrctxt_parse.c score_core.c
ar rcs libscore.a lrctxt_parse.o score_core.o

# 交叉编译
CC=arm-linux-gnueabihf-gcc make lib
```

### 2.4 Android CMake

```cmake
add_library(score STATIC lrctxt_parse.c score_core.c)
target_include_directories(score PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(your-native-lib score)
```

### 2.5 RTOS 堆替换

在 `#include "lrctxt_parse.h"` **之前**定义：

```c
#define LRC_MALLOC(sz)  my_rtos_malloc(sz)
#define LRC_FREE(p)     my_rtos_free(p)
#include "lrctxt_parse.h"
```

`score_core` 不调用任何堆函数，`ScoreCtx` 由调用方分配（栈上或静态全局）。

---

## 3. 歌词解析模块 lrctxt_parse

### 3.1 输入

| 参数 | 类型 | 要求 |
|------|------|------|
| `text` | `const char *` | KRC 格式歌词，`'\0'` 结尾，**必须为合法 UTF-8** |
| `out` | `LrcData *` | 输出结构体指针，**必须非 NULL** |

**歌词格式示例**：

```
[00:12.500]你好世界<800,0><600,0><500,0><700,0>
[00:15.100]再见明天<900,0><400,0><600,0><800,0>
```

- `[mm:ss.mmm]` — 行起始时间戳（毫秒精度）
- `<dur,sp>` — 逐字 token，dur 为持续时长（毫秒），sp 为间距（当前忽略）
- 允许 token 与文字在同一行或下一行
- 同一时间戳的连续行会被合并

### 3.2 输出

```c
typedef struct {
    LrcLine  *lines;      // 行数组（堆分配）
    int32_t   n_lines;    // 行数
    LrcToken *tokens;     // token 数组（堆分配）
    int32_t   n_tokens;   // token 总数
} LrcData;
```

每个 `LrcLine`：

| 字段 | 说明 |
|------|------|
| `start_ms` | 行起始时间（毫秒） |
| `end_ms` | 行结束时间 = 最后一个 token 的 end_ms |
| `token_off` | 该行第一个 token 在 `LrcData.tokens[]` 中的索引 |
| `token_cnt` | 该行 token 数量 |

每个 `LrcToken`：

| 字段 | 说明 |
|------|------|
| `start_ms` | token 起始时间（绝对毫秒） |
| `end_ms` | token 结束时间（绝对毫秒） |

**注意**：解析后仅保留有 token 的行（纯文字无 token 的行会被过滤）。

### 3.3 返回码

| 返回码 | 宏名 | 值 | 含义 | player 应对 |
|--------|------|-----|------|-------------|
| 成功 | `LRC_PARSE_OK` | `0` | 解析成功 | 正常使用 `out` |
| 分配失败 | `LRC_PARSE_ERR_ALLOC` | `-1` | malloc 失败，内存不足 | 提示系统资源不足 |
| 编码错误 | `LRC_PARSE_ERR_ENCODING` | `-2` | 非法 UTF-8（常见：GBK 歌词未转码） | 提示「歌词编码错误」或在上层先转 UTF-8 |
| 格式错误 | `LRC_PARSE_ERR_FORMAT` | `-3` | 时间戳/token 语法非法或数值溢出 | 提示「歌词格式错误」或跳过该曲 |

### 3.4 释放

```c
lrc_free(&lrc);   // 释放 lines 和 tokens，置零
```

`lrc_free(NULL)` 安全，不会 crash。

### 3.5 API 用法

```c
LrcData lrc;
memset(&lrc, 0, sizeof(lrc));

int ret = lrc_parse(text, &lrc);
if (ret != LRC_PARSE_OK) {
    // 处理错误，见返回码表
    return;
}

// 使用 lrc.lines[0..n_lines-1] 和 lrc.tokens[0..n_tokens-1]

lrc_free(&lrc);  // 用完必须释放
```

---

## 4. 打分引擎模块 score_core

### 4.1 初始化

```c
void score_init(ScoreCtx *ctx, int32_t sample_rate, int32_t hop_ms);
```

| 参数 | 说明 | 典型值 | 容错 |
|------|------|--------|------|
| `ctx` | 上下文指针 | — | NULL 时静默返回 |
| `sample_rate` | PCM 采样率 (Hz) | `16000` 或 `44100` | ≤0 自动用 16000 |
| `hop_ms` | 帧步长 (毫秒) | `20` | ≤0 自动用 20 |

**初始化后计算的关键值**：

| 字段 | 公式 | 范围 |
|------|------|------|
| `ctx->hop_samples` | `sample_rate × hop_ms / 1000` | 1 ~ 9600 (自动 clamp) |
| `ctx->early_frames` | `200 / hop_ms` | ≥1 |
| `ctx->combo_thr` | 固定 `82` | — |

### 4.2 校准（二选一）

打分前**必须**完成校准，否则 `thr_e = 0` 导致分数失真。两种方式二选一：

#### 方式 A：环境噪声校准（推荐）

```c
// 安静环境下连续喂 ~300ms 的麦克风 PCM
for (int i = 0; i < 15; i++) {           // 15 帧 × 20ms = 300ms
    read_mic(frame, ctx.hop_samples);
    score_cal_feed(&ctx, frame);
}
score_cal_done(&ctx);
```

| 函数 | 输入 | 说明 |
|------|------|------|
| `score_cal_feed(ctx, samples)` | 一帧 PCM（长度 = `hop_samples`） | 累计噪声能量 |
| `score_cal_done(ctx)` | 无 | 计算阈值：`thr_e = noise×4+100`，未喂帧时 fallback `5000` |

#### 方式 B：直接设阈值

```c
score_set_thr(&ctx, 5000);   // 已知环境噪声水平时直接设
```

| 参数 | 说明 |
|------|------|
| `thr_e` | voiced 能量阈值，≤0 自动 clamp 到 1 |

### 4.3 打分循环

#### 开始一行

```c
score_line_begin(&ctx);
```

#### 开始一个 segment（逐字 token）

```c
score_seg_begin(&ctx);
```

#### 喂音频帧

```c
void score_feed(ScoreCtx *ctx, const int16_t *samples);
```

| 参数 | 要求 |
|------|------|
| `samples` | 单声道 int16 PCM 数组，长度**必须等于** `ctx->hop_samples` |

**调用时机**：仅在当前 token 的 `[start_ms, end_ms)` 时间窗口内，按 `hop_ms` 步进喂帧。不要在 token 窗口外喂帧——会污染分数。

**active 保护**：未调用 `score_seg_begin` / `score_line_begin` 时，`score_feed` 的帧不会被累计，不影响打分结果。

#### 结束一个 segment → 取分

```c
ScoreSegResult r = score_seg_end(&ctx);
```

输出 `ScoreSegResult`：

| 字段 | 类型 | 范围 | 说明 |
|------|------|------|------|
| `score` | `int32_t` | **68 ~ 95** | 该 token 的娱乐分 |
| `combo` | `int32_t` | ≥0 | 当前连击数 |
| `max_combo` | `int32_t` | ≥0 | 本曲最大连击数 |

#### 结束一行 → 取分

```c
ScoreLineResult r = score_line_end(&ctx);
```

输出 `ScoreLineResult`：

| 字段 | 类型 | 范围 | 说明 |
|------|------|------|------|
| `technique` | `int32_t` | **70 ~ 95** | 技巧（有声占比） |
| `emotion` | `int32_t` | **70 ~ 95** | 感情（动态范围） |
| `vibe` | `int32_t` | **70 ~ 95** | 气场（峰值强度） |
| `rhythm` | `int32_t` | **74 ~ 92** | 节奏（起音强度） |
| `total` | `int32_t` | **72 ~ 96** | 总分（加权平均） |
| `combo` | `int32_t` | ≥0 | 当前连击数 |
| `max_combo` | `int32_t` | ≥0 | 本曲最大连击数 |

### 4.4 切歌/释放

```c
lrc_free(&lrc);                        // 释放歌词
// 下一曲重新 lrc_parse + score_init
```

无需额外释放 `ScoreCtx`——它不持有堆内存。

---

## 5. 完整调用流程

```
┌─ 一曲开始 ────────────────────────────────────────────┐
│                                                        │
│  lrc_parse(text, &lrc)     ← 歌词解析（检查返回码）    │
│  score_init(&ctx, 16000, 20)                           │
│                                                        │
│  ┌─ 校准（二选一）────────────────────────────────┐    │
│  │  score_cal_feed(&ctx, quiet_frame) × 15        │    │
│  │  score_cal_done(&ctx)                          │    │
│  │  ─────── 或 ───────                            │    │
│  │  score_set_thr(&ctx, 5000)                     │    │
│  └────────────────────────────────────────────────┘    │
│                                                        │
│  for (i = 0; i < lrc.n_lines; i++):                   │
│    score_line_begin(&ctx)                              │
│                                                        │
│    for (j = 0; j < line.token_cnt; j++):               │
│      token = lrc.tokens[line.token_off + j]            │
│      score_seg_begin(&ctx)                             │
│                                                        │
│      while (播放时间 在 [token.start_ms, token.end_ms)):│
│        read_mic(frame, ctx.hop_samples)                │
│        score_feed(&ctx, frame)                         │
│                                                        │
│      seg_result = score_seg_end(&ctx)  ← 逐字分+combo  │
│                                                        │
│    line_result = score_line_end(&ctx)  ← 四维+总分      │
│                                                        │
│  lrc_free(&lrc)                                        │
│                                                        │
└────────────────────────────────────────────────────────┘
```

---

## 6. 分数说明

### 6.1 Segment 分（逐字）

```
base  = 68 + voiced_ratio% × 22 / 100     (68..90)
bonus = onset 超阈值 ? 5 : 0               (0..5)
e_bonus = avg_energy / threshold × 3       (0..3)
score = clamp(base + bonus + e_bonus, 68, 95)
```

### 6.2 Line 分（逐行）

| 维度 | 权重 | 主要依据 |
|------|------|----------|
| 技巧 technique | 30% | 有声帧占比 |
| 感情 emotion | 30% | 有声帧加权的动态范围（max-min vs avg） |
| 气场 vibe | 25% | 有声帧加权的峰值/均值比 |
| 节奏 rhythm | 15% | 起音(onset)最大值 vs 阈值 |

`total = technique×30 + emotion×30 + vibe×25 + rhythm×15) / 100`，clamp 到 72~96。

### 6.3 Combo

- segment score ≥ 82（`combo_thr`）→ combo + 1
- segment score < 82 → combo 归零
- `max_combo` 全曲最大连击，不会重置

### 6.4 设计意图

这是**娱乐打分**，不是专业音高评测。分数范围窄（68~96），保证：
- 安静/不唱 → 68~75（不会太低打击玩家）
- 正常唱 → 78~88
- 卖力唱 → 85~95
- 不可能 100 也不会 0

---

## 7. 异常处理一览

### 7.1 歌词解析异常

| 异常场景 | 返回码 | SDK 行为 | player 建议处理 |
|----------|--------|----------|----------------|
| `text` 为 NULL | `LRC_PARSE_OK` | `out` 输出为空（n_lines=0） | 视为无歌词，禁用打分 |
| `text` 为空字符串 `""` | `LRC_PARSE_OK` | 同上 | 同上 |
| `out` 为 NULL | `LRC_PARSE_ERR_FORMAT` | 立即返回 | player 代码 bug，修复 |
| 含非法 UTF-8 字节 | `LRC_PARSE_ERR_ENCODING` | 不分配内存，直接返回 | 提示编码错误或上层转 UTF-8 |
| 时间戳数值溢出（如 `[999999:00.000]`） | `LRC_PARSE_ERR_FORMAT` | 不分配内存，直接返回 | 提示歌词格式错误 |
| token dur 溢出（如 `<9999999999,0>`） | `LRC_PARSE_ERR_FORMAT` | 同上 | 同上 |
| token 时间累加溢出 | `LRC_PARSE_ERR_FORMAT` | 释放已分配内存后返回 | 同上 |
| malloc 失败 | `LRC_PARSE_ERR_ALLOC` | 释放已分配部分后返回 | 提示内存不足 |
| 歌词无任何合法行/token | `LRC_PARSE_OK` | `out` 输出为空（n_lines=0） | 视为无歌词 |
| 正文含 `[` `<` 等普通字符 | `LRC_PARSE_OK` | 正常解析，不误报 | 无需处理 |
| 多次 `lrc_free` 同一个 `LrcData` | 安全 | 第二次 free 为 no-op | 无需处理 |
| `lrc_free(NULL)` | 安全 | no-op | 无需处理 |

### 7.2 打分引擎异常

| 异常场景 | SDK 行为 | player 建议处理 |
|----------|----------|----------------|
| 任何 API 传入 `ctx = NULL` | 静默返回（end 函数返回全零） | player 代码 bug，修复 |
| `score_feed` 传入 `samples = NULL` | 静默跳过该帧 | 无需处理 |
| `sample_rate` ≤ 0 | 自动用 16000 | 传正确值 |
| `hop_ms` ≤ 0 | 自动用 20 | 传正确值 |
| `sample_rate × hop_ms` 极大 | `hop_samples` 自动 clamp 到 9600 | 传合理值 |
| 未校准就 `score_feed` | `thr_e = 0`，所有帧判为有声，**分数严重失真** | **必须先校准或 set_thr** |
| 未调 `seg_begin` 就调 `seg_end` | 返回全零 `{0,0,0}` | 检查调用顺序 |
| 未调 `line_begin` 就调 `line_end` | 返回全零 `{0,...}` | 检查调用顺序 |
| 未调 `seg_begin` 时 `score_feed` | 帧不累计到 seg（line 仍正常） | 正常情况：token 间隙 |
| 未调 `line_begin` 时 `score_feed` | 帧不累计到 line（seg 仍正常） | 检查调用顺序 |
| `score_set_thr(ctx, -100)` | 自动 clamp 到 1 | 传正值 |
| 一个 seg 内喂 0 帧就 end | `cnt=0` 按 1 算，返回基础分 68 | 正常：极短 token |
| 切歌不释放直接 `score_init` | 安全——memset 清零全部状态 | 但仍需 `lrc_free` 旧歌词 |

### 7.3 错误码速查表

```c
// lrctxt_parse.h
#define LRC_PARSE_OK            0    // 成功
#define LRC_PARSE_ERR_ALLOC    -1    // 内存分配失败
#define LRC_PARSE_ERR_ENCODING -2    // 非法 UTF-8（GBK 等）
#define LRC_PARSE_ERR_FORMAT   -3    // 时间戳/token 语法或数值非法
```

```c
// score_core — 无错误码，通过返回值结构体表达：
//   全零结构体 = 异常或未激活状态
```

---

## 8. 线程安全与生命周期

### 8.1 线程模型

SDK 本身**不创建任何线程/进程**。所有函数在调用者线程上同步执行。

### 8.2 线程安全

- **不同** `ScoreCtx` 实例可在不同线程并发使用（无共享状态）
- **同一** `ScoreCtx` 实例**不可**被多线程并发调用（无内部锁）
- `lrc_parse` 无全局状态，可并发调用（各自的 `LrcData` 独立）

### 8.3 典型 player 线程分工

```
主线程:  lrc_parse → score_init → 传 LrcData 给音频线程
音频线程: score_cal_feed/done → score_feed/seg_end/line_end 循环
主线程:  切歌时 → 通知音频线程停止 → lrc_free
```

### 8.4 生命周期

```
[lrc_parse] ──→ LrcData 有效 ──→ [lrc_free] ──→ LrcData 失效
[score_init] ──→ ScoreCtx 有效 ──→ [下次 score_init] 覆盖重置
```

- `LrcData` 的生命周期由 `lrc_parse` / `lrc_free` 管理
- `ScoreCtx` 无堆分配，重新 `score_init` 即可复用，无需释放

---

## 9. 常见集成错误

### 9.1 未校准就打分

```c
score_init(&ctx, 16000, 20);
// ❌ 忘了 score_cal_feed + score_cal_done
score_seg_begin(&ctx);
score_feed(&ctx, frame);   // thr_e=0，所有帧都是"有声"，分数≈90+
```

**修复**：在首次 `score_feed` 前必须完成 `score_cal_done()` 或 `score_set_thr()`。

### 9.2 整曲无差别喂帧

```c
// ❌ 不管当前在哪个 token，全部帧都 score_feed
while (has_audio) {
    score_feed(&ctx, frame);
}
```

**修复**：只在当前 token 的 `[start_ms, end_ms)` 内喂帧。参考 `demo_linux.c` 的时间轴驱动逻辑。

### 9.3 帧长度不匹配

```c
int16_t buf[1024];
record.read(buf, 1024);
score_feed(&ctx, buf);  // ❌ hop_samples=320，但传了 1024 个样本
```

**修复**：每次传给 `score_feed` 的数组长度**必须等于** `ctx.hop_samples`。大缓冲区需按 `hop_samples` 切片。

### 9.4 GBK 歌词直传

```c
// ❌ GBK 编码的歌词直接传入
lrc_parse(gbk_text, &lrc);  // → LRC_PARSE_ERR_ENCODING
```

**修复**：在上层（Java / Python / 服务端）先将 GBK 转为 UTF-8 再传入。

### 9.5 忘记 lrc_free 导致内存泄漏

```c
lrc_parse(text1, &lrc);
lrc_parse(text2, &lrc);  // ❌ text1 的 lines/tokens 泄漏
```

**修复**：重新解析前先 `lrc_free(&lrc)`。

### 9.6 JNI Modified UTF-8

Android 的 `GetStringUTFChars` 返回 Modified UTF-8：如果歌词含 `U+0000`（罕见），会编码为 `C0 80`，被 SDK 的 UTF-8 校验器拒绝。

**修复**：从 Java 传 `byte[]`（标准 UTF-8）而非 `String`；或确保歌词不含 NUL 字符。

---

## 10. 平台特殊注意

### 10.1 Android

| 项 | 说明 |
|----|------|
| 音频源 | `AudioRecord` + `ENCODING_PCM_16BIT` + `CHANNEL_IN_MONO` |
| 采样率 | 与 `score_init` 一致，推荐 16000 |
| 线程 | 在独立音频线程调用打分 API，不要在 UI 线程 |
| 播放时间 | 用 `ExoPlayer.getCurrentPosition()` 与 token 时间对齐 |
| JNI 示例 | `examples/android/NativeScore.cpp` + `ScoreBridge.java` |

### 10.2 Linux 嵌入式

| 项 | 说明 |
|----|------|
| 音频源 | ALSA `snd_pcm_readi`，`SND_PCM_FORMAT_S16_LE`，单声道 |
| 编译 | `gcc -std=c99` 或交叉工具链 |
| 无浮点 | 安全——SDK 不使用 `float`/`double` |

### 10.3 RTOS

| 项 | 说明 |
|----|------|
| 音频源 | I2S + DMA 双缓冲 |
| 堆 | 用 `LRC_MALLOC` / `LRC_FREE` 替换 |
| ScoreCtx | 全局静态分配，不要放栈上（约 200 字节） |
| 歌词解析 | 在上电/选歌任务中完成，**不要在 ISR 里** |
| 打分 | `score_feed` 可在音频任务中，O(1) 每帧 |
| 示例 | `examples/rtos_score_stub.c` |

---

## 11. 附录：数据结构速查

### LrcToken

```c
typedef struct {
    int32_t start_ms;    // token 起始（绝对毫秒）
    int32_t end_ms;      // token 结束（绝对毫秒）
} LrcToken;              // 8 bytes
```

### LrcLine

```c
typedef struct {
    int32_t start_ms;    // 行起始（绝对毫秒）
    int32_t end_ms;      // 行结束 = 最后 token 的 end_ms
    int32_t token_off;   // tokens[] 数组中的起始索引
    int32_t token_cnt;   // 本行 token 数量
} LrcLine;               // 16 bytes
```

### LrcData

```c
typedef struct {
    LrcLine  *lines;     // 堆分配，lrc_free 释放
    int32_t   n_lines;
    LrcToken *tokens;    // 堆分配，lrc_free 释放
    int32_t   n_tokens;
} LrcData;               // 24 bytes (64-bit) / 16 bytes (32-bit)
```

### ScoreSegResult

```c
typedef struct {
    int32_t score;       // 68–95
    int32_t combo;       // 当前连击
    int32_t max_combo;   // 全曲最大连击
} ScoreSegResult;        // 12 bytes
```

### ScoreLineResult

```c
typedef struct {
    int32_t technique;   // 技巧 70–95
    int32_t emotion;     // 感情 70–95
    int32_t vibe;        // 气场 70–95
    int32_t rhythm;      // 节奏 74–92
    int32_t total;       // 总分 72–96
    int32_t combo;       // 当前连击
    int32_t max_combo;   // 全曲最大连击
} ScoreLineResult;       // 28 bytes
```

### ScoreCtx

```c
typedef struct {
    int32_t sample_rate;
    int32_t hop_samples;     // 1 ~ 9600
    int32_t early_frames;    // ≥ 1
    int32_t thr_e;           // voiced 阈值（校准后 >0）
    int32_t onset_thr;       // onset 阈值
    int32_t combo_thr;       // 固定 82
    // ... 内部状态（约 200 bytes 总计）
} ScoreCtx;
```

`ScoreCtx` 由调用方分配（栈/静态/堆均可），无需特殊对齐。

---

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2026-04-14 | 初版：歌词解析 + 打分引擎 + 三平台支持 |
