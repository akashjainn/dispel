// callcapture: records a few seconds of what a call app is playing (the other
// person's voice) into a WAV file, then exits. Run only when the user asks the
// wizard to listen; it never runs in the background.
//
// It uses a Core Audio process tap (macOS 14.2+) on the call app's audio
// output, so it hears the caller but not the user's own microphone. If no
// matching app is playing audio, it taps all system audio instead (except
// Dispel itself) and says so ("scope":"system").
// macOS asks for "System Audio Recording" permission the first time. Without
// it the tap delivers silence, which is reported as "silent":true.
//
// Usage: callcapture --seconds 12 --out /path/clip.wav [--prefix com.microsoft.teams ...]
// Prints one JSON line:
//   {"ok":true,"path":str,"seconds":n,"rate":n,"peak":n,"silent":bool,"scope":"app"|"system"}
//   {"ok":false,"error":str}

import AudioToolbox
import CoreAudio
import Foundation

func fail(_ msg: String) -> Never {
    print(#"{"ok":false,"error":"\#(msg.replacingOccurrences(of: "\"", with: "'"))"}"#)
    exit(1)
}

// ---------- arguments ----------

var seconds = 12.0
var outPath = ""
var prefixes: [String] = []
var args = CommandLine.arguments.dropFirst().makeIterator()
while let a = args.next() {
    switch a {
    case "--seconds": seconds = Double(args.next() ?? "") ?? seconds
    case "--out": outPath = args.next() ?? ""
    case "--prefix": if let p = args.next() { prefixes.append(p) }
    default: fail("unknown argument \(a)")
    }
}
guard !outPath.isEmpty, seconds > 0, seconds <= 30 else { fail("usage: --seconds 1..30 --out file.wav") }

// ---------- Core Audio helpers ----------

func address(_ selector: AudioObjectPropertySelector) -> AudioObjectPropertyAddress {
    AudioObjectPropertyAddress(mSelector: selector, mScope: kAudioObjectPropertyScopeGlobal,
                               mElement: kAudioObjectPropertyElementMain)
}

func getUInt32(_ id: AudioObjectID, _ selector: AudioObjectPropertySelector) -> UInt32? {
    var addr = address(selector)
    var value: UInt32 = 0
    var size = UInt32(MemoryLayout<UInt32>.size)
    return AudioObjectGetPropertyData(id, &addr, 0, nil, &size, &value) == noErr ? value : nil
}

func getString(_ id: AudioObjectID, _ selector: AudioObjectPropertySelector) -> String? {
    var addr = address(selector)
    var value: Unmanaged<CFString>?
    var size = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)
    guard AudioObjectGetPropertyData(id, &addr, 0, nil, &size, &value) == noErr, let v = value else { return nil }
    return v.takeRetainedValue() as String
}

func processObjects() -> [AudioObjectID] {
    var addr = address(kAudioHardwarePropertyProcessObjectList)
    var size: UInt32 = 0
    let sys = AudioObjectID(kAudioObjectSystemObject)
    guard AudioObjectGetPropertyDataSize(sys, &addr, 0, nil, &size) == noErr, size > 0 else { return [] }
    var ids = [AudioObjectID](repeating: 0, count: Int(size) / MemoryLayout<AudioObjectID>.size)
    guard AudioObjectGetPropertyData(sys, &addr, 0, nil, &size, &ids) == noErr else { return [] }
    return ids
}

/// Audio process objects for the call app that are currently playing sound.
func callOutputProcesses() -> [AudioObjectID] {
    guard !prefixes.isEmpty else { return [] }
    return processObjects().filter { id in
        guard getUInt32(id, kAudioProcessPropertyIsRunningOutput) == 1,
              let bundle = getString(id, kAudioProcessPropertyBundleID) else { return false }
        return prefixes.contains { bundle.hasPrefix($0) }
    }
}

/// Our parent (Electron) as an audio process, so a system-wide tap skips it.
func parentProcessObject() -> [AudioObjectID] {
    var addr = address(kAudioHardwarePropertyTranslatePIDToProcessObject)
    var pid = getppid()
    var obj = AudioObjectID(kAudioObjectUnknown)
    var size = UInt32(MemoryLayout<AudioObjectID>.size)
    let st = AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &addr,
                                        UInt32(MemoryLayout<pid_t>.size), &pid, &size, &obj)
    return st == noErr && obj != kAudioObjectUnknown ? [obj] : []
}

// ---------- tap + private aggregate device ----------

let appProcs = callOutputProcesses()
let scope = appProcs.isEmpty ? "system" : "app"
let desc = appProcs.isEmpty
    ? CATapDescription(stereoGlobalTapButExcludeProcesses: parentProcessObject())
    : CATapDescription(stereoMixdownOfProcesses: appProcs)
desc.uuid = UUID()
desc.isPrivate = true
desc.muteBehavior = .unmuted // the user keeps hearing the call

var tapID = AudioObjectID(kAudioObjectUnknown)
var st = AudioHardwareCreateProcessTap(desc, &tapID)
guard st == noErr else { fail("could not create audio tap (\(st)); needs macOS 14.2+") }

