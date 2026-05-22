"""Tests for compute_star_rating in stock_snapshot.py."""

from __future__ import annotations

import pytest

from tele_quant.stock_snapshot import StockAnalysisSnapshot, compute_star_rating


def _snap(tech: float, val: float, swing: float) -> StockAnalysisSnapshot:
    s = StockAnalysisSnapshot(symbol="TEST", market="US")
    s.tech_score = tech  # 0~40
    s.val_score = val    # 0~100
    s.swing_score = swing  # 0~100
    return s


class TestComputeStarRating:
    def test_returns_tuple(self):
        s = _snap(30, 70, 60)
        result = compute_star_rating(s)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_five_stars_high_scores(self):
        # tech_norm=100, val=100, swing=100 → composite=100 → 5★
        s = _snap(40, 100, 100)
        star_str, _ = compute_star_rating(s)
        assert star_str == "★★★★★"

    def test_one_star_low_scores(self):
        s = _snap(0, 0, 0)
        star_str, _ = compute_star_rating(s)
        assert star_str == "★☆☆☆☆"

    def test_three_stars_mid_scores(self):
        # tech_norm=50, val=50, swing=50 → composite=50 → 3★ (>=40)
        s = _snap(20, 50, 50)
        star_str, _ = compute_star_rating(s)
        assert star_str.count("★") >= 2

    def test_star_string_length(self):
        for tech in [0, 10, 20, 30, 40]:
            s = _snap(tech, 50, 50)
            star_str, _ = compute_star_rating(s)
            assert len(star_str) == 5

    def test_sub_info_contains_grades(self):
        s = _snap(40, 100, 100)
        _, sub = compute_star_rating(s)
        assert "기술:" in sub
        assert "펀더:" in sub
        assert "스윙:" in sub

    def test_sub_info_grade_a_at_high(self):
        s = _snap(40, 90, 90)
        _, sub = compute_star_rating(s)
        assert "A" in sub

    def test_sub_info_grade_d_at_low(self):
        s = _snap(0, 10, 10)
        _, sub = compute_star_rating(s)
        assert "D" in sub

    def test_composite_boundary_82(self):
        # At composite=82: 5★.  tech_norm=100*0.4 + val*0.3 + swing*0.3
        # 40 + 80*0.3 + 80*0.3 = 40+24+24 = 88 → 5★
        s = _snap(40, 80, 80)
        star_str, _ = compute_star_rating(s)
        assert star_str == "★★★★★"

    def test_four_stars_boundary(self):
        # composite=70~81 → 4★
        # tech_norm=50*0.4 + 70*0.3 + 70*0.3 = 20+21+21 = 62 → 3★
        # tech_norm=75*0.4 + 70*0.3 + 70*0.3 = 30+21+21 = 72 → 4★
        s = _snap(30, 70, 70)  # tech_norm=75
        star_str, _ = compute_star_rating(s)
        assert star_str == "★★★★☆"

    @pytest.mark.parametrize("stars", [1, 2, 3, 4, 5])
    def test_star_count_valid(self, stars: int):
        s = StockAnalysisSnapshot(symbol="X", market="US")
        # Drive composite to desired star bracket
        boundaries = {5: (40, 100, 100), 4: (30, 70, 70), 3: (20, 50, 50), 2: (8, 35, 35), 1: (0, 0, 0)}
        tech, val, swing = boundaries[stars]
        s.tech_score, s.val_score, s.swing_score = tech, val, swing
        star_str, _ = compute_star_rating(s)
        assert 1 <= star_str.count("★") <= 5
