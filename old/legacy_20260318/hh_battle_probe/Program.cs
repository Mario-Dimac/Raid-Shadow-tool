using System.Buffers;
using System.Reflection;
using System.Text.Json;
using MessagePack;
using MessagePack.Formatters;

var summaryMode = args.Any(arg => string.Equals(arg, "--summary", StringComparison.OrdinalIgnoreCase));
var inputPath = args.FirstOrDefault(arg => !string.Equals(arg, "--summary", StringComparison.OrdinalIgnoreCase));

if (string.IsNullOrWhiteSpace(inputPath))
{
    Console.Error.WriteLine("Usage: hh_battle_probe [--summary] <path-to-battleResults>");
    Environment.Exit(1);
}

var path = Path.GetFullPath(inputPath);
if (!File.Exists(path))
{
    Console.Error.WriteLine($"File not found: {path}");
    Environment.Exit(2);
}

var data = File.ReadAllBytes(path);
var decoded = DecodePayload(data);
var decompression = TryDecompressLz4BlockArray(data);
var payload = new Dictionary<string, object?>
{
    ["path"] = path,
    ["size"] = data.Length,
    ["lz4_debug"] = decompression.Debug,
};

payload["decoded"] = summaryMode ? SummarizeDecodedPayload(decoded) : decoded;
if (!summaryMode)
{
    payload["typed_decoded"] = TryDecodeTypedBattleResult(data);
}

if (decompression.Data is not null)
{
    payload["lz4_uncompressed_size"] = decompression.Data.Length;
    var decodedUncompressed = DecodePayload(decompression.Data);
    payload["decoded_uncompressed"] = summaryMode ? SummarizeDecodedPayload(decodedUncompressed) : decodedUncompressed;
    if (!summaryMode)
    {
        payload["typed_decoded_uncompressed"] = TryDecodeTypedBattleResult(decompression.Data);
    }
}

Console.WriteLine(JsonSerializer.Serialize(payload, new JsonSerializerOptions
{
    WriteIndented = true,
}));

static object? DecodePayload(byte[] data)
{
    return DecodeBestEffort(data, 0);
}

static object? SummarizeDecodedPayload(object? payload)
{
    if (payload is not Dictionary<string, object?> map)
    {
        return payload;
    }

    if (IsDecodeWrapper(map))
    {
        return new Dictionary<string, object?>
        {
            ["decode_offset"] = map.GetValueOrDefault("decode_offset"),
            ["remaining_bytes"] = map.GetValueOrDefault("remaining_bytes"),
            ["decoded"] = SummarizeDecodedPayload(map.GetValueOrDefault("decoded")),
        };
    }

    var summary = new Dictionary<string, object?>();
    CopyIfPresent(map, summary, "i");
    CopyIfPresent(map, summary, "c");

    if (map.TryGetValue("p", out var setupSection))
    {
        var setupHeroes = ProjectPathRows(setupSection, new[] { "f", "h" }, SummarizeSetupHero);
        if (setupHeroes is not null)
        {
            summary["p"] = WrapPath("f", "h", setupHeroes);
        }
    }

    if (map.TryGetValue("s", out var resultSection))
    {
        var resultHeroes = ProjectPathRows(resultSection, new[] { "f", "h" }, SummarizeResultHero);
        if (resultHeroes is not null)
        {
            summary["s"] = WrapPath("f", "h", resultHeroes);
        }
    }

    return summary.Count > 0 ? summary : map;
}

static bool IsDecodeWrapper(Dictionary<string, object?> map)
{
    return map.ContainsKey("decoded") && map.Keys.All(key => key is "decode_offset" or "remaining_bytes" or "decoded");
}

static void CopyIfPresent(Dictionary<string, object?> source, Dictionary<string, object?> target, string key)
{
    if (source.TryGetValue(key, out var value))
    {
        target[key] = value;
    }
}

static object? ProjectPathRows(object? root, string[] path, Func<Dictionary<string, object?>, object?> projector)
{
    var current = root;
    foreach (var part in path)
    {
        if (current is not Dictionary<string, object?> currentMap || !currentMap.TryGetValue(part, out current))
        {
            return null;
        }
    }

