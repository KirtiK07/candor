import difflib
from html import escape

_STYLE = """<style>
.rr-diff{font-family:ui-monospace,Consolas,monospace;font-size:0.85rem;line-height:1.45;white-space:pre-wrap}
.rr-diff div{padding:1px 6px;border-radius:3px}
.rr-diff .add{background:rgba(46,160,67,.22)}
.rr-diff .del{background:rgba(248,81,73,.20);text-decoration:line-through;opacity:.8}
</style>"""


def diff_html(old: str, new: str) -> str:
    """Line diff: removed lines in red (struck through), added lines in green."""
    a, b = old.splitlines(), new.splitlines()
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            out += [f"<div>{escape(l) or '&nbsp;'}</div>" for l in a[i1:i2]]
            continue
        out += [f'<div class="del">− {escape(l)}</div>' for l in a[i1:i2] if l.strip()]
        out += [f'<div class="add">+ {escape(l)}</div>' for l in b[j1:j2] if l.strip()]
    return _STYLE + '<div class="rr-diff">' + "".join(out) + "</div>"
