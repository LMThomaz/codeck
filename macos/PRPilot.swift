// PR Pilot para macOS: janela nativa (WebKit) para a tela do backend em Python, com contador no Dock e na
// barra de menus, notificações clicáveis e atualização automática (latest.json no site da ThomSoft).
//
// O app sobe o backend embutido (Resources/backend/server.py) e passa uma chave nova a cada execução: sem ela o
// backend não responde, então nenhum outro programa da máquina consegue ler a fila ou agir por você.
// Desenvolvimento: PR_PILOT_ATTACH=1 + PR_PILOT_PORT=<porta> conecta num backend já rodando (debug no VS Code).
import Cocoa
import ServiceManagement
import UserNotifications
import WebKit

let env = ProcessInfo.processInfo.environment
let attachMode = env["PR_PILOT_ATTACH"] == "1"
let port = Int(env["PR_PILOT_PORT"] ?? "") ?? 47821
let baseURL = URL(string: "http://127.0.0.1:\(port)/")!
let token = attachMode ? (env["PR_PILOT_TOKEN"] ?? "") : UUID().uuidString + UUID().uuidString
let appVersion = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "dev"
let appBuild = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "0"
let updateURL = Bundle.main.object(forInfoDictionaryKey: "PRPilotUpdateURL") as? String ?? ""
let supportDir = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
    .appendingPathComponent("PR Pilot", isDirectory: true)

