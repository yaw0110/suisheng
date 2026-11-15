// 生成 App 图标：swift app/icon/make_icon.swift <输出.png> <风格 ink|paper>
// 设计：一支斜放的羽毛笔，笔尖流出一道由粗到细的波浪墨迹（声音化成文字）。
import AppKit

let args = CommandLine.arguments
let out = args.count > 1 ? args[1] : "icon_1024.png"
let style = args.count > 2 ? args[2] : "paper"
let S: CGFloat = 1024

func rgb(_ h: UInt32, _ a: CGFloat = 1) -> CGColor {
    CGColor(red: CGFloat((h >> 16) & 0xff) / 255, green: CGFloat((h >> 8) & 0xff) / 255, blue: CGFloat(h & 0xff) / 255, alpha: a)
}
let P: (bg0: CGColor, bg1: CGColor, glow: CGColor, q0: CGColor, q1: CGColor, shaft: CGColor, ink0: CGColor, ink1: CGColor) =
    style == "paper"
    ? (rgb(0xFBF8F1), rgb(0xECE4D3), rgb(0xFFFFFF, 0.5), rgb(0x2B3A8C), rgb(0x5163DA), rgb(0xFBF8F1, 0.85), rgb(0x3A47B8), rgb(0x22B3A6))
    : (rgb(0x1F2B4D), rgb(0x0B1020), rgb(0x5B7CFF, 0.22), rgb(0xFFFFFF), rgb(0xC9D4F2), rgb(0x1A2442, 0.75), rgb(0xFFD36B), rgb(0xFF8A4C))

