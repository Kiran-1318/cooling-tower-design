"""Fan, stack and drive: pressures, power, speed, gearbox and motor selection.

Fan total pressure = system static loss upstream of the fan + stack loss + exit velocity pressure.
A velocity-recovery stack regains part of the fan velocity pressure (diffuser efficiency);
a straight stack discharges at the fan velocity. Fan static pressure (CTI/AMCA sense) is the
total pressure minus the velocity pressure in the fan annulus. Shaft power uses a GENERIC
total efficiency: the actual fan, blade count and pitch come from the fan vendor.
"""
from __future__ import annotations

import math

IEC_KW = [0.75, 1.1, 1.5, 2.2, 3, 4, 5.5, 7.5, 11, 15, 18.5, 22, 30, 37, 45, 55, 75, 90, 110, 132,
          160, 200, 250, 315, 355, 400]


def motor_rpm(poles: int, supply: str) -> float:
    hz = 60.0 if "60" in supply.split("/")[-1] else 50.0
    return 120.0 * hz / poles * 0.985                  # ~1.5 % slip


def select(geom, air: dict, Q_fan: float, rho_out: float, s: dict) -> dict:
    f, t, a = s["fan"], s["tower"], s["airside"]
    D = geom.fan_D
    v_fan = air["v_fan"]
    vp_fan = rho_out * v_fan ** 2 / 2
    if t["fan_stack"] == "velocity_recovery":
        A_exit = math.pi / 4 * geom.stack_exit_D ** 2
        v_exit = Q_fan / A_exit
        dP_stack = (1 - a["stack_diffuser_eff"]) * (vp_fan - rho_out * v_exit ** 2 / 2)
    else:
        v_exit = v_fan
        dP_stack = 0.0
    vp_exit = rho_out * v_exit ** 2 / 2
    dP_total = air["dP_static_system"] + dP_stack + vp_exit
    dP_fan_static = dP_total - vp_fan
    P_air = Q_fan * dP_total
    P_shaft = P_air / f["total_efficiency"]
    P_motor_out = P_shaft / f["gear_efficiency"]
    P_input = P_motor_out / f["motor_efficiency"]
    need = P_motor_out * f["motor_margin"] / 1e3
    motor_kW = next((k for k in IEC_KW if k >= need), None)
    U_tip = f["tip_speed_design_m_s"]
    n_fan = U_tip / (math.pi * D) * 60.0
    n_motor = motor_rpm(t["motor_poles"], t["power_supply"])
    return {"D": D, "Q": Q_fan, "v_fan": v_fan, "v_exit": v_exit, "vp_fan": vp_fan, "vp_exit": vp_exit,
            "dP_stack": dP_stack, "dP_total": dP_total, "dP_fan_static": dP_fan_static,
            "P_air_kW": P_air / 1e3, "P_shaft_kW": P_shaft / 1e3, "P_input_kW": P_input / 1e3,
            "motor_kW": motor_kW, "motor_rpm": n_motor, "fan_rpm": n_fan, "gear_ratio": n_motor / n_fan,
            "tip_speed": U_tip, "stack": t["fan_stack"], "stack_H": geom.stack_H, "stack_exit_D": geom.stack_exit_D}
