import hashlib
import io
import os
import platform
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from subprocess import CalledProcessError, run

import requests
from github import Github

if (
    platform.system() == "Linux"
    and platform.freedesktop_os_release()["ID_LIKE"].lower() == "debian"
):
    try:
        import apt
    except ImportError:
        sys.exit("python3-apt is not installed. Please install it first")

build_android = False
build_arm64_linux = False
build_x64_linux = False
build_ios = False
build_ios_simulator = False
build_macos = False
build_arm64_windows = False
build_x64_windows = False
build_angelscript_nc = False
use_official_steam_audio = False
vcpkg_path = (
    Path.cwd() / "vcpkg" / "bin" / ("vcpkg" if sys.platform != "win32" else "vcpkg.exe")
)
oldenv = {}
orig_cwd = Path.cwd()
os.environ["VCPKG_OVERLAY_PORTS"] = str((Path() / "vcpkg" / "ports").resolve())
os.environ["VCPKG_OVERLAY_TRIPLETS"] = str((Path() / "vcpkg" / "triplets").resolve())


def bootstrap_vcpkg() -> None:
    if vcpkg_path.exists() and vcpkg_path.is_file():
        return

    # Check if vcpkg submodule is initialized
    vcpkg_repo_path = Path(orig_cwd) / "vcpkg"
    if (
        not (vcpkg_repo_path / ".git").exists()
        and not (vcpkg_repo_path / "bin" / ".git").exists()
    ):
        print("Initializing vcpkg submodule...")
        run(
            ["git", "submodule", "update", "--init", "--recursive"],
            cwd=orig_cwd,
            check=True,
        )

    # Find where bootstrap script actually is
    bootstrap_dir = vcpkg_repo_path
    if (vcpkg_repo_path / "bin" / "bootstrap-vcpkg.sh").exists():
        bootstrap_dir = vcpkg_repo_path / "bin"
    elif not (vcpkg_repo_path / "bootstrap-vcpkg.sh").exists():
        # Try to find it
        for item in vcpkg_repo_path.rglob("bootstrap-vcpkg.sh"):
            bootstrap_dir = item.parent
            break

    print("Bootstrapping vcpkg...")
    os.chdir(bootstrap_dir)
    if platform.system() == "Windows":
        run("bootstrap-vcpkg.bat", check=True)
    else:
        run("./bootstrap-vcpkg.sh", check=True)

    os.chdir(orig_cwd)
    print("Done")


def find_ndk() -> None:
    env_vars = ["ANDROID_NDK_ROOT", "ANDROID_NDK_HOME", "ANDROID_NDK", "NDK_ROOT"]
    for var in env_vars:
        path = os.environ.get(var)
        if path and Path(path).exists():
            return path

    home = Path.home()
    common_paths = []

    if platform.system() == "Windows":
        common_paths = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Android/Sdk/ndk",
            home / "AppData/Local/Android/Sdk/ndk",
            Path("C:/Android/sdk/ndk"),
        ]
    elif platform.system() == "Darwin":
        common_paths = [home / "Library/Android/sdk/ndk"]
    else:
        common_paths = [home / "Android/Sdk/ndk", Path("/opt/android-sdk/ndk")]

    for base_path in common_paths:
        if base_path.exists():
            for ndk_dir in base_path.iterdir():
                if ndk_dir.is_dir() and (ndk_dir / "source.properties").exists():
                    return str(ndk_dir)

    return None


