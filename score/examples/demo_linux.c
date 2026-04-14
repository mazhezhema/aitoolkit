/*
 * Linux 可运行示例：读 lrctxt 文件 + 合成 PCM，走完整打分流程。
 *
 * 编译（在 aitoolkit/score 目录下）:
 *   make -f examples/Makefile
 *
 * 运行:
 *   ./examples/demo_linux path/to/song.lrctxt [quiet|mid|loud]
 *
 * quiet/mid/loud 控制合成音量（模拟唱得小声 / 一般 / 大声）。
 */
#include "lrctxt_parse.h"
#include "score_core.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define SAMPLE_RATE 16000
#define HOP_MS      20

static int32_t hop_samples(void) {
    return SAMPLE_RATE * HOP_MS / 1000;
}

/* 读整个文件为以 '\0' 结尾的缓冲区 */
static char *read_file(const char *path) {
    FILE *fp = fopen(path, "rb");
    if (!fp) return NULL;
    if (fseek(fp, 0, SEEK_END) != 0) { fclose(fp); return NULL; }
    long sz = ftell(fp);
    if (sz < 0 || sz > 16 * 1024 * 1024) { fclose(fp); return NULL; }
    rewind(fp);
    char *buf = (char *)malloc((size_t)sz + 1);
    if (!buf) { fclose(fp); return NULL; }
    if (fread(buf, 1, (size_t)sz, fp) != (size_t)sz) {
        free(buf);
        fclose(fp);
        return NULL;
    }
    buf[sz] = '\0';
    fclose(fp);
    return buf;
}

/* 简单合成一帧 PCM：mode 0=安静 1=中等 2=大声 */
static void synth_frame(int16_t *out, int32_t n, int mode, uint32_t *rng) {
    uint32_t x = *rng;
    int amp = (mode == 0) ? 40 : (mode == 1) ? 3500 : 11000;
    for (int32_t i = 0; i < n; i++) {
        x ^= x << 13;
        x ^= x >> 17;
        x ^= x << 5;
        *rng = x;
        int32_t v = (int32_t)(x % (2 * amp + 1)) - amp;
        if (v > 32767) v = 32767;
        if (v < -32768) v = -32768;
        out[i] = (int16_t)v;
    }
}

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "用法: %s <歌词.lrctxt> [quiet|mid|loud]\n", argv[0]);
        return 1;
    }
    int mode = 1;
    if (argc >= 3) {
        if (strcmp(argv[2], "quiet") == 0) mode = 0;
        else if (strcmp(argv[2], "loud") == 0) mode = 2;
        else if (strcmp(argv[2], "mid") == 0) mode = 1;
    }

    char *text = read_file(argv[1]);
    if (!text) {
        fprintf(stderr, "无法读取: %s\n", argv[1]);
        return 1;
    }

    LrcData lrc;
    memset(&lrc, 0, sizeof(lrc));
    {
        int pr = lrc_parse(text, &lrc);
        if (pr == LRC_PARSE_ERR_ENCODING) {
            fprintf(stderr, "lrc_parse: 歌词不是合法 UTF-8（可能是 GBK，请先转码）\n");
            free(text);
            return 1;
        }
        if (pr == LRC_PARSE_ERR_FORMAT) {
            fprintf(stderr, "lrc_parse: 歌词格式非法（时间戳 / token 语法错误或数值过大）\n");
            free(text);
            return 1;
        }
        if (pr != LRC_PARSE_OK) {
            fprintf(stderr, "lrc_parse 分配失败\n");
            free(text);
            return 1;
        }
    }
    free(text);

    printf("解析: %d 行, %d 个 token\n", (int)lrc.n_lines, (int)lrc.n_tokens);

    ScoreCtx ctx;
    score_init(&ctx, SAMPLE_RATE, HOP_MS);

    int32_t hs = hop_samples();
    int16_t *frame = (int16_t *)malloc((size_t)hs * sizeof(int16_t));
    if (!frame) {
        lrc_free(&lrc);
        return 1;
    }

    /* 校准：安静帧 */
    uint32_t rng = 12345u;
    for (int i = 0; i < 20; i++) {
        synth_frame(frame, hs, 0, &rng);
        score_cal_feed(&ctx, frame);
    }
    score_cal_done(&ctx);

    /* 只打印前 5 行，避免刷屏 */
    int max_lines = lrc.n_lines < 5 ? lrc.n_lines : 5;

    for (int li = 0; li < max_lines; li++) {
        LrcLine *ln = &lrc.lines[li];
        score_line_begin(&ctx);

        printf("\n--- 行 %d [%d ms .. %d ms] tokens=%d ---\n",
               li, (int)ln->start_ms, (int)ln->end_ms, (int)ln->token_cnt);

        for (int j = 0; j < ln->token_cnt; j++) {
            LrcToken *tk = &lrc.tokens[ln->token_off + j];
            int32_t dur_ms = tk->end_ms - tk->start_ms;
            int32_t nfr = (dur_ms + HOP_MS - 1) / HOP_MS;
            if (nfr < 1) nfr = 1;

            score_seg_begin(&ctx);
            for (int f = 0; f < nfr; f++) {
                synth_frame(frame, hs, mode, &rng);
                score_feed(&ctx, frame);
            }
            ScoreSegResult seg = score_seg_end(&ctx);
            printf("  token[%d] %d..%d ms → seg=%d combo=%d max_combo=%d\n",
                   j, (int)tk->start_ms, (int)tk->end_ms,
                   (int)seg.score, (int)seg.combo, (int)seg.max_combo);
        }
        ScoreLineResult line = score_line_end(&ctx);
        printf("  行小结: 技巧=%d 感情=%d 气场=%d 节奏=%d 总分=%d combo=%d\n",
               (int)line.technique, (int)line.emotion, (int)line.vibe,
               (int)line.rhythm, (int)line.total, (int)line.combo);
    }

    if (lrc.n_lines > max_lines)
        printf("\n... 其余 %d 行略（改 max_lines 可多看）\n", (int)(lrc.n_lines - max_lines));

    free(frame);
    lrc_free(&lrc);
    return 0;
}
