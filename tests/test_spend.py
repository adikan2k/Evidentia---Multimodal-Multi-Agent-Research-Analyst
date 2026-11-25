"""The day's spend survives a restart (D-051)."""

import asyncio
from datetime import date

import pytest
from qdrant_client import AsyncQdrantClient

from evidentia.limits import Limits, Refused
from evidentia.spend import COLLECTION, QdrantSpend

DAY = date(2026, 11, 25)


class MemorySpend:
    def __init__(self, usd: float = 0.0) -> None:
        self.days: dict[date, float] = {DAY: usd} if usd else {}
        self.fail_load = False
        self.fail_save = False
        self.saves: list[tuple[date, float]] = []

    async def load(self, day: date) -> float:
        if self.fail_load:
            raise ConnectionError("down")
        return self.days.get(day, 0.0)

    async def save(self, day: date, usd: float) -> None:
        if self.fail_save:
            raise ConnectionError("down")
        self.days[day] = usd
        self.saves.append((day, usd))


def test_a_new_server_starts_from_what_was_spent_today(settings) -> None:
    store = MemorySpend(usd=settings.daily_budget_usd - 0.05)
    limits = Limits(settings, clock=lambda: DAY, store=store)
    asyncio.run(limits.load())
    assert limits.spent == pytest.approx(settings.daily_budget_usd - 0.05)
    assert not limits.live_available()
    with pytest.raises(Refused, match="budget"):
        limits.start_run("a")


def test_each_finish_writes_the_new_total(settings) -> None:
    store = MemorySpend()
    limits = Limits(settings, clock=lambda: DAY, store=store)
    asyncio.run(limits.load())
    limits.start_run("a")
    limits.finish_run("a", 0.07)
    asyncio.run(limits.save())
    limits.start_check("a")
    limits.finish_check(0.01)
    asyncio.run(limits.save())
    assert store.saves == [(DAY, pytest.approx(0.07)), (DAY, pytest.approx(0.08))]


def test_a_new_day_starts_at_zero_and_reads_its_own_figure(settings) -> None:
    day = [DAY]
    store = MemorySpend(usd=0.5)
    limits = Limits(settings, clock=lambda: day[0], store=store)
    asyncio.run(limits.load())
    assert limits.spent == pytest.approx(0.5)
    day[0] = date(2026, 11, 26)
    asyncio.run(limits.load())
    assert limits.spent == 0.0 and limits.live_available()


def test_an_unreadable_store_refuses_live_runs_until_it_can_be_read(settings) -> None:
    store = MemorySpend()
    store.fail_load = True
    limits = Limits(settings, clock=lambda: DAY, store=store)
    asyncio.run(limits.load())
    assert not limits.live_available() and not limits.audit_available()
    with pytest.raises(Refused, match="could not be read") as err:
        limits.start_audit("a")
    assert err.value.status == 503
    store.fail_load = False
    asyncio.run(limits.load())
    limits.start_audit("a")


def test_a_failed_write_keeps_the_total_and_the_next_write_has_it(settings) -> None:
    store = MemorySpend()
    limits = Limits(settings, clock=lambda: DAY, store=store)
    asyncio.run(limits.load())
    store.fail_save = True
    limits.start_check("a")
    limits.finish_check(0.02)
    asyncio.run(limits.save())  # logged, not raised
    assert limits.spent == pytest.approx(0.02) and store.saves == []
    store.fail_save = False
    limits.start_check("a")
    limits.finish_check(0.01)
    asyncio.run(limits.save())
    assert store.days[DAY] == pytest.approx(0.03)


def test_without_a_store_nothing_changes(settings) -> None:
    limits = Limits(settings, clock=lambda: DAY)
    asyncio.run(limits.load())
    asyncio.run(limits.save())
    limits.start_run("a")
    assert limits.live_available()


def test_qdrant_keeps_one_total_per_day_and_no_address(settings) -> None:
    async def scenario() -> None:
        client = AsyncQdrantClient(location=":memory:")
        store = QdrantSpend(settings, client=client)
        assert await store.load(DAY) == 0.0
        await store.save(DAY, 0.12)
        await store.save(DAY, 0.31)
        await store.save(date(2026, 11, 26), 0.02)
        assert await store.load(DAY) == pytest.approx(0.31)
        # A second server reading the same cluster sees the same figure.
        assert await QdrantSpend(settings, client=client).load(DAY) == pytest.approx(0.31)
        points, _ = await client.scroll(COLLECTION, with_payload=True)
        assert len(points) == 2
        assert all(set(p.payload) == {"day", "usd"} for p in points)
        await client.close()

    asyncio.run(scenario())


def test_the_api_reads_the_stored_spend_and_writes_each_run(settings) -> None:
    from tests.test_api import Harness

    today = Limits(settings).day
    full = MemorySpend()
    full.days[today] = settings.daily_budget_usd
    api = Harness(settings, spend=full)
    assert api.call("GET", "/status").json()["live_available"] is False
    assert api.run().status_code == 429

    empty = MemorySpend()
    api = Harness(settings, spend=empty)
    assert api.call("GET", "/status").json()["live_available"] is True
    assert api.run().status_code == 200
    assert empty.days[today] == pytest.approx(api.limits.spent) and api.limits.spent > 0
