#ifndef __INGRESS_P4__
#define __INGRESS_P4__

#include <core.p4>
#include <v1model.p4>
#include "../include/headers.p4"
#include "../include/constants.p4"
#include "register.p4"

control NetlockIngress(inout headers_t hdr, inout metadata_t meta, inout standard_metadata_t smeta) {
    action drop() {
        mark_to_drop(smeta);
    }
    
    action send_to_port(bit<9> port) {
        smeta.egress_spec = port;
    }

    action forward_to_lock_server() {
        smeta.egress_spec = port_to_lock_server;
    }

    action mark_lock_state(bit<3> lock_state) {
        meta.lock_state = lock_state;
    }

    action read_lock_information() {
        lock_queue_base.read(meta.queue_base, hdr.netlock.lock_id);
        lock_queue_depth.read(meta.queue_depth, hdr.netlock.lock_id);
        lock_queue_head.read(meta.queue_head, hdr.netlock.lock_id);
        lock_queue_tail.read(meta.queue_tail, hdr.netlock.lock_id);
        lock_queue_occupancy.read(meta.queue_occupancy, hdr.netlock.lock_id);
        lock_holder.read(meta.current_lock_holder_id, hdr.netlock.lock_id);
    }

    action acquire_lock() {
        mac_addr_t tmp_mac    = hdr.ethernet.src_addr;
        hdr.ethernet.src_addr = hdr.ethernet.dst_addr;
        hdr.ethernet.dst_addr = tmp_mac;

        ipv4_addr_t tmp_ip = hdr.ipv4.src_addr;
        hdr.ipv4.src_addr  = hdr.ipv4.dst_addr;
        hdr.ipv4.dst_addr  = tmp_ip;

        bit<24> tmp_qp     = hdr.bth.dest_qp;
        hdr.bth.dest_qp    = hdr.deth.src_qp;
        hdr.deth.src_qp    = tmp_qp;

        hdr.netlock.op_type = GRANT;

        smeta.egress_spec = smeta.ingress_port;
        // update lock holder
        lock_holder.write(hdr.netlock.lock_id, hdr.netlock.tenant_id);

        // TODO: update lock state to HOT_HELD
    }

    action enqueue_lock_request() {
        meta.queue_slot = (bit<32>)(meta.queue_base + meta.queue_tail);

        // update lock queue info
        lock_queue_tail.write(hdr.netlock.lock_id, meta.next_queue_tail);
        lock_queue_occupancy.write(hdr.netlock.lock_id, meta.queue_occupancy + 1);

        // store requester tenant_id
        queue_tenant_id.write(meta.queue_slot, hdr.netlock.tenant_id);
        queue_transaction_id.write(meta.queue_slot, hdr.netlock.transaction_id);
        queue_priority.write(meta.queue_slot, hdr.netlock.priority);
        queue_src_mac.write(meta.queue_slot, hdr.ethernet.src_addr);
        queue_src_ip.write(meta.queue_slot, hdr.ipv4.src_addr);
        queue_src_qp.write(meta.queue_slot, hdr.deth.src_qp);
        queue_ingress_port.write(meta.queue_slot, smeta.ingress_port);

        mark_to_drop(smeta);
    }

    action release_lock() {
        lock_holder.write(hdr.netlock.lock_id, 0);
        mark_to_drop(smeta);
    }

    action grant_next_waiter() {
        bit<16> next_tenant_id;
        bit<32> next_transaction_id;
        bit<32> next_priority;
        mac_addr_t next_src_mac;
        ipv4_addr_t next_src_ip;
        bit<24> next_src_qp;
        bit<9> next_ingress_port;
        mac_addr_t grant_src_mac = hdr.ethernet.dst_addr;
        ipv4_addr_t grant_src_ip = hdr.ipv4.dst_addr;
        bit<24> grant_src_qp = hdr.bth.dest_qp;

        meta.queue_slot = (bit<32>)(meta.queue_base + meta.queue_head);

        queue_tenant_id.read(next_tenant_id, meta.queue_slot);
        queue_transaction_id.read(next_transaction_id, meta.queue_slot);
        queue_priority.read(next_priority, meta.queue_slot);
        queue_src_mac.read(next_src_mac, meta.queue_slot);
        queue_src_ip.read(next_src_ip, meta.queue_slot);
        queue_src_qp.read(next_src_qp, meta.queue_slot);
        queue_ingress_port.read(next_ingress_port, meta.queue_slot);

        lock_holder.write(hdr.netlock.lock_id, next_tenant_id);
        lock_queue_head.write(hdr.netlock.lock_id, meta.next_queue_head);
        lock_queue_occupancy.write(hdr.netlock.lock_id, meta.queue_occupancy - 1);

        hdr.ethernet.src_addr = grant_src_mac;
        hdr.ethernet.dst_addr = next_src_mac;
        hdr.ipv4.src_addr = grant_src_ip;
        hdr.ipv4.dst_addr = next_src_ip;
        hdr.bth.dest_qp = next_src_qp;
        hdr.deth.src_qp = grant_src_qp;
        hdr.netlock.tenant_id = next_tenant_id;
        hdr.netlock.transaction_id = next_transaction_id;
        hdr.netlock.priority = next_priority;
        hdr.netlock.op_type = GRANT;
        smeta.egress_spec = next_ingress_port;
    }

    table ipv4_forward {
        key = {
            hdr.ipv4.dst_addr: lpm;
        }
        actions = {
            send_to_port;
            drop;
            NoAction;
        }
        size = 1024;
        default_action= NoAction();
    }

    table lock_state {
        key = {
            hdr.netlock.lock_id: exact;
        }
        actions = {
            mark_lock_state;
            drop;
            NoAction;
        }
        size = 4096;
        default_action = NoAction();
    }

    apply {
        meta.use_ipv4_forward = 0;

        if (!hdr.netlock.isValid()) {
            meta.use_ipv4_forward = 1;
        }
        else {
            // check if the lock is in the current rack
            // TODO: How to map a key to the lock id in a kv storage system?
            if ((bit<4>)(hdr.netlock.lock_id & RACK_ID_MASK) != current_rack_id) {
                // TODO: forward to spine switch when multi-rack
                meta.use_ipv4_forward = 1;
            }
        }

        if (meta.use_ipv4_forward == 1) {
            ipv4_forward.apply();
            return;
        }

        read_lock_information();
        meta.lock_state = 0;
        lock_state.apply();

        if (hdr.netlock.op_type == ACQUIRED) {
            if (meta.lock_state == HOT_FREE) {
                if (meta.queue_depth == 0) {
                    forward_to_lock_server();
                    return;
                }
                acquire_lock();
                return;
            }
            else if (meta.lock_state == HOT_HELD) {
                if ((meta.queue_depth == 0) || (meta.queue_occupancy >= meta.queue_depth)) {
                    // queue full, forward to lock_server;
                    forward_to_lock_server();
                    return;
                }
                // TODO: if the lock server is not empty, handle the request from lock server first.
                meta.next_queue_tail = meta.queue_tail + 1;
                if (meta.next_queue_tail >= meta.queue_depth) {
                    meta.next_queue_tail = 0;
                }
                enqueue_lock_request();
            }
            else if (meta.lock_state == COLD) {
                forward_to_lock_server();
                return;
            }
            else if (meta.lock_state == BUFFERING) {
                if ((meta.queue_depth == 0) || (meta.queue_occupancy >= meta.queue_depth)) {
                    forward_to_lock_server();
                    return;
                }
                else {
                    meta.next_queue_tail = meta.queue_tail + 1;
                    if (meta.next_queue_tail >= meta.queue_depth) {
                        meta.next_queue_tail = 0;
                    }
                    enqueue_lock_request();
                }
            }
            else if (meta.lock_state == DRAINING) {
                forward_to_lock_server();
            }
            else {
                drop();
            }
        }
        else if (hdr.netlock.op_type == RELEASE) {
            if (meta.lock_state == HOT_FREE) {
                drop();
            }
            else if (meta.lock_state == HOT_HELD) {
                if (meta.current_lock_holder_id != hdr.netlock.tenant_id) {
                    drop();
                    return;
                }
                if (meta.queue_occupancy == 0) {
                    release_lock();
                    return;
                }
                else {
                    meta.next_queue_head = meta.queue_head + 1;
                    if (meta.next_queue_head >= meta.queue_depth) {
                        meta.next_queue_head = 0;
                    }
                    grant_next_waiter();
                }
            }
            else if (meta.lock_state == COLD) {
                forward_to_lock_server();
                return;
            }
            else if (meta.lock_state == BUFFERING) {
                forward_to_lock_server();
            }
            else if (meta.lock_state == DRAINING) {
                if (meta.current_lock_holder_id != hdr.netlock.tenant_id) {
                    drop();
                    return;
                }
                if (meta.queue_occupancy == 0) {
                    release_lock();
                    return;
                }
                else {
                    meta.next_queue_head = meta.queue_head + 1;
                    if (meta.next_queue_head >= meta.queue_depth) {
                        meta.next_queue_head = 0;
                    }
                    grant_next_waiter();
                }
                // TODO: check if queue is empty, if so, notify server
            }
            else {
                drop();
            }
        }
        else {
            drop();
        }
    }
}

#endif
