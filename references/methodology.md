# Methodology

## 1. Psychrometrics (`psychro.py`)
- Ideal-gas moist air per ASHRAE Fundamentals (2017), ch. 1. Saturation pressure uses Hyland–Wexler, over liquid water and over ice.
- Enthalpy is per kg of dry air, taking 0 °C dry air and 0 °C liquid water as the datum: h = 1006·T + W·(2.501e6 + 1860·T).
- Barometric pressure comes from altitude through the ICAO standard atmosphere.
- Supersaturated (fog) air: the vapour is capped at W_sat(T) and the excess is carried as liquid, h = cpa·T + Ws·(hfg + cpv·T) + (W − Ws)·cpw·T.
- Checked against:
  - PsychroLib, which agrees to ~1e-4.
  - CoolProp HAPropsSI, which is real-gas with an enhancement factor. It differs by up to 0.4 % in h and 0.6 % in W at 50 °C.

## 2. Merkel method (`thermal.merkel`)
- Merkel number: KaV/L = ∫ cpw dTw / (h_sat(Tw) − h_a). The air operating line is h_a = h_in + (L/G)·cpw·(Tw − Tc).
- Assumptions: Lewis factor 1, the evaporation loss is neglected, and the exit air is treated as saturated in enthalpy terms.
- Integration methods:
  - Gauss–Legendre with 40 points (default).
  - CTI 4-point Chebyshev at 0.1, 0.4, 0.6 and 0.9 of the range, which is what CTI ATC-105 and vendor fill curves use.
- `LG_max` is the L/G at which the air line touches the saturation curve. At that point Me becomes infinite.

### Validation against Perry's Chemical Engineers' Handbook (7th ed., Sec. 12), in `tests/test_perry.py`
| Case | Perry's | This code |
|---|---|---|
| Example 9: Chebyshev KaV/L, 105→85 °F, WB 78 °F, L/G 0.97 | 1.71 | 1.709 |
| Example 9: driving forces Δh₁–Δh₄ (Btu/lb) | 8.41 / 10.91 / 13.33 / 18.30 | 8.38 / 10.85 / 13.25 / 18.18 (≤ 0.7 %) |
| Counterflow statement: WB 78 °F, hot 95 °F, 5 °F approach, L/G 1 | 1.75 (rounded) | 1.726 |
| Example 10: Wood & Betts nomograph, KaV/L | 1.42 | 1.67. Perry's calls the nomograph approximate; its own Chebyshev method gives 1.67 |
| Example 10: cold water after the wet-bulb drops 70→50 °F | 70 °F | 68.3 °F (trend check only) |

## 3. Poppe method (`thermal.poppe`)
- Equations: Kloppers & Kröger, "Cooling tower performance evaluation: Merkel, Poppe, and e-NTU methods of analysis", *J. Eng. Gas Turbines Power* 127 (2005) 1–7, and Kloppers' PhD thesis (Stellenbosch, 2003).
- Integrated with fourth-order Runge–Kutta from the cold, air-inlet end to the hot end. The outlet humidity is iterated until it is self-consistent, because the local water flow is mw = mw_in − ma·(w_out − w).
- Lewis factor (Bosnjakovic): Lef = 0.865^0.667·(x − 1)/ln x, with x = (w_sw + 0.622)/(w + 0.622).
- The solver switches to the supersaturated equations once the air passes saturation.
- Outputs: Poppe Me, the exit air state (T, W, RH, fog), evaporation, and energy balance closure, which reaches 1e-9 in practice.
- Plume: visible if the straight mixing line between the exit air and the ambient air crosses the saturation curve.
- Consistent with the literature, Poppe gives a larger Me than Merkel for the same duty. Kloppers & Kröger also caution that a fill must be characterised with the same method used to predict it. Vendor KaV/L curves are Merkel-based, so the design L/G is set with Merkel and Poppe is used for the exit air and evaporation.

## 4. Tower characteristic, the "supply" (`fill.py`, `references/fill_library.json`)
The tower characteristic is Me_tower(L/G) = Me_fill + Me_rain + Me_spray.

