# Android 示例（JNI + AudioRecord）

将本目录下 `NativeScore.cpp`、`ScoreBridge.java` 拷入 Android Studio 工程后：

1. **包名**：把 Java 里的 `com.example.karaoke` 改成你的包名，并同步修改 `NativeScore.cpp` 中的 `Java_com_example_karaoke_...` 函数名（JNI 命名规则：`Java_` + 包路径下划线 + 类名 + 方法名）。

2. **CMakeLists.txt**（`app/src/main/cpp/CMakeLists.txt`）：

```cmake
cmake_minimum_required(VERSION 3.10)
project(scorejni)

add_library(score STATIC
    ${CMAKE_SOURCE_DIR}/../../../../lrctxt_parse.c
    ${CMAKE_SOURCE_DIR}/../../../../score_core.c)
target_include_directories(score PUBLIC
    ${CMAKE_SOURCE_DIR}/../../../../)

add_library(native-score SHARED NativeScore.cpp)
target_link_libraries(native-score score log android)
```

路径请按你放置 `lrctxt_parse.c` 的实际位置调整（也可把两个 `.c` 复制到 `cpp/` 同目录）。

3. **加载**：在 `Application` 或 `Activity` 里 `System.loadLibrary("native-score");`

4. **真实对齐**：示例里用定时器每 20ms 推进 `positionMs` 模拟伴奏时间轴。上线时请改为 `ExoPlayer.getCurrentPosition()` 或你们播放器提供的毫秒时间。`nativeFeedFrame()` 会根据该时间自动推进 token/line，并把结果打印到 Logcat。

5. **编码**：`nativeParseLyrics` 与 C 侧 `lrc_parse` 一致：歌词字符串须为 **合法 UTF-8**。非法字节序列返回 `LRC_PARSE_ERR_ENCODING`（`-2`），示例里会抛出 `IllegalArgumentException`；`-1` 表示分配失败或 JNI 取字符失败。
