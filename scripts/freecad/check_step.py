"""Re-import a STEP file in a fresh FreeCAD session and report solids, volume and bounding box.

    CT_STEP=<file.step> freecadcmd check_step.py      ->  prints "CTSTEP {json}"
"""
import json
import os

import FreeCAD
import Part

shape = Part.Shape()
shape.read(os.environ["CT_STEP"])
bb = shape.BoundBox
print("CTSTEP " + json.dumps({"solids": len(shape.Solids), "volume_m3": shape.Volume * 1e-9,
                              "bbox_mm": [bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax],
                              "valid": shape.isValid(), "freecad": ".".join(FreeCAD.Version()[:3])}))
