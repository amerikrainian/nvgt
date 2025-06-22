# Build script for NVGT using the scons build system.
# NVGT - NonVisual Gaming Toolkit (https://nvgt.gg)
# Copyright (c) 2022-2024 Sam Tupy
# license: zlib

import os, multiprocessing, tempfile

Help("""
	Available custom build switches for NVGT:
		copylibs=0 or 1 (default 1): Copy shared libraries to release/lib after building?
		debug=0 or 1 (default 0): Include debug symbols in the resulting binaries?
		no_upx=0 or 1 (default 1): Disable UPX stubs?
		no_plugins=0 or 1 (default 0): Disable the plugin system entirely?
		no_shared_plugins=0 or 1 (default 0): Only compile plugins statically?
		no_stubs=0 or 1 (default 0): Disable compilation of all stubs?
		no_user=0 or 1 (default 0): Pretend that the user directory doesn't exist?
		no_<plugname>_plugin=1: Disable a plugin by name.
		static_<plugname>_plugin=1: Cause the given plugin to be linked statically if possible.
		stub_obfuscation=0 or 1 (default 0): Obfuscate some Angelscript function registration strings in the resulting stubs? Could make them bigger.
		warnings (0 or 1, default 0): enable compiler warnings?
		warnings_as_errors (0 or 1, default 0): treat compiler warnings as errors?
	You can also run scons install (for now only on windows) to install the build into C:/nvgt. STILL WIP!
	Note that custom switches or targets may be added by any plugin SConscript and may not be documented here.
""")

# setup
env = Environment()
# Prevent scons from wiping out the environment for certain tools, e.g. scan-build
env["CC"] = os.getenv("CC") or env["CC"]
env["CXX"] = os.getenv("CXX") or env["CXX"]
env["ENV"].update(x for x in os.environ.items() if x[0].startswith("CCC_"))
Decider('content-timestamp')
env.Alias("install", "c:/nvgt")
SConscript("build/upx_sconscript.py", exports = ["env"])
SConscript("build/version_sconscript.py", exports = ["env"])
env.SetOption("num_jobs", multiprocessing.cpu_count())
SConscript("build/osdev_sconscript.py", exports = ["env"])
if ARGUMENTS.get("debug", "0") == "1":
	env.Tool('compilation_db')
	cdb = env.CompilationDatabase()
	Alias('cdb', cdb)

# Platform setup and system libraries
if env["PLATFORM"] == "win32":
	env.Append(CCFLAGS = ["/EHsc", "/J", "/MT" if not "windev_debug" in env else "/MTd", "/Z7", "/std:c++20", "/GF", "/Zc:inline", "/O2" if ARGUMENTS.get("debug", "0") == "0" else "/Od", "/bigobj", "/permissive-", "/W3" if ARGUMENTS.get("warnings", "0") == "1" else "", "/WX" if ARGUMENTS.get("warnings_as_errors", "0") == "1" else ""])
	env.Append(LINKFLAGS = ["/NOEXP", "/NOIMPLIB"], no_import_lib = 1)
	env.Append(LIBS = ["Kernel32", "User32", "imm32", "OneCoreUAP", "dinput8", "dxguid", "gdi32", "winspool", "shell32", "iphlpapi", "ole32", "oleaut32", "delayimp", "uuid", "comdlg32", "advapi32", "netapi32", "winmm", "version", "crypt32", "normaliz", "wldap32", "ws2_32", "ntdll"])
else:
	env.Append(CXXFLAGS = ["-fms-extensions", "-std=c++20", "-fpermissive", "-O0" if ARGUMENTS.get("debug", 0) == "1" else "-O3", "-Wno-narrowing", "-Wno-int-to-pointer-cast", "-Wno-delete-incomplete", "-Wno-unused-result", "-g" if ARGUMENTS.get("debug", 0) == "1" else "", "-Wall" if ARGUMENTS.get("warnings", "0") == "1" else "", "-Wextra" if ARGUMENTS.get("warnings", "0") == "1" else "", "-Werror" if ARGUMENTS.get("warnings_as_errors", "0") == "1" else ""], LIBS = ["m"])
if env["PLATFORM"] == "darwin":
	# homebrew paths and other libraries/flags for MacOS
	env.Append(CCFLAGS = ["-mmacosx-version-min=14.0", "-arch", "arm64", "-arch", "x86_64"], LINKFLAGS = ["-arch", "arm64", "-arch", "x86_64"])
