using System.Reflection;
using System.Runtime.Loader;
var baseDir = @"d:\Programmi python\CB Forge";
var vendorDir = System.IO.Path.Combine(baseDir, "vendor", "hellhades_reference");
AssemblyLoadContext.Default.Resolving += (_, assemblyName) => {
    var candidate = System.IO.Path.Combine(vendorDir, $"{assemblyName.Name}.dll");
    return System.IO.File.Exists(candidate) ? AssemblyLoadContext.Default.LoadFromAssemblyPath(candidate) : null;
};
var asmPaths = new[]{
    System.IO.Path.Combine(vendorDir, "HellHades.ArtifactExtractor.Models.Reader.dll"),
    System.IO.Path.Combine(vendorDir, "HellHades.ArtifactExtractor.Models.dll"),
    System.IO.Path.Combine(vendorDir, "HellHades.ArtifactExtractor.dll")
};
foreach (var asmPath in asmPaths) {
    var asm = AssemblyLoadContext.Default.LoadFromAssemblyPath(asmPath);
    System.Console.WriteLine($"## {System.IO.Path.GetFileName(asmPath)}");
    foreach (var type in asm.GetTypes().Where(t => t.FullName != null && (t.FullName.Contains("Battle") || t.FullName.Contains("Damage") || t.FullName.Contains("Fight"))).OrderBy(t => t.FullName)) {
        System.Console.WriteLine(type.FullName);
        foreach (var prop in type.GetProperties(BindingFlags.Public|BindingFlags.Instance|BindingFlags.Static).Take(15)) {
            System.Console.WriteLine($"  P {prop.PropertyType.Name} {prop.Name}");
        }
        foreach (var field in type.GetFields(BindingFlags.Public|BindingFlags.Instance|BindingFlags.Static).Take(15)) {
            System.Console.WriteLine($"  F {field.FieldType.Name} {field.Name}");
        }
    }
}
