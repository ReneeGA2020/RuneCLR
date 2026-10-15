#include <atomic>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
#include <intrin.h>

using LONG = long;
using LONGLONG = long long;
using INT64 = long long;
#define FORCEINLINE __forceinline
static_assert(sizeof(LONG) == 4 && sizeof(INT64) == 8);

struct CLRConfig
{
    enum Option { EXTERNAL_RuneCLRPhaseAcquireLoad, EXTERNAL_RuneCLRDerivedLedger };
    static std::atomic<int> values[2];
    static int GetConfigValue(Option option) { return values[option].load(); }
};
std::atomic<int> CLRConfig::values[2]{};

static std::atomic<volatile LONGLONG*> pauseAddress{nullptr};
static std::atomic<bool> pauseEntered{false}, pauseRelease{false}, pauseTimedOut{false};
static LONG MeterCAS32(volatile LONG* address, LONG value, LONG compare)
{
    return _InterlockedCompareExchange(address, value, compare);
}
static LONGLONG MeterCAS64(volatile LONGLONG* address, LONGLONG value, LONGLONG compare)
{
    LONGLONG observed = _InterlockedCompareExchange64(address, value, compare);
    // Pause only after the real successful debit, before the header can increment.
    if (compare > 0 && value == compare - 1 && observed == compare &&
        pauseAddress.load() == address)
    {
        pauseEntered.store(true);
        auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(10);
        while (!pauseRelease.load())
        {
            if (std::chrono::steady_clock::now() >= deadline)
            {
                pauseTimedOut.store(true);
                break;
            }
            std::this_thread::yield();
        }
    }
    return observed;
}
static LONGLONG MeterIncrement64(volatile LONGLONG* address)
{
    return _InterlockedIncrement64(address);
}
template<typename T> inline T VolatileLoad(T const* address)
{
    // Mirrors volatile.h's MSVC AMD64 branch with /volatile:ms: aligned load.
    return *(T volatile const*)address;
}

#define InterlockedCompareExchange MeterCAS32
#define InterlockedCompareExchange64 MeterCAS64
#define InterlockedIncrement64 MeterIncrement64
#define private public
#include "candidate-meter.h"
#undef private
#undef InterlockedCompareExchange
#undef InterlockedCompareExchange64
#undef InterlockedIncrement64