elif env["PLATFORM"] == "posix":
	# Use vcpkg libraries if available, otherwise fall back to lindev
	vcpkg_installed = os.path.exists("vcpkg_installed/x64-linux")
	is_debug = ARGUMENTS.get("debug", "0") == "1"
	if vcpkg_installed:
		print("Using vcpkg libraries from vcpkg_installed/x64-linux")
		if is_debug:
			env.Append(CPPPATH = ["vcpkg_installed/x64-linux/include", "/usr/local/include"], LIBPATH = ["vcpkg_installed/x64-linux/debug/lib", "vcpkg_installed/x64-linux-dynamic/debug/lib", "/usr/local/lib", "/usr/lib/x86_64-linux-gnu"])
		else:
			env.Append(CPPPATH = ["vcpkg_installed/x64-linux/include", "/usr/local/include"], LIBPATH = ["vcpkg_installed/x64-linux/lib", "vcpkg_installed/x64-linux-dynamic/lib", "/usr/local/lib", "/usr/lib/x86_64-linux-gnu"])
	else:
		print("Using prebuilt libraries from lindev/")
		env.Append(CPPPATH = ["lindev/include", "/usr/local/include"], LIBPATH = ["lindev/lib", "/usr/local/lib", "/usr/lib/x86_64-linux-gnu"])
	env.Append(LINKFLAGS = ["-fuse-ld=gold", "-g" if is_debug else "-s"])
env.Append(CPPDEFINES = ["POCO_STATIC", "UNIVERSAL_SPEECH_STATIC", "DEBUG" if ARGUMENTS.get("debug", "0") == "1" else "NDEBUG", "UNICODE", "SDL_STATIC_LIB" if env["PLATFORM"] == "posix" else ""])
env.Append(CPPPATH = ["#ASAddon/include", "#dep"], LIBPATH = ["#build/lib"])

# plugins
static_plugins = []
try:
	# First, read the list of static plugins we wish to link if available.
	with open(os.path.join("user", "static_plugins"), "r") as f:
		lines = f.readlines()
		for l in lines:
			if not l or l.startswith("#"): continue
			static_plugins.append(l.strip())
except FileNotFoundError: pass
plugin_env = env.Clone()
# Then loop through all known plugins and build them.
for s in Glob("plugin/*/_SConscript") + Glob("plugin/*/SConscript") + Glob("extra/plugin/integrated/*/_SConscript") + Glob("extra/plugin/integrated/*/SConscript"):
	plugname = str(s).split(os.path.sep)[-2]
	if ARGUMENTS.get(f"no_{plugname}_plugin", "0") == "1": continue
	if ARGUMENTS.get(f"static_{plugname}_plugin", "0") == "1" and not plugname in static_plugins: static_plugins.append(plugname)
	# Build the plugin. A list of static libraries NVGT should link with is returned if the plugin generates any.
	plug = SConscript(s, variant_dir = f"build/obj_plugin/{plugname}", duplicate = 0, exports = {"env": plugin_env, "nvgt_env": env})
	if plug and plugname in static_plugins: env.Append(LIBS = plug)
# Finally generate nvgt_plugins.cpp
static_plugins_object = None
static_plugins_path = os.path.join(tempfile.gettempdir(), "nvgt_plugins")
if len(static_plugins) > 0:
	with open(static_plugins_path + ".cpp", "w") as f:
		f.write("#define NVGT_LOAD_STATIC_PLUGINS\n#include <nvgt_plugin.h>\n")
		for plugin in static_plugins: f.write(f"static_plugin({plugin})" + "\n")
		static_plugins_object = env.Object(static_plugins_path, static_plugins_path + ".cpp", CPPPATH = env["CPPPATH"] + ["#src"])

# Project libraries
if env["PLATFORM"] == "posix" and os.path.exists("vcpkg_installed/x64-linux"):
	# When using vcpkg, we need to specify libraries in the correct order to resolve dependencies
	env.Append(LIBS = ["ASAddon", "deps", "angelscript", "SDL3-static" if os.path.exists("vcpkg_installed/x64-linux/lib/libSDL3-static.a") else "SDL3", "phonon", "enet", "reactphysics3d", "PocoJSON", "PocoNet", "PocoNetSSL", "PocoUtil", "PocoXML", "PocoCrypto", "PocoZip", "PocoFoundation", "ssl", "crypto", "utf8proc", "pcre2-8", "vorbisfile", "vorbis", "ogg", "FLAC", "expat", "z", "mysofa", "pffft", "flatbuffers"])
