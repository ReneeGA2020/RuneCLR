# RuneCLR.GroupedHost.Framework fixture

Assembly: RuneCLR.GroupedHost.Framework (net11.0, deterministic).

Static state is per loaded framework assembly/context (not inherently process-wide).

Public surface:

- Initialize(IGroupedHostContract host)  -- exact one-parameter signature.
  The mode comes from host.Mode:
  - "normal"  : increments StaticInitCount, creates a fresh FrameworkInstance token, records
                "framework:init:normal:count=<n>:token=<token>", returns.
  - "throw-init": same bookkeeping, records the line, then throws FrameworkInitException.
  - "raise-denied-reflection": test-only; raises the existing static event (author callback) without
                re-initializing counters or the instance token.
  - "framework-own-reflection": test-only; invokes the private framework marker through ordinary
                reflection from trusted framework code (no author frame) and records
                "framework:own-reflection:7001:allowed".
- Describe(string caller) -> "framework:describe:caller=<tag>:count=..:token=..:calls=.."
- Touch(string caller) -> increments CallCount and returns it (shared-instance proof for A and B).
- SubscribeFrameworkEvent / UnsubscribeFrameworkEvent / RaiseFrameworkEvent: framework-owned static
  event; Raise returns the handler count. Used for the normal internal author -> framework cycle.
- NativeThreadProbe(): Windows-only kernel32!GetCurrentThreadId. This is a trusted-framework native
  bridge, not an author P/Invoke: authors reach it only through this framework API, under the host's
  explicit API allow policy. Other platforms throw PlatformNotSupportedException.

No RuneCLR.Runtime reference, no engine UI, no processes, no timing assertions, no finalizers.
