// PR Pilot para Windows: janela (WebView2) para a tela do backend em Python, ícone na bandeja com o contador,
// notificações que abrem o item e atualização pelo ThomSoft Setup (`--update --wait-pid`).
//
// O mesmo contrato do app do macOS (macos/PRPilot.swift): sobe backend\server.py com o Python embutido e uma
// chave nova por execução — sem ela o backend não responde, então nenhum outro programa da máquina age por você.
// Desenvolvimento: PR_PILOT_ATTACH=1 + PR_PILOT_PORT conecta num backend já rodando; PR_PILOT_BACKEND_DIR e
// PR_PILOT_PYTHON apontam para o código do repositório e para o python do PATH.
using System.Diagnostics;
using System.Drawing.Drawing2D;
using System.Net.Http;
using System.Runtime.InteropServices;
using System.Text.Json;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;
using Microsoft.Win32;

namespace PRPilot;

static class Program
{
    [STAThread]
    static void Main()
    {
        using var single = new Mutex(true, @"Local\PRPilot.Single", out var first);
        using var showSignal = new EventWaitHandle(false, EventResetMode.AutoReset, @"Local\PRPilot.Show");
        if (!first)
        {
            showSignal.Set(); // já está aberto: só traz a janela para a frente
            return;
        }
        ApplicationConfiguration.Initialize();
        Application.Run(new MainForm(showSignal));
    }
}

sealed class MainForm : Form
{
    const string ProductId = "pr-pilot";
    const string RunKey = @"Software\Microsoft\Windows\CurrentVersion\Run";

    static readonly Dictionary<string, string?> Env = Environment.GetEnvironmentVariables()
        .Cast<System.Collections.DictionaryEntry>().ToDictionary(e => (string)e.Key, e => (string?)e.Value, StringComparer.OrdinalIgnoreCase);