else:
	env.Append(LIBS = [["PocoJSON", "PocoNet", "PocoNetSSL", "PocoUtil", "PocoXML", "PocoCrypto", "PocoZip", "PocoFoundation", "expat", "z"] if env["PLATFORM"] != "win32" else ["UniversalSpeechStatic", "PocoXMLmt", "libexpatMT", "zlib"], "angelscript", "SDL3", "phonon", "enet", "reactphysics3d", "ssl", "crypto", "utf8proc", "pcre2-8", "ASAddon", "deps", "vorbisfile", "vorbis", "ogg"])
if env["PLATFORM"] == "posix": env.ParseConfig("pkg-config --libs alsa")

# nvgt itself
sources = [str(i)[4:] for i in Glob("src/*.cpp")]
if "android.cpp" in sources: sources.remove("android.cpp")
if "version.cpp" in sources: sources.remove("version.cpp")
env.Command(target = "src/version.cpp", source = ["src/" + i for i in sources], action = env["generate_version"])
version_object = env.Object("build/obj_src/version", "src/version.cpp") # Things get weird if we do this after VariantDir.
VariantDir("build/obj_src", "src", duplicate = 0)
env.Append(CPPDEFINES = ["NVGT_BUILDING", "NO_OBFUSCATE"])
if env["PLATFORM"] == "win32":
	env.Append(CPPDEFINES = ["_SILENCE_CXX20_OLD_SHARED_PTR_ATOMIC_SUPPORT_DEPRECATION_WARNING"], LINKFLAGS = ["/OPT:REF", "/OPT:ICF", "/ignore:4099", "/delayload:phonon.dll"])
elif env["PLATFORM"] == "darwin":
	sources.append("apple.mm")
	sources.append("macos.mm")
	# We must link MacOS frameworks here rather than above in the system libraries section to insure that they don't get linked with random plugins.
	env["FRAMEWORKPREFIX"] = "-weak_framework"
	env.Append(FRAMEWORKS = ["CoreAudio",  "CoreFoundation", "CoreHaptics", "CoreMedia", "CoreVideo", "AudioToolbox", "AVFoundation", "AppKit", "IOKit", "Carbon", "Cocoa", "ForceFeedback", "GameController", "QuartzCore", "Metal", "UniformTypeIdentifiers"])
	env.Append(LIBS = ["objc"])
	env.Append(LINKFLAGS = ["-Wl,-rpath,'@loader_path',-rpath,'@loader_path/lib',-rpath,'@loader_path/../Frameworks',-dead_strip_dylibs", "-mmacosx-version-min=14.0"])
elif env["PLATFORM"] == "posix":
	env.Append(LINKFLAGS = ["-Wl,-rpath,'$$ORIGIN/.',-rpath,'$$ORIGIN/lib'"])
if ARGUMENTS.get("no_user", "0") == "0":
	if os.path.isfile("user/nvgt_config.h"):
		env.Append(CPPDEFINES = ["NVGT_USER_CONFIG"])
	for s in ["_SConscript", "SConscript"]:
		if os.path.isfile(f"user/{s}"):
			SConscript(f"user/{s}", exports = {"plugin_env": plugin_env, "nvgt_env": env})
			break # only execute one script from here
SConscript("ASAddon/_SConscript", variant_dir = "build/obj_ASAddon", duplicate = 0, exports = "env")
SConscript("dep/_SConscript", variant_dir = "build/obj_dep", duplicate = 0, exports = "env")
# We'll clone the environment for stubs now so that we can then add any extra libraries that are not needed for stubs to the main nvgt environment.
stub_env = env.Clone(PROGSUFFIX = ".bin")
if env["PLATFORM"] == "win32":
	env.Append(LINKFLAGS = ["/delayload:plist.dll"])
	env.Append(LIBS = ["plist"])
elif env["PLATFORM"] == "posix":
	# For vcpkg builds on Linux, plist is named differently
	if os.path.exists("vcpkg_installed/x64-linux/lib/libplist-2.0.a"):
		env.Append(LIBS = ["plist-2.0", "plist++-2.0"])
	else:
		env.Append(LIBS = ["plist-2.0"])
else:
	env.Append(LIBS = ["plist-2.0"])
extra_objects = [version_object]
if static_plugins_object: extra_objects.append(static_plugins_object)
nvgt = env.Program("release/nvgt", env.Object([os.path.join("build/obj_src", s) for s in sources]) + extra_objects, PDB = "#build/debug/nvgt.pdb")
if env["PLATFORM"] == "darwin":
	# On Mac OS, we need to run install_name_tool to modify the paths of any dynamic libraries we link.
	env.AddPostAction(nvgt, lambda target, source, env: env.Execute("install_name_tool -change /usr/local/lib/libplist-2.0.4.dylib @rpath/libplist-2.0.4.dylib " + str(target[0])))
