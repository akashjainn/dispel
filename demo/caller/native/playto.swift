// playto: plays an audio file into a named output device (e.g. "BlackHole 2ch",
// which a call app uses as its microphone), then exits.
//
// Usage: playto --device "BlackHole 2ch" [--monitor] file.wav
//   --monitor  also play it on the default speakers so the operator hears it
// Prints {"ok":true,"duration":n} when playback starts and {"done":true} at the
// end, or {"ok":false,"error":str,"devices":[str]} if the device isn't there.

import AVFoundation
import CoreAudio
import Foundation

func emit(_ obj: [String: Any]) {
    let data = try! JSONSerialization.data(withJSONObject: obj, options: [.sortedKeys])
    print(String(data: data, encoding: .utf8)!)
    fflush(stdout)
}

var deviceName = ""
var monitor = false
var file = ""
var args = CommandLine.arguments.dropFirst().makeIterator()
while let a = args.next() {
    switch a {
    case "--device": deviceName = args.next() ?? ""
    case "--monitor": monitor = true
    default: file = a
    }
}

func outputDevices() -> [(AudioDeviceID, String)] {
    var addr = AudioObjectPropertyAddress(mSelector: kAudioHardwarePropertyDevices,
                                          mScope: kAudioObjectPropertyScopeGlobal,
                                          mElement: kAudioObjectPropertyElementMain)
    var size: UInt32 = 0
    let sys = AudioObjectID(kAudioObjectSystemObject)
    guard AudioObjectGetPropertyDataSize(sys, &addr, 0, nil, &size) == noErr else { return [] }
    var ids = [AudioDeviceID](repeating: 0, count: Int(size) / MemoryLayout<AudioDeviceID>.size)
    guard AudioObjectGetPropertyData(sys, &addr, 0, nil, &size, &ids) == noErr else { return [] }
    return ids.compactMap { id in
        var streams = AudioObjectPropertyAddress(mSelector: kAudioDevicePropertyStreams,
                                                 mScope: kAudioObjectPropertyScopeOutput,
                                                 mElement: kAudioObjectPropertyElementMain)
        var n: UInt32 = 0
        guard AudioObjectGetPropertyDataSize(id, &streams, 0, nil, &n) == noErr, n > 0 else { return nil }
        var nameAddr = AudioObjectPropertyAddress(mSelector: kAudioObjectPropertyName,
                                                  mScope: kAudioObjectPropertyScopeGlobal,
                                                  mElement: kAudioObjectPropertyElementMain)
        var name: Unmanaged<CFString>?
        var nameSize = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)
        guard AudioObjectGetPropertyData(id, &nameAddr, 0, nil, &nameSize, &name) == noErr,
              let s = name?.takeRetainedValue() else { return nil }
        return (id, s as String)
    }
}

let devices = outputDevices()
guard let target = devices.first(where: { $0.1 == deviceName }) else {
    emit(["ok": false, "error": "no output device named \(deviceName)", "devices": devices.map { $0.1 }])
    exit(1)
}
guard let audio = try? AVAudioFile(forReading: URL(fileURLWithPath: file)) else {
    emit(["ok": false, "error": "can't read \(file)", "devices": []])
    exit(1)
}

/// One engine per output device, each playing the whole file.
func makeEngine(device: AudioDeviceID?, done: @escaping () -> Void) throws -> (AVAudioEngine, AVAudioPlayerNode) {
    let engine = AVAudioEngine()
    if var dev = device, let au = engine.outputNode.audioUnit {
        let st = AudioUnitSetProperty(au, kAudioOutputUnitProperty_CurrentDevice, kAudioUnitScope_Global, 0,
                                      &dev, UInt32(MemoryLayout<AudioDeviceID>.size))
        if st != noErr { throw NSError(domain: "playto", code: Int(st)) }
    }
    let player = AVAudioPlayerNode()
    let own = try AVAudioFile(forReading: audio.url) // each engine reads its own copy
    engine.attach(player)
    engine.connect(player, to: engine.mainMixerNode, format: own.processingFormat)
    player.scheduleFile(own, at: nil, completionCallbackType: .dataPlayedBack) { _ in done() }
    try engine.start()
    return (engine, player)
}

let finished = DispatchSemaphore(value: 0)
var engines: [(AVAudioEngine, AVAudioPlayerNode)] = []
do {
    engines.append(try makeEngine(device: target.0) { finished.signal() })
    if monitor { engines.append(try makeEngine(device: nil) {}) }
} catch {
    emit(["ok": false, "error": "could not open \(deviceName): \(error)", "devices": []])
    exit(1)
}
engines.forEach { $0.1.play() }
emit(["ok": true, "duration": Double(audio.length) / audio.processingFormat.sampleRate])
finished.wait()
emit(["done": true])
