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
 * Orientation IS a real cost, and this file used to claim it was not. The old
 * claim cited Android's `copyExifData` omitting TAG_ORIENTATION — true of
 * `copyExifData`, and `copyExifData` is on a path this app does not take.
 * `MediaHandler.kt` picks `RawImageExporter` while `quality` sits at its `1.0`
 * default, and that exporter is a straight `copyFile`: the camera's own file,
 * orientation tag and all. iOS has the same shape, with `imageModified` false
 * and `tryCopyingOriginalImageFrom` one non-nil `mediaInfo[.imageURL]` away from
 * a raw copy of the original.
 *
 * So the tag is CARRIED rather than assumed away: the strip reads Orientation out
 * of the old APP1 and writes a 34-byte APP1 of its own holding that tag and
 * nothing else. Correct on every path — raw copy or re-encode, capture or file
 * pick — which is what an assumption about one exporter was not.
 */
import { describe, expect, it } from "vitest";

import { readJpegOrientation, stripJpegMetadata } from "./jpeg";

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

/* ------------------------------------------------------------------ */
/* Orientation: the one tag that survives, and the ways it can be lost  */
/* ------------------------------------------------------------------ */

interface Entry {
  tag: number;
  type?: number;
  count?: number;
  value: number;
}

/** A TIFF/EXIF APP1 payload with the entries asked for, in either byte order. */
function exifPayload(opts: {
  little?: boolean;
  ifd0: readonly Entry[];
  ifd1?: readonly Entry[];
}): number[] {
  const little = opts.little === true;
  const w16 = (n: number): number[] =>
    little ? [n & 0xff, (n >> 8) & 0xff] : [(n >> 8) & 0xff, n & 0xff];
  const w32 = (n: number): number[] =>
    little
      ? [n & 0xff, (n >> 8) & 0xff, (n >> 16) & 0xff, (n >> 24) & 0xff]
      : [(n >> 24) & 0xff, (n >> 16) & 0xff, (n >> 8) & 0xff, n & 0xff];
  const entry = (e: Entry): number[] => [
    ...w16(e.tag),
    ...w16(e.type ?? 3),
    ...w32(e.count ?? 1),
    // a SHORT sits in the first half of the 4-byte value field
    ...((e.type ?? 3) === 3 ? [...w16(e.value), 0x00, 0x00] : w32(e.value)),
  ];
  const ifd = (entries: readonly Entry[], next: number): number[] => [
    ...w16(entries.length),
    ...entries.flatMap(entry),
    ...w32(next),
  ];
  const ifd0Size = 2 + opts.ifd0.length * 12 + 4;
  const ifd1Offset = opts.ifd1 === undefined ? 0 : 8 + ifd0Size;
  return [
    ...EXIF_PAYLOAD.slice(0, 6), // "Exif\0\0"
    ...(little ? [0x49, 0x49] : [0x4d, 0x4d]),
    ...w16(42),
    ...w32(8),
    ...ifd(opts.ifd0, ifd1Offset),
    ...(opts.ifd1 === undefined ? [] : ifd(opts.ifd1, 0)),
  ];
}

const ORIENTATION_TAG = 0x0112;
const GPS_POINTER = { tag: 0x8825, type: 4, value: 0 };

function app1(payload: readonly number[]): number[] {
  return segment(0xe1, payload);
}

/** Every APP1 segment in a stream, as `[markerIndex, declaredLength]`. */
function app1Segments(image: Uint8Array): [number, number][] {
  const found: [number, number][] = [];
  for (let i = 2; i + 3 < image.length; i += 1) {
    if (image[i] === 0xff && image[i + 1] === 0xe1) {
      found.push([i, (image[i + 2] << 8) | image[i + 3]]);
    }
    if (image[i] === 0xff && image[i + 1] === 0xda) {
      break; // entropy-coded data is not a segment stream
    }
  }
  return found;
}

