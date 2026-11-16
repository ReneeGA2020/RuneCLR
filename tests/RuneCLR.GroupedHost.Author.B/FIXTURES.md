# RuneCLR.GroupedHost.Author (B) fixture

AssemblyName: RuneCLR.GroupedHost.Author (shared with the other variant); content/MVID differ by tag B.

Public entry: public static int AuthorEntry.Run(IGroupedHostContract host, int value)

- value >= 0 : returns value + 200. Records initial/current author state, calls
  FrameworkEntry.Describe/Touch (shared-instance proof), installs a static author callback into the
  framework-owned event, and subscribes a host-held callback via host.Subscribe (retention negative
  control; the host unsubscribes later).
- value == -1 : throws AuthorCallbackException after the callback installs.
- value == -2 : throws AuthorInitException before touching any static.
- value == -3 : calls FrameworkEntry.NativeThreadProbe() and returns its value. This is a POSITIVE
  trusted-native bridge probe: the native call lives in the trusted framework assembly, author fixtures
  contain no P/Invoke, and the host's explicit API allow policy governs it.

- host.Mode == "raise-denied-reflection": while the framework raises the static event (no InvokeAuthor scope),
  the author callback records the attempt and reflects System.String.StartsWith, which the host policy
  explicitly denies; the denial must be enforced by the runtime origin scan. The callback records the
  denial type/inner/message and rethrows.
- host.DynamicImage non-empty: the normal entry also loads the host-supplied bytes into the author's
  own context (`AssemblyLoadContext.GetLoadContext(typeof(AuthorEntry).Assembly).LoadFromStream(new
  MemoryStream(host.DynamicImage, writable: false))`). The image is a NativeRejected author assembly
  outside the role catalogs, so the strict load hook must reject it; the author records
  attempt/rejected (type and bounded message) or ALLOWED and returns normally.

Statics RunCount/Token are never reset by fixtures; collection is proven by unloading the ALC.

No RuneCLR.Runtime reference, no engine UI, no processes, no timing assertions, no finalizers.
