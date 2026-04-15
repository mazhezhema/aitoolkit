/*
 * lrctxt_parse.c — Hand-written KRC lyric parser (no regex)
 *
 * Two-pass: count entities, allocate, fill.
 * All <dur,sp> tokens between two [timestamp] markers belong to the
 * most recent line — handles tokens on the same line or the next.
 */
#include "lrctxt_parse.h"
#include <string.h>

/* ── helpers ─────────────────────────────────────────────────────── */

static int parse_u31(const char **pp, int32_t *out, int *digits_out) {
    const char *p = *pp;
    int64_t v = 0;
    int digits = 0;

    while (*p >= '0' && *p <= '9') {
        int d = *p - '0';
        if (v > (0x7FFFFFFFLL - d) / 10)
            return -1;
        v = v * 10 + d;
        p++;
        digits++;
    }
    if (digits == 0)
        return -1;
    *pp = p;
    *out = (int32_t)v;
    if (digits_out)
        *digits_out = digits;
    return 0;
}

/*
 * Heuristics for distinguishing "this looks like an actual tag but is malformed"
 * from ordinary lyric text that happens to contain '[' ']' or '<' '>'.
 */
static int looks_like_ts_tag(const char *p) {
    if (*p != '[')
        return 0;
    p++;
    if (!(*p >= '0' && *p <= '9'))
        return 0;
    while (*p >= '0' && *p <= '9')
        p++;
    if (*p != ':')
        return 0;
    p++;
    if (!(*p >= '0' && *p <= '9'))
        return 0;
    while (*p >= '0' && *p <= '9')
        p++;
    if (*p != '.')
        return 0;
    p++;
    return (*p >= '0' && *p <= '9');
}

static int looks_like_tok_tag(const char *p) {
    if (*p != '<')
        return 0;
    p++;
    if (!(*p >= '0' && *p <= '9'))
        return 0;
    while (*p >= '0' && *p <= '9')
        p++;
    if (*p != ',')
        return 0;
    p++;
    return (*p >= '0' && *p <= '9');
}

/* Parse [mm:ss.mmm], return ms or -1. *end_out points past ']'. */
static int32_t parse_ts(const char *p, const char **end_out) {
    if (*p != '[') return -1;
    p++;
    int32_t mm = 0;
    if (parse_u31(&p, &mm, NULL) != 0)
        return -1;
    if (*p != ':') return -1;
    p++;
    int32_t ss = 0;
    if (parse_u31(&p, &ss, NULL) != 0)
        return -1;
    if (*p != '.') return -1;
    p++;
    int32_t ms = 0;
    int d = 0;
    if (parse_u31(&p, &ms, &d) != 0)
        return -1;
    if (*p != ']') return -1;
    p++;
    while (d < 3) {
        if (ms > 0x7FFFFFFF / 10)
            return -1;
        ms *= 10;
        d++;
    }
    while (d > 3) { ms /= 10; d--; }
    if (end_out) *end_out = p;
    {
        int64_t total = (int64_t)mm * 60000 + (int64_t)ss * 1000 + ms;
        if (total > 0x7FFFFFFFLL)
            return -1;
        return (int32_t)total;
    }
}

/* Strict UTF-8 (RFC 3629); rejects continuation/C0-C1/surrogate/overlong. */
static int utf8_valid(const char *s) {
    const unsigned char *p = (const unsigned char *)s;
    while (*p) {
        unsigned c = *p++;
        if (c < 0x80u)
            continue;
        if (c < 0xC2u)
            return 0;
        if (c <= 0xDFu) {
            if ((*p++ & 0xC0u) != 0x80u)
                return 0;
            continue;
        }
        if (c <= 0xEFu) {
            unsigned c1 = *p++;
            if ((c1 & 0xC0u) != 0x80u)
                return 0;
            if (c == 0xE0u && c1 < 0xA0u)
                return 0;
            if (c == 0xEDu && c1 > 0x9Fu)
                return 0;
            unsigned c2 = *p++;
            if ((c2 & 0xC0u) != 0x80u)
                return 0;
            continue;
        }
        if (c <= 0xF4u) {
            unsigned c1 = *p++;
            if ((c1 & 0xC0u) != 0x80u)
                return 0;
            if (c == 0xF0u && c1 < 0x90u)
                return 0;
            if (c == 0xF4u && c1 > 0x8Fu)
                return 0;
            unsigned c2 = *p++;
            if ((c2 & 0xC0u) != 0x80u)
                return 0;
            unsigned c3 = *p++;
            if ((c3 & 0xC0u) != 0x80u)
                return 0;
            continue;
        }
        return 0;
    }
    return 1;
}

