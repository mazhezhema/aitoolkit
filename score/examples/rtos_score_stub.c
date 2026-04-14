/*
 * RTOS 示例：静态 ScoreCtx，按 token/行驱动 score_* API。
 *
 * lrctxt 解析器的堆：
 *   编译 lrctxt_parse.c 时增加（按你的 RTOS 堆函数改名）:
 *     -DLRC_MALLOC=my_malloc -DLRC_FREE=my_free
 *   并在链接阶段提供 my_malloc/my_free 实现。
 *
 * 本文件不调用 lrc_parse，避免与默认 malloc 耦合；选歌后在别的任务里
 *   lrc_parse() 成功后再调用 karaoke_rtos_score_init()。
 *
 * 音频：将 I2S/DMA 每 20ms 得到的 320 个 s16 _mono_16k 填入 frame，
 *       调用 karaoke_rtos_feed_frame()。
 */

#include "score_core.h"

#include <string.h>

static ScoreCtx s_ctx;
static int s_ready;

void karaoke_rtos_score_init(int32_t sample_rate, int32_t hop_ms) {
    score_init(&s_ctx, sample_rate, hop_ms);
    s_ready = 1;
}

/* 开唱前连续调用：静音帧 */
void karaoke_rtos_cal_feed(const int16_t *pcm, int32_t hop_samples) {
    (void)hop_samples;
    if (s_ready) score_cal_feed(&s_ctx, pcm);
}

void karaoke_rtos_cal_done(void) {
    if (s_ready) score_cal_done(&s_ctx);
}

void karaoke_rtos_line_begin(void) {
    if (s_ready) score_line_begin(&s_ctx);
}

void karaoke_rtos_seg_begin(void) {
    if (s_ready) score_seg_begin(&s_ctx);
}

void karaoke_rtos_feed_frame(const int16_t *pcm) {
    if (s_ready) score_feed(&s_ctx, pcm);
}

void karaoke_rtos_seg_end(int *out_score, int *out_combo, int *out_max_combo) {
    ScoreSegResult r = score_seg_end(&s_ctx);
    if (out_score) *out_score = r.score;
    if (out_combo) *out_combo = r.combo;
    if (out_max_combo) *out_max_combo = r.max_combo;
}

void karaoke_rtos_line_end(int *tech, int *emo, int *vibe, int *rhythm,
                           int *total, int *combo, int *max_combo) {
    ScoreLineResult r = score_line_end(&s_ctx);
    if (tech) *tech = r.technique;
    if (emo) *emo = r.emotion;
    if (vibe) *vibe = r.vibe;
    if (rhythm) *rhythm = r.rhythm;
    if (total) *total = r.total;
    if (combo) *combo = r.combo;
    if (max_combo) *max_combo = r.max_combo;
}

/*
 * 伪代码：在“音频任务”里按歌词时间轴驱动（与 Linux demo 相同逻辑）
 *
 *   for each line in LrcData:
 *     karaoke_rtos_line_begin();
 *     for each token in line:
 *       karaoke_rtos_seg_begin();
 *       for (t = token.start_ms; t < token.end_ms; t += hop_ms)
 *           read_i2s_to_buffer(pcm, hop_samples);
 *           karaoke_rtos_feed_frame(pcm);
 *       int s,c,m; karaoke_rtos_seg_end(&s,&c,&m);
 *     int ...; karaoke_rtos_line_end(...);
 */
