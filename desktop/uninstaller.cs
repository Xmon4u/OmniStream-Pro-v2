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
                KillProcess("OmniStream_Pro");
                KillProcess("OmniStream_Pro_Setup");

                // 2. Remove Desktop Shortcut
                string desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
                string desktopShortcut = Path.Combine(desktop, "OmniStream Pro.lnk");
                if (File.Exists(desktopShortcut))
                {
                    try { File.Delete(desktopShortcut); } catch { }
                }

                // 3. Remove Start Menu folder
                string appData = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
                string startMenuDir = Path.Combine(appData, @"Microsoft\Windows\Start Menu\Programs\OmniStream Pro");
                if (Directory.Exists(startMenuDir))
                {
                    try { Directory.Delete(startMenuDir, true); } catch { }
                }

                // 4. Remove Windows Registry Uninstall Entry
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
                string cmdArgs = string.Format("/c timeout /t 1 /nobreak > nul & if exist \"{0}\" rmdir /s /q \"{0}\"", installDir);
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
