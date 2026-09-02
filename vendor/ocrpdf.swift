// OCR a PDF with Apple's Vision framework. Usage: swift ocrpdf.swift IN.pdf > out.txt
import Foundation
import PDFKit
import Vision

let args = CommandLine.arguments
guard args.count > 1, let doc = PDFDocument(url: URL(fileURLWithPath: args[1])) else {
    FileHandle.standardError.write("usage: ocrpdf.swift FILE.pdf\n".data(using: .utf8)!)
    exit(1)
}

let scale: CGFloat = 3.0  // upsample; Vision is much more accurate on larger rasters

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

    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.usesLanguageCorrection = true
    req.revision = VNRecognizeTextRequestRevision3
    try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])

    let lines = (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    FileHandle.standardError.write("page \(i+1)/\(doc.pageCount): \(lines.count) lines\n".data(using: .utf8)!)
    print(lines.joined(separator: "\n"))
    print("")
}
