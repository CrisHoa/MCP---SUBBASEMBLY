// SacHost: tiến trình .NET Framework kiểm định file .pkt bằng chính DLL của Autodesk Subassembly Composer.
//
// Cách dùng:  SacHost.exe "<thư mục cài SAC>"
//   Đọc từng dòng từ stdin, trả về đúng MỘT dòng JSON cho mỗi dòng nhận được:
//     "<đường dẫn .pkt>"          -> kiểm tra đủ 3 bước
//     "nodoc|<đường dẫn .pkt>"    -> bỏ bước 3 (document)
//     "__PING__"                  -> {"pong":true,...}
//     dòng rỗng / EOF             -> thoát
//
// 3 bước kiểm tra:
//   1. xaml_load:  ActivityXamlServices.Load (DynamicActivity).
//   2. validation: ActivityValidationServices.Validate -> dựng cây activity (bắt tag sai, x:Reference treo)
//                  và biên dịch biểu thức VB (biến chưa khai báo, cú pháp VB hỏng, sai kiểu...).
//   3. document:   new SubassemblyDocument(path) của WorkflowEditor.dll (cách SAC GUI mở file).
//                  Lớp này để lại trạng thái tĩnh làm hỏng các lần kiểm tra sau, nên luôn chạy trong
//                  một AppDomain riêng và huỷ ngay sau đó.
//
// Biên dịch bằng csc.exe (C# 5) của .NET Framework 4.x: xem sac_mcp/native/host.py.

using System;
using System.Activities;
using System.Activities.Validation;
using System.Activities.XamlIntegration;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Web.Script.Serialization;

namespace SacMcp
{
    /// <summary>Bộ nạp DLL của SAC theo tên, dùng chung cho AppDomain chính và AppDomain con.</summary>
    public sealed class SacResolver
    {
        readonly string _dir;
        readonly Dictionary<string, Assembly> _cache =
            new Dictionary<string, Assembly>(StringComparer.OrdinalIgnoreCase);

        public SacResolver(string dir) { _dir = dir; }

        public void Install() { AppDomain.CurrentDomain.AssemblyResolve += OnResolve; }

        Assembly OnResolve(object sender, ResolveEventArgs e)
        {
            var name = new AssemblyName(e.Name).Name;
            Assembly asm;
            if (_cache.TryGetValue(name, out asm)) return asm;
            _cache[name] = null; // chặn đệ quy
            var p = Path.Combine(_dir, name + ".dll");
            if (!File.Exists(p)) return null;
            asm = Assembly.LoadFrom(p);
            _cache[name] = asm;
            return asm;
        }
    }

    /// <summary>Chạy trong AppDomain con: mở file bằng SubassemblyDocument giống SAC GUI.</summary>
    public sealed class DocumentChecker : MarshalByRefObject
    {
        public string Check(string sacDir, string pktPath)
        {
            try
            {
                new SacResolver(sacDir).Install();
                var wfe = Assembly.LoadFrom(Path.Combine(sacDir, "WorkflowEditor.dll"));
                var docType = wfe.GetType("Autodesk.SubassemblyComposer.WorkflowEditor.SubassemblyDocument", true);
                Activator.CreateInstance(docType, new object[] { pktPath });
                return null;
            }
            catch (Exception ex)
            {
                return SacHost.Innermost(ex).Message;
            }
        }
    }

    public static class SacHost
    {
        static string _sacDir;

        [STAThread]
        public static int Main(string[] args)
        {
            if (args.Length < 1 || !Directory.Exists(args[0]))
            {
                Console.Error.WriteLine("Usage: SacHost.exe <SubassemblyComposerDir>");
                return 2;
            }
            _sacDir = args[0];
            Console.InputEncoding = new UTF8Encoding(false);
            Console.OutputEncoding = new UTF8Encoding(false);
            new SacResolver(_sacDir).Install();

            // SAC GUI luôn nạp sẵn designer của WF4: các thuộc tính gắn kèm sap2010:WorkflowViewState.*
            // (ViewStateManager, IdRef) nằm trong assembly này. Nạp trước để kết quả không phụ thuộc thứ tự file.
            Assembly.Load("System.Activities.Presentation, Version=4.0.0.0, Culture=neutral, PublicKeyToken=31bf3856ad364e35");

            foreach (var n in new[] { "Subassembly.API", "Subassembly.WorkflowEngine", "Subassembly.ActivityLibrary" })
            {
                var p = Path.Combine(_sacDir, n + ".dll");
                if (File.Exists(p)) Assembly.LoadFrom(p);
            }

            var json = new JavaScriptSerializer { MaxJsonLength = int.MaxValue };
            string line;
            while ((line = Console.In.ReadLine()) != null)
            {
                line = line.Trim();
                if (line.Length == 0) break;
                object result;
                try
                {
                    if (line == "__PING__")
                    {
                        var pong = new Dictionary<string, object>();
                        pong["pong"] = true;
                        pong["sac_dir"] = _sacDir;
                        result = pong;
                    }
                    else if (line == "__CATALOG__")
                    {
                        result = Catalog();
                    }
                    else if (line.StartsWith("nodoc|", StringComparison.Ordinal))
                    {
                        result = Check(line.Substring(6), false);
                    }
                    else
                    {
                        result = Check(line, true);
                    }
                }
                catch (Exception ex)
                {
                    var fail = new Dictionary<string, object>();
                    fail["pkt"] = line;
                    fail["host_error"] = Innermost(ex).ToString();
                    result = fail;
                }
                Console.Out.WriteLine(json.Serialize(result));
                Console.Out.Flush();
            }
            return 0;
        }