def build_packages_for_android() -> None:
    android_ndk_home = find_ndk()
    if android_ndk_home is None:
        # TODO (ethindp): maybe download the NDK?
        sys.exit(
            "Android NDK not found. Please install it on this system to build for android.",
        )
    if os.environ.get("ANDROID_NDK_HOME") is None:
        os.environ["ANDROID_NDK_HOME"] = android_ndk_home
    print("Building android packages, this will take a while...")
    try:
        run(
            [
                vcpkg_path,
                "install",
                "--triplet",
                "arm64-android",
                "enet6[*]",
                "libflac",
                "curl[http2,openssl]",
                "libffi",
                "miniupnpc[*]",
                "libogg",
                "opus[*]",
                "libvorbis[*]",
                "poco[crypto,net,netssl,json,util,xml,zip,encodings,mongodb,redis,jwt,prometheus,sevenzip]",
                "angelscript-nc" if build_angelscript_nc else "angelscript",
            ],
            check=True,
        )
    except CalledProcessError as cpe:
        sys.exit(
            f"Android packages installation failed, code {cpe.returncode}",
        )
    try:
        run(
            [
                vcpkg_path,
                "install",
                "--triplet",
                "arm64-android-dynamic",
                "sdl3[vulkan]",
                "sdl3-ttf[core,svg]",
                "sdl3-image[*]",
                "" if not use_official_steam_audio else "steam-audio",
                "freetype[core,bzip2,error-strings,png,subpixel-rendering,zlib]",
            ],
            check=True,
        )
    except CalledProcessError as cpe:
        sys.exit(
            f"Android packages installation failed, code {cpe.returncode}",
        )
    print("Done")
    print("Generating droiddev package...")
    out_dir = Path(orig_cwd / "build" / "packages" / "droiddev")
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        vcpkg_path.parent / "installed" / "arm64-android" / "include",
        out_dir / "include",
        dirs_exist_ok=True,
    )
    shutil.copytree(
        vcpkg_path.parent / "installed" / "arm64-android" / "lib",
        out_dir / "lib",
        dirs_exist_ok=True,
    )
    shutil.copytree(
        vcpkg_path.parent / "installed" / "arm64-android" / "debug",
        out_dir / "debug",
        dirs_exist_ok=True,
    )
    shutil.copytree(
        vcpkg_path.parent / "installed" / "arm64-android-dynamic" / "include",
        out_dir / "include",
        dirs_exist_ok=True,
    )
    shutil.copytree(
        vcpkg_path.parent / "installed" / "arm64-android-dynamic" / "lib",
        out_dir / "lib",
        dirs_exist_ok=True,
    )
    shutil.copytree(
        vcpkg_path.parent / "installed" / "arm64-android-dynamic" / "debug",
        out_dir / "debug",
        dirs_exist_ok=True,
    )
    if use_official_steam_audio:
        gh = Github()
        repo = gh.get_repo("ValveSoftware/steam-audio")
        release = repo.get_latest_release()
        zip_asset = None
        # TODO (ethindp): refine this
        for asset in release.get_assets():
            if asset.name.startswith("steamaudio_") and asset.name.endswith(".zip"):
                zip_asset = asset
                break
        if zip_asset is None:
            sys.exit("Official steam audio zip asset could not be found")
        response = requests.get(zip_asset.browser_download_url, timeout=30)
        response.raise_for_status()
        zip_data = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_data) as zf:
            zf.extract(
                "steamaudio/lib/android-armv8/libphonon.so",
                path=str((out_dir / "lib").resolve()),
            )
            zf.extract(
                "steamaudio/include/phonon.h",
                path=str((out_dir / "include").resolve()),
            )
            zf.extract(
                "steamaudio/include/phonon_interfaces.h",
                path=str((out_dir / "include").resolve()),
            )
            zf.extract(
                "steamaudio/include/phonon_version.h",
                path=str((out_dir / "include").resolve()),
            )
    shutil.make_archive("droiddev", format="zip", root_dir=out_dir, base_dir="droiddev")
    with (
        Path("droiddev.zip").open("rb") as f,
        Path("droiddev.zip.blake2b").open("w") as hf,
    ):
        h = hashlib.blake2b()
        data = f.read()
        h.update(data)
        hf.write(h.hexdigest())
    print("Done")


