/**
 * INT-138 — the camera path may not carry the patient's location into a
 * stored medical document.
 *
 * This issue adds the camera, and the camera is what creates the hazard:
 * `expo-image-picker`'s Android exporter copies EXIF tags from the source
 * into the exported file, and `ImagePickerConstants.EXIF_TAGS` names the GPS
 * family explicitly (TAG_GPS_LATITUDE, TAG_GPS_LONGITUDE, …). So a photo of
 * a lab report taken in the app reaches the object store carrying where the
 * patient was standing. Location is a category of personal data this project
 * has never declared (CLAUDE.md invariant 18's inventory annotation), and the
 * cheapest correct answer is not to persist it at all.
 *
 * The strip is APP1 only — the segment that carries EXIF and XMP, the two
 * metadata containers that hold coordinates. APP0 (JFIF) and APP2 (ICC colour)
 * stay, and the entropy-coded image data is never touched.
 *
 * Orientation was the one real cost, and it turns out not to be paid: on iOS
 * `ImageUtils.readImageFrom` calls `fixOrientation()` and re-encodes from the
 * bitmap, and on Android `copyExifData` lists TAG_ORIENTATION among the
 * `omittableTags` it deliberately does NOT copy — both exporters hand over an
 * upright image with no orientation tag to lose.
 */
import { describe, expect, it } from "vitest";

import { stripJpegMetadata } from "./jpeg";

const SOI = [0xff, 0xd8];
const EOI = [0xff, 0xd9];

function segment(marker: number, payload: readonly number[]): number[] {
  const length = payload.length + 2;
  return [0xff, marker, (length >> 8) & 0xff, length & 0xff, ...payload];
}

/** "Exif\0\0" then a little-endian TIFF header — the shape a camera writes. */
const EXIF_PAYLOAD = [
  0x45, 0x78, 0x69, 0x66, 0x00, 0x00, 0x49, 0x49, 0x2a, 0x00, 0x08, 0x00, 0x00, 0x00,
  // one IFD entry: tag 0x8825 (GPS IFD pointer), type LONG, count 1, offset 26
  0x01, 0x00, 0x25, 0x88, 0x04, 0x00, 0x01, 0x00, 0x00, 0x00, 0x1a, 0x00, 0x00, 0x00,
];

const APP0 = segment(0xe0, [0x4a, 0x46, 0x49, 0x46, 0x00, 0x01, 0x01]);
const APP1 = segment(0xe1, EXIF_PAYLOAD);
const APP2 = segment(0xe2, [0x49, 0x43, 0x43, 0x5f]);
const SOS = segment(0xda, [0x01, 0x01, 0x00]);
const SCAN = [0x12, 0x34, 0x56];

function jpeg(...parts: readonly (readonly number[])[]): Uint8Array<ArrayBuffer> {
  return bytes(parts.flat());
}

function bytes(values: readonly number[]): Uint8Array<ArrayBuffer> {
  const out = new Uint8Array(values.length);
  out.set(values);
  return out;
}

describe("a JPEG loses its EXIF/XMP container and nothing else", () => {
  it("drops the APP1 segment and keeps every other byte in order", () => {
    const stripped = stripJpegMetadata(jpeg(SOI, APP0, APP1, APP2, SOS, SCAN, EOI));
    expect(stripped).toEqual(jpeg(SOI, APP0, APP2, SOS, SCAN, EOI));
  });

  it("removes the GPS pointer tag the exporter would have copied", () => {
    const before = jpeg(SOI, APP0, APP1, SOS, SCAN, EOI);
    // 0x8825 little-endian, the GPS IFD pointer as it sits in the entry
    expect(Array.from(before).join(",")).toContain("37,136");
    expect(Array.from(stripJpegMetadata(before)).join(",")).not.toContain("37,136");
  });

  it("still starts SOI and ends EOI — the file stays a JPEG", () => {
    const stripped = stripJpegMetadata(jpeg(SOI, APP1, SOS, SCAN, EOI));
    expect([stripped[0], stripped[1]]).toEqual(SOI);
    expect([stripped[stripped.length - 2], stripped[stripped.length - 1]]).toEqual(EOI);
  });

  it("keeps the ICC colour profile — APP2 is not metadata about the patient", () => {
    const stripped = stripJpegMetadata(jpeg(SOI, APP2, SOS, SCAN, EOI));
    expect(stripped).toEqual(jpeg(SOI, APP2, SOS, SCAN, EOI));
  });

  it("returns a JPEG that carries no APP1 unchanged", () => {
    const clean = jpeg(SOI, APP0, SOS, SCAN, EOI);
    expect(stripJpegMetadata(clean)).toEqual(clean);
  });
});

describe("the near miss: image data that merely looks like a marker", () => {
  it("does not scan past the start of scan, so 0xFFE1 in the pixels survives", () => {
    // Entropy-coded data is not a segment stream. A parser that kept walking
    // markers past SOS would read these two bytes as an APP1 header, take the
    // next two as a length, and cut the image apart. This is the control that
    // tells a correct stripper from one that happens to pass the tests above.
    const pixels = [0x12, 0xff, 0xe1, 0x00, 0x40, 0x34];
    const source = jpeg(SOI, APP1, SOS, pixels, EOI);
    expect(stripJpegMetadata(source)).toEqual(jpeg(SOI, SOS, pixels, EOI));
  });
});

describe("anything it cannot read whole is returned untouched", () => {
  it("passes a PNG through — the strip is a JPEG rule", () => {
    const png = bytes([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x01]);
    expect(stripJpegMetadata(png)).toEqual(png);
  });

  it("passes a PDF through", () => {
    const pdf = bytes([0x25, 0x50, 0x44, 0x46, 0x2d, 0x31, 0x2e, 0x34]);
    expect(stripJpegMetadata(pdf)).toEqual(pdf);
  });

  it("returns a truncated segment untouched rather than a partial file", () => {
    // The declared length runs past the end of the buffer. Emitting what could
    // be read would upload a corrupt document that the patient believes is
    // their report; refusing to edit it at all is the only safe answer.
    const truncated = bytes([...SOI, 0xff, 0xe1, 0x00, 0x40, 0x01, 0x02]);
    expect(stripJpegMetadata(truncated)).toEqual(truncated);
  });

  it("returns a stream with a missing marker byte untouched", () => {
    const broken = bytes([...SOI, 0x00, 0xe1, 0x00, 0x04, 0x01, 0x02]);
    expect(stripJpegMetadata(broken)).toEqual(broken);
  });

  it("returns two bytes of nothing untouched", () => {
    const bare = bytes(SOI);
    expect(stripJpegMetadata(bare)).toEqual(bare);
  });

  it("tolerates 0xFF fill bytes between segments", () => {
    const padded = bytes([...SOI, 0xff, ...APP1, ...SOS, ...SCAN, ...EOI]);
    expect(stripJpegMetadata(padded)).toEqual(jpeg(SOI, SOS, SCAN, EOI));
  });
});
