// flipper-loopback rig jig: holds EMITTER and DUT at a fixed, repeatable spacing.
//
// Two modes (render with: openscad -D 'mode="back_to_back"' -o jig.stl flipper_jig.scad)
//   back_to_back : both Flippers stand on the long edge opposite the GPIO header, backs
//                  facing, `gap` mm apart. Use for Sub-GHz, RFID 125 kHz and NFC (the coils
//                  are behind the back cover).
//   head_to_head : both lie face-up, top edges (IR window) facing, `ir_gap` mm apart.
//                  Use for Infrared.
//
// Only the lower `cradle_h` mm of each device is held; ends and top edge stay open so
// USB-C, the GPIO header and the IR window are never covered.
//
// Body dimensions are nominal (100.3 x 40.1 x 25.6 mm). MEASURE YOUR UNITS and adjust `fit`
// (slicer/printer tolerance) before printing. Print in PLA/PETG, no metal inserts: metal near
// the antennas changes the RF result you are trying to hold constant.

mode      = "back_to_back";  // "back_to_back" | "head_to_head"
body_l    = 100.3;           // long side
body_w    = 40.1;            // short side (face height when standing)
body_t    = 25.6;            // thickness (max, at the thickest point)
fit       = 0.6;             // clearance added to every pocket dimension
gap       = 20;              // back_to_back: air gap between the two backs, mm
ir_gap    = 60;              // head_to_head: air gap between the two top edges, mm
wall      = 3;
base_t    = 3;
cradle_h  = 12;              // how much of the device the pocket holds
label     = "flipper-loopback";

$fn = 48;

module pocket(l, t, h) { // open-ended slot, rounded entry
    translate([-1, 0, base_t]) cube([l + 2, t, h + 1]);
}

module back_to_back() {
    pl = body_l + fit;
    pt = body_t + fit;
    total_t = 2 * pt + gap + 2 * wall;
    difference() {
        cube([pl, total_t, base_t + cradle_h]);
        // emitter slot
        translate([0, wall, 0]) pocket(pl, pt, cradle_h);
        // DUT slot
        translate([0, wall + pt + gap, 0]) pocket(pl, pt, cradle_h);
        // keep the gap region open to the air, only a thin floor ties the halves
        translate([-1, wall + pt, base_t]) cube([pl + 2, gap, cradle_h + 1]);
        // cable channel under the gap for GPIO/iButton jumpers
        translate([pl / 2 - 6, -1, -1]) cube([12, total_t + 2, base_t - 1]);
        engrave(pl, total_t);
    }
    // spacer bars at the ends define `gap` exactly and stop the devices tipping inward
    for (x = [0, pl - wall])
        translate([x, wall + pt, 0]) cube([wall, gap, base_t + cradle_h]);
}

module head_to_head() {
    pl = body_w + fit;       // pocket along the short side (devices lie flat, rotated)
    pw = body_l + fit;
    lip = 6;                 // low lips only; the face stays uncovered
    total = 2 * pw + ir_gap + 2 * wall;
    difference() {
        cube([pl + 2 * wall, total, base_t + lip]);
        translate([wall, wall, base_t]) cube([pl, pw, lip + 1]);
        translate([wall, wall + pw + ir_gap, base_t]) cube([pl, pw, lip + 1]);
        // open the IR path between the top edges
        translate([wall, wall + pw - 1, base_t]) cube([pl, ir_gap + 2, lip + 1]);
        engrave(pl + 2 * wall, total);
    }
}

module engrave(l, w) {
    translate([l / 2, w / 2, 0.6]) rotate([180, 0, 0])
        linear_extrude(1) text(str(label, " ", mode), size = 4, halign = "center", valign = "center");
}

if (mode == "back_to_back") back_to_back();
else if (mode == "head_to_head") head_to_head();
else assert(false, str("unknown mode: ", mode));
