#!/usr/bin/env bash
# Wave 44 - the line numbers the report cites, taken mechanically (read-only greps).
# Theirs: the clones under /home/cyrux/hakios/refs at the ledger's commits. Ours: hakios.adreno.c, read only.
set -u
R=/home/cyrux/hakios/refs
K=/home/cyrux/hakios/kernel/drivers/gpu/hakios.adreno.c
V=$R/kernel_oneplus_sm8475/drivers/gpu/msm
echo "##### ours: $(sha256sum $K | cut -c1-64) ($(wc -l < $K) lines)"
echo "--- negative checks: registers the references write and this file never names (a count of 0 is the finding)"
for p in 'GBIF_GX' '10240e0' 'RB_CMP_DBG' 'CP_BV_' 'CP_LPAC_APRIV' 'CP_LPAC_CHICKEN' 'CMDQ_CONFIG *,' 'CP_PROTECT_CNTL' 'CP_PROTECT_REG' 'APERTURE' 'INT_0_MASK' 'CP_WAIT_TIMESTAMP' 'CP_SET_THREAD' 'RPTR_ADDR' 'GMEM_RANGE' 'FENCE_STATUS_WRITEDROPPED'; do
  printf '%-28s %s\n' "$p" "$(grep -c -- "$p" $K)"