        /// <summary>Danh mục activity của Subassembly.ActivityLibrary: {tên: [tên thuộc tính public]}.</summary>
        static Dictionary<string, object> Catalog()
        {
            var acts = new Dictionary<string, object>();
            var lib = AppDomain.CurrentDomain.GetAssemblies()
                .FirstOrDefault(a => a.GetName().Name == "Subassembly.ActivityLibrary");
            if (lib != null)
            {
                Type[] types;
                try { types = lib.GetTypes(); }
                catch (ReflectionTypeLoadException ex) { types = ex.Types.Where(t => t != null).ToArray(); }
                foreach (var t in types)
                {
                    if (!t.IsPublic || t.IsAbstract || !typeof(Activity).IsAssignableFrom(t)) continue;
                    var props = t.GetProperties(BindingFlags.Public | BindingFlags.Instance);
                    var info = new Dictionary<string, object>();
                    info["properties"] = props.Select(p => p.Name).Distinct().OrderBy(n => n).ToArray();
                    info["required"] = props
                        .Where(p => p.IsDefined(typeof(RequiredArgumentAttribute), true))
                        .Select(p => p.Name).Distinct().OrderBy(n => n).ToArray();
                    acts[t.Name] = info;
                }
            }
            var r = new Dictionary<string, object>();
            r["sac_dir"] = _sacDir;
            r["assembly_version"] = lib != null ? lib.GetName().Version.ToString() : null;
            r["activities"] = acts;
            return r;
        }

        public static Exception Innermost(Exception ex)
        {
            while (ex.InnerException != null) ex = ex.InnerException;
            return ex;
        }

        static Dictionary<string, object> Check(string pktPath, bool runDocument)
        {
            var sw = Stopwatch.StartNew();
            var r = new Dictionary<string, object>();
            r["pkt"] = pktPath;
            var errors = new List<object>();
            var warnings = new List<object>();
            r["validation_errors"] = errors;
            r["validation_warnings"] = warnings;

            string xaml = null;
            string readError = null;
            try
            {
                using (var zip = ZipFile.OpenRead(pktPath))
                {
                    var entry = zip.Entries.FirstOrDefault(
                        z => z.Name.EndsWith(".xaml", StringComparison.OrdinalIgnoreCase));
                    if (entry == null)
                    {
                        readError = "Gói .pkt không có file .xaml.";
                    }
                    else
                    {
                        using (var sr = new StreamReader(entry.Open(), Encoding.UTF8, true))
                            xaml = sr.ReadToEnd();
                    }
                }
            }
            catch (Exception ex)
            {
                readError = "Không đọc được gói .pkt: " + Innermost(ex).Message;
            }

            if (xaml == null)
            {
                r["xaml_load_ok"] = false;
                r["xaml_load_error"] = readError;
                r["validation_ok"] = false;
            }
            else
            {
                Activity act = null;
                try
                {
                    var settings = new ActivityXamlServicesSettings { CompileExpressions = false };
                    act = ActivityXamlServices.Load(new StringReader(xaml), settings);
                    r["xaml_load_ok"] = true;
                }
                catch (Exception ex)
                {
                    r["xaml_load_ok"] = false;
                    r["xaml_load_error"] = Innermost(ex).Message;
                    r["validation_ok"] = false;
                }

                if (act != null)
                {
                    try
                    {
                        var res = ActivityValidationServices.Validate(act);
                        foreach (var e in res.Errors) errors.Add(Describe(e));
                        foreach (var w in res.Warnings) warnings.Add(Describe(w));
                        r["validation_ok"] = res.Errors.Count == 0;
                    }
                    catch (Exception ex)
                    {
                        // DynamicActivity dựng cây activity lười: tag sai / x:Reference treo nổ ở đây
                        r["validation_ok"] = false;
                        var d = new Dictionary<string, object>();
                        d["activity"] = null;
                        d["property"] = null;
                        d["message"] = Innermost(ex).Message;
                        errors.Add(d);
                    }
                }
            }

            if (runDocument)
            {
                AppDomain domain = null;
                try
                {
                    var setup = new AppDomainSetup { ApplicationBase = AppDomain.CurrentDomain.BaseDirectory };
                    domain = AppDomain.CreateDomain("SacDocumentCheck", null, setup);
                    var checker = (DocumentChecker)domain.CreateInstanceAndUnwrap(
                        typeof(DocumentChecker).Assembly.FullName, typeof(DocumentChecker).FullName);
                    var err = checker.Check(_sacDir, pktPath);
                    r["document_ok"] = err == null;
                    if (err != null) r["document_error"] = err;
                }
                catch (Exception ex)
                {
                    r["document_ok"] = false;
                    r["document_error"] = Innermost(ex).Message;
                }
                finally
                {
                    if (domain != null)
                    {
                        try { AppDomain.Unload(domain); } catch (Exception) { }
                    }
                }
            }

            r["elapsed_ms"] = sw.ElapsedMilliseconds;
            return r;
        }

        static Dictionary<string, object> Describe(ValidationError e)
        {
            var d = new Dictionary<string, object>();
            d["activity"] = e.Source != null ? e.Source.DisplayName : null;
            d["property"] = e.PropertyName;
            d["message"] = e.Message;
            return d;
        }
    }
}
