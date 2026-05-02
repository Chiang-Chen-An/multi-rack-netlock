# Unit Test Plan

This document explains the unit tests added for the current project progress.
The tests focus on behavior that exists today and on static contracts that the
current P4 and Python code already depend on.

## Test Command

Run all default tests with:

```sh
make test
```

or directly:

```sh
python3 -m unittest discover -s tests
```

The default test suite does not require BMv2, Docker, or `p4runtime-sh`.
P4Runtime is mocked in Python tests, and P4 tests inspect the current source
contract statically.

To also run the optional P4 compiler smoke test:

```sh
RUN_P4_COMPILE_TESTS=1 python3 -m unittest tests.test_p4_static.P4CompileSmokeTests
```

That optional test requires Docker and the `p4lang/p4c` image used by the
project `Makefile`.

## Python Control-Plane Tests

File: `tests/test_control_plane.py`

### Configuration Tests

Goal: verify that the controller configuration layer accepts valid current
configuration and rejects unsafe configuration.

Covered behavior:

1. `load_controller_config()` returns the default single-switch configuration.
2. `PipelineConfig.validate()` accepts existing P4Info and BMv2 artifact paths.
3. `ControllerConfig.validate()` rejects duplicate `(device_id, grpc_addr)`
   switch connections.
4. `SwitchConfig.from_dict()` rejects malformed P4Runtime election IDs.

These tests protect the startup path in `control_plane/controller.py` and
`control_plane/config.py`.

### Knapsack Tests

Goal: verify the current memory-placement helper chooses switch-resident locks
within a queue-slot budget.

Covered behavior:

1. The selected lock set maximizes value under the slot budget.
2. Candidates with non-positive slot requirements are ignored.
3. An empty or invalid budget produces no selected locks.

These tests protect `control_plane/knapsack.py`, which is the current basis for
future hot-lock placement.

### Migration Manager Tests

Goal: verify that migration plan construction matches the documented lock-state
transition model.

Covered behavior:

1. Switch-to-server migration creates a `HOT_HELD -> DRAINING` plan.
2. Server-to-switch migration creates a `COLD -> BUFFERING` plan and carries the
   assigned queue slice.

These tests protect `control_plane/migration_manager.py`.

### P4Runtime Switch Tests

Goal: verify the implemented P4Runtime wrapper lifecycle without requiring a
real switch or the real `p4runtime-sh` package.

Covered behavior:

1. `connect()` validates artifacts, builds a forwarding pipeline config, calls
   shell setup, and marks the switch connected.
2. `table_entry()` and `register_entry()` delegate to the connected shell.
3. `disconnect()` calls shell teardown and clears connection state.

These tests protect `control_plane/p4runtime_switch.py` while keeping the test
environment lightweight.

## P4 Static Contract Tests

File: `tests/test_p4_static.py`

The current repository does not include a PTF or BMv2 runtime test harness yet,
so the default P4 tests are static unit checks. They verify contracts that the
controller and data plane must keep synchronized.

### Lock-State Constants

Goal: ensure the P4 constants match the Python `LockState` enum values.

Covered values:

1. `HOT_FREE = 1`
2. `HOT_HELD = 2`
3. `COLD = 3`
4. `DRAINING = 4`
5. `BUFFERING = 5`

### NetLock Header and Metadata

Goal: ensure the P4 header and metadata still expose the fields needed by the
current controller plan.

Covered fields include `op_type`, `tenant_id`, `lock_id`, `transaction_id`,
`priority`, `timestamp`, `queue_base`, `queue_head`, `queue_tail`,
`queue_depth`, `queue_occupancy`, and `current_lock_holder_id`.

### Register Layout

Goal: ensure the queue metadata and queued-request payload registers remain
available with the expected dimensions.

The tests check per-lock registers sized by `TOTAL_LOCKS_NUM` and shared queue
payload registers sized by `TOTAL_SLOTS`.

### Parser Chain

Goal: ensure the parser still extracts the expected RoCEv2 NetLock chain:

```text
Ethernet -> IPv4 -> UDP -> BTH -> DETH -> NetLock
```

The test also checks that UDP destination port `ROCEV2_PORT` transitions to BTH
parsing.

### Ingress Fast Path Contract

Goal: ensure the current ingress source still contains the key lock-state fast
path branches and queue operations.

Covered behavior:

1. `lock_state` table matches on `hdr.netlock.lock_id`.
2. Queue metadata is read before lock-state processing.
3. All current lock states appear in ingress branch logic.
4. Enqueue, dequeue, lock-server forwarding, and grant-next-waiter operations
   remain present.

## Optional P4 Compile Smoke Test

The optional compiler smoke test runs `make compile` only when
`RUN_P4_COMPILE_TESTS=1` is set. It is skipped by default because it requires
Docker and may need to download the `p4lang/p4c` image.

This test is useful before larger P4 changes because it checks the whole leaf P4
program against `p4c-bm2-ss`.

## Future Test Work

The next useful tests are:

1. Register read/write unit tests once `StatsCollector.read_lock_queue_stats`
   is implemented.
2. Lock-state table programming tests once controller write helpers exist.
3. Migration state-machine tests with timeout and retry behavior.
4. BMv2 or PTF packet tests for acquire, release, queue-full forwarding,
   `DRAINING`, and `BUFFERING`.
5. End-to-end tests that run a small topology, issue lock requests, and compare
   grants, queue occupancy, and lock-server forwarding behavior.
