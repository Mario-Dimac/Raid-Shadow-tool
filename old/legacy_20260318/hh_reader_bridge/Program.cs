using System.Reflection;
using System.Runtime.Loader;
using System.Text.Json;

var baseDir = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", ".."));
var vendorDir = Path.Combine(baseDir, "vendor", "hellhades_reference");
var installDir = Path.Combine(
    Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
    "HellHades Artifact Extractor"
);

AssemblyLoadContext.Default.Resolving += (_, assemblyName) =>
{
    var candidateNames = new[]
    {
        Path.Combine(vendorDir, $"{assemblyName.Name}.dll"),
        Path.Combine(installDir, $"{assemblyName.Name}.dll"),
    };
    var found = candidateNames.FirstOrDefault(File.Exists);
    return found is null ? null : AssemblyLoadContext.Default.LoadFromAssemblyPath(found);
};

var result = new Dictionary<string, object?>
{
    ["base_dir"] = baseDir,
    ["install_dir"] = installDir,
    ["started_at"] = DateTimeOffset.UtcNow,
};

try
{
    var extractorAsm = AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.Combine(vendorDir, "HellHades.ArtifactExtractor.dll"));
    var readerAsm = AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.Combine(vendorDir, "HellHades.ArtifactExtractor.Models.Reader.dll"));
    var modelsAsm = AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.Combine(vendorDir, "HellHades.ArtifactExtractor.Models.dll"));
    var loggingAsm = AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.Combine(installDir, "Microsoft.Extensions.Logging.Abstractions.dll"));

    var windowsProcessMemoryType = readerAsm.GetType("HellHades.ArtifactExtractor.Models.Reader.Windows.WindowsProcessMemory", true)!;
    var windowsHelperType = readerAsm.GetType("HellHades.ArtifactExtractor.Models.Reader.Windows.WindowsHelper", true)!;
    var raidMemoryReaderType = readerAsm.GetType("HellHades.ArtifactExtractor.Models.Reader.RaidMemoryReader", true)!;
    var iRaidReaderType = readerAsm.GetType("HellHades.ArtifactExtractor.Models.Reader.IRaidReader", true)!;
    var optionsType = extractorAsm.GetType("HellHades.ArtifactExtractor.LiveUpdates.UpdateRaidDataRequestHandlerOptions", true)!;
    var raidProcessReaderType = extractorAsm.GetType("HellHades.ArtifactExtractor.RaidReader.RaidProcessReader", true)!;
    var nullLoggerType = loggingAsm.GetType("Microsoft.Extensions.Logging.Abstractions.NullLogger", true)!;

    var processMemory = Activator.CreateInstance(windowsProcessMemoryType)!;
    var helper = Activator.CreateInstance(windowsHelperType, processMemory)!;
    var raidMemoryReader = Activator.CreateInstance(raidMemoryReaderType, processMemory)!;
    var options = Activator.CreateInstance(optionsType)!;
    var logger = nullLoggerType.GetProperty("Instance", BindingFlags.Public | BindingFlags.Static)!.GetValue(null)!;

    var readerImplementations = readerAsm.GetTypes()
        .Where(type => type.IsClass && !type.IsAbstract && iRaidReaderType.IsAssignableFrom(type))
        .OrderBy(type => type.FullName)
        .Select(type => new
        {
            type = type,
            instance = Activator.CreateInstance(type)!,
        })
        .ToArray();

    var readerArray = Array.CreateInstance(iRaidReaderType, readerImplementations.Length);
    for (var i = 0; i < readerImplementations.Length; i++)
    {
        readerArray.SetValue(readerImplementations[i].instance, i);
    }

    var raidProcessReader = Activator.CreateInstance(
        raidProcessReaderType,
        options,
        readerArray,
        raidMemoryReader,
        logger,
        helper
    )!;

    var isRaidRunning = (bool?)raidProcessReaderType.GetProperty("IsRaidRunning")?.GetValue(raidProcessReader);
    var raidProcess = raidProcessReaderType.GetProperty("RaidProcess")?.GetValue(raidProcessReader);
    var raidProcessId = raidProcess?.GetType().GetProperty("Id")?.GetValue(raidProcess);

    result["readers"] = readerImplementations.Select(x => x.type.FullName).ToArray();
    result["is_raid_running"] = isRaidRunning;
    result["raid_process_id"] = raidProcessId;
    result["battle_type_inspection"] = InspectBattleTypes(extractorAsm, readerAsm, modelsAsm);
    result["battle_loader_inspection"] = InspectBattleLoaders(extractorAsm, readerAsm, modelsAsm);
    result["damage_inspection"] = InspectDamageTypes(extractorAsm, readerAsm, modelsAsm);

    var loadAccountData = raidProcessReaderType.GetMethod("LoadAccountData", BindingFlags.Public | BindingFlags.Instance)!;
    var raidData = loadAccountData.Invoke(raidProcessReader, null);

    result["load_account_data"] = "ok";
    result["summary"] = SummarizeRaidData(raidData);
    result["data"] = DumpRaidData(raidData);
}
catch (TargetInvocationException ex)
{
    result["error"] = ex.InnerException?.ToString() ?? ex.ToString();
}
catch (Exception ex)
{
    result["error"] = ex.ToString();
}

