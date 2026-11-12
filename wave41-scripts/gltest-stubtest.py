#!/usr/bin/env python3
"""Wave 41 isolated self-test for gl_test: the real main() against stub GL and IOKit.

The report-4 method, kept as a standing test. It takes the CURRENT gl_test.c, replaces the
framework includes and the GL extern block with stand-ins, and runs three scenarios:

  error    glGetError says 0x502, glReadPixels does nothing (the 0x55 memset stays), no GPU
           service -- exactly report 4's negative control, which the old program answered with
           "100%, the picture is on the panel, exit 0". The judge must leave nonzero (4), and
           must not print any PASS line.
  hw       a synthetic, geometrically exact picture, no GL error, renderer FD725, the panel call
           takes -- the judge must print RENDER backend=hw, RENDER_PASS, READBACK_PASS and
           PRESENT_CALL_OK and exit 0.
  sw       the same picture but renderer "softpipe" -- assertions still pass (a software
           renderer draws correctly), but the backend line must say sw, so no runner can call
           it the FD725.

No device, no real GL: the picture is computed here the way the geometry says it must be.
"""
import subprocess
import sys

SRC = "/home/cyrux/hakios/kernel/userland/src/gl_test.c"
CFILE = "/tmp/wave41-gltest-stub.c"
BIN = "/tmp/wave41-gltest-stub"

src = open(SRC).read()

# cut the framework includes
head = "#include <CoreFoundation/CoreFoundation.h>\n#include <IOKit/IOKitLib.h>\n#include <mach/mach_time.h>\n"
if head not in src:
    sys.exit("the framework include block is not where it was expected")
src = src.replace(head, "", 1)

# cut the GL extern block (the stubs below define the same names)
EXT_HEAD = "/* GL/osmesa.h and GLES2/gl2.h of Mesa, as far as they are used here */\n"
EXT_TAIL = "extern void glReadPixels(int x, int y, int width, int height, unsigned format, unsigned type, void *pixels);\n"
if EXT_HEAD not in src or EXT_TAIL not in src:
    sys.exit("the GL extern block is not where it was expected")
a = src.index(EXT_HEAD)
b = src.index(EXT_TAIL) + len(EXT_TAIL)
src = src[:a] + "__WAVE41_STUBS__\n" + src[b:]

