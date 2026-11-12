#!/usr/bin/env python3
"""Wave 34: apply the mount_writable re-entry guard (the wave31 fix order).
Edits, in the WSL kernel tree: libmini/mini.h (SYS_statfs64 + struct + decl),
libmini/mini.c (the statfs64() wrapper), userland/src/init.c (the guard).
Backs up the three files to /tmp/w34bak/ first. Refuses to run twice cleanly
(exact anchors must be present; the guard text must be absent)."""
import os

B = "/home/cyrux/hakios/kernel"
BAK = "/tmp/w34bak"
os.makedirs(BAK, exist_ok=True)


def edit(path, subs):
    full = os.path.join(B, path)
    bak = os.path.join(BAK, os.path.basename(path))
    if not os.path.exists(bak):
        data = open(full).read()
        open(bak, "w").write(data)
    else:
        data = open(bak).read()  # always edit from the backup: idempotent re-runs
    for old, new in subs:
        assert data.count(old) == 1, "anchor not unique in %s: %r" % (path, old[:60])
        data = data.replace(old, new)
    open(full, "w").write(data)
    print("edited", path)


# --- mini.h: enum + struct + declaration ---
edit("userland/libmini/mini.h", [
    ("SYS_lstat64 = 340, SYS_getdirentries64 = 344, SYS_lchown = 364,",
     "SYS_lstat64 = 340, SYS_getdirentries64 = 344, SYS_statfs64 = 345, SYS_lchown = 364,"),
    ("int     mount(const char *type, const char *dir, int flags, void *data);",
     "int     mount(const char *type, const char *dir, int flags, void *data);\n"
     "int     statfs64(const char *path, struct statfs64 *fs);\n"
     "\n"
     "/* struct statfs64, as statfs64() fills it in (bsd/sys/mount.h, __DARWIN_STRUCT_STATFS64;\n"
     " * 2168 bytes): the wave 34 re-entry guard of mount_writable (src/init.c) reads f_mntfromname */\n"
     "struct statfs64 {\n"
     "\tuint32_t f_bsize;\n"
     "\tint32_t  f_iosize;\n"
     "\tuint64_t f_blocks, f_bfree, f_bavail, f_files, f_ffree;\n"
     "\tuint32_t f_fsid[2];\n"
     "\tuint32_t f_owner, f_type, f_flags, f_fssubtype;\n"
     "\tchar     f_fstypename[16], f_mntonname[1024], f_mntfromname[1024];\n"
     "\tuint32_t f_flags_ext, f_reserved[7];\n"
     "};"),
])

# --- mini.c: the statfs64() wrapper ---
edit("userland/libmini/mini.c", [
    ("""int
mount(const char *type, const char *dir, int flags, void *data)
{
\treturn (int)SC(SYS_mount, type, dir, flags, data, 0, 0);
}""",
     """int
mount(const char *type, const char *dir, int flags, void *data)
{
\treturn (int)SC(SYS_mount, type, dir, flags, data, 0, 0);
}

int
statfs64(const char *path, struct statfs64 *fs)
{
\treturn (int)SC(SYS_statfs64, path, fs, 0, 0, 0, 0);
}"""),
])

# --- init.c: the re-entry guard of mount_writable ---
GUARD = """\tprintf("\\n-- writable filesystem --\\n");
\t/* wave 34: init has been seen to run twice (wave31: the mount table carried the data volume
\t * AND a fallback ramfs stacked over it, so the visible /private/var was a memory filesystem,
\t * empty at every boot). On the second pass the volume's mount fails with EBUSY and the
\t * fallback below used to go on top of the volume. If /private/var already carries the volume
\t * (or a first pass's memory filesystem), this pass keeps what is there. */
\tif (statfs64("/private/var", &sf) == 0 &&
\t    (strncmp(sf.f_mntfromname, "/dev/ufs_darwin_data", sizeof("/dev/ufs_darwin_data") - 1) == 0 ||
\t    strcmp(sf.f_mntfromname, "ramfs") == 0)) {
\t\tvar_kept = strncmp(sf.f_mntfromname, "/dev/ufs_darwin_data", sizeof("/dev/ufs_darwin_data") - 1) == 0;
\t\tprintf("  /private/var already mounted from %s%s; the re-entry guard keeps it, skipping the fallback\\n",
\t\t    sf.f_mntfromname, var_kept ? ", kept between boots" : "");
\t\treturn;
\t}
\tvar_kept = mount_data_volume();"""

edit("userland/src/init.c", [
    ("""\tint ok, fd, made = 0, files = 0;
\tconst char *jb;
\tstruct stat st;
""",
     """\tint ok, fd, made = 0, files = 0;
\tconst char *jb;
\tstruct stat st;
\tstruct statfs64 sf;
"""),
    ("""\tprintf("\\n-- writable filesystem --\\n");
\tvar_kept = mount_data_volume();""", GUARD),
])

print("all three files edited")