    if (current is not List<object?> rows)
    {
        return null;
    }

    return rows
        .OfType<Dictionary<string, object?>>()
        .Select(projector)
        .Where(item => item is not null)
        .ToList();
}

static Dictionary<string, object?> WrapPath(string outerKey, string innerKey, object? value)
{
    return new Dictionary<string, object?>
    {
        [outerKey] = new Dictionary<string, object?>
        {
            [innerKey] = value,
        },
    };
}

static object? SummarizeSetupHero(Dictionary<string, object?> row)
{
    var summary = new Dictionary<string, object?>();
    foreach (var key in new[] { "d", "t", "u", "i", "h", "g", "l" })
    {
        CopyIfPresent(row, summary, key);
    }
    return summary.Count > 0 ? summary : null;
}

static object? SummarizeResultHero(Dictionary<string, object?> row)
{
    var summary = new Dictionary<string, object?>();
    foreach (var key in new[] { "i", "d", "t", "u", "h", "dt", "s", "da" })
    {
        CopyIfPresent(row, summary, key);
    }

    if (row.TryGetValue("ad", out var additionalDamage) && additionalDamage is Dictionary<string, object?> damageMap)
    {
        var reducedDamageMap = new Dictionary<string, object?>();
        CopyIfPresent(damageMap, reducedDamageMap, "2004");
        if (reducedDamageMap.Count > 0)
        {
            summary["ad"] = reducedDamageMap;
        }
    }

    return summary.Count > 0 ? summary : null;
}

static Lz4DecompressionResult TryDecompressLz4BlockArray(byte[] data)
{
    try
    {
        var reader = new MessagePackReader(new ReadOnlySequence<byte>(data));
        if (reader.NextMessagePackType != MessagePackType.Array)
        {
            return new Lz4DecompressionResult(null, "root is not array");
        }

        var itemCount = reader.ReadArrayHeader();
        if (itemCount < 2 || reader.NextMessagePackType != MessagePackType.Extension)
        {
            return new Lz4DecompressionResult(null, $"unexpected header count={itemCount} type={reader.NextMessagePackType}");
        }

        var extension = reader.ReadExtensionFormat();
        if (extension.TypeCode != ReservedExtensionTypeCodes.Lz4BlockArray)
        {
            return new Lz4DecompressionResult(null, $"extension type {extension.TypeCode} is not Lz4BlockArray");
        }

        var blockLengths = ReadBlockLengths(extension.Data.ToArray());
        if (blockLengths.Count == 0 || blockLengths.Count != itemCount - 1)
        {
            return new Lz4DecompressionResult(null, $"block length count mismatch lengths={blockLengths.Count} items={itemCount}");
        }

        var totalLength = blockLengths.Sum();
        var output = new byte[totalLength];
        var outputOffset = 0;

        foreach (var blockLength in blockLengths)
        {
            var compressedBlock = reader.ReadBytes()?.ToArray() ?? Array.Empty<byte>();
            var written = DecodeLz4Block(compressedBlock, output.AsSpan(outputOffset, blockLength));
            if (written != blockLength)
            {
                return new Lz4DecompressionResult(null, $"block decode mismatch expected={blockLength} written={written}");
            }

            outputOffset += written;
        }

        return new Lz4DecompressionResult(output, $"ok:{string.Join(",", blockLengths)}");
    }
    catch (Exception ex)
    {
        return new Lz4DecompressionResult(null, ex.ToString());
    }
}

static List<int> ReadBlockLengths(byte[] data)
{
    var lengths = new List<int>();
    var reader = new MessagePackReader(new ReadOnlySequence<byte>(data));
    while (!reader.End)
    {
        lengths.Add(reader.ReadInt32());
    }

    return lengths;
}

