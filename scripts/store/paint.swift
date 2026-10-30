// INT-502: the painter for the App Store frames and header.
//
// It reads one JSON file of plans written by scripts/store/render_frames.py and
// draws each one with CoreGraphics and CoreText: the ground, the caption text, and
// the phone. The phone is a drawn body with a capture clipped to its screen. The
// capture carries the simulator's alpha mask, so the device's own corners and island
// show the body colour through it. Every position, size, colour and font path comes
// from the plan, which scripts/store/frame_plan.py computes and the tests check. This file makes no layout
// decision. It does refuse text that cannot fit its box at the plan's smallest size,
// rather than shrinking it further.
//
// The output is PNG, 8-bit RGB with no alpha channel, as App Store Connect requires.
//
// Usage: swiftc -O -o paint scripts/store/paint.swift && ./paint plans.json

import CoreGraphics
import CoreText
import Foundation
import ImageIO
import UniformTypeIdentifiers

struct Shadow: Decodable {
    let color: String
    let opacity: Double
    let blur: Double
    let offset_y: Double
}

struct Item: Decodable {
    let kind: String
    // text
    let text: String?
    let font: String?
    let size: Double?
    let min_size: Double?
    let color: String?
    let box: [Double]?
    let align: String?
    let leading: Double?
    // phone
    let capture: String?
    let body: [Double]?
    let screen: [Double]?
    let outer_radius: Double?
    let screen_radius: Double?
    let body_color: String?
    let rim_color: String?
    let rim_width: Double?
    let shadow: Shadow?
}

struct Plan: Decodable {
    let out: String
    let width: Int
    let height: Int
    let ground: String
    let items: [Item]
}

struct Plans: Decodable {
    let jobs: [Plan]
}

struct PaintError: Error, CustomStringConvertible {
    let description: String
}

func colour(_ hex: String, alpha: Double = 1.0) throws -> CGColor {
    let digits = hex.hasPrefix("#") ? String(hex.dropFirst()) : hex
    guard digits.count == 6, let value = UInt32(digits, radix: 16) else {
        throw PaintError(description: "colour \(hex) is not #RRGGBB")
    }
    let r = Double((value >> 16) & 0xFF) / 255.0
    let g = Double((value >> 8) & 0xFF) / 255.0
    let b = Double(value & 0xFF) / 255.0
    return CGColor(srgbRed: r, green: g, blue: b, alpha: alpha)
}

/// A plan rectangle is [x, y, w, h] from the top-left; CoreGraphics counts from the
/// bottom-left.
func rect(_ raw: [Double]?, canvasHeight: Double) throws -> CGRect {
    guard let raw, raw.count == 4 else { throw PaintError(description: "a rect is [x, y, w, h]") }
    return CGRect(x: raw[0], y: canvasHeight - raw[1] - raw[3], width: raw[2], height: raw[3])
}

func loadFont(_ path: String, size: Double) throws -> CTFont {
    let url = URL(fileURLWithPath: path) as CFURL
    guard let descriptors = CTFontManagerCreateFontDescriptorsFromURL(url) as? [CTFontDescriptor],
        let first = descriptors.first
    else {
        throw PaintError(description: "font \(path) cannot be read")
    }
    return CTFontCreateWithFontDescriptor(first, CGFloat(size), nil)
}

func line(_ text: String, font: CTFont, colour: CGColor) -> CTLine {
    let attributes: [NSAttributedString.Key: Any] = [
        NSAttributedString.Key(kCTFontAttributeName as String): font,
        NSAttributedString.Key(kCTForegroundColorAttributeName as String): colour,
    ]
    return CTLineCreateWithAttributedString(NSAttributedString(string: text, attributes: attributes))
}

func drawText(_ item: Item, in ctx: CGContext, canvasHeight: Double) throws {
    guard let text = item.text, let fontPath = item.font, var size = item.size,
        let colourHex = item.color, let box = item.box, box.count == 4
    else { throw PaintError(description: "a text item lacks a field") }
    let floor = item.min_size ?? size
    let ink = try colour(colourHex)
    let rows = text.components(separatedBy: "\n")
    var font = try loadFont(fontPath, size: size)
    var lines = rows.map { line($0, font: font, colour: ink) }
    func widest() -> Double {
        lines.map { Double(CTLineGetTypographicBounds($0, nil, nil, nil)) }.max() ?? 0
    }
    while widest() > box[2] {
        size -= 1
        if size < floor {
            throw PaintError(description: "\"\(text)\" does not fit \(Int(box[2])) px at \(Int(floor)) px")
        }
        font = try loadFont(fontPath, size: size)
        lines = rows.map { line($0, font: font, colour: ink) }
    }
    let ascent = Double(CTFontGetAscent(font))
    let step = size * (item.leading ?? 1.0)
    for (index, row) in lines.enumerated() {
        let width = Double(CTLineGetTypographicBounds(row, nil, nil, nil))
        let x: Double
        switch item.align ?? "center" {
        case "left": x = box[0]
        default: x = box[0] + (box[2] - width) / 2
        }
        let baselineFromTop = box[1] + ascent + Double(index) * step
        ctx.textPosition = CGPoint(x: x, y: canvasHeight - baselineFromTop)
        CTLineDraw(row, ctx)
    }
}