if env["PLATFORM"] == "win32":
	# Only on windows we must go through the frustrating hastle of compiling a version of nvgt with no console E. the windows subsystem. It is at least set up so that we only need to recompile one object
	if "nvgt.cpp" in sources: sources.remove("nvgt.cpp")
	nvgtw = env.Program("release/nvgtw", env.Object([os.path.join("build/obj_src", s) for s in sources]) + [env.Object("build/obj_src/nvgtw", "build/obj_src/nvgt.cpp", CPPDEFINES = ["$CPPDEFINES", "NVGT_WIN_APP"]), extra_objects], LINKFLAGS = ["$LINKFLAGS", "/subsystem:windows"], PDB = "#build/debug/nvgtw.pdb")
	sources.append("nvgt.cpp")
	# Todo: Properly implement the install target on other platforms
	env.Install("c:/nvgt", nvgt)
	env.Install("c:/nvgt", nvgtw)
	env.Install("c:/nvgt/include", Glob("#release/include/*"))
	env.Install("c:/nvgt/lib", Glob("#release/lib/*"))

# stubs
def fix_stub(target, source, env):
	"""On windows, we replace the first 2 bytes of a stub with 'NV' to stop some sort of antivirus scan upon script compile that makes it take a bit longer. We do the same on MacOS because otherwise apple's notarization service detects the stub as an unsigned binary and fails. Stubs must be unsigned until the nvgt scripter signs their compiled games."""
	for t in target:
		if not str(t).endswith(".bin"): continue
		with open(str(t), "rb+") as f:
			f.seek(0)
			f.write(b"NV")
			f.close()

if ARGUMENTS.get("no_stubs", "0") == "0":
	stub_platform = "" # This detection will likely need to be improved as we get more platforms working.
	if env["PLATFORM"] == "win32": stub_platform = "windows"
	elif env["PLATFORM"] == "darwin": stub_platform = "mac"
	elif env["PLATFORM"] == "posix": stub_platform = "linux"
	else: stub_platform = env["PLATFORM"]
	VariantDir("build/obj_stub", "src", duplicate = 0)
	stub_env.Append(CPPDEFINES = ["NVGT_STUB"])
	if env["PLATFORM"] == "win32": stub_env.Append(LINKFLAGS = ["/subsystem:windows"])
	if ARGUMENTS.get("stub_obfuscation", "0") == "1": stub_env["CPPDEFINES"].remove("NO_OBFUSCATE")
	stub_objects = stub_env.Object([os.path.join("build/obj_stub", s) for s in sources]) + extra_objects
	stub = stub_env.Program(f"release/stub/nvgt_{stub_platform}", stub_objects, PDB = "#build/debug/nvgt_windows.pdb")
	if env["PLATFORM"] == "win32": env.Install("c:/nvgt/stub", stub)
	if "upx" in env:
		stub_u = stub_env.UPX(f"release/stub/nvgt_{stub_platform}_upx.bin", stub)
		if env["PLATFORM"] == "win32": env.Install("c:/nvgt/stub", stub_u)
	# on windows, we should have a version of the Angelscript library without the compiler, allowing for slightly smaller executables.
	if env["PLATFORM"] == "darwin":
		stub_env.AddPostAction(stub, fix_stub)
	elif env["PLATFORM"] == "win32":
		stub_env.AddPostAction(stub, fix_stub)
		if "upx" in env: stub_env.AddPostAction(stub_u, fix_stub)
		stublibs = list(stub_env["LIBS"])
		if "angelscript" in stublibs:
			stublibs.remove("angelscript")
			stublibs.append("angelscript-nc")
			stub_nc = stub_env.Program(f"release/stub/nvgt_{stub_platform}_nc", stub_objects, LIBS = stublibs)
			stub_env.AddPostAction(stub_nc, fix_stub)
			env.Install("c:/nvgt/stub", stub_nc)
			if "upx" in env:
				stub_nc_u = stub_env.UPX(f"release/stub/nvgt_{stub_platform}_nc_upx.bin", stub_nc)
				stub_env.AddPostAction(stub_nc_u, fix_stub)
				env.Install("c:/nvgt/stub", stub_nc_u)

if ARGUMENTS.get("copylibs", "1") == "1":
	env["NVGT_OSDEV_COPY_LIBS"](env)
