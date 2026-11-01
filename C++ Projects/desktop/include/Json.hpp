#pragma once

#include <string>
#include <vector>
#include <map>
#include <sstream>
#include <stdexcept>
#include <cctype>
#include <memory>
#include <iomanip>

namespace OmniStream {

class JsonValue {
public:
    enum class Type { Null, Bool, Number, String, Array, Object };

private:
    Type type_ = Type::Null;
    bool bool_val_ = false;
    double num_val_ = 0.0;
    std::string str_val_;
    std::vector<JsonValue> arr_val_;
    std::map<std::string, JsonValue> obj_val_;

public:
    JsonValue() : type_(Type::Null) {}
    JsonValue(std::nullptr_t) : type_(Type::Null) {}
    JsonValue(bool b) : type_(Type::Bool), bool_val_(b) {}
    JsonValue(int n) : type_(Type::Number), num_val_(n) {}
    JsonValue(int64_t n) : type_(Type::Number), num_val_(static_cast<double>(n)) {}
    JsonValue(double n) : type_(Type::Number), num_val_(n) {}
    JsonValue(const char* s) : type_(Type::String), str_val_(s ? s : "") {}
    JsonValue(const std::string& s) : type_(Type::String), str_val_(s) {}
    JsonValue(std::string_view s) : type_(Type::String), str_val_(s) {}
    JsonValue(const std::vector<JsonValue>& arr) : type_(Type::Array), arr_val_(arr) {}
    JsonValue(const std::map<std::string, JsonValue>& obj) : type_(Type::Object), obj_val_(obj) {}

    static JsonValue Array() {
        JsonValue v;
        v.type_ = Type::Array;
        return v;
    }

    static JsonValue Object() {
        JsonValue v;
        v.type_ = Type::Object;
        return v;
    }

    Type GetType() const { return type_; }
    bool IsNull() const { return type_ == Type::Null; }
    bool IsBool() const { return type_ == Type::Bool; }
    bool IsNumber() const { return type_ == Type::Number; }
    bool IsString() const { return type_ == Type::String; }
    bool IsArray() const { return type_ == Type::Array; }
    bool IsObject() const { return type_ == Type::Object; }

    bool AsBool(bool def = false) const { return IsBool() ? bool_val_ : def; }
    int AsInt(int def = 0) const { return IsNumber() ? static_cast<int>(num_val_) : def; }
    int64_t AsInt64(int64_t def = 0) const { return IsNumber() ? static_cast<int64_t>(num_val_) : def; }
    double AsDouble(double def = 0.0) const { return IsNumber() ? num_val_ : def; }
    std::string AsString(const std::string& def = "") const { return IsString() ? str_val_ : def; }

    const std::vector<JsonValue>& AsArray() const { return arr_val_; }
    std::vector<JsonValue>& AsArray() { return arr_val_; }

    const std::map<std::string, JsonValue>& AsObject() const { return obj_val_; }
    std::map<std::string, JsonValue>& AsObject() { return obj_val_; }

    bool Has(const std::string& key) const {
        return IsObject() && obj_val_.find(key) != obj_val_.end();
    }

    JsonValue Get(const std::string& key, const JsonValue& def = JsonValue()) const {
        if (!IsObject()) return def;
        auto it = obj_val_.find(key);
        return it != obj_val_.end() ? it->second : def;
    }

    void Set(const std::string& key, const JsonValue& val) {
        if (!IsObject()) type_ = Type::Object;
        obj_val_[key] = val;
    }

    void PushBack(const JsonValue& val) {
        if (!IsArray()) type_ = Type::Array;
        arr_val_.push_back(val);
    }

    std::string Dump() const {
        std::ostringstream ss;
        Serialize(ss);
        return ss.str();
    }

private:
    void Serialize(std::ostream& os) const {
        switch (type_) {
            case Type::Null: os << "null"; break;
            case Type::Bool: os << (bool_val_ ? "true" : "false"); break;
            case Type::Number: {
                if (num_val_ == static_cast<int64_t>(num_val_)) {
                    os << static_cast<int64_t>(num_val_);
                } else {
                    os << num_val_;
                }
                break;
            }
            case Type::String: {
                os << '"';
                for (char c : str_val_) {
                    switch (c) {
                        case '"': os << "\\\""; break;
                        case '\\': os << "\\\\"; break;
                        case '\b': os << "\\b"; break;
                        case '\f': os << "\\f"; break;
                        case '\n': os << "\\n"; break;
                        case '\r': os << "\\r"; break;
                        case '\t': os << "\\t"; break;
                        default:
                            if (static_cast<unsigned char>(c) < 0x20) {
                                os << "\\u" << std::hex << std::setw(4) << std::setfill('0') << static_cast<int>(c);
                            } else {
                                os << c;
                            }
                            break;
                    }
                }
                os << '"';
                break;
            }
            case Type::Array: {
                os << '[';
                for (size_t i = 0; i < arr_val_.size(); ++i) {
                    if (i > 0) os << ',';
                    arr_val_[i].Serialize(os);
                }
                os << ']';
                break;
            }
            case Type::Object: {
                os << '{';
                bool first = true;
                for (const auto& [k, v] : obj_val_) {
                    if (!first) os << ',';
                    first = false;
                    os << '"' << k << "\":";
                    v.Serialize(os);
                }
                os << '}';
                break;
            }
        }
    }
};

class JsonParser {
public:
    static JsonValue Parse(std::string_view json_str) {
        size_t idx = 0;
        SkipWhitespace(json_str, idx);
        if (idx >= json_str.size()) return JsonValue();
        return ParseValue(json_str, idx);
    }

private:
    static void SkipWhitespace(std::string_view s, size_t& idx) {
        while (idx < s.size() && (s[idx] == ' ' || s[idx] == '\t' || s[idx] == '\n' || s[idx] == '\r')) {
            ++idx;
        }
    }

