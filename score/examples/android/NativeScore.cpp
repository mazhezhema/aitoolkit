/*
 * Android JNI 示例：桥接 score_core + lrctxt_parse
 *
 * 1. 按包名修改 JNI 函数名（见 README.md）
 * 2. 与 CMake 一起编进 libnative-score.so
 */
#include <jni.h>
#include <android/log.h>
#include <string.h>
#include <stdlib.h>

extern "C" {
#include "lrctxt_parse.h"
#include "score_core.h"
}

#define LOG_TAG "KaraokeScore"
#define ALOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)

static LrcData g_lrc;
static ScoreCtx g_ctx;
static int g_inited = 0;
static int32_t g_hop_samples = 0;
static int32_t g_line_idx = 0;
static int32_t g_token_rel = 0;
static int32_t g_line_active = 0;
static int32_t g_seg_active = 0;
static int64_t g_last_pos_ms = -1;

static void reset_progress(void) {
    g_line_idx = 0;
    g_token_rel = 0;
    g_line_active = 0;
    g_seg_active = 0;
    g_last_pos_ms = -1;
}

static int has_current_line(void) {
    return g_line_idx >= 0 && g_line_idx < g_lrc.n_lines;
}

static LrcLine *current_line(void) {
    return has_current_line() ? &g_lrc.lines[g_line_idx] : NULL;
}

static LrcToken *current_token(void) {
    LrcLine *ln = current_line();
    if (!ln || g_token_rel < 0 || g_token_rel >= ln->token_cnt)
        return NULL;
    return &g_lrc.tokens[ln->token_off + g_token_rel];
}

static void close_current_segment(void) {
    if (!g_seg_active)
        return;
    ScoreSegResult r = score_seg_end(&g_ctx);
    LrcToken *tk = current_token();
    if (tk) {
        ALOGI("seg %d:%d [%d..%d] score=%d combo=%d max=%d",
              (int)g_line_idx, (int)g_token_rel,
              (int)tk->start_ms, (int)tk->end_ms,
              (int)r.score, (int)r.combo, (int)r.max_combo);
    } else {
        ALOGI("seg %d:%d score=%d combo=%d max=%d",
              (int)g_line_idx, (int)g_token_rel,
              (int)r.score, (int)r.combo, (int)r.max_combo);
    }
    g_seg_active = 0;
}

static void close_current_line(void) {
    if (!g_line_active)
        return;
    ScoreLineResult r = score_line_end(&g_ctx);
    LrcLine *ln = current_line();
    if (ln) {
        ALOGI("line %d [%d..%d] tech=%d emo=%d vibe=%d rhythm=%d total=%d combo=%d max=%d",
              (int)g_line_idx, (int)ln->start_ms, (int)ln->end_ms,
              (int)r.technique, (int)r.emotion, (int)r.vibe,
              (int)r.rhythm, (int)r.total, (int)r.combo, (int)r.max_combo);
    } else {
        ALOGI("line %d total=%d combo=%d max=%d",
              (int)g_line_idx, (int)r.total, (int)r.combo, (int)r.max_combo);
    }
    g_line_active = 0;
}

static void advance_finished_items(int64_t positionMs) {
    while (has_current_line()) {
        LrcLine *ln = current_line();
        if (g_token_rel >= ln->token_cnt) {
            close_current_line();
            g_line_idx++;
            g_token_rel = 0;
            continue;
        }

        LrcToken *tk = current_token();
        if (tk && positionMs >= tk->end_ms) {
            close_current_segment();
            g_token_rel++;
            continue;
        }
        break;
    }
}

static void ensure_active_items_started(int64_t positionMs) {
    while (has_current_line()) {
        LrcLine *ln = current_line();
        if (g_token_rel >= ln->token_cnt) {
            close_current_line();
            g_line_idx++;
            g_token_rel = 0;
            continue;
        }

        LrcToken *tk = current_token();
        if (!tk)
            return;

        if (!g_line_active && positionMs >= ln->start_ms) {
            score_line_begin(&g_ctx);
            g_line_active = 1;
        }
        if (!g_seg_active && positionMs >= tk->start_ms && positionMs < tk->end_ms) {
            score_seg_begin(&g_ctx);
            g_seg_active = 1;
        }
        return;
    }
}

extern "C" JNIEXPORT jint JNICALL
Java_com_example_karaoke_ScoreBridge_nativeParseLyrics(JNIEnv *env, jclass,
                                                       jstring jtext) {
    lrc_free(&g_lrc);
    memset(&g_lrc, 0, sizeof(g_lrc));

    const char *utf = env->GetStringUTFChars(jtext, NULL);
    if (!utf)
        return LRC_PARSE_ERR_ALLOC;
    int ret = lrc_parse(utf, &g_lrc);
    env->ReleaseStringUTFChars(jtext, utf);
    if (ret != LRC_PARSE_OK)
        return ret;
    reset_progress();
    ALOGI("lrc_parse ok: lines=%d tokens=%d", (int)g_lrc.n_lines, (int)g_lrc.n_tokens);
    return LRC_PARSE_OK;
}

