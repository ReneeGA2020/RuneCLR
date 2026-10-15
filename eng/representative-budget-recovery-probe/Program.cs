using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;
using RuneCLR.Runtime;

if (args.Length != 2) throw new ArgumentException("Expected frozen author DLL and nonce.");
string author = Path.GetFullPath(args[0]);
string nonce = args[1];
if (nonce.Length != 32 || !nonce.All(Uri.IsHexDigit)) throw new ArgumentException("Invalid nonce.");
string authorHash = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(author)));
long[] limits = [1, 32, 64, 128, 2048, 8192, 100000];
var rows = new List<RecoveryRow>();
foreach (string workload in new[] { "entities", "host-api" })
{
    foreach (long limit in limits)
    {
        var failed = RunFrame(author, workload, limit);
        ValidateFailure(failed.Report, limit);
        Collect(failed.Unload);
        rows.Add(new(workload, limit, "terminated", failed.Report, failed.Unload.IsCollected));

        var recovery = RunFrame(author, "host-api", 1_000_000_000_000);
        ValidateRecovery(recovery.Report);
        Collect(recovery.Unload);
        rows.Add(new(workload, limit, "recovery", recovery.Report, recovery.Unload.IsCollected));
    }
}
if (authorHash != Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(author))))
    throw new InvalidOperationException("Frozen author changed.");
Console.WriteLine(JsonSerializer.Serialize(new
{
    passed = true, processId = Environment.ProcessId, nonce, authorHash,
    runtime = RuntimeInformation.FrameworkDescription, architecture = RuntimeInformation.ProcessArchitecture.ToString(),
    limits, rows, collected = rows.Count(row => row.Collected),
    scope = "Native low-budget workload termination and same-process fresh-session recovery; no timing or new method-entry proof."
}));

[MethodImpl(MethodImplOptions.NoInlining)]
static MapRunResult RunFrame(string author, string workload, long limit)
{
    var package = new MapPackage("representative-budget-recovery", author,
        "RuneCLR.BudgetWorkloadScripts." + (workload == "entities" ? "EntityMap" : "HostApiMap"));
    return new MapRunner().Run(package, new MapRunOptions
    {
        ExecutionPolicy = MapExecutionPolicy.RequireInterpreter, PrototypeInstructionBudget = limit,
        PrototypeCleanupInstructionBudget = 4096, TickCount = 3,
        OperationBudgetPerCallback = 1_000_000, MaxEntities = 2, MaxLogMessages = 512
    });
}

static void ValidateFailure(MapRunReport report, long limit)
{
    Check(report.ExecutionPolicy == MapExecutionPolicy.RequireInterpreter && report.ExecutionPolicyVersion == 1,
        "Required policy acknowledgement differs.");
    Check(report.Outcome == MapRunOutcome.Failed && report.CompletedTicks == 0 &&
        report.Error == "The native prototype instruction budget terminated author execution.",
        "Low-budget run returned or did not report native termination.");
    Check(report.CreatedEntities == report.ReleasedEntities && report.RemainingEntities == 0,
        "Terminated session resources remain.");
    Check(report.Logs.All(message => message == "benchmark-tick"),
        "OnStop checksum marker appeared after native termination.");
    Check(report.PrototypeBudget == new PrototypeBudgetSnapshot(0, limit, true, true, 1, 1, 4096, 0),
        "Exact native terminal ledger differs.");
}

static void ValidateRecovery(MapRunReport report)
{
    Check(report.ExecutionPolicy == MapExecutionPolicy.RequireInterpreter && report.ExecutionPolicyVersion == 1,
        "Recovery policy acknowledgement differs.");
    Check(report.Outcome == MapRunOutcome.Completed && report.CompletedTicks == 3 && report.Error is null,
        "Same-process recovery failed.");
    Check(report.CreatedEntities == 24576 && report.ReleasedEntities == 24576 && report.RemainingEntities == 0,
        "Recovered API session resource counts differ.");
    Check(report.Logs.Count == 385 && report.Logs.Take(384).All(message => message == "benchmark-tick") &&
        report.Logs[^1] == "budget-workloads:host-api:starts=1;sum=302002176",
        "Recovered checksum/static state/logs differ.");
    Check(report.PrototypeBudget == new PrototypeBudgetSnapshot(1_000_000_000_000 - 689851,
        689851, false, false, 0, 0, 4096, 0), "Recovered ledger differs.");
}

static void Collect(UnloadTicket ticket)
{
    for (int i = 0; i < 12 && !ticket.IsCollected; i++)
    {
        GC.Collect();
        GC.WaitForPendingFinalizers();
        GC.Collect();
    }
    Check(ticket.IsCollected, "Context retained after execution stack returned.");
}

static void Check(bool value, string message)
{
    if (!value) throw new InvalidOperationException(message);
}

sealed record RecoveryRow(string Workload, long Limit, string Role, MapRunReport Report, bool Collected);