static unsigned checks = 0;
static std::vector<std::string> cases;
struct PauseObservation
{
    int derived, acquire;
    bool cleanup;
    INT64 remaining, getter, oldSlot;
    LONG phase;
};
struct ConcurrentObservation
{
    int derived, acquire, threads;
    INT64 executionAdmitted, cleanupAdmitted;
};
static std::vector<PauseObservation> pauses;
static std::vector<ConcurrentObservation> concurrency;
static void require(bool condition, const char* message)
{
    ++checks;
    if (!condition) throw std::runtime_error(message);
}
static void configure(int derived, int acquire)
{
    CLRConfig::values[CLRConfig::EXTERNAL_RuneCLRDerivedLedger].store(derived);
    CLRConfig::values[CLRConfig::EXTERNAL_RuneCLRPhaseAcquireLoad].store(acquire);
}
static void ledger(const RuneCLRInstructionMeter& meter, INT64 limit, INT64 admitted,
                   INT64 cleanupLimit, INT64 cleanupAdmitted, bool derived)
{
    require(meter.Remaining() == limit - admitted, "execution remaining");
    require(meter.Executed() == admitted, "execution getter");
    require(meter.CleanupRemaining() == cleanupLimit - cleanupAdmitted, "cleanup remaining");
    require(meter.CleanupExecuted() == cleanupAdmitted, "cleanup getter");
    require(MeterCAS64(&meter.m_executed, 0, 0) == (derived ? 0 : admitted), "old execution slot");
    require(MeterCAS64(&meter.m_cleanupExecuted, 0, 0) == (derived ? 0 : cleanupAdmitted), "old cleanup slot");
}
static std::string profile(int derived, int acquire)
{
    return "_derived" + std::to_string(derived) + "_phaseLoad" + std::to_string(acquire);
}
static void terminal(int derived, int acquire, INT64 limit)
{
    configure(derived, acquire);
    const INT64 cleanupLimit = limit == 1 ? 2 : 1;
    RuneCLRInstructionMeter meter(limit, true, cleanupLimit);
    require(meter.Enabled() && meter.IsTerminalPrototype(), "terminal flags");
    require(meter.m_derivedLedger == (derived != 0), "cached derived flag");
    require(meter.m_phaseAcquireLoad == (acquire != 0), "cached phase flag");
    require(meter.Phase() == 0 && meter.Reason() == 0 && !meter.IsTerminated(), "initial phase");
    require(!meter.TryChargeCleanup(), "cleanup forbidden in execution phase");
    ledger(meter, limit, 0, cleanupLimit, 0, derived != 0);
    for (INT64 count = 1; count <= limit; ++count)
    {
        require(meter.ChargeExecution(), "execution admitted");
        require(meter.Phase() == 0, "last allowance remains execution phase");
        ledger(meter, limit, count, cleanupLimit, 0, derived != 0);
    }
    require(!meter.ChargeExecution(), "first execution rejection");
    require(meter.Phase() == 1 && meter.Reason() == 1 && meter.IsTerminated(), "execution rejection latches phase1");
    require(!meter.ChargeExecution(), "sticky execution rejection");
    ledger(meter, limit, limit, cleanupLimit, 0, derived != 0);
    for (INT64 count = 1; count <= cleanupLimit; ++count)
    {
        require(meter.TryChargeCleanup(), "cleanup admitted independently");
        require(meter.Phase() == 1, "last cleanup allowance remains phase1");
        ledger(meter, limit, limit, cleanupLimit, count, derived != 0);
    }
    require(!meter.TryChargeCleanup(), "first cleanup rejection");
    require(meter.Phase() == 2 && meter.Reason() == 1, "cleanup rejection latches phase2");
    require(!meter.TryChargeCleanup() && !meter.ChargeExecution(), "phase2 sticky rejection");
    ledger(meter, limit, limit, cleanupLimit, cleanupLimit, derived != 0);
    cases.push_back("terminal_limit" + std::to_string(limit) + profile(derived, acquire));
}
static void immutableConfig(int derived, int acquire)
{
    configure(derived, acquire);
    RuneCLRInstructionMeter meter(1, true, 1);
    configure(1 - derived, 1 - acquire);
    require(meter.m_derivedLedger == (derived != 0) && meter.m_phaseAcquireLoad == (acquire != 0), "config cached after construction");
    require(meter.ChargeExecution(), "cached configuration execution");
    require(!meter.ChargeExecution() && meter.TryChargeCleanup(), "cached configuration cleanup");
    ledger(meter, 1, 1, 1, 1, derived != 0);
    require(!meter.TryChargeCleanup() && meter.Phase() == 2, "cached configuration exhaustion");
    cases.push_back("immutable_configuration" + profile(derived, acquire));
}
static void maximum(int derived, int acquire)
{
    configure(derived, acquire);
    RuneCLRInstructionMeter meter(INT64_MAX, true, INT64_MAX);
    require(meter.ChargeExecution(), "maximum first execution");
    ledger(meter, INT64_MAX, 1, INT64_MAX, 0, derived != 0);
    // Controlled near-boundary injection avoids INT64_MAX iterations.
    meter.m_remaining = 1;
    if (!derived) meter.m_executed = INT64_MAX - 1;
    require(meter.ChargeExecution(), "maximum last execution");
    require(meter.Executed() == INT64_MAX && meter.Remaining() == 0, "maximum execution no overflow");
    require(!meter.ChargeExecution() && meter.Phase() == 1, "maximum execution exhaustion");
    require(meter.TryChargeCleanup(), "maximum first cleanup");
    meter.m_cleanupRemaining = 1;
    if (!derived) meter.m_cleanupExecuted = INT64_MAX - 1;
    require(meter.TryChargeCleanup(), "maximum last cleanup");
    ledger(meter, INT64_MAX, INT64_MAX, INT64_MAX, INT64_MAX, derived != 0);
    require(!meter.TryChargeCleanup() && meter.Phase() == 2, "maximum cleanup exhaustion");
    cases.push_back("maximum_with_controlled_near_boundary_injection" + profile(derived, acquire));
}
static void diagnostic(int derived, int acquire)
{
    configure(derived, acquire);
    RuneCLRInstructionMeter meter(1, false, 2);
    require(!meter.m_derivedLedger && !meter.m_phaseAcquireLoad, "diagnostic never enables terminal options");
    require(meter.ChargeExecution() && meter.ChargeExecution() && meter.ChargeExecution(), "diagnostic continues past zero");
    require(meter.Executed() == 3 && meter.Remaining() == 0 && meter.Phase() == 0, "diagnostic count past zero");
    require(!meter.TryChargeCleanup() && meter.CleanupExecuted() == 0, "diagnostic has no terminal cleanup");
    meter.m_executed = INT64_MAX - 1;
    meter.Charge();
    require(meter.Executed() == INT64_MAX, "diagnostic reaches maximum");
    meter.Charge();
    require(meter.Executed() == INT64_MAX && meter.Remaining() == 0, "diagnostic maximum saturates");
    RuneCLRInstructionMeter zero(0, false);
    require(!zero.Enabled() && zero.ChargeExecution() && zero.Executed() == 1 && zero.Remaining() == 0, "zero diagnostic behavior preserved");
    cases.push_back("nonterminal_saturating_diagnostic" + profile(derived, acquire));
}
static void zeroCleanup(int derived, int acquire)
{
    configure(derived, acquire);
    RuneCLRInstructionMeter meter(1, true, 0);
    require(meter.ChargeExecution() && !meter.ChargeExecution(), "zero cleanup execution transition");
    require(meter.Phase() == 1 && !meter.TryChargeCleanup() && meter.Phase() == 2, "zero cleanup immediate exhaustion");
    ledger(meter, 1, 1, 0, 0, derived != 0);
    cases.push_back("zero_cleanup" + profile(derived, acquire));
}
static void concurrent(int derived, int acquire, int threads)
{
    configure(derived, acquire);
    const INT64 executionLimit = 20003, cleanupLimit = 10007;
    RuneCLRInstructionMeter meter(executionLimit, true, cleanupLimit);
    std::atomic<INT64> executionAdmitted{0}, cleanupAdmitted{0};
    std::vector<std::thread> workers;
    for (int index = 0; index < threads; ++index)
        workers.emplace_back([&] { while (meter.ChargeExecution()) executionAdmitted.fetch_add(1); });
    for (auto& worker : workers) worker.join();
    require(executionAdmitted.load() == executionLimit && meter.Phase() == 1, "concurrent execution exact admissions");
    ledger(meter, executionLimit, executionLimit, cleanupLimit, 0, derived != 0);
    workers.clear();
    for (int index = 0; index < threads; ++index)
        workers.emplace_back([&] { while (meter.TryChargeCleanup()) cleanupAdmitted.fetch_add(1); });
    for (auto& worker : workers) worker.join();
    require(cleanupAdmitted.load() == cleanupLimit && meter.Phase() == 2, "concurrent cleanup exact admissions");
    ledger(meter, executionLimit, executionLimit, cleanupLimit, cleanupLimit, derived != 0);
    concurrency.push_back({derived, acquire, threads, executionAdmitted.load(), cleanupAdmitted.load()});
    cases.push_back("trusted_shared_meter_threads" + std::to_string(threads) + profile(derived, acquire));
}
static void pauseWindow(int derived, int acquire, bool cleanup)
{
    configure(derived, acquire);
    RuneCLRInstructionMeter meter(1, true, 1);
    if (cleanup) require(meter.ChargeExecution() && !meter.ChargeExecution(), "pause fixture enters cleanup");
    pauseEntered.store(false); pauseRelease.store(false); pauseTimedOut.store(false);
    pauseAddress.store(cleanup ? &meter.m_cleanupRemaining : &meter.m_remaining);
    std::atomic<bool> admitted{false};
    std::thread worker([&] { admitted.store(cleanup ? meter.TryChargeCleanup() : meter.ChargeExecution()); });
    auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(5);
    while (!pauseEntered.load() && std::chrono::steady_clock::now() < deadline) std::this_thread::yield();
    bool reached = pauseEntered.load();
    INT64 duringRemaining = cleanup ? meter.CleanupRemaining() : meter.Remaining();
    INT64 duringExecuted = cleanup ? meter.CleanupExecuted() : meter.Executed();
    INT64 duringSlot = MeterCAS64(cleanup ? &meter.m_cleanupExecuted : &meter.m_executed, 0, 0);
    LONG duringPhase = meter.Phase();
    pauseRelease.store(true);
    worker.join();
    pauseAddress.store(nullptr);
    require(reached && !pauseTimedOut.load(), "successful debit pause reached without timeout");
    require(duringRemaining == 0 && duringSlot == 0, "debit paused before old increment");
    require(duringExecuted == (derived ? 1 : 0), "derived getter linearizes at debit CAS");
    require(duringPhase == (cleanup ? 1 : 0), "last paused admission preserves phase");
    require(admitted.load(), "paused debit returns admitted");
    ledger(meter, 1, 1, 1, cleanup ? 1 : 0, derived != 0);
    pauses.push_back({derived, acquire, cleanup, duringRemaining, duringExecuted, duringSlot, duringPhase});
    cases.push_back(std::string("real_CAS_pause_") + (cleanup ? "cleanup" : "execution") + profile(derived, acquire));
}
int main()
{
    try
    {
        require(sizeof(RuneCLRInstructionMeter) == 64 && alignof(RuneCLRInstructionMeter) == 8, "native layout size64 align8");
        require(offsetof(RuneCLRInstructionMeter, m_enabled) == 0 && offsetof(RuneCLRInstructionMeter, m_terminalPrototype) == 1 &&
                offsetof(RuneCLRInstructionMeter, m_phaseAcquireLoad) == 2 && offsetof(RuneCLRInstructionMeter, m_derivedLedger) == 3,
                "native flag layout");
        require(offsetof(RuneCLRInstructionMeter, m_remaining) == 8 && offsetof(RuneCLRInstructionMeter, m_executed) == 16 &&
                offsetof(RuneCLRInstructionMeter, m_cleanupRemaining) == 24 && offsetof(RuneCLRInstructionMeter, m_cleanupExecuted) == 32 &&
                offsetof(RuneCLRInstructionMeter, m_phase) == 40 && offsetof(RuneCLRInstructionMeter, m_initialExecutionLimit) == 48 &&
                offsetof(RuneCLRInstructionMeter, m_initialCleanupLimit) == 56, "native old offsets and immutable allowance offsets");
        cases.push_back("layout64_align8_old_offsets_unchanged");
        for (int derived : {0, 1}) for (int acquire : {0, 1})
        {
            terminal(derived, acquire, 1); terminal(derived, acquire, 2);
            immutableConfig(derived, acquire); maximum(derived, acquire);
            diagnostic(derived, acquire); zeroCleanup(derived, acquire);
            concurrent(derived, acquire, 2); concurrent(derived, acquire, 4);
            pauseWindow(derived, acquire, false); pauseWindow(derived, acquire, true);
        }
        std::cout << "{\"passed\":true,\"checks\":" << checks << ",\"caseCount\":" << cases.size() << ",\"cases\":[";
        for (size_t index = 0; index < cases.size(); ++index)
        {
            if (index) std::cout << ',';
            std::cout << '"' << cases[index] << '"';
        }
        std::cout << "],\"CASPauseObservations\":[";
        for (size_t index = 0; index < pauses.size(); ++index)
        {
            if (index) std::cout << ',';
            const auto& value = pauses[index];
            std::cout << "{\"derived\":" << value.derived << ",\"phaseAcquire\":" << value.acquire
                      << ",\"cleanup\":" << (value.cleanup ? "true" : "false")
                      << ",\"remaining\":" << value.remaining << ",\"getter\":" << value.getter
                      << ",\"oldSlot\":" << value.oldSlot << ",\"phase\":" << value.phase << '}';
        }
        std::cout << "],\"trustedConcurrencyObservations\":[";
        for (size_t index = 0; index < concurrency.size(); ++index)
        {
            if (index) std::cout << ',';
            const auto& value = concurrency[index];
            std::cout << "{\"derived\":" << value.derived << ",\"phaseAcquire\":" << value.acquire
                      << ",\"threads\":" << value.threads << ",\"executionAdmitted\":" << value.executionAdmitted
                      << ",\"cleanupAdmitted\":" << value.cleanupAdmitted << '}';
        }
        std::cout << "]}\n";
        return 0;
    }
    catch (const std::exception& error)
    {
        std::cerr << "FAIL after " << checks << " checks: " << error.what() << '\n';
        return 1;
    }
}
