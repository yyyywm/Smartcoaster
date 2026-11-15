"""Create an inspection assembly of the housing and load-cell proxy."""

from pathlib import Path
import win32com.client
import pythoncom

ROOT = Path(__file__).parent
TEMPLATE = r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2023\templates\gb_assembly.asmdot"
PARTS = [
    ("Coaster_Base_v4.SLDPRT", 0.0, False),
    ("LoadCell_5kg_75x12p7x7_proxy.SLDPRT", 0.014, False),
    ("Coaster_Top_v5.SLDPRT", 0.030, True),
]

app = win32com.client.Dispatch("SldWorks.Application")
assembly = app.NewDocument(TEMPLATE, 0, 0, 0)
assert assembly is not None
title = assembly.GetTitle
print("assembly", title)

for filename, offset, flip in PARTS:
    path = str(ROOT / filename)
    if not Path(path).exists():
        raise FileNotFoundError(path)
    errors = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    warnings = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    opened = app.OpenDoc6(path, 1, 32, "", errors, warnings)
    print("opened", filename, bool(opened))
    activate_error = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    app.ActivateDoc2(title, False, activate_error)
    component = assembly.AddComponent5(path, 0, "", False, "", 0.0, offset, 0.0)
    if component is None:
        raise RuntimeError(f"Could not insert {filename}")
    # SOLIDWORKS transform: row-major rotation, translation, scale.
    sign = -1.0 if flip else 1.0
    matrix = [1.0, 0.0, 0.0,
              0.0, sign, 0.0,
              0.0, 0.0, sign,
              0.0, offset, 0.0,
              1.0, 0.0, 0.0, 0.0]
    math_utility = app.GetMathUtility
    data = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, matrix)
    dispatch = math_utility._oleobj_.Invoke(1, 0, pythoncom.DISPATCH_METHOD, True, data)
    transform = win32com.client.Dispatch(dispatch)
    if not component.SetTransformAndSolve2(transform):
        raise RuntimeError(f"Cannot position {filename}")
    actual = component.Transform2.ArrayData
    print("transform", tuple(round(v, 4) for v in actual))
    print("inserted", component.Name2, "axial offset", offset, "flipped", flip)

assembly.ForceRebuild3(False)
assembly.ShowNamedView2("*Isometric", 7)
assembly.ViewRotXPlusNinety()
assembly.ViewRotXPlusNinety()
assembly.ViewZoomtofit2()
out = ROOT / "Smart_Coaster_layout_v5.SLDASM"
assembly.SaveAs3(str(out), 0, 1)
assert out.exists() and out.stat().st_size > 10000
print("saved", out, out.stat().st_size)
preview = ROOT / "Smart_Coaster_layout_v5.bmp"
print("preview", assembly.SaveBMP(str(preview), 1200, 900), preview.exists())
