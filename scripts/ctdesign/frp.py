"""Pultruded FRP sections, end-use material properties and LRFD capacities (ASCE/SEI 74 basis).

Design format:  R_u <= lambda * phi * R_n,  R_n = C * R_o   (ASCE/SEI 74)
  lambda  time-effect factor of the load combination (loads.COMBOS)
  C       material adjustment for moisture (C_M) and sustained temperature (C_T); a cooling-tower
          interior is permanently wet and warm, so both apply
Resistance factors - SOURCE noted per value:
  global (Euler / lateral-torsional) buckling 0.70, local buckling 0.80, web crippling 0.70,
  pin bearing 0.80, net tension 0.50 (1 row) / 0.45 (multi-row): 2010 ASCE pre-standard as reported
  by Mottram (Composite Engineering Show 2014);
  material rupture 0.65, shear 0.70, shear-out 0.50: ASSUMED (not confirmed against ASCE 74-23).
Compression strength cap  lambda phi Pn <= 0.7 lambda F_L^c A_g, serviceability Euler check with
  phi_0 = 1 - 500 delta_0/L and Ps <= 0.3 F_L^c A_g, slenderness KL/r <= 1.4 sqrt(E_L A_g / P_D):
  ASCE 74 as presented by Zarghamee (2021).
Local buckling uses classical orthotropic-plate solutions (permitted as rational analysis):
  outstanding flange (simply supported - free, web restraint neglected): F_cr = 4 G_LT t^2 / b_f^2
  internal plate (both edges simply supported):
      F_cr = (pi^2 / 6)(t/b)^2 [ (sqrt(E_L E_T) + nu_LT E_T) / (1 - nu_LT nu_TL) + 2 G_LT ]
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

LIB = Path(__file__).resolve().parents[2] / "references" / "frp_profiles.json"
IN = 0.0254

PHI = {"global": 0.70, "local": 0.80, "crippling": 0.70, "bearing": 0.80, "net_tension_1": 0.50,
       "net_tension_n": 0.45, "rupture": 0.65, "shear": 0.70, "shear_out": 0.50, "bolt": 0.75}
PHI_SOURCE = {"global": "pre-standard", "local": "pre-standard", "crippling": "pre-standard",
              "bearing": "pre-standard", "net_tension_1": "pre-standard", "net_tension_n": "pre-standard",
              "rupture": "ASSUMED", "shear": "ASSUMED", "shear_out": "ASSUMED", "bolt": "ASSUMED (AISC-type, SS bolts)"}


def library(path: Path = LIB) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


@dataclass
class Section:
    name: str
    family: str
    d: float          # depth (m)
    bf: float         # flange width / tube side (m)
    t: float          # wall / flange / web thickness (m; pultruded shapes have equal tf = tw)
    A: float
    Iz: float         # strong axis
    Iy: float         # weak axis
    J: float
    Cw: float
    Sz: float
    Sy: float
    Aw: float         # shear area (webs)

    @property
    def rz(self):
        return math.sqrt(self.Iz / self.A)

    @property
    def ry(self):
        return math.sqrt(self.Iy / self.A)

    def mass_per_m(self, rho):
        return self.A * rho


def make_section(family: str, dims) -> Section:
    if family == "SQ":
        b, t = dims[0] * IN, dims[1] * IN
        bi = b - 2 * t
        A = b * b - bi * bi
        I = (b ** 4 - bi ** 4) / 12
        J = t * (b - t) ** 3
        return Section(f"SQ {dims[0]:g}x{dims[0]:g}x{dims[1]:g}", "SQ", b, b, t, A, I, I, J, 0.0,
                       I / (b / 2), I / (b / 2), 2 * (b - 2 * t) * t)
    if family in ("I", "W"):
        d, bf, t = dims[0] * IN, dims[1] * IN, dims[2] * IN
        hw = d - 2 * t
        A = 2 * bf * t + hw * t
        Iz = (bf * d ** 3 - (bf - t) * hw ** 3) / 12
        Iy = 2 * t * bf ** 3 / 12 + hw * t ** 3 / 12
        J = (2 * bf * t ** 3 + (d - t) * t ** 3) / 3
        Cw = Iy * (d - t) ** 2 / 4
        return Section(f"{family} {dims[0]:g}x{dims[1]:g}x{dims[2]:g}", family, d, bf, t, A, Iz, Iy, J, Cw,
                       Iz / (d / 2), Iy / (bf / 2), hw * t)
    if family == "L":
        b, t = dims[0] * IN, dims[2] * IN
        A = (2 * b - t) * t
        return Section(f"L {dims[0]:g}x{dims[1]:g}x{dims[2]:g}", "L", b, b, t, A, 0, 0, 0, 0, 0, 0, b * t)
    raise ValueError(family)


def family_sections(lib: dict, family: str) -> list[Section]:
    return [make_section(family, dims) for dims in lib["shapes"][family]]


@dataclass
class Material:
    name: str
    E_L: float
    E_T: float
    G: float
    nu: float
    F_Lt: float
    F_Lc: float
    F_Lb: float
    F_v: float
    F_br: float
    rho: float
    C_strength: float
    C_modulus: float
    basis: str


def end_use_material(lib: dict, name: str, wet: bool, T_service_C: float) -> Material:
    m = lib["materials"][name]
    adj = lib["adjustment"][m["resin"]]
    Cs = adj["CM_strength"] if wet else 1.0
    Cm = adj["CM_modulus"] if wet else 1.0
    T_F = T_service_C * 1.8 + 32
    if T_F > 90:
        a, k = adj["CT_strength"]; Cs *= min(1.0, a + k * T_F)
        a, k = adj["CT_modulus"]; Cm *= min(1.0, a + k * T_F)
    E = 1e9
    return Material(name, m["E_L_GPa"] * E * Cm, m["E_T_GPa"] * E * Cm, m["G_LT_GPa"] * E * Cm, m["nu_LT"],
                    m["F_Lt_MPa"] * 1e6 * Cs, m["F_Lc_MPa"] * 1e6 * Cs, m["F_Lb_MPa"] * 1e6 * Cs,
                    m["F_v_MPa"] * 1e6 * Cs, m["F_br_MPa"] * 1e6 * Cs, m["density_kg_m3"], Cs, Cm, m["basis"])


# ----------------------------------------------------------------------------- local buckling
def plate_ss_ss(m: Material, b: float, t: float) -> float:
    """Long orthotropic plate, both unloaded edges simply supported:
    N_cr = (2 pi^2 / b^2)[sqrt(D11 D22) + D12 + 2 D66]; reduces to k = 4 for an isotropic plate."""
    nu_TL = m.nu * m.E_T / m.E_L
    return (math.pi ** 2 / 6) * (t / b) ** 2 * ((math.sqrt(m.E_L * m.E_T) + m.nu * m.E_T) / (1 - m.nu * nu_TL) + 2 * m.G)


def flange_outstand(m: Material, bf: float, t: float) -> float:
    return 4 * m.G * t ** 2 / bf ** 2


def local_compression(s: Section, m: Material) -> float:
    if s.family == "SQ":
        return plate_ss_ss(m, s.bf - s.t, s.t)
    return min(flange_outstand(m, s.bf, s.t), plate_ss_ss(m, s.d - 2 * s.t, s.t))


# ----------------------------------------------------------------------------- member capacities
def capacities(s: Section, m: Material, L: float, K: float = 1.0, Lb: float | None = None, Cb: float = 1.0) -> dict:
    """Factored capacities phi*Rn (without lambda) and the governing limit state of each."""
    KLr = K * L / min(s.ry, s.rz)
    Fe = math.pi ** 2 * m.E_L / KLr ** 2
    F_loc = local_compression(s, m)
    comp = {"global": PHI["global"] * Fe * s.A, "local": PHI["local"] * F_loc * s.A, "cap": 0.7 * m.F_Lc * s.A}
    Pc_mode = min(comp, key=comp.get)
    ten = PHI["rupture"] * m.F_Lt * s.A
    # flexure about the strong axis
    fz = {"rupture": PHI["rupture"] * m.F_Lb * s.Sz}
    if s.family == "SQ":
        fz["local"] = PHI["local"] * plate_ss_ss(m, s.bf - s.t, s.t) * s.Sz
    else:
        fz["local"] = PHI["local"] * flange_outstand(m, s.bf, s.t) * s.Sz
        Lb = L if Lb is None else Lb
        Mltb = Cb * math.pi / Lb * math.sqrt(m.E_L * s.Iy * m.G * s.J + s.Iy * s.Cw * (math.pi * m.E_L / Lb) ** 2)
        fz["ltb"] = PHI["global"] * Mltb
    Mz_mode = min(fz, key=fz.get)
    fy = {"rupture": PHI["rupture"] * m.F_Lb * s.Sy,
          "local": PHI["local"] * (plate_ss_ss(m, s.bf - s.t, s.t) if s.family == "SQ" else flange_outstand(m, s.bf, s.t)) * s.Sy}
    My_mode = min(fy, key=fy.get)
    hw = s.d - 2 * s.t
    tau_cr = 5.35 * math.pi ** 2 * math.sqrt(m.E_L * m.E_T) / (12 * (1 - m.nu * m.nu * m.E_T / m.E_L)) * (s.t / hw) ** 2
    sh = {"rupture": PHI["shear"] * m.F_v * s.Aw, "buckling": PHI["local"] * tau_cr * s.Aw}
    V_mode = min(sh, key=sh.get)
    return {"Pc": comp[Pc_mode], "Pc_mode": Pc_mode, "Pt": ten, "Mz": fz[Mz_mode], "Mz_mode": Mz_mode,
            "My": fy[My_mode], "My_mode": My_mode, "V": sh[V_mode], "V_mode": V_mode,
            "Pe": math.pi ** 2 * m.E_L * s.A / KLr ** 2, "KLr": KLr, "F_loc": F_loc}


def check_member(s: Section, m: Material, L: float, forces: dict, lam: float, K=1.0, Lb=None, caps=None) -> dict:
    """forces: P (+tension), Mz, My, V (absolute maxima along the member). Linear interaction with
    moment amplification 1/(1 - Pu/Pe) for compression."""
    c = caps or capacities(s, m, L, K, Lb)
    P, Mz, My, V = forces["P"], abs(forces["Mz"]), abs(forces["My"]), abs(forces["V"])
    if P < 0:
        amp = 1.0 / max(1e-3, 1 - (-P) / c["Pe"])
        ur_ax = -P / (lam * c["Pc"])
    else:
        amp = 1.0
        ur_ax = P / (lam * c["Pt"])
    ur_int = ur_ax + amp * (Mz / (lam * c["Mz"]) + My / (lam * c["My"]))
    ur_v = V / (lam * c["V"])
    ur = max(ur_int, ur_v)
    gov = "shear" if ur_v >= ur_int else ("axial+bending" if (Mz + My) > 0 and ur_ax < ur_int else
                                          ("compression " + c["Pc_mode"] if P < 0 else "tension"))
    return {"UR": ur, "UR_interaction": ur_int, "UR_shear": ur_v, "governs": gov, **{k: c[k] for k in ("KLr", "Pc_mode", "Mz_mode")}}


def slenderness_ok(s: Section, m: Material, L: float, P_D: float, K=1.0) -> tuple[bool, float, float]:
    """ASCE 74: KL/r <= 1.4 sqrt(E_L A_g / P_D) for members in compression under unfactored dead load."""
    KLr = K * L / min(s.ry, s.rz)
    if P_D <= 0:
        return True, KLr, math.inf
    lim = 1.4 * math.sqrt(m.E_L * s.A / P_D)
    return KLr <= lim, KLr, lim


def serviceability_ok(s: Section, m: Material, L: float, Ps: float, delta0_L=0.001, K=1.0) -> tuple[bool, float]:
    """Ps <= phi_0 pi^2 E_L A / (KL/r)^2 <= 0.3 F_L^c A_g, phi_0 = 1 - 500 delta_0/L (ASCE 74)."""
    phi0 = 1 - 500 * delta0_L
    KLr = K * L / min(s.ry, s.rz)
    lim = min(phi0 * math.pi ** 2 * m.E_L * s.A / KLr ** 2, 0.3 * m.F_Lc * s.A)
    return Ps <= lim, Ps / lim if lim > 0 else math.inf


# ----------------------------------------------------------------------------- bolted connections
BOLT_FU = {"SS316": 515e6, "SS304": 515e6, "HDG": 825e6}


def bolted(force: float, t: float, w: float, lam: float, m: Material, bolt_mat: str = "SS316",
           diameters=(12, 16, 20), planes: int = 1, max_bolts: int = 4) -> dict:
    """Smallest bolt group (diameter, count in one row along the force) for a lap/clip connection.

    Limit states per bolt group: bolt shear, pin bearing on the FRP part, net tension at the bolt row
    and shear-out (end distance 2d, pitch 4d). Returns the first passing arrangement or the best one."""
    best = None
    for n in range(1, max_bolts + 1):
        for dmm in diameters:
            d = dmm / 1e3
            dh = d + 1.6e-3
            e = 2 * d
            Rb = PHI["bolt"] * 0.45 * BOLT_FU[bolt_mat] * math.pi / 4 * d * d * planes * n
            Rbr = PHI["bearing"] * n * d * t * m.F_br
            Rnt = (PHI["net_tension_1"] if n == 1 else PHI["net_tension_n"]) * m.F_Lt * max(0.0, w - dh) * t
            Rso = PHI["shear_out"] * n * 2 * e * t * m.F_v
            caps = {"bolt shear": Rb, "pin bearing": Rbr, "net tension": Rnt, "shear-out": Rso}
            mode = min(caps, key=caps.get)
            ur = abs(force) / (lam * caps[mode])
            rec = {"bolts": n, "d_mm": dmm, "UR": ur, "governs": mode, "end_dist_mm": e * 1e3, "pitch_mm": 4 * d * 1e3}
            if best is None or ur < best["UR"]:
                best = rec
            if ur <= 1.0:
                return rec
    return best
