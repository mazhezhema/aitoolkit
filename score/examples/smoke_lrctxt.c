/*
 * lrctxt_parse 冒烟：UTF-8 门禁 + 基本解析。
 *
 * 在 aitoolkit/score 目录执行:
 *   make -f examples/Makefile smoke
 */
#include "lrctxt_parse.h"
#include <stdio.h>
#include <string.h>

static int die(const char *msg, int code) {
    fprintf(stderr, "smoke_lrctxt: %s\n", msg);
    return code;
}

int main(void) {
    LrcData d;

    memset(&d, 0, sizeof(d));
    if (lrc_parse("", &d) != LRC_PARSE_OK)
        return die("empty string should return OK", 1);
    lrc_free(&d);

    const char *ascii_ok = "[00:00.000]x<100,0>\n";
    memset(&d, 0, sizeof(d));
    if (lrc_parse(ascii_ok, &d) != LRC_PARSE_OK)
        return die("ascii lrctxt should parse", 2);
    if (d.n_lines < 1 || d.n_tokens < 1)
        return die("expected at least one line and one token", 3);
    lrc_free(&d);

    /* UTF-8「你」 + token */
    const char *utf8_ok = "[00:00.000]\xe4\xbd\xa0<100,0>\n";
    memset(&d, 0, sizeof(d));
    if (lrc_parse(utf8_ok, &d) != LRC_PARSE_OK)
        return die("utf-8 lyric text should parse", 4);
    lrc_free(&d);

    /* 歌词正文允许出现看起来像标签的普通文本 */
    const char *text_with_brackets = "[00:00.000]abc[1]<100,0>\n";
    memset(&d, 0, sizeof(d));
    if (lrc_parse(text_with_brackets, &d) != LRC_PARSE_OK)
        return die("plain lyric text containing [] should still parse", 41);
    lrc_free(&d);

    const char *text_with_angles = "[00:00.000]a<3><100,0>\n";
    memset(&d, 0, sizeof(d));
    if (lrc_parse(text_with_angles, &d) != LRC_PARSE_OK)
        return die("plain lyric text containing <> should still parse", 42);
    lrc_free(&d);

    /* 非法 UTF-8：孤立的 0xFF */
    const char *bad = "\xff";
    memset(&d, 0, sizeof(d));
    if (lrc_parse(bad, &d) != LRC_PARSE_ERR_ENCODING)
        return die("lone 0xFF should be LRC_PARSE_ERR_ENCODING", 5);
    lrc_free(&d);

    /* 非法 UTF-8：0xC3 后接 ASCII '(' 非续字节 */
    const char *bad2 = "[00:00.000]\xc3(<100,0>\n";
    memset(&d, 0, sizeof(d));
    if (lrc_parse(bad2, &d) != LRC_PARSE_ERR_ENCODING)
        return die("ill-formed 2-byte seq should be encoding error", 6);
    lrc_free(&d);

    /* 超大 timestamp：应拒绝，而不是整型溢出后继续解析 */
    const char *huge_ts = "[999999999999:00.000]x<100,0>\n";
    memset(&d, 0, sizeof(d));
    if (lrc_parse(huge_ts, &d) != LRC_PARSE_ERR_FORMAT)
        return die("oversized timestamp should be format error", 7);
    lrc_free(&d);

    /* 超大 dur：应拒绝，而不是 tk/end_ms/cur 溢出 */
    const char *huge_dur = "[00:00.000]x<999999999999,0>\n";
    memset(&d, 0, sizeof(d));
    if (lrc_parse(huge_dur, &d) != LRC_PARSE_ERR_FORMAT)
        return die("oversized token duration should be format error", 8);
    lrc_free(&d);

    puts("smoke_lrctxt: ok");
    return 0;
}
