import json

d = json.load(open("<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave21-scripts/f10_scan2_result.json"))
print("total files:", len(d))
print()
print("== Binaries/ vendor files with hits ==")
for r in d:
    if "/Binaries/" in r["file"]:
        name = r["file"].split("/Binaries/")[1]
        print("%-64s tot=%3d al4=%3d" % (name, r["total"], r["aligned4"]))
print()
print("== FD ==")
for r in d:
    if r["file"].endswith(".fd"):
        print("%s: tot=%d al4=%d size=%d" % (r["file"], r["total"], r["aligned4"], r["size"]))
        print("   first aligned hits:", [hex(c["off"]) for c in r["context"][:6]])
print()
print("== built .efi top aligned4 ==")
rest = [r for r in d if "/Binaries/" not in r["file"] and not r["file"].endswith(".fd")]
for r in sorted(rest, key=lambda x: -x["aligned4"])[:12]:
    name = r["file"].split("AARCH64/")[-1]
    print("%-64s tot=%3d al4=%3d" % (name, r["total"], r["aligned4"]))
