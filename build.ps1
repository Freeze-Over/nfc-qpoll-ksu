<#
.SYNOPSIS
    Build the nfc-qpoll KernelSU module.

.DESCRIPTION
    Compiles the Zygisk module, fetches frida-gadget on first run, assembles the
    module directory and packs build/nfc-qpoll.zip.

.PARAMETER Ndk
    Android NDK root (contains toolchains/llvm). Defaults to $env:ANDROID_NDK_HOME.

.PARAMETER OutDir
    Output directory, defaults to .\build

.PARAMETER Python
    Python 3 executable, defaults to "python".

.EXAMPLE
    .\build.ps1 -Ndk "D:\Android\Sdk\ndk\25.2.9519653"
#>
[CmdletBinding()]
param(
    [string]$Ndk = $env:ANDROID_NDK_HOME,
    [string]$OutDir,
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
if (-not $root) { $root = Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not $OutDir) { $OutDir = Join-Path $root "build" }

if (-not $Ndk) {
    throw "Android NDK not specified. Pass -Ndk <path> or set `$env:ANDROID_NDK_HOME."
}

$clangCandidates = @(
    (Join-Path $Ndk "toolchains\llvm\prebuilt\windows-x86_64\bin\clang++.exe"),
    (Join-Path $Ndk "toolchains\llvm\prebuilt\linux-x86_64\bin\clang++"),
    (Join-Path $Ndk "toolchains\llvm\prebuilt\darwin-x86_64\bin\clang++")
)
$clang = $clangCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $clang) { throw "clang++ not found under $Ndk" }

Write-Host "[1/4] compiling zygisk module"
New-Item -ItemType Directory -Force -Path (Join-Path $OutDir "zygisk") | Out-Null
& $clang "--target=aarch64-linux-android21" "-shared" "-fPIC" "-O2" `
    "-fno-exceptions" "-fno-rtti" "-static-libstdc++" `
    "-o" (Join-Path $OutDir "zygisk\arm64-v8a.so") `
    (Join-Path $root "jni\module.cpp") "-llog"
if ($LASTEXITCODE -ne 0) { throw "clang++ failed with exit code $LASTEXITCODE" }

Write-Host "[2/4] checking frida-gadget"
$gadget = Join-Path $root "gadget\libgadget.so"
if (-not (Test-Path $gadget)) {
    & $Python (Join-Path $root "gadget\get_gadget.py")
    if ($LASTEXITCODE -ne 0) { throw "gadget download failed" }
}

Write-Host "[3/4] assembling module"
$mod = Join-Path $OutDir "module"
Remove-Item -Recurse -Force $mod -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path (Join-Path $mod "zygisk"), (Join-Path $mod "system\lib64") | Out-Null
Copy-Item (Join-Path $root "module\module.prop") $mod
Copy-Item (Join-Path $root "module\service.sh") $mod
Copy-Item (Join-Path $OutDir "zygisk\arm64-v8a.so") (Join-Path $mod "zygisk\arm64-v8a.so")
Copy-Item $gadget (Join-Path $mod "system\lib64\libgadget.so")
Copy-Item (Join-Path $root "gadget\libgadget.config.so") (Join-Path $mod "system\lib64\libgadget.config.so")
Copy-Item (Join-Path $root "gadget\hook.js") (Join-Path $mod "system\lib64\nfcq-hook.js")

Write-Host "[4/4] packing zip"
& $Python (Join-Path $root "tools\pack_module.py") $mod (Join-Path $OutDir "nfc-qpoll.zip")
if ($LASTEXITCODE -ne 0) { throw "pack failed" }

Write-Host ""
Write-Host "done: $(Join-Path $OutDir 'nfc-qpoll.zip')"
