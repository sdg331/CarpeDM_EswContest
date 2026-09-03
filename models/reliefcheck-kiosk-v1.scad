// ReliefCheck kiosk v1 concept model
// Unit: millimeter
// This is a first layout model for demo and review, not a fabrication-ready CAD file.

$fn = 36;

module part_box(name, pos, size, color_value) {
  color(color_value)
    translate(pos)
      cube(size, center = true);
}

module label_plate(pos, size, color_value) {
  color(color_value)
    translate(pos)
      cube(size, center = true);
}

module touch_display() {
  translate([0, 74, 342])
    rotate([-14, 0, 0]) {
      part_box("screen_frame", [0, 0, 0], [290, 18, 185], "#1f2933");
      part_box("screen_glass", [0, -10, 0], [262, 3, 156], "#111827");
      label_plate([0, -12, 0], [236, 2, 126], "#1769e0");
    }
}

module camera_module() {
  color("#2f3945")
    translate([0, 126, 402])
      cylinder(h = 130, r = 9, center = true);
  part_box("camera_head", [0, 126, 476], [74, 28, 42], "#1f2933");
  color("#0f172a")
    translate([0, 109, 476])
      rotate([90, 0, 0])
        cylinder(h = 4, r = 10, center = true);
}

module nfc_pad(x_pos, color_value) {
  part_box("nfc_pad", [x_pos, -92, 249], [126, 92, 10], color_value);
  color("#ffffff")
    translate([x_pos, -92, 255])
      cylinder(h = 2, r = 32, center = true);
}

module printer_module() {
  part_box("printer_module", [0, -168, 158], [170, 54, 76], "#374151");
  part_box("paper_slot", [0, -197, 181], [138, 8, 18], "#111827");
  part_box("receipt_paper", [0, -210, 171], [140, 66, 2], "#f8fafc");
}

module pi_service_bay() {
  part_box("pi_service_cover", [0, 136, 126], [156, 12, 86], "#4b5563");
  part_box("cable_exit", [0, 174, 54], [90, 10, 34], "#111827");
}

module reliefcheck_kiosk_v1() {
  part_box("base_plinth", [0, 0, 14], [460, 340, 28], "#d8dee4");
  part_box("main_body", [0, -8, 120], [390, 265, 184], "#f8fafc");
  part_box("touch_console", [0, -32, 226], [430, 260, 34], "#e5e7eb");

  nfc_pad(-108, "#1769e0");
  nfc_pad(108, "#147447");
  printer_module();
  touch_display();
  camera_module();
  pi_service_bay();

  // Foot pads
  part_box("foot_left_front", [-170, -135, -4], [70, 46, 8], "#9ca3af");
  part_box("foot_right_front", [170, -135, -4], [70, 46, 8], "#9ca3af");
  part_box("foot_left_back", [-170, 135, -4], [70, 46, 8], "#9ca3af");
  part_box("foot_right_back", [170, 135, -4], [70, 46, 8], "#9ca3af");
}

reliefcheck_kiosk_v1();
