#ifndef __HEADERS_P4__
#define __HEADERS_P4__
#include <core.p4>
#include <v1model.p4>
#include "constants.p4"

header ethernet_t { 
    mac_addr_t dst_addr;
    mac_addr_t src_addr;
    bit<16> ether_type;
}

header ipv4_t {
    bit<4> version;
    bit<4> ihl;
    bit<8> diffserv;
    bit<16> total_len;
    bit<16> identification;
    bit<3> flags;
    bit<13> frag_offset;
    bit<8> ttl;
    bit<8> protocol;
    bit<16> hdr_checksum;
    ipv4_addr_t src_addr;
    ipv4_addr_t dst_addr;
}

header udp_t { 
    bit<16> src_port;
    bit<16> dst_port;
    bit<16> length;
    bit<16> checksum;
}

// RoCEV2 Base Transport Header
// https://zhuanlan.zhihu.com/p/657265815
header bth_t {
    bit<8> opcode;
    bit<1> solicited_event;
    bit<1> mig_req;
    bit<2> pad_count;
    bit<4> transport_version;
    bit<16> pkey;
    bit<8> reserved0;
    qp_t dest_qp;
    bit<1> ack_req;
    bit<7> reserved1;
    bit<24> psn;
}

// Datagram extended header, UD only
header deth_t {
    bit<32> q_key;
    bit<8> reserved;
    qp_t src_qp;
}

// netlock header
header netlock_t {
    bit<8> op_type;
    bit<8> flag;
    bit<16> tenant_id;
    bit<32> lock_id;
    bit<32> transaction_id;
    bit<32> priority;
    bit<32> timestamp;
}

struct headers_t {
    ethernet_t ethernet;
    ipv4_t ipv4;
    udp_t udp;
    bth_t bth;
    deth_t deth;
    netlock_t netlock;
}

struct metadata_t {
    bit<3> lock_state;
    bit<1> use_ipv4_forward;
    bit<13> queue_base;
    bit<13> queue_head;
    bit<13> queue_tail;
    bit<13> queue_depth;
    bit<13> queue_occupancy;
    bit<16> current_lock_holder_id;
    bit<13> next_queue_head;
    bit<13> next_queue_tail;
    bit<32> queue_slot;
}

#endif
