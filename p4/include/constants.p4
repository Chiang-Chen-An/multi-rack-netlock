#ifndef __CONSTANTS_P4__
#define __CONSTANTS_P4__
typedef bit<48> mac_addr_t;
typedef bit<32> ipv4_addr_t;
typedef bit<24> qp_t;

const bit<16> ETHERTYPE_IPV4 = 0x0800;
const bit<8> IP_PROTO_UDP = 17;
const bit<16> ROCEV2_PORT = 4791;

// lock state
const bit<3> HOT_FREE = 1;
const bit<3> HOT_HELD = 2;
const bit<3> COLD = 3;
const bit<3> DRAINING = 4;
const bit<3> BUFFERING = 5;

// netlock op_type
const bit<8> ACQUIRED = 1;
const bit<8> RELEASE = 2;
const bit<8> GRANT = 3;

const bit<32> TOTAL_SLOTS = 4096;
const bit<32> TOTAL_LOCKS_NUM = 4096;
const bit<4> TOTAL_RACKS_NUM = 8;
// TOTAL_RACKS_NUM is a power of two, so use a mask instead of modulo for target compatibility.
const bit<32> RACK_ID_MASK = ((bit<32>)TOTAL_RACKS_NUM) - 1;

// NOTE: change this to the cuurent rack_id
const bit<4> current_rack_id = 1;
// NOTE: change this to the real port to the server in each rack.
const bit<9> port_to_lock_server = 1;

#endif
