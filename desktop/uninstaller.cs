using System;
using System.IO;
using System.Diagnostics;
using System.Windows.Forms;
using Microsoft.Win32;

namespace OmniStreamUninstaller
{
    static class Program
    {
        [STAThread]
        static void Main(string[] args)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            bool isQuiet = false;
            foreach (var arg in args)
            {
                if (arg.Equals("--quiet", StringComparison.OrdinalIgnoreCase) ||
                    arg.Equals("/quiet", StringComparison.OrdinalIgnoreCase) ||
                    arg.Equals("/S", StringComparison.OrdinalIgnoreCase) ||
                    arg.Equals("-s", StringComparison.OrdinalIgnoreCase))
                {
                    isQuiet = true;
                }
            }

            if (!isQuiet)
            {
                DialogResult dr = MessageBox.Show(
                    "Are you sure you want to completely uninstall OmniStream Pro and all of its components?",
                    "OmniStream Pro Uninstall",
                    MessageBoxButtons.YesNo,
                    MessageBoxIcon.Question
                );
                if (dr != DialogResult.Yes)
                {
                    return;
                }
            }

            try
            {
                // 1. Terminate running processes
                KillProcess("OmniStreamPro");
                KillProcess("OmniStream_Pro");
                KillProcess("OmniStream_Pro_Setup");
                KillProcess("OmniStreamPro-Setup");
                KillProcess("N_m3u8DL-RE");
                KillProcess("ffmpeg");

                // 2. Remove Desktop Shortcuts
                string desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
                string[] desktopShortcuts = {
                    Path.Combine(desktop, "OmniStream Pro.lnk"),
                    Path.Combine(desktop, "OmniStream_Pro.lnk")
                };
                foreach (var sc in desktopShortcuts)
                {
                    if (File.Exists(sc))
                    {
                        try { File.Delete(sc); } catch { }
                    }
                }

                // 3. Remove Start Menu folder
                string appData = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
                string startMenuDir = Path.Combine(appData, @"Microsoft\Windows\Start Menu\Programs\OmniStream Pro");
                if (Directory.Exists(startMenuDir))
                {
                    try { Directory.Delete(startMenuDir, true); } catch { }
                }

                // 4. Remove Windows Registry Uninstall & Native Messaging Entries
                try
                {
                    using (RegistryKey parentKey = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Uninstall", true))
                    {
                        if (parentKey != null)
                        {
                            parentKey.DeleteSubKeyTree("OmniStreamPro", false);
                        }
                    }
                }
                catch { }

                string[] browserHosts = {
                    @"Software\Google\Chrome\NativeMessagingHosts\com.xmon4u.omnistream",
                    @"Software\Microsoft\Edge\NativeMessagingHosts\com.xmon4u.omnistream",
                    @"Software\BraveSoftware\Brave-Browser\NativeMessagingHosts\com.xmon4u.omnistream"
                };
                foreach (var hostKey in browserHosts)
                {
                    try
                    {
                        Registry.CurrentUser.DeleteSubKeyTree(hostKey, false);
                    }
                    catch { }
                }

                // 5. Remove Installation Directory
                string localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
                string installDir = Path.Combine(localAppData, "OmniStreamPro");
                string currentExe = Application.ExecutablePath;

                if (Directory.Exists(installDir))
                {
                    foreach (var file in Directory.GetFiles(installDir))
                    {
                        if (!string.Equals(file, currentExe, StringComparison.OrdinalIgnoreCase))
                        {
                            try { File.Delete(file); } catch { }
                        }
                    }
                    foreach (var dir in Directory.GetDirectories(installDir))
                    {
                        try { Directory.Delete(dir, true); } catch { }
                    }
                }

                // 6. Schedule self-deletion of installDir via background command
                string cmdArgs = string.Format("/c ping 127.0.0.1 -n 3 > nul & if exist \"{0}\" rd /s /q \"{0}\"", installDir);
                ProcessStartInfo psi = new ProcessStartInfo("cmd.exe", cmdArgs)
                {
                    CreateNoWindow = true,
                    UseShellExecute = false,
                    WindowStyle = ProcessWindowStyle.Hidden
                };
                Process.Start(psi);

                if (!isQuiet)
                {
                    MessageBox.Show(
                        "OmniStream Pro was successfully removed from your computer.",
                        "Uninstall Complete",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Information
                    );
                }
            }
            catch (Exception ex)
            {
                if (!isQuiet)
                {
                    MessageBox.Show(
                        "An error occurred during uninstallation:\n" + ex.Message,
                        "Uninstall Error",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Error
                    );
                }
            }
        }

        static void KillProcess(string procName)
        {
            try
            {
                foreach (var p in Process.GetProcessesByName(procName))
                {
                    try
                    {
                        p.Kill();
                        p.WaitForExit(2000);
                    }
                    catch { }
                }
            }
            catch { }
        }
    }
}
