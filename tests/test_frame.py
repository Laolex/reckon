"""The frame must stay true, not merely stay pretty.

If either half of the picture stops holding — the OPA log becoming
classifiable, or the re-emitted pair losing C2 — the frame is a claim we
can no longer make, and it should fail here rather than in front of a
reader.
"""

import contextlib
import io

from demo.frame import main, render


def test_the_frame_prints_both_columns():
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        main()
    output = buffer.getvalue()

    assert "AS OPA RECORDED IT" in output
    assert "WITH RECKON" in output
    assert "REFUSED — no class" in output
    assert "C2 (Loosening Replay)" in output
    # The finding, not the fix, is the point.
    assert "No record carries its own soundness proof." in output


def test_the_refused_column_is_read_first():
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        main()
    output = buffer.getvalue()
    assert output.index("AS OPA RECORDED IT") < output.index("WITH RECKON")


def test_columns_clear_the_widest_cell():
    frame = render("t", [("l", "x" * 60, "y")], [])
    line = next(row for row in frame.split("\n") if "y" in row)
    assert line.index("y") > 60
