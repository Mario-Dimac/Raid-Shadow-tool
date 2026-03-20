from __future__ import annotations

from pathlib import Path

import hellhades_live


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        import json

        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeWebSocket:
    def __init__(self, messages):
        self.messages = list(messages)
        self.sent = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def send(self, data):
        self.sent.append(data)

    async def recv(self):
        if not self.messages:
            raise TimeoutError("no more messages")
        return self.messages.pop(0)


def test_build_websocket_url_includes_connection_id_and_token() -> None:
    url = hellhades_live._build_websocket_url(
        base_url="https://raidoptimiser.hellhades.com",
        connection_token="abc 123",
        access_token="tok+en",
    )

    assert url == "wss://raidoptimiser.hellhades.com/live-updates?id=abc%20123&access_token=tok%2Ben"


def test_normalize_access_token_accepts_full_login_url() -> None:
    token = hellhades_live.normalize_access_token("https://raidoptimiser.hellhades.com/login#token=abc123")

    assert token == "abc123"


def test_discover_access_token_from_edge_reads_latest_jwt(tmp_path: Path) -> None:
    leveldb = tmp_path / "leveldb"
    leveldb.mkdir()
    (leveldb / "002270.ldb").write_bytes(
        b"_https://raidoptimiser.hellhades.com\x00access_token\x00eyJaaa.bbb.ccc"
    )

    token = hellhades_live.discover_access_token_from_edge(leveldb)

    assert token == "eyJaaa.bbb.ccc"


def test_equip_artifacts_live_invokes_signalr_and_returns_helper_result(monkeypatch) -> None:
    fake_socket = FakeWebSocket(
        [
            "{}\x1e",
            '{"type":3,"invocationId":"1","result":true}\x1e',
            '{"type":1,"target":"HelperRequestResult","arguments":[{"request":"EquipArtifacts","isSuccess":true,"error":""}]}\x1e',
        ]
    )

    monkeypatch.setattr(hellhades_live, "urlopen", lambda request, timeout: FakeResponse({"connectionToken": "connection-token"}))
    monkeypatch.setattr(hellhades_live.websockets, "connect", lambda *args, **kwargs: fake_socket)

    result = hellhades_live.equip_artifacts_live(
        hero_id="6206",
        artifact_ids=["100", "101"],
        access_token="secret-token",
    )

    assert result["status"] == "success"
    assert result["requested_count"] == 2
    assert result["helper_result"]["request"] == "EquipArtifacts"
    assert fake_socket.sent[0] == '{"protocol": "json", "version": 1}\x1e'
    assert '"target": "EquipArtifacts"' in fake_socket.sent[1]
    assert '"arguments": [6206, [100, 101]]' in fake_socket.sent[1]


def test_equip_artifacts_live_requires_token() -> None:
    original = hellhades_live.discover_access_token_from_edge
    hellhades_live.discover_access_token_from_edge = lambda leveldb_dir=hellhades_live.EDGE_LEVELDB_DIR: ""
    try:
        hellhades_live.equip_artifacts_live(hero_id="6206", artifact_ids=["100"], access_token="")
    except ValueError as exc:
        assert str(exc) == "token HellHades mancante"
    else:
        raise AssertionError("expected ValueError")
    finally:
        hellhades_live.discover_access_token_from_edge = original
