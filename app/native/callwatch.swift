// callwatch: reports which call apps are using the microphone, and where
// their main window is. Prints one JSON line to stdout whenever that changes.
//
// It never opens the microphone or reads any audio. It only asks Core Audio
// which processes are currently running audio input (macOS 14.2+), and asks
// the window server for the on-screen bounds of the matching app's windows.
// Neither call needs the Microphone or Screen Recording permission.
//
// Output: {"active":bool,"app":str|null,"bundle":str|null,"canEnd":bool,
//          "bounds":{"x":n,"y":n,"width":n,"height":n}|null}
//
// Input (one command per line on stdin):
//   end   politely quits the current call app (like Cmd+Q), which hangs up.
//         Replies {"event":"end","ok":bool}. Browsers are never quit, since
//         that would close every tab; for them canEnd is false.
// Coordinates are global points with the origin at the top-left of the main
// display, which matches Electron's screen coordinates on macOS.

import AppKit
import CoreAudio
import CoreGraphics
import Foundation

struct CallApp {
    let name: String            // shown in the UI
    let bundlePrefixes: [String] // matched against the audio process's bundle ID
    let windowOwners: [String]  // kCGWindowOwnerName of the app that owns the call window
    var quitBundles: [String] = [] // apps to quit to end the call; empty = can't end it
}

// Browsers count as a call only while they hold the mic (Meet, Teams web, etc.).
let callApps: [CallApp] = [
    CallApp(name: "Zoom", bundlePrefixes: ["us.zoom."], windowOwners: ["zoom.us"], quitBundles: ["us.zoom.xos"]),
    // FaceTime's audio runs in a system daemon; quit the FaceTime app, never the daemon.
    CallApp(name: "FaceTime", bundlePrefixes: ["com.apple.FaceTime", "com.apple.avconferenced"], windowOwners: ["FaceTime"],
            quitBundles: ["com.apple.FaceTime"]),
    CallApp(name: "Microsoft Teams", bundlePrefixes: ["com.microsoft.teams"], windowOwners: ["Microsoft Teams", "Microsoft Teams (work or school)"],
            quitBundles: ["com.microsoft.teams"]),
    CallApp(name: "Discord", bundlePrefixes: ["com.hnc.Discord"], windowOwners: ["Discord"], quitBundles: ["com.hnc.Discord"]),
    CallApp(name: "Slack", bundlePrefixes: ["com.tinyspeck.slackmacgap"], windowOwners: ["Slack"], quitBundles: ["com.tinyspeck.slackmacgap"]),
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

func matches(_ app: CallApp, _ bundle: String) -> Bool {
    app.bundlePrefixes.contains { bundle.hasPrefix($0) }
}

/// The first call app (in list order) that is using the mic, and its audio bundle ID.
func currentCall() -> (CallApp, String)? {
    let mic = processesUsingMic()
    for app in callApps {
        if let b = mic.first(where: { matches(app, $0) }) { return (app, b) }
    }
    return nil
}

func snapshot() -> [String: Any] {
    guard let (app, bundle) = currentCall() else {
        return ["active": false, "app": NSNull(), "bundle": NSNull(), "canEnd": false, "bounds": NSNull()]
    }
    var out: [String: Any] = ["active": true, "app": app.name, "bundle": bundle,
                              "canEnd": !app.quitBundles.isEmpty, "bounds": NSNull()]
    if let r = mainWindowBounds(owners: app.windowOwners) {
        out["bounds"] = ["x": Int(r.minX), "y": Int(r.minY), "width": Int(r.width), "height": Int(r.height)]
    }
    return out
}

/// Politely quits the current call app. Returns false if there's nothing we may quit.
func endCall() -> Bool {
    guard let (app, _) = currentCall(), !app.quitBundles.isEmpty else { return false }
    var ok = false
    for running in NSWorkspace.shared.runningApplications {
        let id = running.bundleIdentifier ?? ""
        if app.quitBundles.contains(where: { id.hasPrefix($0) }) { ok = running.terminate() || ok }
    }
    return ok
}

let output = DispatchQueue(label: "callwatch.output")
func emit(_ obj: [String: Any]) -> String? {
    guard let data = try? JSONSerialization.data(withJSONObject: obj, options: [.sortedKeys]),
          let line = String(data: data, encoding: .utf8) else { return nil }
    output.sync { print(line) }
    return line
}

setvbuf(stdout, nil, _IOLBF, 0)

Thread {
    while let line = readLine() {
        if line.trimmingCharacters(in: .whitespaces) == "end" {
            _ = emit(["event": "end", "ok": endCall()])
        }
    }
    exit(0) // Electron went away
}.start()

var last = ""
while true {
    let snap = snapshot()
    if let data = try? JSONSerialization.data(withJSONObject: snap, options: [.sortedKeys]),
       let line = String(data: data, encoding: .utf8), line != last {
        output.sync { print(line) }
        last = line
    }
    // Poll fast during a call so the highlight keeps up when the window is dragged.
    Thread.sleep(forTimeInterval: (snap["active"] as? Bool) == true ? 0.08 : 0.5)
}