STUBS = r"""
/* ---- wave 41 stub framework: stand-ins for CoreFoundation / IOKit / mach clocks / GL ---- */
typedef struct osmesa_context *OSMesaContext;
typedef uint32_t io_service_t;
typedef uint32_t io_connect_t;
typedef int kern_return_t;
typedef struct { uint32_t numer, denom; } mach_timebase_info_data_t;

enum { STUB_GOOD_HW = 0, STUB_GOOD_SW = 1, STUB_ERROR = 2 };
static int stub_mode = STUB_GOOD_HW;

static uint32_t mach_task_self(void) { return 0; }
static uint64_t stub_ticks;
static uint64_t mach_absolute_time(void) { stub_ticks += 1000000; return stub_ticks; }
static int mach_timebase_info(mach_timebase_info_data_t *info) { info->numer = 1; info->denom = 1; return 0; }

static void *IOServiceMatching(const char *name) { return (void *)name; }
static io_service_t IOServiceGetMatchingService(uint32_t a, void *matching)
{
	(void)a; (void)matching;
	return stub_mode == STUB_ERROR ? 0 : 7;
}
static kern_return_t IOServiceOpen(io_service_t s, uint32_t t, uint32_t type, io_connect_t *c)
{
	*c = 42; (void)s; (void)t; (void)type;
	return 0;
}
static kern_return_t IOConnectCallStructMethod(io_connect_t c, uint32_t selector, const void *in, size_t in_size,
    void *out, size_t *out_size)
{
	(void)c; (void)selector; (void)in; (void)in_size; (void)out; (void)out_size;
	return 0;
}

/* the synthetic picture: what the geometry says the frame must contain, at the pixel centres */
static void stub_draw_picture(int width, int height, unsigned char *buf)
{
	double A[2] = { 0.10 * width, 0.20 * height }, B[2] = { 0.90 * width, 0.20 * height }, C[2] = { 0.50 * width, 0.85 * height };
	int y, x;

	for (y = 0; y < height; y++) {
		for (x = 0; x < width; x++) {
			double px = x + 0.5, py = y + 0.5;
			double det = (B[1] - C[1]) * (A[0] - C[0]) + (C[0] - B[0]) * (A[1] - C[1]);
			double wa = ((B[1] - C[1]) * (px - C[0]) + (C[0] - B[0]) * (py - C[1])) / det;
			double wb = ((C[1] - A[1]) * (px - C[0]) + (A[0] - C[0]) * (py - C[1])) / det;
			double wc = 1.0 - wa - wb;
			unsigned char *p = buf + ((size_t)y * (size_t)width + (size_t)x) * 4;

			if (wa >= 0 && wb >= 0 && wc >= 0) {
				p[0] = (unsigned char)(wa * 255.0 + 0.5);
				p[1] = (unsigned char)(wb * 255.0 + 0.5);
				p[2] = (unsigned char)(wc * 255.0 + 0.5);
			} else {
				p[0] = 26; p[1] = 26; p[2] = 51;
			}
			p[3] = 255;
		}
	}
}

static const char *stub_renderers[3] = { "FD725", "softpipe", "FD725" };

static const unsigned char *glGetString(unsigned name) { (void)name; return (const unsigned char *)stub_renderers[stub_mode]; }
static unsigned glGetError(void) { return stub_mode == STUB_ERROR ? 0x502 : 0; }
static void glGenTextures(int n, unsigned *names) { names[0] = 1; (void)n; }
static void glBindTexture(unsigned t, unsigned n) { (void)t; (void)n; }
static void glTexImage2D(unsigned t, int l, int i, int w, int h, int b, unsigned f, unsigned ty, const void *px)
{ (void)t; (void)l; (void)i; (void)w; (void)h; (void)b; (void)f; (void)ty; (void)px; }
static void glTexParameteri(unsigned t, unsigned n, int v) { (void)t; (void)n; (void)v; }
static void glGenFramebuffers(int n, unsigned *names) { names[0] = 1; (void)n; }
static void glBindFramebuffer(unsigned t, unsigned f) { (void)t; (void)f; }
static void glFramebufferTexture2D(unsigned t, unsigned a, unsigned tt, unsigned tx, int l)
{ (void)t; (void)a; (void)tt; (void)tx; (void)l; }
static unsigned glCheckFramebufferStatus(unsigned t) { (void)t; return 0x8cd5; }
static void glViewport(int x, int y, int w, int h) { (void)x; (void)y; (void)w; (void)h; }
static void glClearColor(float r, float g, float b, float a) { (void)r; (void)g; (void)b; (void)a; }
static void glClear(unsigned m) { (void)m; }
static unsigned glCreateShader(unsigned t) { (void)t; return 1; }
static void glShaderSource(unsigned s, int c, const char *const *str, const int *len) { (void)s; (void)c; (void)str; (void)len; }
static void glCompileShader(unsigned s) { (void)s; }
static void glGetShaderiv(unsigned s, unsigned n, int *v) { *v = 1; (void)s; (void)n; }
static unsigned glCreateProgram(void) { return 1; }
static void glAttachShader(unsigned p, unsigned s) { (void)p; (void)s; }
static void glBindAttribLocation(unsigned p, unsigned i, const char *n) { (void)p; (void)i; (void)n; }
static void glLinkProgram(unsigned p) { (void)p; }
static void glGetProgramiv(unsigned p, unsigned n, int *v) { *v = 1; (void)p; (void)n; }
static void glUseProgram(unsigned p) { (void)p; }
static void glVertexAttribPointer(unsigned i, int s, unsigned t, unsigned char nrm, int strd, const void *ptr)
{ (void)i; (void)s; (void)t; (void)nrm; (void)strd; (void)ptr; }
static void glEnableVertexAttribArray(unsigned i) { (void)i; }
static void glDrawArrays(unsigned m, int f, int c) { (void)m; (void)f; (void)c; }
static void glFinish(void) { }
static void glEnable(unsigned w) { (void)w; }
static void glDisable(unsigned w) { (void)w; }
static void glBlendFunc(unsigned s, unsigned d) { (void)s; (void)d; }
static int glGetUniformLocation(unsigned p, const char *n) { (void)p; (void)n; return 0; }
static void glUniform1i(int l, int v) { (void)l; (void)v; }
static void glUniform4f(int l, float x, float y, float z, float w) { (void)l; (void)x; (void)y; (void)z; (void)w; }
static void glReadPixels(int x, int y, int w, int h, unsigned f, unsigned t, void *data)
{
	if (stub_mode == STUB_ERROR) {
		return;                                 /* the 0x55 memset stays: nothing was read back */
	}
	stub_draw_picture(w, h, (unsigned char *)data);
	(void)x; (void)y; (void)f; (void)t;
}
static OSMesaContext OSMesaCreateContextAttribs(const int *at, OSMesaContext share)
{ (void)at; (void)share; return (OSMesaContext)1; }
static unsigned char OSMesaMakeCurrent(OSMesaContext c, void *buf, unsigned t, int w, int h)
{ (void)c; (void)buf; (void)t; (void)w; (void)h; return 1; }
"""

