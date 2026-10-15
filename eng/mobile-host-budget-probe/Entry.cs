using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace MobileHostBudgetProbe;

// Trusted fixed native-entry adapter. The linked original host retains all
// actual MapRunner assertions; this class never loads author reflection metadata.
public static class Entry
{
    private static readonly string[] Cases = ["Normal", "EndlessTick", "StartLoop", "CatchResume",
        "BroadCatchResume", "SignalFilter", "FilterExhaustion", "ConstructorLoop", "StaticConstructorLoop",
        "FiniteCleanup", "InfiniteCleanup", "StopLoop", "MaliciousMessage", "ExplicitCanceled", "Recovery"];
    private static readonly string[] PumpedCases = [.. Cases, "TickWork"];

    // Native executable bridge calls this exact public static method, not an
    // Assembly.EntryPoint. All paths and mode are selected by the trusted host.
    public static int Run(string[] args)
    {
        if (args.Length is not (4 or 5) || args.Length == 5 && args[4] != "--pumped")
            throw new ArgumentException("Expected plugin directory, fresh evidence directory, nonce, all or fixed case, optional --pumped.");
        bool pumped = args.Length == 5;
        string plugin = Path.GetFullPath(args[0]), evidence = Path.GetFullPath(args[1]), nonce = args[2], selected = args[3];
        if (nonce.Length != 32 || !nonce.All(Uri.IsHexDigit)) throw new ArgumentException("Owned nonce must contain32 hex digits.");
        string[] available = pumped ? PumpedCases : Cases;
        string[] cases = selected == "all" ? available : available.Contains(selected, StringComparer.Ordinal) ? [selected] :
            throw new ArgumentException("Unknown fixed host-budget case.");
        if (Directory.Exists(evidence)) throw new IOException("Evidence directory must be fresh; preserve failed runs.");
        Directory.CreateDirectory(evidence);
        TextWriter original = Console.Out;
        Console.WriteLine($"MOBILE_HOST_BUDGET_START nonce={nonce} scenario={selected} pid={Environment.ProcessId} cases={cases.Length}");
        var rows = new List<object>();
        int contexts = 0;
        foreach (string name in cases)
        {
            string childNonce = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(nonce + ":" + name)))[..32].ToLowerInvariant();
            string lane = Path.Combine(evidence, name);
            int result;
            try
            {
                string[] hostArgs = [plugin, lane, name, childNonce, "budget"];
                result = HostBudgetProbe.Host.Program.Main(pumped ? [.. hostArgs, "--pumped"] : hostArgs);
            }
            finally { Console.SetOut(original); }
            if (result != 0) throw new InvalidOperationException("Fixed host-budget scenario failed: " + name);
            string path = Path.Combine(lane, "result.json");
            using JsonDocument receipt = JsonDocument.Parse(File.ReadAllBytes(path));
            JsonElement root = receipt.RootElement;
            int count = name == "Normal" ? 20 : name == "Recovery" ? 40 : 1;
            if (!root.GetProperty("passed").GetBoolean() || root.GetProperty("nonce").GetString() != childNonce ||
                root.GetProperty("scenario").GetString() != name || root.GetProperty("mode").GetString() != "budget" ||
                root.GetProperty("rows").GetArrayLength() != count)
                throw new InvalidDataException("Owned actual MapRunner result differs: " + name);
            if (pumped)
            {
                foreach (JsonElement row in root.GetProperty("rows").EnumerateArray())
                {
                    if (!row.GetProperty("pumped").GetBoolean() || !row.GetProperty("collected").GetBoolean() ||
                        !row.GetProperty("retainedStoppedSessionCollected").GetBoolean() ||
                        row.GetProperty("successfulHostReturns").GetInt32() !=
                        row.GetProperty("report").GetProperty("CompletedTicks").GetInt32())
                        throw new InvalidDataException("Owned pumped session return or collection differs: " + name);
                }
            }
            contexts += count;
            rows.Add(new { scenario = name, nonce = childNonce, contexts = count, receipt = name + "/result.json",
                receiptSha256 = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant() });
            Console.WriteLine($"MOBILE_HOST_BUDGET_CASE nonce={nonce} caseNonce={childNonce} scenario={name} contexts={count} passed=true");
        }
        File.WriteAllText(Path.Combine(evidence, "result.json"), JsonSerializer.Serialize(new {
            passed = true, nonce, scenario = selected, processId = Environment.ProcessId, cases = rows, contexts,
            prototypeOnly = true, nativeEntryProof = false, authorFinalizersProductionSupported = false
        }, new JsonSerializerOptions { WriteIndented = true }));
        Console.WriteLine($"MOBILE_HOST_BUDGET_COMPLETE nonce={nonce} scenario={selected} pid={Environment.ProcessId} cases={cases.Length} contexts={contexts} passed=true");
        return 0;
    }
}
