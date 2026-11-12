namespace SessionOrigin.Chain;

/// <summary>A single foreign-frame hop used to build a deep collectible-ALC stack.</summary>
public static class ChainStep
{
    public static void Invoke(System.Action next) => next();
}