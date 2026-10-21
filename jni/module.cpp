// Minimal: uid-based targeting (nice_name is not always available), no threads.
// gadget is served from the module's /system overlay so the nfc domain can
// actually open/execute it (/data/adb is not traversable for app domains).
#include <jni.h>
#include <android/log.h>
#include <dlfcn.h>
#include <unistd.h>
#include <cerrno>
#include <cstring>

#include "zygisk.hpp"

#define TAG "NfcQ"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, TAG, __VA_ARGS__)

static const char *kGadget = "/system/lib64/libgadget.so";

class NfcQModule : public zygisk::ModuleBase {
public:
    void onLoad(zygisk::Api *api, JNIEnv *env) override {
        api_ = api;
        env_ = env;
    }

    void postAppSpecialize(const zygisk::AppSpecializeArgs *args) override {
        jint uid = args->uid;
        if (uid != 1027) return;
        const char *name = nullptr;
        if (env_ != nullptr && args->nice_name != nullptr) {
            name = env_->GetStringUTFChars(args->nice_name, nullptr);
        }
        LOGI("nfc target pid=%d uid=%d jni=%s", getpid(), uid, name ? name : "(null)");
        if (name != nullptr) env_->ReleaseStringUTFChars(args->nice_name, name);
        void *h = dlopen(kGadget, RTLD_NOW | RTLD_LOCAL);
        LOGI("dlopen %s -> %s", kGadget, h ? "ok" : dlerror());
    }

private:
    zygisk::Api *api_ = nullptr;
    JNIEnv *env_ = nullptr;
};

REGISTER_ZYGISK_MODULE(NfcQModule)
