# Runtime platform build baseline

Decision recorded on 2026-11-16. These are RuneCLR's current runtime build
targets, independent of any embedding application's platform requirements.
They are build requirements, not a claim that matching artifacts have already
been produced or that every target OS version has been tested.

| Platform | Runtime build baseline |
| --- | --- |
| Android | Minimum Android API level 24 (Android 7.0) |
| iOS | Minimum deployment target iOS 12.2 |
| Windows | Keep the selected CoreCLR upstream revision's default Windows compilation and linker settings |

## Build verification

For Android and iOS, configure the native runtime and its required native
dependencies for the stated minimum target. Record the source revision,
architecture, toolchain, resolved minimum-version flags and output identities.
Check the effective generated build configuration and available binary version
metadata; setting only an application's manifest or deployment target does not
establish the runtime's build target.

For Windows, retain upstream defaults for `WINVER`, `_WIN32_WINNT` and PE
subsystem versions rather than imposing a separate RuneCLR override. Record the
selected Windows SDK, target architecture and effective upstream settings.
Neither the SDK version nor the PE subsystem version alone establishes the
oldest compatible or supported Windows release.

If a selected upstream revision or dependency cannot build for a mobile
baseline, report that conflict explicitly rather than silently raising the
minimum. Changes to these baselines require a separate project decision.

## Acceptance boundary

This decision requires compilation for the candidate minimum versions. It does
not require obtaining Android API 24 or iOS 12.2 devices and testing on those
specific OS versions. Report successful builds separately from device-tested
compatibility and upstream vendor support lifecycles.

Existing execution, loading, signing, interpreter/R2R and lifecycle acceptance
work remains separate. An embedding application may require a newer OS because
of its own engine, dependencies or distribution policy.

## Reference

The mobile candidate values follow the minimum SDK/deployment targets in the
[official .NET 11 OS requirements](https://github.com/dotnet/core/blob/main/release-notes/11.0/supported-os.md).
That document's actively supported OS list is a different boundary. Following
the [RuneCLR runtime development branch](coreclr.md#where-the-runtime-source-lives-start-here)
does not automatically replace this decision with a newer upstream default.
