"""The end-frame QR is opt-in: off by default in the node, the CLI and the assemblers."""
import ast
import importlib.util
import sys
from pathlib import Path

PACK = Path(__file__).resolve().parent.parent
ROOT = PACK.parent.parent


def _load_nodes_recipe():
    # nodes_recipe uses a relative import of recipe; load it as part of a throwaway package
    pkg = "sg_pack_for_test"
    if pkg not in sys.modules:
        spec = importlib.util.spec_from_file_location(pkg, PACK / "recipe.py")
        sys.modules[pkg] = importlib.util.module_from_spec(spec)
        sys.modules[pkg].__path__ = [str(PACK)]
    spec = importlib.util.spec_from_file_location(f"{pkg}.nodes_recipe", PACK / "nodes_recipe.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_node_burn_qr_defaults_off():
    nr = _load_nodes_recipe()
    opt = nr.SGRecipeEmbed.INPUT_TYPES()["optional"]
    assert opt["burn_qr"][0] == "BOOLEAN"
    assert opt["burn_qr"][1]["default"] is False


def test_node_returns_frames_untouched_without_qr(tmp_path, monkeypatch):
    nr = _load_nodes_recipe()
    monkeypatch.setattr(nr, "_output_root", lambda: tmp_path)
    sentinel = object()  # no tensor work happens when the QR is off
    out, rec_json, rid = nr.SGRecipeEmbed().run(sentinel, "levitate", 11, "https://example.invalid/", "", "{}")
    assert out is sentinel
    assert rid and rid in rec_json


def _default_of(path: Path, func: str, arg: str):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func:
            names = [a.arg for a in node.args.args + node.args.kwonlyargs]
            defaults = node.args.defaults + [d for d in node.args.kw_defaults if d is not None]
            all_args = node.args.args[len(node.args.args) - len(node.args.defaults):] + \
                [a for a, d in zip(node.args.kwonlyargs, node.args.kw_defaults) if d is not None]
            for a, d in zip(all_args, defaults):
                if a.arg == arg:
                    return ast.literal_eval(d)
            raise AssertionError(f"{func} has no default for {arg} (args: {names})")
    raise AssertionError(f"{func} not found in {path}")


def test_cli_and_trailer_default_off():
    assert _default_of(ROOT / "app" / "opensauce.py", "render", "qr") is False
    assert _default_of(ROOT / "app" / "opensauce.py", "trailer", "qr") is False
    assert _default_of(PACK / "trailer.py", "assemble", "burn_qr") is False
