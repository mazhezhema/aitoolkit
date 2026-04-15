/*
 * score_core.h — Entertainment karaoke scoring engine
 *
 * Pure C99, integer-only, no third-party dependencies.
 * Works on Android NDK / Linux / RTOS.
 *
 * Version — bump on every interface / behaviour change.
 */
#define SCORE_VERSION_MAJOR  1
#define SCORE_VERSION_MINOR  0
#define SCORE_VERSION_PATCH  0

/*
 * Two-level output:
 *   - Per segment (<dur,sp> token):  1 score  + combo
 *   - Per line   ([mm:ss.mmm]):      4 scores + total + combo
 *
 * Usage flow（完整顺序见同目录 PLATFORM_CALLING.md §1.3）:
 *   score_init()
 *   score_cal_feed() × N   // ~300 ms of silence
 *   score_cal_done()       // 或改用 score_set_thr() —— 二选一，见下
 *   for each line:
 *     score_line_begin()
 *     for each token in line:
 *       score_seg_begin()
 *       while (audio frames within token window):
 *         score_feed(ctx, pcm_frame)
 *       result = score_seg_end()   // → segment score + combo
 *     line_result = score_line_end()  // → 4-dim + total
 *
 * 硬性约定：在第一次 score_feed() 打分之前，必须完成其一，否则 thr_e 仍为 0，
 * 几乎所有非静音帧都会被当成「有声」，分数失真：
 *   · 安静环境 score_cal_feed() 若干帧后调用 score_cal_done()，或
 *   · 直接 score_set_thr() 设定能量阈值。
 */
#ifndef SCORE_CORE_H
#define SCORE_CORE_H

#include <stdint.h>

/* ── Result types ────────────────────────────────────────────────── */

typedef struct {
    int32_t score;        /* 68–95  */
    int32_t combo;        /* current streak */
    int32_t max_combo;    /* session best   */
} ScoreSegResult;

typedef struct {
    int32_t technique;    /* 技巧 70–95 */
    int32_t emotion;      /* 感情 70–95 */
    int32_t vibe;         /* 气场 70–95 */
    int32_t rhythm;       /* 节奏 70–95 */
    int32_t total;        /* 总分 72–96 */
    int32_t combo;
    int32_t max_combo;
} ScoreLineResult;

/* ── Internal accumulator (exposed for static alloc on RTOS) ───── */

typedef struct {
    int32_t cnt;          /* frames fed          */
    int32_t voiced;       /* frames above thr    */
    int64_t sum_e;        /* sum of frame energy */
    int32_t max_e;        /* peak energy         */
    int32_t min_e;        /* valley energy       */
    int32_t onset_max;    /* max onset in early window */
} ScoreAccum;

/* ── Context (one per session) ───────────────────────────────────── */

typedef struct {
    /* config */
    int32_t sample_rate;
    int32_t hop_samples;     /* PCM samples per frame         */
    int32_t early_frames;    /* frames counted as "early" for onset */

    /* thresholds */
    int32_t thr_e;           /* voiced threshold (mean-sq energy)   */
    int32_t onset_thr;       /* onset magnitude threshold           */
    int32_t combo_thr;       /* segment score >= this → combo +1    */

    /* running state */
    int32_t prev_e;          /* previous frame energy               */
    int32_t seg_frames;      /* frames since seg_begin              */
    int32_t line_frames;     /* frames since line_begin             */

    /* accumulators */
    ScoreAccum seg;
    ScoreAccum line;

    /* active guards — set by begin, cleared by end */
    int32_t seg_active;
    int32_t line_active;

    /* combo */
    int32_t combo;
    int32_t max_combo;

    /* calibration scratch */
    int32_t cal_cnt;
    int64_t cal_sum;
    int32_t cal_done;
} ScoreCtx;

/* ── API ─────────────────────────────────────────────────────────── */

/* Initialize context. hop_ms: frame step (e.g. 20). 不设置 thr_e。 */
void score_init(ScoreCtx *ctx, int32_t sample_rate, int32_t hop_ms);

/*
 * 校准：每帧长度须为 hop_samples；建议在安静环境喂 ~300ms 再 score_cal_done。
 * 与 score_set_thr 二选一完成「首帧打分前」的阈值建立。
 */
void score_cal_feed(ScoreCtx *ctx, const int16_t *samples);

/* 根据 cal_feed 累计噪声估计 thr_e / onset_thr；未喂过帧时用安全默认。 */
void score_cal_done(ScoreCtx *ctx);

/* 跳过校准、直接设 voiced 能量阈 thr_e（onset_thr 随之推导）。 */
void score_set_thr(ScoreCtx *ctx, int32_t thr_e);

/* Begin new segment / line (resets accumulator).                    */
void score_seg_begin(ScoreCtx *ctx);
void score_line_begin(ScoreCtx *ctx);

/* Feed one audio frame.  mono PCM int16, len = hop_samples.        */
void score_feed(ScoreCtx *ctx, const int16_t *samples);

/* End segment / line — compute and return scores.                  */
ScoreSegResult  score_seg_end(ScoreCtx *ctx);
ScoreLineResult score_line_end(ScoreCtx *ctx);

#endif /* SCORE_CORE_H */