describe("the orientation tag is carried, and it is carried alone", () => {
  it("keeps the orientation and drops the GPS pointer sitting beside it", () => {
    const source = jpeg(
      SOI,
      APP0,
      app1(exifPayload({ ifd0: [GPS_POINTER, { tag: ORIENTATION_TAG, value: 6 }] })),
      SOS,
      SCAN,
      EOI,
    );
    expect(readJpegOrientation(source)).toBe(6);
    const stripped = stripJpegMetadata(source);
    expect(readJpegOrientation(stripped)).toBe(6);
    expect(Array.from(stripped).join(",")).not.toContain("37,136");
  });

  it("writes exactly one APP1, 34 declared bytes, in the position the old one held", () => {
    const source = jpeg(
      SOI,
      APP0,
      app1(exifPayload({ ifd0: [{ tag: ORIENTATION_TAG, value: 3 }] })),
      APP2,
      SOS,
      SCAN,
      EOI,
    );
    const stripped = stripJpegMetadata(source);
    const segments = app1Segments(stripped);
    expect(segments).toHaveLength(1);
    expect(segments[0][1]).toBe(34);
    // SOI, APP0, then the replacement, then APP2 — order preserved
    expect(segments[0][0]).toBe(SOI.length + APP0.length);
  });

  it.each([2, 3, 4, 5, 6, 7, 8])("round-trips orientation %i", (orientation) => {
    const source = jpeg(
      SOI,
      app1(exifPayload({ ifd0: [{ tag: ORIENTATION_TAG, value: orientation }] })),
      SOS,
      SCAN,
      EOI,
    );
    expect(readJpegOrientation(stripJpegMetadata(source))).toBe(orientation);
  });

  it("NEAR MISS: reads a little-endian TIFF block in its own byte order", () => {
    // A reader that assumed big-endian would read orientation 8 as 0x0800 —
    // out of range, so `null`, so the tag silently vanishes and the clinician
    // gets a sideways report. Byte order is load-bearing, not cosmetic.
    const source = jpeg(
      SOI,
      app1(exifPayload({ little: true, ifd0: [{ tag: ORIENTATION_TAG, value: 8 }] })),
      SOS,
      SCAN,
      EOI,
    );
    expect(readJpegOrientation(source)).toBe(8);
    expect(readJpegOrientation(stripJpegMetadata(source))).toBe(8);
  });

  it("NEAR MISS: ignores an orientation that belongs to the THUMBNAIL", () => {
    // IFD1 describes the embedded preview. Rotating the document by whatever
    // the camera did to its thumbnail is a different image's fact.
    const source = jpeg(
      SOI,
      app1(exifPayload({ ifd0: [GPS_POINTER], ifd1: [{ tag: ORIENTATION_TAG, value: 6 }] })),
      SOS,
      SCAN,
      EOI,
    );
    expect(readJpegOrientation(source)).toBeNull();
    expect(app1Segments(stripJpegMetadata(source))).toHaveLength(0);
  });

  it("writes no segment for orientation 1 — upright needs no tag to say so", () => {
    const source = jpeg(
      SOI,
      app1(exifPayload({ ifd0: [{ tag: ORIENTATION_TAG, value: 1 }] })),
      SOS,
      SCAN,
      EOI,
    );
    expect(app1Segments(stripJpegMetadata(source))).toHaveLength(0);
  });

  it("writes no segment when the source declared no orientation", () => {
    const source = jpeg(SOI, app1(exifPayload({ ifd0: [GPS_POINTER] })), SOS, SCAN, EOI);
    expect(app1Segments(stripJpegMetadata(source))).toHaveLength(0);
  });

  it("refuses an orientation in the wrong shape rather than reading it anyway", () => {
    const source = jpeg(
      SOI,
      app1(exifPayload({ ifd0: [{ tag: ORIENTATION_TAG, type: 4, count: 1, value: 6 }] })),
      SOS,
      SCAN,
      EOI,
    );
    expect(readJpegOrientation(source)).toBeNull();
  });

  it("reads nothing out of an APP1 that is not EXIF at all (XMP)", () => {
    const xmp = [0x68, 0x74, 0x74, 0x70, 0x3a, 0x2f, 0x2f, 0x6e, 0x73];
    const source = jpeg(SOI, app1(xmp), SOS, SCAN, EOI);
    expect(readJpegOrientation(source)).toBeNull();
    expect(app1Segments(stripJpegMetadata(source))).toHaveLength(0);
  });

  it("reads nothing out of a truncated directory rather than walking off the end", () => {
    const short = exifPayload({ ifd0: [{ tag: ORIENTATION_TAG, value: 6 }] }).slice(0, 14);
    const source = jpeg(SOI, app1(short), SOS, SCAN, EOI);
    expect(readJpegOrientation(source)).toBeNull();
    expect(stripJpegMetadata(source)).toEqual(jpeg(SOI, SOS, SCAN, EOI));
  });

  it("reads nothing out of a non-JPEG", () => {
    expect(readJpegOrientation(bytes([0x89, 0x50, 0x4e, 0x47]))).toBeNull();
  });
});
