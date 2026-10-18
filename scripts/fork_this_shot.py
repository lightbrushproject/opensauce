"""Fork This Shot CLI.

  python scripts/fork_this_shot.py <video.mp4>                      print recipe, write <video>.api.json
  python scripts/fork_this_shot.py --embed <video.mp4> --recipe <recipe.json>
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "custom_nodes" / "shotgrammar"))
import recipe as R  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", nargs="?")
    ap.add_argument("--embed", metavar="VIDEO")
    ap.add_argument("--recipe", metavar="JSON")
    a = ap.parse_args()

    if a.embed:
        if not a.recipe:
            ap.error("--embed requires --recipe")
        rec = json.loads(Path(a.recipe).read_text(encoding="utf-8"))
        print(R.embed_mp4_metadata(a.embed, rec))
        return 0
    if not a.video:
        ap.error("video path required")
    rec = R.read_recipe_from_mp4(a.video, ROOT / "recipes")
    print(json.dumps({k: v for k, v in rec.items() if k != "api_workflow"}, indent=2))
    out = Path(a.video).with_suffix(".api.json")
    out.write_text(json.dumps(rec["api_workflow"], indent=2), encoding="utf-8")
    print(f"workflow: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
