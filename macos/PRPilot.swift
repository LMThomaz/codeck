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
        guard let body = message.body as? [String: Any] else { return }
        if body["type"] as? String == "pickFolder", let id = body["id"] as? String {
            return pickFolder(id: id, title: body["title"] as? String ?? "Escolha uma pasta")
        }
        guard body["type"] as? String == "install", let path = body["path"] as? String else { return }
        do { try installUpdate(dmg: path) } catch { alert("Não consegui atualizar", error.localizedDescription) }
    }

    // MARK: seletor de pasta — devolve o caminho para a tela por window.__nativeResolve(id, path|null)

    func pickFolder(id: String, title: String) {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.canCreateDirectories = true
        panel.allowsMultipleSelection = false
        panel.message = title
        panel.prompt = "Escolher"
        panel.beginSheetModal(for: window) { [weak self] resp in
            guard let self else { return }
            let path = resp == .OK ? panel.url?.path : nil
            self.web.evaluateJavaScript("window.__nativeResolve && window.__nativeResolve(\(self.jsString(id)), \(path.map(self.jsString) ?? "null"))")
        }
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
    <div style="text-align:center;max-width:520px;padding:0 24px"><div style="margin:0 auto 14px;width:56px"><svg width="56" height="56" viewBox="0 0 512 512" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M184.0 439.2 L184.0 78.3 L122.1 78.3 L122.1 439.2 Z" fill="url(#g)"/><path d="M153.2 324.3 L158.6 324.3 L164.2 324.2 L170.0 324.1 L175.8 323.8 L181.7 323.5 L187.7 323.2 L193.8 322.7 L200.0 322.2 L206.2 321.6 L212.4 320.9 L218.7 320.1 L225.1 319.3 L231.4 318.3 L237.8 317.3 L244.1 316.1 L250.5 314.9 L256.9 313.5 L263.2 312.0 L269.5 310.5 L275.8 308.8 L282.1 306.9 L288.3 305.0 L294.4 302.9 L300.5 300.7 L306.5 298.3 L312.4 295.8 L318.3 293.1 L324.0 290.2 L329.7 287.2 L335.2 284.0 L340.6 280.6 L345.9 277.0 L351.0 273.1 L356.0 269.0 L360.8 264.7 L365.4 260.1 L369.7 255.3 L373.9 250.2 L377.7 244.8 L381.2 239.1 L384.4 233.2 L387.3 227.0 L389.7 220.6 L391.8 214.0 L393.3 207.2 L394.5 200.2 L395.2 193.1 L395.4 186.8 L333.5 184.9 L333.3 189.1 L333.0 192.2 L332.6 195.1 L331.9 197.9 L331.1 200.5 L330.1 203.1 L329.0 205.5 L327.7 207.9 L326.2 210.3 L324.5 212.7 L322.6 215.1 L320.5 217.4 L318.1 219.8 L315.6 222.1 L312.8 224.4 L309.8 226.6 L306.6 228.8 L303.1 231.0 L299.5 233.1 L295.6 235.2 L291.6 237.2 L287.4 239.1 L283.0 241.0 L278.5 242.8 L273.8 244.5 L269.0 246.1 L264.1 247.6 L259.1 249.1 L253.9 250.5 L248.7 251.8 L243.4 253.0 L238.1 254.2 L232.7 255.2 L227.2 256.2 L221.8 257.1 L216.3 257.9 L210.8 258.7 L205.3 259.4 L199.8 260.0 L194.4 260.5 L188.9 260.9 L183.6 261.3 L178.3 261.7 L173.0 261.9 L167.9 262.1 L162.8 262.3 L157.9 262.4 L152.9 262.4 Z" fill="url(#g)"/><path d="M395.4 184.8 L395.2 178.7 L394.5 171.6 L393.3 164.7 L391.7 157.9 L389.7 151.4 L387.2 145.0 L384.4 138.9 L381.2 133.0 L377.6 127.4 L373.8 122.1 L369.7 117.1 L365.3 112.3 L360.7 107.7 L356.0 103.4 L351.0 99.4 L345.9 95.5 L340.7 91.9 L335.3 88.5 L329.7 85.3 L324.1 82.2 L318.4 79.4 L312.5 76.7 L306.6 74.1 L300.6 71.7 L294.6 69.5 L288.4 67.4 L282.2 65.4 L276.0 63.5 L269.7 61.8 L263.4 60.2 L257.1 58.7 L250.7 57.3 L244.3 56.0 L238.0 54.8 L231.6 53.7 L225.2 52.7 L218.9 51.8 L212.6 51.0 L206.3 50.3 L200.1 49.6 L194.0 49.1 L187.9 48.6 L181.8 48.2 L175.9 47.9 L170.0 47.6 L164.3 47.5 L158.6 47.4 L153.2 47.3 L152.8 109.3 L157.8 109.3 L162.8 109.4 L167.8 109.6 L173.0 109.8 L178.2 110.1 L183.5 110.4 L188.8 110.8 L194.2 111.3 L199.6 111.9 L205.1 112.5 L210.6 113.2 L216.1 114.0 L221.6 114.8 L227.0 115.8 L232.5 116.8 L237.9 117.9 L243.2 119.1 L248.5 120.3 L253.7 121.6 L258.9 123.1 L263.9 124.6 L268.9 126.2 L273.7 127.8 L278.4 129.6 L282.9 131.4 L287.3 133.3 L291.5 135.2 L295.6 137.2 L299.4 139.3 L303.1 141.5 L306.5 143.6 L309.8 145.9 L312.8 148.1 L315.6 150.4 L318.2 152.8 L320.5 155.1 L322.7 157.4 L324.6 159.8 L326.3 162.1 L327.8 164.5 L329.1 166.9 L330.2 169.3 L331.2 171.8 L332.0 174.3 L332.6 177.0 L333.1 179.7 L333.4 182.7 L333.5 186.8 Z" fill="url(#g)"/><path d="M205.9 439.2 L205.7 443.8 L205.1 448.3 L204.1 452.8 L202.7 457.2 L200.9 461.5 L198.8 465.6 L196.3 469.5 L193.5 473.1 L190.4 476.5 L187.0 479.6 L183.3 482.4 L179.5 484.9 L175.4 487.0 L171.1 488.8 L166.7 490.2 L162.2 491.2 L157.6 491.8 L153.0 492.0 L148.4 491.8 L143.9 491.2 L139.4 490.2 L135.0 488.8 L130.7 487.0 L126.6 484.9 L122.7 482.4 L119.1 479.6 L115.7 476.5 L112.5 473.1 L109.7 469.5 L107.3 465.6 L105.1 461.5 L103.4 457.2 L102.0 452.8 L101.0 448.3 L100.4 443.8 L100.2 439.2 L100.4 434.5 L101.0 430.0 L102.0 425.5 L103.4 421.1 L105.1 416.8 L107.3 412.7 L109.7 408.8 L112.5 405.2 L115.7 401.8 L119.1 398.7 L122.7 395.9 L126.6 393.4 L130.7 391.3 L135.0 389.5 L139.4 388.1 L143.9 387.1 L148.4 386.5 L153.0 386.3 L157.6 386.5 L162.2 387.1 L166.7 388.1 L171.1 389.5 L175.4 391.3 L179.5 393.4 L183.3 395.9 L187.0 398.7 L190.4 401.8 L193.5 405.2 L196.3 408.8 L198.8 412.7 L200.9 416.8 L202.7 421.1 L204.1 425.5 L205.1 430.0 L205.7 434.5 Z" fill="url(#g)"/><path d="M417.3 185.8 L417.1 190.4 L416.5 195.0 L415.5 199.5 L414.1 203.9 L412.3 208.2 L410.2 212.3 L407.7 216.2 L404.9 219.8 L401.8 223.2 L398.4 226.3 L394.7 229.1 L390.9 231.6 L386.8 233.7 L382.5 235.5 L378.1 236.9 L373.6 237.9 L369.0 238.5 L364.4 238.7 L359.8 238.5 L355.3 237.9 L350.8 236.9 L346.4 235.5 L342.1 233.7 L338.0 231.6 L334.1 229.1 L330.5 226.3 L327.1 223.2 L323.9 219.8 L321.1 216.2 L318.7 212.3 L316.5 208.2 L314.8 203.9 L313.4 199.5 L312.4 195.0 L311.8 190.4 L311.6 185.8 L311.8 181.2 L312.4 176.7 L313.4 172.2 L314.8 167.8 L316.5 163.5 L318.7 159.4 L321.1 155.5 L323.9 151.9 L327.1 148.5 L330.5 145.4 L334.1 142.5 L338.0 140.1 L342.1 137.9 L346.4 136.2 L350.8 134.8 L355.3 133.8 L359.8 133.2 L364.4 133.0 L369.0 133.2 L373.6 133.8 L378.1 134.8 L382.5 136.2 L386.8 137.9 L390.9 140.1 L394.7 142.5 L398.4 145.4 L401.8 148.5 L404.9 151.9 L407.7 155.5 L410.2 159.4 L412.3 163.5 L414.1 167.8 L415.5 172.2 L416.5 176.7 L417.1 181.2 Z" fill="url(#g)"/><path d="M211.4 78.3 L211.1 83.4 L210.5 88.4 L209.4 93.4 L207.8 98.3 L205.9 103.0 L203.5 107.5 L200.8 111.8 L197.7 115.8 L194.3 119.6 L190.5 123.0 L186.5 126.1 L182.2 128.8 L177.7 131.2 L173.0 133.1 L168.1 134.6 L163.2 135.7 L158.1 136.4 L153.0 136.6 L148.0 136.4 L142.9 135.7 L137.9 134.6 L133.1 133.1 L128.4 131.2 L123.9 128.8 L119.6 126.1 L115.5 123.0 L111.8 119.6 L108.4 115.8 L105.3 111.8 L102.5 107.5 L100.2 103.0 L98.2 98.3 L96.7 93.4 L95.6 88.4 L94.9 83.4 L94.7 78.3 L94.9 73.2 L95.6 68.2 L96.7 63.2 L98.2 58.4 L100.2 53.7 L102.5 49.2 L105.3 44.9 L108.4 40.8 L111.8 37.1 L115.5 33.6 L119.6 30.5 L123.9 27.8 L128.4 25.5 L133.1 23.5 L137.9 22.0 L142.9 20.9 L148.0 20.2 L153.0 20.0 L158.1 20.2 L163.2 20.9 L168.1 22.0 L173.0 23.5 L177.7 25.5 L182.2 27.8 L186.5 30.5 L190.5 33.6 L194.3 37.1 L197.7 40.8 L200.8 44.9 L203.5 49.2 L205.9 53.7 L207.8 58.4 L209.4 63.2 L210.5 68.2 L211.1 73.2 Z" fill="#22C38E"/><path d="M175.8 78.3 L175.7 80.3 L175.5 82.3 L175.0 84.2 L174.4 86.1 L173.7 87.9 L172.8 89.7 L171.7 91.4 L170.5 93.0 L169.1 94.4 L167.7 95.8 L166.1 97.0 L164.4 98.0 L162.7 99.0 L160.8 99.7 L158.9 100.3 L157.0 100.8 L155.0 101.0 L153.0 101.1 L151.0 101.0 L149.1 100.8 L147.1 100.3 L145.2 99.7 L143.4 99.0 L141.6 98.0 L140.0 97.0 L138.4 95.8 L136.9 94.4 L135.6 93.0 L134.4 91.4 L133.3 89.7 L132.4 87.9 L131.6 86.1 L131.0 84.2 L130.6 82.3 L130.3 80.3 L130.3 78.3 L130.3 76.3 L130.6 74.4 L131.0 72.4 L131.6 70.5 L132.4 68.7 L133.3 66.9 L134.4 65.3 L135.6 63.7 L136.9 62.2 L138.4 60.9 L140.0 59.7 L141.6 58.6 L143.4 57.7 L145.2 56.9 L147.1 56.3 L149.1 55.9 L151.0 55.6 L153.0 55.5 L155.0 55.6 L157.0 55.9 L158.9 56.3 L160.8 56.9 L162.7 57.7 L164.4 58.6 L166.1 59.7 L167.7 60.9 L169.1 62.2 L170.5 63.7 L171.7 65.3 L172.8 66.9 L173.7 68.7 L174.4 70.5 L175.0 72.4 L175.5 74.4 L175.7 76.3 Z" fill="#FFFFFF"/><defs><linearGradient id="g" x1="0" y1="512" x2="512" y2="0" gradientUnits="userSpaceOnUse"><stop stop-color="#6D4AF0"/><stop offset="1" stop-color="#2F8CF0"/></linearGradient><linearGradient id="bg" x1="100" y1="924" x2="924" y2="100" gradientUnits="userSpaceOnUse"><stop stop-color="#4B2FC9"/><stop offset="1" stop-color="#2F86EE"/></linearGradient></defs></svg></div>Iniciando…</div></body></html>
    """
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