    readonly bool attach = Env.GetValueOrDefault("PR_PILOT_ATTACH") == "1";
    readonly int port = int.TryParse(Env.GetValueOrDefault("PR_PILOT_PORT"), out var p) ? p : 47821;
    readonly string token;
    readonly string baseUrl;
    readonly string dataDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "PR Pilot");
    readonly HttpClient http = new() { Timeout = TimeSpan.FromSeconds(4) };
    readonly WebView2 web = new() { Dock = DockStyle.Fill };
    readonly NotifyIcon tray = new();
    readonly ToolStripMenuItem autostartItem = new("Iniciar com o Windows");
    readonly System.Windows.Forms.Timer timer = new() { Interval = 15000 };
    readonly Icon baseIcon, windowIcon;
    readonly IntPtr job = Job.Create();
    readonly (string Version, int Build, string UpdateUrl) office = ReadOffice();
    Process? backend;
    bool quitting, loaded, hintShown;
    int lastSeq = -1;
    string? lastTarget;

    public MainForm(EventWaitHandle showSignal)
    {
        token = attach ? Env.GetValueOrDefault("PR_PILOT_TOKEN") ?? "" : Guid.NewGuid().ToString("N") + Guid.NewGuid().ToString("N");
        baseUrl = $"http://127.0.0.1:{port}/";
        http.DefaultRequestHeaders.Add("X-PR-Pilot-Token", token);
        baseIcon = LoadIcon(SystemInformation.SmallIconSize);   // bandeja
        windowIcon = LoadIcon(SystemInformation.IconSize);      // barra de tarefas / Alt+Tab
        RefreshShellIconsOnUpgrade();

        Text = "PR Pilot";
        Icon = windowIcon;
        MinimumSize = new Size(760, 520);
        StartPosition = FormStartPosition.CenterScreen;
        Size = new Size(1440, 900);
        Controls.Add(web);

        var menu = new ContextMenuStrip();
        menu.Items.Add("Abrir PR Pilot", null, (_, _) => ShowMain());
        menu.Items.Add("Ler o Azure agora", null, async (_, _) => await RefreshNow());
        menu.Items.Add("Procurar atualização", null, async (_, _) => { ShowMain(); await Js("window.checkUpdate && window.checkUpdate(true)"); });
        menu.Items.Add(new ToolStripSeparator());
        autostartItem.Click += (_, _) => ToggleAutostart();
        menu.Items.Add(autostartItem);
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("Sair do PR Pilot", null, (_, _) => Quit());
        menu.Opening += (_, _) => autostartItem.Checked = AutostartEnabled();
        tray.Icon = baseIcon;
        tray.Text = "PR Pilot";
        tray.ContextMenuStrip = menu;
        tray.Visible = true;
        tray.DoubleClick += (_, _) => ShowMain();
        tray.BalloonTipClicked += async (_, _) => { ShowMain(); if (lastTarget != null) await OpenTarget(lastTarget); };

        timer.Tick += async (_, _) => await Poll();
        new Thread(() => { while (showSignal.WaitOne()) BeginInvoke(ShowMain); }) { IsBackground = true }.Start();
        Load += async (_, _) => await Start();
    }

    // ------------------------------------------------------------------ backend

    static (string, int, string) ReadOffice()
    {
        // O ThomSoft Setup grava office.json ao lado do .exe: versão, build e onde procurar a próxima.
        try
        {
            var doc = JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "office.json"))).RootElement;
            return (doc.GetProperty("version").GetString() ?? "dev", doc.GetProperty("build").GetInt32(),
                    doc.TryGetProperty("updateUrl", out var u) ? u.GetString() ?? "" : "");
        }
        catch { return ("dev", 0, ""); }
    }

    async Task<(int Code, JsonElement? Json)> Get(string path)
    {
        try
        {
            using var r = await http.GetAsync(baseUrl + path);
            var body = await r.Content.ReadAsStringAsync();
            return ((int)r.StatusCode, body.Length > 0 ? JsonDocument.Parse(body).RootElement.Clone() : null);
        }
        catch { return (0, null); }
    }

    async Task Start()
    {
        await InitWebView();
        var (code, _) = await Get("api/summary");
        if (code is 401 or 403) { Fatal($"Outro PR Pilot já está usando a porta {port}. Feche-o e abra de novo."); return; }
        if (code != 200 && !attach) StartBackend();
        for (var i = 0; i < (attach ? 240 : 80); i++)
        {
            if ((await Get("api/summary")).Code == 200)
            {
                loaded = true;
                web.CoreWebView2.Navigate(baseUrl);
                timer.Start();
                await Poll();
                return;
            }
            await Task.Delay(500);
        }
        Fatal($"O backend do PR Pilot não respondeu. Log: {Path.Combine(dataDir, "pr-pilot.log")}");
    }

    void StartBackend()
    {
        var dir = AppContext.BaseDirectory;
        var backendDir = Env.GetValueOrDefault("PR_PILOT_BACKEND_DIR") ?? Path.Combine(dir, "backend");
        var python = Env.GetValueOrDefault("PR_PILOT_PYTHON") ?? Path.Combine(dir, "python", "pythonw.exe");
        var script = Path.Combine(backendDir, "server.py");
        if (!File.Exists(script) || (!File.Exists(python) && Env.GetValueOrDefault("PR_PILOT_PYTHON") == null))
        {
            Fatal("Instalação incompleta: falta o backend ou o Python embutido. Reinstale o PR Pilot.");
            return;
        }
        Directory.CreateDirectory(dataDir);
        var psi = new ProcessStartInfo(python, $"\"{script}\"")
        {
            UseShellExecute = false, CreateNoWindow = true, WorkingDirectory = dataDir,
            RedirectStandardOutput = true, RedirectStandardError = true,
        };
        psi.Environment["PR_PILOT_PORT"] = port.ToString();
        psi.Environment["PR_PILOT_TOKEN"] = token;
        psi.Environment["PR_PILOT_PARENT_PID"] = Environment.ProcessId.ToString();
        psi.Environment["PR_PILOT_NATIVE_NOTIFY"] = "1";
        psi.Environment["PR_PILOT_VERSION"] = office.Version;
        psi.Environment["PR_PILOT_BUILD"] = office.Build.ToString();
        psi.Environment["PR_PILOT_PLATFORM"] = "windows";
        psi.Environment["PR_PILOT_UPDATE_URL"] = office.UpdateUrl;
        psi.Environment["PYTHONDONTWRITEBYTECODE"] = "1";
        psi.Environment["PYTHONUNBUFFERED"] = "1";
        psi.Environment["PYTHONIOENCODING"] = "utf-8";
        var log = new StreamWriter(Path.Combine(dataDir, "pr-pilot.log"), append: true) { AutoFlush = true };
        var proc = new Process { StartInfo = psi, EnableRaisingEvents = true };
        proc.OutputDataReceived += (_, e) => { if (e.Data != null) lock (log) log.WriteLine(e.Data); };
        proc.ErrorDataReceived += (_, e) => { if (e.Data != null) lock (log) log.WriteLine(e.Data); };
        proc.Exited += (_, _) =>
        {
            if (quitting) return;
            // caiu sozinho: sobe de novo
            BeginInvoke(async () => { await Task.Delay(3000); if (!quitting) { StartBackend(); await Task.Delay(2000); web.Reload(); } });
        };
        proc.Start();
        Job.Assign(job, proc); // o Windows encerra o backend junto com o app, mesmo se o app cair
        proc.BeginOutputReadLine();
        proc.BeginErrorReadLine();
        backend = proc;
    }

    // ------------------------------------------------------------------ janela

    async Task InitWebView()
    {
        try
        {
            var envWv = await CoreWebView2Environment.CreateAsync(null, Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "PR Pilot", "WebView2"));
            await web.EnsureCoreWebView2Async(envWv);
        }
        catch (WebView2RuntimeNotFoundException)
        {
            MessageBox.Show("O PR Pilot precisa do Microsoft Edge WebView2 Runtime. A página de download vai abrir.", "PR Pilot");
            Process.Start(new ProcessStartInfo("https://go.microsoft.com/fwlink/p/?LinkId=2124703") { UseShellExecute = true });
            Quit();
            return;
        }
        var core = web.CoreWebView2;
        core.Settings.AreDevToolsEnabled = attach;
        core.Settings.IsStatusBarEnabled = false;
        core.Settings.AreDefaultContextMenusEnabled = attach;
        await core.AddScriptToExecuteOnDocumentCreatedAsync(
            $"window.PR_PILOT_TOKEN = {JsonSerializer.Serialize(token)}; window.PR_PILOT_PLATFORM = 'windows';");
        core.NewWindowRequested += (_, e) => { e.Handled = true; OpenExternal(e.Uri); }; // target=_blank → navegador
        core.NavigationStarting += (_, e) =>
        {
            if (e.Uri.StartsWith("http", StringComparison.OrdinalIgnoreCase) && !e.Uri.StartsWith(baseUrl, StringComparison.OrdinalIgnoreCase))
            {
                e.Cancel = true;
                OpenExternal(e.Uri);
            }
        };
        core.WebMessageReceived += (_, e) => OnWebMessage(e.WebMessageAsJson);
        core.NavigateToString(Splash("Iniciando…"));
    }

    static void OpenExternal(string url) => Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });

    void Fatal(string text)
    {
        if (web.CoreWebView2 != null) web.CoreWebView2.NavigateToString(Splash(System.Net.WebUtility.HtmlEncode(text)));
        else MessageBox.Show(text, "PR Pilot");
    }

    void ShowMain()
    {
        Show();
        if (WindowState == FormWindowState.Minimized) WindowState = FormWindowState.Normal;
        Activate();
    }

    protected override void OnFormClosing(FormClosingEventArgs e)
    {
        if (!quitting && e.CloseReason == CloseReason.UserClosing)
        {
            e.Cancel = true; // só esconde: o piloto continua agindo e avisando
            Hide();
            if (!hintShown)
            {
                hintShown = true;
                tray.ShowBalloonTip(4000, "PR Pilot continua rodando", "Ele segue aprovando e avisando aqui na bandeja. Para fechar de vez: botão direito → Sair.", ToolTipIcon.Info);
            }
            return;
        }
        base.OnFormClosing(e);
    }

    void Quit()
    {
        quitting = true;
        timer.Stop();
        tray.Visible = false;
        try { if (backend is { HasExited: false }) backend.Kill(true); } catch { }
        Application.Exit();
    }

    async Task Js(string script)
    {
        if (loaded && web.CoreWebView2 != null) await web.CoreWebView2.ExecuteScriptAsync(script);
    }

    async Task OpenTarget(string target) => await Js($"window.openTarget && window.openTarget({JsonSerializer.Serialize(target)})");

    async Task RefreshNow()
    {
        try
        {
            using var req = new HttpRequestMessage(HttpMethod.Post, baseUrl + "api/refresh") { Content = new StringContent("{}") };
            req.Headers.Add("X-PR-Pilot", "1");
            await http.SendAsync(req);
        }
        catch { }
        await Task.Delay(6000);
        await Poll();
        web.Reload();
    }

    // ------------------------------------------------------------------ contador e notificações

    async Task Poll()
    {
        var (code, json) = await Get("api/summary");
        var total = code == 200 && json?.TryGetProperty("total", out var t) == true ? t.GetInt32() : 0;
        Text = total > 0 ? $"({total}) PR Pilot" : "PR Pilot";
        tray.Text = code != 200 ? "PR Pilot — backend fora do ar" : total > 0 ? $"PR Pilot — {total} pendente(s)" : "PR Pilot — nada pendente";
        SetBadge(total);
        if (code != 200 || json?.TryGetProperty("notifySeq", out var s) != true) return;
        var seq = s.GetInt32();
        if (lastSeq < 0) { lastSeq = seq; return; } // ao abrir, não repete o que já passou
        if (seq <= lastSeq) return;
        var (_, list) = await Get($"api/notifications?after={lastSeq}");
        if (list?.TryGetProperty("items", out var items) == true)
            foreach (var n in items.EnumerateArray())
            {
                lastTarget = n.TryGetProperty("target", out var tg) ? tg.GetString() : null;
                var title = n.GetProperty("title").GetString() ?? "PR Pilot";
                var body = $"{n.GetProperty("subtitle").GetString()}\n{n.GetProperty("message").GetString()}".Trim();
                tray.ShowBalloonTip(8000, title, body.Length > 250 ? body[..250] : body, ToolTipIcon.Info);
            }
        lastSeq = list?.TryGetProperty("seq", out var ns) == true ? ns.GetInt32() : seq;
    }

    int lastBadge = -1;
    void SetBadge(int total)
    {
        if (total == lastBadge) return;
        lastBadge = total;
        var old = tray.Icon;
        if (total <= 0) { tray.Icon = baseIcon; }
        else
        {
            using var bmp = new Bitmap(32, 32);
            using (var g = Graphics.FromImage(bmp))
            {
                g.SmoothingMode = SmoothingMode.AntiAlias;
                g.TextRenderingHint = System.Drawing.Text.TextRenderingHint.AntiAliasGridFit;
                g.DrawIcon(new Icon(windowIcon, 32, 32), 0, 0);
                var label = total > 99 ? "99+" : total.ToString();
                g.FillEllipse(Brushes.Red, 13, 13, 19, 19);
                using var f = new Font("Segoe UI", label.Length > 1 ? 8f : 10f, FontStyle.Bold, GraphicsUnit.Pixel);
                var sz = g.MeasureString(label, f);
                g.DrawString(label, f, Brushes.White, 22.5f - sz.Width / 2, 22.5f - sz.Height / 2);
            }
            var h = bmp.GetHicon();
            tray.Icon = (Icon)Icon.FromHandle(h).Clone();
            Native.DestroyIcon(h);
        }
        if (old != baseIcon) old?.Dispose();
    }

    static Icon LoadIcon(Size size)
    {
        using var s = typeof(MainForm).Assembly.GetManifestResourceStream("PRPilot.app.ico");
        return s != null ? new Icon(s, size) : SystemIcons.Application;
    }

    /// O Windows guarda o ícone por caminho do .exe: depois de atualizar por cima, a barra de tarefas e o menu
    /// Iniciar continuariam com o ícone antigo. Na primeira execução de cada versão, pede para ele recarregar.
    void RefreshShellIconsOnUpgrade()
    {
        try
        {
            using var k = Registry.CurrentUser.CreateSubKey(@"Software\ThomSoft\PR Pilot");
            var current = $"{office.Version}+{office.Build}";
            if ((k.GetValue("IconVersion") as string) == current) return;
            Native.SHChangeNotify(0x08000000, 0x1000, IntPtr.Zero, IntPtr.Zero); // SHCNE_ASSOCCHANGED, SHCNF_FLUSH
            k.SetValue("IconVersion", current);
        }
        catch { }
    }

    // ------------------------------------------------------------------ iniciar com o Windows (mesma chave do ThomSoft Setup)

    static bool AutostartEnabled()
    {
        using var k = Registry.CurrentUser.OpenSubKey(RunKey);
        return k?.GetValue(ProductId) != null;
    }

    static void ToggleAutostart()
    {
        using var k = Registry.CurrentUser.CreateSubKey(RunKey);
        if (k.GetValue(ProductId) != null) k.DeleteValue(ProductId);
        else k.SetValue(ProductId, $"\"{Environment.ProcessPath}\"");
    }

    // ------------------------------------------------------------------ atualização

    void OnWebMessage(string json)
    {
        try
        {
            var msg = JsonDocument.Parse(json).RootElement;
            if (msg.GetProperty("type").GetString() != "install") return;
            var path = Path.GetFullPath(msg.GetProperty("path").GetString() ?? "");
            var updates = Path.GetFullPath(Path.Combine(dataDir, "updates")) + Path.DirectorySeparatorChar;
            // o backend baixou e conferiu o SHA-256; aqui só aceita o que está na pasta dele
            if (!path.StartsWith(updates, StringComparison.OrdinalIgnoreCase) || !path.EndsWith(".exe", StringComparison.OrdinalIgnoreCase) || !File.Exists(path))
                throw new InvalidOperationException("Instalador fora da pasta de atualizações.");
            Process.Start(new ProcessStartInfo(path, $"--update --wait-pid {Environment.ProcessId}") { UseShellExecute = true });
            Quit();
        }
        catch (Exception ex)
        {
            MessageBox.Show($"Não consegui atualizar: {ex.Message}", "PR Pilot");
        }
    }

    static string Splash(string text) => $$"""
        <html><body style="margin:0;height:100vh;display:grid;place-items:center;font:15px 'Segoe UI',sans-serif;background:#0f1115;color:#b4bac6">
        <div style="text-align:center;max-width:520px;padding:0 24px"><div style="margin:0 auto 14px;width:56px"><svg width="56" height="56" viewBox="0 0 512 512" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M184.0 439.2 L184.0 78.3 L122.1 78.3 L122.1 439.2 Z" fill="url(#g)"/><path d="M153.2 324.3 L158.6 324.3 L164.2 324.2 L170.0 324.1 L175.8 323.8 L181.7 323.5 L187.7 323.2 L193.8 322.7 L200.0 322.2 L206.2 321.6 L212.4 320.9 L218.7 320.1 L225.1 319.3 L231.4 318.3 L237.8 317.3 L244.1 316.1 L250.5 314.9 L256.9 313.5 L263.2 312.0 L269.5 310.5 L275.8 308.8 L282.1 306.9 L288.3 305.0 L294.4 302.9 L300.5 300.7 L306.5 298.3 L312.4 295.8 L318.3 293.1 L324.0 290.2 L329.7 287.2 L335.2 284.0 L340.6 280.6 L345.9 277.0 L351.0 273.1 L356.0 269.0 L360.8 264.7 L365.4 260.1 L369.7 255.3 L373.9 250.2 L377.7 244.8 L381.2 239.1 L384.4 233.2 L387.3 227.0 L389.7 220.6 L391.8 214.0 L393.3 207.2 L394.5 200.2 L395.2 193.1 L395.4 186.8 L333.5 184.9 L333.3 189.1 L333.0 192.2 L332.6 195.1 L331.9 197.9 L331.1 200.5 L330.1 203.1 L329.0 205.5 L327.7 207.9 L326.2 210.3 L324.5 212.7 L322.6 215.1 L320.5 217.4 L318.1 219.8 L315.6 222.1 L312.8 224.4 L309.8 226.6 L306.6 228.8 L303.1 231.0 L299.5 233.1 L295.6 235.2 L291.6 237.2 L287.4 239.1 L283.0 241.0 L278.5 242.8 L273.8 244.5 L269.0 246.1 L264.1 247.6 L259.1 249.1 L253.9 250.5 L248.7 251.8 L243.4 253.0 L238.1 254.2 L232.7 255.2 L227.2 256.2 L221.8 257.1 L216.3 257.9 L210.8 258.7 L205.3 259.4 L199.8 260.0 L194.4 260.5 L188.9 260.9 L183.6 261.3 L178.3 261.7 L173.0 261.9 L167.9 262.1 L162.8 262.3 L157.9 262.4 L152.9 262.4 Z" fill="url(#g)"/><path d="M395.4 184.8 L395.2 178.7 L394.5 171.6 L393.3 164.7 L391.7 157.9 L389.7 151.4 L387.2 145.0 L384.4 138.9 L381.2 133.0 L377.6 127.4 L373.8 122.1 L369.7 117.1 L365.3 112.3 L360.7 107.7 L356.0 103.4 L351.0 99.4 L345.9 95.5 L340.7 91.9 L335.3 88.5 L329.7 85.3 L324.1 82.2 L318.4 79.4 L312.5 76.7 L306.6 74.1 L300.6 71.7 L294.6 69.5 L288.4 67.4 L282.2 65.4 L276.0 63.5 L269.7 61.8 L263.4 60.2 L257.1 58.7 L250.7 57.3 L244.3 56.0 L238.0 54.8 L231.6 53.7 L225.2 52.7 L218.9 51.8 L212.6 51.0 L206.3 50.3 L200.1 49.6 L194.0 49.1 L187.9 48.6 L181.8 48.2 L175.9 47.9 L170.0 47.6 L164.3 47.5 L158.6 47.4 L153.2 47.3 L152.8 109.3 L157.8 109.3 L162.8 109.4 L167.8 109.6 L173.0 109.8 L178.2 110.1 L183.5 110.4 L188.8 110.8 L194.2 111.3 L199.6 111.9 L205.1 112.5 L210.6 113.2 L216.1 114.0 L221.6 114.8 L227.0 115.8 L232.5 116.8 L237.9 117.9 L243.2 119.1 L248.5 120.3 L253.7 121.6 L258.9 123.1 L263.9 124.6 L268.9 126.2 L273.7 127.8 L278.4 129.6 L282.9 131.4 L287.3 133.3 L291.5 135.2 L295.6 137.2 L299.4 139.3 L303.1 141.5 L306.5 143.6 L309.8 145.9 L312.8 148.1 L315.6 150.4 L318.2 152.8 L320.5 155.1 L322.7 157.4 L324.6 159.8 L326.3 162.1 L327.8 164.5 L329.1 166.9 L330.2 169.3 L331.2 171.8 L332.0 174.3 L332.6 177.0 L333.1 179.7 L333.4 182.7 L333.5 186.8 Z" fill="url(#g)"/><path d="M205.9 439.2 L205.7 443.8 L205.1 448.3 L204.1 452.8 L202.7 457.2 L200.9 461.5 L198.8 465.6 L196.3 469.5 L193.5 473.1 L190.4 476.5 L187.0 479.6 L183.3 482.4 L179.5 484.9 L175.4 487.0 L171.1 488.8 L166.7 490.2 L162.2 491.2 L157.6 491.8 L153.0 492.0 L148.4 491.8 L143.9 491.2 L139.4 490.2 L135.0 488.8 L130.7 487.0 L126.6 484.9 L122.7 482.4 L119.1 479.6 L115.7 476.5 L112.5 473.1 L109.7 469.5 L107.3 465.6 L105.1 461.5 L103.4 457.2 L102.0 452.8 L101.0 448.3 L100.4 443.8 L100.2 439.2 L100.4 434.5 L101.0 430.0 L102.0 425.5 L103.4 421.1 L105.1 416.8 L107.3 412.7 L109.7 408.8 L112.5 405.2 L115.7 401.8 L119.1 398.7 L122.7 395.9 L126.6 393.4 L130.7 391.3 L135.0 389.5 L139.4 388.1 L143.9 387.1 L148.4 386.5 L153.0 386.3 L157.6 386.5 L162.2 387.1 L166.7 388.1 L171.1 389.5 L175.4 391.3 L179.5 393.4 L183.3 395.9 L187.0 398.7 L190.4 401.8 L193.5 405.2 L196.3 408.8 L198.8 412.7 L200.9 416.8 L202.7 421.1 L204.1 425.5 L205.1 430.0 L205.7 434.5 Z" fill="url(#g)"/><path d="M417.3 185.8 L417.1 190.4 L416.5 195.0 L415.5 199.5 L414.1 203.9 L412.3 208.2 L410.2 212.3 L407.7 216.2 L404.9 219.8 L401.8 223.2 L398.4 226.3 L394.7 229.1 L390.9 231.6 L386.8 233.7 L382.5 235.5 L378.1 236.9 L373.6 237.9 L369.0 238.5 L364.4 238.7 L359.8 238.5 L355.3 237.9 L350.8 236.9 L346.4 235.5 L342.1 233.7 L338.0 231.6 L334.1 229.1 L330.5 226.3 L327.1 223.2 L323.9 219.8 L321.1 216.2 L318.7 212.3 L316.5 208.2 L314.8 203.9 L313.4 199.5 L312.4 195.0 L311.8 190.4 L311.6 185.8 L311.8 181.2 L312.4 176.7 L313.4 172.2 L314.8 167.8 L316.5 163.5 L318.7 159.4 L321.1 155.5 L323.9 151.9 L327.1 148.5 L330.5 145.4 L334.1 142.5 L338.0 140.1 L342.1 137.9 L346.4 136.2 L350.8 134.8 L355.3 133.8 L359.8 133.2 L364.4 133.0 L369.0 133.2 L373.6 133.8 L378.1 134.8 L382.5 136.2 L386.8 137.9 L390.9 140.1 L394.7 142.5 L398.4 145.4 L401.8 148.5 L404.9 151.9 L407.7 155.5 L410.2 159.4 L412.3 163.5 L414.1 167.8 L415.5 172.2 L416.5 176.7 L417.1 181.2 Z" fill="url(#g)"/><path d="M211.4 78.3 L211.1 83.4 L210.5 88.4 L209.4 93.4 L207.8 98.3 L205.9 103.0 L203.5 107.5 L200.8 111.8 L197.7 115.8 L194.3 119.6 L190.5 123.0 L186.5 126.1 L182.2 128.8 L177.7 131.2 L173.0 133.1 L168.1 134.6 L163.2 135.7 L158.1 136.4 L153.0 136.6 L148.0 136.4 L142.9 135.7 L137.9 134.6 L133.1 133.1 L128.4 131.2 L123.9 128.8 L119.6 126.1 L115.5 123.0 L111.8 119.6 L108.4 115.8 L105.3 111.8 L102.5 107.5 L100.2 103.0 L98.2 98.3 L96.7 93.4 L95.6 88.4 L94.9 83.4 L94.7 78.3 L94.9 73.2 L95.6 68.2 L96.7 63.2 L98.2 58.4 L100.2 53.7 L102.5 49.2 L105.3 44.9 L108.4 40.8 L111.8 37.1 L115.5 33.6 L119.6 30.5 L123.9 27.8 L128.4 25.5 L133.1 23.5 L137.9 22.0 L142.9 20.9 L148.0 20.2 L153.0 20.0 L158.1 20.2 L163.2 20.9 L168.1 22.0 L173.0 23.5 L177.7 25.5 L182.2 27.8 L186.5 30.5 L190.5 33.6 L194.3 37.1 L197.7 40.8 L200.8 44.9 L203.5 49.2 L205.9 53.7 L207.8 58.4 L209.4 63.2 L210.5 68.2 L211.1 73.2 Z" fill="#22C38E"/><path d="M175.8 78.3 L175.7 80.3 L175.5 82.3 L175.0 84.2 L174.4 86.1 L173.7 87.9 L172.8 89.7 L171.7 91.4 L170.5 93.0 L169.1 94.4 L167.7 95.8 L166.1 97.0 L164.4 98.0 L162.7 99.0 L160.8 99.7 L158.9 100.3 L157.0 100.8 L155.0 101.0 L153.0 101.1 L151.0 101.0 L149.1 100.8 L147.1 100.3 L145.2 99.7 L143.4 99.0 L141.6 98.0 L140.0 97.0 L138.4 95.8 L136.9 94.4 L135.6 93.0 L134.4 91.4 L133.3 89.7 L132.4 87.9 L131.6 86.1 L131.0 84.2 L130.6 82.3 L130.3 80.3 L130.3 78.3 L130.3 76.3 L130.6 74.4 L131.0 72.4 L131.6 70.5 L132.4 68.7 L133.3 66.9 L134.4 65.3 L135.6 63.7 L136.9 62.2 L138.4 60.9 L140.0 59.7 L141.6 58.6 L143.4 57.7 L145.2 56.9 L147.1 56.3 L149.1 55.9 L151.0 55.6 L153.0 55.5 L155.0 55.6 L157.0 55.9 L158.9 56.3 L160.8 56.9 L162.7 57.7 L164.4 58.6 L166.1 59.7 L167.7 60.9 L169.1 62.2 L170.5 63.7 L171.7 65.3 L172.8 66.9 L173.7 68.7 L174.4 70.5 L175.0 72.4 L175.5 74.4 L175.7 76.3 Z" fill="#FFFFFF"/><defs><linearGradient id="g" x1="0" y1="512" x2="512" y2="0" gradientUnits="userSpaceOnUse"><stop stop-color="#6D4AF0"/><stop offset="1" stop-color="#2F8CF0"/></linearGradient><linearGradient id="bg" x1="100" y1="924" x2="924" y2="100" gradientUnits="userSpaceOnUse"><stop stop-color="#4B2FC9"/><stop offset="1" stop-color="#2F86EE"/></linearGradient></defs></svg></div>{{text}}</div></body></html>
        """;
}