final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate, WKUIDelegate, WKNavigationDelegate,
    WKScriptMessageHandler, UNUserNotificationCenterDelegate, NSMenuDelegate {
    var window: NSWindow!
    var web: WKWebView!
    var statusItem: NSStatusItem!
    var loginMenuItem: NSMenuItem!
    var server: Process?
    var quitting = false
    var loaded = false
    var lastSeq = -1
    var nativeNotifications = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        buildMainMenu()
        buildWindow()
        buildStatusItem()
        setupNotifications()
        ensureServer { [weak self] in self?.loadUI() }
        Timer.scheduledTimer(withTimeInterval: 15, repeats: true) { [weak self] _ in self?.poll() }
        if !attachMode { enableLoginItemOnFirstRun() }
    }

    // MARK: backend

    func request(_ path: String, method: String = "GET") -> URLRequest {
        var req = URLRequest(url: URL(string: path, relativeTo: baseURL)!)
        req.httpMethod = method
        req.timeoutInterval = 3
        req.setValue(token, forHTTPHeaderField: "X-PR-Pilot-Token")
        if method == "POST" { req.setValue("1", forHTTPHeaderField: "X-PR-Pilot") }
        return req
    }

    func getJSON(_ path: String, _ done: @escaping ([String: Any]?, Int) -> Void) {
        URLSession.shared.dataTask(with: request(path)) { data, resp, _ in
            let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
            let json = data.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] }
            DispatchQueue.main.async { done(json, code) }
        }.resume()
    }

    func pythonPath() -> String? {
        ["/opt/homebrew/bin/python3", "/usr/local/bin/python3", "/usr/bin/python3"].first { FileManager.default.isExecutableFile(atPath: $0) }
    }

    func ensureServer(_ ready: @escaping () -> Void) {
        getJSON("api/summary") { [weak self] _, code in
            guard let self else { return }
            if code == 200 { return ready() }
            if code == 401 || code == 403 {
                return self.showFatal("Outro PR Pilot já está usando a porta \(port). Feche-o (ou o ▶ do editor) e abra de novo.")
            }
            if attachMode { return self.waitForServer(attempts: 240, ready) } // espera o backend do debug subir
            self.startServer()
            self.waitForServer(attempts: 60, ready)
        }
    }

    func waitForServer(attempts: Int, _ ready: @escaping () -> Void) {
        getJSON("api/summary") { [weak self] _, code in
            if code == 200 { return ready() }
            guard attempts > 0 else {
                self?.showFatal("O backend do PR Pilot não respondeu. Log: ~/Library/Application Support/PR Pilot/pr-pilot.log")
                return
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { self?.waitForServer(attempts: attempts - 1, ready) }
        }
    }

    func startServer() {
        guard let script = Bundle.main.path(forResource: "server", ofType: "py", inDirectory: "backend") else {
            return showFatal("O backend não está dentro do app.")
        }
        guard let python = pythonPath() else {
            return showFatal("Python 3 não encontrado. Instale as ferramentas da Apple com: xcode-select --install")
        }
        try? FileManager.default.createDirectory(at: supportDir, withIntermediateDirectories: true)
        let logURL = supportDir.appendingPathComponent("pr-pilot.log")
        if !FileManager.default.fileExists(atPath: logURL.path) { FileManager.default.createFile(atPath: logURL.path, contents: nil) }
        let log = try? FileHandle(forWritingTo: logURL)
        log?.seekToEndOfFile()

        let p = Process()
        p.executableURL = URL(fileURLWithPath: python)
        p.arguments = [script]
        var e = env
        e["PR_PILOT_PORT"] = String(port)
        e["PR_PILOT_TOKEN"] = token
        e["PR_PILOT_PARENT_PID"] = String(ProcessInfo.processInfo.processIdentifier)
        e["PR_PILOT_NATIVE_NOTIFY"] = "1"
        e["PR_PILOT_VERSION"] = appVersion
        e["PR_PILOT_BUILD"] = appBuild
        e["PR_PILOT_PLATFORM"] = "macos"
        e["PR_PILOT_UPDATE_URL"] = updateURL
        e["PYTHONDONTWRITEBYTECODE"] = "1"
        e["PYTHONUNBUFFERED"] = "1"
        p.environment = e
        p.currentDirectoryURL = supportDir
        p.standardOutput = log
        p.standardError = log
        p.terminationHandler = { [weak self] _ in
            DispatchQueue.main.async {
                guard let self, !self.quitting else { return }
                // caiu sozinho: sobe de novo
                DispatchQueue.main.asyncAfter(deadline: .now() + 3) { self.ensureServer { self.web.reload() } }
            }
        }
        do { try p.run(); server = p } catch { showFatal("Não consegui iniciar o backend: \(error.localizedDescription)") }
    }

    func applicationWillTerminate(_ notification: Notification) {
        quitting = true
        server?.terminate()
    }

    // MARK: janela

    func buildWindow() {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .default()
        let js = "window.PR_PILOT_TOKEN = \(jsString(token)); window.PR_PILOT_PLATFORM = 'macos';"
        config.userContentController.addUserScript(WKUserScript(source: js, injectionTime: .atDocumentStart, forMainFrameOnly: true))
        config.userContentController.add(self, name: "prpilot")
        web = WKWebView(frame: .zero, configuration: config)
        web.uiDelegate = self
        web.navigationDelegate = self
        web.setValue(false, forKey: "drawsBackground")
        web.loadHTMLString(Self.splash, baseURL: nil)

        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1440, height: 900),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "PR Pilot"
        window.minSize = NSSize(width: 760, height: 520)
        window.contentView = web
        window.isReleasedWhenClosed = false
        window.delegate = self
        window.tabbingMode = .disallowed
        window.center()
        window.setFrameAutosaveName("PRPilotMain")
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func loadUI() {
        loaded = true
        web.load(URLRequest(url: baseURL))
        poll()
    }

    @objc func showWindow() {
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func windowShouldClose(_ sender: NSWindow) -> Bool {
        sender.orderOut(nil) // só esconde: o piloto continua agindo e avisando
        return false
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        showWindow()
        return true
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }

    @objc func reloadPage() {
        if loaded { web.reload() } else { ensureServer { [weak self] in self?.loadUI() } }
    }

    func openTarget(_ target: String) {
        showWindow()
        web.evaluateJavaScript("window.openTarget && window.openTarget(\(jsString(target)))")
    }

    // MARK: contador e notificações

    func buildStatusItem() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        if let button = statusItem.button {
            button.image = NSImage(systemSymbolName: "arrow.triangle.pull", accessibilityDescription: "PR Pilot")
            button.imagePosition = .imageLeading
        }
        let menu = NSMenu()
        menu.addItem(withTitle: "Abrir PR Pilot", action: #selector(showWindow), keyEquivalent: "")
        menu.addItem(withTitle: "Ler o Azure agora", action: #selector(refreshNow), keyEquivalent: "")
        menu.addItem(withTitle: "Procurar atualização", action: #selector(checkUpdate), keyEquivalent: "")
        menu.addItem(.separator())
        loginMenuItem = menu.addItem(withTitle: "Abrir ao iniciar o Mac", action: #selector(toggleLoginItem), keyEquivalent: "")
        menu.addItem(.separator())
        menu.addItem(withTitle: "Sair do PR Pilot", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        menu.delegate = self
        statusItem.menu = menu
    }

    func menuWillOpen(_ menu: NSMenu) {
        loginMenuItem.state = SMAppService.mainApp.status == .enabled ? .on : .off
    }

    func poll() {
        getJSON("api/summary") { [weak self] json, _ in
            guard let self else { return }
            let total = json?["total"] as? Int ?? 0
            NSApp.dockTile.badgeLabel = total > 0 ? String(total) : nil
            self.statusItem.button?.title = total > 0 ? " \(total)" : ""
            self.statusItem.button?.toolTip = json == nil ? "PR Pilot — backend fora do ar" : "PR Pilot — \(total) pendente(s)"
            guard let seq = json?["notifySeq"] as? Int else { return }
            if self.lastSeq < 0 { self.lastSeq = seq; return } // ao abrir, não repete o que já passou
            if seq > self.lastSeq { self.fetchNotifications() }
        }
    }

    func fetchNotifications() {
        getJSON("api/notifications?after=\(lastSeq)") { [weak self] json, _ in
            guard let self, let items = json?["items"] as? [[String: Any]] else { return }
            for n in items { self.deliver(n) }
            self.lastSeq = json?["seq"] as? Int ?? self.lastSeq
        }
    }

    func setupNotifications() {
        let center = UNUserNotificationCenter.current()
        center.delegate = self
        center.requestAuthorization(options: [.alert, .sound, .badge]) { [weak self] granted, _ in
            DispatchQueue.main.async { self?.nativeNotifications = granted }
        }
    }

    func deliver(_ n: [String: Any]) {
        let title = n["title"] as? String ?? "PR Pilot", subtitle = n["subtitle"] as? String ?? "", body = n["message"] as? String ?? ""
        let target = n["target"] as? String ?? ""
        if nativeNotifications {
            let content = UNMutableNotificationContent()
            content.title = title
            content.subtitle = subtitle
            content.body = body
            content.sound = .default
            content.userInfo = ["target": target]
            UNUserNotificationCenter.current().add(UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil))
        } else {
            // sem permissão de notificação: aviso simples (não abre o item ao clicar)
            let q = { (s: String) in "\"" + s.replacingOccurrences(of: "\\", with: "\\\\").replacingOccurrences(of: "\"", with: "\\\"") + "\"" }
            NSAppleScript(source: "display notification \(q(body)) with title \(q(title)) subtitle \(q(subtitle))")?.executeAndReturnError(nil)
        }
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
                                withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .sound])
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse,
                                withCompletionHandler completionHandler: @escaping () -> Void) {
        if let target = response.notification.request.content.userInfo["target"] as? String { openTarget(target) }
        completionHandler()
    }

    @objc func refreshNow() {
        URLSession.shared.dataTask(with: request("api/refresh", method: "POST")) { [weak self] _, _, _ in
            DispatchQueue.main.asyncAfter(deadline: .now() + 6) { self?.poll(); self?.web.reload() }
        }.resume()
    }

    @objc func checkUpdate() {
        showWindow()
        web.evaluateJavaScript("window.checkUpdate && window.checkUpdate(true)")
    }

    // MARK: atualização — o backend baixou e conferiu o SHA-256; aqui o .app é trocado

    func userContentController(_ ucc: WKUserContentController, didReceive message: WKScriptMessage) {
        guard let body = message.body as? [String: Any], body["type"] as? String == "install", let path = body["path"] as? String else { return }
        do { try installUpdate(dmg: path) } catch { alert("Não consegui atualizar", error.localizedDescription) }
    }

    func installUpdate(dmg: String) throws {
        let updates = supportDir.appendingPathComponent("updates").path
        guard dmg.hasPrefix(updates + "/"), dmg.hasSuffix(".dmg"), FileManager.default.fileExists(atPath: dmg) else {
            throw NSError(domain: "PRPilot", code: 1, userInfo: [NSLocalizedDescriptionKey: "Instalador fora da pasta de atualizações."])
        }
        let bundle = Bundle.main.bundlePath
        let parent = (bundle as NSString).deletingLastPathComponent
        let staged = "\(parent)/.pr-pilot-update.app"
        let mount = NSTemporaryDirectory() + "prpilot-mnt-\(UUID().uuidString)"
        try run("/usr/bin/hdiutil", ["attach", "-nobrowse", "-readonly", "-noautoopen", "-mountpoint", mount, dmg], "Não consegui abrir o .dmg baixado.")
        defer { _ = try? run("/usr/bin/hdiutil", ["detach", "-quiet", "-force", mount], "") }
        guard let app = try FileManager.default.contentsOfDirectory(atPath: mount).first(where: { $0.hasSuffix(".app") }) else {
            throw NSError(domain: "PRPilot", code: 2, userInfo: [NSLocalizedDescriptionKey: "O .dmg não tem o aplicativo."])
        }
        _ = try? run("/bin/rm", ["-rf", staged], "")
        try run("/usr/bin/ditto", ["\(mount)/\(app)", staged], "Sem permissão para gravar em \(parent). Instale o .dmg à mão desta vez.")
        // Troca depois que este processo sair; se falhar, a versão antiga volta. Nunca fica sem app.
        let q = { (s: String) in "'" + s.replacingOccurrences(of: "'", with: "'\\''") + "'" }
        let pid = ProcessInfo.processInfo.processIdentifier
        let old = "\(bundle).old-\(pid)"
        let script = """
        #!/bin/sh
        for i in $(seq 1 120); do kill -0 \(pid) 2>/dev/null || break; sleep 0.5; done
        mv \(q(bundle)) \(q(old)) || exit 1
        if mv \(q(staged)) \(q(bundle)); then
          xattr -dr com.apple.quarantine \(q(bundle)) 2>/dev/null
          rm -rf \(q(old))
        else
          mv \(q(old)) \(q(bundle))
        fi
        open \(q(bundle))
        rm -f "$0"
        """
        let path = NSTemporaryDirectory() + "prpilot-swap-\(pid).sh"
        try script.write(toFile: path, atomically: true, encoding: .utf8)
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/sh")
        p.arguments = [path]
        try p.run()
        NSApp.terminate(nil)
    }

    @discardableResult
    func run(_ cmd: String, _ args: [String], _ message: String) throws -> Int32 {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: cmd)
        p.arguments = args
        p.standardOutput = FileHandle.nullDevice
        p.standardError = FileHandle.nullDevice
        try p.run()
        p.waitUntilExit()
        if p.terminationStatus != 0 && !message.isEmpty {
            throw NSError(domain: "PRPilot", code: Int(p.terminationStatus), userInfo: [NSLocalizedDescriptionKey: message])
        }
        return p.terminationStatus
    }

    // MARK: abrir no login

    func enableLoginItemOnFirstRun() {
        let key = "loginItemOffered"
        guard !UserDefaults.standard.bool(forKey: key) else { return }
        UserDefaults.standard.set(true, forKey: key)
        try? SMAppService.mainApp.register()
    }

    @objc func toggleLoginItem() {
        do {
            if SMAppService.mainApp.status == .enabled { try SMAppService.mainApp.unregister() } else { try SMAppService.mainApp.register() }
        } catch {
            alert("Não consegui alterar o item de login", error.localizedDescription)
        }
    }

    // MARK: diálogos do JavaScript (alert/confirm/prompt) e links externos

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let a = NSAlert()
        a.messageText = message
        a.addButton(withTitle: "OK")
        a.beginSheetModal(for: window) { _ in completionHandler() }
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let a = NSAlert()
        a.messageText = message
        a.addButton(withTitle: "Confirmar")
        a.addButton(withTitle: "Cancelar")
        a.beginSheetModal(for: window) { completionHandler($0 == .alertFirstButtonReturn) }
    }

    func webView(_ webView: WKWebView, runJavaScriptTextInputPanelWithPrompt prompt: String, defaultText: String?,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (String?) -> Void) {
        let a = NSAlert()
        a.messageText = prompt
        let field = NSTextField(frame: NSRect(x: 0, y: 0, width: 320, height: 24))
        field.stringValue = defaultText ?? ""
        a.accessoryView = field
        a.addButton(withTitle: "Confirmar")
        a.addButton(withTitle: "Cancelar")
        a.window.initialFirstResponder = field
        a.beginSheetModal(for: window) { completionHandler($0 == .alertFirstButtonReturn ? field.stringValue : nil) }
    }

    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = navigationAction.request.url { NSWorkspace.shared.open(url) } // target=_blank → navegador
        return nil
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if let url = navigationAction.request.url, let host = url.host, host != "127.0.0.1", url.scheme?.hasPrefix("http") == true {
            NSWorkspace.shared.open(url)
            return decisionHandler(.cancel)
        }
        decisionHandler(.allow)
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { [weak self] in self?.reloadPage() }
    }

    // MARK: menus e utilidades

    func buildMainMenu() {
        let main = NSMenu()
        let appItem = NSMenuItem()
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "Sobre o PR Pilot", action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        appMenu.addItem(withTitle: "Procurar atualização…", action: #selector(checkUpdate), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Ocultar PR Pilot", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Sair do PR Pilot", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu
        main.addItem(appItem)

        let editItem = NSMenuItem()
        let edit = NSMenu(title: "Editar")
        edit.addItem(withTitle: "Desfazer", action: Selector(("undo:")), keyEquivalent: "z")
        edit.addItem(withTitle: "Refazer", action: Selector(("redo:")), keyEquivalent: "Z")
        edit.addItem(.separator())
        edit.addItem(withTitle: "Recortar", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        edit.addItem(withTitle: "Copiar", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        edit.addItem(withTitle: "Colar", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        edit.addItem(withTitle: "Selecionar tudo", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        editItem.submenu = edit
        main.addItem(editItem)

        let viewItem = NSMenuItem()
        let view = NSMenu(title: "Visualizar")
        view.addItem(withTitle: "Recarregar", action: #selector(reloadPage), keyEquivalent: "r")
        view.addItem(withTitle: "Ler o Azure agora", action: #selector(refreshNow), keyEquivalent: "R")
        viewItem.submenu = view
        main.addItem(viewItem)

        let winItem = NSMenuItem()
        let win = NSMenu(title: "Janela")
        win.addItem(withTitle: "Minimizar", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        win.addItem(withTitle: "Fechar", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")
        win.addItem(withTitle: "Mostrar PR Pilot", action: #selector(showWindow), keyEquivalent: "0")
        winItem.submenu = win
        main.addItem(winItem)
        NSApp.windowsMenu = win
        NSApp.mainMenu = main
    }

    func alert(_ title: String, _ text: String) {
        let a = NSAlert()
        a.messageText = title
        a.informativeText = text
        a.runModal()
    }

    func showFatal(_ text: String) {
        web?.loadHTMLString(Self.splash.replacingOccurrences(of: "Iniciando…", with: text), baseURL: nil)
    }

    func jsString(_ s: String) -> String {
        let data = try? JSONSerialization.data(withJSONObject: [s])
        let arr = data.flatMap { String(data: $0, encoding: .utf8) } ?? "[\"\"]"
        return String(arr.dropFirst().dropLast())
    }

    static let splash = """
    <html><body style="margin:0;height:100vh;display:grid;place-items:center;font:15px -apple-system,sans-serif;
    background:#f4f5f7;color:#4a5160"><style>@media(prefers-color-scheme:dark){body{background:#0f1115!important;color:#b4bac6!important}}</style>
    <div style="text-align:center;max-width:520px;padding:0 24px"><div style="margin:0 auto 14px;width:56px"><svg width="56" height="56" viewBox="0 0 512 512" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M158.4 443.1 L158.4 288.4 L101.4 288.4 L101.4 443.1 Z" fill="url(#g)"/><path d="M321.3 442.1 L321.1 436.9 L320.4 430.8 L319.4 424.8 L318.0 419.0 L316.2 413.3 L314.1 407.8 L311.7 402.4 L309.1 397.3 L306.2 392.2 L303.2 387.3 L299.9 382.6 L296.5 378.0 L292.9 373.5 L289.1 369.2 L285.2 364.9 L281.2 360.8 L277.1 356.7 L272.9 352.8 L268.6 348.9 L264.2 345.1 L259.7 341.4 L255.2 337.8 L250.6 334.2 L246.0 330.7 L241.3 327.3 L236.6 323.9 L231.9 320.6 L227.1 317.4 L222.4 314.2 L217.7 311.0 L213.0 308.0 L208.4 305.0 L203.7 302.0 L199.2 299.2 L194.7 296.3 L190.2 293.6 L185.9 290.8 L181.6 288.2 L177.4 285.6 L173.4 283.1 L169.5 280.6 L165.7 278.2 L162.1 275.9 L158.7 273.7 L155.4 271.5 L152.3 269.4 L149.5 267.4 L146.7 265.3 L113.2 311.5 L116.4 313.8 L119.9 316.3 L123.6 318.8 L127.3 321.2 L131.1 323.7 L135.0 326.3 L139.0 328.8 L143.1 331.4 L147.3 334.0 L151.5 336.6 L155.8 339.2 L160.1 341.9 L164.4 344.6 L168.8 347.4 L173.2 350.2 L177.6 353.0 L182.0 355.8 L186.4 358.7 L190.8 361.6 L195.1 364.5 L199.4 367.4 L203.6 370.4 L207.8 373.4 L211.9 376.4 L215.9 379.5 L219.8 382.5 L223.7 385.6 L227.4 388.6 L230.9 391.7 L234.4 394.8 L237.6 397.9 L240.7 400.9 L243.7 404.0 L246.5 407.0 L249.0 410.0 L251.4 413.0 L253.6 415.9 L255.6 418.7 L257.3 421.5 L258.9 424.3 L260.2 426.9 L261.4 429.4 L262.3 431.9 L263.0 434.3 L263.6 436.6 L264.0 438.8 L264.2 441.0 L264.3 444.2 Z" fill="url(#g)"/><path d="M158.4 289.2 L158.5 285.7 L158.7 283.4 L159.0 281.3 L159.4 279.5 L159.8 277.8 L160.4 276.4 L160.9 275.1 L161.6 273.8 L162.3 272.6 L163.1 271.5 L164.1 270.3 L165.2 269.1 L166.4 267.8 L167.9 266.6 L169.6 265.2 L171.4 263.9 L173.5 262.5 L175.8 261.0 L178.3 259.6 L180.9 258.1 L183.8 256.6 L186.9 255.1 L190.1 253.6 L193.5 252.1 L197.1 250.5 L200.8 248.9 L204.7 247.2 L208.7 245.5 L212.8 243.8 L217.0 242.0 L221.3 240.1 L225.7 238.1 L230.2 236.1 L234.8 234.0 L239.5 231.7 L244.2 229.4 L249.0 226.9 L253.8 224.3 L258.6 221.5 L263.5 218.6 L268.4 215.6 L273.3 212.3 L278.3 208.9 L283.2 205.3 L288.0 201.5 L292.9 197.5 L297.7 193.2 L302.1 189.1 L263.1 147.5 L259.3 151.1 L255.9 154.1 L252.3 157.1 L248.7 159.9 L245.1 162.6 L241.4 165.1 L237.6 167.6 L233.9 170.0 L230.0 172.2 L226.2 174.4 L222.3 176.5 L218.4 178.5 L214.4 180.5 L210.5 182.4 L206.5 184.3 L202.5 186.1 L198.4 187.9 L194.4 189.6 L190.4 191.4 L186.3 193.1 L182.3 194.8 L178.2 196.5 L174.2 198.3 L170.2 200.1 L166.1 201.9 L162.2 203.8 L158.2 205.7 L154.2 207.8 L150.3 209.9 L146.4 212.2 L142.5 214.6 L138.7 217.2 L134.9 220.0 L131.2 222.9 L127.6 226.1 L124.1 229.6 L120.7 233.2 L117.6 237.2 L114.6 241.4 L111.9 245.9 L109.4 250.6 L107.3 255.6 L105.5 260.7 L104.0 266.0 L102.9 271.4 L102.1 277.0 L101.6 282.6 L101.4 287.7 Z" fill="url(#g)"/><path d="M423.8 27.1 L427.6 32.1 L430.0 37.7 L430.9 43.8 L430.5 50.2 L428.6 56.8 L425.5 63.5 L421.1 70.1 L415.6 76.4 L381.4 110.6 L421.0 235.0 L399.2 256.9 L337.6 154.3 L295.2 191.3 L303.4 232.3 L288.4 247.3 L254.2 196.7 L203.6 162.5 L218.6 147.5 L259.7 155.7 L296.6 113.3 L194.0 51.8 L215.9 29.9 L340.4 69.5 L374.6 35.3 L380.9 29.8 L387.4 25.4 L394.1 22.3 L400.7 20.5 L407.1 20.0 L413.2 20.9 L418.8 23.3 Z" fill="url(#g)"/><path d="M178.8 443.1 L178.6 447.4 L178.1 451.6 L177.1 455.8 L175.9 459.9 L174.2 463.8 L172.3 467.6 L170.0 471.2 L167.4 474.5 L164.5 477.7 L161.3 480.6 L158.0 483.2 L154.4 485.5 L150.6 487.4 L146.6 489.1 L142.6 490.3 L138.4 491.3 L134.2 491.8 L129.9 492.0 L125.7 491.8 L121.5 491.3 L117.3 490.3 L113.2 489.1 L109.3 487.4 L105.5 485.5 L101.9 483.2 L98.5 480.6 L95.4 477.7 L92.5 474.5 L89.9 471.2 L87.6 467.6 L85.7 463.8 L84.0 459.9 L82.7 455.8 L81.8 451.6 L81.3 447.4 L81.1 443.1 L81.3 438.9 L81.8 434.7 L82.7 430.5 L84.0 426.4 L85.7 422.5 L87.6 418.7 L89.9 415.1 L92.5 411.7 L95.4 408.6 L98.5 405.7 L101.9 403.1 L105.5 400.8 L109.3 398.9 L113.2 397.2 L117.3 395.9 L121.5 395.0 L125.7 394.5 L129.9 394.3 L134.2 394.5 L138.4 395.0 L142.6 395.9 L146.6 397.2 L150.6 398.9 L154.4 400.8 L158.0 403.1 L161.3 405.7 L164.5 408.6 L167.4 411.7 L170.0 415.1 L172.3 418.7 L174.2 422.5 L175.9 426.4 L177.1 430.5 L178.1 434.7 L178.6 438.9 Z" fill="url(#g)"/><path d="M341.7 443.1 L341.5 447.4 L340.9 451.6 L340.0 455.8 L338.7 459.9 L337.1 463.8 L335.1 467.6 L332.8 471.2 L330.2 474.5 L327.4 477.7 L324.2 480.6 L320.8 483.2 L317.2 485.5 L313.5 487.4 L309.5 489.1 L305.5 490.3 L301.3 491.3 L297.1 491.8 L292.8 492.0 L288.5 491.8 L284.3 491.3 L280.2 490.3 L276.1 489.1 L272.2 487.4 L268.4 485.5 L264.8 483.2 L261.4 480.6 L258.3 477.7 L255.4 474.5 L252.8 471.2 L250.5 467.6 L248.5 463.8 L246.9 459.9 L245.6 455.8 L244.7 451.6 L244.1 447.4 L243.9 443.1 L244.1 438.9 L244.7 434.7 L245.6 430.5 L246.9 426.4 L248.5 422.5 L250.5 418.7 L252.8 415.1 L255.4 411.7 L258.3 408.6 L261.4 405.7 L264.8 403.1 L268.4 400.8 L272.2 398.9 L276.1 397.2 L280.2 395.9 L284.3 395.0 L288.5 394.5 L292.8 394.3 L297.1 394.5 L301.3 395.0 L305.5 395.9 L309.5 397.2 L313.5 398.9 L317.2 400.8 L320.8 403.1 L324.2 405.7 L327.4 408.6 L330.2 411.7 L332.8 415.1 L335.1 418.7 L337.1 422.5 L338.7 426.4 L340.0 430.5 L340.9 434.7 L341.5 438.9 Z" fill="url(#g)"/><path d="M174.7 288.4 L174.6 292.3 L174.0 296.2 L173.2 300.0 L172.0 303.7 L170.5 307.3 L168.7 310.8 L166.6 314.1 L164.2 317.2 L161.6 320.1 L158.7 322.7 L155.6 325.1 L152.3 327.2 L148.9 329.0 L145.3 330.5 L141.5 331.7 L137.7 332.5 L133.8 333.0 L129.9 333.2 L126.0 333.0 L122.2 332.5 L118.3 331.7 L114.6 330.5 L111.0 329.0 L107.5 327.2 L104.2 325.1 L101.1 322.7 L98.3 320.1 L95.6 317.2 L93.2 314.1 L91.1 310.8 L89.3 307.3 L87.8 303.7 L86.7 300.0 L85.8 296.2 L85.3 292.3 L85.1 288.4 L85.3 284.5 L85.8 280.6 L86.7 276.8 L87.8 273.1 L89.3 269.5 L91.1 266.0 L93.2 262.7 L95.6 259.6 L98.3 256.7 L101.1 254.1 L104.2 251.7 L107.5 249.6 L111.0 247.8 L114.6 246.3 L118.3 245.2 L122.2 244.3 L126.0 243.8 L129.9 243.6 L133.8 243.8 L137.7 244.3 L141.5 245.2 L145.3 246.3 L148.9 247.8 L152.3 249.6 L155.6 251.7 L158.7 254.1 L161.6 256.7 L164.2 259.6 L166.6 262.7 L168.7 266.0 L170.5 269.5 L172.0 273.1 L173.2 276.8 L174.0 280.6 L174.6 284.5 Z" fill="#22C38E"/><path d="M147.2 288.4 L147.2 289.9 L147.0 291.4 L146.7 292.9 L146.2 294.3 L145.6 295.7 L144.9 297.1 L144.1 298.3 L143.2 299.5 L142.2 300.6 L141.1 301.7 L139.9 302.6 L138.6 303.4 L137.2 304.1 L135.9 304.7 L134.4 305.1 L132.9 305.5 L131.4 305.7 L129.9 305.7 L128.4 305.7 L126.9 305.5 L125.5 305.1 L124.0 304.7 L122.6 304.1 L121.3 303.4 L120.0 302.6 L118.8 301.7 L117.7 300.6 L116.7 299.5 L115.8 298.3 L115.0 297.1 L114.3 295.7 L113.7 294.3 L113.2 292.9 L112.9 291.4 L112.7 289.9 L112.6 288.4 L112.7 286.9 L112.9 285.4 L113.2 283.9 L113.7 282.5 L114.3 281.1 L115.0 279.8 L115.8 278.5 L116.7 277.3 L117.7 276.2 L118.8 275.2 L120.0 274.2 L121.3 273.4 L122.6 272.7 L124.0 272.2 L125.5 271.7 L126.9 271.4 L128.4 271.2 L129.9 271.1 L131.4 271.2 L132.9 271.4 L134.4 271.7 L135.9 272.2 L137.2 272.7 L138.6 273.4 L139.9 274.2 L141.1 275.2 L142.2 276.2 L143.2 277.3 L144.1 278.5 L144.9 279.8 L145.6 281.1 L146.2 282.5 L146.7 283.9 L147.0 285.4 L147.2 286.9 Z" fill="#FFFFFF"/><defs><linearGradient id="g" x1="0" y1="512" x2="512" y2="0" gradientUnits="userSpaceOnUse"><stop stop-color="#6D4AF0"/><stop offset="1" stop-color="#2F8CF0"/></linearGradient><linearGradient id="bg" x1="100" y1="924" x2="924" y2="100" gradientUnits="userSpaceOnUse"><stop stop-color="#4B2FC9"/><stop offset="1" stop-color="#2F86EE"/></linearGradient></defs></svg></div>Iniciando…</div></body></html>
    """
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
