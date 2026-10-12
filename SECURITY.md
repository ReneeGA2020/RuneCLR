# Security model

RuneCLR currently runs trusted code only. Its prototype does not isolate hostile
maps from the host process, user files, network, or other sessions. It must not be
used to execute arbitrary public UGC with sensitive process privileges.

Current quotas apply to host API calls and retained host resources. They do not
limit arbitrary managed allocations or execution. Collectible assembly contexts
provide loading/unloading, not permissions. The native loader override blocks
one load path and is not a comprehensive interop restriction.

Dead loops, blocked calls, finalizers, threads, process-level failures, and leaked
references are outside the prototype's recovery guarantees. Framework and host
state can outlive a map. Manifest path checks are packaging validation, not a
filesystem isolation mechanism.

Development starts with controlled internal maps. Expanding the trust model
requires runtime enforcement, a constrained framework surface, dependency
validation, abuse tests, and a threat-model review.

For accidental exposures or security-sensitive findings, use GitHub private
vulnerability reporting if available. Otherwise contact the maintainer before
posting sensitive details publicly. Ordinary prototype bugs can use issues.
