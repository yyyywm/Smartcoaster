"""Generate the first editable smart-coaster housing in SOLIDWORKS 2023.

All dimensions below are millimetres. Run with the Python installation that
has pywin32; SOLIDWORKS is driven through its COM API.
"""

from pathlib import Path
import win32com.client
import pythoncom

ROOT = Path(__file__).resolve().parents[2] / "models"
TEMPLATE = r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2023\templates\gb_part.prtdot"
MM = 0.001


def plane(model):
    refs = []
    feature = model.FirstFeature
    while feature is not None:
        if feature.GetTypeName2 == "RefPlane":
            refs.append(feature)
        feature = feature.GetNextFeature
    if len(refs) < 2:
        raise RuntimeError("Top reference plane missing")
    model.ClearSelection2(True)
    if not refs[1].Select2(False, 0):
        raise RuntimeError("Could not select top plane")


def circles(model, specs):
    plane(model)
    model.SketchManager.InsertSketch(True)
    for x, y, r in specs:
        if model.SketchManager.CreateCircleByRadius(x * MM, y * MM, 0, r * MM) is None:
            raise RuntimeError("Could not create circle")
    model.SketchManager.InsertSketch(True)


def boss(model, name, specs, height):
    circles(model, specs)
    feature = model.FeatureManager.FeatureExtrusion2(
        True, False, False, 0, 0, height * MM, height * MM,
        False, False, False, False, 0.0, 0.0,
        False, False, False, False, True, True, True, 0, 0.0, False,
    )
    if feature is None:
        raise RuntimeError(f"Extrusion failed: {name}")
    feature.Name = name
    print("created", name)


def cut(model, name, specs, depth):
    circles(model, specs)
    feature = model.FeatureManager.FeatureCut3(
        True, False, True, 0, 0, depth * MM, depth * MM,
        False, False, False, False, 0.0, 0.0,
        False, False, False, False, False, True, True, True,
        True, False, 0, 0.0, False,
    )
    if feature is None:
        raise RuntimeError(f"Cut failed: {name}")
    feature.Name = name
    print("created", name)


def usb_side_opening(model):
    refs = []
    item = model.FirstFeature
    while item is not None:
        if item.GetTypeName2 == "RefPlane":
            refs.append(item)
        item = item.GetNextFeature
    model.ClearSelection2(True)
    assert refs[1].Select2(False, 0)
    offset = model.FeatureManager.InsertRefPlane(8, 8 * MM, 0, 0, 0, 0)
    assert offset is not None
    model.ClearSelection2(True)
    assert offset.Select2(False, 0)
    model.SketchManager.InsertSketch(True)
    model.SketchManager.CreateCornerRectangle(-6 * MM, 49 * MM, 0, 6 * MM, 60 * MM, 0)
    model.SketchManager.InsertSketch(True)
    feature = model.FeatureManager.FeatureCut3(
        True, False, True, 0, 0, 7 * MM, 7 * MM,
        False, False, False, False, 0.0, 0.0,
        False, False, False, False, False, True, True, True,
        True, False, 0, 0.0, False,
    )
    assert feature is not None, "USB side cut failed"
    feature.Name = "USB_C_side_opening_12x7"
    print("created", feature.Name)


def round_outer_edge(model, name, x, axial, radius):
    body = model.GetBodies2(0, False)[0]
    print("body box mm", tuple(round(v / MM, 2) for v in body.GetBodyBox()))
    model.ClearSelection2(True)
    no_callout = win32com.client.VARIANT(pythoncom.VT_DISPATCH, None)
    selected = model.Extension.SelectByID2("", "EDGE", x * MM, axial * MM, 0.0,
                                           False, 1, no_callout, 0)
    print("edge selected", name, selected)
    if not selected:
        raise RuntimeError(f"Could not select {name} edge")
    feature = model.FeatureManager.FeatureFillet(2, radius * MM, 0, 0, None, None, None)
    if feature is None:
        raise RuntimeError(f"Could not fillet {name}")
    feature.Name = name
    print("created", name)


def save(model, name):
    model.ClearSelection2(True)
    model.ForceRebuild3(False)
    bodies = model.GetBodies2(0, False)
    if bodies is None or len(bodies) != 1:
        raise RuntimeError(f"Expected one solid body in {name}, got {0 if bodies is None else len(bodies)}")
    path = ROOT / name
    model.SaveAs3(str(path), 0, 1)
    if not path.exists() or path.stat().st_size < 10000:
        raise RuntimeError(f"Save failed: {path}")
    print("saved", path, path.stat().st_size)


app = win32com.client.Dispatch("SldWorks.Application")
print("SOLIDWORKS", app.RevisionNumber)

# Lower shell: 108 mm fixed base, 3 mm floor, 24 mm rim. The sensor's
# wire end is assumed to be the fixed end at x=+22/+32 mm.
base = app.NewDocument(TEMPLATE, 0, 0, 0)
assert base is not None
boss(base, "Floor_D108_T4p5", [(0, 0, 54)], 4.5)
boss(base, "Rim_OD108_ID102_H24", [(0, 0, 54), (0, 0, 51)], 24)
boss(base, "Sensor_fixed_posts", [(22, 0, 4.5), (32, 0, 4.5)], 14)
cut(base, "M4_fixed_mount_clearance", [(22, 0, 2.15), (32, 0, 2.15)], 14)
cut(base, "M4_fixed_head_recess_D8p2_T2p7", [(22, 0, 4.1), (32, 0, 4.1)], 2.7)
usb_side_opening(base)
round_outer_edge(base, "Base_outer_round_R1", 54, 24, 1)
save(base, "Coaster_Base_v4.SLDPRT")

# Floating cup plate: 116 mm top for a 100 mm cup; a downward 6 mm
# perimeter skirt overlaps the fixed rim with 1.5 mm radial clearance.
top = app.NewDocument(TEMPLATE, 0, 0, 0)
assert top is not None
boss(top, "Moving_post_A", [(-22, 0, 4.5)], 9)
boss(top, "Cup_plate_D116_T5", [(0, 0, 58)], 5)
boss(top, "Moving_post_B", [(-32, 0, 4.5)], 9)
boss(top, "Drip_skirt_OD116_ID111_H10", [(0, 0, 58), (0, 0, 55.5)], 10)
cut(top, "M4_moving_mount_clearance", [(-22, 0, 2.15), (-32, 0, 2.15)], 9)
cut(top, "M4_moving_head_recess_D8p2_T2p7", [(-22, 0, 4.1), (-32, 0, 4.1)], 2.7)
round_outer_edge(top, "Cup_top_outer_round_R2", 58, 0, 2)
save(top, "Coaster_Top_v5.SLDPRT")
