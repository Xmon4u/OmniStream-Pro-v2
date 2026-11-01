#include "Common.hpp"
#include "Database.hpp"
#include "SettingsManager.hpp"
#include "QueueManager.hpp"
#include "BridgeServer.hpp"
#include "NativeMessaging.hpp"
#include "MainWindow.h"

#include <QApplication>
#include <QIcon>
#include <iostream>
#include <string>
#include <fstream>
#include <exception>
#include <windows.h>

using namespace OmniStream;

static LONG WINAPI CrashHandler(EXCEPTION_POINTERS* p) {
    std::ofstream crash("C:\\Users\\XMON4U\\AppData\\Local\\OmniStreamPro\\logs\\unhandled_crash.log", std::ios::app);
    crash << "SEH ExceptionCode: 0x" << std::hex << p->ExceptionRecord->ExceptionCode << "\n";
    crash << "Address: " << p->ExceptionRecord->ExceptionAddress << "\n";
    crash.flush();
    return EXCEPTION_CONTINUE_SEARCH;
}

static void TerminateHandler() {
    std::ofstream crash("C:\\Users\\XMON4U\\AppData\\Local\\OmniStreamPro\\logs\\unhandled_crash.log", std::ios::app);
    crash << "std::terminate called!\n";
    try {
        auto ep = std::current_exception();
        if (ep) std::rethrow_exception(ep);
    } catch (const std::exception& e) {
        crash << "Exception what(): " << e.what() << "\n";
    } catch (...) {
        crash << "Unknown non-std exception thrown!\n";
    }
    crash.flush();
}

int main(int argc, char* argv[]) {
    SetUnhandledExceptionFilter(CrashHandler);
    std::set_terminate(TerminateHandler);

    // 1. Check for command-line arguments (Native Messaging or Headless mode)
    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--native-messaging" || arg == "-nm") {
            NativeMessaging::RunHostLoop();
            return 0;
        }
    }

    // 2. Initialize GUI Application
    int exitCode = 0;
    try {
        QApplication app(argc, argv);
        app.setApplicationName("OmniStream Pro");
        app.setApplicationVersion("2.6.0");
        app.setWindowIcon(QIcon(":/assets/images/app_logo.png"));

        // 3. Initialize Core Subsystems
        if (!Database::GetInstance().Initialize()) {
            return 1;
        }
        SettingsManager::GetInstance().Load();
        QueueManager::GetInstance().Initialize();

        // 4. Start Extension Bridge Server
        BridgeServer::GetInstance().Start(28795);

        // 5. Create and show Main Window
        MainWindow mainWindow;
        mainWindow.show();

        exitCode = app.exec();

        // 6. Clean Shutdown
        QueueManager::GetInstance().Shutdown();
        BridgeServer::GetInstance().Stop();
        Database::GetInstance().Close();
    } catch (const std::exception& e) {
        std::ofstream el("C:\\Users\\XMON4U\\AppData\\Local\\OmniStreamPro\\logs\\app_exit.log", std::ios::app);
        el << "Fatal caught exception in main: " << e.what() << "\n";
        exitCode = 1;
    } catch (...) {
        std::ofstream el("C:\\Users\\XMON4U\\AppData\\Local\\OmniStreamPro\\logs\\app_exit.log", std::ios::app);
        el << "Fatal unknown exception in main\n";
        exitCode = 1;
    }

    return exitCode;
}
