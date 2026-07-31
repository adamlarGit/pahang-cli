"""Tests for WhatsApp Report Generator Components."""

from datetime import datetime
from pathlib import Path
import pandas as pd
import pytest

from src.workflows.whatsapp import (
    WhatsAppReportFilter,
    WhatsAppReportTransformer,
    WhatsAppRawTuple,
    WhatsAppTargetEntity,
)
from src.whatsapp.models import WhatsAppReportResources

def test_whatsapp_filter_success():
    df = pd.DataFrame([
        {"PE NO": 1, "SUBSTATION NAME": "SSU CHEROH", "WO": "12345", "DATE": datetime(2026, 5, 1), "FL NUMBER": "CMRN/SUB1"},
        {"PE NO": 2, "SUBSTATION NAME": "PE PEKAN", "WO": "12346.0", "DATE": datetime(2026, 5, 2), "FL NUMBER": "PEKN/SUB1"},
    ])
    raw = WhatsAppRawTuple(
        substation_docx_files=[
            Path("001 SSU CHEROH (VI).docx"),
            Path("002 PE PEKAN.docx")
        ],
        total_pe_df=df,
        resources=None
    )
    
    stage = WhatsAppReportFilter()
    targets = stage.filter(raw)
    
    assert len(targets) == 2
    assert targets[0].substation_number == 1
    assert targets[0].substation_name == "SSU CHEROH"
    assert targets[0].defect == "VI"
    assert targets[0].msms == "12345"
    assert targets[0].fl_number == "CMRN/SUB1"

    assert targets[1].substation_number == 2
    assert targets[1].defect == "-"
    assert targets[1].msms == "12346"

def test_whatsapp_filter_no_dates():
    df = pd.DataFrame([
        {"PE NO": 1, "SUBSTATION NAME": "SSU CHEROH", "WO": "12345", "DATE": pd.NaT, "FL NUMBER": "CMRN/SUB1"},
    ])
    raw = WhatsAppRawTuple(
        substation_docx_files=[
            Path("001 SSU CHEROH (VI).docx"),
        ],
        total_pe_df=df,
        resources=None
    )
    
    stage = WhatsAppReportFilter()
    with pytest.raises(ValueError, match="No valid inspection dates found"):
        stage.filter(raw)

def test_whatsapp_transformer_success():
    targets = [
        WhatsAppTargetEntity(
            substation_number=1,
            substation_name="SSU CHEROH",
            defect="VI",
            msms="12345",
            raw_date=datetime(2026, 5, 1),
            fl_number="CMRN/SUB1"
        )
    ]
    
    resources = WhatsAppReportResources(
        quick_report_dir=Path("/qr"),
        save_dir=Path("/save"),
        template_path=Path("/template.docx"),
        total_pe_path=Path("/total_pe.xlsx"),
        station_mapping={"CMRN": "CAMERON HIGHLAND"}
    )
    
    stage = WhatsAppReportTransformer()
    plan = stage.transform(targets, resources)
    
    assert plan.substations_count == 1
    assert plan.station_name == "CAMERON HIGHLAND"
    assert plan.report_date == "01/05/2026"
    assert plan.context["date"] == "01/05/2026"
    assert plan.context["station"] == "CAMERON HIGHLAND"
    assert len(plan.context["items"]) == 1
    assert plan.context["items"][0]["name"] == "SSU CHEROH"