var fmt = AudioStreamBasicDescription()
var fmtSize = UInt32(MemoryLayout<AudioStreamBasicDescription>.size)
var fmtAddr = address(kAudioTapPropertyFormat)
st = AudioObjectGetPropertyData(tapID, &fmtAddr, 0, nil, &fmtSize, &fmt)
guard st == noErr, fmt.mFormatID == kAudioFormatLinearPCM, fmt.mFormatFlags & kAudioFormatFlagIsFloat != 0,
      fmt.mBitsPerChannel == 32, fmt.mSampleRate > 0 else {
    AudioHardwareDestroyProcessTap(tapID)
    fail("unexpected tap format")
}
let rate = fmt.mSampleRate
let channels = Int(max(fmt.mChannelsPerFrame, 1))
let nonInterleaved = fmt.mFormatFlags & kAudioFormatFlagIsNonInterleaved != 0

let outputUID: String = {
    var addr = address(kAudioHardwarePropertyDefaultSystemOutputDevice)
    var dev = AudioObjectID(kAudioObjectUnknown)
    var size = UInt32(MemoryLayout<AudioObjectID>.size)
    AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &addr, 0, nil, &size, &dev)
    return getString(dev, kAudioDevicePropertyDeviceUID) ?? ""
}()

let aggDesc: [String: Any] = [
    kAudioAggregateDeviceNameKey: "Dispel call capture",
    kAudioAggregateDeviceUIDKey: UUID().uuidString,
    kAudioAggregateDeviceMainSubDeviceKey: outputUID,
    kAudioAggregateDeviceIsPrivateKey: true,
    kAudioAggregateDeviceIsStackedKey: false,
    kAudioAggregateDeviceTapAutoStartKey: true,
    kAudioAggregateDeviceSubDeviceListKey: [[kAudioSubDeviceUIDKey: outputUID]],
    kAudioAggregateDeviceTapListKey: [[kAudioSubTapDriftCompensationKey: true,
                                        kAudioSubTapUIDKey: desc.uuid.uuidString]],
]
var aggID = AudioObjectID(kAudioObjectUnknown)
st = AudioHardwareCreateAggregateDevice(aggDesc as CFDictionary, &aggID)
guard st == noErr else {
    AudioHardwareDestroyProcessTap(tapID)
    fail("could not create capture device (\(st))")
}

func cleanup() {
    AudioHardwareDestroyAggregateDevice(aggID)
    AudioHardwareDestroyProcessTap(tapID)
}

// ---------- record ----------

let wanted = Int(seconds * rate)
var mono = [Float]()
mono.reserveCapacity(wanted)
let lock = NSLock()
let done = DispatchSemaphore(value: 0)
var finished = false

var procID: AudioDeviceIOProcID?
st = AudioDeviceCreateIOProcIDWithBlock(&procID, aggID, DispatchQueue(label: "callcapture.io")) { _, input, _, _, _ in
    let abl = UnsafeMutableAudioBufferListPointer(UnsafeMutablePointer(mutating: input))
    lock.lock()
    defer { lock.unlock() }
    if finished { return }
    if nonInterleaved {
        let n = Int(abl[0].mDataByteSize) / 4
        for i in 0..<n {
            var sum: Float = 0
            for b in abl { if let p = b.mData?.assumingMemoryBound(to: Float.self) { sum += p[i] } }
            mono.append(sum / Float(abl.count))
        }
    } else if let p = abl[0].mData?.assumingMemoryBound(to: Float.self) {
        let n = Int(abl[0].mDataByteSize) / 4 / channels
        for i in 0..<n {
            var sum: Float = 0
            for c in 0..<channels { sum += p[i * channels + c] }
            mono.append(sum / Float(channels))
        }
    }
    if mono.count >= wanted {
        finished = true
        done.signal()
    }
}
guard st == noErr, let procID else {
    cleanup()
    fail("could not start capture (\(st))")
}
st = AudioDeviceStart(aggID, procID)
guard st == noErr else {
    AudioDeviceDestroyIOProcID(aggID, procID)
    cleanup()
    fail("could not start capture (\(st))")
}

// Give up if the device never delivers audio (e.g. output device went away).
let timedOut = done.wait(timeout: .now() + seconds + 5) == .timedOut
AudioDeviceStop(aggID, procID)
AudioDeviceDestroyIOProcID(aggID, procID)
cleanup()

lock.lock()
let samples = Array(mono.prefix(wanted))
lock.unlock()
if timedOut && samples.count < Int(rate) { fail("no audio arrived from the output device") }

// ---------- write 16-bit mono WAV ----------

let peak = samples.reduce(Float(0)) { max($0, abs($1)) }
var pcm = Data(capacity: samples.count * 2)
for s in samples {
    var v = Int16(max(-1, min(1, s)) * 32767).littleEndian
    withUnsafeBytes(of: &v) { pcm.append(contentsOf: $0) }
}
func le<T: FixedWidthInteger>(_ v: T) -> Data { withUnsafeBytes(of: v.littleEndian) { Data($0) } }
let sr = UInt32(rate)
var wav = Data("RIFF".utf8)
wav += le(UInt32(36 + pcm.count))
wav += Data("WAVEfmt ".utf8)
wav += le(UInt32(16)) + le(UInt16(1)) + le(UInt16(1)) + le(sr) + le(sr * 2) + le(UInt16(2)) + le(UInt16(16))
wav += Data("data".utf8) + le(UInt32(pcm.count)) + pcm
do {
    try wav.write(to: URL(fileURLWithPath: outPath))
} catch {
    fail("could not write \(outPath)")
}

let result: [String: Any] = [
    "ok": true, "path": outPath, "seconds": Double(samples.count) / rate, "rate": Int(rate),
    "peak": Double(peak), "silent": peak < 0.003, "scope": scope,
]
let data = try! JSONSerialization.data(withJSONObject: result, options: [.sortedKeys])
print(String(data: data, encoding: .utf8)!)
