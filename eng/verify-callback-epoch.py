#!/usr/bin/env python3
"""Paired clock-vs-epoch callback-deadline campaign for the RuneCLR epoch experiment.

Stock lanes (probe, selfcheck, bounded ticker lanes, mechanical lifecycle) run
anywhere. Private lanes need the epoch runtime build and a matching private layout;
they are opt-in with --private so a stock machine never reports timing claims.

Pre-declared rules:
- Matched-latency eligibility: a lane is comparable only when its actual p50 tick
  spacing is within 5% of its declared period. A safely spaced but slower lane is
  characterised and excluded from the matched-latency verdict; it is not a failure.
- True failure: spacing violations, publish failures, non-zero exit, or a missing
  expected termination.
- Late ticks alone never fail a lane (scheduler delays are normal).
- Equivalence: +/-2% on the paired epoch/clock median ratio with a 95% bootstrap CI.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys

NL = chr(10)
EQUIVALENCE = 0.02
DILATION_LIMIT = 0.05
INTERVALS = (100, 1000)
CUTOFFS_MS = (100, 1000, 5000)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + NL, encoding="utf-8")


def median(values):
    ordered = sorted(values)
    return ordered[len(ordered) // 2] if ordered else None


def mean(values):
    return sum(values) / len(values) if values else None


def paired_summary(pairs, seed=20261110):
    ratios = [candidate / baseline for baseline, candidate in pairs if baseline and candidate]
    if not ratios:
        return {"count": 0, "verdict": "no-data"}
    rng = random.Random(seed)
    boots = []
    for _ in range(2000):
        sample = [ratios[rng.randrange(len(ratios))] for _ in ratios]
        boots.append(median(sample))
    boots.sort()
    low, high = boots[50], boots[1949]
    positive = sum(1 for ratio in ratios if ratio > 1.0)
    if low >= 1 - EQUIVALENCE and high <= 1 + EQUIVALENCE:
        verdict = "equivalent-within-2pct"
    elif low > 1 + EQUIVALENCE:
        verdict = "candidate-slower"
    elif high < 1 - EQUIVALENCE:
        verdict = "candidate-faster"
    else:
        verdict = "inconclusive"
    return {"count": len(ratios), "medianRatio": median(ratios), "ci95": [low, high],
            "candidateSlowerSigns": positive, "candidateFasterSigns": len(ratios) - positive,
            "verdict": verdict}


def watchdog_ms(requested_ms):
    return int(max(10_000, min(30_000, requested_ms + 5_000)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--quick", action="store_true", help="bounded stock checks only")
    parser.add_argument("--private", action="store_true")
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--layout", type=Path)
    parser.add_argument("--framework-version", default="12.0.0")
    parser.add_argument("--replicates", type=int, default=15)
    parser.add_argument("--ticks", type=int, default=20)
    parser.add_argument("--deadline-ms", type=int, default=2_000)
    parser.add_argument("--ticker-us", type=int, default=1_000)
    parser.add_argument("--epoch-period-us", type=int, default=0)
    parser.add_argument("--ticker-wait", default="hr")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--runtime-source-manifest", type=Path)
    parser.add_argument("--runtime-base", default="3126bbc9a8851a09ac6435b18a12882bad48f3ee")
    parser.add_argument("--build-rid", default="windows.x64.Release")
    parser.add_argument("--stats-selftest", action="store_true")
    args = parser.parse_args()

    if args.stats_selftest:
        return stats_selftest()
    if args.ticker_us < 1:
        raise ValueError("The ticker period must be positive.")
    period = args.epoch_period_us or args.ticker_us
    if args.ticker_us < period:
        raise ValueError("--ticker-us must be at least --epoch-period-us.")

    root = args.host_root.resolve()
    output = args.output.resolve()
    if output.exists():
        raise ValueError("Output must be a new directory.")
    output.mkdir(parents=True)

    bench = root / "tests/RuneCLR.EpochBench/bin/Release/net11.0/RuneCLR.EpochBench.dll"
    logs = []
    tick_ticks = 150 if args.quick else 1000

    def run(name, command, timeout=None, extra_env=None):
        stdout = output / (name + ".stdout.log")
        stderr = output / (name + ".stderr.log")
        env = environment()
        if extra_env:
            env.update(extra_env)
        with stdout.open("wb") as out, stderr.open("wb") as err:
            timed_out = False
            try:
                process = subprocess.run([str(part) for part in command], cwd=root, env=env,
                                         stdout=out, stderr=err, timeout=timeout or args.timeout)
                code = process.returncode
            except subprocess.TimeoutExpired:
                code = None
                timed_out = True
        text = stdout.read_text(encoding="utf-8", errors="replace")
        parsed = None
        start = text.find("{")
        if start >= 0:
            try: parsed = json.loads(text[start:])
            except json.JSONDecodeError: parsed = None
        entry = {"name": name, "exit": code, "timedOut": timed_out, "log": str(stdout), "parsed": parsed}
        logs.append(entry)
        print(("PASS" if code == 0 else "FAIL"), name, "exit=" + str(code), "log=" + stdout.name)
        return entry

    def run_negative(name, command, marker):
        stdout = output / (name + ".stdout.log")
        stderr = output / (name + ".stderr.log")
        with stdout.open("wb") as out, stderr.open("wb") as err:
            process = subprocess.run([str(part) for part in command], cwd=root, env=environment(),
                                     stdout=out, stderr=err, timeout=args.timeout)
        combined = stdout.read_text(encoding="utf-8", errors="replace") + stderr.read_text(encoding="utf-8", errors="replace")
        passed = process.returncode != 0 and marker in combined
        entry = {"name": name, "exit": process.returncode, "log": str(stdout), "negative": True, "rejected": passed}
        logs.append(entry)
        print(("PASS" if passed else "FAIL"), name, "rejected=" + str(passed), "log=" + stdout.name)
        return passed

    if args.build:
        run("build", ["dotnet", "build", "RuneCLR.slnx", "-c", "Release"], timeout=900)

    stock = run("probe", ["dotnet", bench, "probe"])
    capabilities = stock["parsed"] or {}
    run("selfcheck", ["dotnet", bench, "selfcheck"])
    for wait in ("sleep", "timer", "hr", "hybrid", "spin"):
        run("ticker-1ms-" + wait, ["dotnet", bench, "ticker", "--ticker-us", "1000",
                                   "--ticks", str(tick_ticks), "--ticker-wait", wait])
    for wait in ("hr", "hybrid", "spin"):
        run("ticker-200us-" + wait, ["dotnet", bench, "ticker", "--ticker-us", "200",
                                     "--ticks", str(tick_ticks), "--ticker-wait", wait])
    if not args.quick:
        run("ticker-10ms-hr", ["dotnet", bench, "ticker", "--ticker-us", "10000",
                               "--ticks", "2000", "--ticker-wait", "hr"])
    run_negative("m3-fast-ticker-rejected",
                 ["dotnet", bench, "ticker", "--ticker-us", "100", "--epoch-period-us", "1000",
                  "--ticks", "50"], "at least the declared epoch period")
    run("mechanical", ["dotnet", bench, "mechanical", "--policy", "default",
                       "--entry", "EpochBench.Author.ArithmeticSmall", "--ticks", "5", "--samples", "3"])
    run("concurrent", ["dotnet", bench, "concurrent", "--policy", "default", "--sessions", "4",
                       "--entry", "EpochBench.Author.ArithmeticSmall", "--ticks", "5",
                       "--ticker-us", "1000", "--ticker-wait", "timer"])

    result = {"stock": {"capabilities": capabilities}, "quick": args.quick, "logs": logs,
              "dilationLimit": DILATION_LIMIT, "equivalenceMargin": EQUIVALENCE,
              "effectiveTickerUs": args.ticker_us, "declaredEpochPeriodUs": period}
    if args.private:
        result["private"] = run_private(args, root, bench, run, period, output)
        if result["private"].get("failedLanes"):
            raise RuntimeError("Lane failures: " + ", ".join(result["private"]["failedLanes"]))
        if result["private"].get("watchdogKilled") is not True:
            raise RuntimeError("The frozen-ticker watchdog lane did not behave as an unprovided liveness case.")

    inputs = {bench, Path(__file__).resolve(), root / "RuneCLR.slnx", root / "Directory.Build.props"}
    inputs.update(path for path in bench.parent.rglob("*") if path.is_file())
    for folder in (root / "src", root / "tests"):
        inputs.update(path for path in folder.rglob("*") if path.is_file()
                      and not {"bin", "obj"}.intersection(path.relative_to(folder).parts))
    pins = {str(path): digest(path) for path in sorted(inputs) if path.is_file()}
    after = {str(path): digest(path) if path.is_file() else None for path in sorted(inputs)}
    drift = [path for path in pins if pins[path] != after[path]]
    result["pins"] = len(pins)
    result["drift"] = drift
    result["dotnetVersion"] = subprocess.run(["dotnet", "--version"], capture_output=True, text=True).stdout.strip()
    positives = [entry for entry in logs if not entry.get("negative")]
    result["passed"] = (not drift and all(entry["exit"] == 0 for entry in positives)
                        and not result.get("private", {}).get("failedLanes"))
    write_json(output / "summary.json", result)
    if not result["passed"]:
        raise RuntimeError("One or more lanes failed; see summary.json")
    print("CALLBACK_EPOCH_LANES PASS; pins=" + str(len(pins)) + "; logs=" + str(len(logs)))


def lane_health(samples, tickers, replicates, declared_us):
    clean = [value for value in samples if isinstance(value, (int, float))]
    p50s = [item["p50IntervalUs"] for item in tickers if item and "p50IntervalUs" in item]
    means = [item["actualMeanUs"] for item in tickers if item and "actualMeanUs" in item]
    violations = sum((item or {}).get("violations", 0) for item in tickers if item)
    failures = sum((item or {}).get("publishFailures", 0) for item in tickers if item)
    hr_unsupported = any((item or {}).get("highResolutionUnsupported") for item in tickers if item)
    p50 = median(p50s)
    mean_value = mean(means)
    p50_dilation = (p50 / declared_us) if (p50 and declared_us) else None
    mean_dilation = (mean_value / declared_us) if (mean_value and declared_us) else None
    ok = len(clean) == replicates and violations == 0 and failures == 0
    matched = ok and p50_dilation is not None and p50_dilation <= 1 + DILATION_LIMIT
    return {
        "count": len(clean), "medianMs": median(clean),
        "processCpuMsMedian": median([item.get("processCpuMs") for item in samples if isinstance(item, dict)]) if samples and isinstance(samples[0], dict) else None,
        "declaredUs": declared_us, "actualMeanUs": mean_value, "actualP50Us": p50,
        "meanDilation": mean_dilation, "p50Dilation": p50_dilation,
        "violations": violations, "publishFailures": failures,
        "highResolutionUnsupported": hr_unsupported,
        "ok": ok, "matchedLatencyEligible": matched,
    }


def run_private(args, root, bench, run, period, output):
    if not args.layout or not args.runtime_root:
        raise ValueError("--private requires --runtime-root and --layout.")
    host = args.layout / ("dotnet.exe" if os.name == "nt" else "dotnet")
    if not host.exists():
        raise ValueError("Private layout host is absent: " + str(host))

    def private(name, *tail, timeout=None, extra_env=None):
        return run(name, [host, "exec", "--fx-version", args.framework_version, bench, *tail],
                   timeout=timeout, extra_env=extra_env)

    probe = private("private-probe", "probe")
    epoch_ready = bool(((probe["parsed"] or {}).get("epochCapability") or 0) & 2)
    result = {"epochReady": epoch_ready, "failedLanes": []}
    if not epoch_ready:
        raise RuntimeError("The private runtime does not advertise the epoch capability.")

    proof_jit = output / "work-proof.jit"
    work = private("work-proof", "proof", "--entry", "EpochBench.Author.ArithmeticSmall",
                   "--ticks", "5", "--ticker-us", str(args.ticker_us), "--ticker-wait", args.ticker_wait,
                   "--epoch-period-us", str(period), "--deadline-ms", str(args.deadline_ms),
                   extra_env={"DOTNET_InterpList": "1", "DOTNET_JitDisasmSummary": "1",
                              "DOTNET_JitStdOutFile": str(proof_jit)})
    proof_text = (output / "work-proof.stdout.log").read_text(encoding="utf-8", errors="replace")
    jit_text = proof_jit.read_text(encoding="utf-8", errors="replace") if proof_jit.exists() else ""
    result["workProof"] = work["parsed"]
    result["interpreterProof"] = {
        "authorCompiled": [line for line in proof_text.splitlines()
                           if line.startswith("Compiled method:") and "EpochBench.Author." in line],
        "authorJitAbsent": "JIT compiled EpochBench.Author." not in jit_text,
        "jitLog": str(proof_jit)
    }

    lanes = {
        "off-noticker": ("off", 0, 100),
        "off-ticker": ("off", -1, 100),
        "clock100-noticker": ("clock", 0, 100),
        "clock100-ticker": ("clock", -1, 100),
        "clock1000-noticker": ("clock", 0, 1000),
        "clock1000-ticker": ("clock", -1, 1000),
        "epoch100": ("epoch", -1, 100),
        "epoch1000": ("epoch", -1, 1000),
    }
    samples = {name: [] for name in lanes}
    details = {name: [] for name in lanes}
    tickers = {name: [] for name in lanes}
    pairs = {interval: [] for interval in INTERVALS}
    for replicate in range(args.replicates):
        current = list(lanes)
        random.Random(20261110 + replicate).shuffle(current)
        for lane in current:
            mode, ticker_flag, interval = lanes[lane]
            ticker_us = args.ticker_us if ticker_flag == -1 else 0
            entry = private("rep%02d-%s" % (replicate, lane), "timing", "--mode", mode,
                            "--interval", str(interval), "--ticker-us", str(ticker_us),
                            "--ticker-wait", args.ticker_wait, "--epoch-period-us", str(period),
                            "--entry", "EpochBench.Author.ArithmeticMedium",
                            "--ticks", str(args.ticks), "--samples", "1", "--warmup", "0",
                            "--deadline-ms", str(args.deadline_ms))
            parsed = entry["parsed"] or {}
            sample = (parsed.get("samples") or [{}])[0]
            samples[lane].append(sample.get("totalMs"))
            details[lane].append(sample)
            tickers[lane].append(parsed.get("ticker"))
        for interval in INTERVALS:
            clock = samples["clock%d-ticker" % interval][-1]
            epoch = samples["epoch%d" % interval][-1]
            if isinstance(clock, (int, float)) and isinstance(epoch, (int, float)):
                pairs[interval].append((clock, epoch))

    health = {lane: lane_health(samples[lane], tickers[lane], args.replicates, period)
              for lane in lanes}
    matched_pairs = {}
    for interval in INTERVALS:
        clock_ok = health["clock%d-ticker" % interval]["matchedLatencyEligible"]
        epoch_ok = health["epoch%d" % interval]["matchedLatencyEligible"]
        matched_pairs[str(interval)] = (paired_summary(pairs[interval]) if (clock_ok and epoch_ok)
                                        else {"count": len(pairs[interval]), "verdict": "excluded-dilated-or-failed"})
    result.update({"lanes": health, "paired": matched_pairs,
                   "tickerUs": args.ticker_us, "epochPeriodUs": period, "replicates": args.replicates,
                   "baselineCommand": "timing --mode off with the same ticker and tick count"})

    cutoff_rows = []
    for mode, interval in (("clock", 100), ("epoch", 100), ("clock", 1000), ("epoch", 1000)):
        for requested in CUTOFFS_MS:
            lane = "%s%d-cutoff-%dms" % (mode, interval, requested)
            entry = private(lane, "cutoff", "--mode", mode, "--interval", str(interval),
                            "--ticker-us", str(args.ticker_us), "--ticker-wait", args.ticker_wait,
                            "--epoch-period-us", str(period),
                            "--entry", "EpochBench.Author.ArithmeticLong", "--ticks", "1",
                            "--deadline-ms", str(requested))
            parsed = entry["parsed"] or {}
            sample = parsed.get("sample") or {}
            budget = (sample.get("snapshot") or {}).get("EpochBudgetTicks")
            effective = (period * budget / 1000.0) if budget else None
            trip = sample.get("tripMs")
            cutoff_rows.append({
                "lane": lane, "requestedMs": requested, "effectiveMs": effective,
                "tripMs": trip, "stopMs": sample.get("stopMs"), "totalMs": sample.get("totalMs"),
                "processCpuMs": sample.get("processCpuMs"),
                "overshootVsRequestedMs": (trip - requested) if isinstance(trip, (int, float)) else None,
                "overshootVsEffectiveMs": (trip - effective) if (isinstance(trip, (int, float)) and effective) else None,
                "terminatedAtTick": sample.get("terminatedAtTick"),
                "outcome": sample.get("outcome"), "error": sample.get("error")
            })
            if sample.get("terminatedAtTick") != 0:
                raise RuntimeError("Cutoff lane did not trip: " + lane)
    result["cutoffs"] = cutoff_rows
    result["artifact"] = verify_artifacts(args, output)

    pause = private("pause-probe-epoch1000ms", "pauseprobe", "--mode", "epoch", "--interval", "100",
                    "--ticker-us", str(args.ticker_us), "--ticker-wait", args.ticker_wait,
                    "--epoch-period-us", str(period), "--entry", "EpochBench.Author.ArithmeticLong",
                    "--deadline-ms", "1000", "--pause-for-ms", "400")
    result["pauseProbe"] = pause["parsed"]
    if not (pause["parsed"] or {}).get("ok"):
        result["failedLanes"].append("pause-probe")

    frozen = run("frozen-watchdog-epoch1000ms",
                 [host, "exec", "--fx-version", args.framework_version, bench, "cutoff",
                  "--mode", "epoch", "--interval", "100", "--ticker-us", str(args.ticker_us),
                  "--ticker-wait", args.ticker_wait, "--epoch-period-us", str(period),
                  "--entry", "EpochBench.Author.ArithmeticLong", "--ticks", "1",
                  "--deadline-ms", "1000", "--pause-at-ms", "100", "--pause-for-ms", "60000"],
                 timeout=watchdog_ms(1000) / 1000.0)
    result["watchdogKilled"] = frozen["timedOut"] is True
    result["watchdogBudgetMs"] = watchdog_ms(1000)
    result["watchdogVerdict"] = ("liveness-not-provided (process killed by host watchdog)"
                                 if result["watchdogKilled"] else "unexpected-completion")

    concurrent = private("private-concurrent", "concurrent", "--mode", "epoch", "--sessions", "4",
                         "--ticker-us", str(args.ticker_us), "--ticker-wait", args.ticker_wait,
                         "--epoch-period-us", str(period), "--entry", "EpochBench.Author.ArithmeticMedium",
                         "--ticks", str(args.ticks), "--deadline-ms", str(args.deadline_ms))
    result["concurrent"] = concurrent["parsed"]

    failed = [lane for lane, item in health.items() if not item["ok"]]
    result["failedLanes"].extend(failed)
    return result


def verify_artifacts(args, output):
    """B1: pin the private layout, the five runtime outputs, and the exact source delta."""
    if not args.runtime_source_manifest or not args.runtime_root or not args.layout:
        raise ValueError("--private requires --runtime-source-manifest, --runtime-root and --layout.")
    manifest = json.loads(args.runtime_source_manifest.read_text(encoding="utf-8"))
    runtime = args.runtime_root.resolve()
    head = subprocess.check_output(["git", "-C", str(runtime), "rev-parse", "HEAD"], text=True).strip()
    manifest_head = manifest.get("head") or manifest.get("baseline_head")
    manifest_base = manifest.get("baseline_head") or manifest.get("base")
    files = manifest.get("dirty_files") or manifest.get("files") or {}
    if head != manifest_head:
        raise ValueError("Runtime HEAD " + head + " != source manifest head " + str(manifest_head) + ".")
    if manifest_base != args.runtime_base:
        raise ValueError("Source manifest base must be " + args.runtime_base + ".")
    changed = sorted(files)
    status = subprocess.check_output(["git", "-C", str(runtime), "status", "--porcelain", "--untracked-files=normal"],
                                     text=True).splitlines()
    actual = sorted(line[3:].strip() for line in status if line.strip())
    if actual != changed:
        raise ValueError("Runtime delta does not equal the source manifest: " + repr(actual))
    for name, value in files.items():
        if digest(runtime / name) != value:
            raise ValueError("Runtime source hash mismatch: " + name)
    framework = args.layout / "shared/Microsoft.NETCore.App" / args.framework_version
    build = runtime / "artifacts/bin/coreclr" / args.build_rid
    outputs = {
        "System.Private.CoreLib.dll": build / "System.Private.CoreLib.dll",
        "coreclr.dll": build / "coreclr.dll",
        "clrjit.dll": build / "clrjit.dll",
        "clrinterpreter.dll": build / "clrinterpreter.dll",
        "corerun.exe": build / "corerun.exe",
    }
    rows = {}
    for name, produced in outputs.items():
        if not produced.is_file():
            raise ValueError("Runtime artifact output is absent (build not terminal): " + str(produced))
        installed = framework / name
        if not installed.is_file():
            raise ValueError("Layout is missing " + name + ".")
        built, copied = digest(produced), digest(installed)
        if built != copied:
            raise ValueError("Layout " + name + " does not equal the runtime build output.")
        rows[name] = {"sha256": built, "path": str(produced), "layoutEqual": True}
    layout_pins = {str(path): digest(path) for path in args.layout.rglob("*") if path.is_file()}
    write_json(output / "artifact-pins.json", {"buildRID": args.build_rid, "outputs": rows,
                                               "layoutFiles": len(layout_pins),
                                               "layoutSha256": hashlib.sha256(
                                                   json.dumps(layout_pins, sort_keys=True).encode()).hexdigest(),
                                               "sourceManifest": str(args.runtime_source_manifest),
                                               "sourceManifestSha256": digest(args.runtime_source_manifest)})
    return {"buildRID": args.build_rid, "outputs": rows, "layoutFiles": len(layout_pins),
            "sourceIdentity": {"base": args.runtime_base, "head": head,
                               "deltaFiles": len(changed), "localUncommitted": True}}


def stats_selftest():
    same = [(100.0 + i, 100.5 + i) for i in range(15)]
    slower = [(100.0 + i, 105.0 + i) for i in range(15)]
    noisy = [(100.0 + i, 100.0 + (i % 7)) for i in range(15)]
    results = {"equivalent": paired_summary(same), "slower": paired_summary(slower),
               "noisy": paired_summary(noisy)}
    checks = {
        "equivalent": results["equivalent"]["verdict"] == "equivalent-within-2pct",
        "slower": results["slower"]["verdict"] == "candidate-slower",
        "dilation-limit": lane_health([50.0] * 15, [{"p50IntervalUs": 1600, "actualMeanUs": 1600,
                                                     "violations": 0, "publishFailures": 0}] * 15, 15, 1000)["matchedLatencyEligible"] is False,
        "matched": lane_health([50.0] * 15, [{"p50IntervalUs": 1020, "actualMeanUs": 1020,
                                             "violations": 0, "publishFailures": 0}] * 15, 15, 1000)["matchedLatencyEligible"] is True,
        "violations-fail": lane_health([50.0] * 15, [{"p50IntervalUs": 1000, "actualMeanUs": 1000,
                                                     "violations": 1, "publishFailures": 0}] * 15, 15, 1000)["ok"] is False,
        "late-not-fail": lane_health([50.0] * 15, [{"p50IntervalUs": 1000, "actualMeanUs": 1000,
                                                   "violations": 0, "publishFailures": 0, "lateTicks": 5}] * 15, 15, 1000)["ok"] is True,
    }
    ok = all(checks.values())
    print(json.dumps({"ok": ok, "checks": checks, "paired": results}, indent=2))
    return 0 if ok else 1


def environment():
    env = dict(os.environ)
    for key in list(env):
        if key.startswith(("DOTNET_", "COMPlus_")):
            del env[key]
    env.update({"DOTNET_MULTILEVEL_LOOKUP": "0", "DOTNET_RuneCLRInterpretCollectible": "1",
                "DOTNET_InterpMode": "0", "DOTNET_ReadyToRun": "1", "DOTNET_TieredCompilation": "0"})
    return env


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("FAIL " + str(error), file=sys.stderr)
        raise
