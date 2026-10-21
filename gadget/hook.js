// Runs inside com.android.nfc via frida-gadget (loaded by Zygisk module nfc-qpoll).
// NCI 0x71 is Huawei "Q-Poll": NFA does not know it, so translate at the NCI
// boundary: outgoing RF_DISCOVER tech 0x00 -> 0x71, incoming 0x71 -> 0x00.
var CANDIDATES = ["libsn100nfc-nci.so", "libnfc_nci_jni.so"];
var LOG = "/data/user/0/com.android.nfc/files/hook.log";
var MAX_DUMP = 60;
var dumped = 0;

function log(msg) {
    try {
        var f = new File(LOG, "a");
        f.write("[" + new Date().toISOString() + "] " + msg + "\n");
        f.flush();
        f.close();
    } catch (e) {}
    try { console.log("NfcQ " + msg); } catch (e) {}
}

function hex(b, n) {
    var out = [];
    for (var i = 0; i < n && i < b.length; i++) {
        var h = b[i].toString(16);
        out.push(h.length < 2 ? "0" + h : h);
    }
    return out.join(" ");
}

function patchDiscover(b) {
    if (b.length < 4) return false;
    var num = b[3], changed = false;
    for (var i = 0; i < num; i++) {
        var o = 4 + i * 2;
        if (o + 1 < b.length && b[o] === 0x00 && b[o + 1] === 0x01) {
            b[o] = 0x71;
            changed = true;
        }
    }
    return changed;
}

function hookNtf(mod, name, idx, tag) {
    var fn;
    try {
        fn = mod.getExportByName(name);
    } catch (e) {
        log("missing " + name);
        return;
    }
    var seen = 0;
    Interceptor.attach(fn, {
        onEnter: function (args) {
            try {
                var p = args[0];
                var b = new Uint8Array(p.readByteArray(16));
                if (seen < 20) {
                    seen++;
                    log(tag + " NTF " + hex(b, 16));
                }
                // discover_ntf receives the full NCI message (0x61 ...);
                // activate receives the payload only (starts at discovery id).
                if (b[0] === 0x61 && idx > 0 && b[idx] === 0x71) {
                    b[idx] = 0x00;
                    p.writeByteArray(Array.prototype.slice.call(b));
                    log(tag + " RX-PATCH [" + idx + "] " + hex(b, 16));
                } else if (b[0] !== 0x61) {
                    // Vendor Q-Poll activation: rewrite the tech byte so NFA can
                    // build an NFC-A tag instead of dropping the notification.
                    for (var i = 0; i < 8; i++) {
                        if (b[i] === 0x71) {
                            b[i] = 0x00;
                            p.writeByteArray(Array.prototype.slice.call(b));
                            log(tag + " RX-PATCH [" + i + "] " + hex(b, 16));
                            break;
                        }
                    }
                }
            } catch (e) {}
        }
    });
    log("hook ok " + tag);
}

function install(mod) {
    log("target " + mod.name + " base=" + mod.base);

    // Probe: is the framework NCI stack moving any traffic at all?
    try {
        var ev = mod.getExportByName("_Z22nfc_ncif_process_eventP7NFC_HDR");
        Interceptor.attach(ev, {
            onEnter: function (args) {
                try {
                    if (dumped >= MAX_DUMP) return;
                    dumped++;
                    var h = new Uint8Array(args[0].readByteArray(16));
                    log("EVT hdr=" + hex(h, 16));
                } catch (e) {}
            }
        });
        log("hook ok process_event");
    } catch (e) {
        log("no process_event: " + e);
    }

    // Probe + TX patch on the command path.
    var sendCmd = mod.getExportByName("_Z17nfc_ncif_send_cmdP7NFC_HDR");
    var sent = 0;
    Interceptor.attach(sendCmd, {
        onEnter: function (args) {
            try {
                var hdr = args[0];
                var hb = new Uint8Array(hdr.readByteArray(16));
                var event = hdr.readU16();
                var total = hdr.add(2).readU16();
                var off = hdr.add(4).readU16();
                if (sent < MAX_DUMP) {
                    sent++;
                    log("CMD event=" + event + " len=" + total + " off=" + off + " hdr=" + hex(hb, 16));
                }
                // NXP NFC_HDR is 8 bytes; the payload starts at 8 + offset.
                if (off > 64 || total < 3 || total > 255) return;
                var p = hdr.add(8).add(off);
                var b = new Uint8Array(p.readByteArray(total));
                if (b[0] === 0x21 && b[1] === 0x03 && patchDiscover(b)) {
                    p.writeByteArray(Array.prototype.slice.call(b));
                    log("TX-PATCH " + hex(b, Math.min(total, 24)));
                }
            } catch (e) {}
        }
    });
    log("hook ok send_cmd");

    hookNtf(mod, "_Z26nfc_ncif_proc_discover_ntfPht", 5, "discover");
    hookNtf(mod, "_Z22nfc_ncif_proc_activatePhh", 6, "activate");
    log("hooks installed");
}

function findTarget() {
    for (var i = 0; i < CANDIDATES.length; i++) {
        try {
            return Process.getModuleByName(CANDIDATES[i]);
        } catch (e) {}
    }
    return null;
}

var done = false;
var timer = null;

function tick() {
    if (done) return;
    var mod = findTarget();
    if (mod === null) return;
    done = true;
    try {
        install(mod);
    } catch (e) {
        log("install error: " + e);
    }
}

log("hook.js loaded, waiting for NCI lib");
tick();
if (!done) {
    timer = setInterval(function () {
        tick();
        if (done) {
            clearInterval(timer);
            timer = null;
        }
    }, 200);
}
