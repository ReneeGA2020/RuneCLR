#include <ctype.h>
#include <unistd.h>
#include <assert.h>
#include <limits.h>
// Licensed to the .NET Foundation under one or more agreements.
// The .NET Foundation licenses this file to you under the MIT license.

#import <Foundation/Foundation.h>
#include "coreclrhost.h"
#include "host_runtime_contract.h"
#include <TargetConditionals.h>
#import <os/log.h>
#include <sys/stat.h>
#include <sys/mman.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <dlfcn.h>

#import "util.h"
#include "path_norm.h"

#define APPLE_RUNTIME_IDENTIFIER "ios-arm64"

const char *
get_bundle_path (void)
{
    static char *bundle_path = NULL;
    if (bundle_path)
        return bundle_path;
    NSBundle* main_bundle = [NSBundle mainBundle];
    NSString* path = [main_bundle bundlePath];

#if TARGET_OS_MACCATALYST
    path = [path stringByAppendingString:@"/Contents/Resources"];
#endif

    bundle_path = strdup ([path UTF8String]);

    return bundle_path;
}

char *
compute_trusted_platform_assemblies ()
{
    const char *bundle_path = get_bundle_path ();

    NSMutableArray<NSString *> *files = [NSMutableArray array];

    NSFileManager *manager = [NSFileManager defaultManager];
    NSString *dir = [NSString stringWithUTF8String: bundle_path];
    NSDirectoryEnumerator *enumerator = [manager enumeratorAtURL:[NSURL fileURLWithPath: dir]
                                                 includingPropertiesForKeys:@[NSURLNameKey, NSURLIsDirectoryKey]
                                                 options:NSDirectoryEnumerationSkipsSubdirectoryDescendants
                                                 errorHandler:nil];
    for (NSURL *file in enumerator) {
        NSNumber *isDirectory = nil;
        if (![file getResourceValue:&isDirectory forKey:NSURLIsDirectoryKey error:nil] || [isDirectory boolValue])
            continue;

        NSString *name = nil;
        if (![file getResourceValue:&name forKey:NSURLNameKey error:nil])
            continue;
        if ([name length] < 4)
            continue;
       if ([name compare: @".dll" options: NSCaseInsensitiveSearch range: NSMakeRange ([name length] - 4, 4)] == NSOrderedSame) {
            [files addObject: [dir stringByAppendingPathComponent: name]];
        }
    }

    NSString *joined = [files componentsJoinedByString: @":"];
    return strdup([joined UTF8String]);
}

const void*
pinvoke_override (const char *libraryName, const char *entrypointName)
{
    if (!strcmp (libraryName, "__Internal"))
    {
        return dlsym (RTLD_DEFAULT, entrypointName);
    }

    return NULL;
}

#include <mach-o/dyld.h>
#include <mach-o/loader.h>
size_t get_image_size(const struct mach_header_64* header)
{
    const struct load_command* cmd = (const struct load_command*)((const char*)header + sizeof(struct mach_header_64));

    size_t image_size = 0;
    for (uint32_t j = 0; j < header->ncmds; ++j)
    {
        if (cmd->cmd == LC_SEGMENT_64)
        {
            const struct segment_command_64* seg = (const struct segment_command_64*)cmd;
            size_t end_addr = (size_t)(seg->vmaddr + seg->vmsize);
            if (end_addr > image_size)
                image_size = end_addr;
        }

        cmd = (const struct load_command*)((const char*)cmd + cmd->cmdsize);
    }

    return image_size;
}

