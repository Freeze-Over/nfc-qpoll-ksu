# Third-party notices

本仓库只包含自己编写的代码。以下组件由外部提供，遵循各自许可。

## jni/zygisk.hpp

Copyright 2022-2023 John "topjohnwu" Wu

Zygisk API 头文件，随 Magisk 分发。许可文本见文件头：

> Permission to use, copy, modify, and/or distribute this software for any
> purpose with or without fee is hereby granted.
>
> THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES ...

上游：https://github.com/topjohnwu/Magisk

## frida-gadget

本项目在构建时（`gadget/get_gadget.py`）从 Frida 官方 release 下载
`frida-gadget-17.24.3-android-arm64.so`，**不随仓库分发**。

Frida 以 LGPL-3.0 发布，另有部分组件为其他许可，详见：
https://github.com/frida/frida#license

运行时如果重新分发打包好的模块 zip（内含 gadget），请自行确认 LGPL 的合规要求。

## Zygisk Next / KernelSU / Magisk

模块依赖用户设备上已安装的 Zygisk 实现与 root 方案，本项目不包含它们的代码。

## 协议与设备行为参考

- ZhaoGY-N/huawei-nfc-eink-android-app（PolyForm Noncommercial 1.0.0）
- wiwiwei/ink-nfc-lab（PolyForm Noncommercial 1.0.0）
- kur0neko/huawei-epd-pn532（PolyForm Noncommercial 1.0.0）

本项目未复制上述项目的代码，仅在文档中描述其协议结论（NCI 帧格式、APDU 命令等），
这些属于接口事实。若你计划商用，请自行评估相关专利与许可风险。