static int DecodeLz4Block(byte[] compressedBlock, Span<byte> destination)
{
    var codecType = typeof(MessagePackSerializer).Assembly.GetType("MessagePack.LZ4.LZ4Codec", throwOnError: true)!;
    var decodeMethod = codecType.GetMethod(
        "Decode",
        BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static,
        binder: null,
        types: new[] { typeof(ReadOnlySpan<byte>), typeof(Span<byte>) },
        modifiers: null
    )!;
    var decoder = decodeMethod.CreateDelegate<Lz4DecodeDelegate>();
    return decoder(compressedBlock, destination);
}

static object? ReadValue(ref MessagePackReader reader, int depth)
{
    if (depth > 64)
    {
        return "<max-depth>";
    }

    switch (reader.NextMessagePackType)
    {
        case MessagePackType.Nil:
            reader.ReadNil();
            return null;
        case MessagePackType.Boolean:
            return reader.ReadBoolean();
        case MessagePackType.Integer:
            return ReadInteger(ref reader);
        case MessagePackType.Float:
            return reader.ReadDouble();
        case MessagePackType.String:
            return reader.ReadString();
        case MessagePackType.Binary:
            return ReadBinary(ref reader, depth);
        case MessagePackType.Array:
            return ReadArray(ref reader, depth);
        case MessagePackType.Map:
            return ReadMap(ref reader, depth);
        case MessagePackType.Extension:
            return ReadExtension(ref reader, depth);
        default:
            return $"<unsupported:{reader.NextMessagePackType}>";
    }
}

static object ReadInteger(ref MessagePackReader reader)
{
    try
    {
        return reader.ReadInt64();
    }
    catch
    {
        return reader.ReadUInt64();
    }
}

static object ReadBinary(ref MessagePackReader reader, int depth)
{
    var data = reader.ReadBytes()?.ToArray() ?? Array.Empty<byte>();
    var payload = new Dictionary<string, object?>
    {
        ["binary_length"] = data.Length,
        ["hex_preview"] = Convert.ToHexString(data.AsSpan(0, Math.Min(32, data.Length))),
    };
    if (TryDecodeNested(data, depth + 1, out var nested))
    {
        payload["decoded"] = nested;
    }
    return payload;
}

static List<object?> ReadArray(ref MessagePackReader reader, int depth)
{
    var length = reader.ReadArrayHeader();
    var items = new List<object?>(length);
    for (var index = 0; index < length; index++)
    {
        items.Add(ReadValue(ref reader, depth + 1));
    }
    return items;
}

static Dictionary<string, object?> ReadMap(ref MessagePackReader reader, int depth)
{
    var length = reader.ReadMapHeader();
    var items = new Dictionary<string, object?>(length);
    for (var index = 0; index < length; index++)
    {
        var key = ReadValue(ref reader, depth + 1);
        var value = ReadValue(ref reader, depth + 1);
        var propertyName = key switch
        {
            null => "null",
            string text => text,
            _ => JsonSerializer.Serialize(key),
        };
        if (items.ContainsKey(propertyName))
        {
            propertyName = $"{propertyName}#{index}";
        }
        items[propertyName] = value;
    }
    return items;
}

static object ReadExtension(ref MessagePackReader reader, int depth)
{
    var ext = reader.ReadExtensionFormat();
    var data = ext.Data.ToArray();
    var payload = new Dictionary<string, object?>
    {
        ["ext_type"] = ext.TypeCode,
        ["length"] = data.Length,
        ["hex_preview"] = Convert.ToHexString(data.AsSpan(0, Math.Min(32, data.Length))),
    };
    if (TryDecodeNested(data, depth + 1, out var nested))
    {
        payload["decoded"] = nested;
    }
    return payload;
}

static bool TryDecodeNested(byte[] data, int depth, out object? nested)
{
    nested = null;
    if (data.Length == 0)
    {
        return false;
    }

    var best = DecodeBestEffort(data, depth);
    if (best is null)
    {
        return false;
    }

    nested = best;
    return true;
}

static object? DecodeBestEffort(byte[] data, int depth)
{
    DecodeCandidate? best = null;
    var maxOffset = Math.Min(8, Math.Max(0, data.Length - 1));
    for (var offset = 0; offset <= maxOffset; offset++)
    {
        if (!TryDecodeAtOffset(data, offset, depth + 1, out var candidate))
        {
            continue;
        }

        if (best is null || candidate.Score > best.Value.Score)
        {
            best = candidate;
        }
    }

