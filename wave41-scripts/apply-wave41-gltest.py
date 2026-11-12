#!/usr/bin/env python3
"""Wave 41 (P1-b): gl_test stops being a diagnostic printer and becomes a judge.

Report 4 (docs/review/gpt-review-report-4-2026-11-11-gpu.md) P1-2, independently confirmed by
wave 40 (docs/waves/wave40-gpu-verify.md section 3): gl_test could exit 0 with GL_INVALID
_OPERATION on the wire, every pixel the 0x55 memset pattern, 100% "coverage" and a failed
panel call -- nothing conditioned on any of it. This patch:

  1. shader(): compile failure returns 0 (was: printf and carry on), and main() leaves when a
     shader did not compile -- compile failures propagate;
  2. the renderer string is captured once and announced as a structured line
     (RENDER backend=hw|sw), so a software renderer can never pass for the FD725;
  3. after the draw and after the read-back the GL error is captured per stage (setup/draw/read),
     and any nonzero error is GL_ERROR_FAIL and exit code 4;
  5 pixels are judged: the clear colour (which also proves the read back anything at all: the
     memset pattern 0x55 = 85 is outside its tolerance), the middle of the triangle (an even
     7:7:12 blend of the corners) and three more points by the red, green and blue corners, each
     against its barycentric expectation with a tolerance. The counted coverage (pixels with a
     channel over 60: inside this triangle every point has at least one channel at 85 or more,
     the background has none) must land in 25..27% -- 26% is the triangle's share of the frame
     by geometry, and a rasteriser differs from an area by under half a percent here. Failures
     are READBACK_FAIL lines and exit code 2;
  4. the panel call's own return value is judged: PRESENT_CALL_OK, or PRESENT_CALL_FAIL and
     exit code 3 (also when there is no GPU service at all -- which used to `return 0`);
  5. every stage prints its structured line and flushes, so a remote, non-tty run leaves the
     stage it hung in on the wire (report 4 P1-2's parting request).

Exit codes: 0 pass; 1 context/FBO/link/compile; 2 pixels; 3 panel; 4 GL error.

Each anchor must appear exactly once; the file must be the wave 39 baseline (724d6e96...).
Never run twice.
"""
import hashlib
import sys

PATH = "/home/cyrux/hakios/kernel/userland/src/gl_test.c"
BASE_SHA = "724d6e96475d1ac64aeadfed094ba1fe61481c4ab3353acbeb4472edaeae25f3"

src = open(PATH, "rb").read().decode("utf-8")
if hashlib.sha256(src.encode()).hexdigest() != BASE_SHA:
    sys.exit("gl_test.c is not the wave 39 baseline (724d6e96...); the patch anchors are void")

REPL = []

# --- Hunk A: shader() compile failure returns 0 -------------------------------------------------
REPL.append((
    '\tif (!good) {\n\t\tprintf("gl_test: a shader does not compile\\n");\n\t}\n\treturn name;\n',
    '\tif (!good) {\n\t\tprintf("gl_test: GL_COMPILE_FAIL a shader does not compile\\n");\n'
    '\t\treturn 0;                       /* the callers judge: a shader that did not compile ends the run */\n'
    '\t}\n\treturn name;\n',
))

# --- Hunk B: renderer captured once, backend announced ------------------------------------------
REPL.append((
    '\tprintf("gl_test: %s; %s; %s\\n", (const char *)glGetString(GL_VENDOR), (const char *)glGetString(GL_RENDERER),\n'
    '\t    (const char *)glGetString(GL_VERSION));\n',
    '\tconst char *vendor_string = (const char *)glGetString(GL_VENDOR), *renderer = (const char *)glGetString(GL_RENDERER),\n'
    '\t           *version_string = (const char *)glGetString(GL_VERSION);\n'
    '\n'
    '\tprintf("gl_test: %s; %s; %s\\n", vendor_string, renderer, version_string);\n'
    '\tprintf("gl_test: RENDER backend=%s renderer=%s\\n", strstr(renderer, "FD725") != NULL ? "hw" : "sw", renderer);\n'
    '\tfflush(stdout);\n',
))

# --- Hunk C: shaders hoisted and judged, RENDER_PASS after the link -----------------------------
C_START = ('\tglAttachShader(program, shader(GL_VERTEX_SHADER,\n'
           '\t    "attribute vec2 where; attribute vec3 colour; varying vec3 c;\\n"\n')
