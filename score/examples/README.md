# 示例索引

| 平台 | 文件 | 说明 |
|------|------|------|
| **Linux / macOS / WSL** | `demo_linux.c` + `Makefile` | 可执行程序：读 lrctxt + 合成 PCM，打印前 5 行打分 |
| **Android** | `android/NativeScore.cpp`、`android/ScoreBridge.java`、`android/README.md` | JNI + `AudioRecord` 骨架 |
| **RTOS** | `rtos_score_stub.c` | 仅 C 打分侧封装；`lrc_parse` 在别任务完成，堆用 `-DLRC_MALLOC` |

## Linux 一键编译运行

在目录 `aitoolkit/score` 下：

```bash
make demo
./examples/demo_linux /path/to/song.lrctxt loud
```

参数：`quiet` | `mid` | `loud` 控制合成音量（模拟小声/一般/大声）。

### 冒烟测试

在 `aitoolkit/score` 下：

```bash
make test          # 全部冒烟（lrctxt + score_core）
make smoke         # 仅 lrctxt UTF-8 + 解析
make smoke-score   # 仅 score_core 初始化/校准/打分/combo
```

均应打印 `ok` 并以退出码 0 结束；用于 CI 或改代码后的快速回归。

## Android

见 `android/README.md`：改包名、配 CMake、把 `lrctxt_parse.c` / `score_core.c` 编进 `native-score`。

## RTOS

编译 `lrctxt_parse.c` 时传入自定义分配器，与 `rtos_score_stub.c` + `score_core.c` 一同链接。歌词解析成功后按 `PLATFORM_CALLING.md` 的时间轴调用 `karaoke_rtos_*`。
