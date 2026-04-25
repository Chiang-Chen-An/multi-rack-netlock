#ifndef __CONSTANTS_P4__
#define __CONSTANTS_P4__
typedef bit<48> mac_addr_t;
typedef bit<32> ipv4_addr_t;
typedef bit<24> qp_t;

const bit<16> ETHERTYPE_IPV4 = 0x0800;
const bit<8> IP_PROTO_UDP = 17;
const bit<16> ROCEV2_PORT = 4791;

#endif