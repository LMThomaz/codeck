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
    readonly Icon baseIcon;
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
        baseIcon = LoadIcon();

        Text = "PR Pilot";
        Icon = baseIcon;
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
                g.DrawIcon(new Icon(baseIcon, 32, 32), 0, 0);
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

    static Icon LoadIcon()
    {
        using var s = typeof(MainForm).Assembly.GetManifestResourceStream("PRPilot.app.ico");
        return s != null ? new Icon(s) : SystemIcons.Application;
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
        <div style="text-align:center;max-width:520px;padding:0 24px"><div style="width:44px;height:44px;border-radius:11px;background:#2a78d6;color:#fff;
        display:grid;place-items:center;margin:0 auto 14px;font-weight:700">PR</div>{{text}}</div></body></html>
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
}
