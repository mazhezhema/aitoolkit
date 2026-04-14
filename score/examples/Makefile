# 兼容旧调用方式：从 examples/ 子目录执行时代理到上级统一 Makefile
# 用法不变：
#   cd aitoolkit/score && make -f examples/Makefile smoke
#   cd aitoolkit/score && make -f examples/Makefile smoke-score
#
# 推荐直接使用:
#   cd aitoolkit/score && make test

%:
	$(MAKE) -C .. -f Makefile $@

.DEFAULT_GOAL := all
