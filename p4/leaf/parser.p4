#ifndef __PARSER_P4__
#define __PARSER_P4__

#include <core.p4>
#include <v1model.p4>
#include "../include/constants.p4"
#include "../include/headers.p4"

parser NetlockParser(packet_in packet, out headers_t hdr, inout metadata_t meta, inout standard_metadata_t smeta) {
    state start { 
        packet.extract(hdr.ethernet);
        transition select(hdr.ethernet.ether_type) { 
            ETHERTYPE_IPV4: parse_ipv4;
            default: accept; 
        } 
    }

    state parse_ipv4 {
        packet.extract(hdr.ipv4);
        transition select(hdr.ipv4.protocol) {
            IP_PROTO_UDP: parse_udp;
            default: accept;
        }
    }

    state parse_udp {
        packet.extract(hdr.udp);
        transition select(hdr.udp.dst_port) {
            ROCEV2_PORT: parse_bth;
            default: accept;
        }
    }

    state parse_bth {
        packet.extract(hdr.bth);
        transition parse_deth;
    }

    state parse_deth {
        packet.extract(hdr.deth);
        transition parse_netlock;
    }

    state parse_netlock {
        packet.extract(hdr.netlock);
        transition accept;
    }
}

#endif