let cs = CGColorSpaceCreateDeviceRGB()
let ctx = CGContext(data: nil, width: Int(S), height: Int(S), bitsPerComponent: 8, bytesPerRow: 0, space: cs,
                    bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!

// ---- 底：圆角方块（Apple 图标网格 824/1024）+ 阴影 + 渐变 + 柔光 ----
let body = CGRect(x: 100, y: 100, width: 824, height: 824), R: CGFloat = 185
let bodyPath = CGPath(roundedRect: body, cornerWidth: R, cornerHeight: R, transform: nil)
ctx.saveGState()
ctx.setShadow(offset: CGSize(width: 0, height: -10), blur: 26, color: rgb(0x000000, 0.30))
ctx.addPath(bodyPath); ctx.setFillColor(P.bg1); ctx.fillPath()
ctx.restoreGState()
ctx.saveGState(); ctx.addPath(bodyPath); ctx.clip()
ctx.drawLinearGradient(CGGradient(colorsSpace: cs, colors: [P.bg0, P.bg1] as CFArray, locations: [0, 1])!,
                       start: CGPoint(x: 0, y: body.maxY), end: CGPoint(x: 0, y: body.minY), options: [])
ctx.drawRadialGradient(CGGradient(colorsSpace: cs, colors: [P.glow, P.glow.copy(alpha: 0)!] as CFArray, locations: [0, 1])!,
                       startCenter: CGPoint(x: 600, y: 640), startRadius: 0, endCenter: CGPoint(x: 600, y: 640), endRadius: 420, options: [])
ctx.restoreGState()

// ---- 墨迹：从笔尖流出的波浪，由粗到细 ----
let nib = CGPoint(x: 318, y: 352)
func bez(_ p0: CGPoint, _ c1: CGPoint, _ c2: CGPoint, _ p1: CGPoint, _ t: CGFloat) -> CGPoint {
    let u = 1 - t
    return CGPoint(x: u*u*u*p0.x + 3*u*u*t*c1.x + 3*u*t*t*c2.x + t*t*t*p1.x,
                   y: u*u*u*p0.y + 3*u*u*t*c1.y + 3*u*t*t*c2.y + t*t*t*p1.y)
}
let segs: [(CGPoint, CGPoint, CGPoint, CGPoint)] = [
    (nib, CGPoint(x: 360, y: 250), CGPoint(x: 470, y: 238), CGPoint(x: 540, y: 300)),
    (CGPoint(x: 540, y: 300), CGPoint(x: 600, y: 352), CGPoint(x: 680, y: 345), CGPoint(x: 730, y: 290)),
    (CGPoint(x: 730, y: 290), CGPoint(x: 765, y: 252), CGPoint(x: 805, y: 252), CGPoint(x: 838, y: 278)),
]
var pts: [CGPoint] = []
for (i, s) in segs.enumerated() { for k in 0...40 where !(i > 0 && k == 0) { pts.append(bez(s.0, s.1, s.2, s.3, CGFloat(k) / 40)) } }
var left: [CGPoint] = [], right: [CGPoint] = []
for i in 0..<pts.count {
    let a = pts[max(i - 1, 0)], b = pts[min(i + 1, pts.count - 1)]
    var nx = -(b.y - a.y), ny = b.x - a.x; let l = max(hypot(nx, ny), 0.001); nx /= l; ny /= l
    let t = CGFloat(i) / CGFloat(pts.count - 1)
    let w = 4 + 20 * pow(1 - t, 1.3) * (0.75 + 0.25 * sin(t * .pi * 3))   // 由粗到细，略带笔锋起伏
    left.append(CGPoint(x: pts[i].x + nx * w, y: pts[i].y + ny * w))
    right.append(CGPoint(x: pts[i].x - nx * w, y: pts[i].y - ny * w))
}
let inkPath = CGMutablePath(); inkPath.addLines(between: left + right.reversed()); inkPath.closeSubpath()
ctx.saveGState(); ctx.addPath(inkPath); ctx.clip()
ctx.drawLinearGradient(CGGradient(colorsSpace: cs, colors: [P.ink0, P.ink1] as CFArray, locations: [0, 1])!,
                       start: CGPoint(x: 300, y: 0), end: CGPoint(x: 850, y: 0), options: [])
ctx.restoreGState()
// 墨点（笔尖刚落下的那一滴）
ctx.addEllipse(in: CGRect(x: nib.x - 15, y: nib.y - 15, width: 30, height: 30)); ctx.setFillColor(P.ink0); ctx.fillPath()

// ---- 羽毛笔：局部坐标 y 轴沿笔杆，笔尖在原点；整体向右上倾斜 ----
let L: CGFloat = 610
ctx.saveGState()
ctx.translateBy(x: nib.x, y: nib.y)
ctx.rotate(by: -38 * .pi / 180)
ctx.setShadow(offset: CGSize(width: 6, height: -10), blur: 22, color: rgb(0x000000, style == "paper" ? 0.18 : 0.45))
ctx.beginTransparencyLayer(auxiliaryInfo: nil)
// 羽片：左宽右窄、略带弧度
let vane = CGMutablePath()
vane.move(to: CGPoint(x: -3, y: 0.20 * L))
vane.addCurve(to: CGPoint(x: 0.03 * L, y: L), control1: CGPoint(x: -0.20 * L, y: 0.42 * L), control2: CGPoint(x: -0.17 * L, y: 0.86 * L))
vane.addCurve(to: CGPoint(x: 4, y: 0.23 * L), control1: CGPoint(x: 0.14 * L, y: 0.80 * L), control2: CGPoint(x: 0.13 * L, y: 0.42 * L))
vane.closeSubpath()
// 笔头：细长尖
let nibPath = CGMutablePath()
nibPath.move(to: .zero)
nibPath.addQuadCurve(to: CGPoint(x: -11, y: 0.215 * L), control: CGPoint(x: -12, y: 0.07 * L))
nibPath.addLine(to: CGPoint(x: 11, y: 0.225 * L))
nibPath.addQuadCurve(to: .zero, control: CGPoint(x: 10, y: 0.07 * L))
for p in [vane, nibPath] {
    ctx.saveGState(); ctx.addPath(p); ctx.clip()
    ctx.drawLinearGradient(CGGradient(colorsSpace: cs, colors: [P.q1, P.q0] as CFArray, locations: [0, 1])!,
                           start: CGPoint(x: 0, y: 0), end: CGPoint(x: 0, y: L), options: [])
    ctx.restoreGState()
}
// 羽片上的两道缺口（羽毛的质感），用 clear 在这一层里挖掉
ctx.setBlendMode(.clear)
for (y, side) in [(0.50, -1.0), (0.70, -1.0), (0.60, 1.0)] as [(CGFloat, CGFloat)] {
    let c = CGMutablePath()
    let edgeX = side < 0 ? -0.19 * L : 0.14 * L
    c.move(to: CGPoint(x: edgeX * 1.3, y: (y + 0.02) * L))
    c.addLine(to: CGPoint(x: edgeX * 0.42, y: (y - 0.035) * L))
    c.addLine(to: CGPoint(x: edgeX * 1.3, y: (y - 0.01) * L))
    c.closeSubpath(); ctx.addPath(c); ctx.fillPath()
}
// 笔头开缝
ctx.setLineWidth(3); ctx.move(to: CGPoint(x: 0, y: 0.03 * L)); ctx.addLine(to: CGPoint(x: 0, y: 0.15 * L)); ctx.strokePath()
ctx.setBlendMode(.normal)
// 羽轴（中线）
let shaft = CGMutablePath()
shaft.move(to: CGPoint(x: 0, y: 0.215 * L))
shaft.addQuadCurve(to: CGPoint(x: 0.025 * L, y: 0.97 * L), control: CGPoint(x: -0.03 * L, y: 0.62 * L))
ctx.addPath(shaft); ctx.setStrokeColor(P.shaft); ctx.setLineWidth(7); ctx.setLineCap(.round); ctx.strokePath()
ctx.endTransparencyLayer()
ctx.restoreGState()

let rep = NSBitmapImageRep(cgImage: ctx.makeImage()!)
try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: out))
print("写入 \(out)")
