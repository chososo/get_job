import Foundation
import Vision
import ImageIO
let url = URL(fileURLWithPath: CommandLine.arguments[1])
let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.recognitionLanguages = ["ko-KR", "en-US"]
request.usesLanguageCorrection = true
try VNImageRequestHandler(url: url).perform([request])
for observation in request.results ?? [] {
    if let text = observation.topCandidates(1).first?.string { print(text) }
}
