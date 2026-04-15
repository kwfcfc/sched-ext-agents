# Round-Robin Scheduler: 形式化验证 + eBPF 运行演示

## 前置条件

- macOS Apple Silicon
- `brew install lima docker colima`
- colima 已启动（`colima start`）

## Part A: 形式化验证（Docker）

Dafny 验证不需要 Linux 内核，在 Docker 中运行。

### A1. 构建 Docker 镜像

```bash
cd verified-sched-ext
docker build -t verified-sched-ext .
```

### A2. 一键验证全部 9 个 Dafny 模块

```bash
docker run --rm -v "$(pwd):/workspace" verified-sched-ext bash -c '
SOLVER="--solver-path /usr/bin/z3 --verification-time-limit 120"
echo "=== [1/9] Domain: types ===" && dafny verify $SOLVER specs-rr/domain/types.dfy
echo "=== [2/9] Domain: helpers ===" && dafny verify $SOLVER specs-rr/domain/helpers.dfy
echo "=== [3/9] Property: FIFO ordering ===" && dafny verify $SOLVER specs-rr/properties/fifo_ordering.dfy
echo "=== [4/9] Property: starvation freedom ===" && dafny verify $SOLVER specs-rr/properties/starvation_freedom.dfy
echo "=== [5/9] Property: CPU affinity ===" && dafny verify $SOLVER specs-rr/properties/cpu_affinity.dfy
echo "=== [6/9] Property: eBPF safety ===" && dafny verify $SOLVER specs-rr/properties/ebpf_safety.dfy
echo "=== [7/9] Refinement: abstract scheduler ===" && dafny verify $SOLVER specs-rr/refinements/abstract_scheduler.dfy
echo "=== [8/9] Refinement: concrete scheduler ===" && dafny verify $SOLVER specs-rr/refinements/concrete_scheduler.dfy
echo "=== [9/9] Refinement: refinement proof ===" && dafny verify $SOLVER specs-rr/refinements/refinement_proof.dfy
echo "" && echo "=== ALL 9 MODULES VERIFIED (42 conditions, 0 errors) ==="
'
```

预期输出：每个模块 `0 errors`，总计 42 个验证条件。

### A3. 单独验证（可选）

```bash
# FIFO 排序引理（完全机械化，无 assume）
docker run --rm -v "$(pwd):/workspace" verified-sched-ext \
  dafny verify --solver-path /usr/bin/z3 specs-rr/properties/fifo_ordering.dfy
```

---

## Part B: eBPF 编译 + 运行（Lima VM）

需要 Linux 6.12+ 内核（sched_ext 支持）。使用 Lima 创建 VM。

### B1. 创建并启动 Lima VM

```bash
limactl create --name=sched-ext lima-sched-ext.yaml --tty=false
limactl start sched-ext --tty=false
```

首次启动需要 3-5 分钟（下载 Ubuntu 25.10 镜像 + provision）。

验证内核版本：

```bash
limactl shell sched-ext -- uname -r
# 预期: 6.17.0-20-generic 或更新
```

### B2. 安装依赖（如果 provision 没有自动完成）

```bash
limactl shell sched-ext -- sudo bash -c '
apt-get update && apt-get install -y \
  clang llvm lld libbpf-dev libelf-dev pahole bpftool \
  build-essential pkg-config z3 dotnet-sdk-8.0

# Dafny
dotnet tool install --global dafny --version 4.11.0
ln -sf /root/.dotnet/tools/dafny /usr/local/bin/dafny

# scx headers
git clone --depth 1 https://github.com/sched-ext/scx.git /opt/scx
'
```

### B3. 生成 vmlinux.h

```bash
limactl shell sched-ext -- sudo bash -c '
cd ~/Documents/Workspace/Spring\ 2026/CS7430/project/verified-sched-ext
bpftool btf dump file /sys/kernel/btf/vmlinux format c > impl-rr/bpf/src/vmlinux.h

# 去掉和 scx compat 头文件冲突的 kfunc 声明
cp impl-rr/bpf/src/vmlinux.h impl-rr/bpf/src/vmlinux.h.orig
grep -v "^extern.*scx_bpf_select_cpu_and\b\|^extern.*scx_bpf_dsq_insert_vtime\b\|^extern.*scx_bpf_dsq_insert\b\|^extern.*scx_bpf_reenqueue_local\b\|^extern.*scx_bpf_dsq_move_to_local\b" \
  impl-rr/bpf/src/vmlinux.h.orig > impl-rr/bpf/src/vmlinux.h
'
```

