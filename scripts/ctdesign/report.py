"""REPORT.md (technical design report) and the CTI-style datasheet (DATASHEET.md + .xlsx)."""
from __future__ import annotations

import pandas as pd

from .spec import Basis


def _t(rows, head):
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def datasheet_rows(d: dict, b: Basis) -> list[tuple[str, str, str]]:
    s, g, th, fn, hy, bs, wb = (b.spec, d["geom"], d["thermal"]["selected"], d["fan"], d["hyd"], d["basin"],
                                d["water_balance"])
    ch = th["_char"] if "_char" in th else None
    p = s["project"]
    return [
        ("General", "Project / tag", f"{p['name']} / {p['tag']}"),
        ("General", "Client / site", f"{p['client']} / {p['site_name']}"),
        ("General", "Type", "Mechanical induced-draft counterflow, pultruded FRP structure"),
        ("Design conditions", "Circulating water flow", f"{b.V_w:,.0f} m3/h ({b.m_w:,.1f} kg/s)"),
        ("Design conditions", "Hot / cold water", f"{b.T_hot:.2f} / {b.T_cold:.2f} C"),
        ("Design conditions", "Range / approach", f"{b.range:.2f} / {b.approach:.2f} K"),
        ("Design conditions", "Design wet-bulb (incl. recirculation)", f"{b.T_wb:.2f} C"),
        ("Design conditions", "Design dry-bulb", "-" if b.T_db is None else f"{b.T_db:.1f} C"),
        ("Design conditions", "Barometric pressure", f"{b.P_atm / 1e3:.2f} kPa (altitude {s['site']['altitude_m']} m)"),
        ("Design conditions", "Heat rejected", f"{b.Q / 1e6:.2f} MW"),
        ("Thermal", "L/G (design)", f"{th['LG']:.3f}"),
        ("Thermal", "KaV/L required / supplied", f"{th['Me_demand']:.3f} / {th['Me_total']:.3f}"),
        ("Thermal", "Thermal capability", f"{th['capability_pct']:.1f} %"),
        ("Thermal", "Dry-air flow (total)", f"{th['G_dry_kg_s']:,.1f} kg/s"),
        ("Thermal", "Exit air (Poppe)", f"{th['T_air_out']:.1f} C, RH {100 * th['RH_out']:.0f} %"),
        ("Tower", "Cells x (L x W)", f"{g.cells} x ({g.L:.2f} x {g.W:.2f}) m"),
        ("Tower", "Overall plan (L x W)", f"{g.cells * g.L:.2f} x {g.W:.2f} m"),
        ("Tower", "Air inlet height", f"{g.H_inlet:.2f} m ({s['tower']['air_inlets'].replace('_', ' ')})"),
        ("Tower", "Fill", f"{s['tower']['fill_type']}, {g.depth:.2f} m deep, {g.plan_area * g.depth:,.0f} m3"),
        ("Tower", "Drift eliminator / drift rate", f"{s['tower']['drift_eliminator']} / {s['tower']['drift_rate_pct']} %"),
        ("Tower", "Fan deck / stack top elevation", f"{g.z['fan_deck']:.2f} / {g.z['stack_top']:.2f} m above basin water"),
        ("Fan & drive", "Fans", f"{g.cells} x {fn['D']:.1f} m dia, {fn['fan_rpm']:.0f} rpm, tip {fn['tip_speed']:.0f} m/s"),
        ("Fan & drive", "Air flow per fan", f"{fn['Q']:,.1f} m3/s at exit density"),
        ("Fan & drive", "Fan static / total pressure", f"{fn['dP_fan_static']:.0f} / {fn['dP_total']:.0f} Pa"),
        ("Fan & drive", "Absorbed (shaft) power per fan", f"{fn['P_shaft_kW']:.1f} kW"),
        ("Fan & drive", "Motor", f"{fn['motor_kW']} kW, {s['tower']['motor_poles']}-pole, {s['tower']['power_supply']}"),
        ("Fan & drive", "Gear ratio", f"{fn['gear_ratio']:.2f} : 1"),
        ("Fan & drive", "Stack", f"{fn['stack'].replace('_', ' ')}, {fn['stack_H']:.1f} m, exit dia {fn['stack_exit_D']:.2f} m"),
        ("Water distribution", "Nozzles per cell / orifice", f"{hy['nozzles_per_cell']} / {hy['orifice_mm']} mm at {hy['dp_nozzle_kPa']:.0f} kPa"),
        ("Water distribution", "Header / lateral / riser", f"DN{hy['header_DN']} / DN{hy['lateral_DN']} / DN{hy['riser_DN']}"),
        ("Water distribution", "Pump head at tower (static + dynamic)", f"{hy['pump_head_m']:.2f} m"),
        ("Water distribution", "Inlet pressure at header", f"{hy['inlet_pressure_kPa']:.0f} kPa(g)"),
        ("Basin", "Plan / depth (curb to floor)", f"{bs['plan_L']:.2f} x {bs['plan_W']:.2f} m / {bs['depth_m']:.2f} m"),
        ("Basin", "Operating water depth / volume", f"{bs['water_depth_m']:.2f} m / {bs['volume_operating_m3']:,.0f} m3"),
        ("Basin", "Pumps / bell dia / submergence", f"{bs['pumps_duty']}+{bs['pumps_standby']} / {bs['bell_D_m']:.2f} m / {bs['submergence_m']:.2f} m"),
        ("Basin", "Connections (makeup/overflow/blowdown/drain)",
         "DN{makeup_DN} / DN{overflow_DN} / DN{blowdown_DN} / DN{drain_DN}".format(**bs["connections"])),
        ("Water balance", "Evaporation / drift / blowdown", f"{wb['evaporation_m3_h']:.1f} / {wb['drift_m3_h']:.2f} / {wb['blowdown_m3_h']:.1f} m3/h"),
        ("Water balance", "Makeup", f"{wb['makeup_m3_h']:.1f} m3/h at {wb['cycles']:.1f} cycles"),
        ("Power", "Fans (input) / tower pumping", f"{g.cells * fn['P_input_kW']:.1f} / {hy['pump_kW']:.1f} kW"),
    ]


