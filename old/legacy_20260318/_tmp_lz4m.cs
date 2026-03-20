using System;
using System.Linq;
using System.Reflection;
using MessagePack;
foreach (var m in typeof(MessagePackSerializer).GetMethods(BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Static).Where(m => m.Name.Contains("LZ4") || m.Name.Contains("Compression") || m.Name.Contains("Deserialize") || m.Name.Contains("Serialize")).OrderBy(m => m.Name)) {
  if (m.Name.Contains("LZ4") || m.Name.Contains("Compression") || (m.Name=="Deserialize" && !m.IsGenericMethodDefinition))
    Console.WriteLine(m.ToString());
}