Console.WriteLine(JsonSerializer.Serialize(result, new JsonSerializerOptions { WriteIndented = true }));

static object SummarizeRaidData(object? raidData)
{
    if (raidData is null)
    {
        return new { error = "raidData is null" };
    }

    var type = raidData.GetType();
    var heroes = GetEnumerablePropertyItems(raidData, "Heroes");
    var artifacts = GetEnumerablePropertyItems(raidData, "Artifacts");
    var greatHall = type.GetProperty("GreatHall")?.GetValue(raidData);
    var battleResults = GetEnumerablePropertyItems(raidData, "BattleResults");

    return new
    {
        type = type.FullName,
        properties = type.GetProperties(BindingFlags.Public | BindingFlags.Instance).Select(p => p.Name).OrderBy(name => name).ToArray(),
        hero_count = heroes.Count,
        artifact_count = artifacts.Count,
        battle_results_count = battleResults.Count,
        hero_preview = heroes.Take(10).Select(item => ProjectObject(item, 1)).ToArray(),
        artifact_preview = artifacts.Take(10).Select(item => ProjectObject(item, 1)).ToArray(),
        battle_results_preview = battleResults.Take(5).Select(item => ProjectObject(item, 2)).ToArray(),
        great_hall = ProjectObject(greatHall, 1),
    };
}

static object DumpRaidData(object? raidData)
{
    if (raidData is null)
    {
        return new { error = "raidData is null" };
    }

    var type = raidData.GetType();
    var heroes = GetEnumerablePropertyItems(raidData, "Heroes");
    var artifacts = GetEnumerablePropertyItems(raidData, "Artifacts");
    var greatHall = type.GetProperty("GreatHall")?.GetValue(raidData);
    var battleResults = GetEnumerablePropertyItems(raidData, "BattleResults");

    return new
    {
        heroes = heroes.Select(item => ProjectObject(item, 2)).ToArray(),
        artifacts = artifacts.Select(item => ProjectObject(item, 2)).ToArray(),
        battle_results = battleResults.Select(item => ProjectObject(item, 3)).ToArray(),
        great_hall = ProjectObject(greatHall, 2),
    };
}

static List<object?> GetEnumerablePropertyItems(object target, string propertyName)
{
    var value = target.GetType().GetProperty(propertyName)?.GetValue(target);
    if (value is System.Collections.IEnumerable enumerable && value is not string)
    {
        return enumerable.Cast<object?>().ToList();
    }

    return new List<object?>();
}

static object? ProjectObject(object? value, int depth)
{
    if (value is null || depth < 0)
    {
        return value;
    }

    var type = value.GetType();
    if (type.IsPrimitive || value is string || value is decimal || value is DateTime || value is DateTimeOffset || value is Guid || value is Enum)
    {
        return value;
    }

    if (value is System.Collections.IEnumerable enumerable && value is not string)
    {
        return enumerable.Cast<object?>().Take(8).Select(item => ProjectObject(item, depth - 1)).ToArray();
    }

