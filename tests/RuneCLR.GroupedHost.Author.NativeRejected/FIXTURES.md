# RuneCLR.GroupedHost.Author.NativeRejected fixture

AssemblyName: RuneCLR.GroupedHost.Author.NativeRejected (references Contracts only).

Negative author-admission fixture: the author assembly contains its OWN direct kernel32!GetCurrentThreadId
P/Invoke. The grouped host must reject this assembly during admission, before any author code runs, so
Run() is expected never to execute. If admission ever allowed it, Run() would return the native thread id.

Public entry: public static int AuthorEntry.Run(IGroupedHostContract host, int value)

No RuneCLR.Runtime reference, no processes, no timing, no finalizers. It is not executed by this slice.
