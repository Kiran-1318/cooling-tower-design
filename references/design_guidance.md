# Design guidance

This file covers practical judgement for writing a spec and for reviewing the results. Every rule of thumb names where it comes from: Perry's (7th edition, section 12), CTI practice, ASCE 7 or 74, ANSI/HI 9.8, or experience gathered while building this skill. Values that the code itself uses are cross-referenced to `spec_schema.md`.

## 1. Design conditions

### Wet-bulb temperature
- Use the site's 0.4 % or 1 % summer design wet-bulb (ASHRAE climatic data) unless the client specifies one.
- Add a recirculation/interference allowance (`site.recirculation_allowance_C`):

| Arrangement | Allowance |
|---|---|
| Single cell, open site | 0 K |
| Row of cells | 0.5 K |
| Long row, congested plot or a neighbouring tower downwind | 1.0 K |

### Dry-bulb temperature
Give the coincident dry-bulb. Poppe uses it for evaporation and exit air.
- Hot, dry air increases evaporation above Perry's rule of thumb (×1.1–1.2 is normal).
- Cold, humid air produces a visible plume.

### Approach
- Below 2.8 K (5 °F) is not economic and is rarely guaranteed (Perry). The loader rejects it.
- 3–6 K is normal.
- Every 1 K of approach saved costs a disproportionate amount of tower.

### Range
- HVAC: 4.5–6 K.
- Process and power: 8–12 K.
- Larger ranges need taller fill or a lower L/G.

### Thermal capability
Leave `limits.thermal_capability_min_pct` at 100 for a CTI-style guarantee. Use 105–110 % when fouling or future load growth is expected; the design L/G scales down by the same factor.

## 2. Thermal design (Merkel, Poppe, fill)
- **Typical ranges** for mechanical-draft towers (Perry): L/G 0.75–1.5 and KaV/L 0.5–2.5.
- **Results outside those ranges:** an L/G near `LG_max` means the approach is too tight for the air flow, and the demand curve goes vertical.
- **Fill choice follows water quality.** The skill warns when a limit is exceeded.

| Fill | TSS, mg/L | Max hot water | Notes |
|---|---|---|---|
| `film` (cross-fluted PVC, 19 mm) | < 25 | 50 °C | best performance; clean HVAC/chiller water |
| `low_clog_film` (vertical/offset flute) | < 100 | 52 °C | process and refinery water |
| `splash_grid` (PP grid) | up to ~500 | 60 °C | dirty water, high temperature, scaling; lower performance, needs a deeper fill |

- **Hot water above 50–55 °C:** PVC fill is unsuitable. Use PP or high-temperature fill and enter vendor data through `tower.fill_override`.
- **Vendor curves:** whenever you have them, enter them with `tower.fill_override` `{"C", "n", "m", "k", ...}`. The film coefficients shipped with the skill are GENERIC and are labelled as such in every output.
- **Rain zone:** the rain-zone correlation (Vitkovic & Dvorak 2016) was measured for H 1.45–3.03 m and L/G 1.0–2.0. Larger air inlets push H above 3 m, and the skill warns when they do. The extrapolation is mild but should be stated.
- **Merkel vs Poppe:** Merkel sets the design L/G, because vendor fill curves are Merkel-based. Poppe supplies the evaporation, exit air and plume figures. Poppe's KaV/L is normally 5–15 % above Merkel's, which is consistent with Kloppers & Kröger.

## 3. Sizing and economics
- **Water loading** is 8–20 m³/h·m² for film fill. Perry's 2–5 gpm/ft² (5–12 m³/h·m²) reflects older, deep splash towers.
- **Fill air velocity** is typically 2.0–3.0 m/s. The optimiser runs lower (≈2 m/s) when energy is valued highly, which happens with long `costs.years`, a high `electricity_per_kWh` or many `hours_per_year`. Present the cheapest higher-velocity alternative from the candidate table as well.
- **Cell size:** standard plan sizes are 4.9 / 6.1 / 7.3 / 9.8 / 12.2 / 14.6 m (16–48 ft). Fan diameter should be 0.55–0.9 of the cell side.
- **Fan tip speed:** ≤ 61 m/s, and 55 m/s by default for noise.
- **Velocity-recovery stack:** recovers part of the fan velocity pressure, which is worth it on fans of 4 m and above.
- **Fan control:**
  - Two-speed motors: at half speed, about 17 % of full power (Perry).
  - VFD or variable pitch: these track load.
  - Colder water usually saves more in the cooled process (chillers and condensers) than the fan energy saved in the tower (Perry).