| Zone | Model | Source |
|---|---|---|
| Film / low-clog film fill | C·(L/G)^−n·h^m | **GENERIC**, representative values; replace with vendor data |
| Grid splash fill | 0.3672·(L/G)^−0.2794·h^0.7 | Vitkovic & Dvorak, MCM'16, paper HTFF 127 (2016), eq. 2 |
| Rain zone | 0.066·(L/G)^−0.3684·H | same paper, eq. 3; tested at H 1.45–3.03 m and L/G 1.0–2.0 |
| Spray zone | 0 by default | conservative; vendor fill-test curves usually include the spray zone already |

- Fill loss coefficient: K = k·h·(Gw/Gw_ref)^d·(Ga/Ga_ref)^e, referred to the air dynamic pressure at the fill face. These coefficients are **generic**.
- The skill warns when the design is outside a correlation's tested range, exceeds a fill's temperature limit, or relies on generic data.
- The de Villiers–Kröger rain-zone correlation (Kröger 2004, *Air-Cooled Heat Exchangers and Cooling Towers*) is the more general alternative, for large towers with tall rain zones. It is not implemented, because its exact form could not be confirmed from an accessible source.

## 5. Design point, capability and rating (`thermal.py`, `thermal_design.py`)
- Design L/G: the point where supply meets demand, divided by the required capability. This follows CTI: a capability of C % means the tower cools C % of design flow at design conditions.
- Rating: for a fixed tower and L/G, find the cold-water temperature at which demand equals supply. Two modes:
  - fixed hot-water temperature
  - fixed range (fixed heat load)
- Perry's inputs for Phase 2 (Sec. 12, pp. 12-16 to 12-18):
  - Makeup: Wm = We + Wd + Wb (eq. 12-9).
  - Evaporation: We ≈ 0.00085·Wc·ΔT(°F), which is 0.153 %/K (eq. 12-10). This is the check value; Poppe gives the actual evaporation.
  - Blowdown: Wb = We/(cycles − 1) (eq. 12-12). Perry's form ignores drift. The skill will use Wb = We/(C − 1) − Wd, because drift also removes solids, and will report Perry's form as the conservative bound. Example 13 becomes the test case.
  - Fan static air power: SAHP = Q·hs·d/(33,000·12) (eq. 12-13).
  - Pump power: Pump bhp = gpm·ht/(3960·η) (eq. 12-14). Counterflow pump head is static lift plus nozzle pressure.
  - Typical figures: exit velocity ≤ 10.2 m/s; half-speed fan ≈ 17 % of full-speed power; cooling towers are seldom designed for approaches below 2.8 °C.
- Performance curves (ATC-105 format): cold water against wet-bulb at 90/100/110 % flow and 80/100/120 % range.
  - Phase 1 holds the dry-air mass flow constant.
  - Phase 2 adds the fan-law and air-density corrections.

## 6. Sizing and optimisation (`sizing.py`, `geometry.py`)

### Candidates and screening
- A candidate is a combination of: number of cells, cell length × width, fill depth, and fan diameter. Any of these that the spec fixes is held constant.
- Screening uses the Merkel design point, with the exit air taken as saturated at the exit enthalpy. Thermal results are cached by (fill depth, rain-zone height).
- The finalised design is re-solved with Poppe.

### Air-inlet height
The inlet height is the largest of three values, rounded up to 0.1 m:
- the minimum inlet height
- the air-travel rule: (W/2)/H ≤ `inlet_aspect_max` (with four-sided inlets, the travel is min(L, W)/2)
- the inlet-velocity rule

The inlet height, rain-zone height and L/G depend on each other, so they are iterated until consistent. This takes 2–3 passes.

### Elevations
All elevations are measured above the basin operating water level. Going up the tower:

| Elevation | Rule |
|---|---|
| Curb | +0.3 m |
| Air inlet | from the curb up by H_inlet |
| Fill bottom | inlet top + 0.15 m for supports |
| Fill top | fill bottom + fill depth |
| Nozzle | fill top + `nozzle_clearance_m` |
| Header centreline | nozzle + 0.15 m + D_header/2 |
| Eliminator | header top + 0.3 m |
| Fan deck | eliminator top + max(1.5 m, 0.4·D) |
| Stack top | fan deck + stack height; a velocity-recovery stack is max(1.8 m, 0.5·D) tall with a 7° half-angle |

