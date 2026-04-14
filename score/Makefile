CC      ?= gcc
CFLAGS  ?= -std=c99 -Wall -Wextra -O2
HDRS     = -I.

# ── library ──────────────────────────────────────────────
LIB      = libscore.a
LIB_SRCS = lrctxt_parse.c score_core.c
LIB_OBJS = $(LIB_SRCS:.c=.o)

# ── examples & tests ─────────────────────────────────────
DEMO         = examples/demo_linux
SMOKE_LRC    = examples/smoke_lrctxt
SMOKE_SCORE  = examples/smoke_score_core

.PHONY: all lib demo smoke smoke-score test clean

all: lib demo

lib: $(LIB)

$(LIB): $(LIB_OBJS)
	ar rcs $@ $^

%.o: %.c
	$(CC) $(CFLAGS) $(HDRS) -c $< -o $@

demo: $(DEMO)

$(DEMO): examples/demo_linux.c $(LIB_SRCS)
	$(CC) $(CFLAGS) $(HDRS) -o $@ examples/demo_linux.c $(LIB_SRCS)

$(SMOKE_LRC): examples/smoke_lrctxt.c lrctxt_parse.c
	$(CC) $(CFLAGS) $(HDRS) -o $@ examples/smoke_lrctxt.c lrctxt_parse.c

$(SMOKE_SCORE): examples/smoke_score_core.c score_core.c
	$(CC) $(CFLAGS) $(HDRS) -o $@ examples/smoke_score_core.c score_core.c

smoke: $(SMOKE_LRC)
	$(SMOKE_LRC)

smoke-score: $(SMOKE_SCORE)
	$(SMOKE_SCORE)

test: smoke smoke-score

clean:
	rm -f *.o $(LIB)
	rm -f $(DEMO) $(DEMO).exe
	rm -f $(SMOKE_LRC) $(SMOKE_LRC).exe
	rm -f $(SMOKE_SCORE) $(SMOKE_SCORE).exe
