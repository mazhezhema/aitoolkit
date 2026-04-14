# 三平台调用说明（Android / Linux 嵌入式 F133 / RTOS）

本文说明如何把 `lrctxt_parse` + `score_core` 接到 **麦克风 PCM** 与 **lrctxt 歌词** 上。两路输入、两级输出与 `score_core.h` 头文件注释一致。

---

## 一、三平台共性约定

### 1.1 输入

| 输入 | 说明 |
|------|------|
| **歌词** | 整段 lrctxt 文本（**须为合法 UTF-8** + `'\0'` 结尾），调用 `lrc_parse()` → `LrcData`；非法 UTF-8（常见为 GBK）返回 `LRC_PARSE_ERR_ENCODING`（`-2`），时间戳 / token 非法或数值过大返回 `LRC_PARSE_ERR_FORMAT`（`-3`） |
| **JNI 注意** | `GetStringUTFChars` 为 **Modified UTF-8**：内嵌 `U+0000` 会变成字节 `C0 80`，按 RFC 3629 属于非法 UTF-8，会被本解析器判为 **编码错误**。歌词文本勿含内嵌 NUL；或改为从 Java 传 `byte[]`（标准 UTF-8）再 `'\0'` 结尾后调用 C。 |
| **音频** | 单声道 **s16le** PCM；采样率与 `score_init(ctx, sample_rate, hop_ms)` 一致，常用 **16000** 或 **44100** |
| **帧长** | `hop_samples = sample_rate * hop_ms / 1000`；`hop_ms` 建议 **20**，即每帧 `hop_samples` 个 `int16_t` |

### 1.2 输出

- 每个 `<dur,sp>` 窗口结束时：`score_seg_end()` → `ScoreSegResult`（单分 + combo）
- 每行（`LrcLine`）结束时：`score_line_end()` → `ScoreLineResult`（四维 + 总分 + combo）

### 1.3 推荐调用顺序（三平台相同）

1. `lrc_parse(text, &lrc)`：`LRC_PARSE_OK`（`0`）成功；`LRC_PARSE_ERR_ALLOC`（`-1`）堆不足；`LRC_PARSE_ERR_ENCODING`（`-2`）非 UTF-8（曲库中少量 GBK 应先转 UTF-8 再喂入）；`LRC_PARSE_ERR_FORMAT`（`-3`）表示时间戳 / `<dur,sp>` 语法错误或数值超范围
2. `score_init(&ctx, sample_rate, hop_ms)`
3. **硬性约定（首帧 `score_feed` 之前必须完成）**：在安静环境连续调用 `score_cal_feed()`（每帧 `hop_samples` 个 s16）若干次（建议 ≥300ms 等效帧数），再调用 **`score_cal_done()`**；**或** 若已知环境噪声水平，直接调用 **`score_set_thr(thr_e)`**。二者至少其一；若都跳过，则 **`thr_e` 仍为 0**，几乎所有非零能量帧都会被判为「有声」，分数严重失真。
4. 按 `LrcLine` / `LrcToken` 时间轴：
   - `score_line_begin(&ctx)`
   - 对每个 token：`score_seg_begin` → 在 `[start_ms, end_ms)` 内按 20ms 步进 `score_feed` → `score_seg_end`
   - `score_line_end(&ctx)`
5. `lrc_free(&lrc)`

**对齐音频与歌词**：用播放器的 **当前播放时间**（毫秒，与 lrctxt 同一时间轴）决定当前应处于哪个 `LrcToken`，只把该 token 时间窗内的 PCM 喂给 `score_feed`。不要整曲无差别喂满，否则分数无意义。

**Android（与示例 `ScoreBridge` 对齐）**：一曲内建议顺序为 **`nativeParseLyrics` → `nativeScoreInit` → 若干 `nativeCalFeed` → `nativeCalDone` → 再 `nativeFeedFrame`**；不要在未 `nativeCalDone` 前依赖打分语义。

---

## 二、Android（NDK + JNI）

### 2.1 音频输入

- Java/Kotlin：`AudioRecord`  
  - `AudioFormat.ENCODING_PCM_16BIT`  
  - `AudioFormat.CHANNEL_IN_MONO`  
  - `sampleRate` 与 C 侧 `score_init` 一致（如 16000）
- 缓冲区：`minBufferSize` 可能大于一帧；在 native 侧 **按 `hop_samples` 切分** 再调 `score_cal_feed` / `score_feed`

### 2.2 编译与链接

**方式 A：CMake（推荐）**

在 `app/src/main/cpp/CMakeLists.txt` 中：

```cmake
add_library(score STATIC
    lrctxt_parse.c
    score_core.c)
target_include_directories(score PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})

add_library(native-lib SHARED native-lib.cpp)
target_link_libraries(native-lib score log)
```

**方式 B：`ndk-build`**

`Android.mk` 中将 `lrctxt_parse.c`、`score_core.c` 加入 `LOCAL_SRC_FILES`，`LOCAL_STATIC_LIBRARIES` 或直接把 `.c` 编进一个 `.so`。

### 2.3 JNI 调用形态（要点）