func loadImage(_ path: String) throws -> CGImage {
    let url = URL(fileURLWithPath: path) as CFURL
    guard let source = CGImageSourceCreateWithURL(url, nil),
        let image = CGImageSourceCreateImageAtIndex(source, 0, nil)
    else {
        throw PaintError(description: "capture \(path) cannot be read")
    }
    return image
}

func roundedPath(_ r: CGRect, radius: Double) -> CGPath {
    let limit = min(r.width, r.height) / 2
    let corner = min(CGFloat(radius), limit)
    return CGPath(roundedRect: r, cornerWidth: corner, cornerHeight: corner, transform: nil)
}

func drawPhone(_ item: Item, in ctx: CGContext, canvasHeight: Double) throws {
    guard let capturePath = item.capture, let outer = item.outer_radius,
        let inner = item.screen_radius, let bodyHex = item.body_color,
        let rimHex = item.rim_color
    else { throw PaintError(description: "a phone item lacks a field") }
    let body = try rect(item.body, canvasHeight: canvasHeight)
    let screen = try rect(item.screen, canvasHeight: canvasHeight)
    let bodyPath = roundedPath(body, radius: outer)
    if let shadow = item.shadow {
        ctx.saveGState()
        ctx.setShadow(
            offset: CGSize(width: 0, height: -shadow.offset_y), blur: CGFloat(shadow.blur),
            color: try colour(shadow.color, alpha: shadow.opacity))
        ctx.addPath(bodyPath)
        ctx.setFillColor(try colour(bodyHex))
        ctx.fillPath()
        ctx.restoreGState()
    }
    ctx.addPath(bodyPath)
    ctx.setFillColor(try colour(bodyHex))
    ctx.fillPath()
    let rimWidth = item.rim_width ?? 2
    let rimRect = body.insetBy(dx: rimWidth / 2, dy: rimWidth / 2)
    ctx.addPath(roundedPath(rimRect, radius: outer - rimWidth / 2))
    ctx.setStrokeColor(try colour(rimHex))
    ctx.setLineWidth(CGFloat(rimWidth))
    ctx.strokePath()
    ctx.saveGState()
    ctx.addPath(roundedPath(screen, radius: inner))
    ctx.clip()
    ctx.interpolationQuality = .high
    ctx.draw(try loadImage(capturePath), in: screen)
    ctx.restoreGState()
}

func paint(_ plan: Plan) throws {
    guard let space = CGColorSpace(name: CGColorSpace.sRGB),
        let ctx = CGContext(
            data: nil, width: plan.width, height: plan.height, bitsPerComponent: 8,
            bytesPerRow: 0, space: space, bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue)
    else { throw PaintError(description: "\(plan.out): no bitmap context") }
    ctx.setShouldSmoothFonts(false)
    ctx.setFillColor(try colour(plan.ground))
    ctx.fill(CGRect(x: 0, y: 0, width: plan.width, height: plan.height))
    let height = Double(plan.height)
    for item in plan.items {
        switch item.kind {
        case "text": try drawText(item, in: ctx, canvasHeight: height)
        case "phone": try drawPhone(item, in: ctx, canvasHeight: height)
        default: throw PaintError(description: "unknown item kind \(item.kind)")
        }
    }
    guard let image = ctx.makeImage() else { throw PaintError(description: "\(plan.out): no image") }
    let url = URL(fileURLWithPath: plan.out)
    try FileManager.default.createDirectory(
        at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
    guard
        let destination = CGImageDestinationCreateWithURL(
            url as CFURL, UTType.png.identifier as CFString, 1, nil)
    else { throw PaintError(description: "\(plan.out): cannot write") }
    CGImageDestinationAddImage(destination, image, nil)
    guard CGImageDestinationFinalize(destination) else {
        throw PaintError(description: "\(plan.out): PNG not written")
    }
}

let arguments = CommandLine.arguments
guard arguments.count == 2 else {
    FileHandle.standardError.write("usage: paint <plans.json>\n".data(using: .utf8)!)
    exit(2)
}
do {
    let data = try Data(contentsOf: URL(fileURLWithPath: arguments[1]))
    let plans = try JSONDecoder().decode(Plans.self, from: data)
    for plan in plans.jobs {
        try paint(plan)
        print("painted \(plan.out)")
    }
} catch {
    FileHandle.standardError.write("paint: \(error)\n".data(using: .utf8)!)
    exit(1)
}