### Constraints
A candidate is rejected if it breaks any of these:
- **Water loading:** inside both the spec limits and the fill's range.
- **Air velocities:** fill face, inlet and eliminator velocities within their limits.
- **Fan:**
  - annulus velocity within the allowed range
  - fits the cell with tip clearance
  - covers at least `min_cover` of the shorter side
  - static pressure and tip speed within limits
- **Fill material:** within its temperature limit.
- **Nozzle pressure:** within its range.

### Objective
Total present cost = capital cost + present value of the fan input power and the tower's share of pumping power.
- **Capital** covers: FRP framing (estimated per m³ of envelope), fill, eliminators, casing and deck, fan sets (cost per motor kW), basin, and a fixed cost per cell.
- **Energy:** valued over `years` at `rate`, using `hours_per_year`.
- **Sensitivity:** with cheap capital or expensive energy, the optimum moves to low air velocities (bigger towers, small fans). The report says so when this happens.

## 7. Air side and fan (`airside.py`, `fan.py`)

### Losses
Each loss is ΔP = K·ρv²/2 at its local velocity and density:
- **inlet:** ambient density
- **rain zone and fill:** the mean density in the fill
- **spray, eliminator and plenum:** exit-air density

A natural-draft credit, (ρ_in − ρ_out)·g·(z_stack_top − z_fill_top), is subtracted from the total.

### Fan pressures
- **Total pressure:** system static loss + stack loss + exit velocity pressure.
- **Velocity-recovery stack:** loss = (1 − η_diffuser)·(vp_fan − vp_exit).
- **Fan static pressure:** total pressure − velocity pressure in the annulus.

### Power and drive
- **Air power:** Q·ΔP_total. This equals Perry's eq. 12-13, SAHP = Q·hs·d/(33,000·12), which is tested.
- **Shaft power:** air power / η_total.
- **Motor:** the smallest IEC size ≥ margin × shaft power / η_gear.
- **Fan speed:** set by the design tip speed. The gear ratio is motor rpm / fan rpm.

### Plausibility
With the generic loss set, fan static pressure scales from about 125–175 Pa at fill velocities of 2.5–3 m/s down to about 65–90 Pa at 2 m/s. This is consistent with typical counterflow film-fill towers.

## 8. Water side (`hydraulics.py`, `basin.py`, `water_balance.py`)

### Distribution
- **Layout:** one riser per cell, outside the inlet face. A header runs across the cell (W), laterals branch both ways along L, and nozzles sit on a square grid.
- **Nozzle orifice:** the largest standard orifice whose pressure drop stays at or above the minimum nozzle pressure. Flow follows q = Cd·A·√(2Δp/ρ).
- **Pipe sizes:** the smallest DN that meets each velocity limit.
- **Friction:** the Colebrook factor from `fluids`. The header and laterals are manifolds with uniform outflow, so they use 1/3 of the full-flow loss.
- **Riser:** K = 2 elbows + valve + tee.
- **Tower pump head:** lift to the nozzle + nozzle Δp + pipe losses. This matches Perry's eq. 12-14 for pump bhp, which is tested.

### Basin
- **Water depth:** holds the retention volume, never less than the minimum depth.
- **Freeboard:** holds the drain-down volume: pipe volume, plus 0.03 m³ per m³ of fill, plus 5 s of water in flight.

### Pump sump (ANSI/HI 9.8)
- Bell velocity is 1.7 m/s.
- Submergence: S = D·(1 + 2.3·Fr).
- Floor clearance is 0.5·D.
- A sump pit is called for when the sump floor falls below the basin floor.

### Water balance
Perry's eqs. 12-9 to 12-12, with blowdown corrected for drift (B = E/(C − 1) − D). Perry's uncorrected form is also reported as the conservative bound, and Perry's Example 13 is reproduced in the tests.

## 9. FRP structure (`structure.py`, `frp.py`, `loads.py`, `bom.py`)

