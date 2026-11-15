"""Dimensionally matched assembly proxy for the user's 5 kg load cell.

The outside envelope and M4 hole centres follow the supplied drawing.
Strain-gauge reliefs and cable are intentionally omitted.
"""

from pathlib import Path
import win32com.client

ROOT = Path(__file__).parent
TEMPLATE = r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2023\templates\gb_part.prtdot"
MM = 0.001


def select_top(model):
    feature = model.FirstFeature
    planes = []
    while feature is not None:
        if feature.GetTypeName2 == "RefPlane":
            planes.append(feature)
        feature = feature.GetNextFeature
    model.ClearSelection2(True)
    if not planes[1].Select2(False, 0):
        raise RuntimeError("Cannot select top plane")
    model.SketchManager.InsertSketch(True)


app = win32com.client.Dispatch("SldWorks.Application")
part = app.NewDocument(TEMPLATE, 0, 0, 0)
assert part is not None
select_top(part)
part.SketchManager.CreateCornerRectangle(-37.5 * MM, -6.35 * MM, 0, 37.5 * MM, 6.35 * MM, 0)
part.SketchManager.InsertSketch(True)
body_feature = part.FeatureManager.FeatureExtrusion2(
    True, False, False, 0, 0, 7 * MM, 7 * MM,
    False, False, False, False, 0.0, 0.0,
    False, False, False, False, True, True, True, 0, 0.0, False,
)
assert body_feature is not None
body_feature.Name = "Sensor_envelope_75x12p7x7"

select_top(part)
for x in (-32, -22, 22, 32):
    part.SketchManager.CreateCircleByRadius(x * MM, 0, 0, 2 * MM)
part.SketchManager.InsertSketch(True)
holes = part.FeatureManager.FeatureCut3(
    True, False, True, 0, 0, 7 * MM, 7 * MM,
    False, False, False, False, 0.0, 0.0,
    False, False, False, False, False, True, True, True,
    True, False, 0, 0.0, False,
)
assert holes is not None
holes.Name = "Four_M4_nominal_holes"
part.ForceRebuild3(False)
assert len(part.GetBodies2(0, False)) == 1
part.ClearSelection2(True)
for name in ("LoadCell_5kg_75x12p7x7_proxy.SLDPRT", "LoadCell_5kg_75x12p7x7_proxy.STEP"):
    path = ROOT / name
    part.SaveAs3(str(path), 0, 1)
    assert path.exists() and path.stat().st_size > 1000, path
    print(path, path.stat().st_size)
