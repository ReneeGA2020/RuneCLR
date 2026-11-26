Status: implemented public API with a scoped **Windows x64, private .NET 12 dev runtime functional acceptance**
for the measured grouped modes (no method-level execution witness, no iOS/macOS/other-platform claim, no
security or sandbox claim). The design page keeps the wider, still-optional scope:
[design proposal](grouped-alc-host-design.md).

## What the option is for

A host sometimes needs both a trusted framework and an author module to start with fresh per-session
static state, while the two roles run under different execution policies:

| Role | Lifetime | Execution |
| --- | --- | --- |
| Host, runtime, stable contracts | Process-wide (Default) | Normal |
| Trusted framework and its session-private dependencies | One group | Ordinary collectible context; normal CLR/JIT where the platform allows |
| Author module and its private dependencies | One group | Required-interpreter collectible context |

Trust, lifetime and execution policy are separate decisions. A collectible context is not a sandbox, and
a collectible author is not "interpreter only" by definition - the author context is required-interpreter
because that is how RuneCLR runs author code, not because it is collectible.

## Public surface (v1)

GroupedHostOptions (record). All members are required:

| Member | Meaning |
| --- | --- |
| Contract | Host contract type; must already live in the Default context. The host instance must implement it. |
| FrameworkDirectory, FrameworkAssembly | Directory and plain .dll file name of the framework primary image. |
| FrameworkEntryType, FrameworkEntryMethod | Entry with signature: public static void Initialize(Contract host). |
| AuthorDirectory, AuthorAssembly | Directory and plain .dll file name of the author primary image. |
| AuthorEntryType, AuthorEntryMethod | Entry with signature: public static int Run(Contract host, int value). |
| SharedAssemblies | Optional additional Default-context assemblies shared with both roles. |
| AuthorApiPolicy | API access policy used for author admission and reflection policy. |

GroupedHostSession:

| Member | Behaviour |
| --- | --- |
| Open(options, host) | Validates options and every role image, builds both contexts, returns an active group. |
| InvokeFramework() | Runs the framework entry while the group is active. |
| InvokeAuthor(int) | Runs the author entry under the author reflection policy while the group is active. |
| BeginCleanup() | Closes entry admission and returns a GroupedHostCleanupToken. |
| AcknowledgeCleanup(token) | Records that the host finished detaching callbacks and draining in-flight work. |
| CompleteCleanup(token) | Completes cleanup. Requires the acknowledgement; it never grants one implicitly. |
| Close() | Retires the group and returns a GroupedHostTicket. After a completed close, repeat calls return the same ticket; it requires completed cleanup. |
| Dispose() | Same preconditions as Close. It deliberately rejects a group whose cleanup is pending or unacknowledged instead of acknowledging cleanup on the host behalf. |

GroupedHostTicket holds two nullable WeakReference targets, FrameworkUnloadRequested,
AuthorUnloadRequested, LeasesReleased, and the FrameworkCollected / AuthorCollected / BothCollected
helpers. Those helpers report true only for a weak target that exists and is dead; a missing target is
unknown, not collected.

## Role catalogs and identity rules

Both role directories are catalogued **before** any context exists. For every managed .dll in a role
directory the host reads the bytes once, reads the assembly identity from those same bytes, and hashes
those same bytes; later loads use exactly those bytes (LoadFromStream), never a re-read of the path.

Selection rules, in order:

1. Full identity equal to the contract or to a SharedAssemblies entry: the file is a **reference copy**.
   It is checked for identity equality and then ignored - the Default-context instance is used. A primary
   image may not be a reference copy.
2. In the author directory, full identity equal to an approved framework image: the file is a **framework
   copy**. Its bytes must hash identically to the approved framework image, otherwise Open throws. It is
   ignored for loading; the framework instance is shared instead.
3. Anything else is a **private role image** and is admitted as such. Duplicate simple names are rejected.
   An image whose simple name is a BCL/framework name that the host did not select is rejected; there is no
   fallback to an arbitrary Default copy.
4. The file whose name equals the configured role assembly must be that role primary image, otherwise
   Open throws.

File names must be plain <identity>.dll, must match the inspected identity, and must stay inside the role
directory. Unreadable or non-managed images in a role directory fail Open rather than being skipped.

## Execution policy and native code

