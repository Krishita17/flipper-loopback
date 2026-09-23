# Rig jig

[`flipper_jig.scad`](flipper_jig.scad) is a parametric OpenSCAD model. It holds the emitter and DUT at a fixed distance and orientation, so RF/IR results repeat from run to run. CI renders both modes to STL (the `jig-stl` artifact on every CI run), or you can render them locally:

```bash
openscad -D 'mode="back_to_back"' -o flipper_jig_back_to_back.stl hardware/jig/flipper_jig.scad
openscad -D 'mode="head_to_head"' -o flipper_jig_head_to_head.stl hardware/jig/flipper_jig.scad
```

| Mode | Orientation | Subsystems | Default spacing |
|---|---|---|---|
| `back_to_back` | standing on the long edge opposite the GPIO header, backs facing | Sub-GHz, RFID 125 kHz, NFC, wired iButton/GPIO | `gap = 20` mm |
| `head_to_head` | lying face-up, top edges (IR window) facing | Infrared | `ir_gap = 60` mm |

**Before printing:** the body dimensions are nominal. Measure your units and adjust `fit` for your printer. Record the `gap` you use in your bench report, because results are only comparable at the same spacing.

**Material:** PLA or PETG. Don't use metal inserts or magnets. Metal near the coils and antenna changes exactly the thing the jig is supposed to hold constant.

**Status:** the model has not been test-printed yet. Please open an issue with fit feedback and photos.
