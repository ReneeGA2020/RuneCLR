using System;

namespace TrustedUpdate;

public interface IHostApi
{
    int Echo(int value);
}

public interface IUpdate
{
    int Run(IHostApi host, Func<int, int> callback);
}
