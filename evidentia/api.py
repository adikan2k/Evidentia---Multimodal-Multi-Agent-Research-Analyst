"""The web API (D-027, D-041). Start a run or an audit and stream it, check one claim, status.

    uvicorn evidentia.api:create_app --factory --port 8000

A run is streamed as server-sent events, the same events a replay file holds:
`node` as each pipeline step finishes, then `report`, or `error`.
"""

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from langgraph.errors import NodeTimeoutError
from pydantic import BaseModel, Field

from evidentia.__main__ import build_deps
from evidentia.audit.cli import build_audit_deps
from evidentia.audit.events import AuditEventBuilder
from evidentia.audit.graph import AuditDeps, run_audit
from evidentia.config import Settings, load_settings
from evidentia.cost import BudgetExceeded, Ledger
from evidentia.events import EventBuilder
from evidentia.graph import Deps, run_question
from evidentia.limits import Limits, Refused
from evidentia.llm import CHECK_SYSTEM, LLM, ModelStopped, check_prompt, new_tag, with_tag
from evidentia.schemas import Judgement, RunState
from evidentia.tracing import LangfuseTracer, Tracer

log = logging.getLogger("evidentia.api")

EXPECTED_STOPS = (BudgetExceeded, ModelStopped, NodeTimeoutError)


class RunRequest(BaseModel):
    question: str = Field(min_length=10, max_length=300)


class AuditRequest(BaseModel):
    answer: str = Field(min_length=20, max_length=12_000)


class CheckRequest(BaseModel):
    claim: str = Field(min_length=3, max_length=600)
    quote: str = Field(min_length=3, max_length=2_000)


@dataclass
class Services:
    """What the API needs from outside. Tests pass fakes."""

    settings: Settings
    tracer: Tracer
    make_deps: Callable[[Ledger], Deps]
    make_llm: Callable[[Ledger], LLM]
    make_audit_deps: Callable[[Ledger], AuditDeps] | None = None


def real_services() -> Services:
    settings = load_settings()
    tracer = LangfuseTracer(settings)
    return Services(
        settings=settings,
        tracer=tracer,
        make_deps=lambda ledger: build_deps(settings, ledger, tracer),
        make_llm=lambda ledger: LLM(settings, ledger),
        make_audit_deps=lambda ledger: build_audit_deps(settings, ledger, tracer),
    )