C_END = '\t\tprintf("gl_test: the program does not link\\n");\n\t\treturn 1;\n\t}\n'
C_NEW = (
    '\tunsigned vertex = shader(GL_VERTEX_SHADER,\n'
    '\t    "attribute vec2 where; attribute vec3 colour; varying vec3 c;\\n"\n'
    '\t    "void main() { gl_Position = vec4(where, 0.0, 1.0); c = colour; }\\n");\n'
    '\tunsigned fragment = shader(GL_FRAGMENT_SHADER,\n'
    '\t    "precision mediump float; varying vec3 c;\\n"\n'
    '\t    "void main() { gl_FragColor = vec4(c, 1.0); }\\n");\n'
    '\n'
    '\tif (vertex == 0 || fragment == 0) {\n'
    '\t\treturn 1;                       /* shader() has already told which of them does not compile */\n'
    '\t}\n'
    '\tglAttachShader(program, vertex);\n'
    '\tglAttachShader(program, fragment);\n'
    '\tglBindAttribLocation(program, 0, "where");\n'
    '\tglBindAttribLocation(program, 1, "colour");\n'
    '\tglLinkProgram(program);\n'
    '\tglGetProgramiv(program, GL_LINK_STATUS, &good);\n'
    '\tif (!good) {\n'
    '\t\tprintf("gl_test: the program does not link\\n");\n'
    '\t\treturn 1;\n'
    '\t}\n'
    '\tprintf("gl_test: RENDER_PASS backend=%s renderer=%s\\n", strstr(renderer, "FD725") != NULL ? "hw" : "sw", renderer);\n'
    '\tfflush(stdout);\n'
)

# --- Hunk D: the GL error captured around the draw ----------------------------------------------
REPL.append((
    '\tglEnableVertexAttribArray(0);\n\tglEnableVertexAttribArray(1);\n\tglDrawArrays(GL_TRIANGLES, 0, 3);\n'
    '\tglFinish();\n\tdrew = now_ms();\n',
    '\tglEnableVertexAttribArray(0);\n\tglEnableVertexAttribArray(1);\n\tunsigned error_setup = glGetError();\n'
    '\n\tglDrawArrays(GL_TRIANGLES, 0, 3);\n\tglFinish();\n\tdrew = now_ms();\n\tunsigned error_drawn = glGetError();\n',
))

