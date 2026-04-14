package com.example.karaoke;

import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.MediaRecorder;
import android.os.Handler;
import android.os.Looper;

/**
 * 示例：录音 + JNI 调 C 侧打分。
 * nativeFeedFrame() 会根据 positionMs 自动推进歌词窗口，并把 segment/line
 * 结果打印到 Logcat。上线前请把 positionMs 换成真实播放器 getCurrentPosition()。
 */
public final class ScoreBridge {

    /** 与 lrctxt_parse.h 中 LRC_PARSE_* 一致，便于 Java 侧分支 */
    public static final int LRC_PARSE_OK = 0;
    public static final int LRC_PARSE_ERR_ALLOC = -1;
    public static final int LRC_PARSE_ERR_ENCODING = -2;
    public static final int LRC_PARSE_ERR_FORMAT = -3;

    static {
        System.loadLibrary("native-score");
    }

    public static native int nativeParseLyrics(String lrctxtUtf8);
    public static native void nativeScoreInit(int sampleRate, int hopMs);
    public static native void nativeCalFeed(short[] pcmOneHop);
    public static native void nativeCalDone();
    public static native void nativeLineBegin();
    public static native void nativeSegBegin();
    public static native void nativeFeedFrame(short[] pcmOneHop, long positionMs);
    public static native int[] nativeSegEnd();
    public static native int[] nativeLineEnd();
    public static native void nativeRelease();

    private static final int SAMPLE_RATE = 16000;
    private static final int HOP_MS = 20;
    private static final int HOP_SAMPLES = SAMPLE_RATE * HOP_MS / 1000;

    private AudioRecord record;
    private Thread ioThread;
    private volatile boolean running;

    /** 仅演示：用 Handler 每 20ms 推进的“假伴奏时间” */
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private volatile long fakePositionMs;

    public void startDemo(String lrctxt) {
        int pr = nativeParseLyrics(lrctxt);
        if (pr == LRC_PARSE_ERR_ENCODING)
            throw new IllegalArgumentException(
                    "歌词编码错误：lrctxt 须为 UTF-8（检测到非法 UTF-8，常见为 GBK 未转码）");
        if (pr == LRC_PARSE_ERR_FORMAT)
            throw new IllegalArgumentException(
                    "歌词格式错误：时间戳或 <dur,sp> 非法，或数值超出解析范围");
        if (pr != LRC_PARSE_OK)
            throw new IllegalStateException("parse lyrics failed: " + pr);
        nativeScoreInit(SAMPLE_RATE, HOP_MS);

        int minBuf = AudioRecord.getMinBufferSize(
                SAMPLE_RATE,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT);
        if (minBuf <= 0) throw new IllegalStateException("min buffer");

        record = new AudioRecord(
                MediaRecorder.AudioSource.MIC,
                SAMPLE_RATE,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT,
                Math.max(minBuf, HOP_SAMPLES * 4));

        record.startRecording();
        running = true;

        /* 校准：读几帧安静环境（示例简化：直接读麦） */
        short[] cal = new short[HOP_SAMPLES];
        for (int i = 0; i < 15; i++) {
            int r = record.read(cal, 0, cal.length);
            if (r == cal.length) nativeCalFeed(cal);
        }
        nativeCalDone();

        fakePositionMs = 0;
        mainHandler.postDelayed(tickPosition, HOP_MS);

        ioThread = new Thread(this::readLoop, "score-audio");
        ioThread.start();
    }

    private final Runnable tickPosition = new Runnable() {
        @Override public void run() {
            if (!running) return;
            fakePositionMs += HOP_MS;
            mainHandler.postDelayed(this, HOP_MS);
        }
    };

    private void readLoop() {
        short[] buf = new short[HOP_SAMPLES];
        while (running) {
            int n = record.read(buf, 0, buf.length);
            if (n != buf.length) continue;
            /* JNI 会根据 fakePositionMs（或 ExoPlayer 时间）自动推进 token/line */
            nativeFeedFrame(buf, fakePositionMs);
        }
    }

    public void stop() {
        running = false;
        mainHandler.removeCallbacks(tickPosition);
        if (ioThread != null) {
            try { ioThread.join(2000); } catch (InterruptedException ignored) {}
        }
        if (record != null) {
            try { record.stop(); } catch (Throwable ignored) {}
            record.release();
            record = null;
        }
        nativeRelease();
    }
}
