"""on_message 不得记入命令统计。"""

from __future__ import annotations

import uuid
import asyncio
from copy import deepcopy
from typing import Literal
from pathlib import Path

from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.handler import count_data
from gsuid_core.trigger import Trigger
from gsuid_core.global_val import PlatformVal, bot_val, bot_dirty, bot_summary_saved
from gsuid_core.utils.database.global_val_models import (
    DataType,
    is_uuid4_command_name,
)

TriggerKind = Literal[
    "prefix",
    "suffix",
    "keyword",
    "fullmatch",
    "command",
    "file",
    "regex",
    "message",
    "meta",
]

_ROOT = Path(__file__).resolve().parents[1]
_STARTUP = _ROOT / "gsuid_core" / "utils" / "database" / "startup.py"


def _isolate_bot_val() -> tuple[
    dict[str, dict[str, PlatformVal]],
    dict[str, dict[str, set[tuple[DataType, str, str]]]],
    dict[str, dict[str, tuple[int, int, int, int, int, int]]],
]:
    snapshot = deepcopy(bot_val)
    dirty = {bot: {self_id: set(keys) for self_id, keys in bots.items()} for bot, bots in bot_dirty.items()}
    saved = {bot: dict(bots) for bot, bots in bot_summary_saved.items()}
    bot_val.clear()
    bot_dirty.clear()
    bot_summary_saved.clear()
    return snapshot, dirty, saved


def _restore_bot_val(
    snapshot: dict[str, dict[str, PlatformVal]],
    dirty: dict[str, dict[str, set[tuple[DataType, str, str]]]],
    saved: dict[str, dict[str, tuple[int, int, int, int, int, int]]],
) -> None:
    bot_val.clear()
    bot_val.update(snapshot)
    bot_dirty.clear()
    bot_dirty.update(dirty)
    bot_summary_saved.clear()
    bot_summary_saved.update(saved)


async def _noop(_bot: Bot, _ev: Event) -> None:
    return None


def _trigger(kind: TriggerKind, keyword: str) -> Trigger:
    return Trigger(kind, keyword, _noop)


def _event() -> Event:
    ev = Event(
        bot_id="onebot",
        bot_self_id="self1",
        user_type="group",
        group_id="g1",
        user_id="u1",
        user_pm=6,
    )
    ev.real_bot_id = "onebot"
    return ev


def test_uuid4_from_stdlib_is_detected() -> None:
    for _ in range(20):
        assert is_uuid4_command_name(str(uuid.uuid4()))


def test_uuid4_uppercase_is_detected() -> None:
    assert is_uuid4_command_name(str(uuid.uuid4()).upper())


def test_non_uuid4_command_names_are_kept() -> None:
    assert not is_uuid4_command_name("帮助")
    assert not is_uuid4_command_name("")
    assert not is_uuid4_command_name("png")
    assert not is_uuid4_command_name("a" * 36)
    assert not is_uuid4_command_name(str(uuid.uuid1()))
    assert not is_uuid4_command_name(str(uuid.uuid3(uuid.NAMESPACE_DNS, "gscore")))
    assert not is_uuid4_command_name(str(uuid.uuid5(uuid.NAMESPACE_DNS, "gscore")))
    assert not is_uuid4_command_name("00000000-0000-0000-0000-000000000000")
    assert not is_uuid4_command_name("550e8400e29b41d4a716446655440000")
    named = str(uuid.uuid4()) + "-extra"
    assert not is_uuid4_command_name(named)


def test_count_data_skips_on_message() -> None:
    snapshot, dirty, saved = _isolate_bot_val()
    try:
        ev = _event()
        fake = str(uuid.uuid4())
        asyncio.run(count_data(ev, _trigger("message", fake)))
        command = 0
        if "onebot" in bot_val and "self1" in bot_val["onebot"]:
            local = bot_val["onebot"]["self1"]
            command = local["command"]
            if "u1" in local["user"]:
                assert fake not in local["user"]["u1"]
        assert command == 0
    finally:
        _restore_bot_val(snapshot, dirty, saved)


def test_count_data_records_real_command_and_ignores_later_message() -> None:
    snapshot, dirty, saved = _isolate_bot_val()
    try:
        ev = _event()
        fake = str(uuid.uuid4())
        asyncio.run(count_data(ev, _trigger("command", "帮助")))
        asyncio.run(count_data(ev, _trigger("fullmatch", "状态")))
        asyncio.run(count_data(ev, _trigger("message", fake)))
        local = bot_val["onebot"]["self1"]
        assert local["command"] == 2
        assert local["user"]["u1"]["帮助"] == 1
        assert local["user"]["u1"]["状态"] == 1
        assert local["group"]["g1"]["帮助"] == 1
        assert fake not in local["user"]["u1"]
    finally:
        _restore_bot_val(snapshot, dirty, saved)


def test_count_data_still_records_file_trigger() -> None:
    snapshot, dirty, saved = _isolate_bot_val()
    try:
        ev = _event()
        asyncio.run(count_data(ev, _trigger("file", "png")))
        local = bot_val["onebot"]["self1"]
        assert local["command"] == 1
        assert local["user"]["u1"]["png"] == 1
    finally:
        _restore_bot_val(snapshot, dirty, saved)
