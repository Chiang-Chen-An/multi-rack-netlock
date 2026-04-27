#ifndef __UTILS_P4__
#define __UTILS_P4__

#include <core.p4>
#include <v1model.p4>
#include "../include/constants.p4"
#include "../include/headers.p4"

control NetlockVerifyChecksum(inout headers_t hdr, inout metadata_t meta) {
    apply { } 
}

control NetlockEgress(inout headers_t hdr, inout metadata_t meta, inout standard_metadata_t smeta) {
    apply { }
}

control NetlockComputeChecksum(inout headers_t hdr, inout metadata_t meta) {
    apply { 
        update_checksum(
            hdr.ipv4.isValid(),
            { 
                hdr.ipv4.version,
                hdr.ipv4.ihl,
                hdr.ipv4.diffserv,
                hdr.ipv4.total_len,
                hdr.ipv4.identification,
                hdr.ipv4.flags,
                hdr.ipv4.frag_offset,
                hdr.ipv4.ttl,
                hdr.ipv4.protocol,
                hdr.ipv4.src_addr,
                hdr.ipv4.dst_addr
            }, 
            hdr.ipv4.hdr_checksum,
            HashAlgorithm.csum16
        ); 
    }
}

control NetlockDeparser(packet_out packet, in headers_t hdr) {
    apply { 
        packet.emit(hdr.ethernet);
        packet.emit(hdr.ipv4);
        packet.emit(hdr.udp);
        packet.emit(hdr.bth);
        packet.emit(hdr.deth);
        packet.emit(hdr.netlock);
    }
}

#endif