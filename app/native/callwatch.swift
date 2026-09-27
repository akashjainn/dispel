// callwatch: reports which call apps are using the microphone, and where
// their main window is. Prints one JSON line to stdout whenever that changes.
//
// It never opens the microphone or reads any audio. It only asks Core Audio
// which processes are currently running audio input (macOS 14.2+), and asks
// the window server for the on-screen bounds of the matching app's windows.
// Neither call needs the Microphone or Screen Recording permission.
//
// Output: {"active":bool,"app":str|null,"bundle":str|null,"prefixes":[str],"canEnd":bool,"front":bool,
//          "bounds":{"x":n,"y":n,"width":n,"height":n}|null}
// prefixes: the app's bundle-ID prefixes, which callcapture uses to tap its audio.
// front: the call app owns the frontmost normal window (our own windows and
// dialogs, owned by the parent Electron process, are skipped).
//
// Input (one command per line on stdin):
//   end [name]  politely quits the call app (like Cmd+Q), which hangs up.
//         name is the "app" this helper reported (e.g. "Discord"); without it,
//         the app using the mic right now. The name matters: apps like
//         Discord let go of the mic for moments mid-call, and the app shouldn't
//         get a pass for that. Only apps in callApps with quitBundles can be quit.
//         If the app refuses, or is still running 2.5 s later, it gets
//         SIGTERM (what a normal quit sends; Electron apps close cleanly).
//   focus [name]  brings the call app to the front (the hang-up spell is aimed
//         at its window, which may be behind others).
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
    // Demo: demo/call-sim's fake phone call (it holds the mic while "connected").
    CallApp(name: "Call Simulator", bundlePrefixes: ["tech.hocuspocus.callsim"], windowOwners: ["Call Simulator"],
            quitBundles: ["tech.hocuspocus.callsim"]),
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

/// Owner name of the frontmost normal (layer 0) window, skipping our parent
/// (the Electron app), so clicking the wizard doesn't count as leaving the call.
func frontmostOwner() -> String? {
    guard let list = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID)
            as? [[String: Any]] else { return nil }
    let me = getppid()
    for w in list { // front to back
        guard (w[kCGWindowLayer as String] as? Int) == 0,
              (w[kCGWindowOwnerPID as String] as? Int32) != me,
              let dict = w[kCGWindowBounds as String] as? NSDictionary,
              let rect = CGRect(dictionaryRepresentation: dict),
              rect.width >= 50, rect.height >= 50 else { continue }
        return w[kCGWindowOwnerName as String] as? String
    }
    return nil
}

func snapshot() -> [String: Any] {
    guard let (app, bundle) = currentCall() else {
        return ["active": false, "app": NSNull(), "bundle": NSNull(), "prefixes": [String](), "canEnd": false, "front": false,
                "bounds": NSNull()]
    }
    let front = frontmostOwner().map { app.windowOwners.contains($0) } ?? false
    var out: [String: Any] = ["active": true, "app": app.name, "bundle": bundle, "prefixes": app.bundlePrefixes,
                              "canEnd": !app.quitBundles.isEmpty, "front": front, "bounds": NSNull()]
    if let r = mainWindowBounds(owners: app.windowOwners) {
        out["bounds"] = ["x": Int(r.minX), "y": Int(r.minY), "width": Int(r.width), "height": Int(r.height)]
    }
    return out
}

func log(_ msg: String) {
    FileHandle.standardError.write(("[callwatch] " + msg + "\n").data(using: .utf8)!)
}

/// The call app's own running app(s) (not its helper processes), for a name
/// this helper reported, or the app using the mic.
func quittableApps(named name: String?) -> (CallApp, [NSRunningApplication])? {
    guard let app = callApps.first(where: { $0.name == name }) ?? currentCall()?.0,
          !app.quitBundles.isEmpty else { return nil }
    let running = NSWorkspace.shared.runningApplications.filter { r in
        let id = r.bundleIdentifier ?? ""
        return !r.isTerminated && r.activationPolicy == .regular && app.quitBundles.contains(where: { id.hasPrefix($0) })
    }
    return (app, running)
}

/// Quits the named call app (or the one using the mic): politely first, then
/// SIGTERM if it refuses or is still up 2.5 s later. Returns false if there's
/// nothing we may quit.
func endCall(named name: String?) -> Bool {
    guard let (app, running) = quittableApps(named: name), !running.isEmpty else {
        log("end \(name ?? "-"): nothing to quit")
        return false
    }
    var ok = false
    for r in running {
        let polite = r.terminate()
        log("end \(app.name): \(r.bundleIdentifier ?? "?") pid \(r.processIdentifier) terminate -> \(polite)")
        var sent = polite
        if !polite {
            sent = kill(r.processIdentifier, SIGTERM) == 0
            log("end \(app.name): SIGTERM -> \(sent)")
        }
        ok = ok || sent
        let pid = r.processIdentifier
        Thread {
            Thread.sleep(forTimeInterval: 2.5)
            if kill(pid, 0) == 0 { log("end \(app.name): still running, SIGTERM -> \(kill(pid, SIGTERM) == 0)") }
        }.start()
    }
    return ok // false if nothing could even be asked to quit
}

/// Brings the named call app to the front.
func focusCall(named name: String?) {
    guard let (app, running) = quittableApps(named: name) else { return }
    for r in running { log("focus \(app.name): activate -> \(r.activate(options: [.activateAllWindows]))") }
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
        let cmd = line.trimmingCharacters(in: .whitespaces)
        if cmd == "end" || cmd.hasPrefix("end ") {
            let name = cmd.dropFirst(3).trimmingCharacters(in: .whitespaces)
            _ = emit(["event": "end", "ok": endCall(named: name.isEmpty ? nil : name)])
        } else if cmd == "focus" || cmd.hasPrefix("focus ") {
            let name = cmd.dropFirst(5).trimmingCharacters(in: .whitespaces)
            focusCall(named: name.isEmpty ? nil : name)
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
    // Wait by running the main run loop, not sleeping: NSWorkspace only updates
    // runningApplications while it runs, so a sleeping helper keeps a frozen
    // list and tries to quit an app that has since quit and been reopened.
    RunLoop.main.run(until: Date().addingTimeInterval((snap["active"] as? Bool) == true ? 0.08 : 0.5))
}
