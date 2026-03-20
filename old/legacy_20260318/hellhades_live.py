from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import Request, urlopen

try:
    import websockets
except ModuleNotFoundError:
    websockets = None


RECORD_SEPARATOR = "\x1e"
DEFAULT_BASE_URL = "https://raidoptimiser.hellhades.com"
EDGE_LEVELDB_DIR = Path.home() / "AppData" / "Local" / "Microsoft" / "Edge" / "User Data" / "Default" / "Local Storage" / "leveldb"
JWT_PATTERN = re.compile(r"(eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)")


class HellHadesEquipError(RuntimeError):
    pass


def normalize_access_token(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if "#token=" in raw:
        fragment = raw.split("#", 1)[1]
        return parse_qs(fragment).get("token", [""])[0].strip()
    if "access_token=" in raw:
        parsed = urlparse(raw)
        from_query = parse_qs(parsed.query).get("access_token", [""])[0].strip()
        if from_query:
            return from_query
        from_fragment = parse_qs(parsed.fragment).get("access_token", [""])[0].strip()
        if from_fragment:
            return from_fragment
    return raw


def discover_access_token_from_edge(leveldb_dir: Path = EDGE_LEVELDB_DIR) -> str:
    if not leveldb_dir.exists():
        return ""

    candidates = sorted(
        [path for path in leveldb_dir.iterdir() if path.suffix.lower() in {".ldb", ".log"}],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in candidates[:8]:
        token = _extract_access_token_from_leveldb_file(path)
        if token:
            return token
    return ""


def _extract_access_token_from_leveldb_file(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except OSError:
        return ""
    if b"raidoptimiser.hellhades.com" not in raw or b"access_token" not in raw:
        return ""
    text = raw.decode("latin-1", errors="ignore")
    matches = JWT_PATTERN.findall(text)
    if not matches:
        return ""
    return matches[-1].strip()


def equip_artifacts_live(
    hero_id: str,
    artifact_ids: Iterable[str],
    access_token: Optional[str] = None,
    base_url: str = DEFAULT_BASE_URL,
    timeout_seconds: float = 10.0,
) -> Dict[str, Any]:
    token = normalize_access_token(access_token or os.getenv("HELLHADES_ACCESS_TOKEN") or "")
    if not token:
        token = discover_access_token_from_edge()
    normalized_hero_id = str(hero_id).strip()
    normalized_artifact_ids = [str(item).strip() for item in artifact_ids if str(item).strip()]

    if not token:
        raise ValueError("token HellHades mancante")
    if not normalized_hero_id:
        raise ValueError("hero_id mancante")
    if not normalized_artifact_ids:
        raise ValueError("artifact_ids mancanti")

    payload_hero_id = _coerce_id(normalized_hero_id)
    payload_artifact_ids = [_coerce_id(item) for item in normalized_artifact_ids]

    if websockets is None:
        return _equip_artifacts_live_via_powershell(
            hero_id=payload_hero_id,
            artifact_ids=payload_artifact_ids,
            access_token=token,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
        )

    return asyncio.run(
        _equip_artifacts_live_async(
            hero_id=payload_hero_id,
            artifact_ids=payload_artifact_ids,
            access_token=token,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
        )
    )


async def _equip_artifacts_live_async(
    hero_id: Any,
    artifact_ids: List[Any],
    access_token: str,
    base_url: str,
    timeout_seconds: float,
) -> Dict[str, Any]:
    connection_token = _negotiate_connection(base_url=base_url, access_token=access_token, timeout_seconds=timeout_seconds)
    websocket_url = _build_websocket_url(base_url=base_url, connection_token=connection_token, access_token=access_token)
    invocation_id = "1"
    completion: Dict[str, Any] | None = None
    helper_result: Dict[str, Any] | None = None
    deadline = asyncio.get_running_loop().time() + timeout_seconds

    async with websockets.connect(websocket_url, open_timeout=timeout_seconds, close_timeout=2) as websocket:
        await websocket.send(json.dumps({"protocol": "json", "version": 1}) + RECORD_SEPARATOR)
        buffered_frames = await _perform_handshake(websocket, deadline=deadline)
        await websocket.send(
            json.dumps(
                {
                    "type": 1,
                    "invocationId": invocation_id,
                    "target": "EquipArtifacts",
                    "arguments": [hero_id, artifact_ids],
                }
            )
            + RECORD_SEPARATOR
        )

        pending_frames = list(buffered_frames)
        while asyncio.get_running_loop().time() < deadline:
            if not pending_frames:
                remaining = max(0.1, deadline - asyncio.get_running_loop().time())
                try:
                    raw_message = await asyncio.wait_for(websocket.recv(), timeout=remaining)
                except TimeoutError:
                    break
                pending_frames.extend(_parse_signalr_frames(raw_message))

            frame = pending_frames.pop(0)
            frame_type = frame.get("type")

            if frame_type == 6:
                continue
            if frame_type == 7:
                raise HellHadesEquipError(frame.get("error") or "connessione SignalR chiusa dal server")
            if frame_type == 3 and frame.get("invocationId") == invocation_id:
                completion = frame
                if frame.get("error"):
                    raise HellHadesEquipError(str(frame["error"]))
                continue
            if frame_type == 1 and frame.get("target") == "HelperRequestResult":
                candidate = _extract_first_argument(frame)
                if candidate.get("request") == "EquipArtifacts":
                    helper_result = candidate
                    if not bool(candidate.get("isSuccess")):
                        raise HellHadesEquipError(candidate.get("error") or "EquipArtifacts fallito")
                    break

    status = "success" if helper_result and helper_result.get("isSuccess") else "requested"
    message = (
        "EquipArtifacts eseguito correttamente."
        if status == "success"
        else "Richiesta inviata a HellHades; nessun esito helper ricevuto entro il timeout."
    )
    return {
        "hero_id": hero_id,
        "artifact_ids": artifact_ids,
        "requested_count": len(artifact_ids),
        "completion": completion or {},
        "helper_result": helper_result or {},
        "status": status,
        "message": message,
    }


def _equip_artifacts_live_via_powershell(
    hero_id: Any,
    artifact_ids: List[Any],
    access_token: str,
    base_url: str,
    timeout_seconds: float,
) -> Dict[str, Any]:
    connection_token = _negotiate_connection(base_url=base_url, access_token=access_token, timeout_seconds=timeout_seconds)
    websocket_url = _build_websocket_url(base_url=base_url, connection_token=connection_token, access_token=access_token)
    payload = {
        "websocket_url": websocket_url,
        "hero_id": hero_id,
        "artifact_ids": artifact_ids,
        "timeout_ms": max(1000, int(timeout_seconds * 1000)),
        "record_separator": RECORD_SEPARATOR,
    }
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", _powershell_signalr_script()],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=max(5, int(timeout_seconds) + 5),
        check=False,
    )
    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    if completed.returncode != 0:
        message = stderr or stdout or "PowerShell websocket helper fallito"
        raise HellHadesEquipError(message)
    if not stdout:
        raise HellHadesEquipError("PowerShell websocket helper non ha restituito output")
    try:
        result = json.loads(_extract_json_object(stdout))
    except json.JSONDecodeError as exc:
        raise HellHadesEquipError(f"output helper PowerShell non valido: {stdout[:300]}") from exc
    if not isinstance(result, dict):
        raise HellHadesEquipError("risposta helper PowerShell non valida")
    if result.get("error"):
        raise HellHadesEquipError(str(result["error"]))
    return result


def _negotiate_connection(base_url: str, access_token: str, timeout_seconds: float) -> str:
    negotiate_url = f"{base_url.rstrip('/')}/live-updates/negotiate?negotiateVersion=1"
    request = Request(
        negotiate_url,
        method="POST",
        headers={"Authorization": f"Bearer {access_token}", "User-Agent": "CB Forge"},
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise HellHadesEquipError(f"negoziazione HellHades fallita: {exc}") from exc

    connection_token = str(payload.get("connectionToken") or payload.get("connectionId") or "").strip()
    if not connection_token:
        raise HellHadesEquipError("connectionToken HellHades mancante nella risposta di negotiate")
    return connection_token


def _build_websocket_url(base_url: str, connection_token: str, access_token: str) -> str:
    parsed = urlparse(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    path = parsed.path.rstrip("/")
    query = f"id={quote(connection_token, safe='')}&access_token={quote(access_token, safe='')}"
    return f"{scheme}://{parsed.netloc}{path}/live-updates?{query}"


async def _perform_handshake(websocket: Any, deadline: float) -> List[Dict[str, Any]]:
    buffered_frames: List[Dict[str, Any]] = []
    while asyncio.get_running_loop().time() < deadline:
        remaining = max(0.1, deadline - asyncio.get_running_loop().time())
        raw_message = await asyncio.wait_for(websocket.recv(), timeout=remaining)
        for frame in _parse_signalr_frames(raw_message):
            if not frame or "type" not in frame:
                return buffered_frames
            buffered_frames.append(frame)
    raise HellHadesEquipError("timeout durante handshake SignalR con HellHades")


def _parse_signalr_frames(raw_message: Any) -> List[Dict[str, Any]]:
    if isinstance(raw_message, bytes):
        text = raw_message.decode("utf-8")
    else:
        text = str(raw_message)

    frames: List[Dict[str, Any]] = []
    for chunk in text.split(RECORD_SEPARATOR):
        chunk = chunk.strip()
        if not chunk:
            continue
        payload = json.loads(chunk)
        if isinstance(payload, dict):
            frames.append(payload)
    return frames


def _extract_first_argument(frame: Dict[str, Any]) -> Dict[str, Any]:
    arguments = frame.get("arguments")
    if not isinstance(arguments, list) or not arguments:
        return {}
    first = arguments[0]
    if isinstance(first, dict):
        return first
    return {}


def _coerce_id(value: str) -> Any:
    raw = str(value).strip()
    if raw.isdigit():
        try:
            return int(raw)
        except ValueError:
            return raw
    return raw


def _extract_json_object(stdout: str) -> str:
    text = str(stdout or "").strip()
    if not text:
        return text
    for line in reversed(text.splitlines()):
        candidate = line.strip()
        if candidate.startswith("{") and candidate.endswith("}"):
            return candidate
    return text


def _powershell_signalr_script() -> str:
    return r"""
$ErrorActionPreference = 'Stop'

$payload = [Console]::In.ReadToEnd() | ConvertFrom-Json
$recordSeparator = [string]$payload.record_separator
$timeoutMs = [int]$payload.timeout_ms
$deadline = [DateTime]::UtcNow.AddMilliseconds($timeoutMs)

$webSocket = [System.Net.WebSockets.ClientWebSocket]::new()
$cts = [System.Threading.CancellationTokenSource]::new()
$cts.CancelAfter($timeoutMs)
$uri = [Uri]$payload.websocket_url
[void]$webSocket.ConnectAsync($uri, $cts.Token).GetAwaiter().GetResult()

function Send-Frame([System.Net.WebSockets.ClientWebSocket]$socket, [string]$text, [System.Threading.CancellationToken]$token) {
  $bytes = [System.Text.Encoding]::UTF8.GetBytes($text)
  $segment = [System.ArraySegment[byte]]::new($bytes, 0, $bytes.Length)
  [void]$socket.SendAsync($segment, [System.Net.WebSockets.WebSocketMessageType]::Text, $true, $token).GetAwaiter().GetResult()
}

function Receive-Text([System.Net.WebSockets.ClientWebSocket]$socket, [System.Threading.CancellationToken]$token) {
  $buffer = New-Object byte[] 4096
  $stream = [System.IO.MemoryStream]::new()
  do {
    $segment = [System.ArraySegment[byte]]::new($buffer, 0, $buffer.Length)
    try {
      $result = $socket.ReceiveAsync($segment, $token).GetAwaiter().GetResult()
    } catch [System.OperationCanceledException] {
      return $null
    }
    if ($result.MessageType -eq [System.Net.WebSockets.WebSocketMessageType]::Close) {
      return $null
    }
    if ($result.Count -gt 0) {
      $stream.Write($buffer, 0, $result.Count)
    }
  } while (-not $result.EndOfMessage)
  return [System.Text.Encoding]::UTF8.GetString($stream.ToArray())
}

function Parse-Frames([string]$raw, [string]$separator) {
  $frames = @()
  if ([string]::IsNullOrEmpty($raw)) {
    return $frames
  }
  foreach ($chunk in $raw.Split($separator)) {
    if ([string]::IsNullOrWhiteSpace($chunk)) {
      continue
    }
    $trimmed = $chunk.Trim()
    if (-not $trimmed) {
      continue
    }
    $frames += ,($trimmed | ConvertFrom-Json)
  }
  return $frames
}

Send-Frame $webSocket ('{"protocol":"json","version":1}' + $recordSeparator) $cts.Token
$handshakeRaw = Receive-Text $webSocket $cts.Token
if ($null -eq $handshakeRaw) {
  throw 'timeout durante handshake SignalR con HellHades'
}
$pendingFrames = New-Object System.Collections.ArrayList
foreach ($frame in (Parse-Frames $handshakeRaw $recordSeparator)) {
  if ($null -ne $frame.PSObject.Properties['type']) {
    [void]$pendingFrames.Add($frame)
  }
}

$invocationPayload = @{
  type = 1
  invocationId = '1'
  target = 'EquipArtifacts'
  arguments = @($payload.hero_id, @($payload.artifact_ids))
} | ConvertTo-Json -Compress -Depth 6
Send-Frame $webSocket ($invocationPayload + $recordSeparator) $cts.Token

$completion = $null
$helperResult = $null

while ([DateTime]::UtcNow -lt $deadline) {
  if ($pendingFrames.Count -eq 0) {
    $raw = Receive-Text $webSocket $cts.Token
    if ($null -eq $raw) {
      break
    }
    foreach ($frame in (Parse-Frames $raw $recordSeparator)) {
      [void]$pendingFrames.Add($frame)
    }
  }

  if ($pendingFrames.Count -eq 0) {
    continue
  }

  $frame = $pendingFrames[0]
  $pendingFrames.RemoveAt(0)
  $frameType = if ($null -ne $frame.PSObject.Properties['type']) { [int]$frame.type } else { -1 }

  if ($frameType -eq 6) {
    continue
  }
  if ($frameType -eq 7) {
    if ($frame.error) {
      throw [string]$frame.error
    }
    throw 'connessione SignalR chiusa dal server'
  }
  if ($frameType -eq 3 -and $frame.invocationId -eq '1') {
    $completion = $frame
    if ($frame.error) {
      throw [string]$frame.error
    }
    continue
  }
  if ($frameType -eq 1 -and $frame.target -eq 'HelperRequestResult' -and $frame.arguments.Count -gt 0) {
    $candidate = $frame.arguments[0]
    if ($candidate.request -eq 'EquipArtifacts') {
      $helperResult = $candidate
      if (-not [bool]$candidate.isSuccess) {
        if ($candidate.error) {
          throw [string]$candidate.error
        }
        throw 'EquipArtifacts fallito'
      }
      break
    }
  }
}

$status = if ($null -ne $helperResult -and [bool]$helperResult.isSuccess) { 'success' } else { 'requested' }
$message = if ($status -eq 'success') {
  'EquipArtifacts eseguito correttamente.'
} else {
  'Richiesta inviata a HellHades; nessun esito helper ricevuto entro il timeout.'
}

$result = @{
  hero_id = $payload.hero_id
  artifact_ids = @($payload.artifact_ids)
  requested_count = @($payload.artifact_ids).Count
  completion = if ($null -ne $completion) { $completion } else { @{} }
  helper_result = if ($null -ne $helperResult) { $helperResult } else { @{} }
  status = $status
  message = $message
}

$result | ConvertTo-Json -Compress -Depth 10
"""
