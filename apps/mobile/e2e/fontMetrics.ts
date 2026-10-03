/**
 * Advance widths, read out of the face the app actually ships (INT-295).
 *
 * React Native has no DOM and vitest has no text engine, so a claim about
 * whether a Turkish label fits a phone can be arithmetic or it can be a
 * guess. This module makes it arithmetic: it reads a TrueType file and sums
 * the horizontal advances the font itself declares for the exact code points
 * in a string.
 *
 * Since INT-422 the app sets the platform face (SF Pro on iOS), which is not
 * redistributable, so the specs read Inter (OFL) instead. On the build Mac SF
 * Pro's advances measured 0.85 to 0.91 of Inter's across all 1066 Turkish
 * catalogue strings, and SF Pro Semibold set by CoreText 0.92 of Inter
 * SemiBold on the widest question words (docs/evidence/INT-422.md): a line
 * that fits in Inter fits
 * on the device, and Inter is an upper bound in the same direction as the
 * kerning note below.
 *
 * What it does NOT model: kerning. Inter carries its pairs in GPOS, which
 * CoreText applies and this reader ignores, and kerning only ever pulls
 * glyphs closer. The number returned is therefore an upper bound on the
 * natural width — the safe direction for a "does it fit" assertion, since
 * the error can only make a passing layout look tighter than it is.
 *
 * Validated against a device: at the app's largest text step the model puts
 * the `intake.mode.hastanedeyim` chip at 196.0 pt, and the same chip
 * measured 195.7 pt in the iPhone 16 Pro capture recorded in
 * docs/evidence/INT-295.md. Sixteen tables, one file, no network.
 */
import { readFileSync } from "node:fs";

/** A parsed face: everything needed to advance a caret across a string. */
export interface FontMetrics {
  /** The natural width of `text` set at `fontSizePt`, in points. */
  readonly advance: (text: string, fontSizePt: number) => number;
}

interface TableRecord {
  readonly offset: number;
  readonly length: number;
}

function tables(buf: Buffer): Map<string, TableRecord> {
  const count = buf.readUInt16BE(4);
  const found = new Map<string, TableRecord>();
  for (let i = 0; i < count; i += 1) {
    const record = 12 + 16 * i;
    found.set(buf.toString("ascii", record, record + 4), {
      offset: buf.readUInt32BE(record + 8),
      length: buf.readUInt32BE(record + 12),
    });
  }
  return found;
}

function required(found: Map<string, TableRecord>, tag: string): TableRecord {
  const record = found.get(tag);
  if (record === undefined) {
    throw new Error(`font has no ${tag} table; it cannot be measured`);
  }
  return record;
}

/**
 * The best character map the face offers. Format 12 covers the whole of
 * Unicode and format 4 covers the Basic Multilingual Plane; Turkish lives in
 * the BMP, so either answers, and 12 is preferred where both exist.
 */
function selectCmap(buf: Buffer, cmap: TableRecord): { offset: number; format: number } {
  const encodings = buf.readUInt16BE(cmap.offset + 2);
  let best: { offset: number; format: number } | null = null;
  for (let i = 0; i < encodings; i += 1) {
    const record = cmap.offset + 4 + 8 * i;
    const offset = cmap.offset + buf.readUInt32BE(record + 4);
    const format = buf.readUInt16BE(offset);
    if (format !== 4 && format !== 12) {
      continue;
    }
    if (best === null || (format === 12 && best.format !== 12)) {
      best = { offset, format };
    }
  }
  if (best === null) {
    throw new Error("font carries no format 4 or format 12 character map");
  }
  return best;
}

function glyphFormat12(buf: Buffer, offset: number, codePoint: number): number {
  const groups = buf.readUInt32BE(offset + 12);
  for (let i = 0; i < groups; i += 1) {
    const group = offset + 16 + 12 * i;
    const start = buf.readUInt32BE(group);
    const end = buf.readUInt32BE(group + 4);
    if (codePoint >= start && codePoint <= end) {
      return buf.readUInt32BE(group + 8) + (codePoint - start);
    }
  }
  return 0;
}

function glyphFormat4(buf: Buffer, offset: number, codePoint: number): number {
  const segmentsX2 = buf.readUInt16BE(offset + 6);
  const endCodes = offset + 14;
  const startCodes = endCodes + segmentsX2 + 2;
  const deltas = startCodes + segmentsX2;
  const rangeOffsets = deltas + segmentsX2;
  for (let i = 0; i < segmentsX2 / 2; i += 1) {
    if (codePoint > buf.readUInt16BE(endCodes + 2 * i)) {
      continue;
    }
    const start = buf.readUInt16BE(startCodes + 2 * i);
    if (codePoint < start) {
      return 0;
    }
    const delta = buf.readInt16BE(deltas + 2 * i);
    const rangeOffset = buf.readUInt16BE(rangeOffsets + 2 * i);
    if (rangeOffset === 0) {
      return (codePoint + delta) & 0xffff;
    }
    const glyph = buf.readUInt16BE(rangeOffsets + 2 * i + rangeOffset + 2 * (codePoint - start));
    return glyph === 0 ? 0 : (glyph + delta) & 0xffff;
  }
  return 0;
}

/**
 * Parse a TrueType file into a width model.
 *
 * A code point the face cannot render raises rather than scoring zero: a
 * silent zero would shrink a string the app can still be asked to draw, and
 * a fit assertion that under-measures is the one failure mode that matters
 * here.
 */
export function readFontMetrics(path: string): FontMetrics {
  const buf = readFileSync(path);
  const found = tables(buf);
  const unitsPerEm = buf.readUInt16BE(required(found, "head").offset + 18);
  const metricCount = buf.readUInt16BE(required(found, "hhea").offset + 34);
  const hmtx = required(found, "hmtx").offset;
  const map = selectCmap(buf, required(found, "cmap"));
  const glyphs = new Map<number, number>();

  const glyphFor = (codePoint: number): number => {
    const cached = glyphs.get(codePoint);
    if (cached !== undefined) {
      return cached;
    }
    const glyph =
      map.format === 12
        ? glyphFormat12(buf, map.offset, codePoint)
        : glyphFormat4(buf, map.offset, codePoint);
    if (glyph === 0) {
      throw new Error(`the face has no glyph for U+${codePoint.toString(16).toUpperCase()}`);
    }
    glyphs.set(codePoint, glyph);
    return glyph;
  };

  return {
    advance(text: string, fontSizePt: number): number {
      let units = 0;
      for (const character of text) {
        const glyph = glyphFor(character.codePointAt(0) ?? 0);
        units += buf.readUInt16BE(hmtx + 4 * Math.min(glyph, metricCount - 1));
      }
      return (units / unitsPerEm) * fontSizePt;
    },
  };
}