def write_datasheet(d: dict, b: Basis, md_path, xlsx_path):
    rows = datasheet_rows(d, b)
    lines = [f"# Cooling tower datasheet - {b.spec['project']['tag']} (rev {b.spec['project']['revision']})", ""]
    for sec in dict.fromkeys(r[0] for r in rows):
        lines += [f"## {sec}", _t([(r[1], r[2]) for r in rows if r[0] == sec], ["Item", "Value"]), ""]
    lines.append("Fill and fan data marked GENERIC in the report are indicative; final values come from vendor selections.")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    pd.DataFrame(rows, columns=["Section", "Item", "Value"]).to_excel(xlsx_path, index=False)


def structure_section(d: dict, b: Basis) -> list[str]:
    if "structure" not in d:
        return ["## 7. FRP structure", "", "Not run - add the `structure` stage.", ""]
    st, s = d["structure"], b.spec
    mt, se, summ = st["material"], st["seismic"], d["bom_summary"]
    L = ["## 7. FRP structure", "",
         "Pultruded FRP frame per ASCE/SEI 74 'ordinary braced cooling tower' (R = Cd = Omega0 = 2): columns continuous from "
         f"the basin floor to the fan deck, beams on every grid line at {len(st['grid']['tiers']) - 1} tiers, every column line "
         f"diagonally braced. Grid {len(st['grid']['xs'])} x {len(st['grid']['zs'])} lines over the analysed block of "
         f"{st['grid']['cells_modelled']} cell(s): {st['n_nodes']} nodes, {st['n_members']} members (PyNite 3D frame, linear, "
         "per-case superposition).", "",
         "Tiers: " + ", ".join(f"{n} {y:+.2f} m" for n, y in st["grid"]["tiers"]), "",
         f"Material {mt['name']} ({mt['basis'].split(' - ')[0]}), end-use factors for a wet interior at "
         f"{mt['T_service_C']:.0f} C: C = {mt['C_strength']:.3f} (strength), {mt['C_modulus']:.3f} (modulus); "
         f"E_L {mt['E_L_GPa']:.1f} GPa, F_Lc {mt['F_Lc_MPa']:.0f} MPa.", "",
         "Resistance factors: " + ", ".join(f"{k} {v} ({st['phi_source'][k]})" for k, v in st["phi"].items()) + ".", "",
         f"Loads: wind V = {st['wind']['V_m_s']} m/s exposure {st['wind']['exposure']}, q at the fan deck {st['wind']['qz_deck_Pa']:.0f} Pa; "
         f"seismic S_DS {se['SDS']:.3f}, S_D1 {se['SD1']:.3f} ({se['source']}), T {se['T']:.2f} s, Cs {se['Cs']:.3f}, "
         f"W {se['W_kN']:.0f} kN, V {se['V_kN']:.0f} kN on the analysed block; fill hold-up {s['structure']['fill_hold_up_kg_m3']} kg/m3, "
         f"deck live {s['structure']['fan_deck_live_kPa']} kPa, equipment {st['equipment_kg_per_cell']:.0f} kg + stack "
         f"{st['stack_kg_per_cell']:.0f} kg per cell. LRFD combinations of ASCE 7 with the ASCE 74 time-effect factor lambda.", "",
         _t([(g.replace("_", " "), v["section"], v["count"], f"{v['UR_max']:.2f}", v["governs"], v["combo"])
             for g, v in st["groups"].items()], ["Group", "Section", "Members", "Max UR", "Governs", "Combination"]), "",
         _t([(g.replace("_", " "), c["type"], f"{c['force_kN']:.1f}", f"{c['bolts']} x M{c['d_mm']}", f"{c['UR']:.2f}", c["governs"])
             for g, c in st["connections"].items()], ["Connection", "Type", "Force kN", "Bolts", "UR", "Governs"]), "",
         f"Serviceability: worst beam mid-span deflection {st['deflection']['mid_mm']:.1f} mm "
         f"({100 * st['deflection']['ratio_to_limit']:.0f} % of {st['deflection']['limit']}); drift {st['drift']['mm']:.1f} mm "
         f"(limit {st['drift']['limit_mm']:.0f} mm). ASCE 74 slenderness failures {st['slenderness_failures']}, serviceability "
         f"compression failures {st['serviceability_failures']}. Base reactions per column: down {st['base_reactions']['max_down_kN']:.1f} kN, "
         f"uplift {st['base_reactions']['max_uplift_kN']:.1f} kN, shear {st['base_reactions']['max_shear_kN']:.1f} kN.", "",
         "![structure](plots/06_structure_utilisation.png)", "",
         f"Bill of materials (whole tower): FRP framing {summ['frp_structure_kg'] / 1e3:.1f} t, connections "
         f"{summ['connections_kg'] / 1e3:.1f} t, total listed {summ['total_kg'] / 1e3:.1f} t "
         f"(Phase-2 volumetric estimate was {d['cost']['frp_kg_estimate'] / 1e3:.1f} t of FRP).", "",
         _t([(k, f"{v / 1e3:,.1f}") for k, v in summ["by_category_kg"].items()], ["BOM category", "t"]), ""]
    return L