    if (best is null)
    {
        return null;
    }

    var selected = best.Value;
    if (selected.Offset == 0 && selected.RemainingBytes == 0)
    {
        return selected.Payload;
    }

    return new Dictionary<string, object?>
    {
        ["decode_offset"] = selected.Offset,
        ["remaining_bytes"] = selected.RemainingBytes,
        ["decoded"] = selected.Payload,
    };
}

static bool TryDecodeAtOffset(byte[] data, int offset, int depth, out DecodeCandidate candidate)
{
    candidate = default;
    try
    {
        var slice = data.AsMemory(offset).ToArray();
        var reader = new MessagePackReader(new ReadOnlySequence<byte>(slice));
        var values = new List<object?>();
        while (!reader.End)
        {
            values.Add(ReadValue(ref reader, depth + 1));
        }

        var payload = values.Count == 1 ? values[0] : values;
        var remainingBytes = slice.Length - (int)reader.Consumed;
        candidate = new DecodeCandidate(
            offset,
            remainingBytes,
            ScorePayload(payload, offset, remainingBytes),
            payload
        );
        return true;
    }
    catch
    {
        return false;
    }
}

static int ScorePayload(object? payload, int offset, int remainingBytes)
{
    var structureScore = ScoreStructure(payload, 0);
    var remainingPenalty = Math.Min(remainingBytes, 1024);
    return structureScore - remainingPenalty - (offset * 4);
}

static int ScoreStructure(object? payload, int depth)
{
    if (payload is null || depth > 8)
    {
        return 0;
    }

    return payload switch
    {
        Dictionary<string, object?> map => 200 + (map.Count * 15) + map.Values.Sum(value => ScoreStructure(value, depth + 1)),
        List<object?> list => 150 + (list.Count * 10) + list.Take(8).Sum(value => ScoreStructure(value, depth + 1)),
        string text => Math.Min(24, text.Length),
        bool => 2,
        byte or sbyte or short or ushort or int or uint or long or ulong or float or double or decimal => 3,
        _ => 1,
    };
}

static object? TryDecodeTypedBattleResult(byte[] data)
{
    try
    {
        var baseDir = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", ".."));
        var vendorDir = Path.Combine(baseDir, "vendor", "hellhades_reference");
        var modelsAssembly = Assembly.LoadFrom(Path.Combine(vendorDir, "HellHades.ArtifactExtractor.Models.dll"));
        var extractorAssembly = Assembly.LoadFrom(Path.Combine(vendorDir, "HellHades.ArtifactExtractor.dll"));
        var resolverType = modelsAssembly.GetType("MessagePack.GeneratedMessagePackResolver", throwOnError: false);
        var resolver = resolverType?.GetProperty("Instance", BindingFlags.Public | BindingFlags.Static)?.GetValue(null) as IFormatterResolver;
        var options = resolver is null
            ? MessagePackSerializerOptions.Standard
            : MessagePackSerializerOptions.Standard.WithResolver(resolver);

        var candidates = new List<(string Name, Type Type)>();
        var battleResultType = modelsAssembly.GetType("HellHades.ArtifactExtractor.Models.BattleResult", throwOnError: false);
        if (battleResultType is not null)
        {
            candidates.Add(("BattleResult[]", battleResultType.MakeArrayType()));
            candidates.Add(("BattleResult", battleResultType));
            candidates.Add(("List<BattleResult>", typeof(List<>).MakeGenericType(battleResultType)));
        }

        foreach (var assembly in new[] { extractorAssembly, modelsAssembly })
        {
            var eventType = assembly.GetType("HellHades.ArtifactExtractor.Models.Events.BattleResultEvent", throwOnError: false);
            if (eventType is not null)
            {
                candidates.Add(("BattleResultEvent", eventType));
            }
        }

        var attempts = new List<object?>();
        foreach (var candidate in candidates)
        {
            if (!TryDeserialize(candidate.Type, data, options, out var value, out var error))
            {
                attempts.Add(new Dictionary<string, object?>
                {
                    ["type"] = candidate.Name,
                    ["ok"] = false,
                    ["error"] = error,
                });
                continue;
            }

            attempts.Add(new Dictionary<string, object?>
            {
                ["type"] = candidate.Name,
                ["ok"] = true,
                ["summary"] = ProjectObject(value, 4),
            });
        }

        return attempts;
    }
    catch (Exception ex)
    {
        return new Dictionary<string, object?>
        {
            ["error"] = ex.ToString(),
        };
    }
}

