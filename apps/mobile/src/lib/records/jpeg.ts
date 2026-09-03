/**
 * Drop the metadata container from a JPEG before it is uploaded (INT-138).
 *
 * The camera this issue adds is what makes this necessary. On the path this app
 * actually takes — `quality` at its `1.0` default — Android's `RawImageExporter`
 * copies the camera's file byte for byte, so the ENTIRE original EXIF reaches the
 * upload: the GPS family, the maker notes and an embedded thumbnail that is a
 * second copy of the document. (The compressing exporter is no better on the
 * point that matters: `ImagePickerConstants.EXIF_TAGS` names `TAG_GPS_LATITUDE`,
 * `TAG_GPS_LONGITUDE` and `TAG_GPS_TIMESTAMP` among the tags it deliberately
 * copies forward.) Without this function a photograph of a lab report reaches the
 * object store carrying where the patient was standing when they took it.
 *
 * Location has never been declared as a category of personal data anywhere in
 * this repository, and CLAUDE.md invariant 18 requires an inventory annotation
 * — {category, purpose, basis, retention, recipients} — for every new data
 * field. The cheapest correct answer is not to persist it at all.
 *
 * **APP1 only, and one tag survives it.** APP1 is the segment that carries EXIF
 * and XMP, the two containers coordinates live in. APP0 (JFIF) and APP2 (ICC
 * colour profile) are kept — a colour profile says nothing about a person, and
 * dropping it would change how the document renders for the clinician. The one
 * thing read out of the old APP1 and written back into a new one is
 * **Orientation**, because deleting it turns an upright lab report sideways.
 *
 * **Why orientation has to be carried rather than assumed away.** An earlier
 * version of this file argued that both exporters hand over an upright bitmap
 * with no orientation tag to lose, citing Android's `copyExifData` omitting
 * `TAG_ORIENTATION`. That is true of `copyExifData` — and `copyExifData` is on
 * a path this app does not take. `MediaHandler.kt` picks `RawImageExporter`
 * whenever `options.quality == MAXIMUM_QUALITY`, `ImagePickerOptions.kt`
 * defaults `quality` to `1.0`, and `RawImageExporter` is a straight `copyFile`
 * — no re-encode, no `omittableTags`, the ENTIRE original EXIF preserved.
 * iOS has the same shape from the other side: `MediaHandler.swift` sets
 * `imageModified = allowsEditing || quality < 1`, and when that is false it
 * tries `tryCopyingOriginalImageFrom`, a raw file copy; a camera capture
 * survives today only because `mediaInfo[.imageURL]` happens to be nil there
 * and it falls back to a `fixOrientation()`-ed bitmap. That is an unwritten
 * UIKit behaviour, one non-nil away from copying the original file.
 *
 * So on both platforms the bytes reaching this function can be the camera's own
 * file, orientation tag and all. Carrying the tag explicitly is correct on every
 * path — raw copy or re-encode, capture or file pick — which is exactly what an
 * assumption about one exporter was not.
 *
 * Two things fall out of the raw copy and they point the same way: the original
 * also carries maker notes and an embedded EXIF **thumbnail**, which is a second
 * copy of the patient's document. Dropping APP1 removes both. The replacement is
 * 34 bytes this file authors and holds one tag, so nothing survives that was not
 * chosen.
 *
 * **Anything it cannot read whole is returned untouched.** A partially rewritten
 * JPEG is a corrupt document the patient believes is their report, which is worse
 * than the metadata. Non-JPEG bytes (PDF, PNG) pass straight through. That trade
 * — file integrity over invariant 6 — is named in the `records` threat row for a
 * human to confirm or overturn, along with PNG's own `eXIf`/XMP containers, which
 * this function does NOT strip.
 */

const MARKER = 0xff;
const SOI = 0xd8;
const EOI = 0xd9;
const SOS = 0xda;
const APP1 = 0xe1;
const TEM = 0x01;
const RST_FIRST = 0xd0;
const RST_LAST = 0xd7;

