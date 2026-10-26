#pragma once

#include "common.hpp"

namespace OmniStream {

class Crypto {
public:
    static bool DecryptAes128Cbc(
        const std::vector<uint8_t>& ciphertext,
        const std::vector<uint8_t>& key,
        const std::vector<uint8_t>& iv,
        std::vector<uint8_t>& plaintext
    );

    static std::vector<uint8_t> HexToBytes(const std::string& hexStr);
    static std::string BytesToHex(const uint8_t* data, size_t len);
    static std::string GenerateRandomToken(size_t byteCount = 24);
};

} // namespace OmniStream
