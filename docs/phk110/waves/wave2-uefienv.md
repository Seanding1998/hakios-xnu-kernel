# 阶段 2 · 2026-11-02 · UEFI 构建环境搭建（WSL Fedora）

日期：2026-11-02。结论：**全部通过，且做了最强验证**——`build_uefi.py -d ingres -r RELEASE` 完整跑通并产出 `SILICIUM_UEFI.fd` 与 `Mu-ingres.img`（EXIT=0）。未碰手机，未改 `kernel/**`、`Binaries/**`、`Platforms/Xiaomi/ingresPkg`。

## 1. 子模块状态（git submodule status，全部非 "-"）

| 子模块 | commit | 备注 |
|---|---|---|
| Binaries | `9f4dbfd7d61a` (heads/main) | 原已 init，未改动 |
| Common/Mu (mu_plus) | `566cf5c8c2c8` (heads/release/202608) | 本次 `--depth 1` 补齐 |
| Common/Mu_OEM_Sample | `9292f9254adb` (heads/release/202608) | 本次补齐 |
| Mu_Basecore | `42d6d889f7c1` (42d6d88) | 本次补齐 |
| Silicium-ACPI | `f50bc115dccd` (heads/main) | 本次补齐 |
| Silicon/Silicium/OpensslPkg/Library/OpensslLib/openssl | `67b5686b4419` (67b5686) | 本次补齐 |

命令：`git submodule update --init --depth 1`，一次成功（无重试）。注意：后续 stuart_setup 又对 Mu_Basecore 做了 `--recursive` 递归拉取（嵌套子模块 libspdm、cmocka 等，走 github/gitlab），首次构建时自动完成。

## 2. 系统依赖（按 setup_env.sh 的 dnf 清单核对）

本次 root 安装（`dnf install -y`）：

| 包 | 版本 | 用途 |
|---|---|---|
| nasm | 3.02 | EDK2 汇编 |
| gcc-aarch64-linux-gnu | 16.2.1 (Red Hat Cross) | 交叉链接/工具链前缀 |
| gnupg | — | 清单要求 |
| mono-devel | 6.14.1 | stuart_update 用 mono 跑 NuGet.exe 拉 mu_nasm 等 |
| nuget | 2.8.7 | 同上（清单要求） |

已存在未动：git 2.56.0、make 4.4.1、lld/clang/llvm 22.1.8、gcc 16.0.1（主机）、automake、python3 3.14.8、python3-pip 26.0.1、gettext、ca-certificates、git-core、curl、uuid/libuuid。

工具链版本记录：
- `nasm -v` → NASM version 3.02
- `aarch64-linux-gnu-gcc --version` → 16.2.1
- `clang` → 22.1.8（CLANGPDB 实际用的编译器，`/usr/bin/clang`）
- `ld.lld` → 22.1.8

## 3. Python venv

- 路径：`~/hakios/Mu-Silicium/venv`
- **Python 3.14.8 一次成功**（regex==2026.9.29 有 3.14 预编译轮子，未触发 python3.13 预案）
- 直接依赖安装成功：edk2-pytool-library==0.23.17、edk2-pytool-extensions==0.31.3、antlr4-python3-runtime==4.13.2、regex==2026.9.29、pefile==2024.8.26、coloredlogs==15.0.1（传递依赖含 GitPython、cryptography、rich 等）
- 构建/运行一律用 `venv/bin/python3`（build_uefi.py 用 `sys.executable` 调 DeviceBuild.py，自动继承 venv）

## 4. 空跑验证（实际为全量构建，最强验证）

### 4.1 `build_uefi.py --help`
正常输出 usage（-d/-m/-r/-s/-c/-u），EXIT=0。

### 4.2 完整构建 `CLANGPDB_AARCH64_PREFIX=aarch64-linux-gnu- venv/bin/python3 build_uefi.py -d ingres -r RELEASE`

