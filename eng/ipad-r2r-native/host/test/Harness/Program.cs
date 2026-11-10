using System; using System.IO; using System.Runtime.Loader;
namespace TrustedUpdate { public static class Driver {
  public static int Run() {
    var mode = Environment.GetEnvironmentVariable("TEST_MODE") ?? "ok";
    var privateValue = Environment.GetEnvironmentVariable("TEST_PRIVATE") ?? "100";
    var helperValue = Environment.GetEnvironmentVariable("TEST_HELPER") ?? "307";
    var version = Environment.GetEnvironmentVariable("TEST_STAMP_VERSION") ?? "A";
    if (Environment.GetEnvironmentVariable("TEST_LOAD_STAMP") == "1") {
      var path = Environment.GetEnvironmentVariable("TEST_STAMP_PATH") ?? "";
      AssemblyLoadContext.Default.LoadFromAssemblyPath(path);
    }
    Console.WriteLine("TRUSTED_UPDATE_BEGIN expected=" + version + " directory=/tmp");
    Console.WriteLine("UPDATE_BUSINESS input=5");
    Console.WriteLine("UPDATE_RUN result=215");
    Console.WriteLine("PRIVATE_VALUE=" + privateValue);
    Console.WriteLine("IL_HELPER=" + helperValue);
    Console.WriteLine("HOST_REFLECTION_PRIVATE=" + privateValue + " HOST_REFLECTION_HELPER=" + helperValue);
    if (mode == "fail") { Console.WriteLine("TRUSTED_UPDATE_FAILURE version=" + version + " failure=ActivationFailed"); return 17; }
    if (mode == "no-success") { return 0; }
    Console.WriteLine("TRUSTED_UPDATE_SUCCESS version=" + version + " result=216 MANAGED_BYTES=4096");
    if (mode == "ambiguous") { Console.WriteLine("TRUSTED_UPDATE_SUCCESS version=" + version + " result=216 MANAGED_BYTES=4096"); }
    return 0; } } }
