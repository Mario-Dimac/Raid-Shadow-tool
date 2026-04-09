using System.Diagnostics;
using System.Reflection;
using System.Text.Json;
using Common.Events;
using HellHades.ArtifactExtractor.Helper;
using HellHades.ArtifactExtractor.LiveUpdates;
using HellHades.ArtifactExtractor.Models.Events;
using HellHades.ArtifactExtractor.Models.Reader;
using HellHades.ArtifactExtractor.Models.Reader.Windows;
using HellHades.ArtifactExtractor.RaidReader;
using Microsoft.Extensions.Logging.Abstractions;

var hhRoot = Path.Combine(
    Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
    "HellHades Artifact Extractor"
);

AppDomain.CurrentDomain.AssemblyResolve += (_, eventArgs) =>
{
    var name = new System.Reflection.AssemblyName(eventArgs.Name).Name;
    if (string.IsNullOrWhiteSpace(name))
    {
        return null;
    }
    var candidate = Path.Combine(hhRoot, name + ".dll");
    return File.Exists(candidate) ? System.Reflection.Assembly.LoadFrom(candidate) : null;
};

var command = args.FirstOrDefault()?.Trim().ToLowerInvariant() ?? "status";
try
{
    var bridge = new LocalBridge();
    object result = command switch
    {
        "status" => bridge.BuildStatusPayload(),
        "equip" => bridge.Equip(
            heroId: ParseRequiredInt(args, 1, "hero_id"),
            artifactIds: ParseArtifactIds(args, 2)
        ),
        "sell" => bridge.Sell(
            artifactIds: ParseArtifactIds(args, 1)
        ),
        _ => throw new InvalidOperationException($"Comando non supportato: {command}"),
    };
    Console.WriteLine(JsonSerializer.Serialize(result, new JsonSerializerOptions { WriteIndented = true }));
    return 0;
}
catch (Exception exc)
{
    Console.WriteLine(
        JsonSerializer.Serialize(
            new
            {
                ok = false,
                error = exc.Message,
                type = exc.GetType().FullName,
            },
            new JsonSerializerOptions { WriteIndented = true }
        )
    );
    return 1;
}

static int ParseRequiredInt(string[] args, int index, string label)
{
    if (args.Length <= index || !int.TryParse(args[index], out var value))
    {
        throw new InvalidOperationException($"{label} mancante o non valido.");
    }
    return value;
}

static int[] ParseArtifactIds(string[] args, int index)
{
    if (args.Length <= index)
    {
        throw new InvalidOperationException("artifact_ids mancanti.");
    }
    var ids = args[index]
        .Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
        .Select(text => int.TryParse(text, out var value) ? value : 0)
        .Where(value => value > 0)
        .ToArray();
    if (ids.Length == 0)
    {
        throw new InvalidOperationException("artifact_ids mancanti.");
    }
    return ids;
}

sealed class LocalBridge
{
    private readonly WindowsProcessMemory _processMemory = new();
    private readonly RaidMemoryReader _raidMemoryReader;
    private readonly WindowsHelper _helper;
    private readonly RaidProcessReader _raidProcessReader;
    private readonly HelperHandler _helperHandler;
    private readonly NoopEventPublisher _eventPublisher = new();
    private readonly string[] _readerNames;

    public LocalBridge()
    {
        _raidMemoryReader = new RaidMemoryReader(_processMemory);
        _helper = new WindowsHelper(_processMemory);
        var raidReaders = DiscoverRaidReaders();
        _readerNames = raidReaders.Select(static reader => reader.GetType().Name).ToArray();
        _raidProcessReader = new RaidProcessReader(
            new UpdateRaidDataRequestHandlerOptions(),
            raidReaders,
            _raidMemoryReader,
            NullLogger.Instance,
            _helper
        );
        _helperHandler = new HelperHandler(_raidProcessReader, _eventPublisher, NullLogger.Instance);
    }

