/*
 * fence_probe: the wave45 gate-B probe (P0 device-level first test).
 *
 * Two minimal BO/IB submissions, each one CP_MEM_WRITE of its own nonce into
 * the buffer it runs from, through the real user client path (gem new -> map ->
 * gem info -> gem submit -> wait fence). The verdict is on the device:
 *   - a fence that completes is the GPU having written that number into
 *     GPU_FENCE_AT (hakios_gpu_done reads the RAM word the wave41 fence event
 *     0x08000031 asked the SQE to write back), and
 *   - the nonce read back in the buffer is the IB having really run.
 * Two rounds prove the fence numbers increase (submit #2 is a fresh write).
 *
 * wave44 s5-3's failure branch, the userland edition: a submission that is not
 * answered is retried -- every resubmit rewrites the ring's WPTR, the
 * Adreno740 field lesson (5397 submissions, 5361 passing only on the handler's
 * rewrite). A wait >= 1 s that times out makes the kernel print its register
 * report (RPTR/WPTR and friends, GMU_AHB_FENCE_STATUS among them) into the
 * klog -- the runner reads it from /dev/logdump; this program only names the
 * round that timed out.
 *
 * Also consulted: GET_PARAM 0x03 (chip id) and 0x10 (highest bank bit, the
 * number the five NC_MODE registers were computed from; expect 16 here).
 *
 * Build (the gl_test recipe without Mesa):
 *   xnu-clang -arch arm64 -isysroot $HOME/theos/sdks/iPhoneOS16.5.sdk -O1 \
 *     -framework CoreFoundation -framework IOKit -o fence_probe fence_probe.c
 */
#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/IOKitLib.h>
#include <mach/mach.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/* the kernel's selectors (drivers/gpu/hakios.gpu.cpp) */
#define K_MSM_GET_PARAM  0x40
#define K_MSM_GEM_NEW    0x42
#define K_MSM_GEM_INFO   0x43
#define K_MSM_GEM_SUBMIT 0x46
#define K_MSM_WAIT_FENCE 0x47

#define MSM_INFO_GET_IOVA  1
#define MSM_SUBMIT_CMD_BUF 1
#define CP_MEM_WRITE       0x3d

/* the kernel's structures, field for field (hakios.gpu.cpp) */
struct msm_timespec { int64_t seconds, nanoseconds; };
struct msm_param { uint32_t pipe, param; uint64_t value; uint32_t len, pad; };
struct msm_gem_new { uint64_t size; uint32_t flags, handle; };
struct msm_gem_info { uint32_t handle, info; uint64_t value; uint32_t len, pad; };
struct msm_gem_submit_cmd { uint32_t type, submit_idx, submit_offset, size, pad, nr_relocs; uint64_t relocs; };
struct msm_gem_submit_bo { uint32_t flags, handle; uint64_t presumed; };
struct msm_gem_submit {
	uint32_t flags, fence, nr_bos, nr_cmds;
	uint64_t bos, cmds;
	int32_t fence_fd;
	uint32_t queueid;
	uint64_t in_syncobjs, out_syncobjs;
	uint32_t nr_in_syncobjs, nr_out_syncobjs, syncobj_stride, pad;
};
struct msm_wait_fence { uint32_t fence, flags; struct msm_timespec timeout; uint32_t queueid; };

/* the ring packet header's parity, the driver's own formula (hakios.adreno.c) */
static uint32_t
odd_parity(uint32_t v)
{
	return 0x9669 >> (0xf & (v ^ v >> 4 ^ v >> 8 ^ v >> 12 ^ v >> 16 ^ v >> 20 ^ v >> 24 ^ v >> 28)) & 1;
}

static kern_return_t
call(io_connect_t connection, uint32_t selector, void *r, size_t size)
{
	size_t out = size;

	return IOConnectCallStructMethod(connection, selector, r, size, r, &out);
}

#define ROUNDS 2
#define RETRIES 8

