/**
 * Drop the metadata container from a JPEG before it is uploaded (INT-138).
 *
 * The camera this issue adds is what makes this necessary. `expo-image-picker`
 * exports an Android capture through `CompressionImageExporter`, which calls
 * `copyExifData` to copy `ImagePickerConstants.EXIF_TAGS` from the source into
 * the exported file — and that table names the GPS family explicitly
 * (`TAG_GPS_LATITUDE`, `TAG_GPS_LONGITUDE`, `TAG_GPS_TIMESTAMP`, …). Without
 * this function a photograph of a lab report reaches the object store carrying
 * where the patient was standing when they took it.
 *
 * Location has never been declared as a category of personal data anywhere in
 * this repository, and CLAUDE.md invariant 18 requires an inventory annotation
 * — {category, purpose, basis, retention, recipients} — for every new data
 * field. The cheapest correct answer is not to persist it at all.
 *
 * **APP1 only.** That is the segment that carries EXIF and XMP, which are the
 * two containers coordinates live in. APP0 (JFIF) and APP2 (ICC colour profile)
 * are kept — a colour profile says nothing about a person, and dropping it
 * would change how the document renders for the clinician who reads it.
 *
 * **Orientation is not the cost it looks like.** Both exporters hand over an
 * upright bitmap with no orientation tag to lose: on iOS `ImageUtils
 * .readImageFrom` calls `fixOrientation()` and re-encodes, and on Android
 * `copyExifData` lists `TAG_ORIENTATION` among the `omittableTags` it
 * deliberately does not copy.
 *
 * **Anything it cannot read whole is returned untouched.** A partially rewritten
 * JPEG is a corrupt document the patient believes is their report, which is
 * worse than the metadata. Non-JPEG bytes (PDF, PNG) pass straight through.
 */

const MARKER = 0xff;
const SOI = 0xd8;
const EOI = 0xd9;
const SOS = 0xda;
const APP1 = 0xe1;
const TEM = 0x01;
const RST_FIRST = 0xd0;
const RST_LAST = 0xd7;

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

/**
 * `bytes` with every APP1 segment removed, or `bytes` unchanged when they are
 * not a JPEG this reader can walk end to end.
 */
export function stripJpegMetadata(bytes: Uint8Array<ArrayBuffer>): Uint8Array<ArrayBuffer> {
  if (bytes.length < 2 || bytes[0] !== MARKER || bytes[1] !== SOI) {
    return bytes;
  }
  const kept: Uint8Array<ArrayBuffer>[] = [bytes.subarray(0, 2)];
  let dropped = false;
  let at = 2;

  while (at < bytes.length) {
    const segmentStart = at;
    if (bytes[at] !== MARKER) {
      return bytes; // not a marker where one must be: do not edit what we misread
    }
    // A run of 0xFF before the marker byte is legal padding; it belongs to the
    // segment it introduces, so it is kept or dropped with it.
    let markerAt = at + 1;
    while (markerAt < bytes.length && bytes[markerAt] === MARKER) {
      markerAt += 1;
    }
    if (markerAt >= bytes.length) {
      return bytes;
    }
    const marker = bytes[markerAt];

    if (isStandalone(marker)) {
      kept.push(bytes.subarray(segmentStart, markerAt + 1));
      at = markerAt + 1;
      continue;
    }
    if (marker === SOS || marker === EOI) {
      // Past the start of scan the stream is entropy-coded data, not segments:
      // a 0xFFE1 pair in the pixels is image, not an APP1 header. Everything
      // from here on is copied verbatim.
      kept.push(bytes.subarray(segmentStart));
      at = bytes.length;
      break;
    }
    if (markerAt + 2 >= bytes.length) {
      return bytes;
    }
    const length = (bytes[markerAt + 1] << 8) | bytes[markerAt + 2];
    const segmentEnd = markerAt + 1 + length;
    if (length < 2 || segmentEnd > bytes.length) {
      return bytes;
    }
    if (marker === APP1) {
      dropped = true;
    } else {
      kept.push(bytes.subarray(segmentStart, segmentEnd));
    }
    at = segmentEnd;
  }

  return dropped ? concat(kept) : bytes;
}