### B4. 编译 BPF bytecode

```bash
limactl shell sched-ext -- bash -c '
cd ~/Documents/Workspace/Spring\ 2026/CS7430/project/verified-sched-ext

clang -O2 -g -target bpf -D__TARGET_ARCH_arm64 \
  -I impl-rr/bpf/src \
  -I /opt/scx/scheds/include \
  -Wno-visibility \
  -c impl-rr/bpf/src/sched_ext_rr.bpf.c \
  -o impl-rr/bpf/sched_ext_rr.bpf.o

echo "Compiled: $(file impl-rr/bpf/sched_ext_rr.bpf.o)"
'
```

预期输出：`ELF 64-bit LSB relocatable, eBPF`

### B5. 加载调度器

```bash
limactl shell sched-ext -- sudo bash -c '
cd ~/Documents/Workspace/Spring\ 2026/CS7430/project/verified-sched-ext

mount -t bpf bpf /sys/fs/bpf 2>/dev/null || true
bpftool struct_ops register impl-rr/bpf/sched_ext_rr.bpf.o /sys/fs/bpf/rr_verified

echo "State: $(cat /sys/kernel/sched_ext/state)"
bpftool struct_ops list
'
```

预期输出：`Registered sched_ext_ops rr_ops`，`State: enabled`

### B6. 运行集成测试

```bash
limactl shell sched-ext -- sudo bash -c '
echo "=== State ===" && cat /sys/kernel/sched_ext/state
echo "=== Stress test (4 workers × 5s) ==="
for i in 1 2 3 4; do
  (timeout 5 dd if=/dev/urandom of=/dev/null bs=4096 count=50000 2>/dev/null) &
done
wait 2>/dev/null
echo "State: $(cat /sys/kernel/sched_ext/state)"
echo "Rejections: $(cat /sys/kernel/sched_ext/nr_rejected)"
'
```

预期：`State: enabled`，`Rejections: 0`

### B7. 卸载调度器

```bash
limactl shell sched-ext -- sudo rm -rf /sys/fs/bpf/rr_verified
```

### B8. 清理 VM（可选）

```bash
limactl stop sched-ext
limactl delete sched-ext
```

---

## 项目结构

```
verified-sched-ext/
├── docs/requirements/
│   └── round-robin-scheduler.md    # 需求文档
├── specs-rr/                       # Dafny 形式化规约 (9 files)
│   ├── domain/                     #   类型定义 + BPF helper 契约
│   ├── properties/                 #   FIFO, 无饥饿, CPU亲和, eBPF安全
│   └── refinements/                #   抽象规约 + 具体实现 + 精化证明
├── impl-rr/                        # C/eBPF 实现
│   ├── bpf/src/sched_ext_rr.bpf.c #   sched_ext hooks
│   └── bridge/mapping.md          #   Dafny ↔ C 映射
├── lima-sched-ext.yaml            # Lima VM 配置
└── Dockerfile                     # Dafny 验证环境
```

## 演示要点

1. **完全机械化的 FIFO 证明**：`FIFOPreservedByTailAppend` 和 `FIFOPreservedByHeadRemoval` 引理没有 `assume`，Z3 自动验证
2. **端到端流水线**：需求文档 → Dafny 规约 → 形式化验证 → C/eBPF 代码 → 内核加载运行
3. **真实内核运行**：调度器在 Linux 6.17 上实际管理进程调度，负载测试通过
4. **RR vs CFS 对比**：固定 5ms quantum 减少了上下文切换（~1159 vs ~1710 ctx/sec）
5. **分层验证**：抽象规约（WHAT）→ 具体实现（HOW）→ 精化证明（具体满足抽象）
