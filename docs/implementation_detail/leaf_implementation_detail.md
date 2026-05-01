# Lead switch implementation details

## Ingress.p4

### Step 1

Check if the package is a netlock package, if not, use ipv4 forwarding, else, continue.

### Step 2

Check if the target lock is in the current rack, if so, continue, else:
1. ipv4 forwarding for single rack structure.
2. forward to spine switch in multi-rack structure.

### Step 3

Look up the table for the lock state of this lock id.

```json
{
    "HOT_FREE" = 1,
    "HOT_HELD" = 2,
    "COLD" = 3,
    "DRAINING" = 4,
    "BUFFERING" = 5,
}
```

### Step 4

### Shared lock queue

The leaf switch keeps all queued lock requests in one shared queue register set. Each lock owns a fixed slice of that shared queue:

```text
absolute slot = lock_queue_base[lock_id] + queue_offset
```

For each lock, `lock_queue_head` and `lock_queue_tail` are circular offsets inside that lock's slice, not absolute shared-queue slots. `lock_queue_depth` is the slice size, and `lock_queue_occupancy` tracks how many requests are currently buffered so the switch can distinguish an empty queue from a full queue when head and tail wrap to the same offset.

On enqueue, the switch writes the request at `base + tail`, advances `tail` modulo `depth`, and increments `occupancy`. On release, the switch grants the request at `base + head`, advances `head` modulo `depth`, and decrements `occupancy`. If `occupancy >= depth`, new acquire requests are forwarded to the lock server instead of being buffered in the switch.