- **Pump head:** the lift to the nozzles plus the nozzle pressure often exceeds the fan power (8–10 m on large towers). The optimiser counts it.

## 4. Water side and basin
- **Nozzles:** low-pressure spray nozzles at 20–70 kPa on a square grid of about 1.2 m. The skill picks the largest standard orifice that stays at or above the minimum pressure, which limits clogging.
- **Headers and laterals:** ≤ 2.4 and ≤ 1.8 m/s respectively. The riser is ≤ 2.5 m/s.
- **Basin retention:** at least 5 minutes of circulating flow. Add the system drain-back volume if the client gives one.
- **Freeboard:** must hold the drain-down volume when the pumps stop.
- **Pump sump:** sized to ANSI/HI 9.8 (bell velocity 1.7 m/s, S = D(1 + 2.3·Fr)). Confirm the bell diameter with the pump vendor.
- **Water balance:**
  - Cycles of concentration are normally 3–5 (Perry). Below 3, consider acid dosing.
  - Modern cellular eliminators reach 0.0005–0.001 % drift; Perry's 0.1–0.2 % is for old eliminators.
  - Blowdown is corrected for drift. Perry's uncorrected value is reported as the conservative bound.

## 5. Structure (pultruded FRP, ASCE/SEI 74)
- **Resin:** use vinyl ester for cooling towers (wet, warm, chemically treated water).
- **End-use factors:** moisture C_M (0.75 strength / 0.90 modulus) applies everywhere. C_T applies above 32 °C (90 °F), so at 43 °C a member keeps about 62 % of its strength.
- **Time-effect factor λ = 0.4** applies to the permanent combination 1.4(D+F), so members carrying only fill and water are creep-rupture critical. Fill-support beams often govern under 1.4(D+F), and the same applies to their connections; the skill applies demand/λ to the connections as well.
- **Seismic:** R = 2 (ordinary braced cooling tower) gives high Cs (S_DS·Ie/2).
  - Supply S_DS and S_D1 from the ASCE Hazard Tool.
  - ASCE 74 allows the seismic weight of the fill and water film to be reduced on the basis of testing.
- **Connections** are usually governed by shear-out. Keep end distance ≥ 2d and pitch ≥ 4d; the BOM lists bolts by diameter and grip.
- **Material data:** the material values are GENERIC, and four φ factors are ASSUMED (see `methodology.md` §9). Before construction, replace them with the pultruder's ASTM D7290 characteristic values (add an entry to `frp_profiles.json`) and check the φ factors against ASCE/SEI 74-23.

## 6. Data provenance (state this in every deliverable)
| Item | Basis |
|---|---|
| Psychrometrics | ASHRAE (checked against PsychroLib and CoolProp) |
| Merkel | CTI Chebyshev; checked against Perry's Example 9 (1.709 vs 1.71) |
| Poppe | Kloppers & Kröger (2005) |
| Grid fill and rain zone | Published: Vitkovic & Dvorak (2016) |
| Film and low-clog fill, all air-side K values except the fill, fan efficiency | **GENERIC**; use vendor data |
| Makeup, fan and pump power | Perry's eqs. 12-9 to 12-14 (tested) |
| Wind and seismic | ASCE 7-16 constants |
| FRP design | ASCE/SEI 74 values taken from the standard developers' presentations; four φ factors ASSUMED |
| Sump | ANSI/HI 9.8 |

## 7. Lessons learned while building the skill
- **Cost must reflect size.** An area-only capital cost drives the optimiser to many tiny cells. The objective here is weight- and plan-based capital cost plus the present value of fan and pump energy.
- **Read the warnings.** The rain-zone and fill-range warnings are real extrapolations, not noise.
- **Check the drawings visually.** Text collisions are the commonest defect, so open the PNG previews or the merged PDF before handing over.
- **3D model mass check.** FRP mass in the model is about 1–2 % above the BOM, because braces run centre-to-centre. A larger gap means a section-geometry error: an early build that filled the tubes solid showed a 3× gap.
- **Windows encoding.** Always write files with `encoding="utf-8"`.