bool get_native_code_data(const struct host_runtime_contract_native_code_context* context, struct host_runtime_contract_native_code_data* data)
{
    if (!context || !data || !context->assembly_path || !context->owner_composite_name)
        return false;

    char r2r_path[PATH_MAX];
    const char *last_slash = strrchr(context->assembly_path, '/');
    size_t dir_len = last_slash ? (size_t)(last_slash - context->assembly_path) : 0;
    if (dir_len >= sizeof(r2r_path) - 1)
        return false;

    strncpy(r2r_path, context->assembly_path, dir_len);
    int written = snprintf(r2r_path + dir_len, sizeof(r2r_path) - dir_len, "/%s", context->owner_composite_name);
    if (written <= 0 || (size_t)written >= sizeof(r2r_path) - dir_len)
        return false;

    void* handle = dlopen(r2r_path, RTLD_LAZY | RTLD_LOCAL);
    if (handle == NULL)
        return false;

    void* r2r_header = dlsym(handle, "RTR_HEADER");
    if (r2r_header == NULL)
    {
        dlclose(handle);
        return false;
    }

    Dl_info info;
    if (dladdr(r2r_header, &info) == 0)
    {
        dlclose(handle);
        return false;
    }

    void* base_address = info.dli_fbase;
    const struct mach_header_64* header = (const struct mach_header_64*)base_address;

    {
        struct stat owner_stat;
        memset (&owner_stat, 0, sizeof (owner_stat));
        stat (r2r_path, &owner_stat);
        printf ("RUNECLR_NATIVE_CALLBACK owner=%s assembly=%s path=%s base=%p rtr_header=%p image_size=%zu file_size=%lld\n",
                context->owner_composite_name, context->assembly_path, r2r_path,
                info.dli_fbase, r2r_header, get_image_size (header), (long long)owner_stat.st_size);
        fflush (stdout);
    }

    data->size = sizeof(struct host_runtime_contract_native_code_data);
    data->r2r_header_ptr = r2r_header;
    data->image_size = get_image_size(header);
    data->image_base = base_address;
    return true;
}

#include <time.h>

static const char *
argument_value (int argc, char **argv, const char *name)
{
    for (int index = 1; index + 1 < argc; index++)
    {
        if (strcmp (argv[index], name) == 0)
            return argv[index + 1];
    }
    return NULL;
}

static int
argument_flag (int argc, char **argv, const char *name)
{
    for (int index = 1; index < argc; index++)
    {
        if (strcmp (argv[index], name) == 0)
            return 1;
    }
    return 0;
}

