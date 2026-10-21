using System;
using System.Runtime.CompilerServices;

namespace TrustedGameGenericSize;

internal static class VariantRoot
{
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static void Fill(object?[] results)
    {
#if BASELINE
        var c0 = new CellB("baseline-0");
        c0.Set("baseline-0b");
        results[0] = OpsB.Relay(c0);

        var c1 = new CellB("baseline-1");
        c1.Set("baseline-1b");
        results[1] = OpsB.Relay(c1);

        var c2 = new CellB("baseline-2");
        c2.Set("baseline-2b");
        results[2] = OpsB.Relay(c2);

        var c3 = new CellB("baseline-3");
        c3.Set("baseline-3b");
        results[3] = OpsB.Relay(c3);

        var c4 = new CellB("baseline-4");
        c4.Set("baseline-4b");
        results[4] = OpsB.Relay(c4);

        var c5 = new CellB("baseline-5");
        c5.Set("baseline-5b");
        results[5] = OpsB.Relay(c5);

        var c6 = new CellB("baseline-6");
        c6.Set("baseline-6b");
        results[6] = OpsB.Relay(c6);

        var c7 = new CellB("baseline-7");
        c7.Set("baseline-7b");
        results[7] = OpsB.Relay(c7);
#elif REF1
        var c0 = new Cell<string>("ref-0");
        c0.Set("ref-0b");
        results[0] = Ops.Relay(c0);
#elif REF8
        var c0 = new Cell<string>("ref-0");
        c0.Set("ref-0b");
        results[0] = Ops.Relay(c0);

        var c1 = new Cell<object>(new object());
        c1.Set(new object());
        results[1] = Ops.Relay(c1);

        var c2 = new Cell<InvalidOperationException>(new InvalidOperationException("ref-2"));
        c2.Set(new InvalidOperationException("ref-2b"));
        results[2] = Ops.Relay(c2);

        var c3 = new Cell<int[]>(new[] { 3, 4 });
        c3.Set(new[] { 5, 6 });
        results[3] = Ops.Relay(c3);

        var c4 = new Cell<string[]>(new[] { "ref-4" });
        c4.Set(new[] { "ref-4b" });
        results[4] = Ops.Relay(c4);

        var c5 = new Cell<RefA>(new RefA(5));
        c5.Set(new RefA(6));
        results[5] = Ops.Relay(c5);

        var c6 = new Cell<RefB>(new RefB(7));
        c6.Set(new RefB(8));
        results[6] = Ops.Relay(c6);

        var c7 = new Cell<RefC>(new RefC(9));
        c7.Set(new RefC(10));
        results[7] = Ops.Relay(c7);
#elif VAL1
        var c0 = new Cell<int>(123456);
        c0.Set(654321);
        results[0] = Ops.Relay(c0);
#elif VAL8
        var c0 = new Cell<byte>((byte)1);
        c0.Set((byte)2);
        results[0] = Ops.Relay(c0);

        var c1 = new Cell<short>((short)300);
        c1.Set((short)301);
        results[1] = Ops.Relay(c1);

        var c2 = new Cell<int>(123456);
        c2.Set(654321);
        results[2] = Ops.Relay(c2);

        var c3 = new Cell<long>(1234567890123L);
        c3.Set(1234567890124L);
        results[3] = Ops.Relay(c3);

        var c4 = new Cell<float>(1.25f);
        c4.Set(2.5f);
        results[4] = Ops.Relay(c4);

        var c5 = new Cell<double>(3.75);
        c5.Set(4.5);
        results[5] = Ops.Relay(c5);

        var c6 = new Cell<Guid>(new Guid("11111111-1111-1111-1111-111111111111"));
        c6.Set(new Guid("22222222-2222-2222-2222-222222222222"));
        results[6] = Ops.Relay(c6);

        var c7 = new Cell<Blob>(new Blob(1, 2, 3));
        c7.Set(new Blob(4, 5, 6));
        results[7] = Ops.Relay(c7);
#else
#error Define exactly one variant: BASELINE, REF1, REF8, VAL1 or VAL8.
#endif
    }
}