* The grouped profile requires the session-origin scan capability. The two process switches involved are
  RuneCLR.EnableReflectionPolicy (the reflection policy itself) and
  RuneCLR.EnableReflectionPolicyOriginScan (stack-origin checks for framework-invoked author callbacks);
  the origin-scan switch defaults to enabled unless it is explicitly turned off. Open binds the
  required-interpreter bridge and prepares the reflection policy and its origin scan before any role
  catalog, admission preflight or context is created, and it never sets either switch itself. A missing or
  disabled capability fails closed with PlatformNotSupportedException; single-domain paths keep their own rules.
* The author context is created through the audited required-interpreter bridge. Opening it fails if the
  running CoreCLR/CoreLib cannot acknowledge the required-interpreter policy. Matching private builds are
  required; the stock runtime rejects this mode before any author image is executed.
* An author image that declares its own native import stays rejected by that context and by admission.
* A method the author calls on the shared framework assembly executes **in the framework context**, where an
  ordinary collectible context may use trusted native interop. That is trusted-wrapper interop, not an
  author native-load path, and the host owns that trust decision for the framework it selected.
* Policy acknowledgement is not method-level JIT/interpreter evidence. v1 does not claim a method witness.
* Delegate profile (Windows x64 grouped only): trusted standard BCL delegate constructors that the
  Packages gate has proven (a narrowly validated ctor plus managed pointer IL). Custom or author-defined
  delegate construction stays strict and is rejected; no blanket IntPtr or native-signature support was added.

External hosts can now opt in to the same standard-delegate metadata checks via
the [public external-host admission entry](external-host-admission.md), while
retaining their own loaders. That static stock-.NET validation has a separate
scope from the grouped host's private-runtime execution acceptance above.


