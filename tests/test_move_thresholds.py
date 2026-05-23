"""Tests for move_thresholds module."""

from __future__ import annotations

from tele_quant.move_thresholds import (
    MoveTier,
    format_tier_label,
    get_move_tier,
    get_significant_move_threshold,
    is_significant_mover,
)

# ── MoveTier dataclass ────────────────────────────────────────────────────────


class TestMoveTier:
    def test_frozen(self) -> None:
        from dataclasses import FrozenInstanceError

        tier = MoveTier(label="Test", low_pct=5.0, high_pct=10.0)
        try:
            tier.label = "X"  # type: ignore[misc]
        except FrozenInstanceError:
            return
        raise AssertionError("FrozenInstanceError was not raised")

    def test_defaults(self) -> None:
        tier = MoveTier(label="X", low_pct=1.0, high_pct=2.0)
        assert tier.note == ""


# ── get_move_tier — US ────────────────────────────────────────────────────────


class TestGetMoveTierUS:
    def test_mega_cap(self) -> None:
        tier = get_move_tier(1_000_000_000_000.0, "US")  # $1T
        assert tier.label == "Mega"
        assert tier.low_pct == 5.0

    def test_large_cap(self) -> None:
        tier = get_move_tier(100_000_000_000.0, "US")  # $100B
        assert tier.label == "Large"

    def test_mid_cap(self) -> None:
        tier = get_move_tier(10_000_000_000.0, "US")  # $10B
        assert tier.label == "Mid"

    def test_small_cap(self) -> None:
        tier = get_move_tier(1_000_000_000.0, "US")  # $1B
        assert tier.label == "Small"

    def test_micro_cap(self) -> None:
        tier = get_move_tier(100_000_000.0, "US")  # $100M
        assert tier.label == "Micro"
        assert tier.low_pct == 30.0

    def test_none_market_cap_returns_default(self) -> None:
        tier = get_move_tier(None, "US")
        assert tier.label == "Mid"

    def test_zero_market_cap_returns_micro(self) -> None:
        tier = get_move_tier(0.0, "US")
        assert tier.label == "Micro"


# ── get_move_tier — KR ────────────────────────────────────────────────────────


class TestGetMoveTierKR:
    def test_초대형_cap(self) -> None:
        tier = get_move_tier(60_000_000_000_000.0, "KR")  # 60조
        assert tier.label == "초대형"
        assert tier.low_pct == 5.0

    def test_대형_cap(self) -> None:
        tier = get_move_tier(20_000_000_000_000.0, "KR")  # 20조
        assert tier.label == "대형"

    def test_중형_cap(self) -> None:
        tier = get_move_tier(2_000_000_000_000.0, "KR")  # 2조
        assert tier.label == "중형"

    def test_소형_cap(self) -> None:
        tier = get_move_tier(500_000_000_000.0, "KR")  # 5000억
        assert tier.label == "소형"

    def test_초소형_cap(self) -> None:
        tier = get_move_tier(100_000_000_000.0, "KR")  # 1000억
        assert tier.label == "초소형"
        assert tier.low_pct == 30.0
        assert "상한가" in tier.note

    def test_none_market_cap_kr(self) -> None:
        tier = get_move_tier(None, "KR")
        assert tier.label == "중형"

    def test_lowercase_kr(self) -> None:
        tier = get_move_tier(60_000_000_000_000.0, "kr")
        assert tier.label == "초대형"


# ── get_significant_move_threshold ───────────────────────────────────────────


class TestGetSignificantMoveThreshold:
    def test_us_mega(self) -> None:
        t = get_significant_move_threshold("NVDA", 2_000_000_000_000.0, "US")
        assert t == 5.0

    def test_kr_초소형(self) -> None:
        t = get_significant_move_threshold("X", 50_000_000_000.0, "KR")
        assert t == 30.0

    def test_none_cap_returns_mid_threshold(self) -> None:
        t = get_significant_move_threshold("X", None, "US")
        assert t == 10.0


# ── is_significant_mover ─────────────────────────────────────────────────────


class TestIsSignificantMover:
    def test_mega_5pct_is_significant(self) -> None:
        assert is_significant_mover("NVDA", 5.5, 2_000_000_000_000.0, "US")

    def test_mega_4pct_not_significant(self) -> None:
        assert not is_significant_mover("NVDA", 4.0, 2_000_000_000_000.0, "US")

    def test_negative_move_abs_check(self) -> None:
        assert is_significant_mover("NVDA", -6.0, 2_000_000_000_000.0, "US")

    def test_micro_30pct_significant(self) -> None:
        assert is_significant_mover("X", 31.0, 100_000_000.0, "US")

    def test_micro_25pct_not_significant(self) -> None:
        assert not is_significant_mover("X", 25.0, 100_000_000.0, "US")

    def test_kr_초소형_상한가(self) -> None:
        assert is_significant_mover("Y", 30.1, 100_000_000_000.0, "KR")


# ── format_tier_label ─────────────────────────────────────────────────────────


class TestFormatTierLabel:
    def test_no_note(self) -> None:
        tier = MoveTier(label="Mega", low_pct=5.0, high_pct=10.0)
        label = format_tier_label(tier)
        assert "Mega" in label
        assert "5%" in label
        assert "10%" in label

    def test_with_note(self) -> None:
        tier = MoveTier(label="초소형", low_pct=30.0, high_pct=50.0, note="상한가(30%) 주의")
        label = format_tier_label(tier)
        assert "초소형" in label
        assert "상한가" in label
        assert "—" in label