/** "Exif\0\0" — the six bytes that open an EXIF APP1 payload. */
const EXIF_PREFIX = [0x45, 0x78, 0x69, 0x66, 0x00, 0x00] as const;
const BYTE_ORDER_LITTLE = 0x4949; // "II"
const BYTE_ORDER_BIG = 0x4d4d; // "MM"
const TIFF_MAGIC = 42;
const TAG_ORIENTATION = 0x0112;
const TYPE_SHORT = 3;
/** EXIF orientation is 1-8; 1 is upright, so it needs no tag to say so. */
const ORIENTATION_MIN = 1;
const ORIENTATION_MAX = 8;

/** Markers that carry no length word, so nothing follows them to skip. */
function isStandalone(marker: number): boolean {
  return marker === TEM || marker === SOI || (marker >= RST_FIRST && marker <= RST_LAST);
}

function concat(parts: readonly Uint8Array<ArrayBuffer>[]): Uint8Array<ArrayBuffer> {
  let total = 0;
  for (const part of parts) {
    total += part.length;
  }
  const out = new Uint8Array(total);
  let at = 0;
  for (const part of parts) {
    out.set(part, at);
    at += part.length;
  }
  return out;
}

function u16(bytes: Uint8Array, at: number, little: boolean): number {
  return little ? bytes[at] | (bytes[at + 1] << 8) : (bytes[at] << 8) | bytes[at + 1];
}

function u32(bytes: Uint8Array, at: number, little: boolean): number {
  return little
    ? (bytes[at] | (bytes[at + 1] << 8) | (bytes[at + 2] << 16) | (bytes[at + 3] << 24)) >>> 0
    : ((bytes[at] << 24) | (bytes[at + 1] << 16) | (bytes[at + 2] << 8) | bytes[at + 3]) >>> 0;
}

/**
 * The EXIF orientation of an APP1 payload, or `null` when there is not one this
 * reader can vouch for.
 *
 * IFD0 only. IFD1 holds the THUMBNAIL's orientation, which is a fact about a
 * different image; reading it would rotate the document by whatever the camera
 * did to its preview.
 */
function orientationOf(payload: Uint8Array): number | null {
  if (payload.length < EXIF_PREFIX.length + 8) {
    return null;
  }
  for (let i = 0; i < EXIF_PREFIX.length; i += 1) {
    if (payload[i] !== EXIF_PREFIX[i]) {
      return null; // XMP or another APP1 flavour: no TIFF header to walk
    }
  }
  const tiff = EXIF_PREFIX.length;
  const order = (payload[tiff] << 8) | payload[tiff + 1];
  if (order !== BYTE_ORDER_LITTLE && order !== BYTE_ORDER_BIG) {
    return null;
  }
  const little = order === BYTE_ORDER_LITTLE;
  if (u16(payload, tiff + 2, little) !== TIFF_MAGIC) {
    return null;
  }
  const ifd0 = tiff + u32(payload, tiff + 4, little);
  if (ifd0 + 2 > payload.length) {
    return null;
  }
  const entries = u16(payload, ifd0, little);
  if (ifd0 + 2 + entries * 12 > payload.length) {
    return null; // a count the buffer cannot hold is not a directory
  }
  for (let i = 0; i < entries; i += 1) {
    const entry = ifd0 + 2 + i * 12;
    if (u16(payload, entry, little) !== TAG_ORIENTATION) {
      continue;
    }
    if (u16(payload, entry + 2, little) !== TYPE_SHORT || u32(payload, entry + 4, little) !== 1) {
      return null; // the right tag in the wrong shape is not an orientation
    }
    const value = u16(payload, entry + 8, little);
    return value >= ORIENTATION_MIN && value <= ORIENTATION_MAX ? value : null;
  }
  return null;
}

/**
 * A 34-byte APP1 holding exactly one tag: Orientation, big-endian, IFD0, no
 * next directory. Authored here rather than salvaged, so nothing rides along.
 */
function orientationSegment(orientation: number): Uint8Array<ArrayBuffer> {
  const payload = [
    ...EXIF_PREFIX,
    0x4d,
    0x4d,
    0x00,
    0x2a, // "MM", 42
    0x00,
    0x00,
    0x00,
    0x08, // IFD0 begins 8 bytes into the TIFF block
    0x00,
    0x01, // one entry
    0x01,
    0x12, // Orientation
    0x00,
    0x03, // SHORT
    0x00,
    0x00,
    0x00,
    0x01, // count 1
    (orientation >> 8) & 0xff,
    orientation & 0xff,
    0x00,
    0x00, // the value occupies the first half of the 4-byte field
    0x00,
    0x00,
    0x00,
    0x00, // no next IFD
  ];
  const length = payload.length + 2;
  const out = new Uint8Array(payload.length + 4);
  out.set([MARKER, APP1, (length >> 8) & 0xff, length & 0xff]);
  out.set(payload, 4);
  return out;
}

