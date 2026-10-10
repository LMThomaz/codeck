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
    <div style="text-align:center;max-width:520px;padding:0 24px"><div style="margin:0 auto 14px;width:56px"><svg width="56" height="56" viewBox="0 0 512 512" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M476 36L36 226L218 290L476 36Z" fill="url(#wing)"/><path d="M476 36L234 306L300 476L476 36Z" fill="url(#body)"/><path d="M218 290L234 306L250 382L210 338L218 290Z" fill="url(#body)"/><path d="M150 362C150 379.673 135.673 394 118 394C100.327 394 86 379.673 86 362C86 344.327 100.327 330 118 330C135.673 330 150 344.327 150 362Z" fill="url(#wing)"/><path d="M90 436C90 449.255 79.2548 460 66 460C52.7452 460 42 449.255 42 436C42 422.745 52.7452 412 66 412C79.2548 412 90 422.745 90 436Z" fill="url(#wing)"/><path d="M44 488C44 496.837 36.8366 504 28 504C19.1634 504 12 496.837 12 488C12 479.163 19.1634 472 28 472C36.8366 472 44 479.163 44 488Z" fill="url(#wing)"/><defs><linearGradient id="wing" x1="12" y1="504" x2="476" y2="36" gradientUnits="userSpaceOnUse"><stop stop-color="#7B5CFA"/><stop offset="1" stop-color="#3F95F2"/></linearGradient><linearGradient id="body" x1="234" y1="476" x2="476" y2="36" gradientUnits="userSpaceOnUse"><stop stop-color="#4B2FD0"/><stop offset="1" stop-color="#2A6FD6"/></linearGradient></defs></svg></div>Iniciando…</div></body></html>
    """
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