## Host lifecycle

    var group = GroupedHostSession.Open(options, host);
    try
    {
        group.InvokeFramework();                // framework initialisation, ordinary context
        var result = group.InvokeAuthor(7);     // author work, required-interpreter context

        var token = group.BeginCleanup();       // entry admission closes here
        host.DetachCallbacksAndDrain();         // host-owned resources and in-flight work
        group.AcknowledgeCleanup(token);
        group.CompleteCleanup(token);           // throws if the acknowledgement is missing

        var ticket = group.Close();             // requests both unloads, releases leases
        Observe(ticket);                        // in a NoInlining helper, after all frames return
    }
    catch
    {
        // A failed close throws and leaves the group retryable: handle the exception, then retry Close.
        // A failed business call and a failed cleanup are different results.
        throw;
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    static void Observe(GroupedHostTicket ticket)
    {
        GC.Collect();
        GC.WaitForPendingFinalizers();
        GC.Collect();
        Console.WriteLine(ticket.FrameworkCollected + " " + ticket.AuthorCollected);
    }

Rules the pseudocode depends on:

* Author or framework entry is only invoked while the group is active. Any entry after BeginCleanup throws.
* Dispose follows exactly the same preconditions as Close and throws on a pending or unacknowledged
  cleanup. Do not wrap the group in a bare using block that would hide the original failure; drive cleanup
  explicitly and let the original exception surface.
* A retained GroupedHostTicket, cleanup token or result object holds no Assembly, Type, delegate, instance
  or exception. A host that keeps its own Assembly, delegate or instance references is responsible for
  releasing them; the group cannot do that for the host.
* Unload request, per-context collection and business outcome are separate observations. One dead context
  does not mean the group collected, and a collection is not a business success.

## Concurrency, retirement and pending state

* All session state uses ONE lock. Entry bodies run outside it; the lock only validates phase and reentrancy, marks the
  group in-flight and copies the locals needed for the call; the framework/author callback then runs, and a
  final lock clears the in-flight marker. A concurrent or reentrant lifecycle call therefore rejects
  promptly instead of blocking behind user code.
* Only one retire attempt owns the group. While it runs, the phase is Retiring and every other entry,
  cleanup or close call rejects.
* Unload is requested outside the state lock. The CLR raises the Unloading event once per context and clears
  the handler list before invoking it, so a throwing handler aborts that attempt before the native transition
  and a later retry can complete WITHOUT re-raising the handlers. An event count of one therefore does not
  count Unload API calls or native transitions; the single-request/retry behaviour above is additionally a
  source and state-protocol property, not runtime call-count instrumentation.
* A failed unload request throws a host-owned error and leaves the group retryable with its contexts and
  leases in place; the failure type name is exposed through FrameworkUnloadFailure / AuthorUnloadFailure.
  Those fields are null on a successful terminal close. A throwing Close never returns a failure ticket: the
  caller sees the exception, and a retried Close either returns the normal ticket or throws again.
* Resolution and retirement interact explicitly. The loaded-instance cache uses the same state lock, and
  an in-flight resolution is counted: retirement refuses to start while one is running (retry after it
  completes). The lock is never held across a cross-context LoadFromStream call. A second concurrent
  resolution of the same simple name is rejected rather than silently duplicated. The v1 host contract is
  still that the host serializes its own entry calls and drains host-side work before BeginCleanup; the
  cache guards exist so CLR-initiated resolution cannot corrupt state, not as a substitute for that drain.
* Resolver leases and host references are released only after both unload requests succeed. Clearing
  business static fields is never used to manufacture collection.
* Resolution after retirement started throws; an unknown non-BCL, non-shared, non-catalog framework
  dependency throws FileNotFoundException instead of falling back to a Default copy.
## Measured results (final cut, Windows x64 / private .NET 12 dev runtime)

The following functional results cover the final grouped harness on Windows x64. Run the listed modes
with the matching private runtime and configured harness DLL, as shown in the
[harness README](../tests/RuneCLR.GroupedHost.Tests/README.md). The stock negative control uses stock dotnet.

| area | harness mode | cases / checks | result |
| --- | --- | --- | --- |
| basic group lifecycle | --positive | 8 | 8/8 pass: both contexts collected in every group |
| author callback policy | --callback-policy | 2 | 2/2 pass: callback reflection denied outside an entry scope; framework-owned reflection allowed |
| dynamic load hook | --dynamic-rejected | 1 | pass: actual hook rejects the native import; collection and the next group succeed |
| failed Open rollback | --rollback | 1 | pass: host InvalidDataException (MissingEntry), both contexts collected, next group succeeds |
| unload retry | --unload-retry | 3 | 3/3 pass: framework/author/Dispose failure followed by controlled retry and collection |
| trusted native interop | --framework-native | 1 | pass: framework thread id observed through the trusted wrapper |
| rejected author provenance | --rejected-author | 3 gates | pass: framework catalog accepted; author intake rejects the import; no host records |
| reference copies | --framework-copy | 2 | pass: identical framework copy accepted, mismatched copy denied |
| stock runtime negative | --stock-negative | 2 | 2/2 pass: required mode rejects before author loading |
| policy decisions | --policy-negative | 11 | 11/11 pass |
| author reference audit | --policy-audit | all staged author references | pass: zero denials |
| origin-scan capability | --runtime-check | origin on / off | capability bit 0 present / absent, respectively |
| origin-scan rejection | --origin-negative | 1 | pass: Open fails closed when the capability is disabled |

Solution build for this cut: 0 warnings, 0 errors. Packaging tests pass 333/333, including all 13 new
opcode/delegate cases. Runtime tests pass 156/156; both ordinary and host-pumped SampleHost runs report
collection. These regressions and the grouped results above have separate execution receipts.

### Not measured / not claimed

The later [November 17 fixture method-entry record](experiments/grouped-method-witness-20261117.md)
adds 16 actual framework JIT / author interpreter observations with independent
verification, including direct method-group callbacks. This is separate from
the functional results above. Original closure private child-frame execution
and whole-method coverage remain unproven. Policy acknowledgement, module
presence and collection alone are not execution witnesses.

* Any platform other than Windows x64, and any runtime other than the matching private .NET 12 dev build.
* Security/sandbox properties, unloadable R2R, and collection timing guarantees.
* Runtime call-count instrumentation for the single unload request (see the unload note above).

## Known limitations

* Catalogs cover managed .dll files only. Native companion libraries are not scanned as role images and are
  currently unsupported: a role directory containing a non-managed .dll fails Open instead of being
  interpreted as a companion.
* Reference copies are checked by full identity only; there is no byte comparison against a Default-context
  assembly (the host cannot read those bytes).
* The ticket reports unload requests and weak targets; it does not prove collection.
* Business result, cleanup result, each unload request and each collection observation stay separate
  dimensions. None of them implies another.