- **谁在调 C**：单独 **音频线程** 读 `AudioRecord`，在持有「当前播放时间 ms」的前提下调用打分 API；避免在 UI 线程做 `score_feed` 循环。
- **播放时间**：从 `ExoPlayer` / `MediaPlayer` / 自研解码器取 **position**，与 `LrcToken.start_ms/end_ms` 比较，落在窗口内才 `score_feed`。
- **生命周期**：一曲开始 `score_init` + 校准；一曲结束可 `lrc_free`；下一曲重新 `lrc_parse`。
- **与 §1.3 对齐的 JNI 顺序**：`nativeParseLyrics` → `nativeScoreInit` → `nativeCalFeed`×N → **`nativeCalDone`** → `nativeFeedFrame`（及内部自动的 line/seg 收尾）。**`nativeCalDone` 之前不要指望 `thr_e` 已就绪。**

### 2.4 伪代码（Kotlin + JNI）

```kotlin
// 与 native 约定同一采样率、hop_ms = 20
external fun nativeScoreInit(sampleRate: Int)
external fun nativeOnPcmFrame(pcm: ShortArray, playPositionMs: Long)
external fun nativeScoreReset() // 切歌时
```

Native 内根据 `playPositionMs` 选择 token，凑满 `hop_samples` 即 `score_feed`。

---

## 三、Linux 嵌入式（如全志 F133 等，用户态 + ALSA）

### 3.1 音频输入

- 使用 **ALSA** `snd_pcm_open` / `snd_pcm_readi`（或 `arecord` 管道）读取 **MONO S16_LE**
- `pcm` 设备名因板卡而异，例如 `hw:0,0` 或 `default`
- 采样率固定为 16000 或 44100 时，在打开 PCM 时指定 `SND_PCM_FORMAT_S16_LE`、`SND_PCM_ACCESS_RW_INTERLEAVED`、单声道

### 3.2 编译

在板卡或交叉工具链上：

```bash
# 示例：宿主编译（板子上若有 gcc）
gcc -std=c99 -O2 -Wall -c lrctxt_parse.c score_core.c
ar rcs libscore.a lrctxt_parse.o score_core.o

# 链接到你的主程序
gcc your_app.c libscore.a -o your_app -lasound   # 若用 ALSA
```

交叉编译时把 `gcc` 换成 `arm-linux-gnueabihf-gcc` 等即可。

### 3.3 线程与时间

- **读音频线程**：阻塞 `snd_pcm_readi`，读到的 buffer 按 `hop_samples` 切片调用 `score_feed`
- **播放时间**：若伴奏由本机播放，需与 **同一时钟源** 的 position 同步（如与 `aplay`/`mpv` 进程间通信，或自研播放器内部时间轴）；原则是 **PCM 帧对应的时间戳** 与 lrctxt 对齐

### 3.4 无浮点环境

`score_core` 为整数实现；若工具链需 `-msoft-float`，按平台文档链接软浮点库（本库逻辑不依赖 `float`/`double`）。

---

## 四、RTOS（裸机 / 轻量 OS，无 Linux）

### 4.1 音频输入

- 典型路径：**I2S + DMA** 双缓冲中断，在 **DMA 半满/全满回调** 中得到一块 PCM
- 格式仍为 **单声道 s16**；若硬件为立体声，只取左声道或驱动层混成单声道后再喂引擎

### 4.2 内存：`malloc` 替代

`lrctxt_parse.h` 支持覆盖分配器：

```c
#define LRC_MALLOC(sz)  my_rtos_malloc(sz)
#define LRC_FREE(p)     my_rtos_free(p)
#include "lrctxt_parse.h"
```

在 `#include "lrctxt_parse.h"` **之前** 定义宏；`score_core` 不调用 `malloc`，`ScoreCtx` 由调用方 **静态或栈上** 分配。

### 4.3 栈与上下文

- `ScoreCtx` 建议 **全局静态** 或 **每会话一块静态内存**，避免大栈占用
- **不要在 ISR 里** 跑完整 `lrc_parse`（耗时长）；解析在 **上电/选歌** 时在任务里完成一次即可
- `score_feed` 可做在 **音频任务** 或 **低优先级从 ISR 投递的队列** 中，保证每帧 O(1)

### 4.4 校准

RTOS 上若无「绝对安静」，可：

- 用 `score_set_thr()` 写死经验阈值，或  
- 在用户按下「开始」后的前 N 帧调用 `score_cal_feed` / `score_cal_done`

### 4.5 编译

将 `lrctxt_parse.c`、`score_core.c` 加入工程，指定 `-std=c99`，链接标准 **无** 额外第三方库；若 RTOS 无 `stdlib`，需为 `lrctxt_parse` 提供 `malloc/free` 兼容实现或预解析歌词后在主机侧生成 **二进制时间轴**（需自研格式，当前仓库未提供该格式）。

---

## 五、快速自检清单

| 检查项 | Android | Linux F133 | RTOS |
|--------|---------|------------|------|
| PCM 与 `score_init` 采样率一致 | ✓ | ✓ | ✓ |
| 每帧 `score_feed` 长度 = `hop_samples` | ✓ | ✓ | ✓ |
| 歌词时间与播放 position 同一毫秒轴 | ✓ | ✓ | ✓ |
| 仅当前 token 时间窗内喂 PCM | ✓ | ✓ | ✓ |
| 切歌 `lrc_free` + 重新 `lrc_parse` / `score_init` | ✓ | ✓ | ✓ |

更细的 API 顺序见 `score_core.h` 顶部注释。
