"""Tests for clinical_pipeline — biotech/pharma clinical stage lookup."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tele_quant.clinical_pipeline import (
    _PHASE_DISPLAY,
    _STATUS_DISPLAY,
    ClinicalPipelineResult,
    ClinicalTrial,
    fetch_clinical_pipeline,
    format_clinical_pipeline,
)

# ── ClinicalTrial dataclass ───────────────────────────────────────────────────


def test_clinical_trial_defaults():
    trial = ClinicalTrial()
    assert trial.nct_id == ""
    assert trial.source == "ClinicalTrials.gov"


def test_clinical_trial_fields():
    trial = ClinicalTrial(
        nct_id="NCT12345678",
        title="GLP-1 Agonist in Obesity",
        phase="Phase 2",
        status="모집 중",
        condition="Obesity",
        primary_completion="2026-12",
    )
    assert trial.nct_id == "NCT12345678"
    assert trial.phase == "Phase 2"
    assert trial.status == "모집 중"


# ── Phase/Status display maps ─────────────────────────────────────────────────


def test_phase_display_map():
    assert _PHASE_DISPLAY["PHASE2"] == "Phase 2"
    assert _PHASE_DISPLAY["PHASE3"] == "Phase 3"
    assert "Phase 1" in _PHASE_DISPLAY.values()


def test_status_display_map():
    assert _STATUS_DISPLAY["RECRUITING"] == "모집 중"
    assert _STATUS_DISPLAY["COMPLETED"] == "완료"
    assert _STATUS_DISPLAY["TERMINATED"] == "종료"


# ── fetch_clinical_pipeline ───────────────────────────────────────────────────


def _mock_ct_response(phase: str = "PHASE2", status: str = "RECRUITING") -> dict:
    return {
        "studies": [{
            "protocolSection": {
                "identificationModule": {
                    "nctId": "NCT99999999",
                    "briefTitle": "Test Drug in Type 2 Diabetes",
                },
                "statusModule": {
                    "overallStatus": status,
                    "primaryCompletionDateStruct": {"date": "2027-06"},
                    "completionDateStruct": {"date": "2028-01"},
                    "startDateStruct": {"date": "2025-01"},
                },
                "designModule": {
                    "phases": [phase],
                },
                "conditionsModule": {
                    "conditions": ["Type 2 Diabetes", "Obesity"],
                },
                "sponsorCollaboratorsModule": {
                    "leadSponsor": {"name": "Test Pharma Inc"},
                },
            }
        }]
    }


def test_fetch_clinical_pipeline_with_mock_response():
    with patch("urllib.request.urlopen") as mock_urlopen:
        import json
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = json.dumps(_mock_ct_response()).encode()
        mock_urlopen.return_value = mock_resp

        result = fetch_clinical_pipeline("HAMI", "한미약품", "KR")

    assert isinstance(result, ClinicalPipelineResult)
    assert len(result.trials) == 1
    trial = result.trials[0]
    assert trial.nct_id == "NCT99999999"
    assert trial.phase == "Phase 2"
    assert trial.status == "모집 중"
    assert trial.primary_completion == "2027-06"
    assert "Diabetes" in trial.condition


def test_fetch_clinical_pipeline_phase3_status():
    with patch("urllib.request.urlopen") as mock_urlopen:
        import json
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = json.dumps(
            _mock_ct_response(phase="PHASE3", status="ACTIVE_NOT_RECRUITING")
        ).encode()
        mock_urlopen.return_value = mock_resp

        result = fetch_clinical_pipeline("TEST")

    assert result.trials[0].phase == "Phase 3"
    assert result.trials[0].status == "진행 중 (모집 종료)"


def test_fetch_clinical_pipeline_network_failure_returns_limited():
    with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
        result = fetch_clinical_pipeline("128940.KS", "한미약품", "KR")

    assert result.data_limited is True
    assert result.trials == []
    assert result.limitation_note != ""


def test_fetch_clinical_pipeline_no_hallucination_on_empty():
    """데이터 없으면 임상 정보를 지어내지 않아야 한다."""
    with patch("urllib.request.urlopen", side_effect=OSError("timeout")):
        result = fetch_clinical_pipeline("UNKNOWN_BIO", "Unknown")

    output = format_clinical_pipeline(result)
    forbidden = ["성공 가능성 높음", "확정 수익", "FDA 승인 예정", "반드시 상승"]
    for word in forbidden:
        assert word not in output, f"Hallucination: '{word}'"


# ── format_clinical_pipeline ─────────────────────────────────────────────────


def test_format_with_trial():
    result = ClinicalPipelineResult(
        symbol="128940.KS",
        name="한미약품",
        trials=[
            ClinicalTrial(
                nct_id="NCT00001",
                title="Efpeglenatide in Obesity",
                phase="Phase 2",
                status="모집 중",
                condition="Obesity",
                primary_completion="2026-12",
            )
        ],
    )
    output = format_clinical_pipeline(result)
    assert "Phase 2" in output
    assert "모집 중" in output
    assert "2026-12" in output
    assert "🧬" in output


def test_format_no_forbidden_words():
    result = ClinicalPipelineResult(
        symbol="TEST",
        trials=[
            ClinicalTrial(
                title="Test Drug",
                phase="Phase 3",
                status="완료",
                condition="Cancer",
            )
        ],
    )
    output = format_clinical_pipeline(result)
    forbidden = ["성공 가능성 높음", "매수 권장", "확정 수익", "반드시 상승"]
    for word in forbidden:
        assert word not in output


def test_format_includes_variability_disclaimer():
    result = ClinicalPipelineResult(symbol="TEST", trials=[])
    output = format_clinical_pipeline(result)
    assert "변동성" in output or "확인 제한" in output


def test_format_cash_burn_note():
    result = ClinicalPipelineResult(
        symbol="TEST",
        trials=[],
        cash_burn_note="유상증자 1000억 공시 (공시 기반)",
    )
    output = format_clinical_pipeline(result)
    assert "현금소진" in output or "증자" in output


def test_format_partner_note():
    result = ClinicalPipelineResult(
        symbol="TEST",
        trials=[],
        partner_note="사노피 기술이전 계약 (공시 기반)",
    )
    output = format_clinical_pipeline(result)
    assert "파트너" in output or "기술이전" in output


def test_format_no_trial_shows_limitation():
    result = ClinicalPipelineResult(
        symbol="TEST",
        trials=[],
        data_limited=True,
        limitation_note="공개자료 기준 임상 정보 확인 제한",
    )
    output = format_clinical_pipeline(result)
    assert "확인 제한" in output


# ── DB extraction ─────────────────────────────────────────────────────────────


def test_extract_from_db_empty(tmp_path):
    from tele_quant.clinical_pipeline import _extract_from_db
    from tele_quant.db import Store

    store = Store(tmp_path / "test.db")
    signals, cash, partner, market = _extract_from_db("128940.KS", "한미약품", store)
    assert signals == []
    assert cash == ""
    assert partner == ""
    assert market == ""