void
mono_ios_runtime_init (void)
{
#if INVARIANT_GLOBALIZATION
    setenv ("DOTNET_SYSTEM_GLOBALIZATION_INVARIANT", "1", TRUE);
#endif

#ifdef DIAGNOSTIC_PORTS
    setenv ("DOTNET_DiagnosticPorts", DIAGNOSTIC_PORTS, true);
#endif

    NSArray<NSString *> *arguments = [[NSProcessInfo processInfo] arguments];
    int argc = (int)[arguments count];
    char **argv = (char **)malloc (sizeof (char *) * (size_t)(argc > 0 ? argc : 1));
    for (int index = 0; index < argc; index++)
        argv[index] = strdup ([[arguments objectAtIndex:index] UTF8String]);
    if (argc == 0)
    {
        argv[0] = strdup ("RuneClrIpadProbe");
        argc = 1;
    }

    const char *payload = argument_value (argc, argv, "--payload");
    const char *nonce = argument_value (argc, argv, "--nonce");
    int probe = argument_flag (argc, argv, "--probe");
    int delivery = argument_flag (argc, argv, "--delivery");
    rn_start_mode start_mode = rn_start_mode_select (probe, delivery);

    if (start_mode == RN_MODE_CONFLICT)
    {
        printf ("RUNE_IPAD_REJECT pid=%d reason=conflicting-mode flags=probe,delivery\n", getpid ());
        fflush (stdout);
        exit (122);
    }

    char generated_nonce[33];
    if (!nonce || strlen (nonce) != 32)
    {
        struct timespec now;
        clock_gettime (CLOCK_REALTIME, &now);
        snprintf (generated_nonce, sizeof (generated_nonce), "%08lx%08lx%08lx%08lx",
                  (unsigned long)getpid (), (unsigned long)now.tv_sec,
                  (unsigned long)now.tv_nsec, (unsigned long)((now.tv_nsec >> 8) ^ (now.tv_sec >> 3)));
        nonce = generated_nonce;
    }

    const char *documents = [NSSearchPathForDirectoriesInDomains (NSDocumentDirectory, NSUserDomainMask, YES)[0] UTF8String];

    setenv ("RUNECLR_PROBE_NONCE", nonce, 1);
    setenv ("RUNECLR_PROBE_PAYLOAD", payload ? payload : "", 1);
    setenv ("RUNECLR_PROBE_MODE", rn_start_mode_name (start_mode), 1);
    setenv ("RUNECLR_DOCUMENTS", documents, 1);
    char documents_physical[PATH_MAX] = {0};
    if (realpath (documents, documents_physical) != NULL)
        setenv ("RUNECLR_DOCUMENTS_PHYSICAL", documents_physical, 1);

    unsetenv ("COMPlus_InterpMode"); setenv ("DOTNET_InterpMode", "1", 1);
    unsetenv ("COMPlus_RuneCLRInterpretCollectible"); setenv ("DOTNET_RuneCLRInterpretCollectible", "1", 1);
    unsetenv ("COMPlus_ReadyToRun"); setenv ("DOTNET_ReadyToRun", "1", 1);
    unsetenv ("COMPlus_TieredCompilation"); setenv ("DOTNET_TieredCompilation", "0", 1);
    unsetenv ("COMPlus_SYSTEM_GLOBALIZATION_INVARIANT"); setenv ("DOTNET_SYSTEM_GLOBALIZATION_INVARIANT", "1", 1);
    unsetenv ("COMPlus_InterpList"); setenv ("DOTNET_InterpList", "0", 1);
    unsetenv ("DOTNET_InterpDump"); unsetenv ("COMPlus_InterpDump");

    printf ("RUNE_IPAD_NATIVE pid=%d nonce=%s mode=%s payload=%s InterpMode=1 InterpretCollectible=1 ReadyToRun=1 Tiered=0\n",
            getpid (), nonce, rn_start_mode_name (start_mode), payload ? payload : "");
    fflush (stdout);

    const char* bundle = get_bundle_path ();
    chdir (bundle);

    struct host_runtime_contract host_contract = {
        .size = sizeof (struct host_runtime_contract),
        .pinvoke_override = &pinvoke_override,
        .get_native_code_data = &get_native_code_data
    };

    char contract_str[19];
    snprintf (contract_str, 19, "0x%zx", (size_t)(&host_contract));

#define PROPERTY_COUNT 6

    const char *appctx_keys[PROPERTY_COUNT];
    appctx_keys[0] = "RUNTIME_IDENTIFIER";
    appctx_keys[1] = "APP_CONTEXT_BASE_DIRECTORY";
    appctx_keys[2] = "TRUSTED_PLATFORM_ASSEMBLIES";
    appctx_keys[3] = "HOST_RUNTIME_CONTRACT";
    appctx_keys[4] = "NATIVE_DLL_SEARCH_DIRECTORIES";
    appctx_keys[5] = "System.Globalization.Invariant";

    const char *appctx_values[PROPERTY_COUNT];
    appctx_values[0] = APPLE_RUNTIME_IDENTIFIER;
    appctx_values[1] = bundle;
    appctx_values[2] = compute_trusted_platform_assemblies ();
    appctx_values[3] = contract_str;
    appctx_values[4] = bundle;
    appctx_values[5] = "true";

    const char *executable = "RunEntry.dll";
    const char *executablePath = [[[[NSBundle mainBundle] executableURL] path] UTF8String];
    unsigned int coreclr_domainId = 0;
    void *coreclr_handle = NULL;

    char payload_path[PATH_MAX] = {0};
    char result_path[PATH_MAX] = {0};
    char run_id[RN_MAX_RUN_ID + 1] = {0};

    if (delivery)
    {
        const char *run_name = (payload && *payload) ? payload : "delivery";
        rn_status result_status = rn_result_path (documents, run_name, result_path, sizeof (result_path));
        rn_status run_status = rn_run_id (run_name, run_id);
        if (result_status == RN_OK && run_status == RN_OK)
            printf ("RUNECLR_DELIVERY_PATH_OK pid=%d runId=%s result=%s\n", getpid (), run_id, result_path);
        else
            printf ("RUNECLR_DELIVERY_PATH_REJECT pid=%d raw=%s\n", getpid (), run_name);
        fflush (stdout);
        if (result_status != RN_OK || run_status != RN_OK)
            exit (123);
        setenv ("RUNECLR_RESULT_PATH", result_path, 1);
        setenv ("RUNECLR_RUN_ID", run_id, 1);
        setenv ("RUNECLR_HOST_MODE", "delivery", 1);
    }
    else if (!probe)
    {
        rn_status payload_status = rn_payload_dir (documents, payload ? payload : "", payload_path, sizeof (payload_path));
        rn_status result_status = rn_result_path (documents, payload ? payload : "", result_path, sizeof (result_path));
        if (payload_status == RN_OK && rn_run_id (payload ? payload : "", run_id) == RN_OK)
            printf ("RUNECLR_PATH_OK pid=%d runId=%s payload=%s result=%s\n", getpid (), run_id, payload_path, result_path);
        else
            printf ("RUNECLR_PATH_REJECT pid=%d status=%s raw=%s\n", getpid (), rn_status_name (payload_status), payload ? payload : "");
        fflush (stdout);
        if (payload_status != RN_OK || result_status != RN_OK)
            exit (123);
        setenv ("RUNECLR_RESULT_PATH", result_path, 1);
        setenv ("RUNECLR_UPDATE_DIR", payload_path, 1);
        setenv ("RUNECLR_RUN_ID", run_id, 1);
    }

    int res = coreclr_initialize (
        executablePath, executable,
        sizeof (appctx_keys) / sizeof (appctx_keys [0]), appctx_keys, appctx_values,
        &coreclr_handle, &coreclr_domainId);
    printf ("RUNE_IPAD_INITIALIZE pid=%d nonce=%s hr=%d documents=%s\n", getpid (), nonce, res, documents);
    fflush (stdout);
    if (res != 0) exit (126);

    if (probe)
    {
        const char *tpa = appctx_values[2];
        int count = 1;
        for (const char *cursor = tpa; *cursor; cursor++)
            if (*cursor == ':') count++;
        printf ("RUNE_IPAD_PROBE pid=%d nonce=%s hr=%d tpaCount=%d bundle=%s documents=%s\n",
                getpid (), nonce, res, count, bundle, documents);
        printf ("RUNE_IPAD_EXIT pid=%d nonce=%s managedExit=0 actualExit=0\n", getpid (), nonce);
        fflush (stdout);
        exit (0);
    }



    char *managed_argv[5];
    managed_argv[0] = (char *)"RunEntry";
    managed_argv[1] = (char *)"--payload";
    managed_argv[2] = payload_path;
    managed_argv[3] = (char *)"--result";
    managed_argv[4] = result_path;

    char assembly_path[PATH_MAX];
    snprintf (assembly_path, sizeof (assembly_path), "%s/%s", bundle, executable);

    unsigned int exit_code = 255;
    res = coreclr_execute_assembly (coreclr_handle, coreclr_domainId, 5, managed_argv, assembly_path, &exit_code);
    printf ("RUNE_IPAD_INVOKE pid=%d nonce=%s hr=%d managedExit=%u\n", getpid (), nonce, res, exit_code);
    fflush (stdout);
    os_log_info (OS_LOG_DEFAULT, "RUNE_IPAD_EXIT_CODE: %u", exit_code);

    printf ("RUNE_IPAD_EXIT pid=%d nonce=%s managedExit=%u actualExit=%u\n",
            getpid (), nonce, exit_code, res == 0 ? exit_code : 254);
    fflush (stdout);
    exit (res == 0 ? (int)exit_code : 254);
}
