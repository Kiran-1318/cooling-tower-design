# Spec schema

A spec is one JSON file. Anything you leave out takes the default from `DEFAULT_SPEC` in
`scripts/ctdesign/spec.py`. All units are SI: °C, m, m³/h, kg/s, kPa, m/s.

## project
`name`, `tag` (e.g. `CT-101`; used as the drawing-number prefix), `client`, `site_name`, `date`, `revision`, `drawn_by`.

## site
| field | default | notes |
|---|---|---|
| `design_wet_bulb_C` | **required** | the ambient design wet-bulb |
| `recirculation_allowance_C` | 0.0 | added to the wet-bulb. Use 0.5–1.0 K for long rows of cells or a congested plot |
| `altitude_m` | 0 | gives the barometric pressure from the ICAO standard atmosphere |
| `P_atm_kPa` | null | overrides `altitude_m` |
| `design_dry_bulb_C` | null | sets the inlet humidity for the Poppe method; if absent, the inlet air is taken as saturated at the wet-bulb |

## duty
- `water_flow_m3_h` (at the hot-water temperature) or `water_flow_kg_s`: one is required.
- Temperatures: give two of `hot_water_C`, `cold_water_C`, `range_C` and `approach_C`. At least one of the two must be a temperature or the approach. If you give more than two, they must be consistent to within 0.05 K.
- The loader stops with an error if the approach is below `limits.approach_min_C`.

## tower
Leave a field as `null` and the optimiser chooses it from `grid`. Give a value and it is fixed.

| field | default | notes |
|---|---|---|
| `cells` | null | number of cells in one row |
| `cell_length_m`, `cell_width_m` | null | plan size of one cell |
| `fill_type` | `film` | key into `fill_library.json`: `film`, `low_clog_film`, `splash` |
| `fill_depth_m` | null | |
| `fill_override` | null | vendor data: `{"C":..,"n":..,"dp":{...}}`. Use it whenever you have vendor curves |
| `air_inlet_height_m` | null | |
| `air_inlets` | `two_sides` | `two_sides` (a row of cells) or `four_sides` (a stand-alone cell) |
| `drift_eliminator` | `cellular` | `cellular` or `blade` |
| `drift_rate_pct` | 0.0005 | |
| `fan_diameter_m` | null | |
| `fan_stack` | `velocity_recovery` | `straight` or `velocity_recovery` |
| `fan_stack_height_m` | null | |
| `motor_poles` | 4 | |
| `power_supply` | `415V/3ph/50Hz` | |
| `basin` | `concrete` | `concrete` (civil works by others) or `frp` |
| `basin_depth_m` | null | |

More `tower` fields:

| field | default | notes |
|---|---|---|
| `inlet_louvers` | false | rain-trap louvers; when true, `airside.K_louver` is added at the inlet |
| `nozzle_pitch_m` | 1.2 | pitch of the square nozzle grid |
| `nozzle_clearance_m` | 0.6 | distance from the nozzle orifice to the top of the fill |

## airside (GENERIC loss coefficients)
Each K multiplies the velocity pressure ρv²/2 at the stated local velocity.

| field | default | velocity it applies to |
|---|---|---|
| `K_inlet` | 1.5 | inlet face |
| `K_louver` | 1.0 | inlet face, added only with louvers |
| `K_rain_per_m` | 1.2 | fill face, multiplied by the rain-zone height |
| `K_fill_support` | 0.5 | fill face |
| `K_spray` | 1.0 | plan velocity at exit density |
| `K_eliminator` | `{cellular: 2.5, blade: 4.0}` | plan velocity at exit density |
| `K_plenum` | 0.3 | fan annulus |

Two more fields shape the velocity-recovery stack:
- `stack_diffuser_eff` (0.65): its static regain.
- `stack_half_angle_deg` (7): its cone half-angle.

Replace any of these with vendor data when you have it.

## fan
| field | default | notes |
|---|---|---|
| `total_efficiency` | 0.75 | GENERIC |
| `gear_efficiency` | 0.95 | |
| `motor_efficiency` | 0.94 | |
| `motor_margin` | 1.10 | motor rating ≥ margin × the absorbed power at design |
| `hub_ratio` | 0.2 | |
| `tip_speed_design_m_s` | 55 | |
| `fan_velocity_m_s` | [6, 12] | allowed velocity through the fan annulus |
| `min_cover` | 0.55 | fan diameter ≥ min_cover × the shorter cell side |
| `tip_clearance_m` | 0.3 | cell side ≥ D + 2 × clearance |

