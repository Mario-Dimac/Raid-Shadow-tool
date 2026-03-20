using System;
using System.Linq;
using System.Reflection;
using MessagePack;
var t = typeof(MessagePackSerializer).GetNestedTypes(BindingFlags.NonPublic | BindingFlags.Public).FirstOrDefault(x => x.Name.Contains("LZ4Transform"));
Console.WriteLine(t?.FullName ?? "not found");
if (t != null) {
  foreach (var m in t.GetMethods(BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Static|BindingFlags.Instance|BindingFlags.DeclaredOnly)) {
    Console.WriteLine(m.ToString());
  }
}
Console.WriteLine(typeof(MessagePack.ReservedExtensionTypeCodes).FullName);
foreach (var f in typeof(MessagePack.ReservedExtensionTypeCodes).GetFields(BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Static)) {
  Console.WriteLine($"{f.Name}={f.GetRawConstantValue()}");
}
