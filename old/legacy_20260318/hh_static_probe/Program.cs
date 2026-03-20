using System.Reflection;
using System.Text.Json;

var baseDir = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", ".."));
var vendorDir = Path.Combine(baseDir, "vendor", "hellhades_reference");
var modelsPath = Path.Combine(vendorDir, "HellHades.ArtifactExtractor.Models.dll");

var asm = Assembly.LoadFrom(modelsPath);
var typeNames = new[]
{
    "HellHades.ArtifactExtractor.Models.ArtifactSet",
    "HellHades.ArtifactExtractor.Models.HeroFraction",
    "HellHades.ArtifactExtractor.Models.HeroRole",
    "HellHades.ArtifactExtractor.Models.ArtifactKind",
};

var result = new Dictionary<string, Dictionary<string, int>>();

foreach (var typeName in typeNames)
{
    var type = asm.GetType(typeName, throwOnError: true)!;
    var values = new Dictionary<string, int>();
    foreach (var name in Enum.GetNames(type))
    {
        var value = Convert.ToInt32(Enum.Parse(type, name));
        values[name] = value;
    }

    result[type.Name] = values;
}

Console.WriteLine(JsonSerializer.Serialize(result, new JsonSerializerOptions
{
    WriteIndented = true,
}));
