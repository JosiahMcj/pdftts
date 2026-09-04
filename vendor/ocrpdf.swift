// OCR a PDF or an image with Apple's Vision framework.
//   swift ocrpdf.swift IN.pdf   > out.txt
//   swift ocrpdf.swift page.jpg > out.txt
//
// Pages come out blank-line separated, in reading order. An image is treated as
// a single page, which is what a photograph of a page is.
import Foundation
import PDFKit
import Vision

let args = CommandLine.arguments
guard args.count > 1 else {
    FileHandle.standardError.write("usage: ocrpdf.swift FILE.pdf|FILE.png\n".data(using: .utf8)!)
    exit(1)
}
let url = URL(fileURLWithPath: args[1])

/// Vision is markedly more accurate on a larger raster, so pages are upsampled.
let scale: CGFloat = 3.0

func read(_ cg: CGImage) -> [String] {
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.usesLanguageCorrection = true
    req.revision = VNRecognizeTextRequestRevision3
    try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
    return (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
}

func emit(_ lines: [String], _ label: String) {
    FileHandle.standardError.write("\(label): \(lines.count) lines\n".data(using: .utf8)!)
    print(lines.joined(separator: "\n"))
    print("")
}

if let doc = PDFDocument(url: url) {
    for i in 0..<doc.pageCount {
        guard let page = doc.page(at: i) else { continue }
        let bounds = page.bounds(for: .mediaBox)
        let size = CGSize(width: bounds.width * scale, height: bounds.height * scale)
        let img = NSImage(size: size, flipped: false) { rect in
            guard let ctx = NSGraphicsContext.current?.cgContext else { return false }
            ctx.setFillColor(.white); ctx.fill(rect)
            ctx.scaleBy(x: scale, y: scale)
            ctx.translateBy(x: -bounds.origin.x, y: -bounds.origin.y)
            page.draw(with: .mediaBox, to: ctx)
            return true
        }
        guard let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { continue }
        emit(read(cg), "page \(i + 1)/\(doc.pageCount)")
    }
} else if let img = NSImage(contentsOf: url) {
    // Flatten onto white first. A PNG screenshot usually carries an alpha
    // channel, and Vision reads dark text on transparency as nothing at all —
    // the file looks fine to a human and OCRs to zero lines.
    let size = img.size
    guard size.width > 0, size.height > 0 else {
        FileHandle.standardError.write("empty image\n".data(using: .utf8)!)
        exit(1)
    }
    let flat = NSImage(size: size, flipped: false) { rect in
        guard let ctx = NSGraphicsContext.current?.cgContext else { return false }
        ctx.setFillColor(.white)
        ctx.fill(rect)
        img.draw(in: rect)
        return true
    }
    guard let cg = flat.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        FileHandle.standardError.write("cannot rasterise \(url.lastPathComponent)\n"
            .data(using: .utf8)!)
        exit(1)
    }
    // A photograph arrives at camera resolution already; upsampling it further
    // buys nothing and costs seconds, so the raster is used as it is.
    emit(read(cg), "image")
} else {
    FileHandle.standardError.write("cannot read \(url.lastPathComponent) as a PDF or an image\n"
        .data(using: .utf8)!)
    exit(1)
}