### Sources
- **ASCE/SEI 74-23**, *LRFD of Pultruded FRP Structures*. The values used here were taken from presentations, not from the standard itself:
  - M. Zarghamee (SGH), "New Standard for LRFD Design of Pultruded Structures", ACMA Composites Technology Day / Pultrusion Conference 2021. Source of:
    - time-effect factors λ
    - material adjustment factors C_M and C_T
    - the compression strength, serviceability and slenderness checks
    - the lateral-torsional buckling equation
    - Table 9.1.2: R = Cd = Ω₀ = 2 for an ordinary braced cooling tower
    - the rules for ordinary braced cooling towers
  - J. T. Mottram (Warwick), Composite Engineering Show 2014. Source of the resistance factors φ from the 2010 ASCE pre-standard: global buckling 0.70, local buckling 0.80, web crippling 0.70, pin bearing 0.80, net tension 0.50 (one bolt row) / 0.45 (multiple rows).
- **Assumed** φ values, pending a check against ASCE 74-23: material rupture 0.65, shear 0.70, shear-out 0.50, stainless-steel bolts 0.75 (AISC-type).

### Framing (ASCE 74 ordinary braced cooling tower)
- Column bays fall within `column_bay_m`, with at least 4 column lines.
- Columns are continuous from the basin floor to the fan deck.
- Beam tiers:
  - basin tie (curb level)
  - fill support
  - distribution support
  - eliminator support
  - fan deck
- Every column line is braced in both directions, with diagonals in alternate bays and alternating direction, in each storey at least 0.9 m tall.
- Model idealisation:
  - beams and columns rigidly connected
  - braces pin-ended
  - column bases pinned

### Loads
| Case | Content |
|---|---|
| D | Self weight, dry fill, pipes (30 % of the pipe water weight), wet eliminators (15 kg/m²), deck panels (30 kg/m²), casing (8 kg/m²), fan + gear + motor (25·D² + 8·kW kg) and the FRP stack (20 kg/m²) |
| F | Fill hold-up (`fill_hold_up_kg_m3`) and water in the distribution pipes |
| L | Fan-deck live load |
| S | 0.7·ground snow |
| W | Wind on the full casing face plus the stack. Constants: Kz from exposure, Kd 0.90, Ke from altitude, G 0.85, Cf 1.3–1.4 by h/D (cylinder 0.7 for the stack). |
| E | ELF base shear distributed by C_vx. The seismic weight includes the full hold-up water (conservative). |

### Combinations
LRFD combinations of ASCE 7-16 §2.3, with F carrying the dead-load factor. Each combination has its ASCE 74 time-effect factor λ:

| Combination | λ |
|---|---|
| 1.4(D+F) | 0.4 |
| 1.2(D+F) + 1.6L | 0.8 |
| 1.2(D+F) + 1.6S + (L or 0.5W) | 0.75 |
| full-wind and seismic combinations | 1.0 |

### Analysis
- PyNite 3D frame, linear.
- Each primary case is solved once, and the combinations are built by superposition.
- Internal forces at five stations along each member are rebuilt from PyNite's local end forces plus the member's uniform load. This reconstruction is checked against PyNite's own axial, shear and moment functions in the tests.

### Member check
Each member must satisfy R_u ≤ λ·φ·R_n, with R_n = C·R_o.

- **C factor** for a wet interior at the service temperature, which is the larger of the hot-water temperature and the exit-air temperature.
- **Compression:** min(φ_g·π²·E_L·A/(KL/r)², φ_l·F_local·A, 0.7·F_L^c·A).
- **Local buckling** (orthotropic plates):
  - outstanding flange: 4·G_LT·t²/b_f²
  - internal plate: (π²/6)(t/b)²[(√(E_L·E_T) + ν_LT·E_T)/(1 − ν_LT·ν_TL) + 2·G_LT]
- **Flexure:** the lowest of rupture, local buckling and lateral-torsional buckling.
- **Shear:** the lower of rupture and the web shear-buckling estimate.
- **Interaction:** linear axial + bending, with amplification 1/(1 − P/Pe) in compression.

### Serviceability
- **Slenderness:** KL/r ≤ 1.4·√(E_L·A/P_D).
- **Compression under service load:** P_s ≤ φ₀·Pe ≤ 0.3·F_L^c·A, with φ₀ = 1 − 500·δ₀/L.
- **Beam deflection:** ≤ L/180 under D+F+L.
- **Drift:** ≤ H/150 under 0.6W.

