# Work sequence

This sequence follows the [product direction](product-direction.md), clarified
on 2026-10-15: C# iOS hot updates first, UGC management on the same foundation.
The tracker is [Roadmap #11](https://github.com/ReneeGA2020/RuneCLR/issues/11).
An issue stays open until its acceptance evidence exists. Scheduling a task does
not establish that an unperformed experiment has passed.

On 2026-10-16 the only available phone is an iPhone XR locked to iOS 18.7. Do not build an iphoneos runtime for it. The next simulator task is to reproduce commit c268026, which does not include the temporary failure-type logs used by rerun-a9164cd-20261016-10.

## Current contribution order - 2026-10-15

The [next-session development plan](next-development-plan.md) gives the concrete
increments and acceptance gates. The simulator has now measured downloaded
native entries for Business.Execute in separate A and B processes. A's managed
success line is TRUSTED_UPDATE_SUCCESS version=A result=216 on stderr. B's
stderr now also has TRUSTED_UPDATE_SUCCESS version=B result=216, PRIVATE_VALUE=200
and IL_HELPER_RESULT=607. This is simulator evidence;
physical-device acceptance is paused until a reachable iPhone is available.

The current desktop increment is the third trusted-update step in
src/RuneCLR.TrustedUpdate: its 270/270 selector checks startup selection of one
version, ordinary failure fallback, NotApproved when a correct content hash
has no matching host approval, and a host callback or ITrustedUpdateHost that works only during Tick. A path containing .. is rejected only when it resolves outside the content root; one that still resolves inside is accepted. The console sample passes the candidate directory as that root. A manifest additional file with the wrong hash is rejected before load, and a file name of .. is invalid. A matching additional file is recorded and a later byte change is rejected on restore. It is wired into eng/verify.ps1. Approval is a
version, hash and approval id, not a signature. The iOS experiment host now calls TryPlanCandidate before load when
selector-plan.txt is present. Approval stays outside the candidate directory.
The 2026-10-16 iOS 27 simulator accepted A with SELECTOR_PLAN and result=216,
then returned NotApproved for the same files when the approval hash did not
match, without running the update. A later simulator run of the same day restores the last known good version
when the new candidate is not approved, and an activation failure does not
fall back or rewrite that record. That host still does not call TryStart or
TrySelectCandidate. A later iOS 27 simulator run calls TryStartHostLoaded:
the selector decides and the host runs Run. A succeeds, an unapproved B falls
back to A, and an approved throwing B returns ActivationFailed without
fallback. This is not a new native entry. The rebuilt
experiment host was also measured earlier the same day: version A still
succeeds, a throwing update prints failure=ActivationFailed without its private
message, and a reflected message that starts with "payload file " is hidden. On the measured desktop composition result below, RuneCLR does not pursue unloadable hot-update R2R: an update that must be unloaded stays interpreted, and ordinary first-party execution does not repeatedly unload old assemblies.

The 2026-10-15 simulator pipeline built and installed a fixed host, then stopped
when composite crossgen crashed before linking an owner dylib. That negative
result is recorded in docs/ios-trusted-update-simulator.md; it is not downloaded
native execution.

The same access violation reproduced from a preserved component. A non-composite
Mach-O attempt was rejected by crossgen2 before codegen and is not that crash.

A separate output directory then let the same composite crossgen exit 0. The
object is not yet linked, so downloaded native execution remains unproven.

Version A now has a linked simulator dylib exporting _RTR_HEADER. Downloaded
native execution still needs a runtime method entry.

The simulator load mapped both owners. The entry breakpoint was on the wrong
symbol, so native execution is still unproven.

The corrected Execute breakpoint missed as well. Native execution is still unproven.

Version A's Business.Execute later hit at its downloaded symbol entry. B has
not been captured with that breakpoint.

B's Business.Execute was later captured in a different process and downloaded
dylib. Device signing and the managed success line remain open.

The 2026-10-16 `py -3 eng/verify-trusted-composition.py --runtime E:/runtime --output artifacts/trusted-composition-20261016-desktop --allow-known-collectible-blocker` desktop composition run reported `PASS five functional/execution controls; BLOCKED combined collectible R2R acceptance`; `controlsPassed=true`, `milestoneComplete=false`, and `status=blocked-collectible-r2r`; this is not native R2R for collectible modules and is not iOS or physical-device evidence. The collectible rejection is ReadyToRunInfo::Initialize in src/coreclr/vm/readytoruninfo.cpp, which logs Ready to Run disabled - collectible module and returns NULL; ReadyToRun, InterpMode, and ReadyToRunExcludeList do not enable collectible modules alone. On that measured result, RuneCLR does not pursue unloadable hot-update R2R: an update that must be unloaded stays interpreted, and ordinary first-party execution does not repeatedly unload old assemblies.








1. Keep #2 physical iOS acceptance paused until a target is reachable; do not
   schedule installation before then. Preserve the simulator A/B native-entry
   evidence. B's managed success line is now on stderr, so that simulator
   managed pair is recorded. In parallel, advance the desktop third trusted-update
   step. Its checked scope is now 270/270, including NotApproved, a stored plan reread without loading, host-loaded startup without a selector assembly load, a host callback or ITrustedUpdateHost closed after Tick returns, host-object identity that can be collected after the update releases it, EchoGeneric<T> for an object reference and an int, and a signal subscriber dropped when Listen returns, including when that call throws, and a candidate outside the content root is rejected before load. A .. path that still resolves inside the root is accepted, and one that resolves outside is rejected. Restoring last known good with the host's content root uses the same rule before load. Additional content hashes are checked before load and again when that record is restored. That is not an iOS simulator receipt or iOS-host integration. The selector checks are now 270/270, including host work completed between calls and dropped when the session closes, a throwing Work call that drops only its own new request, keeps an earlier open request and an earlier completed result, and does not keep the exception text, and a host object or signal kept from an earlier call that stays closed on the next call. A later signal subscription is rejected and stores no handler. Removing one subscriber while Listen is open drops only that subscriber. A subscriber that throws during Raise becomes ActivationFailed, keeps no exception text, and leaves the session open for the next Listen. An EchoObject that stores the host object and then throws becomes ActivationFailed, keeps no exception text, and a later EchoObject still returns the same reference after release clears the update field. A throwing EchoGeneric becomes ActivationFailed, keeps no exception text, and the next generic int and object echo still succeed. A boxed value passed to generic object echo throws ArgumentException before the update runs, and a string still comes back as the same reference. A generic method that does not return its type argument is not called. Null still throws ArgumentNullException, and Tick still runs. When a matching EchoGeneric<T>(T) is also present, that overload is used and the mismatched one is not called. An EchoObject that returns a different object still succeeds. The input is not retained, and release lets the created object be collected. Completing or failing a work id a second time is rejected and the first result stays. Completing that id after it is taken is also rejected. A blank work name fails that call, drops only the request made in that call, and keeps an earlier request. A null work name does the same and still leaves an earlier completed result to be taken. A whitespace-only name is rejected without trimming a name that contains other characters. Two requests with the same name keep distinct ids, and completing one does not complete the other. Results are taken in completion order, not request order. A failed result completed first is taken before a later success. An unknown work id is rejected and does not replace the open request. Closing the session drops an untaken failure, and the next session does not take that reason. The next session uses a new id, and the old id does not complete that request. A null host object and a null echoed object are rejected before the update runs. A null host callback is rejected the same way and does not select the no-callback Tick. A successful callback Tick does not run the plain Tick. If that callback throws, the plain Tick is not run either, and a later plain Tick still succeeds. The same split holds for an ITrustedUpdateHost Tick, including when Echo throws. When all three Tick shapes are present, each call runs only its own method. When several Listen methods are present, only the one that takes ITrustedUpdateSignals is called. If that method throws, the parameterless Listen is not called, and the next Listen still uses the signal method. When several Work methods are present, only the one that takes ITrustedUpdateWork is called. If that method throws, the parameterless Work is not called, its new request is dropped, and the next Work still uses the gate method. When several EchoObject methods are present, only the one that takes object and returns object is called. If that method throws, the parameterless EchoObject is not called, and the next EchoObject still uses the object method. When several ReleaseHeldObjects methods are present, only the parameterless void method is called. If that method throws, the ReleaseHeldObjects method that takes object is not called, and the next release still uses the parameterless method. When an instance Listen and a static Listen both take ITrustedUpdateSignals, only the static method is called. When the only signal Listen is an instance method, TryListen fails before calling it and does not call a static parameterless Listen. When an instance Work and a static Work both take ITrustedUpdateWork, only the static method is called. When the only gate Work is an instance method, TryWork fails before calling it and does not call a static parameterless Work. When an instance EchoObject and a static EchoObject both take object and return object, only the static method is called. When the only object EchoObject is an instance method, TryEchoObject fails before calling it and does not call a static parameterless EchoObject. When an instance ReleaseHeldObjects and a static ReleaseHeldObjects are both parameterless void methods, only the static method is called. When the only parameterless ReleaseHeldObjects is an instance method, TryReleaseHeldObjects fails before calling it and does not call a static ReleaseHeldObjects that takes object. When an instance Tick and a static Tick both take int and return int, only the static method is called. When the only Tick that takes int and returns int is an instance method, TryTick fails before calling it and does not call a static Tick that also takes ITrustedUpdateHost. A Listen declared only on a base type is not called, and TryListen does not call a parameterless Listen declared on the entry type. A Work declared only on a base type is not called, and TryWork does not call a parameterless Work declared on the entry type. An EchoObject declared only on a base type is not called, and TryEchoObject does not call a parameterless EchoObject declared on the entry type. A parameterless ReleaseHeldObjects declared only on a base type is not called, and TryReleaseHeldObjects does not call a ReleaseHeldObjects that takes object on the entry type. A Tick that takes int and returns int declared only on a base type is not called, and TryTick does not call a Tick that also takes ITrustedUpdateHost on the entry type. When a non-public Listen and a public Listen both take ITrustedUpdateSignals, only the public method is called. When the only signal Listen is non-public, TryListen fails before calling it and does not call a public parameterless Listen. When a non-public Work and a public Work both take ITrustedUpdateWork, only the public method is called. When the only gate Work is non-public, TryWork fails before calling it and does not call a public parameterless Work. When a non-public EchoObject and a public EchoObject both take object and return object, only the public method is called. When the only object EchoObject is non-public, TryEchoObject fails before calling it and does not call a public parameterless EchoObject. When a non-public ReleaseHeldObjects and a public ReleaseHeldObjects are both parameterless void methods, only the public method is called. When the only parameterless ReleaseHeldObjects is non-public, TryReleaseHeldObjects fails before calling it and does not call a public ReleaseHeldObjects that takes object. When a non-public Tick and a public Tick both take int and return int, only the public method is called. When the only Tick that takes int and returns int is non-public, TryTick fails before calling it and does not call a public Tick that also takes ITrustedUpdateHost. When one Tick takes int and returns long and another takes int and returns int, only the int-returning method is called. When the only Tick that takes int returns long, TryTick fails before calling it and does not call a Tick that also takes ITrustedUpdateHost. When one Listen takes ITrustedUpdateSignals and returns long and another takes ITrustedUpdateSignals and returns int, only the int-returning method is called. When the only signal Listen returns long, TryListen fails before calling it and does not call a parameterless Listen that returns int. When one Work takes ITrustedUpdateWork and returns long and another takes ITrustedUpdateWork and returns int, only the int-returning method is called. When the only gate Work returns long, TryWork fails before calling it and does not call a parameterless Work that returns int. When one EchoObject takes object and returns string and another takes object and returns object, only the object-returning method is called. When the only object EchoObject returns string, TryEchoObject fails before calling it and does not call a parameterless EchoObject that returns object. When one parameterless ReleaseHeldObjects returns int and another returns void, only the void method is called. When the only parameterless ReleaseHeldObjects returns int, TryReleaseHeldObjects fails before calling it and does not call a ReleaseHeldObjects that takes object and returns void. When one parameterless Activate returns int and another returns void, only the void method is called. When the only parameterless Activate returns int, selection fails before calling it, the version is not resident, and last known good is not written. When one Activate takes int and another is parameterless, and both return void, only the parameterless method is called. When the only Activate takes int, selection fails before the method body runs, the version is not resident, and last known good is not written. When an instance Activate and a static Activate are both parameterless void methods, only the static method is called. When the only parameterless Activate is an instance method, selection fails before calling it, does not call a static Activate that takes int, the version is not resident, and last known good is not written. A parameterless Activate declared only on a base type is not called, selection does not call a static Activate that takes int on the entry type, the version is not resident, and last known good is not written. When a non-public Activate and a public Activate are both parameterless void methods, only the public method is called. When the only parameterless Activate is non-public, selection fails before calling it, does not call a public Activate that takes int, the version is not resident, and last known good is not written. When a parameterless Activate throws, selection becomes ActivationFailed, does not call an Activate that takes int, keeps no exception text, the version is not resident, and last known good is not written. When one parameterless method is named activate and another is named Activate, only Activate is called. When the only parameterless method is named activate, selection fails before calling it, does not call an Activate that takes int, the version is not resident, and last known good is not written. When one entry type is named entry and another is named Entry, only Activate on Entry is called. When the only entry type is named entry, selection fails before calling its Activate, the version is not resident, and last known good is not written. When one parameterless Activate is an open generic method and another is not, only the non-generic method is called. When the only parameterless Activate is an open generic method, selection fails before calling it, does not call an Activate that takes int, the version is not resident, and last known good is not written. When the entry type name selects a nested type, only that nested Activate is called. When the entry type name uses a dot for a nested type, selection fails before calling either Activate, the version is not resident, and last known good is not written. When the entry type is an open generic type, selection fails before calling Activate, does not call Activate on another type, the version is not resident, and last known good is not written. When an open generic type and a non-generic entry type are both present, only Activate on the named non-generic type is called. When one parameterless ReleaseHeldObjects is an open generic method and another is not, only the non-generic method is called. When the only parameterless ReleaseHeldObjects is an open generic method, TryReleaseHeldObjects fails before calling it and does not call a ReleaseHeldObjects that takes object. When one Listen takes ITrustedUpdateSignals and is an open generic method and another is not, only the non-generic method is called. When the only signal Listen is an open generic method, TryListen fails before calling it and does not call a parameterless Listen. When one Work takes ITrustedUpdateWork and is an open generic method and another is not, only the non-generic method is called. When the only gate Work is an open generic method, TryWork fails before calling it and does not call a parameterless Work. When one Tick takes int and returns int and is an open generic method and another is not, only the non-generic method is called. When the only Tick that takes int and returns int is an open generic method, TryTick fails before calling it and does not call a Tick that also takes ITrustedUpdateHost. When one EchoObject takes object and returns object and is an open generic method and another is not, only the non-generic method is called. When the only object EchoObject is an open generic method, TryEchoObject fails before calling it and does not call a parameterless EchoObject. When one Tick takes int and ITrustedUpdateHost and is an open generic method and another is not, only the non-generic method is called. When the only Tick that takes int and ITrustedUpdateHost is an open generic method, TryTick fails before calling it and does not call a Tick that only takes int. When one Tick takes int and Func<int, int> and is an open generic method and another is not, only the non-generic method is called. When the only Tick that takes int and Func<int, int> is an open generic method, TryTick fails before calling it, the callback is not run, and a Tick that only takes int is not called. When EchoGeneric has two type parameters and another EchoGeneric has one, only the one-parameter method is called. When the only EchoGeneric has two type parameters, object and int echo fail before calling it, and Tick still runs. When one EchoGeneric returns object and another returns its type argument, only the type-argument method is called. When the only EchoGeneric returns object, object and int echo fail before calling it, and Tick still runs. When one EchoGeneric takes two arguments and another takes its type argument, only the one-argument method is called. When the only EchoGeneric takes two arguments, object and int echo fail before calling it, and Tick still runs. When one generic echo is named echoGeneric and another is named EchoGeneric, only EchoGeneric is called. When the only generic echo is named echoGeneric, object and int echo fail before calling it, and Tick still runs. When an instance EchoGeneric and a static EchoGeneric both take and return their type argument, only the static method is called. When the only EchoGeneric is an instance method, object and int echo fail before calling it, and Tick still runs. An EchoGeneric declared only on a base type is not called, a two-argument EchoGeneric on the entry type is not called, and Tick still runs. When a non-public EchoGeneric and a public EchoGeneric both take and return their type argument, only the public method is called. When the only one-argument EchoGeneric is non-public, object and int echo fail before calling it, a public two-argument EchoGeneric is not called, and Tick still runs. When one EchoGeneric takes its type argument by reference and another takes it by value, only the by-value method is called. When the only EchoGeneric takes its type argument by reference, object and int echo fail before calling it, and Tick still runs. When one EchoGeneric returns its type argument by reference and another returns it by value, only the by-value method is called. When the only EchoGeneric returns its type argument by reference, object and int echo fail before calling it, and Tick still runs. When one EchoGeneric returns an array of its type argument and another returns the type argument, only the type-argument method is called. When the only EchoGeneric returns an array of its type argument, object and int echo fail before calling it, and Tick still runs. When one EchoGeneric takes an array of its type argument and another takes the type argument by value, only the by-value method is called. When the only EchoGeneric takes an array of its type argument, object and int echo fail before calling it, and Tick still runs. When one EchoGeneric takes a list of its type argument and another takes the type argument by value, only the by-value method is called. When the only EchoGeneric takes a list of its type argument, object and int echo fail before calling it, and Tick still runs. When one EchoGeneric returns a list of its type argument and another returns the type argument, only the type-argument method is called. When the only EchoGeneric returns a list of its type argument, object and int echo fail before calling it, and Tick still runs. When one EchoGeneric takes a nullable of its type argument and another takes the type argument by value, the unreadable nullable signature is skipped and only the by-value method is called. When the only EchoGeneric takes a nullable of its type argument, the unreadable signature is skipped, object and int echo fail before calling it, and Tick still runs. When one EchoGeneric returns a nullable of its type argument and another returns the type argument, the unreadable nullable signature is skipped and only the type-argument method is called. When the only EchoGeneric returns a nullable of its type argument, the unreadable signature is skipped, object and int echo fail before calling it, and Tick still runs. When one EchoGeneric takes a pointer to its type argument and another takes the type argument by value, only the by-value method is called. When the only EchoGeneric takes a pointer to its type argument, object and int echo fail before calling it, and Tick still runs. When one EchoGeneric returns a pointer to its type argument and another returns the type argument, only the type-argument method is called. When the only EchoGeneric returns a pointer to its type argument, object and int echo fail before calling it, and Tick still runs. When one EchoGeneric takes its type argument as an out parameter and another takes it by value, only the by-value method is called. When the only EchoGeneric takes its type argument as an out parameter, object and int echo fail before calling it, and Tick still runs. When one EchoGeneric takes its type argument as an in parameter and another takes it by value, only the by-value method is called. When the only EchoGeneric takes its type argument as an in parameter, object and int echo fail before calling it, and Tick still runs. When the only EchoGeneric takes its type argument by value and the parameter is marked in, object and int echo call that method and Tick still runs. When the only EchoGeneric takes its type argument by value and the parameter is marked out, object and int echo call that method and Tick still runs. When the only EchoGeneric takes its type argument by value and the parameter is optional, object and int echo call that method and Tick still runs. When the only EchoGeneric has a class constraint, an object echo calls it, an int echo fails before the body runs, and Tick still runs. When the only EchoGeneric has a struct constraint, an int echo calls it, an object echo fails before the body runs, and Tick still runs. When the only EchoGeneric is constrained to Exception, an exception echo calls it, an object echo and an int echo fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IDisposable, a disposable echo calls it, an object echo and an int echo fail before the body runs, and Tick still runs. When the only EchoGeneric has a public parameterless constructor constraint, an object echo and an int echo call it, a string echo fails before the body runs, and Tick still runs. When the only EchoGeneric has a class constraint and a public parameterless constructor constraint, an object echo calls it, a string echo and an int echo fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IComparable<T>, a string echo and an int echo call it, an object echo fails before the body runs, and Tick still runs. When the only EchoGeneric is constrained to Delegate, a delegate echo calls it, an object echo and an int echo fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IEnumerable<char>, a string echo calls it, an object echo and an int echo fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEnumerable<char> and IComparable<T>, a string echo calls it, a char array, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric has a class constraint and is constrained to IComparable<T>, a string echo calls it, an object echo and an int echo fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IDisposable and a public parameterless constructor, a memory stream echo calls it, a timer, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to Exception and a public parameterless constructor, an invalid-operation exception echo calls it, a target-invocation exception, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IEnumerable<object>, an object-array echo calls it, a string, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IComparer<string>, a comparer of object echo calls it, a string, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IList<object>, a string-array echo and an object-array echo call it, a string, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IList<object>, a list of object is called, while a list of string, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IReadOnlyList<object>, a list of string and a list of object are called, a string, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IList<string>, a list of string and a string array are called, a list of object, an object array, a string, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IList<int>, an int array and a list of int are called, a string array, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IList<object>, a string array is called, an int array, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IReadOnlyList<object>, a list of string is called, a list of int, an int array, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IComparer<int>, a comparer of int is called, a comparer of object, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IList<string>, a one-dimensional string array is called, a rectangular string array, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IList<string>, a zero-based string array is called, a string array with a non-zero lower bound, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IList<string[]>, a jagged string array is called, a string array, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IReadOnlyList<Exception[]>, a jagged array of invalid-operation exceptions and a jagged array of exceptions are called, an exception array, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IList<Exception[]>, a jagged array of invalid-operation exceptions and a jagged array of exceptions are called, an exception array, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IList<Exception[]>, a list of exception arrays is called, a list of invalid-operation-exception arrays, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IReadOnlyList<Exception[]>, a list of invalid-operation-exception arrays and a list of exception arrays are called, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IComparer<Exception[]>, a comparer of exception arrays and a comparer of object are called, a comparer of invalid-operation-exception arrays, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IComparer<InvalidOperationException[]>, a comparer of invalid-operation-exception arrays and a comparer of exception arrays are called, a comparer of exception, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to Func<Exception[], int>, a function of exception arrays and a function of object are called, a function of invalid-operation-exception arrays, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to Func<object, Exception>, a function returning an exception and a function returning an invalid-operation exception are called, a function returning object, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to Func<Exception[], Exception>, a function of exception arrays returning an exception and a function of object returning an invalid-operation exception are called, a function of object returning object, a function of invalid-operation-exception arrays returning an invalid-operation exception, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to Action<Exception[]>, an action of exception arrays and an action of object are called, an action of invalid-operation-exception arrays, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to Action<int>, an action of int is called, an action of object, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to Func<int, object>, a function of int returning object and a function of int returning string are called, a function of object returning object, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to Func<object, int?>, a function of object returning a nullable int is called, a function of object returning int, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to Func<object, string>, a function returning string and a function whose return is annotated as nullable string are both called, an object and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to Func<int?, object>, a function of nullable int is called, a function of int, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to Func<string, object>, a function of string and a function whose input is annotated as nullable string are both called, a function of int, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to Predicate<string>, a predicate of string and a predicate of object are called, a function of string returning bool, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to Func<string, bool>, a function of string returning bool and a function of object returning bool are called, a predicate of string, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to Comparison<string>, a comparison of string and a comparison of object are called, a function of two strings returning int, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to Func<string, string, int>, a function of two strings and a function of two objects are called, a function of object and int, a comparison of string, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to Func<string, string, object>, a function of two strings returning object and a function of two objects returning string are called, a function of two strings returning int, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to Func<string, string, object>, a function of two strings returning object is called, a function of string and int returning string, a function of int and string returning string, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IProgress<string>, a progress of string and a progress of object are called, a progress of int, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IProgress<int>, a progress of int is called, a progress of object, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IObservable<Exception>, an observable of exception and an observable of invalid-operation exception are called, an observable of object, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IObservable<int>, an observable of int is called, an observable of object, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IObserver<Exception>, an observer of exception and an observer of object are called, an observer of invalid-operation exception, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IObserver<int>, an observer of int is called, an observer of object, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IEquatable<string>, a string is called, an object that is only equatable to object, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IEquatable<int>, an int echo calls it, a string, an object that is only equatable to object, and an object fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IComparable<string>, a string and an object that is comparable to object are called, a plain object and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to IComparable<int>, an int echo calls it, a string, an object that is comparable to object, and a plain object fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<string> and IComparable<string>, a string is called, an object that is only comparable to object, an object that is only equatable to object, a plain object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<int> and IComparable<int>, an int echo calls it, a string, an object that is only comparable to object, an object that is only equatable to object, and a plain object fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<string> and IComparable<string>, a string and another type that implements both interfaces are called, an object that is only comparable to object, an object that is only equatable to object, a plain object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<int> and IComparable<int>, an int echo calls it, a struct that implements both interfaces is rejected before the generic call, and a string and an object fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<int> and IComparable<int>, an int echo and a class that implements both interfaces are called, a struct that implements both interfaces is rejected before the generic call, and a string and an object fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<int> and IComparable<int>, an int echo and a class that implements both are called, a class that implements only IEquatable<int>, a class that implements only IComparable<int>, and an object fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<int> and IComparable<int>, an int echo and a type whose interface extends both are called, a type that implements only one of them and an object fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<int> and IComparable<int>, an int echo and a derived class whose base implements both are called, a type that implements only one of them and an object fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<int> and IComparable<int>, an int echo and a generic box closed over int are called, a generic box closed over string and an object fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<int> and IComparable<int>, an int echo and a class derived from a generic box closed over int are called, a generic box closed over string and an object fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<int> and IComparable<int>, an int echo and a generic box closed over int are called, a generic box closed over nullable int and an object fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<DayOfWeek> and IComparable<DayOfWeek>, a generic box closed over that enum is called, an enum value is rejected before the generic call, and a generic box closed over int, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<DateTimeKind> and IComparable<DateTimeKind>, a box closed over that enum is called, an enum value is rejected before the generic call, and a box closed over a different enum, an object, and an int fail before the body runs and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<DateTimeKind> and IComparable<DateTimeKind>, a class derived from a generic box closed over that enum is called, an enum value is rejected before the generic call, and a class derived from a generic box closed over a different enum, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<DateTimeKind> and IComparable<DateTimeKind>, a generic box closed over that enum is called, an enum value is rejected before the generic call, and a generic box closed over the nullable enum, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<DateTimeKind> and IComparable<DateTimeKind>, a class that implements both is called, an enum value is rejected before the generic call, and a class that implements only IEquatable<DateTimeKind>, a class that implements only IComparable<DateTimeKind>, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<DateTimeKind> and IComparable<DateTimeKind>, a type whose interface extends both is called, an enum value is rejected before the generic call, and a type that implements only one of them, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<DateTimeKind> and IComparable<DateTimeKind>, a derived class whose base implements both is called, an enum value is rejected before the generic call, and a type that implements only one of them, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<DateTimeKind> and IComparable<DateTimeKind>, a class that implements both is called, a struct that implements both is rejected before the generic call, and a string, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<DateTimeKind> and IComparable<DateTimeKind>, a class that implements both enum interfaces is called, an enum value is rejected before the generic call, and a type that implements both object interfaces, a type that implements only one of them, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<DateTimeKind> and IComparable<DateTimeKind>, a class that implements both specific enum interfaces is called, an enum value is rejected before the generic call, and a class that implements both interfaces closed over System.Enum, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<DateTimeKind> and IComparable<DateTimeKind>, a class that implements both generic enum interfaces is called, an enum value is rejected before the generic call, and a class that implements IEquatable<DateTimeKind> plus the non-generic IComparable, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both IEquatable<DateTimeKind> and IComparable<DateTimeKind>, a class that implements both non-nullable enum interfaces is called, an enum value is rejected before the generic call, and a class that closes either interface over the nullable enum, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to struct, an int echo calls it, an enum value is rejected before the generic call, and an object, a string, and a class fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to System.Enum, an enum value is rejected before the generic call, and an object, a class, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to class, an object and a class are called, an enum value is rejected before the generic call, and an int fails before the body runs, and Tick still runs. When the only EchoGeneric is constrained to new(), an object, a class, and an int echo are called, an enum value is rejected before the generic call, and a string fails before the body runs, and Tick still runs. When the only EchoGeneric is constrained to both class and new(), an object and a class with a public parameterless constructor are called, an enum value is rejected before the generic call, and a string and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to struct and both IEquatable<DateTimeKind> and IComparable<DateTimeKind>, an enum value is rejected before the generic call, and an object, a class, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to class and both IEquatable<DateTimeKind> and IComparable<DateTimeKind>, a class that implements both is called, an enum value is rejected before the generic call, and an object, a string, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to class, new(), and both IEquatable<DateTimeKind> and IComparable<DateTimeKind>, a class that implements both and has a public parameterless constructor is called, an enum value is rejected before the generic call, and a class without that constructor, an object, a string, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to class, new(), and both IEquatable<DateTimeKind> and IComparable<DateTimeKind>, a class with a public parameterless constructor is called, an enum value is rejected before the generic call, and a class with only a private parameterless constructor, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to class, new(), and both IEquatable<DateTimeKind> and IComparable<DateTimeKind>, a class with a public parameterless constructor is called, an enum value is rejected before the generic call, and a class whose only public constructor has an optional parameter, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to class, new(), and both IEquatable<DateTimeKind> and IComparable<DateTimeKind>, a derived class whose base implements both and which has its own public parameterless constructor is called, an enum value is rejected before the generic call, and a class without a public parameterless constructor, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to class, new(), and both IEquatable<DateTimeKind> and IComparable<DateTimeKind>, a derived class with its own public parameterless constructor is called, an enum value is rejected before the generic call, and a derived class that only declares a parameterized constructor, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to class, new(), and both IEquatable<DateTimeKind> and IComparable<DateTimeKind>, a class that also declares a static constructor is called, an enum value is rejected before the generic call, and a derived class that only declares a parameterized constructor, an object, and an int fail before the body runs, and Tick still runs. When the only EchoGeneric is constrained to class, new(), and both IEquatable<DateTimeKind> and IComparable<DateTimeKind>, a class that declares both a public parameterless constructor and another constructor is called, an enum value is rejected before the generic call, and a derived class that only declares a parameterized constructor, an object, and an int fail before the body runs, and Tick still runs. The console sample self-test prints NULL-CALLBACK, TICK ActivationFailed, CALLS-BEFORE 0, TICK 2, and CALLS 1 for that path. When several EchoGeneric methods have the same shape, the selector does not choose among them by constraints, and the reflection order itself is not a contract.

2. Validate #13's identical business sources in interpreted IL and trusted R2R builds,
   including independently built R2R updateable and non-updateable modules
   running together without requiring one composite image. Verify shared API
   identity, equivalent behavior and actual R2R execution of selected methods.
   First-party modules are trusted and do not inherit UGC's interpreter-only
   policy. #12's simulator native-entry evidence is recorded above; physical
   iOS post-install R2R delivery, signing/loading and device execution remain
   paused until a reachable target is available. Existing IL results do not
   establish that path.
   A failed native load may leave code resident, so record the restart boundary;
   disk-cache deletion is not an unloading result.
   This work does not depend on #5/#6/#7.
3. Define #14's direct-object/ownership matrix and #15's separate compiler language,
   runtime feature, framework and UGC-policy compatibility. Publish diagnostics
   and an honest supported surface; source syntax follows the selected compiler's
   latest stable C# version independently of the UGC API policy.
4. Integrate one real game's trusted hot-update path: startup version selection,
   next-start rollback, errors, callback costs and retention. Same-process version
   switching and native residency growth are later decisions, not first-loop
   gates. This is the first stage of #9, independent of arbitrary public UGC
   readiness.
5. Extend #8 events/resources, #7 allocation observation and the remaining
   #4/#5/#6 package/capability/budget boundaries for UGC; then validate the UGC
   stage of #9 and #10 public readiness. Shared host work can proceed earlier.

The [roadmap](roadmap.md) links the dedicated hot-update issues. Desktop
interpreter feasibility, controlled packages, pumping and budget prototypes
already have evidence below; do not repeat them as prerequisites.

## Scope of the retained UGC sequence

The original sequence was arranged on 2026-10-12 and is retained below with
its dated evidence. Its restricted-author rules apply to UGC, rather than
imposing those constraints on every trusted hot-update host.

UGC map code and map-private managed dependencies use interpretation first.
Trusted host/framework code may remain native. Authors submit source or IL;
controlled builds create runnable packages. Future R2R/JIT must preserve the
same restrictions and cannot directly execute author-supplied native bodies.

The user also requested a later naming review: scripts need not live in a
container called a map. Plan the public API/package/documentation rename as a
separate contribution after current platform checks; the replacement terminology
is not selected yet. Existing names do not constrain the intended embedding API.

## Current evidence

The initial [host-pumped lifecycle](host-pumped-sessions.md) is now implemented
as an independent #8 increment: explicit start/tick/stop, host-supplied delta,
automatic failure cleanup and retained-stopped-session collection. Fresh
Windows verification passes 37 lifecycle/84 packaging/15 player cases; required
interpreter lifecycle also passes 37/37. The native pumped 16-case/74-collection
suite demonstrates a single cumulative allowance across six successful host
returns before tick 7 terminates. Synchronous and stock controls remain passing.
The [controlled-package pumped lane](package-execution-tests.md) subsequently
passes 22/22 on Windows stock and required interpretation, with unchanged
15/15 synchronous controls. The later
[controlled-package native-budget lane](controlled-package-native-budget.md)
passes 33/33 with twenty-five native-budget collections and exact cumulative
execution/cleanup accounting. Game-facing events/resources, mobile execution
of this controlled-package combination, and real-device acceptance remain
follow-ups.
The updated [iOS simulator application](ios-pumped-budget-acceptance.md)
separately passes the diagnostic pumped-budget 16-case/74-collection route
with post-install author IL and the current trusted host. Updated Android
applications and physical-device results remain outstanding.

Current checkpoint, 2026-10-15: [fresh-author entry acceptance](ios-fresh-author-entry-acceptance.md)
binds nine selected interpreter method groups in IL compiled after simulator
installation, with 15 budget cases and all 73 contexts collected. The dedicated
open-delegate branch is now covered in a separate
[three-path capture](ios-open-delegate-entry-acceptance.md) with the same nine
method groups and15/73 results. The latest
[read-only device refresh](ios-device-readiness.md) at 06:12 UTC reports zero
reachable physical targets; simulator evidence does not close real-device #2.
The paragraphs below retain the earlier experiment sequence, with later
acceptance links where preparation has advanced.

On 2026-10-14 the matching Windows 099dacd Release budget increment now has
[independent terminal/finalizer/host acceptance](windows-release-budget-acceptance.md),
[complete production functional controls](windows-release-production.md) and
[controlled joined-worker accounting](windows-terminal-concurrency.md).
Respect their sampled-entry and concurrent-snapshot limits. The smallest
[terminal-counter optimization](windows-budget-increment-hotpath.md) now has
separate20405f7 matching Release products,
[execution/cleanup/finalizer/host acceptance](windows-budget-increment-acceptance.md)
and [concurrent/production controls](windows-budget-increment-concurrency.md).
The actual normal admitted machine-code path has five locked RMWs instead of
six. [Bracketed same-machine measurement](windows-budget-increment-performance.md)
now shows14.73-16.06% less budgeted callback time in the fixed kernel, with
identical managed images and312 collections across24 processes. Original099
products and evidence remain intact. Fresh [matching mobile core builds](mobile-budget-increment-builds.md)
now pass on iOS simulator ARM64 and Android x64 Release, with downloaded bound
receipts and exact37-source composition. New [iOS application/entry acceptance](ios-budget-increment-acceptance.md)
passes15/73 and147 samples/nine requested method groups; independent root
review binds actual source/products, installed observations and ARM64 bytes.
New [Android ABI/framework](android-budget-increment-layout.md) and
[fresh APK acceptance](android-budget-increment-acceptance.md) pass15/73 with203
identical installed hashes. An independent frozen-product review also verifies
actual APK bytes, every installed observation and all 73 scenario rows, with
four additional transport corruption controls. New
[Android observer contract preparation](android-budget-increment-entry-preparation.md)
passed matching machine-code/DWARF checks and five rejection controls. Its
subsequent [actual method-entry acceptance](android-budget-increment-entry-acceptance.md)
now records 178 valid samples across nine requested groups, 15/73 functional
acceptance and a separate same-APK gate-off run on the Android x64 emulator.
The requested [Lua count-hook reference](lua-budget-overhead.md)
now passes raw-log review: every1/100/1000 traced instructions cost6.37x/2.49x/2.44x
the no-hook arithmetic median on Windows. Its non-atomic, catchable hook is
not matched terminal enforcement. The requested [batch100/batch1000 experiment](budget-batching-experiment.md)
is now implemented and measured. The [best-exact desktop comparison](budget-batch-best-exact.md)
passes 48 processes/624 collections: batching saves 44% on arithmetic but
regresses 15-17% on entities. The [mobile timing and cadence record](mobile-batch-measurement.md)
includes actual full/tail settlements on both platforms and separate
debugger-free timing. Android configured arithmetic medians fall from
1.90-1.94x the no-config baseline to 1.095x/1.068x at 100/1000; the extra
benefit of 1000 over 100 is not stable, and iOS timing remains variable. Keep
exact accounting as default and N100 opt-in. Representative physical-device
performance and actual device IL loading/retirement remain outstanding.

The later 2026-10-13 [Android session-policy validation](android-session-policy-validation.md)
passes the matching source-built Checked x64 runtime: 24/24 lifecycle, 15/15
controlled-package cases, three collected sample sessions and five core
selection/refusal controls. The required path does not JIT-fallback after a real
compiler refusal and recovers into twenty successfully collected sessions.
The [iOS simulator session-policy validation](ios-session-policy-acceptance.md)
also records the matching runtime experiment. Its separate
[Release refusal/recovery control](ios-session-policy-refusal.md) now passes one
real scoped compiler refusal, refused-context collection and twenty successful
recovery sessions/collections. The [fresh Android Release core assessment](android-session-policy-release-build-assessment.md)
also passes source, compile and frozen metadata checks; it does not establish
APK execution. The later [Release APK transport experiment](android-session-policy-release-entry-preparation.md)
passes matching construction/deployment and debugger attach/detach followed by
twenty functional sessions/collections. That transport receipt retains
entryProofCollected=false. The subsequent [Release native-entry samples](android-session-policy-entry.md)
cover nine fixture method groups, and an independent
[non-debugger Release selection run](android-session-policy-release-functional.md)
passes twenty exact sessions/collections with unchanged installed bytes.
The later [independent Release production and control lanes](android-session-policy-release-production.md)
pass 24/24 lifecycle, 15/15 packages, three sample collections, scoped compiler
refusal followed by twenty successful recovered collections, ordinary JIT and
unmarked fallback on the same frozen APK. Earlier evidence below remains
historical. Physical devices, production/refusal method-entry samples,
fast-dispatch coverage and further execution-boundary controls remain open.

- [#4](https://github.com/ReneeGA2020/RuneCLR/issues/4): the local controlled
  source/IL CLI and versioned managed-IL intake, including the later capability
  increment, now pass 84/84 packaging
  regressions; the existing lifecycle suite remains 22/22. Fresh operator-built
  source/import/source packages also pass collection/static reset on the pinned
  private interpreter with successful callback dumps. See
  [the contract, commands and evidence](controlled-packaging.md). Server approval
  authentication remains open. The [new Android host/profile](android-controlled-packages.md)
  passes 8/8 controlled package cases plus the original 22/22 late-IL suite;
  iOS new-profile deployment and Android interpretation remain open.

- The [iOS R2R investigation](ios-r2r-investigation.md) captures the original
  production PC-zero fault under LLDB. The later [minimal reproduction](ios-r2r-minimal.md)
  identifies stale collectible cached-interface state. The private native
  candidate passes [Debug lifecycle/package comparisons](ios-r2r-fix-validation.md),
  [explicit interface regressions](ios-r2r-patched-regressions.md) and
  [matching Release package acceptance](ios-r2r-release-packages.md). The
  [upstream defect register](upstream-bugs/README.md) tracks this confirmed
  official-source defect as RCLR-UP-001 with a local fix and an unsubmitted
  report draft; official-fix replacement still requires independent regression
  review. This does not establish physical-device acceptance.

- [#5](https://github.com/ReneeGA2020/RuneCLR/issues/5): the
  [initial static gameplay policy](capability-policy.md) checks every entry/private
  IL image at packaging and versioned loading. Its 25 focused regressions cover
  allowed sessions, denied APIs/unsafe routes, recomputed hashes, profile
  downgrade and identity spoofing. Runtime-backed interpreter selection, hard
  budgets and target-device acceptance remain open; this does not close #5.

- [#1](https://github.com/ReneeGA2020/RuneCLR/issues/1): the pinned Windows
  interpreter lifecycle baseline has passed locally, including twelve cases,
  private dependencies, generic state and a post-host-build map. See
  [the detailed evidence](interpreter-experiment.md).
- [#3](https://github.com/ReneeGA2020/RuneCLR/issues/3): Release synthetic
  kernels have been measured against Lua and V8; see
  [the performance record](performance-experiment.md). The first desktop
  [real-session/boundary increment](session-performance.md) is now measured;
  callback distributions, real workloads, devices and budget overhead remain
  open rather than a reason to declare #3 complete.
- [#2](https://github.com/ReneeGA2020/RuneCLR/issues/2): real-device RuneCLR
  loading/retirement remains unverified. The
  [environment audit](platform-validation.md) records concrete missing tooling
  and separates it from observed Windows results.
  A later [remote Mac preparation](remote-mac-experiment.md) passed stock
  macOS ARM64 lifecycle and a native simulator smoke; managed iOS execution
  was initially outstanding. The later [managed simulator result](ios-simulator-experiment.md)
  passes the actual harness with selective trusted R2R and Runtime IL-only,
  retaining the fully R2R host interface crash on Preview 6, official RC1 and the pinned
  .NET 12 Debug source build as a limitation. The source selective full harness
  now also passes 21/21 and post-install 22/22 with direct callback IR and
  private-generic interpretation evidence; its mini-fixture's 20/20 result is
  recorded separately. Real-device
  acceptance remains outstanding.

## 1. Measure the current session and host boundary — #3

**Dependency:** the proven desktop interpreter layout and existing lifecycle
host; no new production execution backend is needed.

**Deliverable:** extend local measurement beyond warmed kernels to the current
RuneCLR session path. Separate load/start, gameplay callbacks, stop/cleanup and
diagnostic collection; exercise calls into the shared host API and collect
allocation/GC observations. Preserve a same-IL JIT development baseline and
record runtime selection evidence.

**Acceptance:** reproducible commands, workload sizes, raw samples, source and
runtime hashes, checksums/expected gameplay effects and clear timing boundaries.
Report steady-state callback distributions separately from whole-session cost.
Allocation counters describe the measured process/thread scope, not map-owned
heap isolation. Diagnostic forced GC must not be included in a claimed normal
per-frame policy.

The coordinating agent owns integration and the result report. This desktop
extension still leaves target-device, real-game and eventual budget-overhead
measurements open under [#3](https://github.com/ReneeGA2020/RuneCLR/issues/3).

## 2. Build the minimum controlled source/IL-to-package path — #4

**Dependency:** existing map contracts and collectible lifecycle tests. The
session measurements give a baseline for package/load regressions, but do not
need to settle production performance before packaging starts.

**Deliverable:** a local prototype of the controlled server pipeline: accept
source or managed IL, compile/validate using fixed project-owned settings and
approved references, then produce a versioned approved package. The prototype
does not run arbitrary submitted build projects, scripts or NuGet restore.
Document the supported initial language/library surface and package identity.

Split implementation into three independently reviewable tasks once #4 begins:

| Task | Owned deliverable | Focused acceptance |
| --- | --- | --- |
| Manifest and content hashes | Versioned manifest, package file list, API compatibility fields and deterministic hashing rules | Detect changed/missing/extra contents, invalid paths and incompatible format/API; explain that a hash alone does not establish trusted approval |
| Fixed-reference source compilation | Compiler entry point using approved references/options, bounded diagnostics and declared language version | Compile a valid map; reject missing/unsupported references and supplied build instructions; record compiler/reference identities |
| IL-only intake | PE/metadata inspection of map and private managed dependencies without executing them | Accept declared supported managed IL; reject malformed, mixed-mode and embedded R2R/native-body input for the initial profile with explicit reasons; do not equate IL-only with safe API use |

Agents can own these three tasks in parallel; the coordinating agent defines
their common input/output contract, integrates them and owns end-to-end tests.
File ownership must be agreed before overlapping edits. This planning
contribution scheduled the split. The three components and their local CLI are
now implemented; see [the controlled packaging contract](controlled-packaging.md).

**First increment implemented:** explicit [package dependency resolution](package-resolution.md)
replaces the mobile-unsupported `AssemblyDependencyResolver`. Windows normal
and private Checked interpreter suites pass 22/22. The [actual Android harness](android-lifecycle-experiment.md)
passes 21/21, then 22/22 with IL compiled after APK installation, on both the
historical Preview 6 and updated official .NET 11 RC1
JIT-capable runtime. Android interpretation remains separate. The subsequent
local tool adds source/IL compilation/intake and a versioned package format;
authenticated approval/distribution remains outstanding. Keep Abstractions
shared, private dependencies in each collectible session, and resolution of
trusted framework dependencies explicit. Preserve A -> B -> A behavior with
same-name version-distinct dependencies; do not rely on unrestricted default
context fallback or desktop hostpolicy as the portable contract.

**Acceptance:** source and IL paths both create approved packages that load in
the desktop lifecycle harness, including a package compiled after the host.
Tampering/rejected input fails before map execution with host-owned diagnostics.
Unloading and next-map recovery still pass. Record producer provenance and
content identity; production authentication/distribution can remain a separately
stated limitation. Desktop resolver tests prepare mobile integration, not proof
of mobile behavior.

Track this work in [#4](https://github.com/ReneeGA2020/RuneCLR/issues/4), with
the dependency policy coordinated with
[#5](https://github.com/ReneeGA2020/RuneCLR/issues/5). Do not implement source
compilation or packaging merely by adding a plan. The current local increment
has executable compiler/intake/manifest/pipeline regressions, including private
dependency A -> B -> A isolation, tamper recovery and source/import lifecycle.
Mobile versioned-package deployment is the next packaging/platform integration
increment; prior mobile results validate the preceding host snapshot.

## Parallel lane: prepare devices, then prove mobile lifecycle — #2

**Environment preparation can run beside steps 1 and 2.** An owner-supplied M1
Mac with Xcode and working managed iOS simulator deployment is now available.
Preserve the measured configurations, compare the latest official release
package/current source runtime, and locate signing setup and a real iOS device.
The Windows Android SDK/JDK/NDK/emulator lane now runs
the full lifecycle harness with official CoreCLR. For Android interpretation,
prepare an appropriate runtime-build environment and interpreter-enabled binaries
with positive method evidence; repeat on an ARM64 device. Use
[the platform checklist](platform-validation.md), not presumed connectivity
from Cindy's remote phone.

**Runtime/app work depends on:** a matching private mobile runtime/framework
layout and mobile-compatible package resolution. Begin with upstream CoreCLR
samples, then use the RuneCLR lifecycle fixtures in app wrappers.

**Acceptance:** prove execution of IL built after the installed host, actual
interpretation of UGC/private dependencies, static-state reset, ordinary-failure
cleanup, resource release and repeated collectible-context retirement on a
physical iOS device. Record versions/hashes and runtime diagnostics. Android
interpretation gets its own platform evidence; emulator results do not replace
iOS-device acceptance.

Missing environments are recorded blockers. Continue the independent desktop
tasks and schedule toolchain setup separately; environment preparation alone
does not pass platform milestones. [#2](https://github.com/ReneeGA2020/RuneCLR/issues/2)
remains open until its real-device acceptance is met.

## 3. Narrow the supported execution and API surface — #5

**Dependency:** #4's package/reference/dependency identities; #2 supplies
platform evidence as it becomes available.

**Deliverable:** an initial capability/dependency profile covering approved
framework and game APIs, reflection, dynamic loading, native interop and
background work. State which checks happen at intake and which require runtime
enforcement. Establish selection coverage for map-owned methods rather than
presenting method-filter switches as an author-resistant policy.

**Acceptance:** supported maps still load and retire; focused fixtures reject
disallowed dependencies/API routes with bounded diagnostics. Verify constructor,
generic and private-dependency coverage, and unsupported native/JIT/R2R routes.
Document any remaining bypasses/trust assumptions instead of calling the initial
profile a public hostile-code sandbox.

Track [#5](https://github.com/ReneeGA2020/RuneCLR/issues/5). Source review of
runtime control points can occur earlier; final enforcement depends on the
profile being explicit.

## 4. Implement safe terminal execution budgets — #6

**Dependency:** #5's interpreted ownership and supported call boundaries. Keep
runtime changes small and switch-controlled in the separate runtime checkout.
Desktop experimentation can start while mobile validation proceeds; release
claims on each platform require its own regressions.

The [source-reviewed implementation plan](runtime-session-budget-plan.md) records
the actual session-policy source anchors and the next matching desktop patch:
native binder-owned irreversible state, common dispatch charging, owner-aware
catch/filter suppression, finite cleanup reserve and safe finalizer handling.
The separate [diagnostic accounting increment](runtime-session-meter.md) is now
implemented and measured on matching Windows Checked inputs: per-binder counters,
actual owner-aware IR dispatch, twenty fresh sessions per metered lane, boundary
and isolation controls, and joined concurrency. Existing lifecycle 24/24,
player 15/15 and four official loader controls also pass on that private build.
This non-throwing meter continues after exhaustion. Persistent terminal state,
catch/filter suppression, bounded cleanup and finalizer handling remain next;
the milestone is not complete. The later
[terminal prototype](runtime-session-terminal-prototype.md) now establishes
sticky exhaustion, author catch/filter suppression and finite cleanup reserves
for its measured Windows Checked cases. All44 isolated lanes,20 bad/good pairs,
the unchanged production24/24/player15/15 and four official loader controls pass.
The later [finalizer boundary](runtime-session-finalizer-boundary.md) passes
nine scoped recovery cases and six ordinary fatal-exception controls on a
matching Windows Checked build. A later [host budget prototype](host-instruction-budget.md)
passes15 isolated cases and73 collections with explicit opt-in limits and safe
scalar results. The [matching mobile build preparation](mobile-instruction-budget-builds.md)
now combines that source with CID v2; the later
[mobile budget acceptance](mobile-host-budget-acceptance.md) records actual
iOS simulator15/73 functional results and a fresh Android framework/layout.
The separate iOS normal run now also passes installed-before/after sampling,
and Android's strict emulator budget audit passes 15/73 with matching identity
bindings. A separate iOS debugger lane passes 147 entry samples across nine
requested author method groups. The later
[Android budget entry acceptance](android-budget-entry-acceptance.md) passes178
samples across its nine requested groups and a separate same-APK gate-off15/73
run. The [matching Release cost experiment](budget-overhead.md) measures a4.80x
configured-meter ratio for its arithmetic callback after emulator cleanup.
The later [Release acceptance](windows-release-budget-acceptance.md) closes its
scoped terminal/finalizer/host baseline. Subsequent hot-path and
[desktop batching comparisons](budget-batch-best-exact.md), plus
[mobile arithmetic measurements](mobile-batch-measurement.md), are accepted
within their measured scope. Representative physical-device performance and
physical-device validation remain outstanding.
Remaining EH/concurrent topologies and mobile/physical-device
regressions remain open. The
prototype deliberately has a separately named private factory rather than a
complete terminal capability bit. A throw-only counter likewise cannot satisfy
the milestone.

**Deliverable:** interpreter-enforced accounting plus termination that regains
host control for the supported profile, with a persistent terminated session
state. Declare costly framework/native-call restrictions and accounting.

**Acceptance:** dead loops and catch-and-continue loops cannot keep executing
game APIs; host cleanup and the next map work. Include constructors, nested
calls, exception filters/finally, cleanup/finalizer policy and failure paths.
Runtime unwinding must preserve CLR invariants. Cooperative `Charge()` and
arbitrary native jumps are not substitutes. Run relevant upstream tests and
the RuneCLR lifecycle suite on the patched runtime; measure enforcement cost.

Track [#6](https://github.com/ReneeGA2020/RuneCLR/issues/6). Full-framework
mode 3 is not a prerequisite for interpreting and controlling UGC.

## 5. Extend memory and host-owned scheduling — #7 / #8

These two contributions can proceed in parallel after package/capability and
terminal-session contracts are established. Earlier telemetry/design is useful,
but must not predeclare enforcement complete.

| Issue | Deliverable | Acceptance and dependencies |
| --- | --- | --- |
| [#7](https://github.com/ReneeGA2020/RuneCLR/issues/7) | Allocation attribution experiments and a practical memory-limit design | Distinguish direct map, framework-on-behalf and retained host allocations; test repeated-session growth and allocation-heavy maps; explain shared-heap limits and recovery compatibility with #6 before claiming a hard cap |
| [#8](https://github.com/ReneeGA2020/RuneCLR/issues/8) | Host-owned ticks, events, timers and resource handles | Use #4 API versions and #5 capabilities; callbacks obey #6 terminal state; session retirement cancels work, releases subscriptions/resources and allows the next map; map delegates/metadata must not survive in host results |

## 6. Validate one game, then decide later native work — #9 / #10

[The pilot #9](https://github.com/ReneeGA2020/RuneCLR/issues/9) depends on the
supported package/API profile, lifecycle/termination and scheduling contracts,
with a declared practical memory policy. Integrate one server-authoritative game
with internal authors; collect representative frame/session latency, memory
trends, recovery behavior, author feedback and actual device results.

Use those measurements to decide whether UGC JIT/R2R is worth a separate
experiment. Controlled compiler provenance remains mandatory, and equivalent
capability/resource/termination tests must pass before native UGC joins the
restricted profile. Retain the interpreter path and same-IL JIT development
comparison; do not make a speculative public backend API a prerequisite.

[Public UGC readiness #10](https://github.com/ReneeGA2020/RuneCLR/issues/10)
follows the pilot: define distribution/approval, hostile-input review and
operational recovery gates against the supported trust model. It is not a
prerequisite for every controlled-map experiment, and the earlier milestones
do not claim that readiness on its behalf.