    public object BuildStatusPayload()
    {
        var raidProcess = RefreshProcess();
        return new
        {
            ok = true,
            raid_running = _raidProcessReader.IsRaidRunning,
            raid_process_id = raidProcess?.Id ?? 0,
            raid_process_name = raidProcess?.ProcessName ?? "",
            helper_capable = _helper.HelperCapable,
            helper_loaded = _helper.HelperIsLoaded,
            restart_required = _helper.RestartRequired,
            process_memory_ready = _processMemory.IsReady,
            process_memory_pid = _processMemory.ProcessId,
            reader_candidates = _readerNames,
            published_events = _eventPublisher.PublishedEvents,
        };
    }

    public object Equip(int heroId, int[] artifactIds)
    {
        var raidProcess = RefreshProcess();
        var payload = new EquipArtifactsEvent
        {
            HeroId = heroId,
            ArtifactIds = artifactIds,
        };
        _helperHandler.HandleAsync(payload, CancellationToken.None).GetAwaiter().GetResult();
        return new
        {
            ok = true,
            action = "equip",
            hero_id = heroId,
            artifact_ids = artifactIds,
            raid_running = _raidProcessReader.IsRaidRunning,
            raid_process_id = raidProcess?.Id ?? 0,
            helper_capable = _helper.HelperCapable,
            helper_loaded = _helper.HelperIsLoaded,
            restart_required = _helper.RestartRequired,
            reader_candidates = _readerNames,
            published_events = _eventPublisher.PublishedEvents,
        };
    }

    public object Sell(int[] artifactIds)
    {
        var raidProcess = RefreshProcess();
        var payload = new SellArtifactsEvent
        {
            ArtifactIds = artifactIds,
        };
        _helperHandler.HandleAsync(payload, CancellationToken.None).GetAwaiter().GetResult();
        return new
        {
            ok = true,
            action = "sell",
            artifact_ids = artifactIds,
            raid_running = _raidProcessReader.IsRaidRunning,
            raid_process_id = raidProcess?.Id ?? 0,
            helper_capable = _helper.HelperCapable,
            helper_loaded = _helper.HelperIsLoaded,
            restart_required = _helper.RestartRequired,
            reader_candidates = _readerNames,
            published_events = _eventPublisher.PublishedEvents,
        };
    }

    private Process RefreshProcess()
    {
        var process = _raidProcessReader.RaidProcess;
        if (process is not null)
        {
            _processMemory.SetProcess(process);
            _raidMemoryReader.SetProcess(process);
            return process;
        }

        process = Process.GetProcesses()
            .FirstOrDefault(item => item.ProcessName.Equals("Raid", StringComparison.OrdinalIgnoreCase));
        if (process is not null)
        {
            _processMemory.SetProcess(process);
            _raidMemoryReader.SetProcess(process);
            return process;
        }

        throw new InvalidOperationException("Raid: Shadow Legends non risulta in esecuzione.");
    }

    private static IRaidReader[] DiscoverRaidReaders()
    {
        var interfaceType = typeof(IRaidReader);
        var assembly = interfaceType.Assembly;
        var readers = assembly
            .GetTypes()
            .Where(type =>
                type is { IsAbstract: false, IsInterface: false }
                && interfaceType.IsAssignableFrom(type)
                && type.Name.StartsWith("RaidReader", StringComparison.OrdinalIgnoreCase)
            )
            .OrderByDescending(type => ExtractTrailingNumber(type.Name))
            .Select(static type => (IRaidReader?)Activator.CreateInstance(type))
            .Where(static reader => reader is not null)
            .Cast<IRaidReader>()
            .ToArray();
        if (readers.Length == 0)
        {
            throw new InvalidOperationException(
                $"Nessun RaidReader HH disponibile in {assembly.FullName}."
            );
        }
        return readers;
    }

    private static int ExtractTrailingNumber(string value)
    {
        var digits = new string(value.Reverse().TakeWhile(char.IsDigit).Reverse().ToArray());
        return int.TryParse(digits, out var parsed) ? parsed : 0;
    }
}

sealed class NoopEventPublisher : IEventPublisher
{
    public List<object?> PublishedEvents { get; } = [];

    public Task PublishAsync<TEvent>(TEvent @event, CancellationToken cancellationToken)
    {
        PublishedEvents.Add(@event);
        return Task.CompletedTask;
    }
}
