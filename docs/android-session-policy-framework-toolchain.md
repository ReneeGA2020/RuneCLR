# Private Darwin Android framework tools

Executed successfully on 2026-10-13 (local date) for the matching Android source
framework build.
[android-session-policy-framework-toolchain.py](../eng/android-session-policy-framework-toolchain.py)
created a fresh project-private SDK and JDK. All three archive size/checksum
checks, extraction steps and six executable probes passed. This tools result is
a prerequisite; the separate [framework build](android-session-policy-framework.md)
also now passes. Neither result establishes Android application execution.

The first framework attempt failed at src/native/libs/build-native.proj's
BuildNativeAndroid target. Its official AndroidLibBuilderTask uses
AndroidSdkHelper, JavaCompiler, JarBuilder and DexBuilder before the Unix native
library build. A Mac NDK alone does not supply AndroidSdkHelper's platform jar,
build-tools d8, or Java executables. The source checkout's JavaCompiler uses
javac -source1.8 -target1.8 -bootclasspath android.jar; a private JDK17 can provide
that toolchain without installing an entire Android Studio distribution.

## Reviewed inputs

The Google repository2-3.xml was read from the existing
ROOT/android-toolchain-r27c-20261013 directory. Its SHA256 is
13dd16e8984cc6f3202a72c8eb269bd7ad03be4247b41b4412b315c5b8bf6d4b.
The script requires that exact metadata snapshot and its stable channel0 package
records. Google publishes the archive sizes and SHA1 checksums in its
[official repository metadata](https://dl.google.com/android/repository/repository2-3.xml).

| Input | Archive bytes | Published checksum |
| --- | ---: | --- |
| platforms;android-36, revision2: platform-36_r02.zip | 65,878,410 | SHA1 2c1a80dd4d9f7d0e6dd336ec603d9b5c55a6f576 |
| build-tools;35.0.1, macosx: build-tools_r35.0.1_macosx.zip | 76,857,925 | SHA1 f4dda6855ddf1ea1a51ee3ab6587104bd0c1d727 |
| Temurin17.0.20.1+1, Hotspot JDK aarch64/mac tar.gz | 185,851,019 | SHA256 196d13ba5f10414bef7f6a05a9b3f00edacb18ebacef2b99485db9e2ee18f0e8 |

The stable GA JDK record was verified from Adoptium's
[primary version API](https://api.adoptium.net/v3/assets/version/17.0.20.1%2B1?architecture=aarch64&image_type=jdk&os=mac&vendor=eclipse&jvm_impl=hotspot&release_type=ga).
It identifies Eclipse's mac/aarch64 JDK archive, its size and SHA256. The primary
[binary API](https://api.adoptium.net/v3/binary/version/jdk-17.0.20.1%2B1/mac/aarch64/jdk/hotspot/normal/eclipse)
was observed to return307 to that exact Adoptium-owned GitHub release archive.
Downloading that official release is a read operation; no GitHub issue, PR,
repository or other external record is written. The script downloads through
the primary API, retains all redirect headers/effective URLs, and checks the
final bytes against the API's pinned checksum. It does not use the pkg installer.

## Run and outputs

ROOT is /Users/editor/RuneCLR-experiments/20261012-iossim-coreclr. Only the root
agent should launch this command through the configured Cindy SSH connection.
The output directory must not exist; failed attempts remain intact.

~~~sh
python3 "$ROOT/eng/android-session-policy-framework-toolchain.py" \
  --manifest "$ROOT/android-toolchain-r27c-20261013/repository2-3.xml" \
  --output "$ROOT/android-framework-tools-20261013"
~~~

The driver fetches and retains the primary Adoptium metadata first, then
downloads the three pinned archives in parallel. Total compressed bytes are
328,587,354 (about329 MB decimal). Each archive must match its published exact
size and checksum before extraction. Every download keeps a log, .exit and
HTTP response/redirect headers. Request.json binds the Google manifest,
Adoptium response, driver, archive identities and destination. Archives.json
additionally records SHA256 for both Google archives and their download logs.

ZIP members are checked for path escapes and unexpected symlinks. TAR member
names and relative link targets must remain within their single JDK bundle;
special/device members are rejected. ditto preserves SDK executable modes;
tar extracts the verified JDK into the new private directory. There is no
recursive deletion, overlay of an existing SDK, system installer, SDK manager,
or fabricated licence acceptance. The original Google licence reference remains
in metadata. No licenses/ acceptance file is written.

The SDK contains only sdk/platforms/android-36 and sdk/build-tools/35.0.1.
That makes AndroidSdkHelper's actual highest stable API/build-tools selection
deterministic. The JDK remains under jdk/<bundle>/Contents/Home. The driver checks
the extracted source.properties and JDK release before running:

- java -version and java -XshowSettings:properties -version, including actual
  os.arch=aarch64;
- javac -version;
- jar --version;
- d8 --version with the private JAVA_HOME and JDK bin first in process PATH;
- file on the actual Java executable.

These probes use a subprocess environment only. The user's global environment,
system Java registration and /usr/libexec/java_home remain unchanged. The driver
requires an actual Darwin ARM64 host; running it on Windows is not a toolchain
validation substitute. A probe failure produces success=false and retains its
logs and archives without automatically repeating the framework build.

## Framework consumer contract

Successful results.json has schema runeclr.android.framework-toolchain.v1,
success=true, host=darwin-arm64 and the following fields:

| Field | Meaning |
| --- | --- |
| androidSdkRoot | Absolute private sdk directory |
| javaHome | Absolute extracted JDK Contents/Home |
| javaExecutable / javacExecutable / jarExecutable | Absolute actual executable paths |
| d8Executable | sdk/build-tools/35.0.1/d8 |
| platformApi / buildToolsVersion / jdkMajor / jdkRelease | 36 / 35.0.1 / 17 / jdk-17.0.20.1+1 |
| criticalFiles | Absolute path, SHA256 and size for java/javac/jar/d8, lib/d8.jar, android.jar, both SDK source.properties, JDK release/lib/modules/lib/server/libjvm.dylib |
| probes | tool, actual command, exitCode0, absolute log path and logSha256 |
| requestSha256 / archivesReceiptSha256 / metadataHashes / driverSha256 | Immutable input and download provenance |
| globalEnvironmentChanged / licenseAcceptanceWritten / sdkManagerUsed / systemInstallerUsed / deviceOperation | All false |
| frameworkBuildVerified | false: tools are a prerequisite, not the framework product |

The independent framework build driver consumes --android-tools pointing to
this receipt directory. It verifies original request/log/file hashes, exact
highest SDK selection and executable paths, then sets ANDROID_SDK_ROOT,
JAVA_HOME and PATH for its own process. It starts a new framework attempt after
this prerequisite succeeds. Failed attempt1 and its environment/tool-missing
diagnostics remain separate evidence. The result is not labelled a stock NuGet
runtime, and no APK or emulator operation occurs in this toolchain step.

Actual results.json under ROOT/android-framework-tools-20261013 has SHA256
f8a897a0d1ec57a90308dcc0a939f89fc9c84fe2ebccb3b35e85464d82e6d3a3.
The retained archives receipt SHA256 is
a4d32be899121d32cffdea189873867a96afb5474e001f02de82ba70578c937f.
Java, javac and jar report 17.0.20.1; Java reports aarch64 and its executable is
Mach-O ARM64. The selected SDK build-tools35.0.1 d8 reports D8 8.6.2-dev,
build abaab469b5ebd4dd2bb91ba0ed6f45277faae4ca. All 11 critical tool hashes
and six probe-log hashes were independently reread successfully. The
[local archive verification](../artifacts/android-session-policy/20261013-framework-tools/local-verification.json)
checks 35 member hashes and records the separately verified archives/tools.
Global environment changes, licence-acceptance writes, SDK manager use, system
installation and device operations remain false in the original receipt.
