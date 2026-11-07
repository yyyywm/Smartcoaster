# 宿主侧单元测试（不依赖 ESP-IDF / 硬件）
#
# 用法：
#   make all      编译两个测试
#   make test     编译并运行全部测试
#   make clean    清理
#
# 工具链：gcc（Windows 下 MinGW-w64；Linux/macOS 默认 cc 亦可）。
#         可用 `make CC=clang test` 覆盖编译器。
# 注意：GNU make 内置 CC=cc，`?=` 不会覆盖它，故显式判断来源。
ifeq ($(origin CC),default)
  CC := gcc
endif

CFLAGS  ?= -std=c11 -O2 -g -Wall -Wextra -Werror
LDFLAGS ?= -lm

TEST_DIR  := .
ROOT      := ..
CORE_DIR  := $(ROOT)/components/coaster
INC_COMMON := -I$(TEST_DIR) -I$(CORE_DIR)/include
INC_STUBS  := -I$(TEST_DIR)/stubs

CORE_SRCS := $(CORE_DIR)/coaster.c $(CORE_DIR)/protocol.c

COASTER_TEST := test_coaster
PROTO_TEST    := test_protocol

# Windows 用 del 并抑制“文件不存在”报错（保持 clean 幂等）；Unix 用 rm -f
ifeq ($(OS),Windows_NT)
  RUN     := ./
  RM      := del /Q
  RMFLAGS := 2>nul
else
  RUN     :=
  RM      := rm -f
  RMFLAGS :=
endif

.PHONY: all test clean

all: $(COASTER_TEST) $(PROTO_TEST)

$(COASTER_TEST): $(TEST_DIR)/test_coaster.c $(CORE_DIR)/coaster.c $(TEST_DIR)/test_util.h
	$(CC) $(CFLAGS) $(INC_COMMON) $^ -o $@ $(LDFLAGS)

$(PROTO_TEST): $(TEST_DIR)/test_protocol.c $(CORE_DIR)/protocol.c $(CORE_DIR)/include/protocol.h $(CORE_DIR)/include/coaster.h
	$(CC) $(CFLAGS) $(INC_COMMON) $(INC_STUBS) $< $(CORE_DIR)/protocol.c -o $@ $(LDFLAGS)

test: $(COASTER_TEST) $(PROTO_TEST)
	$(RUN)$(COASTER_TEST)
	$(RUN)$(PROTO_TEST)

clean:
	$(RM) $(COASTER_TEST) $(PROTO_TEST) $(RMFLAGS)
