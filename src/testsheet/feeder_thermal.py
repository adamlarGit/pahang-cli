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

