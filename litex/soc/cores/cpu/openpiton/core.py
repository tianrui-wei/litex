#
# This file is part of LiteX.
#
# Copyright (c) 2021 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

from litex import get_data_mod
import os

from migen import *

from litex.soc.interconnect import axi, wishbone
from litex.soc.cores.cpu import CPU, CPU_GCC_TRIPLE_RISCV64

# Variants -----------------------------------------------------------------------------------------

# TODO: add different ISAs to cpu variants
CPU_VARIANTS = ["standard"]

# FemtoRV ------------------------------------------------------------------------------------------


class OpenPitonRV64(CPU):
    name = "openpiton"
    human_name = "OpenPiton RISC-V 64Bit SoC"
    variants = CPU_VARIANTS
    data_width = 64
    addr_width = 32
    endianness = "little"
    gcc_triple = CPU_GCC_TRIPLE_RISCV64
    linker_output_format = "elf64-littleriscv"
    nop = "nop"
    # FIXME: is this correct?
    io_regions = {0x00000000: 0x80000000}  # Origin, Length.

    # GCC Flags.
    @property
    def gcc_flags(self):
        flags = "-march=rv64imc "
        flags += "-mabi=lp64 "
        flags += "-D__openpitonrv64__ "
        return flags

    @property
    def mem_map(self):
        # Rocket reserves the first 256Mbytes for internal use, so we must change default mem_map.
        return {
            "csr"      : 0x12000000,
            "main_ram" : 0x80000000,
        }


    def __init__(self, platform, variant="standard"):
        self.platform = platform
        self.variant = variant

        self.reset = Signal()
        self.interrupt = Signal(32)

        self.mem_axi = mem_axi = axi.AXIInterface(
            data_width=self.data_width, address_width=self.addr_width, id_width=4)

        self.mem_wb = mem_wb = wishbone.Interface(data_width=self.data_width, adr_width=32-log2_int(self.data_width//8))
        
        # Peripheral buses (Connected to main SoC's bus).
        self.periph_buses = [mem_wb]
        # Memory buses (Connected directly to LiteDRAM).
        self.memory_buses = []

        # OpenPiton RISCV 64 Instance.
        # -----------------
        self.cpu_params = dict(
            # Parameters.

            # Clk / Rst.
            i_sys_clk=ClockSignal("sys"),
            i_sys_rst_n=~ResetSignal("sys"),  # Active Low.

            i_mc_clk=ClockSignal("sys"),

            o_m_axi_awid=mem_axi.aw.id,
            o_m_axi_awaddr=mem_axi.aw.addr,
            o_m_axi_awlen=mem_axi.aw.len,
            o_m_axi_awsize=mem_axi.aw.size,
            o_m_axi_awburst=mem_axi.aw.burst,
            o_m_axi_awlock=mem_axi.aw.lock,
            o_m_axi_awcache=mem_axi.aw.cache,
            o_m_axi_awprot=mem_axi.aw.prot,
            o_m_axi_awqos=mem_axi.aw.qos,
            # o_m_axi_awregion=mem_axi.aw.region,
            #o_m_axi_awuser=mem_axi.aw.user,
            o_m_axi_awvalid=mem_axi.aw.valid,
            i_m_axi_awready=mem_axi.aw.ready,

            o_m_axi_wid=mem_axi.w.id,
            o_m_axi_wdata=mem_axi.w.data,
            o_m_axi_wstrb=mem_axi.w.strb,
            o_m_axi_wlast=mem_axi.w.last,
            #o_m_axi_wuser=mem_axi.w.user,
            o_m_axi_wvalid=mem_axi.w.valid,
            i_m_axi_wready=mem_axi.w.ready,

            o_m_axi_arid=mem_axi.ar.id,
            o_m_axi_araddr=mem_axi.ar.addr,
            o_m_axi_arlen=mem_axi.ar.len,
            o_m_axi_arsize=mem_axi.ar.size,
            o_m_axi_arburst=mem_axi.ar.burst,
            o_m_axi_arlock=mem_axi.ar.lock,
            o_m_axi_arcache=mem_axi.ar.cache,
            o_m_axi_arprot=mem_axi.ar.prot,
            o_m_axi_arqos=mem_axi.ar.qos,
#            o_m_axi_arregion=mem_axi.ar.region,
            #o_m_axi_aruser=mem_axi.ar.user,
            o_m_axi_arvalid=mem_axi.ar.valid,
            i_m_axi_arready=mem_axi.ar.ready,

            i_m_axi_rid=mem_axi.r.id,
            i_m_axi_rdata=mem_axi.r.data,
            i_m_axi_rresp=mem_axi.r.resp,
            i_m_axi_rlast=mem_axi.r.last,
            #i_m_axi_ruser=mem_axi.r.user,
            i_m_axi_rvalid=mem_axi.r.valid,
            o_m_axi_rready=mem_axi.r.ready,

            i_m_axi_bid=mem_axi.b.id,
            i_m_axi_bresp=mem_axi.b.resp,
            #i_m_axi_buser=mem_axi.b.user,
            i_m_axi_bvalid=mem_axi.b.valid,
            o_m_axi_bready=mem_axi.b.ready,

            # TODO: add ddr ready
            i_ddr_ready=1,
            i_ext_irq=self.interrupt,
            i_ext_irq_trigger=0,

        )

        # Adapt axi to wishbone
        # ----------------------------------

        bus_a2w = ResetInserter()(axi.AXI2Wishbone(mem_axi, mem_wb, base_address=0))
        # Note: Must be reset with the CPU.
        self.comb += bus_a2w.reset.eq(ResetSignal() | self.reset)
        self.submodules += bus_a2w

        # Add Verilog sources.
        # --------------------
        self.add_sources(platform)

    def set_reset_address(self, reset_address):
        assert not hasattr(self, "reset_address")
        self.reset_address = reset_address
        #self.cpu_params.update(p_RESET_ADDR=Constant(reset_address, 32))

    @staticmethod
    def add_sources(platform):
        if not os.path.exists("generated.v"):
            os.system("cp ~/research/openpiton/build/generated.v .")
        platform.add_source("generated.v")

    def do_finalize(self):
        assert hasattr(self, "reset_address")
        self.specials += Instance("OpenPitonRV64", **self.cpu_params)