## water_system
| field | default | notes |
|---|---|---|
| `pumps_duty`, `pumps_standby` | 2, 1 | |
| `header_velocity_max_m_s` | 2.4 | |
| `lateral_velocity_max_m_s` | 1.8 | |
| `riser_velocity_max_m_s` | 2.5 | |
| `pipe_roughness_mm` | 0.05 | |
| `nozzle_Cd` | 0.85 | |
| `basin_min_water_depth_m` | 1.0 | |
| `basin_freeboard_min_m` | 0.3 | |
| `drain_time_h` | 4 | |

## limits
| field | default |
|---|---|
| `approach_min_C` | 2.8 |
| `water_loading_m3_h_m2` | [8, 20] |
| `fill_air_velocity_m_s` | [1.8, 3.5] |
| `air_inlet_velocity_max_m_s` | 4.0 |
| `fan_tip_speed_max_m_s` | 61 |
| `fan_static_max_Pa` | 250 |
| `eliminator_velocity_max_m_s` | 3.5 |
| `nozzle_pressure_kPa` | [20, 70] |
| `thermal_capability_min_pct` | 100 |
| `basin_retention_min` | 5 |
| `inlet_aspect_max` | 3.0 |
| `inlet_height_min_m` | 1.5 |

`inlet_aspect_max` caps the ratio of air travel (W/2, the distance from the inlet face to the cell centre) to inlet height.

## water
- `cycles_of_concentration` (default 4)
- `makeup_tds_mg_L` (optional)

## structure
| field | default | notes |
|---|---|---|
| `material` | `frp_pultruded` | |
| `profile_library` | `frp_profiles.json` | |
| `column_bay_m` | [1.8, 2.4] | the allowed bay range |
| `fastener_material` | `SS316` | |
| `fill_hold_up_kg_m3` | 150 | wet fill plus a fouling allowance, carried by the fill supports |
| `fan_deck_live_kPa` | 2.4 | |
| `casing` | `frp_corrugated` | |

More `structure` fields:

| field | default | notes |
|---|---|---|
| `frp_material` | `vinyl_ester_generic` | key into `frp_profiles.json` materials; `polyester_generic` is also available, or add the pultruder's own characteristic values |
| `model_cells_max` | 2 | towers with more cells are analysed as a representative block of this many cells, and the member sizes are applied to every cell |
| `deflection_limit` | 180 | beam deflection limit L/n under D+F+L |
| `drift_limit` | 150 | frame drift limit H/n under 0.6W |
| `out_of_straightness` | 0.001 | δ₀/L for the ASCE 74 serviceability compression check |
| `stock_length_m` | 6.1 | beam stock length; beams are spliced at columns |
| `column_stock_length_m` | 12.2 | |

## loads (ASCE 7)
| field | default | notes |
|---|---|---|
| `code` | `ASCE 7-22` | |
| `risk_category` | `II` | |
| `wind_speed_m_s` | 45 | basic wind speed: 3-s gust, 10 m height |
| `exposure` | `C` | `B`, `C` or `D` |
| `seismic` | `{Ss, S1, site_class, Ie}` | |
| `ground_snow_kPa` | 0 | |
| `Kd` | 0.90 | wind directionality factor |

The wind and seismic constants follow ASCE 7-16.

More `seismic` fields:
- Give `SDS` and `SD1` directly whenever you can, taken from the ASCE Hazard Tool (which also covers 7-22). Otherwise they are derived from Ss, S1 and the site class using the ASCE 7-16 Fa/Fv tables.
- `R`, `Cd` and `Omega0` default to 2, the ASCE/SEI 74 values for an ordinary braced cooling tower.
- `TL` defaults to 8 s.

## costs
These rates drive the optimiser objective: capital cost plus the present value of fan and pump energy.
- Capital rates: `frp_per_kg`, `fill_per_m3`, `eliminator_per_m2`, `casing_per_m2`, `fan_set_per_kW`, `fixed_per_cell`, `basin_per_m2`.
- Energy and finance: `electricity_per_kWh`, `hours_per_year`, `years`, `rate`, `pump_efficiency`.

There is one more cost field: `frp_kg_per_m3` (default 9). It estimates the FRP framing weight per m³ of cell envelope, and Phase 3 replaces it with the framed structure.

## grid
The optimiser's search space: `cells`, `cell_plan_m` (a list of `[L, W]` pairs), `fill_depth_m` and `fan_diameter_m`.

## freecad (optional)
- `freecadcmd`: the path to FreeCAD's command-line executable.
- It is used only when FreeCAD is not found automatically, which happens when it is not in `FREECADCMD`, the standard install paths or `PATH`.

## rating_cases
Off-design cases rated on the final tower, each `{"label", "wet_bulb_C", "flow_factor", "range_C"}`.
