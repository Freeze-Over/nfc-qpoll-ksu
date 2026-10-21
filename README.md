# nfc-qpoll-ksu

在**非华为 Android 手机**上驱动**华为 552×768 四色墨水屏手机壳**的 KernelSU / Magisk 模块。

> 原理：壳子只认 **7-bit 短帧 `0x7A`**，NXP 的 **Q-Poll（NCI tech `0x71`）** 发的就是它；
> 但 Android NFA 只支持 NFC-A `0x00`，收到 `0x71` 不会创建 Tag。
> 本模块在 `com.android.nfc` 进程内做 **NCI 双向映射**，让系统把壳子当成普通 NFC-A 标签，
> 之后 App 用标准 ISO-DEP 发送 `D1/D8/D3/D4/DE` 即可刷图。

- 已验证：**Redmi Note 12 Turbo（marble）/ NXP SN110T / Android 15 / KernelSU + Zygisk Next**
- 未验证：其它 NXP 机型、其它 ROM
- 不支持：**小米 15 Pro（haotian，ST54L）**——其 ST HAL 缺少厂商命令引擎（`stpropnci`），
  且实测无法通过替换 HAL/固件/服务二进制移植；小米 17（pudding）原生支持。对比数据与移植清单见 [§10](#10-小米-15-prost54l移植评估)。

---

## 1. 工作原理

### 1.1 壳子只等 7-bit `0x7A`

普通 NFC 读卡器发 `WUPA(0x52)`，壳子不应答；它等待的是一帧 **7 bit 的 `0x7A`**。
NXP SN100/SN220 固件里的 **Q-Poll** 私有寻卡模式正好发送这个短帧，用 NCI 的
`RF technology = 0x71` 表示。

### 1.2 Android 的问题

NFA（`libsn100nfc-nci.so`）只认识标准 NFC-A `0x00`：

- 发 discover 时不会带 `0x71`；
- 收到 `0x71` 的 discover / activate 通知时不会建 Tag，而是直接 deactivate。

### 1.3 三处映射（缺一不可）

| 位置 | 函数 | 改写 |
| --- | --- | --- |
| 发送 RF_DISCOVER | `nfc_ncif_send_cmd` | `21 03 ...` 里 tech `0x00` → `0x71` |
| 接收 RF_DISCOVER_NTF | `nfc_ncif_proc_discover_ntf` | `61 03 ...` 第 5 字节 `0x71` → `0x00` |
| 接收 RF_INTF_ACTIVATED_NTF | `nfc_ncif_proc_activate` | payload 里 `0x71` → `0x00` |

> **最容易漏的是第三处**：只改 discover 时，控制器会正常激活 `0x71`，但 NFA 立刻主动
> deactivate，表现为「永远收不到标签」。`nfc_ncif_proc_activate` 收到的是**不含 NCI 头**的
> payload（以 discovery id 开头），所以要在前 8 字节里扫 `0x71`。

### 1.4 NXP `NFC_HDR` 的坑

`nfc_ncif_send_cmd(NFC_HDR*)` 的 payload 在 **`hdr + 8 + offset`**，不是 `hdr + offset`。
`offset` 通常为 1；按错位置读会永远读不到 `21 03`。

---

## 2. 架构

```
com.android.nfc (zygote 子进程, uid=1027)
 ├─ Zygisk 模块 zygisk/arm64-v8a.so     postAppSpecialize 里判断 uid
 │    └─ dlopen("/system/lib64/libgadget.so")
 ├─ frida-gadget (/system/lib64)         读取 libgadget.config.so
 │    └─ 加载 /system/lib64/nfcq-hook.js  （脚本运行时）
 └─ hook.js 挂 libsn100nfc-nci.so 的三个函数，做 1.3 的字节改写
       └─ 证据写入 /data/user/0/com.android.nfc/files/hook.log
```

### 为什么 gadget 必须放在 `/system/lib64`

这是本项目踩得最深的坑：

1. 放 `/data/user/0/com.android.nfc/files/`（app 私有目录）：SELinux `nfc_data_file` **禁止 execute**，
   `dlopen` 报 `couldn't map segment 1: Permission denied`。
2. 放模块目录 `/data/adb/modules/nfc-qpoll/gadget/`：**`/data/adb` 对 app 域不可穿越**，
   nfc 进程 `read()` 就是 `EACCES`，`dlopen` 只报模糊的 `library not found`。
   （Zygisk 自己的 so 能加载，是因为 zygote 以 root 打开、fork 继承 fd。）
3. 放模块的 `system/lib64/`，由 magic mount 挂到 `/system/lib64/`：标签 `system_lib_file`，
   app 域可读可执行 —— **唯一可行**。

### 为什么不用 frida-server

frida-server 方案需要 PC 常驻、且与 gadget 同进程会冲突。Zygisk + gadget 开机自动生效，
不需要电脑。

---

## 3. 文件结构

```
nfc-qpoll-ksu/
├─ README.md
├─ LICENSE
├─ NOTICE.md
├─ build.ps1                     # 一键构建（NDK + Python）
├─ jni/
│  ├─ module.cpp                 # Zygisk 模块：按 uid 加载 gadget
│  └─ zygisk.hpp                 # Zygisk API 头（来自 Magisk，见 NOTICE）
├─ gadget/
│  ├─ hook.js                    # 核心 hook 脚本
│  ├─ libgadget.config.so        # gadget 配置（指向 /system/lib64/nfcq-hook.js）
│  └─ get_gadget.py              # 下载并解压 frida-gadget
└─ module/                       # 刷入用的模块骨架
   ├─ module.prop
   └─ service.sh
```

构建产物：

```
build/
├─ zygisk/arm64-v8a.so
├─ module/                       # 完整模块目录
└─ nfc-qpoll.zip                 # 可刷入包
```

---

## 4. 构建

依赖：

- Android NDK（r25c 测试通过），需含 `clang++`
- Python 3（下载 gadget、打包 zip）
- Windows PowerShell（或按下面命令手动执行）

```powershell
# 指定 NDK 路径，或先设置 $env:ANDROID_NDK_HOME
.\build.ps1 -Ndk "D:\Android\Sdk\ndk\25.2.9519653"
```

脚本会：

1. 编译 `jni/module.cpp` → `build/zygisk/arm64-v8a.so`
2. 若 `gadget/libgadget.so` 不存在，调用 `gadget/get_gadget.py` 下载 frida-gadget 17.24.3 并解压
3. 组装 `build/module/` 并打成 `build/nfc-qpoll.zip`

手动编译等价命令：

```sh
$NDK/toolchains/llvm/prebuilt/windows-x86_64/bin/clang++ \
  --target=aarch64-linux-android21 -shared -fPIC -O2 \
  -fno-exceptions -fno-rtti -static-libstdc++ \
  -o build/zygisk/arm64-v8a.so jni/module.cpp -llog
```

> **必须带 `-llog`**。缺了它 `__android_log_print` 解析失败，Zygisk Next 会**静默跳过**整个模块
> （既没日志也没映射），极难排查。

---

## 5. 安装

1. 手机需 **KernelSU / Magisk + Zygisk Next**（本项目在 KernelSU + Zygisk Next 1.5.0 上验证）
2. 刷入 `build/nfc-qpoll.zip`，重启
3. 确认模块未被禁用（`/data/adb/modules/nfc-qpoll/` 下没有 `disable` 文件）

验证：

```sh
adb shell su -c 'tail -5 /data/user/0/com.android.nfc/files/hook.log'
```

应看到：

```
hook.js loaded, waiting for NCI lib
target libsn100nfc-nci.so base=0x...
hook ok process_event / send_cmd / discover / activate
hooks installed
```

寻卡时出现：

```
TX-PATCH 21 03 0d 06 71 01 ...
discover RX-PATCH [5] 61 03 0f 01 04 00 ...
activate RX-PATCH [3] 01 02 04 00 ...
```

---

## 6. 使用

1. 安装前台模式的 Q-Poll Lab（`org.nfcresearch.qpolllab`，需以 App 自身 UID 调用 ReaderMode）
2. 打开 App → 选图 → 把壳子贴到手机 NFC 区域 → 刷图
3. 日志里能看到 `D1/D8/D3/D4/DE` 的 APDU 交互；`DE` 返回 `009000` 表示刷新完成

> App 里「Q-Poll：尚未确认」是基于 HAL 日志的判定（要求日志出现 `2103..71`），
> 与实际是否拿到 Tag 无关，可忽略。

---

## 7. 风险与已知问题

**使用前请确认你接受以下风险。**

1. **普通 NFC 会受影响**：模块把 discover 里的 NFC-A(`0x00`) 全部替换成 `0x71`，
   启用期间普通 NFC-A 标签/门禁卡扫不到。需要日常 NFC 时请禁用模块并重启。
2. **依赖 Zygisk**：需要 KernelSU/Magisk + Zygisk Next；Zygisk 关闭或模块被禁用后功能失效。
3. **39 MB gadget**：frida-gadget 会映射进 `com.android.nfc`，增加内存占用与启动时间。
4. **frida 特征**：进程内存在 frida-gadget（线程名、字符串），可能被某些 App 或风控检测；
   支付类 App 可能拒绝在有 hook 的环境下工作。
5. **系统更新/换 ROM 可能失效**：
   - NCI 库名可能不同（脚本会尝试 `libsn100nfc-nci.so` / `libnfc_nci_jni.so`）；
   - 符号被裁剪或改名时 hook 会失败（日志出现 `missing ...`）；
   - `/vendor`、SELinux 策略变化可能让模块目录不可用。
6. **不要在 `onLoad` 里起线程**：早期版本在 `onLoad` 中 `pthread_create`，导致 zygote 在
   specialize `system_server` 时 `selinux_android_setcontext` 失败并进入 **boot loop**。
   当前实现只在 `postAppSpecialize` 里做一次 `dlopen`，不要改成异步/线程。
7. **不保证通用**：仅在 Redmi Note 12 Turbo（marble / NXP SN110T / Android 15）验证。
   其它机型需自行确认库名、符号与 SELinux 行为。
8. **刷机风险自负**：模块会修改 `/system` 的 overlay 视图（不改真实分区），但仍建议先备份、
   确认能进 recovery/fastboot。NFC 异常时删除模块目录并重启即可恢复。
9. **合规**：仅用于你本人拥有的设备与配件；请遵守当地法律与配件厂商条款。

---

## 8. 排错

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `hook.log` 不存在 | gadget 没被加载 | 确认 Zygisk Next 已启用、模块未禁用；`ls /system/lib64/libgadget.so` 是否存在 |
| `dlopen ... not found` | gadget 不在 `/system/lib64` | 检查模块 `system/lib64/` 是否被 magic mount（重启后 `ls /system/lib64/libgadget.so`） |
| `denied { execute }` | gadget 放在了 app 私有目录 | 必须走 `/system/lib64` overlay |
| 有 `TX-PATCH` 但收不到标签 | activate 补丁没生效 / 库名不匹配 | 看日志是否有 `activate RX-PATCH`；确认 `target libsn100nfc-nci.so` |
| `missing _Z...` | 目标库符号被裁剪 | 用 `readelf --dyn-syms` 对照库导出符号，改 `gadget/hook.js` |
| `waiting for NCI lib` 一直不结束 | 该 ROM 的 NCI 库名不同 | 在 `hook.js` 的 `CANDIDATES` 里加库名 |
| NFC 服务反复重启 | 模块与 ROM 不兼容 | 删除 `/data/adb/modules/nfc-qpoll` 并重启 |
| 刷图低电压（`6502/68CA`） | 壳子取电不足 | 调整贴合位置，保持全程贴合 |

---

## 9. 兼容性

| 设备 | 控制器 | 状态 |
| --- | --- | --- |
| Redmi Note 12 Turbo (marble) | NXP SN110T | ✅ 真机验证可刷图 |
| 其它 NXP SN100/SN220 机型 | NXP | ⚠️ 理论可行，需自行确认库名/符号 |
| 小米 17 (pudding) | ST54L | ✅ 原厂即支持（`stpropnci` HAL + 新固件），无需本模块 |
| 小米 15 Pro (haotian, Android 16) | ST54L | ❌ HAL 无厂商命令引擎，`oid=1 0x15/0x13` 返回 `150B/1305` |
| 小米 15 Pro (haotian, OS4.0 / Android 17) | ST54L | ❌ HAL 与 OS3 基本相同，刷系统也不会改善 |

> 小米 15 Pro 的完整对比、移植尝试与缺失依赖见 [§10](#10-小米-15-prost54l移植评估)。

---

## 10. 小米 15 Pro（ST54L）移植评估

**结论：文件级移植不可行，不建议投入。** 下面是实测数据与原因，供后来者参考。

### 10.1 调用链

```
NfcService (com.android.nfc)
  └─ sendVendorNciMessage(gid=0x0F, oid=1, [subcmd, ...])
       └─ HIDL android.hardware.nfc@1.2
            └─ /odm/bin/hw/android.hardware.nfc-service-st   ← init 启动的 vendor 服务
                 └─ dlopen /odm/lib64/nfc_nci.st21nfc.st.so  ← ST HAL
                      └─ /dev/st21nfc (I2C) → CLF 固件 /odm/firmware/st54l_fw.bin
```

`0x13/0x15` 这类厂商命令由 HAL 的 `stpropnci_*` 引擎处理后再下发给 CLF；15 Pro 的 HAL
**没有**这套引擎，命令直接得到 `0x0B`（不支持），换固件也不会出现。

### 10.2 固件对比（实取数据）

| | haotian OS3.0 (Android 16) | haotian OS4.0.0.19 (Android 17) | pudding OS4.0.0.32 (Android 17) | pudding OS3.0.319.0 (Android 16) |
| --- | --- | --- | --- | --- |
| `nfc_nci.st21nfc.st.so` | 200,560 B | 200,560 B | 283,656 B | 267,048 B |
| 导出符号数 | 343 | 345 | 449 | — |
| `stpropnci_*` 引擎 | ❌ 无 | ❌ 无 | ✅ 30 个符号 | ✅ 30 个符号 |
| `st54l_fw.bin` | 250,917 B | 未取到 | 260,157 B | 260,157 B |
| 固件 SHA-256 | `15da4aa9…` | — | `22a9e85d…` | `22a9e85d…`（与 OS4 相同） |
| `libnfc-hal-st.conf` | 6,282 B | 6,282 B（与 OS3 逐字节相同） | 7,177 B | 7,177 B |
| `nfc-service-st` | 86,376 B | 未取到 | 86,400 B | 86,400 B |

关键结论：

1. **OS4 对 15 Pro 没有意义**：haotian 的 OS4 HAL 与 OS3 只有 2 个符号差异
   （`mParamReset`、`property_get`），字符串仅删了几句 `clear/reset FW download status`，
   同样没有 `stpropnci`。
2. **小米 17 的差别是整套的**：HAL 换了实现（+106 KB）、固件换了版本（+9.2 KB）、
   配置与 service 二进制也不同。它出厂就支持墨水屏壳。

### 10.3 子命令实测（15 Pro，Android 16，暂停轮询后）

`NfcAdapter.sendVendorNciMessage(1, 15, 1, payload)`，payload 为单字节子命令：

| 子命令 | 响应 | 含义 |
| --- | --- | --- |
| `0x02` | `0200 0603 0204 1188 03020100 44507000` | 读取配置/版本信息，可用 |
| `0x03` | `03000186` | 可用 |
| `0x10` / `0x11` / `0x12` | `…00` | 接受 |
| `0x13` | `1302` / `1305` | 存在，但参数/状态被拒 |
| `0x15` | `150B` | **不支持**（ink-nfc-lab 用它读轮询帧） |
| `0x14` / `0x16`–`0x1F` | `…0B` | 不支持 |

尝试用 `Protocol.polling7A()` 的原始字节 `01 2A 02 0A 7A` 作为 `0x13` 参数：

```
1300                    → 1305
13012A020A7A            → 1305
13012A020A7A00          → 1305
13012A020A7A0000        → 1305
13012A020A7A10          → 1305
```

即 `0x13` 存在但 HAL/CLF 不接受这组轮询帧参数——这条路在 15 Pro 上走不通。

### 10.4 移植尝试与结果

三次都通过 KSU 模块 + `mount --bind` 覆盖 `/odm`，改完 `kill` 掉 HAL 让 init 重启：

| # | 覆盖内容 | 结果 |
| --- | --- | --- |
| 1 | pudding OS4 HAL + fw + conf | `init.svc.nfc_hal_service = restarting`，无 tombstone |
| 2 | pudding OS3（同为 Android 16）HAL + fw + conf | 同样 `restarting` |
| 3 | pudding OS3 service 二进制 + HAL + fw + conf | 仍然 `restarting` |

回滚方式（立即生效，不用重启）：

```sh
umount /odm/bin/hw/android.hardware.nfc-service-st
umount /odm/lib64/nfc_nci.st21nfc.st.so
umount /odm/firmware/st54l_fw.bin
umount /odm/etc/libnfc-hal-st.conf
setprop ctl.restart nfc_hal_service
```

回滚后 `dumpsys nfc` 应恢复 `mState=on`，HAL 进程正常。

> 注意：`/data` 为 f2fs + `inline_data`/压缩的机型，`losetup` + `mount -t erofs` 可能
> 报 `I/O error`；先 `setenforce 0` 并手动 `mknod` 出正确 minor 的 loop 节点
> （该内核 minor = 序号 × 8）可绕过。仅用于解包，别长期保持 permissive。

### 10.5 还缺什么（移植一整套 vendor 子系统的清单）

| 层 | 需要的组件 | 状态 |
| --- | --- | --- |
| `/odm/bin/hw` | `android.hardware.nfc-service-st` | ✅ 已取到并替换，仍失败 |
| `/odm/lib64` | `nfc_nci.st21nfc.st.so`（`stpropnci` 版） | ✅ 已取到并替换 |
| `/odm/firmware` | `st54l_fw.bin`（260,157 B） | ✅ 已取到并替换 |
| `/odm/etc` | `libnfc-hal-st.conf`、`st54l_conf.txt` | ✅ 已替换 |
| `/vendor/lib64` | `libstnfc-auth.so`、`libstnfc-streset.so` 等 ST 私有库 | ⚠️ 两机版本不同，未替换 |
| init rc | `/odm/etc/init/*nfc*.rc`（user/group/capabilities/seclabel） | ⚠️ 可能不同 |
| 属性 | `ro.hardware.nfc`、`ro.vendor.*`、机型校验 | ⚠️ HAL 可能校验 |
| 框架 | `NfcService`/`NfcNci` + `com.st.android.nfc_extensions_16` | ⚠️ QTag 接口可能在这层 |
| SELinux | `hal_nfc_default_exec`、`vendor_file`、`vendor_configs_file` | ✅ 已按原标签设置 |
| 内核/驱动 | `/dev/st21nfc`、I2C 时序、CLF 接口 | ⚠️ 同 ST54L，理论上兼容 |

即使把 `⚠️` 全部补齐，也要处理 HAL 启动崩溃、eSE/公交卡/门禁回归、开机稳定性；
**最坏情况是 NFC 与安全元件一起不可用**，且这种 vendor 层改动不能靠“删模块”完全回滚。

### 10.6 建议

- 需要驱动墨水屏壳：用 **NXP SN110T 机型（如 marble）** + 本项目模块，已验证；
- 小米 15 Pro：等 OEM 在后续版本换成 17 同款 ST HAL（OS4.0.0.19 尚未换），
  或另找一台可随意刷机的 15 Pro 做实验机再尝试整包移植；
- 不要在主力的 15 Pro 上做 vendor 层替换。

---

## 11. 卸载

KernelSU/Magisk 里禁用或卸载模块，然后重启。overlay 消失后系统即恢复原厂 NFC 行为。

手动：

```sh
adb shell su -c 'rm -rf /data/adb/modules/nfc-qpoll && reboot'
```

---

## 12. 许可与致谢

- 本项目代码（`jni/module.cpp`、`gadget/hook.js`、脚本）：MIT，见 `LICENSE`
- `jni/zygisk.hpp`：Copyright 2022-2023 John "topjohnwu" Wu，ISC 风格许可，见文件头与 `NOTICE.md`
- `frida-gadget`：LGPL-3.0，构建时从官方 release 下载，**不随仓库分发**
- 协议与设备行为参考：
  - [ZhaoGY-N/huawei-nfc-eink-android-app](https://github.com/ZhaoGY-N/huawei-nfc-eink-android-app)
  - [wiwiwei/ink-nfc-lab](https://github.com/wiwiwei/ink-nfc-lab)
  - [kur0neko/huawei-epd-pn532](https://gitee.com/kur0neko/huawei-epd-pn532)
