"""Offline consistency check; does not certify the source's legal accuracy."""
from pathlib import Path
import hashlib
import json
import zipfile

root = Path(__file__).resolve().parents[1]
folder = root / "docs/imports"
rows = json.loads((folder / "questions-draft.json").read_text(encoding="utf-8"))
audit = json.loads((folder / "question-audit.json").read_text(encoding="utf-8"))
assert len(rows) == 600
assert [row["externalId"] for row in rows] == [f"Q{n:03}" for n in range(1, 601)]
assert sum(row["critical"] for row in rows) == 60
for row in rows:
    assert 1 <= row["chapter"] <= 6
    assert 2 <= len(row["options"]) <= 4
    assert 0 <= row["correctAnswer"] < len(row["options"])
    assert row["reviewed"] is False
for number, answer in [(204, 0), (301, 0), (302, 3), (352, 0)]:
    assert rows[number - 1]["correctAnswer"] == answer
images = set()
for name in audit["archives"]:
    path = folder / name
    assert path.stat().st_size <= 20 * 1024 * 1024
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        assert sum(entry.file_size for entry in archive.infolist()) <= 50 * 1024 * 1024
        for entry in archive.infolist():
            assert entry.filename == Path(entry.filename).name
            assert entry.file_size <= 5 * 1024 * 1024
            assert entry.filename not in images
            assert archive.read(entry)[:8] == b"\x89PNG\r\n\x1a\n"
            images.add(entry.filename)
assert images == {f"{row['externalId']}.png" for row in rows if row["imageRequired"]}
assert len(images) == audit["images"] == 318
assert hashlib.sha256((root / "docs" / audit["source"]).read_bytes()).hexdigest() == audit["pdfSha256"]
print("PASS: 600 draft questions, 60 critical, 318 ZIP images and source checksum")
