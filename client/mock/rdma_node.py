#!/usr/bin/env python3

from scapy.all import *
from scapy.layers.inet import UDP
from scapy.layers.inet import IP
from scapy.layers.l2 import Ether
from scapy.packet import Packet, bind_layers
from scapy.fields import (
    ByteField,
    BitField,
    ShortField,
    IntField,
)
import argparse

ROCEV2_PORT = 4791

ACQUIRED = 1
RELEASE = 2
GRANT = 3


class BTH(Packet):
    name = "ROCEv2_BTH"
    fields_desc = [
        ByteField("opcode", 0x64),
        BitField("solicited_event", 0, 1),
        BitField("mig_req", 0, 1),
        BitField("pad_count", 0, 2),
        BitField("transport_version", 0, 4),
        ShortField("pkey", 0xFFFF),
        ByteField("reserved0", 0),
        BitField("dest_qp", 0x111111, 24),
        BitField("ack_req", 0, 1),
        BitField("reserved1", 0, 7),
        BitField("psn", 0, 24),
    ]


class DETH(Packet):
    name = "DETH"
    fields_desc = [
        BitField("q_key", 0x11111111, 32),
        ByteField("reserved", 0),
        BitField("src_qp", 0x222222, 24),
    ]


class NETLOCK(Packet):
    name = "NETLOCK"
    fields_desc = [
        ByteField("op_type", ACQUIRED),
        ByteField("flag", 0),
        ShortField("tenant_id", 1),
        IntField("lock_id", 1),
        IntField("transaction_id", 1),
        IntField("priority", 0),
        IntField("timestamp", 0),
    ]


bind_layers(UDP, BTH, dport=ROCEV2_PORT)
bind_layers(BTH, DETH)
bind_layers(DETH, NETLOCK)


def build_acquired_packet(
    src_mac,
    dst_mac,
    src_ip,
    dst_ip,
    lock_id,
    tenant_id,
    transaction_id,
    dest_qp=0x111111,
    src_qp=0x222222,
):
    return (
        Ether(src=src_mac, dst=dst_mac)
        / IP(src=src_ip, dst=dst_ip)
        / UDP(sport=12345, dport=ROCEV2_PORT)
        / BTH(dest_qp=dest_qp)
        / DETH(src_qp=src_qp)
        / NETLOCK(
            op_type=ACQUIRED,
            lock_id=lock_id,
            tenant_id=tenant_id,
            transaction_id=transaction_id,
        )
    )


def build_release_packet(
    src_mac,
    dst_mac,
    src_ip,
    dst_ip,
    lock_id,
    tenant_id,
    transaction_id,
    dest_qp=0x111111,
    src_qp=0x222222,
):
    return (
        Ether(src=src_mac, dst=dst_mac)
        / IP(src=src_ip, dst=dst_ip)
        / UDP(sport=12345, dport=ROCEV2_PORT)
        / BTH(dest_qp=dest_qp)
        / DETH(src_qp=src_qp)
        / NETLOCK(
            op_type=RELEASE,
            lock_id=lock_id,
            tenant_id=tenant_id,
            transaction_id=transaction_id,
        )
    )


def handle_packet(pkt):
    if pkt.haslayer(NETLOCK):
        nl = pkt[NETLOCK]
        print(
            f"NetLock packet: op={nl.op_type} "
            f"tenant={nl.tenant_id} lock={nl.lock_id} tx={nl.transaction_id}"
        )
        pkt.show()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(epilog="Example: ./rdma_node.py -i ens33 -v")

    parser.add_argument(
        "-i", "--iface", default="ens33", help="Interface to send packet"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Show more detailed"
    )
    args = parser.parse_args()

    iface = args.iface
    verbose = args.verbose

    pkt = build_acquired_packet(
        dst_mac="02:00:00:00:00:02",
        src_mac="02:00:00:00:00:01",
        dst_ip="10.0.0.2",
        src_ip="10.0.0.1",
        lock_id=1,
        tenant_id=1,
        transaction_id=100,
    )

    pkt.show2()
    sendp(pkt, iface=iface, verbose=verbose)

    sniff(
        iface=iface,
        filter="udp port 4791",
        prn=handle_packet,
        store=False,
        timeout=5,
    )
