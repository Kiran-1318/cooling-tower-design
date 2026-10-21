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

## loads (ASCE 7)
| field | default | notes |
|---|---|---|
| `code` | `ASCE 7-22` | |
| `risk_category` | `II` | |
| `wind_speed_m_s` | 45 | basic wind speed: 3-s gust, 10 m height |
| `exposure` | `C` | `B`, `C` or `D` |
| `seismic` | `{Ss, S1, site_class, Ie}` | |
| `ground_snow_kPa` | 0 | |

## costs
These rates drive the optimiser objective: capital cost plus the present value of fan and pump energy.
- Capital rates: `frp_per_kg`, `fill_per_m3`, `eliminator_per_m2`, `casing_per_m2`, `fan_set_per_kW`, `fixed_per_cell`, `basin_per_m2`.
- Energy and finance: `electricity_per_kWh`, `hours_per_year`, `years`, `rate`, `pump_efficiency`.

## grid
The optimiser's search space: `cells`, `cell_plan_m` (a list of `[L, W]` pairs), `fill_depth_m` and `fan_diameter_m`.

## rating_cases
Off-design cases rated on the final tower, each `{"label", "wet_bulb_C", "flow_factor", "range_C"}`.