static bool TryDeserialize(Type targetType, byte[] data, MessagePackSerializerOptions options, out object? value, out string error)
{
    value = null;
    error = "";

    var deserializeMethod = typeof(MessagePackSerializer)
        .GetMethods(BindingFlags.Public | BindingFlags.Static)
        .FirstOrDefault(method =>
            method.Name == "Deserialize" &&
            method.IsGenericMethodDefinition &&
            method.GetParameters().Length >= 2 &&
            typeof(Stream).IsAssignableFrom(method.GetParameters()[0].ParameterType));

    if (deserializeMethod is null)
    {
        error = "MessagePackSerializer.Deserialize(Stream, ...) generic overload not found";
        return false;
    }

    var genericMethod = deserializeMethod.MakeGenericMethod(targetType);
    var parameters = genericMethod.GetParameters();

    try
    {
        using var stream = new MemoryStream(data, writable: false);
        object?[] args = parameters.Length switch
        {
            1 => new object?[] { stream },
            2 => new object?[] { stream, options },
            3 => new object?[] { stream, options, CancellationToken.None },
            _ => BuildDeserializeArgs(parameters, stream, options),
        };
        value = genericMethod.Invoke(null, args);
        return true;
    }
    catch (TargetInvocationException ex)
    {
        error = ex.InnerException?.Message ?? ex.Message;
        return false;
    }
    catch (Exception ex)
    {
        error = ex.Message;
        return false;
    }
}

static object?[] BuildDeserializeArgs(ParameterInfo[] parameters, MemoryStream stream, MessagePackSerializerOptions options)
{
    var args = new object?[parameters.Length];
    for (var index = 0; index < parameters.Length; index++)
    {
        var parameterType = parameters[index].ParameterType;
        if (typeof(Stream).IsAssignableFrom(parameterType))
        {
            args[index] = stream;
        }
        else if (parameterType == typeof(MessagePackSerializerOptions))
        {
            args[index] = options;
        }
        else if (parameterType == typeof(CancellationToken))
        {
            args[index] = CancellationToken.None;
        }
        else
        {
            args[index] = parameterType.IsValueType ? Activator.CreateInstance(parameterType) : null;
        }
    }

    return args;
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

    if (value is System.Collections.IDictionary dictionary)
    {
        var projected = new Dictionary<string, object?>();
        foreach (System.Collections.DictionaryEntry entry in dictionary)
        {
            projected[entry.Key?.ToString() ?? "null"] = ProjectObject(entry.Value, depth - 1);
        }
        return projected;
    }

    if (value is System.Collections.IEnumerable enumerable && value is not string)
    {
        return enumerable.Cast<object?>().Take(20).Select(item => ProjectObject(item, depth - 1)).ToArray();
    }

    return type.GetProperties(BindingFlags.Public | BindingFlags.Instance)
        .Where(property => property.CanRead)
        .Take(25)
        .ToDictionary(
            property => property.Name,
            property =>
            {
                try
                {
                    return ProjectObject(property.GetValue(value), depth - 1);
                }
                catch (Exception ex)
                {
                    return $"<error: {ex.Message}>";
                }
            }
        );
}

readonly record struct DecodeCandidate(int Offset, int RemainingBytes, int Score, object? Payload);
readonly record struct Lz4DecompressionResult(byte[]? Data, string Debug);
delegate int Lz4DecodeDelegate(ReadOnlySpan<byte> input, Span<byte> output);