src = src.replace("__WAVE41_STUBS__\n", STUBS + "\n", 1)

# rename the file's own main, then add the scenario runner
MAIN = "int\nmain(int argc, char **argv)\n{"
if src.count(MAIN) != 1:
    sys.exit("main is not where it was expected")
src = src.replace(MAIN, "#define main gl_test_main\nint\nmain(int argc, char **argv)\n{", 1)
src += r"""

#undef main
int
main(int argc, char **argv)
{
	const char *mode = getenv("STUB_MODE");

	if (mode && strcmp(mode, "error") == 0) {
		stub_mode = STUB_ERROR;
	} else if (mode && strcmp(mode, "sw") == 0) {
		stub_mode = STUB_GOOD_SW;
	} else {
		stub_mode = STUB_GOOD_HW;
	}
	argv[1] = (char *)"1";                  /* one second on the panel: the stub call takes at once */
	return gl_test_main(argc, argv);
}
"""

open(CFILE, "w").write(src)
r = subprocess.run(["cc", "-w", "-o", BIN, CFILE], capture_output=True, text=True)
if r.returncode != 0:
    print(r.stdout, r.stderr)
    sys.exit("the stub harness did not compile")

SCENARIOS = [
    ("error", 4, ["GL_ERROR_FAIL", "READBACK_FAIL", "PRESENT_CALL_FAIL"],
     ["READBACK_PASS", "PRESENT_CALL_OK"]),
    ("hw", 0, ["RENDER backend=hw", "RENDER_PASS backend=hw", "READBACK_PASS samples 5/5", "PRESENT_CALL_OK"],
     ["FAIL"]),
    ("sw", 0, ["RENDER backend=sw", "RENDER_PASS backend=sw", "READBACK_PASS samples 5/5", "PRESENT_CALL_OK"],
     ["FAIL"]),
]
bad = 0
for mode, want_rc, wants, forbids in SCENARIOS:
    env = {"STUB_MODE": mode, "PATH": "/usr/bin:/bin"}
    r = subprocess.run([BIN, "1"], capture_output=True, text=True, env=env)
    out = r.stdout
    ok = r.returncode == want_rc and all(w in out for w in wants) and not any(f in out for f in forbids)
    print(f"--- scenario {mode}: rc={r.returncode} (want {want_rc}) {'PASS' if ok else 'FAIL'}")
    for line in out.splitlines():
        if "gl_test:" in line:
            print("   ", line)
    if not ok:
        bad = 1

sys.exit(bad)