/* Parse <dur,sp>, return dur (ms) or -1. *end_out points past '>'. */
static int32_t parse_tok(const char *p, const char **end_out) {
    if (*p != '<') return -1;
    p++;
    int32_t dur = 0;
    if (parse_u31(&p, &dur, NULL) != 0)
        return -1;
    if (*p != ',') return -1;
    p++;
    {
        int32_t ignored = 0;
        if (parse_u31(&p, &ignored, NULL) != 0)
            return -1;
    }
    if (*p != '>') return -1;
    p++;
    if (end_out) *end_out = p;
    return dur;
}

/* ── public API ──────────────────────────────────────────────────── */

int lrc_parse(const char *text, LrcData *out) {
    if (!out)
        return LRC_PARSE_ERR_FORMAT;
    memset(out, 0, sizeof(*out));
    if (!text || !*text)
        return LRC_PARSE_OK;
    if (!utf8_valid(text))
        return LRC_PARSE_ERR_ENCODING;

    /* ---- pass 1: count lines & tokens ---- */
    int32_t max_lines = 0, max_tokens = 0;
    for (const char *p = text; *p; p++) {
        const char *e;
        if (*p == '[') {
            if (parse_ts(p, &e) >= 0) {
                max_lines++;
            } else if (looks_like_ts_tag(p)) {
                return LRC_PARSE_ERR_FORMAT;
            }
        }
        if (*p == '<') {
            if (parse_tok(p, &e) >= 0) {
                max_tokens++;
            } else if (looks_like_tok_tag(p)) {
                return LRC_PARSE_ERR_FORMAT;
            }
        }
    }
    if (max_lines == 0)
        return LRC_PARSE_OK;

    out->lines  = (LrcLine *)LRC_MALLOC((size_t)max_lines * sizeof(LrcLine));
    out->tokens = max_tokens
                  ? (LrcToken *)LRC_MALLOC((size_t)max_tokens * sizeof(LrcToken))
                  : NULL;
    if (!out->lines || (max_tokens && !out->tokens)) {
        lrc_free(out);
        return LRC_PARSE_ERR_ALLOC;
    }
    memset(out->lines,  0, (size_t)max_lines  * sizeof(LrcLine));
    if (out->tokens)
        memset(out->tokens, 0, (size_t)max_tokens * sizeof(LrcToken));

    /* ---- pass 2: extract in order ---- */
    /*
     * Merge consecutive [timestamp] lines that share the same ms value:
     * text-only line followed by token line → single logical line.
     */
    int32_t li = -1, ti = 0;
    for (const char *p = text; *p; ) {
        const char *e;

        if (*p == '[') {
            int32_t ts = parse_ts(p, &e);
            if (ts >= 0) {
                /* reuse previous line if same timestamp and no tokens yet */
                if (li >= 0 && out->lines[li].start_ms == ts
                    && out->lines[li].token_cnt == 0) {
                    /* same line, just advance past text */
                } else {
                    li++;
                    out->lines[li].start_ms  = ts;
                    out->lines[li].token_off = ti;
                    out->lines[li].token_cnt = 0;
                }
                p = e;
                continue;
            }
        }

        if (*p == '<' && li >= 0) {
            int32_t dur = parse_tok(p, &e);
            if (dur >= 0 && ti < max_tokens) {
                out->tokens[ti].end_ms = dur;   /* temp: store dur */
                ti++;
                out->lines[li].token_cnt++;
                p = e;
                continue;
            }
        }

        p++;
    }

    out->n_lines  = li + 1;
    out->n_tokens = ti;

    /* ---- pass 3: absolute token times ---- */
    for (int32_t i = 0; i < out->n_lines; i++) {
        LrcLine *ln = &out->lines[i];
        int32_t cur = ln->start_ms;
        for (int32_t j = 0; j < ln->token_cnt; j++) {
            LrcToken *tk = &out->tokens[ln->token_off + j];
            int32_t dur  = tk->end_ms;          /* retrieve temp dur */
            if (dur < 0 || cur > 0x7FFFFFFF - dur) {
                lrc_free(out);
                return LRC_PARSE_ERR_FORMAT;
            }
            tk->start_ms = cur;
            tk->end_ms   = cur + dur;
            cur += dur;
        }
        ln->end_ms = (ln->token_cnt > 0)
                      ? cur
                      : ln->start_ms;
    }

    /* ---- pass 4: compact — remove lines with no tokens ---- */
    {
        int32_t w = 0;
        for (int32_t i = 0; i < out->n_lines; i++) {
            if (out->lines[i].token_cnt > 0) {
                if (w != i)
                    out->lines[w] = out->lines[i];
                w++;
            }
        }
        out->n_lines = w;
    }

    return LRC_PARSE_OK;
}

void lrc_free(LrcData *d) {
    if (!d)
        return;
    if (d->lines)  { LRC_FREE(d->lines);  d->lines  = NULL; }
    if (d->tokens) { LRC_FREE(d->tokens); d->tokens = NULL; }
    d->n_lines  = 0;
    d->n_tokens = 0;
}
