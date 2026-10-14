"""T103：心跳超时边界（research.md R1）。

轮询模型下没有长连接可断，"工位是否离线"只能靠心跳时间推断。
阈值默认 30 秒（心跳 5 秒 × 6 次未达），边界行为必须精确——
差一秒就会把在线工位判成离线，导致补打被无谓拒绝。
"""

from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.core.config import get_settings
from app.models.base import utcnow
from app.services.workstation import is_online


def _ws(seconds_ago: float | None):
    """构造一个只需 last_heartbeat_at 的轻量对象。"""
    last = None if seconds_ago is None else utcnow() - timedelta(seconds=seconds_ago)
    return SimpleNamespace(last_heartbeat_at=last)


class TestThresholdBoundary:
    def test_threshold_defaults_to_30_seconds(self):
        assert get_settings().offline_threshold_seconds == 30

    def test_just_reported_is_online(self):
        assert is_online(_ws(0)) is True

    def test_29_seconds_ago_is_still_online(self):
        assert is_online(_ws(29)) is True

    def test_exactly_30_seconds_ago_is_still_online(self):
        # 边界取"小于等于"：正好 30 秒仍算在线，避免临界抖动
        assert is_online(_ws(30)) is True

    def test_31_seconds_ago_is_offline(self):
        assert is_online(_ws(31)) is False

    def test_long_silence_is_offline(self):
        assert is_online(_ws(3600)) is False


class TestMissingHeartbeat:
    def test_never_reported_is_offline(self):
        # 刚建好、从未上报心跳的工位不该被当成在线
        assert is_online(_ws(None)) is False


class TestThresholdIsConfigurable:
    def test_custom_threshold(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "offline_threshold_seconds", 5)
        assert is_online(_ws(4)) is True
        assert is_online(_ws(6)) is False

    def test_longer_threshold_keeps_workstation_online(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "offline_threshold_seconds", 120)
        assert is_online(_ws(100)) is True