# --- Hunk E: read-back, judgement, present, and a return code that means what it says -----------
E_ANCHOR = "\tmemset(drawn, 0x55, (size_t)width * (size_t)height * 4);\n"
E_NEW = (
    '\tmemset(drawn, 0x55, (size_t)width * (size_t)height * 4);\n'
    '\tglReadPixels(0, 0, width, height, GL_RGBA, GL_UNSIGNED_BYTE, drawn);\n'
    '\tread = now_ms();\n'
    '\tunsigned error_read = glGetError();\n'
    '\t/* the panel\'s rows go down and its pixels are blue first */\n'
    '\tfor (int y = 0; y < height; y++) {\n'
    '\t\tconst uint8_t *from = drawn + (size_t)(height - 1 - y) * (size_t)width * 4;\n'
    '\t\tuint8_t *to = shown + (size_t)y * (size_t)width * 4;\n'
    '\n'
    '\t\tfor (int x = 0; x < width; x++) {\n'
    '\t\t\tto[4 * x] = from[4 * x + 2];\n'
    '\t\t\tto[4 * x + 1] = from[4 * x + 1];\n'
    '\t\t\tto[4 * x + 2] = from[4 * x];\n'
    '\t\t\tto[4 * x + 3] = 255;\n'
    '\t\t\tcoloured += from[4 * x] > 60 || from[4 * x + 1] > 60 || from[4 * x + 2] > 60;\n'
    '\t\t}\n'
    '\t}\n'
    '#define PIXEL(x, y) drawn[((size_t)(y) * (size_t)width + (size_t)(x)) * 4], drawn[((size_t)(y) * (size_t)width + (size_t)(x)) * 4 + 1], \\\n'
    '\t    drawn[((size_t)(y) * (size_t)width + (size_t)(x)) * 4 + 2], drawn[((size_t)(y) * (size_t)width + (size_t)(x)) * 4 + 3]\n'
    '\tprintf("gl_test: %d x %d drawn in %llu ms, read back in %llu ms; error %#x; red green blue alpha: a corner %u %u %u %u, "\n'
    '\t    "the middle %u %u %u %u, near the red corner %u %u %u %u, near the green %u %u %u %u, near the blue %u %u %u %u; "\n'
    '\t    "%u of %u pixels inside the triangle (%u%%; 26%% by geometry)\\n", width, height, drew - began, read - drew,\n'
    '\t    error_setup | error_drawn | error_read, PIXEL(2, 2), PIXEL(width / 2, height / 2), PIXEL(width * 15 / 100, height * 22 / 100),\n'
    '\t    PIXEL(width * 85 / 100, height * 22 / 100), PIXEL(width / 2, height * 80 / 100), coloured,\n'
    '\t    (unsigned)(width * height), (unsigned)((uint64_t)coloured * 100 / (uint64_t)(width * height)));\n'
    '\n'
    '\t/*\n'
    '\t * The judgement, in the open. The triangle\'s corners are pure red, green and blue at\n'
    '\t * (-0.8, -0.6), (0.8, -0.6) and (0, 0.7), the clear is (0.1, 0.1, 0.2, 1.0): a pixel inside\n'
    '\t * the triangle is the barycentric mixture of the corners, one outside is the clear colour,\n'
    '\t * the alpha is 255 everywhere, and 26% of the frame lies inside by geometry. A rasteriser\n'
    '\t * covers the pixels whose centres are in the triangle, which differs from its area by no\n'
    '\t * more than half the edges\' length -- under half a percent of this frame. Each judgement\n'
    '\t * prints a line of its own (RENDER_/READBACK_/GL_ERROR_/PRESENT_...), and a failed one\n'
    '\t * leaves by a code that is not 0, so that no runner can call a broken picture a pass:\n'
    '\t * 1 the context or its program, 2 the pixels, 3 the panel call, 4 a GL error.\n'
    '\t */\n'
    '\tint rc = 0;\n'
    '\tunsigned whole = (unsigned)(width * height), coverage = (unsigned)((uint64_t)coloured * 100 / whole);\n'
    '\tconst struct { int x, y, r, g, b, tolerance; } judged[] = {\n'
    '\t\t{ 2, 2, 26, 26, 51, 3 },                /* the clear, outside; also proves the read back anything at all */\n'
    '\t\t{ width / 2, height / 2, 69, 69, 118, 20 },      /* the middle: the corners in a 7 : 7 : 12 mixture */\n'
    '\t\t{ width * 15 / 100, height * 22 / 100, 235, 12, 8, 30 },        /* in, by the red corner */\n'
    '\t\t{ width * 85 / 100, height * 22 / 100, 12, 235, 8, 30 },        /* in, by the green corner */\n'
    '\t\t{ width / 2, height * 80 / 100, 10, 10, 235, 30 },      /* in, by the blue apex */\n'
    '\t};\n'
    '\tunsigned judged_all = sizeof(judged) / sizeof(judged[0]), samples = 0;\n'
    '\n'
    '\tfor (unsigned k = 0; k < judged_all; k++) {\n'
    '\t\tconst uint8_t *p = drawn + ((size_t)judged[k].y * (size_t)width + (size_t)judged[k].x) * 4;\n'
    '\n'
    '\t\tif (abs((int)p[0] - judged[k].r) <= judged[k].tolerance && abs((int)p[1] - judged[k].g) <= judged[k].tolerance\n'
    '\t\t    && abs((int)p[2] - judged[k].b) <= judged[k].tolerance && p[3] >= 254) {\n'
    '\t\t\tsamples++;\n'
    '\t\t} else {\n'
    '\t\t\tprintf("gl_test: READBACK_FAIL pixel %d, %d: red green blue alpha %u %u %u %u, judged %u %u %u 255'
    ' (tolerance %u)\\n",\n'
    '\t\t\t    judged[k].x, judged[k].y, p[0], p[1], p[2], p[3], judged[k].r, judged[k].g, judged[k].b, judged[k].tolerance);\n'
    '\t\t}\n'
    '\t}\n'
    '\tif (error_setup != 0 || error_drawn != 0 || error_read != 0) {\n'
    '\t\tprintf("gl_test: GL_ERROR_FAIL setup %#x, draw %#x, read %#x\\n", error_setup, error_drawn, error_read);\n'
    '\t\trc = 4;\n'
    '\t}\n'
    '\tif (samples == judged_all && coverage >= 25 && coverage <= 27) {\n'
    '\t\tprintf("gl_test: READBACK_PASS samples %u/%u coverage %u%% (26%% by geometry)\\n", samples, judged_all, coverage);\n'
    '\t} else {\n'
    '\t\tif (coverage < 25 || coverage > 27) {\n'
    '\t\t\tprintf("gl_test: READBACK_FAIL coverage %u%% (26%% by geometry; %u of %u pixels judged inside)\\n",\n'
    '\t\t\t    coverage, coloured, whole);\n'
    '\t\t}\n'
    '\t\tif (rc == 0) {\n'
    '\t\t\trc = 2;\n'
    '\t\t}\n'
    '\t}\n'
    '\tfflush(stdout);\n'
    '\n'
    '\tservice = IOServiceGetMatchingService(0, IOServiceMatching("HakiosGPU"));\n'
    '\tif (service == 0 || IOServiceOpen(service, mach_task_self(), 0, &connection) != 0) {\n'
    '\t\tprintf("gl_test: PRESENT_CALL_FAIL no GPU service in this kernel to put the picture on the panel with\\n");\n'
    '\t\tif (rc == 0) {\n'
    '\t\t\trc = 3;\n'
    '\t\t}\n'
    '\t} else {\n'
    '\t\tstruct show show = { (uint64_t)(uintptr_t)shown, (uint32_t)width, (uint32_t)height, (uint32_t)width * 4, 0 };\n'
    '\t\tkern_return_t result = IOConnectCallStructMethod(connection, 0x7f, &show, sizeof(show), NULL, NULL);\n'
    '\n'
    '\t\tprintf("gl_test: the picture is on the panel (%#x), for %d seconds\\n", result, seconds);\n'
    '\t\tif (result != 0) {\n'
    '\t\t\tprintf("gl_test: PRESENT_CALL_FAIL the panel call did not take\\n");\n'
    '\t\t\tif (rc == 0) {\n'
    '\t\t\t\trc = 3;\n'
    '\t\t\t}\n'
    '\t\t} else {\n'
    '\t\t\tprintf("gl_test: PRESENT_CALL_OK\\n");\n'
    '\t\t\tfor (int i = 1; i < seconds * 5; i++) {\n'
    '\t\t\t\tstruct show again = { (uint64_t)(uintptr_t)shown, (uint32_t)width, (uint32_t)height, (uint32_t)width * 4, 0 };\n'
    '\n'
    '\t\t\t\tIOConnectCallStructMethod(connection, 0x7f, &again, sizeof(again), NULL, NULL);\n'
    '\t\t\t\tusleep(200000);\n'
    '\t\t\t}\n'
    '\t\t}\n'
    '\t\tfflush(stdout);\n'
    '\t}\n'
    '\treturn rc;\n'
    '}\n'
)

