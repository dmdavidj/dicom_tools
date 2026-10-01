"""RT Ion Plan (carbon/ION) -> ProKnow-compatible PROTON plan converter.

Changes applied to each RT Ion Plan:
  1. Transfer Syntax: Implicit VR -> Explicit VR Little Endian
  2. Ion Beam: RadiationType ION -> PROTON, remove Radiation Mass/Atomic Number, Charge State
  3. Empty Cumulative Dose Reference Coefficient filled with CMW / Final CMW
  4. Private tags removed
SOP Instance UID and all physical data (energy, spots, meterset, isocenter) are kept.

Usage:
  rp_proton_converter.exe <file or folder> [...]   (or drag & drop onto the exe)
  rp_proton_converter.exe                          (asks for a path)
Output: "<source folder>/fixed/<name>_proton.dcm"
"""
import sys
import warnings
from pathlib import Path

import pydicom
from pydicom.uid import ExplicitVRLittleEndian

RT_ION_PLAN = "1.2.840.10008.5.1.4.1.1.481.8"
ION_TAGS = ("RadiationMassNumber", "RadiationAtomicNumber", "RadiationChargeState")

warnings.simplefilter("ignore")


def convert(ds):
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

    filled = 0
    for beam in ds.IonBeamSequence:
        final = float(beam.FinalCumulativeMetersetWeight or 0)
        last = 0.0
        for cp in beam.IonControlPointSequence:
            if cp.get("CumulativeMetersetWeight") is not None:
                last = float(cp.CumulativeMetersetWeight)
            for ref in cp.get("ReferencedDoseReferenceSequence", []):
                if ref.get("CumulativeDoseReferenceCoefficient") is None and final > 0:
                    ref.CumulativeDoseReferenceCoefficient = f"{last / final:.10g}"[:16]
                    filled += 1

        beam.RadiationType = "PROTON"
        for tag in ION_TAGS:
            if tag in beam:
                delattr(beam, tag)

    ds.remove_private_tags()
    return filled


def process_file(path):
    try:
        ds = pydicom.dcmread(path)
    except Exception:
        return False
    if ds.get("SOPClassUID") != RT_ION_PLAN:
        return False

    types = [b.get("RadiationType") for b in ds.IonBeamSequence]
    filled = convert(ds)

    out_dir = path.parent / "fixed"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"{path.stem}_proton.dcm"
    ds.save_as(out, enforce_file_format=True)
    print(f"[OK] {path.name}")
    print(f"     RadiationType {types} -> PROTON, CDRC filled: {filled}")
    print(f"     -> {out}")
    return True


def collect(paths):
    for p in paths:
        p = Path(p.strip().strip('"'))
        if p.is_dir():
            yield from sorted(f for f in p.iterdir() if f.is_file() and f.suffix.lower() in (".dcm", ""))
        elif p.is_file():
            yield p
        else:
            print(f"[SKIP] not found: {p}")


def main():
    args = sys.argv[1:]
    if not args:
        entered = input("RP 파일 또는 폴더 경로를 입력하세요: ").strip()
        args = [entered] if entered else []

    done = 0
    for f in collect(args):
        try:
            if process_file(f):
                done += 1
        except Exception as e:
            print(f"[ERROR] {f.name}: {e}")

    print(f"\n변환 완료: {done}개 (RT Ion Plan 이외 파일은 건너뜀)")
    if getattr(sys, "frozen", False):
        input("Enter를 누르면 종료합니다...")


if __name__ == "__main__":
    main()