结果 **EXIT=0，全流程通过**，日志 `/tmp/build_ingres.log`（1742 行）。阶段：
1. 设备解析：找到 `Platforms/Xiaomi/ingresPkg` + `Resources/Configs/ingres.toml` ✓
2. BootShim 编译（clang --target=aarch64-linux-gnu + llvm-objcopy）✓
3. stuart_setup：6 个子模块递归解析 ✓（首次，含 gitlab 拉 cmocka）
4. stuart_update：mu_nasm 经 mono+NuGet 就位于 `Mu_Basecore/BaseTools/Bin/mu_nasm_extdep/Linux-x86-64` ✓
5. 4 个 Mu_Basecore 补丁（Auth-Service/Boot-Manager/Timer/Usb-Bus）应用成功（`git -C Mu_Basecore status` 可见改动）✓
6. stuart_build：**35 秒**（20 核），"Postbuild Image Validation Finished — 0048 Images Verified"，Success ✓

产物（均已存在）：
- `~/hakios/Mu-Silicium/Build/ingresPkg/RELEASE_CLANGPDB/FV/SILICIUM_UEFI.fd`（3,145,728 B = 0x300000）
- `~/hakios/Mu-Silicium/Mu-ingres.img`（2,068,480 B，魔数 `ANDROID!` 有效；gzip(fd)+dtb，boot_shim 路径）
- `~/hakios/Mu-Silicium/BootShim/BootShim.bin`（112 B）

注：日志中多处 `make: ... Error 1 (ignored)` 是 EDK2 LTO 构建的正常噪音（genfw 阶段），最终 Success。

## 5. 给 阶段 3 的注意事项

1. **平台路径**：ingresPkg 实际在 `Platforms/Xiaomi/ingresPkg`（不是 Realme；上游如此）。`build_uefi.py` 的 `get_device_package_path` 在 `Platforms/` 下按 `*/<dev>Pkg`、`*/*/<dev>Pkg` 两层 glob 搜索，phk110Pkg 放哪层厂商目录都能找到。D 复制时以 `Platforms/Xiaomi/ingresPkg` + `Binaries/ingres` 为模板即可（Binaries 素材引用是 `Binaries/<codename>` 平铺，不按厂商分）。
2. **环境变量**：构建前必须 `export CLANGPDB_AARCH64_PREFIX=aarch64-linux-gnu-`（setup_env.sh 即此做法；Conf/tools_def.txt 里工具链路径走 `ENV(..._PREFIX)`）。
3. **入口与解释器**：统一 `cd ~/hakios/Mu-Silicium && CLANGPDB_AARCH64_PREFIX=aarch64-linux-gnu- venv/bin/python3 build_uefi.py -d <dev> -r RELEASE`。build_uefi.py 以 `sys.executable` 调 DeviceBuild.py（stuart），venv 自动传递。
4. **EDK2 配置文件（CONF）**：`~/hakios/Mu-Silicium/Conf/{target.txt,tools_def.txt,build_rule.txt}`（由 stuart 首次生成；重置环境可删 Conf/ 与 Build/ 后重跑，会触发 setup+update，约需重新联网拉 NuGet 包）。
5. **增量构建**：`Build/` 目录存在时 build_uefi.py 会跳过 stuart_setup/update（除非 `-u`）。改 dsc/fdf/源码后直接重跑即可，增量很快；全量重建加 `-c`。
6. **补丁时序**：build_uefi.py 每次先反向摘 4 个 Mu_Basecore 补丁（失败容忍）→ 构建/更新环境 → 重新应用。若 阶段 3 的 hakios.patch 也动 Mu_Basecore，注意与之解冲突（build_uefi.py 只管它自己的 4 个）。
7. **性能**：20 核 8GB 下 stuart_build 仅 35s；首次环境搭建（子模块递归 + NuGet）约 10 分钟，网络依赖 github + gitlab + nuget.org（WSL mirrored 网络实测可用）。
8. **MU Basecore 提交**：`42d6d88 [CHERRY-PICK] BaseTools: FMMT...`；hakios-uefi BASE 若为更早提交，阶段 3 应用 hakios.patch 前先核对 BASE commit（`upstream/hakios-uefi/BASE`）与本仓库 HEAD 是否一致。
9. **构建验证日志**：`/tmp/build_ingres.log`（本机留存），stuart 自身日志在 `Build/BUILDLOG_ingresPkg.txt`。