### Sizing
For every group that fails, the next iteration jumps straight to the smallest section that passes the current forces. The frame is then re-analysed until no group needs to change, usually in 2 iterations.

### Connections
- **Beam ends:** a pair of FRP clip angles.
- **Braces:** through-bolted to a 12 mm FRP gusset, in double shear.
- **Limit states checked:** bolt shear, pin bearing, net tension and shear-out. End distance is 2d and pitch is 4d.
- **Demand:** the maximum of force/λ over all combinations, so permanent loads keep their λ of 0.4.

### BOM
- The section sizes are applied to the framing of the whole row of cells.
- Columns run in one piece when the stock length allows.
- Beams are cut from stock lengths and spliced at columns. Each splice uses two FRP plates and 8 bolts, and develops 50 % of the beam's flexural capacity and 25 % of its tensile capacity, per ASCE 74.
- Hardware listed: clip angles, gussets, bolt sets by diameter and length, and column-base anchor brackets.
- Other components listed: envelope, fill and eliminators, nozzles and pipework, mechanical equipment, access, and basin connections.
- The FRP framing and connection weight replaces the Phase 2 volumetric estimate in the capital cost.

## 10. Drawings (`dxfsheet.py`, `drawings_dxf.py`)

### How the sheets are built
- **Geometry:** drawn 1:1 in millimetres in DXF modelspace (`$INSUNITS` = mm).
- **Sheet furniture:** the A1 frame, title block, notes box, text heights and dimension style are all scaled by the sheet scale 1:S. The DXF therefore opens at true size in any CAD program and prints to A1 at 1:S.
- **Scale:** the smallest standard scale from 1:1 to 1:1000 at which every view, plus its annotation margins, fits the view area.
- **Layers:** FRAME, TITLE, OUTLINE, THIN, HIDDEN (dashed), CENTER (grid), DIM, TEXT, STRUCT, BRACE, WATER, PIPE, EQUIP, HATCH, FILLPACK, AIR and CONCRETE, each with its own colour and lineweight.
- **Dimensions:** true associative-style ezdxf linear dimensions that measure model geometry (tested against the design values).
- **Level markers:** where labels fall close together, they are pushed apart and tied back to their marker with a leader.

### Sheets
| Sheet | Content |
|---|---|
| GA-001 | General arrangement: plan at fan deck (grid bubbles, columns, fans, risers, air inlets), side elevation (inlets, casing, stacks, handrails, ladder, risers, levels) and end elevation |
| GA-002 | Section A-A across a cell: every zone from the basin to the stack, nozzles, header and laterals, fan, gear, motor, air and water flows, and the full dimension chain. Section B-B along the row: two cells, plus a break and "similar" note when there are more. |
| ME-003 | Fan deck plan of a typical cell: stack, fan, gear reducer, drive shaft, motor, mechanical support and hatch. Also the stack detail and the fan/drive data table. |
| WD-004 | Distribution plan of a typical cell: header, laterals and nozzles with pitches. Also nozzle, pipe and hydraulics schedules. |
| CV-005 | Basin plan with wall hatching, column bases, pump suction bays to HI 9.8 and connections. Also the sump section with submergence, the basin data and the base reactions. |
| ST-006 | FRP framing plan for each tier of a typical cell, with a member mark on every beam, plus the member schedule from the BOM |
| ST-007 | Framing elevations of grid lines A and 1, showing the actual brace pattern from the analysis model, with tier levels, bay dimensions and the connection schedule |
| DS-008 | Datasheet (the same rows as `DATASHEET.md`) |

### Member marks
| Mark | Member |
|---|---|
| C1 | column |
| TB1 | basin tie beam |
| FB1 | fill support beam |
| DB1 | distribution support beam |
| EB1 | eliminator support beam |
| KB1 | fan deck beam |
| BR1-n | brace (n = cut-length variant) |

### Exports
- Each sheet goes to DXF (the CAD master), SVG (ezdxf drawing add-on), PDF and a PNG preview (PyMuPDF backend).
- All sheets are also merged into `<tag>_drawing_set.pdf`.
- **Checks:** every DXF passes the ezdxf audit with no errors. FreeCAD 1.1's own DXF importer reads the GA sheet; only one dimension-arrow SOLID entity is reported as unsupported.
