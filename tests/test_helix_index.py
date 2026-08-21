import pytest

from reckon.helix_index import HelixProjectionIndex


class Conflict(Exception):
    pass


class FakeQueryRequest:
    @staticmethod
    def write(request):
        return request


class FakeSDK:
    HelixError = Conflict
    QueryRequest = FakeQueryRequest


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = 0

    def query(self, request):
        self.calls += 1
        value = next(self.responses)
        if isinstance(value, Exception):
            raise value
        return value


def index_with(responses):
    index = object.__new__(HelixProjectionIndex)
    index.h = FakeSDK
    index.client = FakeClient(responses)
    return index


def test_write_retries_transaction_conflicts(monkeypatch):
    monkeypatch.setattr("reckon.helix_index.time.sleep", lambda _: None)
    index = index_with(
        [Conflict("transaction conflict"), Conflict("transaction conflict"), {"ok": True}]
    )

    assert index._write("request") == {"ok": True}
    assert index.client.calls == 3


def test_write_does_not_swallow_other_helix_errors(monkeypatch):
    monkeypatch.setattr("reckon.helix_index.time.sleep", lambda _: None)
    index = index_with([Conflict("uniqueness violation")])

    with pytest.raises(Conflict, match="uniqueness violation"):
        index._write("request")
