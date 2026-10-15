/* Unmodified Lua VM, with a Windows wall-clock timer matching .NET/Node semantics. */
#include <windows.h>
#include <stdio.h>
#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"
static LARGE_INTEGER frequency;
static int clock_now(lua_State *L) {
    LARGE_INTEGER counter; QueryPerformanceCounter(&counter);
    lua_pushnumber(L, (double)counter.QuadPart / (double)frequency.QuadPart); return 1;
}
int main(int argc, char **argv) {
    if (argc < 2) { puts(LUA_RELEASE); return 0; }
    QueryPerformanceFrequency(&frequency);
    lua_State *L = luaL_newstate(); if (!L) return 2; luaL_openlibs(L);
    lua_pushcfunction(L, clock_now); lua_setglobal(L, "bench_clock");
    lua_createtable(L, argc - 2, 1);
    for (int i = 1; i < argc; i++) { lua_pushstring(L, argv[i]); lua_rawseti(L, -2, i - 1); }
    lua_setglobal(L, "arg");
    int result = luaL_dofile(L, argv[1]);
    if (result != LUA_OK) fprintf(stderr, "%s\n", lua_tostring(L, -1));
    lua_close(L); return result == LUA_OK ? 0 : 1;
}
