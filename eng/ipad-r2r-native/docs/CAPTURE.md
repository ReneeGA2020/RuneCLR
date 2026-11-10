# On-device loader and native-entry capture contract

Placeholders: `<BUNDLE_ID>`, `<UDID>`, `<COREDEVICE_UUID>`, `<RUN>`,
`<OWNER_NONCE>`, `<DOCS>` = the app's Documents directory.

## Launch

    xcrun devicectl device process launch --console \
      --device <UDID> <BUNDLE_ID> --payload <RUN> --nonce <OWNER_NONCE>

Environment (one JSON dictionary via --environment-variables):

    RUNECLR_EXPECTED_VERSION = A | B
    RUNECLR_GOLDEN_RESULT    = 216
    RUNECLR_GOLDEN_PRIVATE   = 100 (A) | 200 (B)
    RUNECLR_GOLDEN_HELPER    = 307 (A) | 607 (B)

No RUNECLR_APPROVAL_* variables are used (there is no selector plan). The wrapper
normalizes --payload (token, absolute, trailing slash) before CoreCLR starts and
prints RUNECLR_PATH_OK/REJECT; the result JSON is always
`<DOCS>/results/<runId>.json`. Launch MUST pass --nonce; otherwise the wrapper
invents a nonce and the managed entry reports nonceMatches=false.

## Loader callback

When the runtime needs the R2R image for a downloaded assembly the host contract
callback prints one line per request:

    RUNECLR_NATIVE_CALLBACK owner=<owner composite> assembly=<assembly path> path=<abs owner> base=<dlopen base> rtr_header=<RTR_HEADER addr> image_size=<n> file_size=<n>

A callback line is host-side evidence only, not a program counter. On non-Windows
the runtime fails fast when the callback cannot supply an image; an OS dlopen
rejection is an honest terminal result and IL fallback must not be assumed.

## Required native-entry receipt

1. Launch stopped and read the PID:

    xcrun devicectl device process launch --start-stopped --console --device <UDID> \
      --environment-variables '{...}' <BUNDLE_ID> --payload <RUN> --nonce <OWNER_NONCE>

2. Attach and arm a PENDING breakpoint **before** resuming, using the symbol from the
   actually generated owner (LLDB matches the bare name; nm shows a leading underscore):

    xcrun lldb
    (lldb) device select <COREDEVICE_UUID>
    (lldb) device process attach -p <pid>
    (lldb) breakpoint set -n TrustedUpdate_Update_TrustedUpdate_Business__Execute
    (lldb) continue

3. Address conversion (owner load base from the callback line or `image list -o -f`):

    slide       = owner_load_base - text.vmaddr
    method_addr = slide + n_value
    valid range = [slide + text.vmaddr, slide + text.vmaddr + text.vmsize)

4. Record: PID, owner absolute path, owner sha256 (raw, and final-signed when
   signed), LC_UUID, load base, slide, text vmaddr/vmsize, PC, stop module and
   mapping permissions. Accept only when the PC is inside that executable range
   and the UUID/hash match the delivered owner.

Insufficient on their own: static Mach-O acceptance, the callback line, exit code
0, environment variables, or interpreter stub events for IL-only helpers.
