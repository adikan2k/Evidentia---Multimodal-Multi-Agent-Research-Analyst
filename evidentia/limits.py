"""What keeps a public "run" button from draining the account (D-028, D-051).

Everything is counted for the current UTC day. The per-address counts live in memory only. The
day's spend is also kept in a store when one is given, so a restart does not reset it. That is
only correct while there is a single server instance, which is how the API is deployed.
"""

import logging
from collections import Counter
from collections.abc import Callable
from datetime import UTC, date, datetime

from evidentia.config import Settings
from evidentia.spend import SpendStore

log = logging.getLogger("evidentia.limits")

UNREADABLE = "Live runs are paused: today's spend could not be read. The recorded runs still play."


class Refused(Exception):
    """A request we will not serve right now, with the reason to show the visitor."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def today() -> date:
    return datetime.now(UTC).date()


class Limits:
    def __init__(
        self, settings: Settings, clock: Callable[[], date] = today, store: SpendStore | None = None
    ) -> None:
        self.s = settings
        self.clock = clock
        self.store = store
        self.loaded = store is None  # with a store, nothing is spent until today's figure is read
        self.day = clock()
        self.spent = 0.0  # dollars actually spent today
        self.reserved = 0.0  # set aside for runs still in flight
        self.runs: Counter[str] = Counter()
        self.checks: Counter[str] = Counter()
        self.running: set[str] = set()
        self.audits: Counter[str] = Counter()
        self.auditing: set[str] = set()

    def _new_day(self) -> None:
        if self.clock() != self.day:
            self.day = self.clock()
            self.spent = 0.0
            self.runs.clear()
            self.checks.clear()
            self.audits.clear()
            self.loaded = self.store is None

    async def load(self) -> None:
        """Read today's spend from the store, until it has been read once for this day."""
        self._new_day()
        if self.loaded or self.store is None:
            return
        try:
            stored = await self.store.load(self.day)
        except Exception as err:  # any failure: stay closed, try again on the next request
            log.warning("could not read today's spend: %s", type(err).__name__)
            return
        self.spent = max(self.spent, stored)
        self.loaded = True

    async def save(self) -> None:
        """Write today's spend. A failure keeps the figure in memory; the next save retries."""
        if self.store is None or not self.loaded:
            return
        try:
            await self.store.save(self.day, self.spent)
        except Exception as err:
            log.warning("could not save today's spend: %s", type(err).__name__)

    def _require_budget(self, amount: float) -> None:
        if not self.loaded:
            raise Refused(503, UNREADABLE)
        if self.spent + self.reserved + amount > self.s.daily_budget_usd:
            raise Refused(
                429, "Today's budget for live runs is used up. The recorded runs still play."
            )

    def live_available(self) -> bool:
        self._new_day()
        if not self.loaded:
            return False
        return self.spent + self.reserved + self.s.run_reserve_usd <= self.s.daily_budget_usd

    def start_run(self, ip: str) -> None:
        self._new_day()
        if ip in self.running:
            raise Refused(409, "A run from your address is already in progress.")
        if len(self.running) >= self.s.max_concurrent_runs:
            raise Refused(503, "Other runs are in progress. Try again in a minute.")
        if self.runs[ip] >= self.s.max_runs_per_ip:
            raise Refused(
                429, f"That is today's {self.s.max_runs_per_ip} live runs from your address."
            )
        self._require_budget(self.s.run_reserve_usd)
        self.runs[ip] += 1
        self.running.add(ip)
        self.reserved += self.s.run_reserve_usd

    def finish_run(self, ip: str, spent_usd: float) -> None:
        self.running.discard(ip)
        self.reserved = max(0.0, self.reserved - self.s.run_reserve_usd)
        self.spent += spent_usd

    def start_check(self, ip: str) -> None:
        self._new_day()
        if self.checks[ip] >= self.s.max_checks_per_ip:
            raise Refused(
                429, f"That is today's {self.s.max_checks_per_ip} checks from your address."
            )
        self._require_budget(self.s.check_cap_usd)
        self.checks[ip] += 1

    def finish_check(self, spent_usd: float) -> None:
        self.spent += spent_usd

    def audit_available(self) -> bool:
        self._new_day()
        if not self.loaded:
            return False
        return self.spent + self.reserved + self.s.audit_reserve_usd <= self.s.daily_budget_usd

    def start_audit(self, ip: str) -> None:
        self._new_day()
        if ip in self.auditing:
            raise Refused(409, "An audit from your address is already in progress.")
        if len(self.auditing) >= self.s.max_concurrent_audits:
            raise Refused(503, "Other audits are in progress. Try again in a minute.")
        if self.audits[ip] >= self.s.max_audits_per_ip:
            raise Refused(
                429, f"That is today's {self.s.max_audits_per_ip} live audits from your address."
            )
        self._require_budget(self.s.audit_reserve_usd)
        self.audits[ip] += 1
        self.auditing.add(ip)
        self.reserved += self.s.audit_reserve_usd

    def finish_audit(self, ip: str, spent_usd: float) -> None:
        self.auditing.discard(ip)
        self.reserved = max(0.0, self.reserved - self.s.audit_reserve_usd)
        self.spent += spent_usd