def findings(d: dict, b: Basis) -> list[str]:
    th, fn, wb, air = d["thermal"]["selected"], d["fan"], d["water_balance"], d["air"]
    f = []
    for v in d["violations"]:
        f.append(f"**VIOLATION**: {v}")
    for w in d["warnings"]:
        f.append(f"Warning: {w}")
    r = wb["evaporation_m3_h"] / wb["evaporation_perry_rule_m3_h"]
    f.append(f"Evaporation (Poppe) is {r:.2f} x Perry's rule-of-thumb value "
             f"({wb['evaporation_m3_h']:.1f} vs {wb['evaporation_perry_rule_m3_h']:.1f} m3/h)"
             + (" - hot, dry design air adds sensible-to-latent conversion." if r > 1.05 else "."))
    f.append(f"Poppe energy balance closes to {abs(th['energy_balance_err']):.1e}.")
    if th["plume_visible"]:
        f.append("A visible plume is expected at design conditions.")
    f.append("Winter plume is likely whenever the ambient air is cold and humid; check with a rating case if it matters for the site.")
    if air["v_fill"] < 2.2:
        f.append(f"The optimiser chose a low fill air velocity ({air['v_fill']:.2f} m/s): energy is cheap to save "
                 f"over {b.spec['costs']['years']} years at {b.spec['costs']['electricity_per_kWh']}/kWh. A smaller, "
                 "higher-velocity tower trades capital for fan power; see the candidate table.")
    if fn["dP_fan_static"] < 100:
        f.append(f"Fan static pressure is modest ({fn['dP_fan_static']:.0f} Pa) because the air side uses GENERIC loss "
                 "coefficients and a low fill velocity; vendor fill/eliminator curves can raise it materially. "
                 f"The motor carries a {100 * (b.spec['fan']['motor_margin'] - 1):.0f} % margin.")
    if "structure" in d:
        st = d["structure"]
        for v in st["violations"]:
            f.append(f"**STRUCTURE VIOLATION**: {v}")
        top = max(st["groups"].items(), key=lambda kv: kv[1]["UR_max"])
        f.append(f"Structure: highest utilisation {top[1]['UR_max']:.2f} in the {top[0].replace('_', ' ')}s "
                 f"({top[1]['governs']}, {top[1]['combo']}). Members governed by 1.4(D+F) are creep-rupture critical (lambda 0.4).")
        if st["seismic"]["Cs"] >= 0.2:
            f.append(f"Seismic Cs = {st['seismic']['Cs']:.3f} with R = 2 is high and drives the braces; confirm S_DS/S_D1 with the "
                     "ASCE Hazard Tool and consider a testing-based reduction of the fill/water seismic weight (ASCE 74).")
        f.append("FRP material values are GENERIC and several phi factors are ASSUMED - confirm with the selected pultruder and ASCE/SEI 74-23.")
    if d["basin"]["sump_pit"]:
        f.append(f"Pump suction needs a sump pit {d['basin']['sump_pit_depth_below_basin_m']:.2f} m below the basin floor (HI 9.8 submergence).")
    return f


