# ═══════════════════════════════════════════════════════════
# Round-Robin sched_ext eBPF module build
# ═══════════════════════════════════════════════════════════

CLANG      := clang
LLC        := llc
BPFTOOL    := bpftool

# Kernel headers (generated vmlinux.h or system headers)
VMLINUX_H  := /sys/kernel/btf/vmlinux
BPF_CFLAGS := -O2 -g -target bpf \
              -D__TARGET_ARCH_x86 \
              -I/usr/include \
              -I../../specs-rr \
              -Wall -Werror

SRC        := src/sched_ext_rr.bpf.c
OBJ        := sched_ext_rr.bpf.o

.PHONY: all clean vmlinux

all: vmlinux $(OBJ)

# Generate vmlinux.h from kernel BTF if not present
vmlinux: src/vmlinux.h

src/vmlinux.h:
	@if [ -f $(VMLINUX_H) ]; then \
		$(BPFTOOL) btf dump file $(VMLINUX_H) format c > $@; \
	else \
		echo "WARNING: No BTF found at $(VMLINUX_H), using stub"; \
		touch $@; \
	fi

$(OBJ): $(SRC) src/sched_ext_rr.h src/invariants.h src/vmlinux.h
	$(CLANG) $(BPF_CFLAGS) -c $(SRC) -o $@

clean:
	rm -f $(OBJ) src/vmlinux.h
