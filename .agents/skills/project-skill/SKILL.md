---
name: project-skill
description: This skill is to instruct the agents how to implement this project, including how to write the p4 code and the controller code.
---

1. The agent should read the specification under `docs/specification.pdf` to understand the requirements of this project.
2. The agent should write the p4 code and python code by following the skill for p4 and controller.
3. The project structure is shown as below:
   ```
    .
    ├── .agents
    │   └── skills
    │       ├── controller-skill
    │       │   └── SKILL.md
    │       ├── p4-skill
    │       │   └── SKILL.md
    │       └── project-skill
    │           └── SKILL.md
    ├── README.md                        # 專案說明、如何 build、如何跑實驗
    ├── LICENSE
    ├── Makefile                         # 頂層 Makefile，統一 build 所有元件
    │
    ├── p4/                              # 所有 P4 程式碼
    │   ├── include/
    │   │   ├── headers.p4               # 自定義封包 header 定義 (Ethernet/IP/UDP/BTH/DETH/LockHeader)
    │   │   └── constants.p4             # 常數定義 (port, opcode, state enum, TTL threshold)
    │   │
    │   ├── leaf/
    │   │   ├── leaf.p4                  # Leaf switch 主程式 (NetLock pipeline)
    │   │   ├── parser.p4                # Leaf parser (區分 lock UD / RDMA RC / 一般封包)
    │   │   ├── lock_ingress.p4          # Lock acquire/release/TTL 邏輯
    │   │   ├── lock_queue.p4            # Shared queue 的 register 操作
    │   │   └── lock_migration.p4        # DRAINING/BUFFERING 狀態處理
    │   │
    │   ├── spine/
    │   │   ├── spine.p4                 # Spine switch 主程式
    │   │   ├── parser.p4                # Spine parser
    │   │   ├── priority_tagger.p4       # 全域優先權標記邏輯
    │   │   └── rate_limiter.p4          # Per-tenant rate limiting
    │   │
    │   └── Makefile                     # 編譯 P4 程式 (BMv2 或 Tofino)
    │
    ├── control_plane/                   # Control plane 程式
    │   ├── controller.py                # 主控制器：polling registers, 計算 loss, 觸發 migration
    │   ├── knapsack.py                  # 長期：最佳化背包問題求解器
    │   ├── migration_manager.py         # 遷移狀態機管理（發送指令、追蹤狀態、cooldown）
    │   ├── stats_collector.py           # 從 switch 讀 register + 從 lock server 收 stats
    │   ├── config.py                    # 系統參數 (TTL, threshold, alpha, cooldown, num_racks)
    │   └── requirements.txt             # Python dependencies
    │
    ├── lock_server/                     # Lock server daemon
    │   ├── include/
    │   │   ├── lock_table.h             # LockEntry 結構、priority queue
    │   │   ├── protocol.h               # Lock header 定義 (跟 P4 的 headers.p4 保持一致)
    │   │   ├── rdma_utils.h             # RDMA UD QP 建立、AH 管理
    │   │   └── spsc_queue.h             # Lock-free single-producer single-consumer queue
    │   │
    │   ├── src/
    │   │   ├── main.c                   # Lock daemon 入口：建立 threads、初始化 RDMA
    │   │   ├── lock_table.c             # Lock acquire/release/TTL 邏輯
    │   │   ├── rdma_datapath.c          # Thread 1: poll CQ, handle requests, send GRANT
    │   │   ├── ctrl_listener.c          # Thread 2: TCP socket, 收 migration 指令
    │   │   └── ttl_watchdog.c           # Thread 3: 定期掃描 TTL
    │   │
    │   ├── Makefile
    │   └── README.md
    │
    ├── client/                          # Client library 和測試程式
    │   ├── include/
    │   │   ├── lock_client.h            # Lock client API: acquire(), release(), init()
    │   │   ├── protocol.h               # 跟 lock_server 共用同一份，用 symlink 或直接 include
    │   │   └── rdma_utils.h
    │   │
    │   ├── src/
    │   │   ├── lock_client.c            # Lock client 實作：send acquire, wait grant, retry
    │   │   └── rdma_setup.c             # RDMA 連線建立、QP 初始化
    │   │
    │   ├── Makefile
    │   └── README.md
    │
    ├── proto/                           # 共用的 header 定義 (single source of truth)
    │   ├── lock_header.h                # C struct，lock_server 和 client 都 include 這個
    │   └── lock_header.p4               # P4 header，leaf 和 spine 都 include 這個
    │
    ├── topology/                        # 網路拓樸定義
    │   ├── mininet/
    │   │   ├── topo.py                  # Mininet Spine-Leaf 拓樸建立腳本
    │   │   ├── run_leaf_only.py         # 架構 1：每個 rack 獨立 NetLock
    │   │   ├── run_spine_only.py        # 架構 2：只在 Spine 上跑 NetLock
    │   │   └── run_hierarchical.py      # 架構 3：Spine + Leaf 階層式
    │   │
    │   └── config/
    │       ├── leaf_runtime.json        # Leaf switch 的 table entries
    │       ├── spine_runtime.json       # Spine switch 的 table entries
    │       └── topology.json            # Rack 數量、每 rack node 數、lock server 指定
    │
    ├── benchmark/                       # Workload 產生與測試
    │   ├── workload_generator/
    │   │   ├── generator.py             # 產生 lock request trace
    │   │   ├── zipfian.py               # Zipfian 分布實作
    │   │   ├── tpcc_trace.py            # 從 TPC-C transaction profile 萃取 lock pattern
    │   │   └── burst_generator.py       # 突發流量產生器
    │   │
    │   ├── workloads/                   # 預先產生好的 workload 檔案
    │   │   ├── uniform_100k.csv
    │   │   ├── zipfian_100k.csv
    │   │   └── tpcc_neworder_50k.csv
    │   │
    │   ├── runner/
    │   │   ├── run_benchmark.py         # 自動化跑實驗：啟動拓樸 → 跑 workload → 收結果
    │   │   └── run_all_experiments.sh   # 一鍵跑所有實驗組合
    │   │
    │   └── README.md                    # 說明每個 workload 的參數和用途
    │
    ├── evaluation/                      # 實驗結果與畫圖
    │   ├── results/                     # 原始實驗數據 (csv/json)
    │   │   ├── throughput/
    │   │   ├── latency/
    │   │   ├── deadlock/
    │   │   ├── migration/
    │   │   └── fairness/
    │   │
    │   ├── plots/
    │   │   ├── plot_throughput.py        # 畫 throughput vs contention
    │   │   ├── plot_latency_cdf.py       # 畫 tail latency CDF
    │   │   ├── plot_deadlock_rate.py     # 畫 deadlock rate
    │   │   ├── plot_migration_react.py   # 畫 migration 反應時間
    │   │   ├── plot_fairness.py          # 畫 multi-tenant fairness
    │   │   └── plot_utilization.py       # 畫 switch memory utilization
    │   │
    │   ├── figures/                      # 產出的圖 (PDF/SVG)
    │   └── Makefile                      # make plots 一鍵產所有圖
    │
    ├── docs/                             # 設計文件與圖
    │   ├── diagrams/                     # draw.io 原始檔
    │   │
    │   ├── sequences/                    # mermaid 原始檔
    │   │   ├── migration_to_server.mmd
    │   │   └── migration_to_switch.mmd
    │   │
    │   └── Specification_ .pdf
    │
    ├── paper/                            # 論文 (如果用 LaTeX)
    │   ├── main.tex
    │   ├── sections/
    │   ├── figures/                      # 從 docs/ 和 evaluation/ 複製過來的最終版圖
    │   ├── references.bib
    │   └── Makefile
    │
    ├── scripts/                          # 雜項腳本
    │   ├── setup_softroce.sh            # 安裝和設定 SoftRoCE
    │   ├── disable_icrc_check.sh        # 修改 SoftRoCE kernel module 關掉 ICRC
    │   ├── install_deps.sh              # 安裝所有 dependencies
    │   └── clean_all.sh                 # 清理所有 build artifacts
    │
    ├── tests/                            # 單元測試
    │   ├── test_lock_table.c            # 測試 lock server 的 lock_table 邏輯
    │   ├── test_knapsack.py             # 測試 knapsack solver
    │   ├── test_migration_state.py      # 測試 migration 狀態機轉移
    │   └── p4/
    │       ├── test_leaf_acquire.py     # 用 PTF 測試 P4 的 acquire 邏輯
    │       ├── test_leaf_release.py
    │       └── test_spine_priority.py
    │
    └── .gitignore
   ```