/// Job Object com KILL_ON_JOB_CLOSE: quando o app sai (ou cai), o Windows encerra o backend junto.
static class Job
{
    [StructLayout(LayoutKind.Sequential)]
    struct BasicLimit { public long a, b; public uint LimitFlags; public UIntPtr c, d; public uint e; public UIntPtr f; public uint g, h; }
    [StructLayout(LayoutKind.Sequential)]
    struct IoCounters { public ulong a, b, c, d, e, f; }
    [StructLayout(LayoutKind.Sequential)]
    struct ExtendedLimit { public BasicLimit Basic; public IoCounters Io; public UIntPtr a, b, c, d; }

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] static extern IntPtr CreateJobObject(IntPtr a, string? name);
    [DllImport("kernel32.dll")] static extern bool SetInformationJobObject(IntPtr job, int cls, ref ExtendedLimit info, int len);
    [DllImport("kernel32.dll")] static extern bool AssignProcessToJobObject(IntPtr job, IntPtr proc);

    public static IntPtr Create()
    {
        var job = CreateJobObject(IntPtr.Zero, null);
        var info = new ExtendedLimit { Basic = new BasicLimit { LimitFlags = 0x2000 } }; // KILL_ON_JOB_CLOSE
        SetInformationJobObject(job, 9, ref info, Marshal.SizeOf<ExtendedLimit>());
        return job;
    }

    public static void Assign(IntPtr job, Process p)
    {
        try { AssignProcessToJobObject(job, p.Handle); } catch { }
    }
}

static class Native
{
    [DllImport("user32.dll")] public static extern bool DestroyIcon(IntPtr h);
    [DllImport("shell32.dll")] public static extern void SHChangeNotify(int eventId, uint flags, IntPtr item1, IntPtr item2);
}