    static JsonValue ParseValue(std::string_view s, size_t& idx) {
        SkipWhitespace(s, idx);
        if (idx >= s.size()) return JsonValue();
        char c = s[idx];
        if (c == '{') return ParseObject(s, idx);
        if (c == '[') return ParseArray(s, idx);
        if (c == '"') return ParseString(s, idx);
        if (c == 't' || c == 'f') return ParseBool(s, idx);
        if (c == 'n') return ParseNull(s, idx);
        if (c == '-' || std::isdigit(c)) return ParseNumber(s, idx);
        return JsonValue();
    }

    static JsonValue ParseObject(std::string_view s, size_t& idx) {
        ++idx; // skip '{'
        JsonValue obj = JsonValue::Object();
        while (idx < s.size()) {
            SkipWhitespace(s, idx);
            if (idx >= s.size()) break;
            if (s[idx] == '}') { ++idx; return obj; }
            if (s[idx] == ',') { ++idx; continue; }

            JsonValue key = ParseString(s, idx);
            SkipWhitespace(s, idx);
            if (idx < s.size() && s[idx] == ':') ++idx;
            JsonValue val = ParseValue(s, idx);
            obj.Set(key.AsString(), val);
        }
        return obj;
    }

    static JsonValue ParseArray(std::string_view s, size_t& idx) {
        ++idx; // skip '['
        JsonValue arr = JsonValue::Array();
        while (idx < s.size()) {
            SkipWhitespace(s, idx);
            if (idx >= s.size()) break;
            if (s[idx] == ']') { ++idx; return arr; }
            if (s[idx] == ',') { ++idx; continue; }

            JsonValue val = ParseValue(s, idx);
            arr.PushBack(val);
        }
        return arr;
    }

    static JsonValue ParseString(std::string_view s, size_t& idx) {
        if (s[idx] != '"') return JsonValue();
        ++idx;
        std::string res;
        while (idx < s.size()) {
            char c = s[idx++];
            if (c == '"') return JsonValue(res);
            if (c == '\\' && idx < s.size()) {
                char esc = s[idx++];
                switch (esc) {
                    case '"': res += '"'; break;
                    case '\\': res += '\\'; break;
                    case '/': res += '/'; break;
                    case 'b': res += '\b'; break;
                    case 'f': res += '\f'; break;
                    case 'n': res += '\n'; break;
                    case 'r': res += '\r'; break;
                    case 't': res += '\t'; break;
                    case 'u': {
                        if (idx + 4 <= s.size()) {
                            // Basic unicode hex skip/convert
                            idx += 4;
                        }
                        break;
                    }
                    default: res += esc; break;
                }
            } else {
                res += c;
            }
        }
        return JsonValue(res);
    }

    static JsonValue ParseNumber(std::string_view s, size_t& idx) {
        size_t start = idx;
        if (s[idx] == '-') ++idx;
        while (idx < s.size() && (std::isdigit(s[idx]) || s[idx] == '.' || s[idx] == 'e' || s[idx] == 'E' || s[idx] == '+' || s[idx] == '-')) {
            ++idx;
        }
        std::string num_str(s.substr(start, idx - start));
        try {
            if (num_str.find('.') != std::string::npos || num_str.find('e') != std::string::npos || num_str.find('E') != std::string::npos) {
                return JsonValue(std::stod(num_str));
            } else {
                return JsonValue(static_cast<int64_t>(std::stoll(num_str)));
            }
        } catch (...) {
            return JsonValue(0);
        }
    }

    static JsonValue ParseBool(std::string_view s, size_t& idx) {
        if (s.substr(idx, 4) == "true") { idx += 4; return JsonValue(true); }
        if (s.substr(idx, 5) == "false") { idx += 5; return JsonValue(false); }
        return JsonValue(false);
    }

    static JsonValue ParseNull(std::string_view s, size_t& idx) {
        if (s.substr(idx, 4) == "null") { idx += 4; }
        return JsonValue();
    }
};

} // namespace OmniStream

