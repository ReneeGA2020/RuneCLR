using System;
using System.Runtime.CompilerServices;
using RuneCLR.TrustedUpdate;

internal interface ICounterGame
{
    int Value { get; }
    int Add(int value);
}

internal sealed class CounterGame : ICounterGame
{
    public int Value { get; private set; }
    public int Add(int value) => Value += value;
}

internal interface IEchoGame
{
    int Echo(int value);
}

internal sealed class EchoGame : IEchoGame
{
    public int Echo(int value) => value * 2;
}

internal sealed class Capture
{
}

internal static class Program
{
    static int checks;
    static int failures;

    static void Check(string name, bool condition)
    {
        checks++;
        if (!condition)
        {
            failures++;
            Console.Error.WriteLine("FAIL " + name);
        }
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    static (TrustedModuleCallResult Result, WeakReference Module, WeakReference Capture, WeakReference Callback, WeakReference Exception, TrustedModuleSession<ICounterGame> Owner, bool Closed) ExerciseFailure()
    {
        var module = new CounterGame();
        var session = new TrustedModuleSession<ICounterGame>(module);
        var capture = new Capture();
        Exception? captured = null;
        Func<ICounterGame, int> callback = _ =>
        {
            GC.KeepAlive(capture);
            var error = new InvalidOperationException("private-author-text");
            captured = error;
            throw error;
        };
        var result = session.Invoke(callback);
        var closed = session.IsClosed;
        return (result, new WeakReference(module), new WeakReference(capture), new WeakReference(callback), new WeakReference(captured), session, closed);
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    static (TrustedModuleCallResult Result, TrustedModuleSession<ICounterGame> Owner, WeakReference Callback, WeakReference Capture) ExerciseSuccessfulCallRetention()
    {
        var module = new CounterGame();
        var session = new TrustedModuleSession<ICounterGame>(module);
        var capture = new Capture();
        Func<ICounterGame, int> callback = game =>
        {
            GC.KeepAlive(capture);
            return game.Add(8);
        };
        var result = session.Invoke(callback);
        return (result, session, new WeakReference(callback), new WeakReference(capture));
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    static (TrustedModuleSession<ICounterGame> Owner, WeakReference Module, bool Closed) ExerciseCloseRetention()
    {
        var module = new CounterGame();
        var session = new TrustedModuleSession<ICounterGame>(module);
        session.Close();
        return (session, new WeakReference(module), session.IsClosed);
    }

    static int Main()
    {
        var counter = new CounterGame();
        using (var session = new TrustedModuleSession<ICounterGame>(counter))
        {
            var first = session.Invoke(module => module.Add(2));
            var second = session.Invoke(module => module.Add(1));
            Check("direct interface and consecutive calls", first.Succeeded && first.Value == 2 && second.Succeeded && second.Value == 3 && counter.Value == 3 && !session.IsClosed);
        }

        var counterSession = new TrustedModuleSession<ICounterGame>(new CounterGame());
        var echoSession = new TrustedModuleSession<IEchoGame>(new EchoGame());
        var counterResult = counterSession.Invoke(module => module.Add(4));
        var echoResult = echoSession.Invoke(module => module.Echo(7));
        counterSession.Close();
        var echoAfterClose = echoSession.Invoke(module => module.Echo(3));
        Check("two game interfaces", counterResult.Succeeded && counterResult.Value == 4 && echoResult.Succeeded && echoResult.Value == 14 && counterSession.IsClosed && echoAfterClose.Succeeded && echoAfterClose.Value == 6);
        counterSession.Dispose();
        echoSession.Dispose();

        var closedCounter = new CounterGame();
        var closedSession = new TrustedModuleSession<ICounterGame>(closedCounter);
        closedSession.Close();
        closedSession.Dispose();
        closedSession.Dispose();
        var enteredAfterClose = false;
        var closedResult = closedSession.Invoke(module =>
        {
            enteredAfterClose = true;
            return module.Add(1);
        });
        Check("close and dispose reject without entering author", closedResult.Failure == TrustedModuleCallFailure.Closed && !closedResult.Succeeded && !enteredAfterClose && closedCounter.Value == 0 && closedSession.IsClosed);

        var borrowCounter = new CounterGame();
        var borrowSession = new TrustedModuleSession<ICounterGame>(borrowCounter);
        var borrowed = borrowSession.Invoke(module =>
        {
            borrowSession.Close();
            return module.Add(4);
        });
        var enteredAfterBorrow = false;
        var later = borrowSession.Invoke(module =>
        {
            enteredAfterBorrow = true;
            return module.Add(1);
        });
        Check("close during call borrows module and later rejects", borrowed.Succeeded && borrowed.Value == 4 && borrowSession.IsClosed && later.Failure == TrustedModuleCallFailure.Closed && !enteredAfterBorrow && borrowCounter.Value == 4);
        borrowSession.Dispose();

        var closeNestedCounter = new CounterGame();
        var closeNestedSession = new TrustedModuleSession<ICounterGame>(closeNestedCounter);
        var closeNestedEntered = false;
        TrustedModuleCallResult closeNested = default;
        var closeNestedOuter = closeNestedSession.Invoke(module =>
        {
            closeNestedSession.Close();
            closeNested = closeNestedSession.Invoke(inner =>
            {
                closeNestedEntered = true;
                return inner.Add(99);
            });
            return module.Add(6);
        });
        Check("close then nested returns Closed and outer completes", closeNestedOuter.Succeeded && closeNestedOuter.Value == 6 && closeNested.Failure == TrustedModuleCallFailure.Closed && closeNested.Value == 0 && !closeNestedEntered && closeNestedSession.IsClosed && closeNestedCounter.Value == 6);
        closeNestedSession.Dispose();

        var closedNullSession = new TrustedModuleSession<ICounterGame>(new CounterGame());
        closedNullSession.Close();
        var closedNullThrew = false;
        try
        {
            closedNullSession.Invoke(null!);
        }
        catch (ArgumentNullException)
        {
            closedNullThrew = true;
        }
        Check("null callback after close still throws", closedNullThrew && closedNullSession.IsClosed);
        closedNullSession.Dispose();

        var nestedNullSession = new TrustedModuleSession<ICounterGame>(new CounterGame());
        var nestedNullOuter = nestedNullSession.Invoke(module =>
        {
            nestedNullSession.Invoke(null!);
            return module.Add(7);
        });
        Check("nested null throws into outer and closes", nestedNullOuter.Failure == TrustedModuleCallFailure.CallbackFailed && nestedNullOuter.Value == 0 && nestedNullSession.IsClosed);
        nestedNullSession.Dispose();

        var reentrantCounter = new CounterGame();
        var reentrantSession = new TrustedModuleSession<ICounterGame>(reentrantCounter);
        var nestedEntered = false;
        TrustedModuleCallResult nested = default;
        var outer = reentrantSession.Invoke(module =>
        {
            nested = reentrantSession.Invoke(inner =>
            {
                nestedEntered = true;
                return inner.Add(9);
            });
            return module.Add(5);
        });
        Check("reentrant call rejected while outer completes", outer.Succeeded && outer.Value == 5 && nested.Failure == TrustedModuleCallFailure.ReentrantCall && nested.Value == 0 && !nestedEntered && !reentrantSession.IsClosed && reentrantCounter.Value == 5);
        reentrantSession.Dispose();

        var failure = ExerciseFailure();
        GC.Collect();
        GC.WaitForPendingFinalizers();
        GC.Collect();
        Check("callback exception closes with fixed failure", failure.Result.Failure == TrustedModuleCallFailure.CallbackFailed && !failure.Result.Succeeded && failure.Result.Value == 0 && failure.Closed && failure.Owner.IsClosed);
        Check("callback exception object is not retained", !failure.Exception.IsAlive);
        Check("alive owner released module, callback and capture", !failure.Module.IsAlive && !failure.Capture.IsAlive && !failure.Callback.IsAlive);
        GC.KeepAlive(failure.Owner);
        failure.Owner.Dispose();

        var closeRetention = ExerciseCloseRetention();
        GC.Collect();
        GC.WaitForPendingFinalizers();
        GC.Collect();
        Check("normal close releases module while owner alive", closeRetention.Closed && !closeRetention.Module.IsAlive);
        GC.KeepAlive(closeRetention.Owner);
        closeRetention.Owner.Dispose();

        var successful = ExerciseSuccessfulCallRetention();
        GC.Collect();
        GC.WaitForPendingFinalizers();
        GC.Collect();
        Check("successful call releases callback and capture", successful.Result.Succeeded && successful.Result.Value == 8 && !successful.Callback.IsAlive && !successful.Capture.IsAlive);
        GC.KeepAlive(successful.Owner);
        successful.Owner.Dispose();

        var nullSession = new TrustedModuleSession<ICounterGame>(new CounterGame());
        var nullThrew = false;
        try
        {
            nullSession.Invoke(null!);
        }
        catch (ArgumentNullException)
        {
            nullThrew = true;
        }
        var afterNull = nullSession.Invoke(module => module.Add(3));
        Check("null callback is a host argument error", nullThrew && !nullSession.IsClosed && afterNull.Succeeded && afterNull.Value == 3);
        nullSession.Dispose();

        var ctorThrew = false;
        try
        {
            _ = new TrustedModuleSession<ICounterGame>(null!);
        }
        catch (ArgumentNullException)
        {
            ctorThrew = true;
        }
        Check("null module is rejected", ctorThrew);

        Console.WriteLine("TRUSTED_MODULE_SESSION_CHECKS " + checks + " FAILURES " + failures);
        return failures == 0 ? 0 : 1;
    }
}