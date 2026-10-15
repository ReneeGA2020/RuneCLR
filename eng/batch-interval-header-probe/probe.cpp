#include <atomic>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
#include <intrin.h>
using LONG = long;
using LONGLONG = long long;
using INT64 = long long;
using UINT32 = unsigned int;
#define FORCEINLINE __forceinline
#define NOINLINE __declspec(noinline)
struct CLRConfig
{
    enum Option { EXTERNAL_RuneCLRPhaseAcquireLoad, EXTERNAL_RuneCLRDerivedLedger, EXTERNAL_RuneCLRBatchInterval };
    static int values[3];
    static UINT32 GetConfigValue(Option option) { return values[option]; }
};
int CLRConfig::values[3]{};
static volatile LONGLONG* capture = nullptr;
static std::vector<INT64> chunks;
static volatile LONGLONG* pauseRemaining = nullptr;
static std::atomic<int> pauseStage{0};
static LONGLONG CAS64(volatile LONGLONG* p, LONGLONG v, LONGLONG c)
{
    auto result = _InterlockedCompareExchange64(p, v, c);
    if (p == pauseRemaining && v == c-1 && result == c && pauseStage.exchange(1) == 0)
        while (pauseStage.load() != 2) std::this_thread::yield();
    if (p == capture && v > c && result == c) chunks.push_back(v-c);
    return result;
}
static LONG CAS32(volatile LONG* p, LONG v, LONG c) { return _InterlockedCompareExchange(p,v,c); }
template<class T> T VolatileLoad(T const* p) { return *(T volatile const*)p; }
#define InterlockedCompareExchange64 CAS64
#define InterlockedCompareExchange CAS32
#define InterlockedIncrement64 _InterlockedIncrement64
#define private public
#include "candidate-meter.h"
#undef private
#include "candidate-state.h"
static int checks = 0, cases = 0;
static void require(bool value, const char* message) { ++checks; if (!value) throw std::runtime_error(message); }
static void configure(int n, int derived=0)
{
    CLRConfig::values[0]=1; CLRConfig::values[1]=derived; CLRConfig::values[2]=n;
}
int main()
{
    try
    {
        std::cout << "{\"cadence\":[";
        bool first=true;
        for (int n : {1,100,1000})
        {
            configure(n);
            for (INT64 limit : {INT64(1),INT64(n-1),INT64(n),INT64(n+1)})
            {
                if (limit==0) continue;
                ++cases;
                RuneCLRInstructionMeter meter(limit,true,17);
                RuneCLRBatchState state;
                INT64 admitted=0;
                while (state.Admit(&meter,&meter,&state))
                {
                    ++admitted;
                    require(admitted<=limit+n,"single worker overshoot runaway");
                }
                state.Flush();
                require(meter.IsTerminated() && meter.Remaining()==0,"terminal latch");
                require(meter.Executed()==admitted && admitted>=limit && admitted-limit<=n-1,"actual post-admitted overshoot");
                require(meter.TryChargeCleanup(),"cleanup admitted");
                require(meter.CleanupRemaining()==16 && meter.CleanupExecuted()==1,"cleanup remains exact");
            }
            ++cases;
            RuneCLRInstructionMeter meter(100000,true,17);
            capture=&meter.m_executed; chunks.clear();
            RuneCLRBatchState state;
            for (int i=0;i<2*n+7;++i) require(state.Admit(&meter,&meter,&state),"high allowance admit");
            state.Flush(); capture=nullptr;
            require(meter.Executed()==2*n+7 && meter.Remaining()==100000-2*n-7,"partial flush totals");
            require(chunks.size()==(n==1?9u:3u),"actual flush cadence count");
            require(chunks[0]==n && chunks[1]==n && chunks.back()==(n==1?1:7),"actual full/partial flush amounts");
            if (!first) std::cout << ','; first=false;
            std::cout << "{\"interval\":" << n << ",\"actualChunks\":[";
            for (size_t i=0;i<chunks.size();++i) { if(i) std::cout<<',';std::cout<<chunks[i]; }
            std::cout << "]}";
            ++cases;
            configure(n,1);
            RuneCLRInstructionMeter derived(1,true,17);
            { RuneCLRBatchState debt; for(int i=0;i<n;++i) require(debt.Admit(&derived,&derived,&debt),"derived profile safe admit"); }
            require(derived.Executed()==n,"experimental count not clamped derived getter");
            ++cases;
            configure(n);
            RuneCLRInstructionMeter a(10000,true,17), b(10000,true,17);
            RuneCLRBatchState owner;
            require(owner.Admit(&a,&a,&owner),"owner A");
            require(owner.Admit(&b,&b,&owner),"owner B");
            require(a.Executed()==1 && b.Executed()==0,"owner change flush before transfer");
            owner.Flush(); require(b.Executed()==1,"owner B settled");
            ++cases;
            try { RuneCLRBatchState unwind; require(unwind.Admit(&a,&a,&unwind),"unwind admission"); throw 1; } catch(int) {}
            require(a.Executed()==2,"ordinary C++ unwind debt flush");
            ++cases;
            RuneCLRInstructionMeter nearMax(INT64_MAX,true,17);
            nearMax.m_executed=INT64_MAX-1;nearMax.m_remaining=1;
            nearMax.RecordBatch(1000);
            require(nearMax.Executed()==INT64_MAX && nearMax.Remaining()==0 && nearMax.IsTerminated(),"saturating signed range");
            ++cases;
            RuneCLRInstructionMeter mixed(INT64_MAX,true,17);
            mixed.m_executed=INT64_MAX-1;mixed.m_remaining=2;
            pauseRemaining=&mixed.m_remaining;pauseStage.store(0);
            bool exactAdmitted=false;
            std::thread exact([&] { exactAdmitted=mixed.ChargeExecution(); });
            while(pauseStage.load()!=1) std::this_thread::yield();
            mixed.RecordBatch(1000);
            pauseStage.store(2);exact.join();pauseRemaining=nullptr;
            require(exactAdmitted && mixed.Executed()==INT64_MAX && mixed.Remaining()==0,"concurrent exact counter saturates after debt");
            ++cases;
            RuneCLRInstructionMeter shared(1,true,17);
            RuneCLRBatchState s1,s2;
            require(s1.Admit(&shared,&s1,&s1) && s2.Admit(&shared,&s2,&s2),"two workers begin before debt");
            for(int i=1;i<n;++i) require(s1.Admit(&shared,&s1,&s1) && s2.Admit(&shared,&s2,&s2),"two live batches");
            s1.Flush();s2.Flush();
            require(shared.Executed()==2*n && shared.Remaining()==0,"multiple live batches are reported, not refunded");
        }
        ++cases;
        configure(0,1);
        RuneCLRInstructionMeter original(2,true,17);
        require(original.BatchInterval()==0 && original.ChargeExecution() && original.ChargeExecution() && !original.ChargeExecution(),"OFF preserves exact admission");
        require(original.Executed()==2 && original.Remaining()==0,"OFF derived ledger unchanged");
        ++cases;
        configure(1000);
        RuneCLRInstructionMeter diagnostic(2,false,17);
        require(diagnostic.BatchInterval()==0,"diagnostic never batches");
        for(int i=0;i<5;++i) diagnostic.Charge();
        require(diagnostic.Executed()==5 && diagnostic.Remaining()==0 && !diagnostic.IsTerminated(),"diagnostic accounting unchanged");
        ++cases;
        configure(99);
        RuneCLRInstructionMeter invalid(2,true,17);
        require(invalid.BatchInterval()==0,"unsupported interval stays disabled");
        std::cout << "],\"passed\":true,\"cases\":" << cases << ",\"checks\":" << checks << ",\"size\":" << sizeof(RuneCLRInstructionMeter) << "}\n";
    }
    catch(const std::exception& ex) { std::cerr<<ex.what()<<'\n';return 1; }
}
