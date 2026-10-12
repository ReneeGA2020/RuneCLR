# Contributing

RuneCLR is an early prototype. Small changes that establish a concrete runtime
capability are especially useful.

Before proposing a runtime patch, describe the required host behavior, the pinned
CoreCLR base, the supported platforms, and how enforcement will be verified.
Keep host policies outside the runtime when practical.

Run `dotnet build RuneCLR.slnx -c Release`, the executable integration tests, and
the sample host with `--collect`. Add regressions for changes to lifecycle,
dependency resolution, cleanup, and execution limits. Do not describe cooperative
checks or ALC behavior as a security boundary.

The project uses MIT licensing and accepts contributions under that license.
