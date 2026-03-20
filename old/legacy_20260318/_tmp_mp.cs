using System.Reflection;
using MessagePack;
foreach (var t in typeof(MessagePackSerializer).Assembly.GetTypes().Where(t => t.FullName != null && (t.FullName.Contains("LZ4") || t.FullName.Contains("Lz4") || t.FullName.Contains("Compression") || t.FullName.Contains("ReservedExtension"))).OrderBy(t => t.FullName)) {
  System.Console.WriteLine(t.FullName);
  foreach (var m in t.GetMethods(BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Static|BindingFlags.Instance|BindingFlags.DeclaredOnly).Where(m => m.Name.Contains("LZ4") || m.Name.Contains("Lz4") || m.Name.Contains("Compression") || m.Name.Contains("Extension") || m.Name.Contains("Decode") || m.Name.Contains("Decompress")).Take(20)) {
    System.Console.WriteLine("  " + m);
  }
}
