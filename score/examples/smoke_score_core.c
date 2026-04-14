/*
 * score_core 冒烟：初始化、校准、静音/有声、combo 基本行为。
 *
 * 在 aitoolkit/score 目录执行:
 *   make -f examples/Makefile smoke-score
 */
#include "score_core.h"
#include <stdio.h>
#include <string.h>

#define SAMPLE_RATE 16000
#define HOP_MS 20

static int die(const char *msg, int code) {
    fprintf(stderr, "smoke_score_core: %s\n", msg);
    return code;
}

int main(void) {
    ScoreCtx ctx;
    ScoreCtx huge;
    int16_t quiet[SAMPLE_RATE * HOP_MS / 1000];
    int16_t loud[SAMPLE_RATE * HOP_MS / 1000];
    int16_t peak[SAMPLE_RATE * HOP_MS / 1000];

    memset(&ctx, 0, sizeof(ctx));
    memset(&huge, 0, sizeof(huge));
    memset(quiet, 0, sizeof(quiet));
    for (int i = 0; i < (int)(sizeof(loud) / sizeof(loud[0])); i++)
        loud[i] = 12000;
    for (int i = 0; i < (int)(sizeof(peak) / sizeof(peak[0])); i++)
        peak[i] = 32767;

    score_init(&ctx, SAMPLE_RATE, HOP_MS);
    if (ctx.hop_samples != SAMPLE_RATE * HOP_MS / 1000)
        return die("hop_samples mismatch", 1);

    score_init(&huge, 0x7FFFFFFF, 0x7FFFFFFF);
    if (huge.hop_samples < 1 || huge.early_frames < 1)
        return die("extreme init parameters should still clamp safely", 10);

    for (int i = 0; i < 15; i++)
        score_cal_feed(&ctx, quiet);
    score_cal_done(&ctx);
    if (ctx.thr_e <= 0 || ctx.onset_thr <= 0 || !ctx.cal_done)
        return die("calibration did not produce thresholds", 2);

    score_seg_begin(&ctx);
    score_feed(&ctx, quiet);
    {
        ScoreSegResult r = score_seg_end(&ctx);
        if (r.score < 68 || r.score > 95)
            return die("quiet segment score out of range", 3);
        if (r.combo != 0)
            return die("quiet segment should not build combo", 4);
    }

    score_seg_begin(&ctx);
    score_feed(&ctx, loud);
    {
        ScoreSegResult r = score_seg_end(&ctx);
        if (r.score < ctx.combo_thr)
            return die("loud segment should cross combo threshold", 5);
        if (r.combo != 1)
            return die("first strong segment should start combo", 6);
    }

    score_line_begin(&ctx);
    score_feed(&ctx, loud);
    score_feed(&ctx, loud);
    {
        ScoreLineResult r = score_line_end(&ctx);
        if (r.technique < 70 || r.technique > 95)
            return die("technique out of range", 7);
        if (r.total < 72 || r.total > 96)
            return die("total out of range", 8);
        if (r.combo < 1)
            return die("line result should carry combo state", 9);
    }

    score_init(&ctx, SAMPLE_RATE, HOP_MS);
    for (int i = 0; i < 4; i++)
        score_cal_feed(&ctx, peak);
    score_cal_done(&ctx);
    if (ctx.thr_e <= 0 || ctx.onset_thr <= 0)
        return die("calibration should not overflow into negative thresholds", 11);

    puts("smoke_score_core: ok");
    return 0;
}
