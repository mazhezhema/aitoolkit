/*
 * lrctxt_parse.h — Minimal KRC-style lyric time-axis parser
 *
 * Pure C99, no third-party dependencies.
 * Parses [mm:ss.mmm] timestamps and <dur,sp> token pairs.
 *
 * RTOS note: uses malloc/free for output buffers.
 *            Override LRC_MALLOC / LRC_FREE if needed.
 */
#ifndef LRCTXT_PARSE_H
#define LRCTXT_PARSE_H

#define LRC_VERSION_MAJOR  1
#define LRC_VERSION_MINOR  0
#define LRC_VERSION_PATCH  0

#include <stdint.h>

#ifndef LRC_MALLOC
#include <stdlib.h>
#define LRC_MALLOC(sz) malloc(sz)
#define LRC_FREE(p)    free(p)
#endif

/* One <dur,sp> token — syllable-level singing window */
typedef struct {
    int32_t start_ms;
    int32_t end_ms;
} LrcToken;

/* One [mm:ss.mmm] line — sentence-level singing window */
typedef struct {
    int32_t start_ms;
    int32_t end_ms;
    int32_t token_off;   /* first token index in LrcData.tokens[] */
    int32_t token_cnt;   /* number of tokens in this line         */
} LrcLine;

/* Parsed lrctxt data */
typedef struct {
    LrcLine  *lines;
    int32_t   n_lines;
    LrcToken *tokens;
    int32_t   n_tokens;
} LrcData;

/* lrc_parse() return codes — lrctxt 必须为合法 UTF-8（曲库中 GBK 等会先被拦下） */
#define LRC_PARSE_OK            0
#define LRC_PARSE_ERR_ALLOC    -1
#define LRC_PARSE_ERR_ENCODING -2
#define LRC_PARSE_ERR_FORMAT   -3

/*
 * Parse lrctxt content (null-terminated string).
 * 全文先做严格 UTF-8 校验；非法序列（常见为 GBK/ANSI 误当 UTF-8）返回 LRC_PARSE_ERR_ENCODING。
 * 时间戳 / token 若语法错误、数值过大或解析溢出，返回 LRC_PARSE_ERR_FORMAT。
 * 成功返回 LRC_PARSE_OK；堆分配失败返回 LRC_PARSE_ERR_ALLOC。
 * text 为 NULL 或仅含 '\\0' 时返回 LRC_PARSE_OK 且 out 为空。
 * out 必须为非 NULL。
 * Caller must call lrc_free() when done.
 */
int  lrc_parse(const char *text, LrcData *out);
void lrc_free(LrcData *d);

#endif /* LRCTXT_PARSE_H */
