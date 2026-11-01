#pragma once

#include "Common.hpp"
#include <string>

namespace OmniStream {

class NativeMessaging {
public:
    static void RunHostLoop();

    static bool SendMessageToChrome(const std::string& json_msg);
    static bool ReadMessageFromChrome(std::string& out_msg);
};

} // namespace OmniStream

