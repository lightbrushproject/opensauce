# Golden inputs

```
examples/<preset>/
  input_01.png  input_02.png  input_03.png     # the 3 golden inputs (9:16 preferred)
  goldens.json                                 # locked settings per input
  expected/input_01_seed11_final.mp4 ...        # locked-seed 1080p finals (scripts/render_goldens.py)
```

`goldens.json`:
```json
{
  "preset": "levitate",
  "size": [768, 1344],
  "frames": 97,
  "fps": 24,
  "goldens": [
    {"input": "input_01.png", "seed": 11, "prompt": "", "intensity": 0.6, "pass": null},
    {"input": "input_02.png", "seed": 22, "prompt": "", "intensity": 0.6, "pass": null},
    {"input": "input_03.png", "seed": 33, "prompt": "", "intensity": 0.6, "pass": null}
  ]
}
```

Pass rule: a preset ships only if at least 2 of 3 goldens pass at these locked settings (see CONTRIBUTING.md).

Likeness rule: inputs are Lightbrush-owned AI avatar stills, Lightbrush AI animation stills, or openly licensed (CC0) stock. No third-party or celebrity faces. Record the source and license of every input in `goldens.json` under `"source"`.
