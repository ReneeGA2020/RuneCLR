var cases = CompilerCases.Cases().Concat(IntakeCases.Cases()).Concat(ManifestCases.Cases())
    .Concat(PipelineCases.Cases()).Concat(CapabilityCases.Cases()).ToArray();
var failed = 0;
foreach (var (name, run) in cases)
{
    try { run(); Console.WriteLine($"PASS {name}"); }
    catch (Exception exception) { failed++; Console.WriteLine($"FAIL {name}: {exception}"); }
}
Console.WriteLine($"{cases.Length - failed}/{cases.Length} packaging tests passed");
return failed == 0 ? 0 : 1;
