namespace DeliveryAppDep;

public static class Marker
{
    public static string Touch()
    {
        var path = Environment.GetEnvironmentVariable("DELIVERY_APPDEP_SENTINEL");
        if (!string.IsNullOrEmpty(path))
            File.WriteAllText(path, "loaded");
        return "loaded";
    }
}
