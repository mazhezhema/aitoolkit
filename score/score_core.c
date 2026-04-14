/*
 * score_core.c — Entertainment karaoke scoring engine
 *
 * All arithmetic is integer (int32 / int64).
 * No floating point, no malloc, no third-party libs.
 * Safe for Android NDK, Linux userspace, bare-metal RTOS.
 */
#include "score_core.h"
#include <string.h>

/* ── helpers ─────────────────────────────────────────────────────── */

#define SC_MIN(a, b) ((a) < (b) ? (a) : (b))
#define SC_MAX(a, b) ((a) > (b) ? (a) : (b))
#define SC_CLAMP(x, lo, hi) ((x) < (lo) ? (lo) : ((x) > (hi) ? (hi) : (x)))

static int32_t clamp_i64_to_i32(int64_t x) {
    if (x < -2147483647LL - 1)
        return (-2147483647 - 1);
    if (x > 2147483647LL)
        return 2147483647;
    return (int32_t)x;
}

static int32_t frame_energy(const int16_t *samples, int32_t n) {
    int64_t sum = 0;
    for (int32_t i = 0; i < n; i++) {
        int32_t s = samples[i];
        sum += (int64_t)s * s;
    }
    return (n > 0) ? (int32_t)(sum / n) : 0;
}

static void accum_reset(ScoreAccum *a) {
    a->cnt       = 0;
    a->voiced    = 0;
    a->sum_e     = 0;
    a->max_e     = 0;
    a->min_e     = 0x7FFFFFFF;   /* INT32_MAX */
    a->onset_max = 0;
}

static void accum_update(ScoreAccum *a, int32_t e, int32_t voiced,
                         int32_t onset, int32_t is_early) {
    a->cnt++;
    a->voiced += voiced;
    a->sum_e  += e;
    if (e > a->max_e) a->max_e = e;
    if (e < a->min_e) a->min_e = e;
    if (is_early && onset > a->onset_max)
        a->onset_max = onset;
}

/* ── init / calibrate ────────────────────────────────────────────── */

void score_init(ScoreCtx *ctx, int32_t sample_rate, int32_t hop_ms) {
    if (!ctx)
        return;

    if (sample_rate <= 0)
        sample_rate = 16000;
    if (hop_ms <= 0)
        hop_ms = 20;

    memset(ctx, 0, sizeof(*ctx));
    ctx->sample_rate  = sample_rate;
    ctx->hop_samples  = clamp_i64_to_i32((int64_t)sample_rate * hop_ms / 1000);
    if (ctx->hop_samples < 1)
        ctx->hop_samples = 1;
    if (ctx->hop_samples > 9600)              /* cap: 48 kHz × 200 ms */
        ctx->hop_samples = 9600;
    ctx->early_frames = 200 / hop_ms;         /* ~200 ms */
    if (ctx->early_frames < 1)
        ctx->early_frames = 1;
    ctx->combo_thr    = 82;                   /* segment >= 82 → combo */
    accum_reset(&ctx->seg);
    accum_reset(&ctx->line);
}

void score_cal_feed(ScoreCtx *ctx, const int16_t *samples) {
    if (!ctx || !samples)
        return;
    int32_t e = frame_energy(samples, ctx->hop_samples);
    ctx->cal_sum += e;
    ctx->cal_cnt++;
}

void score_cal_done(ScoreCtx *ctx) {
    if (!ctx)
        return;
    if (ctx->cal_cnt > 0) {
        int64_t noise = ctx->cal_sum / ctx->cal_cnt;
        int64_t thr = noise * 4 + 100;
        ctx->thr_e = clamp_i64_to_i32(thr);
    } else {
        ctx->thr_e = 5000;                    /* safe fallback */
    }
    if (ctx->thr_e < 1)
        ctx->thr_e = 1;
    ctx->onset_thr = SC_MAX(ctx->thr_e / 2, 1);
    ctx->cal_done  = 1;
}

void score_set_thr(ScoreCtx *ctx, int32_t thr_e) {
    if (!ctx)
        return;
    ctx->thr_e     = SC_MAX(thr_e, 1);
    ctx->onset_thr = SC_MAX(ctx->thr_e / 2, 1);
    ctx->cal_done  = 1;
}

/* ── begin / feed ────────────────────────────────────────────────── */

void score_seg_begin(ScoreCtx *ctx) {
    if (!ctx)
        return;
    accum_reset(&ctx->seg);
    ctx->seg_frames  = 0;
    ctx->seg_active  = 1;
}

void score_line_begin(ScoreCtx *ctx) {
    if (!ctx)
        return;
    accum_reset(&ctx->line);
    ctx->line_frames = 0;
    ctx->line_active = 1;
}