def write_report(d: dict, b: Basis, df: pd.DataFrame, path, files: dict):
    s, g, th, fn, hy, bs, wb, air = (b.spec, d["geom"], d["thermal"]["selected"], d["fan"], d["hyd"], d["basin"],
                                     d["water_balance"], d["air"])
    p = s["project"]
    L = [f"# {p['name']} - {p['tag']}: cooling tower design report", "",
         f"Rev {p['revision']}. Mechanical induced-draft counterflow, pultruded FRP. Generated by the "
         "`cooling-tower-design` skill (Phases 1-2: thermal, sizing, air side, fan, water side, basin).", "",
         "## 1. Design basis", "",
         _t([("Circulating water", f"{b.V_w:,.0f} m3/h"), ("Hot / cold water", f"{b.T_hot:.2f} / {b.T_cold:.2f} C"),
             ("Range / approach", f"{b.range:.2f} / {b.approach:.2f} K"),
             ("Design wet-bulb", f"{s['site']['design_wet_bulb_C']} C + {s['site']['recirculation_allowance_C']} K recirculation = {b.T_wb:.2f} C"),
             ("Design dry-bulb", "-" if b.T_db is None else f"{b.T_db} C"),
             ("Barometric pressure", f"{b.P_atm / 1e3:.2f} kPa"), ("Heat rejected", f"{b.Q / 1e6:.2f} MW"),
             ("Required capability", f"{s['limits']['thermal_capability_min_pct']} %")], ["Item", "Value"]), "",
         "## 2. Selected design", "",
         _t([("Cells", f"{g.cells} x {g.L:.2f} x {g.W:.2f} m (plan {g.plan_area:,.0f} m2)"),
             ("Fill", f"{s['tower']['fill_type']}, {g.depth:.2f} m"),
             ("Air inlet", f"{g.H_inlet:.2f} m (set by the {g.inlet_rule} rule)"),
             ("Water loading", f"{b.V_w / g.plan_area:.1f} m3/h.m2"),
             ("L/G", f"{th['LG']:.3f}"), ("Fill face velocity", f"{air['v_fill']:.2f} m/s"),
             ("Fans", f"{g.cells} x {fn['D']:.1f} m, {fn['motor_kW']} kW motors"),
             ("Overall height", f"{g.z['stack_top']:.2f} m above basin water level"),
             ("Fan + pump power", f"{d['cost']['energy_kW']:.0f} kW"),
             ("Capital (estimate)", f"{d['cost']['capex_total']:,.0f} {s['costs']['currency']}"),
             ("Total present cost", f"{d['cost']['total_present_cost']:,.0f} {s['costs']['currency']}")], ["Item", "Value"]), "",
         "## 3. Thermal design", "",
         f"Merkel demand at the design L/G is KaV/L = {th['Me_demand']:.3f} (CTI 4-point Chebyshev "
         f"{th['Me_demand_chebyshev']:.3f}). The tower supplies {th['Me_total']:.3f} = fill {th['Me_fill']:.3f} + rain zone "
         f"{th['Me_rain']:.3f} (H = {th['H_rain']:.2f} m) + spray {th['Me_spray']:.3f}; capability {th['capability_pct']:.1f} %.", "",
         f"Poppe: KaV/L {th['Me_poppe']:.3f}; exit air {th['T_air_out']:.1f} C, W {1e3 * th['W_out']:.1f} g/kg, RH "
         f"{100 * th['RH_out']:.0f} %{', supersaturated' if th['supersaturated_out'] else ''}; evaporation "
         f"{th['evap_kg_s']:.2f} kg/s ({th['evap_pct']:.2f} % of flow).", "",
         "![demand vs supply](plots/01_demand_supply.png)", "", "![performance](plots/02_performance_curves.png)", "",
         "![poppe](plots/03_poppe_profile.png)", ""]
    if d["thermal"]["ratings"]:
        L += ["Rating cases (fixed tower, constant dry-air flow):", "",
              _t([(r["label"], f"{r['T_wb']:.1f}", f"{r['T_hot']:.2f}", f"{r['T_cold']:.2f}", f"{r['approach']:.2f}")
                  for r in d["thermal"]["ratings"]], ["Case", "WB C", "Hot C", "Cold C", "Approach K"]), ""]
    L += ["## 4. Air side and fan", "",
          _t([(r["item"], f"{r['K']:.2f}", f"{r['v']:.2f}", f"{r['rho']:.3f}", f"{r['dP']:.1f}") for r in air["rows"]]
             + [("natural-draft credit", "", "", "", f"-{air['buoyancy_credit']:.1f}"),
                ("stack loss", "", "", "", f"{fn['dP_stack']:.1f}"),
                ("exit velocity pressure", "", f"{fn['v_exit']:.2f}", "", f"{fn['vp_exit']:.1f}"),
                ("**fan total pressure**", "", "", "", f"**{fn['dP_total']:.1f}**")],
             ["Item", "K", "v m/s", "rho kg/m3", "dP Pa"]), "",
          f"Fan: {fn['D']:.1f} m, {fn['Q']:.1f} m3/s, annulus velocity {fn['v_fan']:.2f} m/s, static {fn['dP_fan_static']:.0f} Pa, "
          f"shaft {fn['P_shaft_kW']:.1f} kW at a GENERIC total efficiency of {100 * s['fan']['total_efficiency']:.0f} %; "
          f"{fn['fan_rpm']:.0f} rpm (tip {fn['tip_speed']:.0f} m/s), gear ratio {fn['gear_ratio']:.2f}, motor {fn['motor_kW']} kW.", "",
          "![pressure](plots/04_pressure_breakdown.png)", "",
          "## 5. Water distribution", "",
          _t([("Nozzles per cell", f"{hy['nozzles_per_cell']} ({hy['laterals_per_cell']} laterals x {hy['nozzles_per_lateral']})"),
              ("Flow per nozzle / orifice", f"{hy['q_nozzle_m3_h']:.2f} m3/h / {hy['orifice_mm']} mm"),
              ("Nozzle pressure", f"{hy['dp_nozzle_kPa']:.1f} kPa"),
              ("Header", f"DN{hy['header_DN']}, {hy['v_header']:.2f} m/s, dP {hy['dp_header_kPa']:.2f} kPa"),
              ("Laterals", f"DN{hy['lateral_DN']}, {hy['v_lateral']:.2f} m/s, dP {hy['dp_lateral_kPa']:.2f} kPa"),
              ("Riser", f"DN{hy['riser_DN']}, {hy['v_riser']:.2f} m/s, dP {hy['dp_riser_kPa']:.2f} kPa"),
              ("Pump head attributable to the tower", f"{hy['pump_head_m']:.2f} m ({hy['pump_kW']:.1f} kW)")], ["Item", "Value"]), "",
          "## 6. Basin and water balance", "",
          _t([("Plan", f"{bs['plan_L']:.2f} x {bs['plan_W']:.2f} m"), ("Depth curb-to-floor", f"{bs['depth_m']:.2f} m"),
              ("Operating water depth", f"{bs['water_depth_m']:.2f} m ({bs['volume_operating_m3']:,.0f} m3)"),
              ("Drain-down volume", f"{bs['drain_down_m3']:.1f} m3 (freeboard {bs['freeboard_m']:.2f} m)"),
              ("Pump bell / submergence (HI 9.8)", f"{bs['bell_D_m']:.2f} m / {bs['submergence_m']:.2f} m"),
              ("Evaporation (Poppe)", f"{wb['evaporation_m3_h']:.1f} m3/h"),
              ("Drift", f"{wb['drift_m3_h']:.2f} m3/h"),
              ("Blowdown (drift-corrected / Perry)", f"{wb['blowdown_m3_h']:.1f} / {wb['blowdown_perry_m3_h']:.1f} m3/h"),
              ("Makeup (drift-corrected / Perry)", f"{wb['makeup_m3_h']:.1f} / {wb['makeup_perry_m3_h']:.1f} m3/h")], ["Item", "Value"]), ""]
    L += structure_section(d, b)
    L += ["## 8. Optimisation", ""]
    if len(df):
        ok = df[df.feasible.astype(bool)].nsmallest(10, "TPC")
        L += [f"{len(df):,} candidates, {int(df.feasible.sum()):,} feasible. Ten cheapest:", "",
              _t([(int(r.cells), f"{r.L}x{r.W}", r.depth, r.fan_D, f"{r.LG:.2f}", f"{r.v_fill:.2f}",
                   f"{r.energy_kW:.0f}", f"{r.capex / 1e3:,.0f}", f"{r.TPC / 1e3:,.0f}") for r in ok.itertuples()],
                 ["Cells", "Cell m", "Fill m", "Fan m", "L/G", "v_fill", "kW", "Capex k", "TPC k"]), "",
              "Most common rejection reasons:", "",
              _t([(k, v) for k, v in df.violations[df.violations != ""].str.split("; ").explode().value_counts().head(8).items()],
                 ["Reason", "Candidates"]), "", "![optimisation](plots/05_optimisation.png)", ""]
    L += [("Capital cost breakdown (FRP structure from the BOM weight):" if "structure" in d else
           "Capital cost breakdown (estimate; FRP weight from a per-m3 factor until the structure stage runs):"), "",
          _t([(k.replace("_", " "), f"{v:,.0f}") for k, v in d["cost"]["capex"].items()], ["Item", s["costs"]["currency"]]), "",
          "## 9. Findings", ""] + [f"- {x}" for x in findings(d, b)] + ["",
          "## 10. Limitations", "",
          "- Film-fill coefficients, all air-side loss coefficients except the fill, and the fan efficiency are GENERIC. "
          "Use vendor fill, eliminator and fan curves before purchase (spec `tower.fill_override`, `airside`, `fan`).",
          "- The rain-zone correlation is a measured test-cell fit (Vitkovic & Dvorak 2016) and is extrapolated outside H 1.45-3.03 m, L/G 1.0-2.0.",
          "- Ratings and performance curves hold the dry-air mass flow constant; fan-law/density corrections are not yet applied.",
          *(["- FRP structure weight and cost are a volumetric estimate; run the `structure` stage for the framed structure and BOM."]
            if "structure" not in d else
            ["- Structural design aid only, not a stamped design. Material values and the phi factors marked ASSUMED must be confirmed "
             "against the manufacturer's ASTM D7290 characteristic values and ASCE/SEI 74-23 before construction.",
             "- Joints are modelled rigid (beams/columns) and pinned (braces); fan dynamic loads, thermal expansion, "
             "erection loads and ice are not analysed. Seismic weight conservatively includes the full fill hold-up water."]),
          "- Basin civil design (concrete, reinforcement) is by others; dimensions here are hydraulic.", "",
          "## 11. Deliverables", "", _t(list(files.items()), ["File", "Content"]), ""]
    path.write_text("\n".join(L), encoding="utf-8")
