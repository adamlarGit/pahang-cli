from dataclasses import dataclass
import hashlib
import random
import re
from typing import Any

# Column coordinates for incomer and outgoing feeders
# LVDB 1: cable type in Row 45, board average in R50
# LVDB 2: cable type in Row 47, board average in R54
FEEDER_CHANNEL_COLUMNS: dict[str, str] = {
    "IN1": "D",
    "IN2": "E",
    "IN3": "G",
    "OT1": "I",
    "OT2": "J",
    "OT3": "K",
    "OT4": "L",
    "OT5": "M",
    "OT6": "N",
    "OT7": "O",
    "OT8": "P",
    "OT9": "Q",
    "OT10": "R",
}

# Sentinels indicating an inactive, spare, or unpopulated feeder way
INACTIVE_FEEDER_SENTINELS: frozenset[str] = frozenset({
    "",
    "-",
    "--",
    "---",
    "SPARE",
    "N/A",
    "NA",
    "NONE",
    "TIADA",
})


@dataclass(frozen=True)
class FeederChannelResolution:
    """Resolved Feeder Pillar / LVDB circuit way coordinate and label info."""

    pillar_index: int       # 1 for FP1/LVDB1, 2 for FP2/LVDB2
    channel: str            # "IN1".."IN3", "OT1".."OT10"
    feederno_label: str     # "INCOMING 1", "OUTGOING F1", etc.
    column_letter: str      # "D", "E", "G", "I".."R"
    cable_cell: str         # "D45", "I45" for FP1; "D47", "I47" for FP2
    board_temp_cell: str    # "R50" for FP1; "R54" for FP2


def resolve_feeder_channel(
    identifier: str,
    default_pillar_index: int = 1,
) -> FeederChannelResolution | None:
    """Resolve Feeder Pillar / LVDB feeder circuit way information.

    Supports:
        - MSMS meters: 'TH_FPIN1_AVG_PE13R' -> 'IN1', 'TH_FPOT2_MAX_PE13V' -> 'OT2'
        - CBM defect IDs: 'FP TX1 - OUTGOING F1' -> 'OT1' (pillar 1), 'FP TX2 - OUTGOING F3' -> 'OT3' (pillar 2)
        - Partial / bay texts: 'OUTGOING F1', 'OUTGOING F2', 'F1', 'F2', 'INC 1', 'INCOMING 1'
    """
    if not identifier or not identifier.strip():
        return None

    ident_upper = identifier.strip().upper()

    # Determine pillar index (1 or 2)
    if re.search(r"\b(?:FP\s*TX\s*2|LVDB\s*2|FP\s*2|TX\s*2)\b", ident_upper):
        pillar_idx = 2
    elif re.search(r"\b(?:FP\s*TX\s*1|LVDB\s*1|FP\s*1|TX\s*1)\b", ident_upper):
        pillar_idx = 1
    else:
        pillar_idx = default_pillar_index

    # Determine channel
    channel: str | None = None

    # 1. Check MSMS meter pattern
    meter_match = parse_feeder_meter(ident_upper)
    if meter_match:
        channel = meter_match[0]

    # 2. Check direct channel identifier
    if not channel and ident_upper in FEEDER_CHANNEL_COLUMNS:
        channel = ident_upper

    # 3. Check incoming feeder patterns
    if not channel:
        m_inc = re.search(r"\b(?:INCOMING|INCOMER|INC\.?)\s*(?:FEEDER\s*|F\s*)?([1-3])\b", ident_upper)
        if m_inc:
            channel = f"IN{m_inc.group(1)}"
        elif re.search(r"\bIN\s*([1-3])\b", ident_upper):
            m_in = re.search(r"\bIN\s*([1-3])\b", ident_upper)
            if m_in:
                channel = f"IN{m_in.group(1)}"
        elif re.search(r"\b(?:INCOMING|INCOMER)\b", ident_upper):
            channel = "IN1"

    # 4. Check outgoing feeder patterns
    if not channel:
        m_ot = re.search(r"\bOUTGOING\s*(?:FEEDER\s*|F\s*)?(\d+)\b", ident_upper)
        if m_ot:
            num = int(m_ot.group(1))
            if 1 <= num <= 10:
                channel = f"OT{num}"

    if not channel:
        m_fdr = re.search(r"\bFEEDER\s*(\d+)\b", ident_upper)
        if m_fdr:
            num = int(m_fdr.group(1))
            if 1 <= num <= 10:
                channel = f"OT{num}"

    if not channel:
        m_ot_direct = re.search(r"\bOT\s*(\d+)\b", ident_upper)
        if m_ot_direct:
            num = int(m_ot_direct.group(1))
            if 1 <= num <= 10:
                channel = f"OT{num}"

    if not channel:
        m_f = re.search(r"(?<![A-Z])F\s*(\d+)\b", ident_upper)
        if m_f:
            num = int(m_f.group(1))
            if 1 <= num <= 10:
                channel = f"OT{num}"

    if not channel or channel not in FEEDER_CHANNEL_COLUMNS:
        return None

    if channel.startswith("IN"):
        feederno_label = f"INCOMING {channel[2:]}"
    else:
        feederno_label = f"OUTGOING F{channel[2:]}"

    col = FEEDER_CHANNEL_COLUMNS[channel]
    cable_row = 45 if pillar_idx == 1 else 47
    board_temp_cell = "R50" if pillar_idx == 1 else "R54"

    return FeederChannelResolution(
        pillar_index=pillar_idx,
        channel=channel,
        feederno_label=feederno_label,
        column_letter=col,
        cable_cell=f"{col}{cable_row}",
        board_temp_cell=board_temp_cell,
    )


