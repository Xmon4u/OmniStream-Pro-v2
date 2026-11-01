#pragma once

#include <string>
#include <functional>

namespace OmniStream {

class ExtensionInstaller {
public:
    struct SetupResult {
        bool success = false;
        std::string message;
        std::string browser_path;
        std::string extension_dir;
    };

    static std::string FindBrowserExecutable();
    static std::string GetExtensionDirectory();
    static SetupResult InstallExtension(std::function<void(const std::string&)> log_cb = nullptr);
};

} // namespace OmniStream