/** The EXIF orientation this JPEG declares, or `null`. Exported for tests. */
export function readJpegOrientation(bytes: Uint8Array): number | null {
  const payload = firstApp1Payload(bytes);
  return payload === null ? null : orientationOf(payload);
}

function firstApp1Payload(bytes: Uint8Array): Uint8Array | null {
  let found: Uint8Array | null = null;
  walkJpeg(bytes, (marker, segmentStart, segmentEnd, markerAt) => {
    if (marker === APP1 && found === null) {
      found = bytes.subarray(markerAt + 3, segmentEnd);
    }
    void segmentStart;
    return true;
  });
  return found;
}

/**
 * Walk the segment stream, calling `visit` for every length-carrying segment.
 * Returns false when the stream is not one this reader can follow end to end.
 */
function walkJpeg(
  bytes: Uint8Array,
  visit: (marker: number, segmentStart: number, segmentEnd: number, markerAt: number) => boolean,
): boolean {
  if (bytes.length < 2 || bytes[0] !== MARKER || bytes[1] !== SOI) {
    return false;
  }
  let at = 2;
  while (at < bytes.length) {
    const segmentStart = at;
    if (bytes[at] !== MARKER) {
      return false; // not a marker where one must be: do not edit what we misread
    }
    // A run of 0xFF before the marker byte is legal padding; it belongs to the
    // segment it introduces, so it is kept or dropped with it.
    let markerAt = at + 1;
    while (markerAt < bytes.length && bytes[markerAt] === MARKER) {
      markerAt += 1;
    }
    if (markerAt >= bytes.length) {
      return false;
    }
    const marker = bytes[markerAt];
    if (isStandalone(marker)) {
      if (!visit(marker, segmentStart, markerAt + 1, markerAt)) {
        return true;
      }
      at = markerAt + 1;
      continue;
    }
    if (marker === SOS || marker === EOI) {
      // Past the start of scan the stream is entropy-coded data, not segments:
      // a 0xFFE1 pair in the pixels is image, not an APP1 header.
      visit(marker, segmentStart, bytes.length, markerAt);
      return true;
    }
    if (markerAt + 2 >= bytes.length) {
      return false;
    }
    const length = (bytes[markerAt + 1] << 8) | bytes[markerAt + 2];
    const segmentEnd = markerAt + 1 + length;
    if (length < 2 || segmentEnd > bytes.length) {
      return false;
    }
    if (!visit(marker, segmentStart, segmentEnd, markerAt)) {
      return true;
    }
    at = segmentEnd;
  }
  return true;
}

/**
 * `bytes` with every APP1 segment removed and the EXIF orientation carried
 * across in a 34-byte segment of this file's own making — or `bytes` unchanged
 * when they are not a JPEG this reader can walk end to end.
 */
export function stripJpegMetadata(bytes: Uint8Array<ArrayBuffer>): Uint8Array<ArrayBuffer> {
  const orientation = readJpegOrientation(bytes);
  // 1 means upright, and an absent tag says the same thing more quietly.
  const replacement =
    orientation !== null && orientation !== ORIENTATION_MIN
      ? orientationSegment(orientation)
      : null;

  const kept: Uint8Array<ArrayBuffer>[] = [bytes.subarray(0, 2)];
  let dropped = false;
  let replaced = false;
  const walked = walkJpeg(bytes, (marker, segmentStart, segmentEnd) => {
    if (marker === APP1) {
      dropped = true;
      if (replacement !== null && !replaced) {
        // In the position the original held, so segment order is preserved.
        kept.push(replacement);
        replaced = true;
      }
      return true;
    }
    kept.push(bytes.subarray(segmentStart, segmentEnd));
    return true;
  });
  if (!walked) {
    return bytes;
  }
  return dropped ? concat(kept) : bytes;
}
