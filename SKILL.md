---
name: cooling-tower-design
description: Design a complete mechanical induced-draft counterflow cooling tower (multi-cell, pultruded FRP structure) from a cooling duty, and produce fabrication-oriented deliverables. The design covers CTI Merkel/Poppe thermal design, fill and rain-zone characteristics, a cost-optimised choice of cells, plan, fill depth and fan, the air side and fan/motor/gear, nozzles and headers and the tower's pump head, the basin with an HI 9.8 sump, the makeup/blowdown balance, an ASCE 7 wind/seismic and ASCE/SEI 74 LRFD FRP frame design with PyNite, and bolted connections. Deliverables are a fabrication BOM, an A1 drawing set (GA, sections, fan deck, distribution, basin, framing plans/elevations with member marks, datasheet) in DXF/SVG/PDF, a FreeCAD 3D model exported to STEP/FCStd, and a technical report. Use this skill whenever someone wants to design, size, select, rate or check a cooling tower, evaporative cooler or cooling-water tower for HVAC, chillers, power plants, refineries, cement or other process plants. Also use it for a KaV/L, L/G or Merkel number, a demand/supply curve, tower performance curves, makeup water or blowdown, fan power, an FRP cooling tower structure, cooling tower drawings, a GA, a BOM or a 3D/STEP model — even if they only give a flow rate and hot/cold water temperatures, or say "design the cooling tower for this plant".
---

# Cooling tower design (mechanical induced-draft counterflow, FRP)

This skill turns a cooling duty into a reviewable, fabrication-oriented tower design. It produces:
- a thermal design
- an optimised geometry
- an air side, fan and drive selection
- a water distribution system and basin
- a designed FRP frame with connections and a whole-tower BOM
- an A1 drawing set
- a 3D CAD model
- a report

The bundled package `scripts/ctdesign/` does the work behind one CLI. Your job is to:
1. get the design basis right
2. run the CLI
3. read the results critically
4. explain them

**Scope:** mechanical induced-draft counterflow towers with one or more cells in a single row, film or splash fill, a pultruded FRP structure and a concrete basin (civil works by others).

**Out of scope:** crossflow towers, natural-draft (hyperbolic) towers, forced-draft towers, hybrid wet/dry towers and steel or timber structures. If asked about these, say so, and offer the closest counterflow approximation only if it is clearly labelled as such.

## Workflow

### 1. Establish the design basis
These inputs are needed:
- **Water flow:** m³/h or kg/s.
- **Temperatures:** two of hot water, cold water, range and approach.
- **Site:**
  - design wet-bulb (plus the coincident dry-bulb if known)
  - altitude
  - wind speed and exposure
  - seismic S_DS/S_D1, or Ss/S1 and site class
  - risk category
- **Water quality:** cycles of concentration and TSS, which drive the fill choice.
- **Project metadata:** project name, client, site and tag.

Gaps:
- Fill missing values with the defaults in `references/design_guidance.md`, state every assumption, and keep going.
- Ask only for things that change the answer and cannot be defaulted:
  - which outlet temperature is the real requirement
  - whether the water is dirty or hot (> 50 °C), which rules out PVC film fill
  - the site's seismic hazard, if it is clearly significant
- If the user gives a spreadsheet, read it with `openpyxl` (`data_only=True`) and record which cell each input came from.

### 2. Write the spec JSON
- `references/spec_schema.md` lists every field and default.
- Copy the closest example and edit it:
  - `examples/hvac_2cell.json`: chiller plant, 1,000 m³/h, 2 fixed cells.
  - `examples/process_6cell.json`: refinery, 10,000 m³/h, the optimiser chooses the cells, plus rating cases.
- Put the spec in the user's project folder, not in the skill folder.
- Leave tower fields as `null` to let the optimiser choose. Fix them when the user has constraints such as plot size, cell count or a standard cell size.
- If the user has vendor data, put it in `tower.fill_override`, the `airside` K factors and `fan.total_efficiency`.

### 3. Run
Install the dependencies once:

```bash
pip install -r <skill>/requirements.txt
```

FreeCAD 1.x is also needed for the 3D model; it is found automatically or through `FREECADCMD`.

```bash
python <skill>/scripts/run_ct_design.py spec.json --out results                 # everything (~1-3 min + model)
python <skill>/scripts/run_ct_design.py spec.json --out results --stage thermal  # quick look at the thermal design
python <skill>/scripts/run_ct_design.py spec.json --out results --stage size     # then structure / drawings / model / report
python <skill>/scripts/run_ct_design.py spec.json --out results --params '{"cells":4,"L":12.2,"W":12.2,"depth":1.5,"fan_D":8.5}'
```

**Stages,** in order: `basis`, `thermal`, `size`, `structure`, `drawings`, `model`, `report`. Each later stage rebuilds its inputs from `data/design_results.json`, so stages can be re-run one at a time.

**Run times:**
- The optimiser takes about 1 s.
- The structure takes 5–20 s.
- The drawings take about 1 minute.
- The FreeCAD model takes 15–45 s plus a STEP re-check. Run large towers in the background.

**Outputs in `<out>/`:**