for old, new in REPL:
    n = src.count(old)
    if n != 1:
        sys.exit(f"anchor not exactly once ({n}): {old[:70]!r}...")
    src = src.replace(old, new)

if src.count(C_START) != 1:
    sys.exit("hunk C start anchor not exactly once")
if src.count(C_END) != 1:
    sys.exit("hunk C end anchor not exactly once")
a = src.index(C_START)
b = src.index(C_END) + len(C_END)
src = src[:a] + C_NEW + src[b:]

if src.count(E_ANCHOR) != 1:
    sys.exit("hunk E anchor not exactly once")
e = src.index(E_ANCHOR)
src = src[:e] + E_NEW

# never-run-twice markers: the structured lines exist exactly once each
for marker in ("RENDER_PASS backend=", "READBACK_PASS samples ", "PRESENT_CALL_OK\\n", "GL_COMPILE_FAIL"):
    n = src.count(marker)
    if n != 1:
        sys.exit(f"marker {marker!r} appears {n} times, expected 1")
if "no GPU service in this kernel to put the picture on the panel with\\n\");\n\t\treturn 0;" in src:
    sys.exit("the silent no-service return 0 is still in")

open(PATH, "w").write(src)
print("applied: gl_test judges what it draws (RENDER/READBACK/GL_ERROR/PRESENT, rc != 0 on failure)")
print("new sha256:", hashlib.sha256(open(PATH, "rb").read()).hexdigest())
