"""Inline _sprite.svg into every mockup between <!--SPRITE--> markers. Idempotent."""
import pathlib, re
root = pathlib.Path(__file__).parent
sprite = (root / "_sprite.svg").read_text().strip()
for f in sorted(root.glob("*/*.html")):
    s = f.read_text()
    s2 = re.sub(r"<!--SPRITE-->(?:.*?<!--/SPRITE-->)?", lambda m: "<!--SPRITE-->" + sprite + "<!--/SPRITE-->", s, count=1, flags=re.S)
    if s2 != s:
        f.write_text(s2); print("inlined", f.relative_to(root))
