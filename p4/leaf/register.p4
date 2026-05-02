#ifndef __REGISTER_P4__
#define __REGISTER_P4__
#include "../include/constants.p4"

register<bit<16>>(TOTAL_SLOTS) queue_tenant_id;
register<bit<32>>(TOTAL_SLOTS) queue_transaction_id;
register<bit<32>>(TOTAL_SLOTS) queue_priority;
register<mac_addr_t>(TOTAL_SLOTS) queue_src_mac;
register<ipv4_addr_t>(TOTAL_SLOTS) queue_src_ip;
register<bit<24>>(TOTAL_SLOTS) queue_src_qp;
register<bit<9>>(TOTAL_SLOTS) queue_ingress_port;

// the tenant_id of the lock_holder
register<bit<16>>(TOTAL_LOCKS_NUM) lock_holder;
register<bit<13>>(TOTAL_LOCKS_NUM) lock_queue_base;       // first shared slot owned by this lock
register<bit<13>>(TOTAL_LOCKS_NUM) lock_queue_head;       // offset of next slot to dequeue
register<bit<13>>(TOTAL_LOCKS_NUM) lock_queue_tail;       // offset of next slot to enqueue
register<bit<13>>(TOTAL_LOCKS_NUM) lock_queue_depth;      // number of slots owned by this lock
register<bit<13>>(TOTAL_LOCKS_NUM) lock_queue_occupancy;  // queued requests in this lock's slice

// statistic
register<bit<32>>(TOTAL_LOCKS_NUM) lock_acquire_count;
register<bit<32>>(TOTAL_LOCKS_NUM) lock_miss_count;
register<bit<32>>(TOTAL_LOCKS_NUM) lock_overflow_count;

#endif