done
echo "--- ours: anchors"
grep -n 'static bool$' $K >/dev/null
grep -n '^step_gmu_firmware\|^step_gmu_start\|^step_gmu_queues\|^step_core_power\|^step_core_start\|^step_core_commands\|^step_frame\|^hakios_gpu_done\|^hakios_gpu_submit\|^hakios_gpu_parameter\|^ring_fence_event\|^ring_command\|^ring_register\|^ring_send\|^ring_run\|^hfi_send' $K
grep -n 'define CP_RB_CNTL_VALUE\|define FENCE_EVENT\|define CONCURRENT_BINNING\|ring(CP_THREAD_CONTROL_CONCURRENT_BIN_DISABLE)\|ring_command(CP_ME_INIT\|ring(0x0000082f)\|"uche_cache_ways"\|"rbbm_gbif_client_qos_cntl"\|"cp_apriv_cntl"\|"cp_chicken_dbg"\|"gras_nc_mode_cntl"\|"rbbm_interface_hang_int_cntl"\|wr(gpu.base + CP_RB_WPTR\|hfi->queues = \|hfi->words = \|UBWC_SWIZZLE\|MACROTILE_MODE\|last_step = 21\|ring_fence_event(EVENT\|ring(EVENT_INVALIDATE' $K
echo "##### theirs: Adreno740 $(runuser -u cyrux -- git -C $R/UniXNU-Adreno740 rev-parse --short=8 HEAD)"
cd $R/UniXNU-Adreno740
grep -n 'RingFenceOpcode = \|RingFenceEvent = \|RingFenceEnable = \|RingFenceIrq = \|RingBvFenceOffset = \|RingCacheFlush7 = \|RingFramedFenceWords = \|RingFenceWords = ' NativeAdrenoRing.cpp
grep -n '^IOReturn NativeAdrenoRing::\(writeWptr\|readRptr\|emitPrologue\|emitFence\|restart\|fenceValue\|submitWords\|bvProgressState\|progressState\|kick\|drainBus\|stallState\|program\)\|^IOReturn NativeAdrenoRing::emitFramedFence(uint32_t at,uint32_t seqno,uint32_t \*end,bool yield)\|^NativeAdrenoRingFence NativeAdrenoRing::wait' NativeAdrenoRing.cpp
grep -n 'const uint32_t bvWrite\|const uint32_t bvWait\|const uint32_t fence\[4\]\|words\[3\]=RingFenceEvent\|if(value>seqno_)\|rptr>=ring_bytes_/4' NativeAdrenoRing.cpp
grep -n 'CpConcurrentBinDisable = \|words\[1\]=CpConcurrentBinDisable\|words\[6\]=0x00000002\|AdrenoPM4Type7(CpMeInitOpcode,7' NativeAdrenoCpInit.cpp
grep -n 'IrqBitCpFence = \|static constexpr uint32_t kEnable' NativeAdrenoIrq.cpp
grep -n '^void NativeAdrenoSubmit::noteStall\|^bool NativeAdrenoSubmit::madeProgress\|^void NativeAdrenoSubmit::driveSwitch\|if(kick_due && !working)\|stage_due(stall_stage,1,pending,200000)\|native_adreno_switch_timeout\[n\]\|native_adreno_map_met' NativeAdrenoSubmit.cpp NativeAdrenoVm.cpp NativeAdrenoUserClient.cpp | head -20
grep -n 'BV timestamp\|0x31u|(1u<<27)|(1u<<31)' tests/test_ring.cpp | head -4
echo "##### theirs: sheng $(runuser -u cyrux -- git -C $R/UniXNU-UniXNU-sheng rev-parse --short=8 HEAD)"
grep -n '^void gpuHwInit\|A740_UCHE_CACHE_WAYS, \|A740_UCHE_CMDQ_CONFIG, \|A740_RBBM_GBIF_CLIENT_QOS_CNTL, \|A740_CP_APRIV_CNTL, \|A740_CP_BV_APRIV_CNTL, \|A740_GRAS_NC_MODE_CNTL, \|A740_RB_NC_MODE_CNTL, \|A740_UCHE_MODE_CNTL, \|A740_RBBM_INT_0_MASK, \|^NativeAdrenoAbiDeviceInfo gDeviceInfo\|^IOReturn gpuRestart' $R/UniXNU-UniXNU-sheng/package/GpuPowerProbe.cpp
echo "##### theirs: sm8550-common $(runuser -u cyrux -- git -C $R/UniXNU-UniXNU-sm8550-common rev-parse --short=8 HEAD); AdrenoFirmware $(runuser -u cyrux -- git -C $R/UniXNU-AdrenoFirmware rev-parse --short=8 HEAD); AdrenoPM4 $(runuser -u cyrux -- git -C $R/UniXNU-AdrenoPM4 rev-parse --short=8 HEAD)"
grep -n 'REG_GMU_AHB_FENCE_RANGE_0,UINT32_C(0x80000000)\|value<=UINT32_C(0x20010004)\|count!=15' $R/UniXNU-UniXNU-sm8550-common/kits/Sm8550Platform/ShengGmu.c | head -4
grep -n 'shared\[1\]=168\|message=4;n=58\|message=3;n=159\|message=14;n=1\|message=10;n=0\|message=11;n=3;p\[0\]=9' $R/UniXNU-AdrenoFirmware/AdrenoHfi.c $R/UniXNU-AdrenoFirmware/AdrenoHfiStartup.c
grep -n '\*header = 0x' $R/UniXNU-AdrenoPM4/AdrenoPM4.c
echo "##### vendor (same phone)"
grep -n '^void gen7_cp_init_cmds\|cp_type7_packet(CP_ME_INIT, 7)\|Operation mode mask\|GEN7_UCHE_CACHE_WAYS, \|GEN7_UCHE_CMDQ_CONFIG,\|GEN7_UCHE_GBIF_GX_CONFIG, \|GEN7_GRAS_NC_MODE_CNTL,\|GEN7_CP_APRIV_CNTL, \|GEN7_CP_BV_APRIV_CNTL, \|GEN7_CP_BV_CHICKEN_DBG, \|GEN7_RB_CMP_DBG_ECO_CNTL, \|gen7_protect_init(adreno_dev);\|^int gen7_fenced_write' $V/adreno_gen7.c
grep -n 'qtbl_hdr.num_q = \|qtbl_hdr.size = \|^#define HFI_QUEUE_MAX' $V/adreno_gen7_hfi.c $V/adreno_gen7_hwsched_hfi.c
grep -n 'CACHE_CLEAN | BIT(27);\|CACHE_CLEAN | BIT(31) | BIT(27);\|cp_type7_packet(CP_WAIT_TIMESTAMP, 4)\|is_concurrent_binning(drawctxt)' $V/adreno_gen7_ringbuffer.c
grep -n '#define KGSL_UBWC_4_0' $R/kernel_oneplus_sm8475/include/uapi/linux/msm_kgsl.h
echo "##### second pass: the remaining anchors the report cites"
S=$R/UniXNU-UniXNU-sheng/package/GpuPowerProbe.cpp
echo "--- sheng hw_init"
grep -n 'A740_RB_CMP_DBG_ECO_CNTL, \|A740_UCHE_GBIF_GX_CONFIG, \|A740_CP_LPAC_APRIV_CNTL, \|A740_CP_PROTECT_CNTL, \|NativeAdrenoA740Protect\[i\]\|NativeAdrenoA740Hwcg\[i\]\|A740_RBBM_CLOCK_CNTL, 0x8aa8aa82\|A740_UCHE_GMEM_RANGE_M\|for (uint32_t pipe = 1\|A740_CP_APERTURE_CNTL_HOST, 0)' $S
echo "--- vendor gen7_start"
grep -n '^int gen7_start\|GEN7_CP_LPAC_CHICKEN_DBG, \|GEN7_CP_CHICKEN_DBG, \|GEN7_CP_LPAC_APRIV_CNTL, \|^#define GEN7_APRIV_DEFAULT\|^#define GEN7_BR_APRIV_DEFAULT' $V/adreno_gen7.c
grep -n 'GEN7_RBBM_GBIF_CLIENT_QOS_CNTL, 0x2120212' $V/adreno-gpulist.h | head -2
grep -n 'adreno_gpu_core_gen7_4_0 = \|\.gpudev = &adreno_gen7_gmu_gpudev' $V/adreno-gpulist.h | head -6
echo "--- Adreno740 details"
cd $R/UniXNU-Adreno740
grep -n 'msm_rbmemptrs: +0 rptr' NativeAdrenoRing.cpp
grep -n 'PreemptGmemSaveRestore' NativeAdrenoPreempt.cpp | head -3
grep -n 'uint32_t gmem_bytes\|uint32_t ubwc_version' NativeAdrenoABI.h
grep -n "BV thread's progress counts" tests/test_submit.cpp
grep -n 'A740_CP_BV_RB_RPTR_ADDR\|NATIVE_ADRENO_A740_HWCG_COUNT\|NATIVE_ADRENO_A740_PROTECT_COUNT' NativeAdrenoA740HwInit.h
echo "--- AdrenoFirmware HFI send"
grep -n 'uint32_t header=(sequence<<20)\|0xfafafafa\|^AdrenoHfiStatus AdrenoHfiSend' $R/UniXNU-AdrenoFirmware/AdrenoHfi.c
echo "--- ours: the service's wait and the report"
G=/home/cyrux/hakios/kernel/drivers/gpu/hakios.gpu.cpp
grep -n 'define GPU_ASK_AGAIN_US\|^gpuWait\|gGPUReported = true' $G
grep -n '^hakios_gpu_report\|^hakios_gpu_address(' $K
grep -c 'panic(' $K $G
echo "##### ours at the end of the wave: $(sha256sum $K | cut -c1-64)"
