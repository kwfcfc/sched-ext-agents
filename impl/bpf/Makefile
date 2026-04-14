# eBPF module build rules
#
# Compiles sched_ext_fair.bpf.c to sched_ext_fair.bpf.o
# using clang with BPF target.

CLANG     ?= clang-17
LLC       ?= llc-17
BPFTOOL   ?= bpftool

ARCH      := $(shell uname -m | sed 's/x86_64/x86/' | sed 's/aarch64/arm64/')
BPF_FLAGS := -g -O2 \
             -target bpf \
             -D__TARGET_ARCH_$(ARCH) \
             -I headers/ \
             -I src/ \
             -Wall -Werror

# Add DEBUG_INVARIANTS for debug builds
ifdef DEBUG
BPF_FLAGS += -DDEBUG_INVARIANTS
endif

SRCS := $(wildcard src/*.bpf.c)
OBJS := $(SRCS:.bpf.c=.bpf.o)

.PHONY: all clean

all: $(OBJS)

src/%.bpf.o: src/%.bpf.c src/*.h headers/vmlinux.h
	$(CLANG) $(BPF_FLAGS) -c $< -o $@

headers/vmlinux.h:
	$(BPFTOOL) btf dump file /sys/kernel/btf/vmlinux format c > $@

clean:
	rm -f src/*.bpf.o