def parse_feeder_meter(meter_name: str) -> tuple[str, str] | None:
    """Parse a Feeder Pillar thermal meter into (feeder_channel, metric_suffix).

    Examples:
        'TH_FPIN1_AVG_PE13R' -> ('IN1', 'AVG')
        'TH_FPOT2_MAX_PE13V' -> ('OT2', 'MAX')
        'TH_FPOT10_DEL_PE13R' -> ('OT10', 'DEL')
        'TH_EARTH_AVG_PE13R' -> None
    """
    if not meter_name:
        return None
    m = re.match(r"^TH_FP(IN\d+|OT\d+)_(AVG|MAX|REF|DEL)", meter_name.strip().upper())
    if m:
        channel, metric = m.group(1), m.group(2)
        if channel in FEEDER_CHANNEL_COLUMNS:
            return channel, metric
    return None


def extract_board_average_temperature(cell_val: Any) -> float | None:
    """Extract numeric temperature from board average cell (e.g. 'AVG 28.5', 28.5).
    
    Returns float temperature or None if empty/unparseable/sentinel.
    """
    if cell_val is None:
        return None
    if isinstance(cell_val, (int, float)):
        return float(cell_val)
    norm = str(cell_val).strip()
    if not norm or "SERIAL" in norm.upper():
        return None
    m = re.search(r"[-+]?\d*\.?\d+", norm)
    if m:
        try:
            return float(m.group(0))
        except ValueError:
            return None
    return None


def is_active_feeder_cable(cable_val: Any) -> bool:
    """Return True if the cable cell value indicates an active feeder.
    
    A feeder is active if it contains a non-empty cable insulation type string
    (e.g., 'XLPE', 'PILC', 'ABC', 'BUSBAR', 'B/B') and is not an inactive sentinel.
    """
    if cable_val is None:
        return False
    norm = str(cable_val).strip().upper()
    if not norm:
        return False
    if norm in INACTIVE_FEEDER_SENTINELS:
        return False
    return True


def synthesize_feeder_thermal_readings(
    board_avg_temp: float,
    feeder_id: str,
    substation_type: str = "INDOOR",
    seed_key: str = "",
) -> dict[str, float]:
    """Synthesize AVG, MAX, REF, DEL readings for an active feeder.

    Args:
        board_avg_temp: Base average board temperature from R50 (FP1) or R54 (FP2).
        feeder_id: Identifier for the feeder channel (e.g. 'IN1', 'OT2').
        substation_type: 'INDOOR', 'ATTACH', 'PE' vs 'OUTDOOR', 'CS', 'PAT', 'POLE'.
        seed_key: Context string (substation, wonum, date) for deterministic seeding.

    Returns:
        Dict with keys: 'AVG', 'MAX', 'REF', 'DEL'.
    """
    raw_seed = f"{seed_key}:{feeder_id}"
    seed_int = int(hashlib.sha256(raw_seed.encode("utf-8")).hexdigest()[:16], 16)
    rng = random.Random(seed_int)

    sub_norm = str(substation_type or "").strip().upper()
    is_outdoor = any(kw in sub_norm for kw in ("OUTDOOR", "CS", "PAT", "POLE", "PE13O"))

    # Jitter range: indoor +/- 0.5°C, outdoor +/- 1.0°C
    max_jitter = 1.0 if is_outdoor else 0.5
    jitter = rng.uniform(-max_jitter, max_jitter)
    avg_temp = round(board_avg_temp + jitter, 1)

    # Delta T strictly between 0.2 and 0.8 (< 1.0)
    delta_t = round(rng.uniform(0.2, 0.8), 1)

    half_delta = round(delta_t / 2.0, 1)
    ref_temp = round(avg_temp - half_delta, 1)
    max_temp = round(ref_temp + delta_t, 1)

    # Ensure invariant delta_t = max_temp - ref_temp
    exact_delta = round(max_temp - ref_temp, 1)

    return {
        "AVG": avg_temp,
        "MAX": max_temp,
        "REF": ref_temp,
        "DEL": exact_delta,
    }