void score_feed(ScoreCtx *ctx, const int16_t *samples) {
    if (!ctx || !samples)
        return;
    int32_t e      = frame_energy(samples, ctx->hop_samples);
    int32_t voiced = (e > ctx->thr_e) ? 1 : 0;
    int32_t onset  = (e > ctx->prev_e) ? (e - ctx->prev_e) : 0;

    if (ctx->seg_active) {
        accum_update(&ctx->seg, e, voiced, onset,
                     ctx->seg_frames < ctx->early_frames);
        ctx->seg_frames++;
    }

    if (ctx->line_active) {
        accum_update(&ctx->line, e, voiced, onset,
                     ctx->line_frames < ctx->early_frames);
        ctx->line_frames++;
    }

    ctx->prev_e = e;
}

/* ── segment end ─────────────────────────────────────────────────── */

ScoreSegResult score_seg_end(ScoreCtx *ctx) {
    ScoreSegResult r = {0, 0, 0};
    if (!ctx || !ctx->seg_active)
        return r;
    ctx->seg_active = 0;
    ScoreAccum *a = &ctx->seg;
    int32_t cnt   = SC_MAX(a->cnt, 1);

    /* voiced ratio → base score  68..90 */
    int32_t p    = (int32_t)((int64_t)a->voiced * 100 / cnt);
    int32_t base = 68 + p * 22 / 100;

    /* onset bonus  0..5 */
    int32_t bonus = (a->onset_max > ctx->onset_thr) ? 5 : 0;

    /* energy bonus: avg_e vs threshold  0..3 */
    int32_t avg_e = (int32_t)(a->sum_e / cnt);
    int32_t e_bonus = (int32_t)SC_CLAMP(
        (int64_t)avg_e * 3 / SC_MAX(ctx->thr_e, 1), 0, 3);

    r.score = SC_CLAMP(base + bonus + e_bonus, 68, 95);

    /* combo — threshold 82 so mediocre performance does break */
    if (r.score >= ctx->combo_thr) {
        ctx->combo++;
    } else {
        ctx->combo = 0;
    }
    if (ctx->combo > ctx->max_combo)
        ctx->max_combo = ctx->combo;

    r.combo     = ctx->combo;
    r.max_combo = ctx->max_combo;

    accum_reset(&ctx->seg);
    ctx->seg_frames = 0;
    return r;
}

/* ── line end ────────────────────────────────────────────────────── */

ScoreLineResult score_line_end(ScoreCtx *ctx) {
    ScoreLineResult r = {0};
    if (!ctx || !ctx->line_active)
        return r;
    ctx->line_active = 0;
    ScoreAccum *a = &ctx->line;
    int32_t cnt   = SC_MAX(a->cnt, 1);
    int32_t avg_e = (int32_t)(a->sum_e / cnt);

    /* 技巧 technique — voiced ratio */
    {
        int32_t p = (int32_t)((int64_t)a->voiced * 100 / cnt);
        r.technique = 70 + p * 25 / 100;
        r.technique = SC_CLAMP(r.technique, 70, 95);
    }

    /* 感情 emotion — voiced-weighted dynamic range */
    {
        int32_t dyn = a->max_e - SC_MIN(a->min_e, a->max_e);
        int32_t raw = (avg_e > 0)
                      ? (int32_t)SC_MIN(100LL, (int64_t)dyn * 100 / avg_e)
                      : 0;
        int32_t vp  = (int32_t)((int64_t)a->voiced * 100 / cnt);
        int32_t ep  = raw * vp / 100;
        r.emotion = 70 + ep * 25 / 100;
        r.emotion = SC_CLAMP(r.emotion, 70, 95);
    }

    /* 气场 vibe — voiced-weighted peak-to-avg ratio */
    {
        int32_t raw = (avg_e > 0)
                      ? (int32_t)SC_MIN(
                            100LL,
                            SC_MAX(0LL, (int64_t)a->max_e * 100 / avg_e - 100))
                      : 0;
        int32_t vp  = (int32_t)((int64_t)a->voiced * 100 / cnt);
        int32_t pr  = raw * vp / 100;
        r.vibe = 70 + pr * 25 / 100;
        r.vibe = SC_CLAMP(r.vibe, 70, 95);
    }

    /* 节奏 rhythm — onset strength mapped to 74..92 */
    {
        int32_t othr = SC_MAX(ctx->onset_thr, 1);
        int32_t rp   = (int32_t)SC_CLAMP(
            (int64_t)a->onset_max * 100 / othr, 0, 200);
        r.rhythm = 74 + rp * 18 / 200;
        r.rhythm = SC_CLAMP(r.rhythm, 74, 92);
    }

    /* 总分 total — weighted average */
    r.total = (r.technique * 30
             + r.emotion   * 30
             + r.vibe      * 25
             + r.rhythm    * 15) / 100;
    r.total = SC_CLAMP(r.total, 72, 96);

    r.combo     = ctx->combo;
    r.max_combo = ctx->max_combo;

    accum_reset(&ctx->line);
    ctx->line_frames = 0;
    return r;
}
