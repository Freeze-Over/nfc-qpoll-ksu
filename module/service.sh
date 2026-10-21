#!/system/bin/sh
# Zygisk + frida-gadget 注入 com.android.nfc：
#   zygisk/arm64-v8a.so         Zygisk 模块，uid=1027 时 dlopen gadget
#   system/lib64/libgadget.so   经 magic mount 挂到 /system/lib64，nfc 域可执行
#   system/lib64/nfcq-hook.js   gadget 启动时加载的 hook 脚本
LOG=/data/local/tmp/nfcq.log
echo "=== $(date) nfc-qpoll service start ===" >> "$LOG"
ls -lZ /system/lib64/libgadget.so /system/lib64/nfcq-hook.js >> "$LOG" 2>&1
until [ "$(getprop sys.boot_completed)" = "1" ]; do sleep 1; done
sleep 5
echo "--- hook.log ---" >> "$LOG"
tail -n 5 /data/user/0/com.android.nfc/files/hook.log >> "$LOG" 2>&1
echo "=== service done ===" >> "$LOG"