def build_packages_for_linux() -> None:
    if platform.system() != "Linux":
        sys.exit(
            "Linux packages may only be built on Linux. Please re-run this script on Linux",
        )

    print("Building Linux packages, this will take a while...")
    system_packages = [
        "build-essential",
        "libtool",
        "mesa-common-dev",
        "libnccl-dev",
        "libxext-dev",
        "libxcursor-dev",
        "ladspa-sdk",
        "libxcomposite-dev",
        "libsystemd-dev",
        "libnccl2",
        "autoconf",
        "libxxf86vm-dev",
        "libgl1-mesa-dev",
        "libxinerama-dev",
        "libx11-dev",
        "libltdl-dev",
        "libgtk-4-dev",
        "libglib2.0-dev",
        "libspeechd-dev",
        "libudev-dev",
        "linux-libc-dev",
        "libxrandr-dev",
        "libxrender-dev",
        "libwayland-dev",
        "pkg-config",
        "xorg-dev",
        "libglu1-mesa-dev",
        "libxft-dev",
        "libgsasl-dev",
        "clang",
        "python3-jinja2",
        "zip",
        "gcc-aarch64-linux-gnu",
        "g++-aarch64-linux-gnu",
    ]
    if os.getuid() == 0:
        if platform.freedesktop_os_release()["ID_LIKE"].lower() == "debian":
            cache = apt.Cache()
            cache.update()
            cache.open()
            cache.upgrade(dist_upgrade=True)
            cache.open()
            for package in system_packages:
                if package in cache:
                    pkg = cache[package]
                    if not pkg.is_installed:
                        pkg.mark_install()
            cache.commit(None, None)
    elif platform.freedesktop_os_release()["ID_LIKE"].lower() == "debian":
        run(["sudo", "apt-get", "update", "-yqq"], check=True)
        run(["sudo", "apt-get", "full-upgrade", "-yqq"], check=True)
        command = ["sudo", "apt-get", "install", "-yqq"]
        command.extend(system_packages)
        run(command, check=True)
    # Packages are now defined in vcpkg.json manifest
    if build_arm64_linux and not use_official_steam_audio:
        sys.exit(
            "Error: steam audio does not have official libraries for arm64 for Linux",
        )
    if build_arm64_linux:
        try:
            # Build static libraries first and preserve them
            print("Building static libraries for ARM64...")
            command = [vcpkg_path, "install", "--triplet", "arm64-linux"]
            run(command, check=True)

            # Copy static libraries to a temporary location to preserve them
            static_backup = Path(orig_cwd / "vcpkg_installed" / "arm64-linux-backup")
            if Path(orig_cwd / "vcpkg_installed" / "arm64-linux").exists():
                print("Backing up ARM64 static libraries...")
                if static_backup.exists():
                    shutil.rmtree(static_backup)
                shutil.copytree(
                    Path(orig_cwd / "vcpkg_installed" / "arm64-linux"), static_backup
                )

            # Build dynamic libraries
            print("Building dynamic libraries for ARM64...")
            command = [vcpkg_path, "install", "--triplet", "arm64-linux-dynamic"]
            run(command, check=True)

            # Restore static libraries
            if static_backup.exists():
                print("Restoring ARM64 static libraries...")
                if Path(orig_cwd / "vcpkg_installed" / "arm64-linux").exists():
                    shutil.rmtree(Path(orig_cwd / "vcpkg_installed" / "arm64-linux"))
                shutil.move(
                    static_backup, Path(orig_cwd / "vcpkg_installed" / "arm64-linux")
                )
        except CalledProcessError as cpe:
            sys.exit(
                f"Linux packages installation failed, code {cpe.returncode}",
            )
    if build_x64_linux:
        try:
            # Build static libraries first and preserve them
            print("Building static libraries...")
            command = [vcpkg_path, "install", "--triplet", "x64-linux"]
            run(command, check=True)

            # Copy static libraries to a temporary location to preserve them
            static_backup = Path(orig_cwd / "vcpkg_installed" / "x64-linux-backup")
            if Path(orig_cwd / "vcpkg_installed" / "x64-linux").exists():
                print("Backing up static libraries...")
                if static_backup.exists():
                    shutil.rmtree(static_backup)
                shutil.copytree(
                    Path(orig_cwd / "vcpkg_installed" / "x64-linux"), static_backup
                )

            # Build dynamic libraries
            print("Building dynamic libraries...")
            command = [vcpkg_path, "install", "--triplet", "x64-linux-dynamic"]
            run(command, check=True)

            # Restore static libraries
            if static_backup.exists():
                print("Restoring static libraries...")
                if Path(orig_cwd / "vcpkg_installed" / "x64-linux").exists():
                    shutil.rmtree(Path(orig_cwd / "vcpkg_installed" / "x64-linux"))
                shutil.move(
                    static_backup, Path(orig_cwd / "vcpkg_installed" / "x64-linux")
                )
        except CalledProcessError as cpe:
            sys.exit(
                f"Linux packages installation failed, code {cpe.returncode}",
            )
    print("Done")
    print("Generating lindev package...")
    if build_arm64_linux:
        out_dir = Path(orig_cwd / "build" / "packages" / "lindev-arm64")
        out_dir.mkdir(parents=True, exist_ok=True)
        # Copy static libraries from vcpkg_installed directory (manifest mode)
        vcpkg_installed_dir = Path(orig_cwd / "vcpkg_installed" / "arm64-linux")
        if vcpkg_installed_dir.exists():
            shutil.copytree(
                vcpkg_installed_dir / "include",
                out_dir / "include",
                dirs_exist_ok=True,
            )
            shutil.copytree(
                vcpkg_installed_dir / "lib",
                out_dir / "lib",
                dirs_exist_ok=True,
            )
            if (vcpkg_installed_dir / "debug").exists():
                shutil.copytree(
                    vcpkg_installed_dir / "debug",
                    out_dir / "debug",
                    dirs_exist_ok=True,
                )
        # Copy dynamic libraries
        vcpkg_installed_dynamic_dir = Path(
            orig_cwd / "vcpkg_installed" / "arm64-linux-dynamic"
        )
        if vcpkg_installed_dynamic_dir.exists():
            shutil.copytree(
                vcpkg_installed_dynamic_dir / "include",
                out_dir / "include",
                dirs_exist_ok=True,
            )
            shutil.copytree(
                vcpkg_installed_dynamic_dir / "lib",
                out_dir / "lib",
                dirs_exist_ok=True,
            )
            if (vcpkg_installed_dynamic_dir / "debug").exists():
                shutil.copytree(
                    vcpkg_installed_dynamic_dir / "debug",
                    out_dir / "debug",
                    dirs_exist_ok=True,
                )
    if build_x64_linux:
        out_dir = Path(orig_cwd / "build" / "packages" / "lindev-x64")
        out_dir.mkdir(parents=True, exist_ok=True)
        # Copy static libraries from vcpkg_installed directory (manifest mode)
        vcpkg_installed_dir = Path(orig_cwd / "vcpkg_installed" / "x64-linux")
        if vcpkg_installed_dir.exists():
            shutil.copytree(
                vcpkg_installed_dir / "include",
                out_dir / "include",
                dirs_exist_ok=True,
            )
            shutil.copytree(
                vcpkg_installed_dir / "lib",
                out_dir / "lib",
                dirs_exist_ok=True,
            )
            if (vcpkg_installed_dir / "debug").exists():
                shutil.copytree(
                    vcpkg_installed_dir / "debug",
                    out_dir / "debug",
                    dirs_exist_ok=True,
                )
        # Copy dynamic libraries
        vcpkg_installed_dynamic_dir = Path(
            orig_cwd / "vcpkg_installed" / "x64-linux-dynamic"
        )
        if vcpkg_installed_dynamic_dir.exists():
            shutil.copytree(
                vcpkg_installed_dynamic_dir / "include",
                out_dir / "include",
                dirs_exist_ok=True,
            )
            shutil.copytree(
                vcpkg_installed_dynamic_dir / "lib",
                out_dir / "lib",
                dirs_exist_ok=True,
            )
            if (vcpkg_installed_dynamic_dir / "debug").exists():
                shutil.copytree(
                    vcpkg_installed_dynamic_dir / "debug",
                    out_dir / "debug",
                    dirs_exist_ok=True,
                )
        if use_official_steam_audio:
            gh = Github()
            repo = gh.get_repo("ValveSoftware/steam-audio")
            release = repo.get_latest_release()
            zip_asset = None
            # TODO (ethindp): refine this
            for asset in release.get_assets():
                if asset.name.startswith("steamaudio_") and asset.name.endswith(".zip"):
                    zip_asset = asset
                    break
            if zip_asset is None:
                sys.exit("Official steam audio zip asset could not be found")
            response = requests.get(zip_asset.browser_download_url, timeout=30)
            response.raise_for_status()
            zip_data = io.BytesIO(response.content)
            with zipfile.ZipFile(zip_data) as zf:
                if build_x64_linux:
                    out_dir = Path(orig_cwd / "build" / "packages" / "lindev-x64")
                    zf.extract(
                        "steamaudio/lib/linux-x64/libphonon.so",
                        path=str((out_dir / "lib").resolve()),
                    )
                    zf.extract(
                        "steamaudio/include/phonon.h",
                        path=str((out_dir / "include").resolve()),
                    )
                    zf.extract(
                        "steamaudio/include/phonon_interfaces.h",
                        path=str((out_dir / "include").resolve()),
                    )
                    zf.extract(
                        "steamaudio/include/phonon_version.h",
                        path=str((out_dir / "include").resolve()),
                    )
    if build_arm64_linux:
        out_dir = Path(orig_cwd / "build" / "packages" / "lindev-arm64")
        shutil.make_archive(
            "lindev-arm64",
            format="zip",
            root_dir=out_dir.parent,
            base_dir="lindev-arm64",
        )
        with (
            Path("lindev-arm64.zip").open("rb") as f,
            Path("lindev-arm64.zip.blake2b").open("w") as hf,
        ):
            h = hashlib.blake2b()
            data = f.read()
            h.update(data)
            hf.write(h.hexdigest())
    if build_x64_linux:
        out_dir = Path(orig_cwd / "build" / "packages" / "lindev-x64")
        shutil.make_archive(
            "lindev-x64",
            format="zip",
            root_dir=out_dir.parent,
            base_dir="lindev-x64",
        )
        with (
            Path("lindev-x64.zip").open("rb") as f,
            Path("lindev-x64.zip.blake2b").open("w") as hf,
        ):
            h = hashlib.blake2b()
            data = f.read()
            h.update(data)
            hf.write(h.hexdigest())
    print("Done")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Build NVGT packages for various platforms"
    )
    parser.add_argument("--android", action="store_true", help="Build for Android")
    parser.add_argument(
        "--arm64-linux", action="store_true", help="Build for ARM64 Linux"
    )
    parser.add_argument("--x64-linux", action="store_true", help="Build for x64 Linux")
    parser.add_argument("--ios", action="store_true", help="Build for iOS")
    parser.add_argument(
        "--ios-simulator", action="store_true", help="Build for iOS Simulator"
    )
    parser.add_argument("--macos", action="store_true", help="Build for macOS")
    parser.add_argument(
        "--arm64-windows", action="store_true", help="Build for ARM64 Windows"
    )
    parser.add_argument(
        "--x64-windows", action="store_true", help="Build for x64 Windows"
    )
    parser.add_argument(
        "--angelscript-nc",
        action="store_true",
        help="Use angelscript-nc instead of angelscript",
    )
    parser.add_argument(
        "--official-steam-audio", action="store_true", help="Use official Steam Audio"
    )
    parser.add_argument("--all", action="store_true", help="Build for all platforms")

    args = parser.parse_args()

    # Update global flags based on arguments
    if args.all:
        build_android = True
        build_arm64_linux = True
        build_x64_linux = True
        build_ios = True
        build_ios_simulator = True
        build_macos = True
        build_arm64_windows = True
        build_x64_windows = True
    else:
        build_android = args.android
        build_arm64_linux = args.arm64_linux
        build_x64_linux = args.x64_linux
        build_ios = args.ios
        build_ios_simulator = args.ios_simulator
        build_macos = args.macos
        build_arm64_windows = args.arm64_windows
        build_x64_windows = args.x64_windows

    build_angelscript_nc = args.angelscript_nc
    use_official_steam_audio = args.official_steam_audio

    # If no platform specified, show help
    if not any(
        [
            build_android,
            build_arm64_linux,
            build_x64_linux,
            build_ios,
            build_ios_simulator,
            build_macos,
            build_arm64_windows,
            build_x64_windows,
        ]
    ):
        parser.print_help()
        sys.exit(1)

    # Bootstrap vcpkg first
    bootstrap_vcpkg()

    # Build for specified platforms
    if build_android:
        print("Building for Android...")
        build_packages_for_android()

    if build_arm64_linux or build_x64_linux:
        print("Building for Linux...")
        build_packages_for_linux()

    # TODO: Add other platform builds when implemented
    if build_ios:
        print("iOS build not yet implemented")

    if build_ios_simulator:
        print("iOS Simulator build not yet implemented")

    if build_macos:
        print("macOS build not yet implemented")

    if build_arm64_windows:
        print("ARM64 Windows build not yet implemented")

    if build_x64_windows:
        print("x64 Windows build not yet implemented")

    print("Build process completed!")
