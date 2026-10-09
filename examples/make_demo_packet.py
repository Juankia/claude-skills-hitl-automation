#!/usr/bin/env python3
"""Create a small, fictional filing packet (manifest + PDFs) for demos and tests.

Usage:
    python examples/make_demo_packet.py OUT_DIR --client-id <id> [--broken]

``--broken`` introduces typical gaps (bad file name, missing certificate of
service, over-long proposed order, scanned page without text) so the gap
report has something to show.

The PDFs are written by hand (no reportlab needed): a valid PDF 1.4 file with
one Helvetica text line per page.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def make_pdf(pages: list[str]) -> bytes:
    """Return a minimal valid PDF; an empty string yields a page with no text."""
    objects: list[bytes] = []
    n = len(pages)
    page_ids = [3 + i * 2 for i in range(n)]
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode())
    font_id = 3 + n * 2
    for i, text in enumerate(pages):
        content_id = page_ids[i] + 1
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>".encode()
        )
        safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 12 Tf 72 720 Td ({safe}) Tj ET".encode() if text else b""
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def build_packet(out_dir: Path, client_id: str, broken: bool = False) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    docs = [
        ("2026-10-09_motion-to-extend.pdf", "motion", ["Motion to Extend Time - page 1", "Argument - page 2"]),
        ("2026-10-09_proposed-order.pdf", "proposed_order", ["Proposed Order"]),
        ("2026-10-09_certificate-of-service.pdf", "certificate_of_service", ["Certificate of Service"]),
    ]
    if broken:
        docs = [
            ("Motion FINAL v2.pdf", "motion", ["Motion to Extend Time", ""]),
            ("2026-10-09_proposed-order.pdf", "proposed_order", [f"Proposed Order page {i}" for i in range(1, 8)]),
            ("2026-10-09_exhibit-a.pdf", "exhibit", [""]),
        ]
    for name, _type, pages in docs:
        (out_dir / name).write_bytes(make_pdf(pages))
    manifest = {
        "client_id": client_id,
        "case": {
            "case_number": "26-CV-01234" if not broken else "2026/1234",
            "court": "Demo County District Court",
            "case_title": "Brightwater Ceramics LLC v. Mesa Distribution Partners Inc.",
            "filing_type": "motion",
            "filer_name": "Dana Whitfield",
        },
        "documents": [{"path": n, "type": t} for n, t, _ in docs],
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return out_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--broken", action="store_true")
    args = parser.parse_args()
    print(build_packet(args.out_dir, args.client_id, args.broken))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
