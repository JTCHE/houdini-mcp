"""MCP tasks: a long call returns a task at once, and the client polls it.

A cook, a cache or a render holds Houdini for minutes. When the client says it
reads tasks (the io.modelcontextprotocol/tasks extension in the `_meta` of the
request), a call that is not done after QUICK_SECONDS answers with a task, and
the client asks for its state with tasks/get until it ends. The agent works on
in the meantime. A client that does not read tasks waits for the result, as
before.
"""
import asyncio
import os
import time
import uuid
from datetime import datetime, timezone

from mcp.server.extension import Extension, MethodBinding
from mcp_types import CLIENT_CAPABILITIES_META_KEY, RequestParams
from pydantic import Field

from houdinimcp import protocol

from . import connection

IDENTIFIER = "io.modelcontextprotocol/tasks"
QUICK_SECONDS = 3.0
POLL_MS = 2000


class TaskParams(RequestParams):
    task_id: str = Field(alias="taskId")


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Tasks(Extension):
    identifier = IDENTIFIER

    def __init__(self):
        self.tasks = {}

    def methods(self):
        return [MethodBinding("tasks/get", TaskParams, self._get),
                MethodBinding("tasks/cancel", TaskParams, self._cancel)]

    async def intercept_tool_call(self, params, ctx, call_next):
        capabilities = (params.meta or {}).get(CLIENT_CAPABILITIES_META_KEY) or {}
        if IDENTIFIER not in (capabilities.get("extensions") or {}):
            return await call_next(ctx)
        work = asyncio.ensure_future(call_next(ctx))
        await asyncio.wait({work}, timeout=QUICK_SECONDS)
        if work.done():
            return work.result()
        task_id = f"{params.name}-{uuid.uuid4().hex[:12]}"
        self.tasks[task_id] = {"work": work, "tool": params.name, "since": time.monotonic(),
                               "created": _now(), "cancelled": False}
        return {"resultType": "task", **self._state(task_id), "pollIntervalMs": POLL_MS}

    def _state(self, task_id):
        task = self.tasks[task_id]
        state = {"taskId": task_id, "createdAt": task["created"], "lastUpdatedAt": _now(),
                 "ttlMs": None}
        work = task["work"]
        if task["cancelled"]:
            return {**state, "status": "cancelled",
                    "statusMessage": f"'{task['tool']}' was stopped: session action="
                                     f"'interrupt' went to Houdini. What it changed stays."}
        if not work.done():
            seconds = time.monotonic() - task["since"]
            message = f"Houdini runs '{task['tool']}' since {seconds:.0f} seconds."
            printed = _last_line()
            return {**state, "status": "working",
                    "statusMessage": f"{message} It printed: {printed}" if printed else message}
        if work.exception() is not None:
            return {**state, "status": "failed",
                    "error": {"code": -32603, "message": str(work.exception())}}
        result = work.result()
        return {**state, "status": "completed",
                "result": result.model_dump(by_alias=True, mode="json", exclude_none=True)}

    async def _get(self, ctx, params):
        if params.task_id not in self.tasks:
            raise ValueError(f"No task '{params.task_id}' in this bridge.")
        state = self._state(params.task_id)
        if state["status"] != "working":
            self.tasks.pop(params.task_id)
            return {"resultType": "complete", **state}
        return {"resultType": "task", **state, "pollIntervalMs": POLL_MS}

    async def _cancel(self, ctx, params):
        task = self.tasks.get(params.task_id)
        if task is None:
            raise ValueError(f"No task '{params.task_id}' in this bridge.")
        if not task["work"].done():
            task["cancelled"] = True
            await asyncio.to_thread(connection.interrupt)
        return {"resultType": "complete", **self._state(params.task_id)}


def _last_line():
    """The last line that a running script printed, from the file that the
    plugin writes as it goes. Only execute prints there."""
    live = connection._connection
    if live is None or not live.port:
        return None
    try:
        with open(protocol.output_file(live.port), "rb") as handle:
            handle.seek(max(0, os.path.getsize(handle.name) - 400))
            text = handle.read().decode("utf-8", "replace")
    except OSError:
        return None
    # The plugin writes the file as it comes, so the last line can be half done.
    lines = text[:text.rfind("\n")].strip().splitlines()
    return lines[-1][-200:] if lines else None
