using System.Reflection;
using System.Runtime.CompilerServices;

namespace RuneCLR.Runtime;

public sealed class MapRunner
{
    // Keep all map objects and reflection metadata on a stack that disappears before observation.
    [MethodImpl(MethodImplOptions.NoInlining)]
    public MapRunResult Run(MapPackage package, MapRunOptions? options = null)
    {
        ArgumentNullException.ThrowIfNull(package);
        ArgumentException.ThrowIfNullOrWhiteSpace(package.Id);
        ArgumentException.ThrowIfNullOrWhiteSpace(package.AssemblyPath);
        ArgumentException.ThrowIfNullOrWhiteSpace(package.EntryType);
        options ??= new MapRunOptions();
        options.Validate();

        var loadContext = new MapLoadContext(package);
        var ticket = new UnloadTicket(new WeakReference(loadContext, trackResurrection: true));
        using var context = new MapContext(package.Id, options);
        IMapScript? script = null;
        var completedTicks = 0;
        string? error = null;

        try
        {
            var assembly = loadContext.LoadFromAssemblyPath(Path.GetFullPath(package.AssemblyPath));
            var entryType = assembly.GetType(package.EntryType, throwOnError: true)!;
            if (!typeof(IMapScript).IsAssignableFrom(entryType) || entryType.IsAbstract)
            {
                throw new InvalidDataException("The entry type must implement IMapScript and be concrete.");
            }

            script = (IMapScript)Activator.CreateInstance(entryType)!;
            context.BeginCallback();
            script.OnStart(context);
            context.CheckViolation();

            for (var tick = 0; tick < options.TickCount; tick++)
            {
                context.BeginCallback();
                script.OnTick(new MapTick(tick, options.TickDuration));
                context.CheckViolation();
                completedTicks++;
            }
        }
        catch (Exception exception)
        {
            error = Describe(exception);
        }
        finally
        {
            try
            {
                if (script is not null)
                {
                    context.BeginCallback();
                    script.OnStop();
                    context.CheckViolation();
                }
            }
            catch (Exception exception)
            {
                var stopError = $"OnStop: {Describe(exception)}";
                error = error is null ? stopError : $"{error}; {stopError}";
            }
            finally
            {
                context.Dispose();
                script = null;
                loadContext.Unload();
            }
        }

        var report = new MapRunReport(package.Id,
            error is null ? MapRunOutcome.Completed : MapRunOutcome.Failed,
            completedTicks, context.CreatedEntities, context.ReleasedEntities,
            context.RemainingEntities, context.Logs, error);
        return new MapRunResult(report, ticket);
    }

    private static string Describe(Exception exception)
    {
        if (exception is TargetInvocationException { InnerException: { } inner })
        {
            exception = inner;
        }

        // Never retain a map-defined exception or its Type in a host-owned result.
        return $"{exception.GetType().FullName}: {exception.Message}";
    }
}
