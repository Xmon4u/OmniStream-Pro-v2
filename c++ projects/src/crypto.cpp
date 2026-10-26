#include "crypto.hpp"
#include <random>

namespace OmniStream {

std::vector<uint8_t> Crypto::HexToBytes(const std::string& hexStr) {
    std::string clean = hexStr;
    if (clean.rfind("0x", 0) == 0 || clean.rfind("0X", 0) == 0) {
        clean = clean.substr(2);
    }
    if (clean.size() % 2 != 0) {
        clean = "0" + clean;
    }
    std::vector<uint8_t> bytes;
    bytes.reserve(clean.size() / 2);
    for (size_t i = 0; i < clean.size(); i += 2) {
        uint8_t byte = (uint8_t)std::strtoul(clean.substr(i, 2).c_str(), nullptr, 16);
        bytes.push_back(byte);
    }
    return bytes;
}

std::string Crypto::BytesToHex(const uint8_t* data, size_t len) {
    std::ostringstream ss;
    ss << std::hex << std::setfill('0');
    for (size_t i = 0; i < len; ++i) {
        ss << std::setw(2) << (int)data[i];
    }
    return ss.str();
}

std::string Crypto::GenerateRandomToken(size_t byteCount) {
    std::vector<uint8_t> bytes(byteCount);
    BCRYPT_ALG_HANDLE hAlg = nullptr;
    if (BCryptOpenAlgorithmProvider(&hAlg, BCRYPT_RNG_ALGORITHM, nullptr, 0) == 0) {
        BCryptGenRandom(hAlg, bytes.data(), (ULONG)bytes.size(), 0);
        BCryptCloseAlgorithmProvider(hAlg, 0);
    } else {
        std::random_device rd;
        std::mt19937 gen(rd());
        std::uniform_int_distribution<int> dis(0, 255);
        for (size_t i = 0; i < byteCount; ++i) bytes[i] = (uint8_t)dis(gen);
    }
    return BytesToHex(bytes.data(), bytes.size());
}

bool Crypto::DecryptAes128Cbc(
    const std::vector<uint8_t>& ciphertext,
    const std::vector<uint8_t>& key,
    const std::vector<uint8_t>& iv,
    std::vector<uint8_t>& plaintext
) {
    if (ciphertext.empty() || key.size() != 16) return false;

    BCRYPT_ALG_HANDLE hAlg = nullptr;
    BCRYPT_KEY_HANDLE hKey = nullptr;
    NTSTATUS status = 0;

    status = BCryptOpenAlgorithmProvider(&hAlg, BCRYPT_AES_ALGORITHM, nullptr, 0);
    if (status != 0) return false;

    // Set CBC chaining mode
    status = BCryptSetProperty(
        hAlg,
        BCRYPT_CHAINING_MODE,
        (PUCHAR)BCRYPT_CHAIN_MODE_CBC,
        sizeof(BCRYPT_CHAIN_MODE_CBC),
        0
    );
    if (status != 0) {
        BCryptCloseAlgorithmProvider(hAlg, 0);
        return false;
    }

    // Allocate key object
    DWORD keyObjSize = 0;
    DWORD dataSize = 0;
    BCryptGetProperty(hAlg, BCRYPT_OBJECT_LENGTH, (PUCHAR)&keyObjSize, sizeof(keyObjSize), &dataSize, 0);
    std::vector<uint8_t> keyObj(keyObjSize);

    status = BCryptGenerateSymmetricKey(
        hAlg,
        &hKey,
        keyObj.data(),
        (ULONG)keyObj.size(),
        (PUCHAR)key.data(),
        (ULONG)key.size(),
        0
    );

    if (status != 0) {
        BCryptCloseAlgorithmProvider(hAlg, 0);
        return false;
    }

    // IV buffer (BCrypt modifies IV during operation)
    std::vector<uint8_t> ivBuffer(16, 0);
    if (!iv.empty()) {
        size_t copyLen = std::min<size_t>(16, iv.size());
        std::copy(iv.begin(), iv.begin() + copyLen, ivBuffer.begin());
    }

    plaintext.resize(ciphertext.size());
    ULONG bytesWritten = 0;

    status = BCryptDecrypt(
        hKey,
        (PUCHAR)ciphertext.data(),
        (ULONG)ciphertext.size(),
        nullptr,
        ivBuffer.data(),
        (ULONG)ivBuffer.size(),
        plaintext.data(),
        (ULONG)plaintext.size(),
        &bytesWritten,
        BCRYPT_BLOCK_PADDING
    );

    if (status == 0) {
        plaintext.resize(bytesWritten);
    } else {
        // Fallback without padding
        status = BCryptDecrypt(
            hKey,
            (PUCHAR)ciphertext.data(),
            (ULONG)ciphertext.size(),
            nullptr,
            ivBuffer.data(),
            (ULONG)ivBuffer.size(),
            plaintext.data(),
            (ULONG)plaintext.size(),
            &bytesWritten,
            0
        );
        if (status == 0) {
            plaintext.resize(bytesWritten);
        }
    }

    BCryptDestroyKey(hKey);
    BCryptCloseAlgorithmProvider(hAlg, 0);
    return (status == 0);
}

} // namespace OmniStream
