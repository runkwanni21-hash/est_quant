from __future__ import annotations

from tele_quant.catalyst_classifier import (
    CatalystConfidence,
    CatalystType,
    classify_catalyst,
    classify_from_raw_item,
    label_for_display,
)


def test_dart_contract_high_confidence():
    result = classify_catalyst(
        "HD현대중공업 LNG선 수주 계약 공시",
        source_type="dart",
        source_name="opendart",
    )
    assert result.catalyst_type == CatalystType.DART_CONTRACT
    assert result.confidence == CatalystConfidence.HIGH
    assert result.is_actionable is True
    assert result.relation_eligible is True


def test_sec_8k_high_confidence():
    result = classify_catalyst(
        "NVDA files 8-K — record earnings beat",
        source_type="sec_8k",
    )
    assert result.catalyst_type == CatalystType.SEC_8K
    assert result.confidence == CatalystConfidence.HIGH
    assert result.is_actionable is True


def test_earnings_medium_confidence():
    result = classify_catalyst(
        "Apple Q3 earnings beat: EPS $1.53 vs $1.35 est, revenue $92B",
        source_type="rss",
        source_name="reuters",
    )
    assert result.catalyst_type == CatalystType.EARNINGS
    assert result.confidence in (CatalystConfidence.HIGH, CatalystConfidence.MEDIUM)
    assert result.is_actionable is True


def test_clinical_trial_detected():
    result = classify_catalyst(
        "한미약품 임상 3상 성공 — FDA 허가 신청 예정",
        source_type="dart",
    )
    assert result.catalyst_type == CatalystType.CLINICAL
    assert result.confidence == CatalystConfidence.HIGH


def test_order_backlog_detected():
    result = classify_catalyst(
        "한화오션 LNG선 수주잔고 신규 발표",
        source_type="rss",
        source_name="pr_newswire",
    )
    assert result.catalyst_type == CatalystType.ORDER_BACKLOG
    assert result.is_actionable is True


def test_policy_pattern():
    result = classify_catalyst(
        "연준 금리 동결 결정 — FOMC 만장일치",
        source_type="rss",
        source_name="bloomberg",
    )
    assert result.catalyst_type in (CatalystType.POLICY, CatalystType.MACRO)
    assert result.is_actionable is True


def test_flow_only_not_actionable():
    result = classify_catalyst(
        "거래량 급증 외국인 순매수 RSI 과매도 수급 주도",
        source_type="telegram",
    )
    assert result.catalyst_type == CatalystType.FLOW_ONLY
    assert result.confidence == CatalystConfidence.LOW
    assert result.is_actionable is False
    assert result.relation_eligible is False
    assert result.recommendation_side == "WATCH_ONLY"


def test_unknown_low_confidence():
    result = classify_catalyst("", source_type="unknown")
    assert result.catalyst_type in (CatalystType.UNKNOWN, CatalystType.FLOW_ONLY)
    assert result.confidence == CatalystConfidence.LOW
    assert result.is_actionable is False


def test_classify_from_raw_item():
    item = {
        "title": "삼성바이오로직스 CDMO 위탁생산 계약",
        "text": "삼성바이오로직스가 글로벌 제약사와 CMO 계약을 체결했다.",
        "source_type": "dart",
        "source_name": "opendart",
    }
    result = classify_from_raw_item(item)
    assert result.is_actionable is True


def test_label_for_display():
    result = classify_catalyst("수주잔고 급증", source_type="dart")
    label = label_for_display(result)
    assert label  # 빈 문자열이 아니어야 함
    assert "수주" in label or "DART" in label or "🔴" in label or "🟡" in label


def test_flow_only_watch_only_side():
    result = classify_catalyst("이유불명 주가 급등", source_type="telegram")
    assert result.recommendation_side == "WATCH_ONLY"


def test_high_confidence_is_active():
    result = classify_catalyst(
        "삼성전자 자사주 매입 공시",
        source_type="dart",
    )
    assert result.recommendation_side == "ACTIVE"
    assert result.relation_eligible is True