int
main(int argc, char **argv)
{
	io_service_t service;
	io_connect_t connection = 0;
	kern_return_t kr;
	struct msm_gem_new gemNew;
	struct msm_gem_info gemInfo;
	struct msm_param param;
	struct msm_gem_submit_bo bo;
	struct msm_gem_submit_cmd cmd;
	struct msm_gem_submit submit;
	struct msm_wait_fence wait;
	uint32_t *ib = NULL;
	uint64_t iova = 0;
	mach_vm_address_t map = 0;
	mach_vm_size_t mapped = 0;
	uint32_t fences[ROUNDS] = { 0 };
	uint32_t nonces[ROUNDS] = { 0 };
	int memory_ok = 0, rounds_done = 0, retries_used = 0, timeouts = 0;
	int round, retry;

	service = IOServiceGetMatchingService(0, IOServiceMatching("HakiosGPU"));
	if (service == 0) {
		printf("FENCE_PROBE: FAIL no HakiosGPU service\n");
		return 3;
	}
	kr = IOServiceOpen(service, mach_task_self(), 0, &connection);
	IOObjectRelease(service);
	if (kr != 0) {
		printf("FENCE_PROBE: FAIL IOServiceOpen %#x\n", kr);
		return 3;
	}

	/* the consults: who the kernel says it drives, and the NC_MODE seed */
	memset(&param, 0, sizeof(param));
	param.param = 0x03;
	if (call(connection, K_MSM_GET_PARAM, &param, sizeof(param)) == 0) {
		printf("FENCE_PROBE: chip id %#llx (the 0x7030002 family is this phone's)\n", param.value);
	}
	memset(&param, 0, sizeof(param));
	param.param = 0x10;
	if (call(connection, K_MSM_GET_PARAM, &param, sizeof(param)) == 0) {
		printf("FENCE_PROBE: highest bank bit %llu (the NC_MODE registers were computed from it; 16 expected)\n",
		    param.value);
	}

	/* one page: the IB lives in it, and the nonces land in it */
	memset(&gemNew, 0, sizeof(gemNew));
	gemNew.size = 4096;
	kr = call(connection, K_MSM_GEM_NEW, &gemNew, sizeof(gemNew));
	if (kr != 0) {
		printf("FENCE_PROBE: FAIL gem new %#x\n", kr);
		return 3;
	}
	memset(&gemInfo, 0, sizeof(gemInfo));
	gemInfo.handle = gemNew.handle;
	gemInfo.info = MSM_INFO_GET_IOVA;
	kr = call(connection, K_MSM_GEM_INFO, &gemInfo, sizeof(gemInfo));
	if (kr != 0) {
		printf("FENCE_PROBE: FAIL gem info %#x\n", kr);
		return 3;
	}
	iova = gemInfo.value;
	kr = IOConnectMapMemory64(connection, gemNew.handle, mach_task_self(), &map, &mapped, kIOMapAnywhere);
	if (kr != 0) {
		printf("FENCE_PROBE: FAIL map %#x\n", kr);
		return 3;
	}
	ib = (uint32_t *)(uintptr_t)map;
	printf("FENCE_PROBE: buffer handle %u iova %#llx mapped %llu bytes at %#llx\n",
	    gemNew.handle, iova, (unsigned long long)mapped, (unsigned long long)map);

	/* the wait, one done-poll at a time: a 0 patience cannot trip the kernel's
	 * 1 s "no answer" latch, so the retry ladder stays meaningful */
	for (round = 0; round < ROUNDS; round++) {
		nonces[round] = 0x45f000c0u + (uint32_t)round;

		/* the IB: CP_MEM_WRITE lo hi nonce -- the nonce goes 64 bytes in,
		 * well past the four instruction words */
		ib[0] = 7u << 28 | 3 | odd_parity(3) << 15 | CP_MEM_WRITE << 16 | odd_parity(CP_MEM_WRITE) << 23;
		ib[1] = (uint32_t)(iova + 64);
		ib[2] = (uint32_t)(iova >> 32);
		ib[3] = nonces[round];
		ib[16] = 0;

		memset(&submit, 0, sizeof(submit));
		submit.nr_bos = 1;
		submit.nr_cmds = 1;
		bo.flags = 3;                       /* READ | WRITE */
		bo.handle = gemNew.handle;
		bo.presumed = iova;
		cmd.type = MSM_SUBMIT_CMD_BUF;
		cmd.submit_idx = 0;
		cmd.submit_offset = 0;
		cmd.size = 16;
		cmd.nr_relocs = 0;
		submit.bos = (uint64_t)(uintptr_t)&bo;
		submit.cmds = (uint64_t)(uintptr_t)&cmd;
		kr = call(connection, K_MSM_GEM_SUBMIT, &submit, sizeof(submit));
		if (kr != 0 || submit.fence == 0) {
			printf("FENCE_PROBE: FAIL submit round %d kr %#x fence %u\n", round, kr, submit.fence);
			continue;
		}
		fences[round] = submit.fence;

		for (retry = 0;; retry++) {
			memset(&wait, 0, sizeof(wait));
			wait.fence = fences[round];
			wait.timeout.seconds = 0;       /* one poll of the RAM word */
			kr = call(connection, K_MSM_WAIT_FENCE, &wait, sizeof(wait));
			if (kr == 0) {
				break;
			}
			retries_used++;
			if (retry >= RETRIES) {
				timeouts++;
				printf("FENCE_PROBE: TIMEOUT round %d fence %u after %d WPTR rewrites (the klog's "
				    "register report is the evidence: GMU_AHB_FENCE_STATUS, RPTR, WPTR)\n",
				    round, fences[round], retry);
				break;
			}
			/* the wave44 branch: rewrite the WPTR (a fresh submit does) and wait again */
			if (retry == 0) {
				printf("FENCE_PROBE: round %d fence %u not done on the first poll; resubmitting "
				    "(each resubmit rewrites the WPTR)\n", round, fences[round]);
			}
			memset(&submit, 0, sizeof(submit));
			submit.nr_bos = 1;
			submit.nr_cmds = 1;
			bo.flags = 3;
			bo.handle = gemNew.handle;
			bo.presumed = iova;
			cmd.type = MSM_SUBMIT_CMD_BUF;
			cmd.submit_idx = 0;
			cmd.submit_offset = 0;
			cmd.size = 16;
			cmd.nr_relocs = 0;
			submit.bos = (uint64_t)(uintptr_t)&bo;
			submit.cmds = (uint64_t)(uintptr_t)&cmd;
			kr = call(connection, K_MSM_GEM_SUBMIT, &submit, sizeof(submit));
			if (kr != 0 || submit.fence == 0) {
				printf("FENCE_PROBE: FAIL resubmit round %d retry %d kr %#x fence %u\n",
				    round, retry, kr, submit.fence);
				timeouts++;
				break;
			}
			fences[round] = submit.fence;
			usleep(400 * 1000);
		}
		if (kr == 0) {
			rounds_done++;
			if (ib[16] == nonces[round]) {
				memory_ok++;
				printf("FENCE_PROBE: round %d fence %u done, memory reads %#x (the nonce, as written)\n",
				    round, fences[round], ib[16]);
			} else {
				printf("FENCE_PROBE: READBACK_FAIL round %d fence %u done but memory reads %#x, wanted %#x\n",
				    round, fences[round], ib[16], nonces[round]);
			}
		}
	}

	IOServiceClose(connection);

	printf("FENCE_PROBE: rounds done %d/%d, memory ok %d/%d, fence sequence %u then %u (%s), "
	    "polls %d, timeouts %d\n", rounds_done, ROUNDS, memory_ok, ROUNDS,
	    fences[0], fences[1],
	    (fences[1] > fences[0]) ? "increasing" : "NOT increasing",
	    retries_used, timeouts);

	if (rounds_done == ROUNDS && memory_ok == ROUNDS && fences[1] > fences[0]) {
		printf("FENCE_PROBE: PASS the device writes the fence number back and runs the IB "
		    "(the wave41 fence event works on this hardware)\n");
		return 0;
	}
	printf("FENCE_PROBE: FAIL (%s%s%s)\n",
	    rounds_done != ROUNDS ? "fence " : "",
	    memory_ok != ROUNDS ? "memory " : "",
	    fences[1] <= fences[0] ? "sequence " : "");
	return 1;
}
