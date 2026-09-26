// callwatch: reports which call apps are using the microphone, and where
// their main window is. Prints one JSON line to stdout whenever that changes.
//
// It never opens the microphone or reads any audio. It only asks Core Audio
// which processes are currently running audio input (macOS 14.2+), and asks
// the window server for the on-screen bounds of the matching app's windows.
// Neither call needs the Microphone or Screen Recording permission.
//
// Output: {"active":bool,"app":str|null,"bundle":str|null,
//          "bounds":{"x":n,"y":n,"width":n,"height":n}|null}
// Coordinates are global points with the origin at the top-left of the main
// display, which matches Electron's screen coordinates on macOS.

import CoreAudio
import CoreGraphics
import Foundation

struct CallApp {
    let name: String            // shown in the UI
    let bundlePrefixes: [String] // matched against the audio process's bundle ID
    let windowOwners: [String]  // kCGWindowOwnerName of the app that owns the call window
}

// Browsers count as a call only while they hold the mic (Meet, Teams web, etc.).
let callApps: [CallApp] = [
    CallApp(name: "Zoom", bundlePrefixes: ["us.zoom."], windowOwners: ["zoom.us"]),
    CallApp(name: "FaceTime", bundlePrefixes: ["com.apple.FaceTime", "com.apple.avconferenced"], windowOwners: ["FaceTime"]),
    CallApp(name: "Microsoft Teams", bundlePrefixes: ["com.microsoft.teams"], windowOwners: ["Microsoft Teams", "Microsoft Teams (work or school)"]),
    CallApp(name: "Discord", bundlePrefixes: ["com.hnc.Discord"], windowOwners: ["Discord"]),
    CallApp(name: "Slack", bundlePrefixes: ["com.tinyspeck.slackmacgap"], windowOwners: ["Slack"]),
    CallApp(name: "Google Chrome", bundlePrefixes: ["com.google.Chrome"], windowOwners: ["Google Chrome"]),
    CallApp(name: "Arc", bundlePrefixes: ["company.thebrowser."], windowOwners: ["Arc"]),
    CallApp(name: "Safari", bundlePrefixes: ["com.apple.Safari", "com.apple.WebKit"], windowOwners: ["Safari"]),
    CallApp(name: "Firefox", bundlePrefixes: ["org.mozilla.firefox"], windowOwners: ["Firefox"]),
    CallApp(name: "Microsoft Edge", bundlePrefixes: ["com.microsoft.edgemac"], windowOwners: ["Microsoft Edge"]),
]

func address(_ selector: AudioObjectPropertySelector) -> AudioObjectPropertyAddress {
    AudioObjectPropertyAddress(
        mSelector: selector,
        mScope: kAudioObjectPropertyScopeGlobal,
        mElement: kAudioObjectPropertyElementMain)
}

/// Bundle IDs of every process that is currently running audio input.
func processesUsingMic() -> [String] {
    var addr = address(kAudioHardwarePropertyProcessObjectList)
    var size: UInt32 = 0
    guard AudioObjectGetPropertyDataSize(AudioObjectID(kAudioObjectSystemObject), &addr, 0, nil, &size) == noErr,
          size > 0 else { return [] }
    var ids = [AudioObjectID](repeating: 0, count: Int(size) / MemoryLayout<AudioObjectID>.size)
    guard AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &addr, 0, nil, &size, &ids) == noErr
    else { return [] }

    var bundles: [String] = []
    for id in ids {
        var running: UInt32 = 0
        var runningSize = UInt32(MemoryLayout<UInt32>.size)
        var runningAddr = address(kAudioProcessPropertyIsRunningInput)
        guard AudioObjectGetPropertyData(id, &runningAddr, 0, nil, &runningSize, &running) == noErr,
              running != 0 else { continue }

        var bundle: Unmanaged<CFString>?
        var bundleSize = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)
        var bundleAddr = address(kAudioProcessPropertyBundleID)
        if AudioObjectGetPropertyData(id, &bundleAddr, 0, nil, &bundleSize, &bundle) == noErr,
           let b = bundle?.takeRetainedValue() {
            bundles.append(b as String)
        }
    }
    return bundles
}

/// Largest normal on-screen window owned by one of `owners`.
func mainWindowBounds(owners: [String]) -> CGRect? {
    guard let list = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID)
            as? [[String: Any]] else { return nil }
    var best: CGRect?
    for w in list {
        guard let owner = w[kCGWindowOwnerName as String] as? String, owners.contains(owner),
              (w[kCGWindowLayer as String] as? Int) == 0,
              let dict = w[kCGWindowBounds as String] as? NSDictionary,
              let rect = CGRect(dictionaryRepresentation: dict),
              rect.width >= 200, rect.height >= 150 else { continue }
        if best == nil || rect.width * rect.height > best!.width * best!.height { best = rect }
    }
    return best
}

func snapshot() -> [String: Any] {
    let mic = processesUsingMic()
    for app in callApps where mic.contains(where: { b in app.bundlePrefixes.contains { b.hasPrefix($0) } }) {
        let matched = mic.first { b in app.bundlePrefixes.contains { b.hasPrefix($0) } } ?? ""
        var out: [String: Any] = ["active": true, "app": app.name, "bundle": matched, "bounds": NSNull()]
        if let r = mainWindowBounds(owners: app.windowOwners) {
            out["bounds"] = ["x": Int(r.minX), "y": Int(r.minY), "width": Int(r.width), "height": Int(r.height)]
        }
        return out
    }
    return ["active": false, "app": NSNull(), "bundle": NSNull(), "bounds": NSNull()]
}

setvbuf(stdout, nil, _IOLBF, 0)
var last = ""
while true {
    let snap = snapshot()
    if let data = try? JSONSerialization.data(withJSONObject: snap, options: [.sortedKeys]),
       let line = String(data: data, encoding: .utf8), line != last {
        print(line)
        last = line
    }
    // Poll fast during a call so the highlight keeps up when the window is dragged.
    Thread.sleep(forTimeInterval: (snap["active"] as? Bool) == true ? 0.08 : 0.5)
}
