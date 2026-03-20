using System;
using System.IO;
using MessagePack;
var data = File.ReadAllBytes(@"d:\Programmi python\CB Forge\input\battle_result_captures\2026-03-14T19-57-15+00-00_7190f506-a289-4faf-a0ab-521b2198e8c9_ab97720910.bin");
try {
  Console.WriteLine(MessagePackSerializer.ConvertToJson(data));
} catch (Exception ex) {
  Console.WriteLine(ex.ToString());
}
