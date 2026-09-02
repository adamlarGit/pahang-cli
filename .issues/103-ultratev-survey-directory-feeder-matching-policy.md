# Ticket 103: UltraTEV Survey Directory Asset Structure & Feeder Matching Policy

Labels: wayfinder:domain-modeling, hitl, state:closed

## Question

What deterministic matching rules should be enforced to pair a defective switchgear panel (e.g. `CKN00072 - TX 1 500KVA`, Panel 3, `INCOMING 1`) or transformer (e.g. `TX 1`, `TX 2`) with the corresponding feeder subfolder (`SWG/FEEDER_<N>/` or `TX/Transformer/` or `TX<N>/`) inside the extracted UltraTEV survey directory?

## Resolution

- **Switchgear Feeder Matching (3-Tier Precedence)**:
  1. **Tier 1 (Testsheet `panel_no`)**: Primary sequential panel index from Column A in `PCE Testsheet` accumulating across multi-page sheets (Sheet 1 = 1–4, Sheet 2 = 5–8, etc.) $\rightarrow$ maps directly to `SWG/FEEDER_<panel_no>/`.
  2. **Tier 2 (Explicit Digit Extraction)**: Extract digits from `equipment_id` / `panel_feeder_no` (e.g. `F02` $\rightarrow$ `2`) $\rightarrow$ maps to `SWG/FEEDER_2/`.
  3. **Tier 3 (Exact Subfolder Name)**: Match exact folder names (e.g. `SWG/INCOMING_1/`).
- **Transformer Survey Matching**:
  - 1-TX Substation: Matches `TX/Transformer/`.
  - Multi-TX Substation (e.g. 2 TXs): `TX 1` $\rightarrow$ `TX1/Transformer/` (or `TX1/`), `TX 2` $\rightarrow$ `TX2/Transformer/` (or `TX2/`).
- **Timestamp Run Selection**:
  - Scan candidate timestamp folders (`*_TEV/`, `*_Ultrasonic/`); pick the latest timestamp folder containing a valid payload (`eventData.js` / `ultrasonic_phase_plot.js`).
- **Dual Graph Embedding & Fallback Policy**:
  - When survey data exists, both `us.prpd` and `tev.prpd` graphs are always generated and embedded via Option B native Python engine regardless of defect technology type (IR, US, TEV).
  - Clean fallback (`""`) when survey data is missing/unsurveyed.