def client_ip(request: Request) -> str:
    """The visitor's address.

    Cloud Run appends the real address to the end of X-Forwarded-For. Anything before it was
    sent by the visitor and could be made up to dodge the per-address limits, so only the last
    entry is trusted.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def create_app(services: Services | None = None) -> FastAPI:
    svc = services or real_services()
    s = svc.settings
    limits = Limits(s)
    app = FastAPI(title="Evidentia", docs_url=None, redoc_url=None)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in s.allowed_origins.split(",") if o.strip()],
        allow_methods=["GET", "POST"],
        allow_headers=["content-type"],
    )
    app.state.limits = limits

    @app.exception_handler(Refused)
    async def refused(_: Request, err: Refused) -> JSONResponse:
        return JSONResponse({"message": err.message}, status_code=err.status)

    @app.get("/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/status")
    async def status() -> dict[str, Any]:
        """Lets the page say up front whether a live run is possible right now."""
        return {
            "live_available": limits.live_available(),
            "run_cap_usd": s.public_run_cap_usd,
            "audit_available": limits.audit_available() and svc.make_audit_deps is not None,
            "audit_cap_usd": s.audit_cap_usd,
        }

    @app.post("/runs")
    async def start_run(body: RunRequest, request: Request) -> StreamingResponse:
        ip = client_ip(request)
        limits.start_run(ip)
        return StreamingResponse(
            stream_run(body.question.strip(), ip),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def stream_run(question: str, ip: str) -> AsyncIterator[str]:
        ledger = Ledger(min(s.cost_cap_usd, s.public_run_cap_usd))
        deps = svc.make_deps(ledger)
        builder = EventBuilder(ledger)
        queue: asyncio.Queue[tuple[str, dict[str, Any]] | None] = asyncio.Queue()
        initial = RunState(run_id=uuid.uuid4().hex, question=question)
        started = time.monotonic()

        def on_update(node: str, update: dict[str, Any]) -> None:
            seconds = round(time.monotonic() - started, 2)
            queue.put_nowait(("node", {"t": seconds} | builder.node_event(node, update)))

        async def work() -> None:
            try:
                state = await run_question(question, deps, on_update, initial=initial)
                queue.put_nowait(("report", builder.report(state)))
            except EXPECTED_STOPS as err:
                queue.put_nowait(("error", {"message": f"The run stopped: {err}"}))
            except Exception:
                log.exception("run failed")
                queue.put_nowait(("error", {"message": "The run failed unexpectedly."}))
            finally:
                queue.put_nowait(None)

        task = asyncio.create_task(work())
        try:
            while (item := await queue.get()) is not None:
                yield sse(*item)
        finally:
            # Also reached when the visitor closes the tab: stop paying for a run nobody sees.
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await asyncio.gather(
                deps.store.delete_run(initial.run_id),
                deps.fetcher.aclose(),
                return_exceptions=True,
            )
            await asyncio.gather(deps.store.aclose(), return_exceptions=True)
            limits.finish_run(ip, ledger.spent)
            svc.tracer.flush()

    @app.post("/audits")
    async def start_audit(body: AuditRequest, request: Request) -> StreamingResponse:
        if svc.make_audit_deps is None:
            raise Refused(503, "Live audits are not available on this server.")
        ip = client_ip(request)
        limits.start_audit(ip)
        return StreamingResponse(
            stream_audit(body.answer, ip),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def stream_audit(answer: str, ip: str) -> AsyncIterator[str]:
        ledger = Ledger(s.audit_cap_usd)
        deps = svc.make_audit_deps(ledger)
        builder = AuditEventBuilder(ledger)
        queue: asyncio.Queue[tuple[str, dict[str, Any]] | None] = asyncio.Queue()
        started = time.monotonic()

        def on_update(node: str, update: dict[str, Any]) -> None:
            seconds = round(time.monotonic() - started, 2)
            queue.put_nowait(("node", {"t": seconds} | builder.node_event(node, update)))

        async def work() -> None:
            try:
                state = await run_audit(answer, deps, on_update)
                queue.put_nowait(("report", builder.report(state)))
            except EXPECTED_STOPS as err:
                queue.put_nowait(("error", {"message": f"The audit stopped: {err}"}))
            except Exception:
                log.exception("audit failed")
                queue.put_nowait(("error", {"message": "The audit failed unexpectedly."}))
            finally:
                queue.put_nowait(None)

        task = asyncio.create_task(work())
        try:
            while (item := await queue.get()) is not None:
                yield sse(*item)
        finally:
            # Also reached when the visitor closes the tab: stop paying for an audit nobody sees.
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await asyncio.gather(deps.fetcher.aclose(), return_exceptions=True)
            limits.finish_audit(ip, ledger.spent)
            svc.tracer.flush()

    @app.post("/check")
    async def check(body: CheckRequest, request: Request) -> dict[str, str]:
        """Try to break it: the checker's verdict on any claim against any quote."""
        limits.start_check(client_ip(request))
        ledger = Ledger(s.check_cap_usd)
        tag = new_tag("quote")
        try:
            with svc.tracer.span("api.check", "span", {"claim": body.claim}):
                judgement = await svc.make_llm(ledger).structured(
                    node="check",
                    model=s.checker_model,
                    effort=s.checker_effort,
                    max_tokens=s.checker_max_tokens,
                    system=with_tag(CHECK_SYSTEM, tag),
                    user=check_prompt(body.claim, body.quote, tag),
                    schema=Judgement,
                    config={"callbacks": svc.tracer.callbacks()},
                )
        except EXPECTED_STOPS as err:
            raise Refused(502, "The checker did not return a verdict. Try again.") from err
        finally:
            limits.finish_check(ledger.spent)
            svc.tracer.flush()
        label = "unverified" if judgement.label == "unsupported" else judgement.label
        return {"label": label, "verdict": judgement.label, "reason": judgement.reason}

    return app