| File | Content |
|---|---|
| `REPORT.md` | Technical report |
| `DATASHEET.md` | Datasheet |
| `plots/` | Demand/supply, performance curves, Poppe profile, air-side losses, optimisation, structure utilisation |
| `drawings/` | 8 A1 sheets as DXF/SVG/PDF/PNG, plus `<tag>_drawing_set.pdf` |
| `model/<tag>_tower.step`, `.FCStd`, `preview.png` | 3D model |
| `data/` | `design_results.json` (including the model block), `candidates.csv.gz`, `structure.json`, `<tag>_BOM.xlsx/.csv`, `<tag>_datasheet.xlsx`, `model_summary.json`, `drawing_register.json` |

### 4. Review before presenting (this is where judgement matters)
Read REPORT.md §9 (Findings) and check at least the following.

**Duty**
- Q ≈ ṁ·cp·ΔT.
- Evaporation (Poppe) is within roughly ×0.9–1.2 of Perry's 0.153 %/K rule. It runs higher with hot, dry air.
- KaV/L and L/G lie in Perry's ranges (0.5–2.5 and 0.75–1.5).

**Data quality warnings**
- Generic fill coefficients, extrapolation of the fill or rain-zone correlation, and the fill temperature limit.
- Say plainly which numbers are vendor-dependent.

**Economics**
- If the optimiser chose a low fill velocity (about 2 m/s) because energy is expensive, present the cheapest higher-velocity alternative from §8 as well. Owners often value capital cost more.

**Fan**
- Static and total pressure, motor margin and tip speed.
- Fan static pressure scales with v²: about 125–175 Pa at 2.5–3 m/s, about 65–90 Pa at 2 m/s.

**Structure**
- Maximum UR per group, and the governing combination: 1.4(D+F) with λ = 0.4 is common for fill beams.
- Connection URs.
- Seismic Cs: R = 2 makes Cs high. Tell the user to confirm S_DS/S_D1.
- Any `violations`.

**3D model checks** (`data/model_summary.json`)
- FRP mass within about 2 % of the BOM.
- STEP valid, with the same volume as the built model.

**Drawings**
- Open `drawings/*_drawing_set.pdf`, or the PNGs, and look for colliding text before handing over.

If no feasible design exists, the CLI prints the most common rejection reasons. Relax the binding limit or widen `grid` deliberately, and tell the user which limit moved and why.

### 5. Variants
- Run each "what if" into its own output folder, for example `results_splash/` or `results_4cell/`. Never overwrite the baseline.
- Typical variants: a different fill, a fixed cell count or plan, a higher capability margin, another wet-bulb, or a VFD or two-speed study using `rating_cases`.
- Compare the decision metrics side by side: cells and plan, fill, L/G, fan kW, pump kW, capital cost, total present cost, makeup, FRP tonnage and maximum UR.

### 6. Present
1. Lead with the selected tower in one table: cells × plan, fill, height, fans and motors, L/G, KaV/L, air flow, pump head, makeup, FRP tonnage, capital cost and total present cost.
2. Then list the issues the user must act on: vendor data to obtain, seismic inputs, plume, the sump pit, and the assumed φ factors.
3. Then list the files.

The report's status stamp and limitations say what this is: a **design aid, not a stamped design**. Keep that framing.

## Things learned the hard way (keep these)
- **Capital cost must reflect size, not area alone.** Otherwise the optimiser fills the plot with tiny cells.
- **Connections need the time-effect factor.** Check them for demand/λ. A fill-beam connection checked at λ = 1 came out as 2 × M12; it needs 3 × M20 once the permanent-load λ = 0.4 is applied.
- **Size against every limit you report.** The first end-to-end trial (a cement plant) reported an ASCE 74 slenderness failure that the sizing loop had never designed for. Slenderness and service compression are now part of member sizing. P_D is the sustained load D + F: the fill's hold-up water is permanent, while live load is excluded.
- **Plate buckling must pass the isotropic limit.** The orthotropic internal-plate formula must reduce to k = 4 for an isotropic plate; the test suite guards this.
- **The model mass check works.** An early 3D build that filled the tubes solid showed FRP mass at 3× the BOM.
- **The model must be one solid per member.** Build each member as a single extruded section, not several plate solids; this kept the large tower's STEP to 83 MB instead of 123 MB.
- **ezdxf rendering:** use `ColorPolicy.COLOR` on a white background. `COLOR_SWAP_BW` makes colour-7 linework invisible.
- **Windows:** write every file with `encoding="utf-8"`.

## Reference files
- `references/spec_schema.md`: every spec field, default and CLI option. Read it when writing a spec.
- `references/design_guidance.md`: design conditions, fill selection, economics, water side, FRP structure rules of thumb, and the data-provenance table. Read it when defaulting inputs or reviewing results.
- `references/methodology.md`: every model and equation with its source, and the validation against Perry's examples, PsychroLib, CoolProp, ASCE 74 and HI 9.8. Use it as the basis for any "Methods" section.
- `references/fill_library.json`: fill, rain-zone and spray-zone coefficients, each marked PUBLISHED or GENERIC.
- `references/frp_profiles.json`: pultruded shapes, materials and the ASCE 74 adjustment factors.