extern "C" JNIEXPORT void JNICALL
Java_com_example_karaoke_ScoreBridge_nativeScoreInit(JNIEnv *, jclass,
                                                     jint sampleRate, jint hopMs) {
    score_init(&g_ctx, sampleRate, hopMs);
    g_hop_samples = g_ctx.hop_samples;
    reset_progress();
    g_inited = 1;
}

extern "C" JNIEXPORT void JNICALL
Java_com_example_karaoke_ScoreBridge_nativeCalFeed(JNIEnv *env, jclass,
                                                    jshortArray pcm) {
    if (!g_inited || g_hop_samples <= 0) return;
    jsize n = env->GetArrayLength(pcm);
    if (n < g_hop_samples) return;
    jshort *p = env->GetShortArrayElements(pcm, NULL);
    if (!p) return;
    score_cal_feed(&g_ctx, reinterpret_cast<const int16_t *>(p));
    env->ReleaseShortArrayElements(pcm, p, JNI_ABORT);
}

extern "C" JNIEXPORT void JNICALL
Java_com_example_karaoke_ScoreBridge_nativeCalDone(JNIEnv *, jclass) {
    score_cal_done(&g_ctx);
}

/* 喂一帧 PCM（长度须为 hop_samples）；positionMs 为当前伴奏时间，用于选 token */
extern "C" JNIEXPORT void JNICALL
Java_com_example_karaoke_ScoreBridge_nativeFeedFrame(JNIEnv *env, jclass,
                                                     jshortArray pcm,
                                                     jlong positionMs) {
    if (!g_inited || g_hop_samples <= 0 || g_lrc.n_lines <= 0) return;
    jsize n = env->GetArrayLength(pcm);
    if (n < g_hop_samples) return;
    jshort *p = env->GetShortArrayElements(pcm, NULL);
    if (!p) return;

    if (g_last_pos_ms >= 0 && positionMs < g_last_pos_ms) {
        ALOGI("seek detected: reset progress from %lld to %lld",
              (long long)g_last_pos_ms, (long long)positionMs);
        reset_progress();
    }
    g_last_pos_ms = positionMs;

    advance_finished_items(positionMs);
    ensure_active_items_started(positionMs);

    LrcToken *tk = current_token();
    if (g_seg_active && tk && positionMs >= tk->start_ms && positionMs < tk->end_ms) {
        score_feed(&g_ctx, reinterpret_cast<const int16_t *>(p));
    }

    env->ReleaseShortArrayElements(pcm, p, JNI_ABORT);
}

extern "C" JNIEXPORT void JNICALL
Java_com_example_karaoke_ScoreBridge_nativeSegBegin(JNIEnv *, jclass) {
    score_seg_begin(&g_ctx);
}

extern "C" JNIEXPORT void JNICALL
Java_com_example_karaoke_ScoreBridge_nativeLineBegin(JNIEnv *, jclass) {
    score_line_begin(&g_ctx);
}

extern "C" JNIEXPORT jintArray JNICALL
Java_com_example_karaoke_ScoreBridge_nativeSegEnd(JNIEnv *env, jclass) {
    ScoreSegResult r = score_seg_end(&g_ctx);
    jintArray out = env->NewIntArray(3);
    if (!out) return NULL;
    jint v[3] = { r.score, r.combo, r.max_combo };
    env->SetIntArrayRegion(out, 0, 3, v);
    return out;
}

extern "C" JNIEXPORT jintArray JNICALL
Java_com_example_karaoke_ScoreBridge_nativeLineEnd(JNIEnv *env, jclass) {
    ScoreLineResult r = score_line_end(&g_ctx);
    jintArray out = env->NewIntArray(7);
    if (!out) return NULL;
    jint v[7] = {
        r.technique, r.emotion, r.vibe, r.rhythm,
        r.total, r.combo, r.max_combo
    };
    env->SetIntArrayRegion(out, 0, 7, v);
    return out;
}

extern "C" JNIEXPORT void JNICALL
Java_com_example_karaoke_ScoreBridge_nativeRelease(JNIEnv *, jclass) {
    close_current_segment();
    close_current_line();
    lrc_free(&g_lrc);
    memset(&g_lrc, 0, sizeof(g_lrc));
    reset_progress();
    g_inited = 0;
}