    return type.GetProperties(BindingFlags.Public | BindingFlags.Instance)
        .Where(p => p.CanRead)
        .Take(20)
        .ToDictionary(
            p => p.Name,
            p =>
            {
                try
                {
                    return ProjectObject(p.GetValue(value), depth - 1);
                }
                catch (Exception ex)
                {
                    return $"<error: {ex.Message}>";
                }
            }
        );
}

static object InspectBattleTypes(params Assembly[] assemblies)
{
    return assemblies.ToDictionary(
        asm => asm.GetName().Name ?? "unknown",
        asm => asm.GetTypes()
            .Where(type => type.FullName is not null && (
                type.FullName.Contains("BattleResult") ||
                type.FullName.Contains("HeroStatistics") ||
                type.FullName.Contains("BattleStatistics") ||
                type.FullName.Contains("RoundStatistics") ||
                type.FullName.Contains("FinishBattleInfo") ||
                type.FullName.Contains("DamageDealt")
            ))
            .OrderBy(type => type.FullName)
            .Select(type => new
            {
                type = type.FullName,
                properties = type.GetProperties(BindingFlags.Public | BindingFlags.Instance | BindingFlags.Static)
                    .Select(p => new { name = p.Name, property_type = p.PropertyType.FullName })
                    .ToArray(),
                fields = type.GetFields(BindingFlags.Public | BindingFlags.Instance | BindingFlags.Static)
                    .Select(f => new { name = f.Name, field_type = f.FieldType.FullName })
                    .ToArray(),
                methods = type.GetMethods(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static | BindingFlags.DeclaredOnly)
                    .Where(m => !m.IsSpecialName)
                    .Select(m => new
                    {
                        name = m.Name,
                        is_public = m.IsPublic,
                        is_static = m.IsStatic,
                        parameters = m.GetParameters().Select(p => p.ParameterType.FullName).ToArray(),
                        return_type = m.ReturnType.FullName,
                    })
                    .ToArray(),
            })
            .ToArray()
    );
}

static object InspectBattleLoaders(params Assembly[] assemblies)
{
    return assemblies.ToDictionary(
        asm => asm.GetName().Name ?? "unknown",
        asm => asm.GetTypes()
            .Select(type => new
            {
                type = type,
                methods = type.GetMethods(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static | BindingFlags.DeclaredOnly)
                    .Where(method => method.Name.Contains("LoadBattleResult") || method.Name.Contains("BattleResult"))
                    .Select(method => new
                    {
                        name = method.Name,
                        is_public = method.IsPublic,
                        is_static = method.IsStatic,
                        parameters = method.GetParameters().Select(parameter => parameter.ParameterType.FullName).ToArray(),
                        return_type = method.ReturnType.FullName,
                    })
                    .ToArray(),
            })
            .Where(entry => entry.methods.Length > 0)
            .OrderBy(entry => entry.type.FullName)
            .Select(entry => new
            {
                type = entry.type.FullName,
                methods = entry.methods,
            })
            .ToArray()
    );
}

static object InspectDamageTypes(params Assembly[] assemblies)
{
    return assemblies.ToDictionary(
        asm => asm.GetName().Name ?? "unknown",
        asm => asm.GetTypes()
            .Select(type => new
            {
                type = type.FullName,
                properties = type.GetProperties(BindingFlags.Public | BindingFlags.Instance | BindingFlags.Static)
                    .Where(property => property.Name.Contains("Damage") || property.PropertyType.FullName?.Contains("BattleStats") == true)
                    .Select(property => new { name = property.Name, property_type = property.PropertyType.FullName })
                    .ToArray(),
                methods = type.GetMethods(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static | BindingFlags.DeclaredOnly)
                    .Where(method => method.Name.Contains("Damage"))
                    .Select(method => new
                    {
                        name = method.Name,
                        return_type = method.ReturnType.FullName,
                        parameters = method.GetParameters().Select(parameter => parameter.ParameterType.FullName).ToArray(),
                    })
                    .ToArray(),
            })
            .Where(entry => entry.properties.Length > 0 || entry.methods.Length > 0)
            .OrderBy(entry => entry.type)
            .ToArray()
    );
}
