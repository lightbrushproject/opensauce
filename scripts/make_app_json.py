"""Turn an API-format graph into an App Mode workflow (<name>.app.json) with the frontend's own importer.

1. POSTs the API json to the server's userdata as workflows/_src_<name>.api.json.
2. If Playwright + Chromium are installed: opens the frontend headless, runs app.loadApiJson, writes
   extra.linearData / extra.linearMode, saves workflows/<name>.app.json to userdata and copies it to
   workflows/app/. Otherwise prints the JS snippet to paste into the browser console.

  python scripts/make_app_json.py workflows/open_sauce.api.json --name open_sauce \
      --input 9:image --input 200:move --input 201:value --input 17:noise_seed --input 202:value --output 37
"""
from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

JS = """async ({api, name, linear, server}) => {
  await app.loadApiJson(api, name);
  const wf = app.graph.serialize();
  wf.extra = {...(wf.extra || {}), linearData: linear, linearMode: true};
  const url = server + '/api/userdata/' + encodeURIComponent('workflows/' + name + '.app.json') + '?overwrite=true';
  const r = await fetch(url, {method: 'POST', body: JSON.stringify(wf)});
  return {status: r.status, wf};
}"""


def post_userdata(server: str, rel: str, body: bytes) -> int:
    url = f"{server}/api/userdata/{urllib.parse.quote(rel, safe='')}?overwrite=true"
    with urllib.request.urlopen(urllib.request.Request(url, data=body, method="POST")) as r:
        return r.status


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("api_json")
    ap.add_argument("--name", required=True)
    ap.add_argument("--input", action="append", default=[], metavar="NODE:WIDGET", help="exposed control, in order")
    ap.add_argument("--output", action="append", default=[], metavar="NODE")
    ap.add_argument("--server", default="http://127.0.0.1:8189")
    a = ap.parse_args()

    api = json.loads(Path(a.api_json).read_text(encoding="utf-8"))
    linear = {"inputs": [i.split(":", 1) for i in a.input], "outputs": a.output}
    print("userdata src:", post_userdata(a.server, f"workflows/_src_{a.name}.api.json", json.dumps(api).encode()))

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright not installed. Open the frontend, then run in the browser console:\n")
        print(f"await ({JS})({json.dumps({'api': api, 'name': a.name, 'linear': linear, 'server': ''})})")
        return 0

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"{a.server}/", wait_until="networkidle")
        page.wait_for_function("() => window.app && window.app.graph", timeout=60000)
        res = page.evaluate(JS, {"api": api, "name": a.name, "linear": linear, "server": a.server})
        browser.close()
    wf = res["wf"]
    ids = {str(n["id"]) for n in wf["nodes"]}
    missing = sorted(set(api) - ids)
    print(f"userdata app: {res['status']}  nodes {len(wf['nodes'])}/{len(api)}  links {len(wf['links'])}  missing {missing}")
    out = ROOT / "workflows" / "app" / f"{a.name}.app.json"
    out.write_text(json.dumps(wf, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote", out)
    return 1 if missing or res["status"] != 200 else 0


if __name__ == "__main__":
    raise SystemExit(main())
