/* Stock Lua VM; a native, per-state, non-atomic count-hook budget. */
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"

typedef struct { uint64_t remaining, events; int interval; } Budget;
static const uint64_t high_budget = 1000000000000ULL;
static Budget *budget(lua_State *L) { return *(Budget **)lua_getextraspace(L); }
static void count_hook(lua_State *L, lua_Debug *ar) {
    Budget *b = budget(L);
    (void)ar;
    b->events++;
    if (b->remaining < (uint64_t)b->interval) luaL_error(L, "native budget exhausted");
    b->remaining -= b->interval;
}
static void reset(lua_State *L, Budget *b, uint64_t allowance) {
    b->remaining = allowance; b->events = 0;
    lua_sethook(L, b->interval ? count_hook : NULL, b->interval ? LUA_MASKCOUNT : 0, b->interval);
}
static int invoke(lua_State *L, int ref, lua_Integer *checksum) {
    lua_rawgeti(L, LUA_REGISTRYINDEX, ref);
    int status = lua_pcall(L, 0, 1, 0);
    if (status == LUA_OK) {
        if (!lua_isinteger(L, -1)) return -1;
        *checksum = lua_tointeger(L, -1);
    }
    return status;
}
int main(int argc, char **argv) {
    if (argc != 5) return 2;
    int interval = atoi(argv[2]), samples = atoi(argv[3]);
    if ((interval != 0 && interval != 1 && interval != 100 && interval != 1000) || samples != 9) return 2;
    for (const char *p = argv[4]; *p; p++) if (!(('a' <= *p && *p <= 'f') || ('0' <= *p && *p <= '9'))) return 2;
    if (strlen(argv[4]) != 32 || !SetProcessAffinityMask(GetCurrentProcess(), 4)) return 3;
    DWORD_PTR process_mask, system_mask;
    if (!GetProcessAffinityMask(GetCurrentProcess(), &process_mask, &system_mask) || process_mask != 4) return 3;
    LARGE_INTEGER frequency; QueryPerformanceFrequency(&frequency);
    lua_State *L = luaL_newstate(); if (!L) return 4; luaL_openlibs(L);
    Budget b = {0, 0, interval}; *(Budget **)lua_getextraspace(L) = &b;
    if (luaL_dofile(L, argv[1]) != LUA_OK || !lua_isfunction(L, -1)) return 5;
    int ref = luaL_ref(L, LUA_REGISTRYINDEX);
    printf("{\"kind\":\"process\",\"lua\":\"%s\",\"pid\":%lu,\"nonce\":\"%s\",\"interval\":%d,\"affinity\":%llu,\"qpcFrequency\":%lld,\"highBudget\":%llu}\n",
        LUA_RELEASE, GetCurrentProcessId(), argv[4], interval, (unsigned long long)process_mask, frequency.QuadPart, (unsigned long long)high_budget);
    for (int i = 0; i < 3 + samples; i++) {
        reset(L, &b, high_budget);
        LARGE_INTEGER start, stop; lua_Integer checksum = 0;
        QueryPerformanceCounter(&start);
        int status = invoke(L, ref, &checksum);
        QueryPerformanceCounter(&stop);
        lua_sethook(L, NULL, 0, 0);
        if (status != LUA_OK || checksum != 12749776) return 6;
        lua_pop(L, 1);
        printf("{\"kind\":\"%s\",\"index\":%d,\"checksum\":%lld,\"elapsedTicks\":%lld,\"elapsedMs\":%.9f,\"events\":",
            i < 3 ? "warmup" : "sample", i < 3 ? i : i - 3, (long long)checksum, stop.QuadPart - start.QuadPart, (double)(stop.QuadPart - start.QuadPart) * 1000.0 / (double)frequency.QuadPart);
        if (interval) printf("%llu,\"estimatedCountedInstructions\":%llu", (unsigned long long)b.events, (unsigned long long)(b.events * interval));
        else printf("null,\"estimatedCountedInstructions\":null");
        printf("}\n");
    }
    if (interval) {
        for (int control = 0; control < 2; control++) {
            uint64_t allowance = control ? (uint64_t)interval * 2 : 0;
            reset(L, &b, allowance);
            lua_Integer checksum = 0; int status = invoke(L, ref, &checksum);
            lua_sethook(L, NULL, 0, 0);
            int rejected = status == LUA_ERRRUN && strstr(lua_tostring(L, -1), "native budget exhausted") != NULL;
            uint64_t events = b.events, remaining = b.remaining;
            lua_pop(L, 1);
            if (invoke(L, ref, &checksum) != LUA_OK || checksum != 12749776 || !rejected || remaining || events != (uint64_t)(control ? 3 : 1)) return 7;
            lua_pop(L, 1);
            printf("{\"kind\":\"control\",\"name\":\"%s\",\"allowance\":%llu,\"events\":%llu,\"remaining\":%llu,\"rejected\":true,\"recoveredChecksum\":%lld}\n",
                control ? "small-quota" : "zero-quota", (unsigned long long)allowance, (unsigned long long)events, (unsigned long long)remaining, (long long)checksum);
        }
    }
    luaL_unref(L, LUA_REGISTRYINDEX, ref); lua_close(L); return 0;
}
