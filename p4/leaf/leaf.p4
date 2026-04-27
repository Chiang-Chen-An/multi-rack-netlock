#ifndef __LEAF_P4__
#define __LEAF_P4__

#include <core.p4>
#include <v1model.p4>
#include "ingress.p4"
#include "utils.p4"
#include "parser.p4"

V1Switch(NetlockParser(), NetlockVerifyChecksum(), NetlockIngress(), NetlockEgress(), NetlockComputeChecksum(), NetlockDeparser()) main;

#endif