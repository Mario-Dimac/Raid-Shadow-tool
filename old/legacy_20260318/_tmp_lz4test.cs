using System;
using System.Buffers;
using System.Linq;
using System.Reflection;
using MessagePack;
var data = System.IO.File.ReadAllBytes(@"d:\Programmi python\CB Forge\input\battle_result_captures\2026-03-14T19-57-15+00-00_7190f506-a289-4faf-a0ab-521b2198e8c9_ab97720910.bin");
var reader = new MessagePackReader(new ReadOnlySequence<byte>(data));
Console.WriteLine($"type={reader.NextMessagePackType}");
var count=reader.ReadArrayHeader();
Console.WriteLine($"count={count}");
var ext=reader.ReadExtensionFormat();
Console.WriteLine($"extType={ext.TypeCode} len={ext.Data.Length}");
var sr = new MessagePackReader(new ReadOnlySequence<byte>(ext.Data.ToArray()));
var lengths = new System.Collections.Generic.List<int>();
while(!sr.End){ lengths.Add((int)sr.ReadInt32()); }
Console.WriteLine("lengths=" + string.Join(",", lengths));
var codecType = typeof(MessagePackSerializer).Assembly.GetType("MessagePack.LZ4.LZ4Codec", true)!;
var method = codecType.GetMethod("Decode", BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Static, null, new[]{typeof(ReadOnlySpan<byte>), typeof(Span<byte>)}, null)!;
var decoder = method.CreateDelegate<Lz4DecodeDelegate>();
for(int i=0;i<lengths.Count;i++){
  var block = reader.ReadBytes()?.ToArray() ?? Array.Empty<byte>();
  var output = new byte[lengths[i]];
  try {
    var written = decoder(block, output);
    Console.WriteLine($"block{i} compressed={block.Length} target={lengths[i]} written={written} head={Convert.ToHexString(output.AsSpan(0, Math.Min(24, written)))}");
  } catch(Exception ex) {
    Console.WriteLine($"block{i} ex={ex}");
  }
}
delegate int Lz4DecodeDelegate(ReadOnlySpan<byte> input, Span<byte> output);
