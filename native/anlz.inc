// Benoit Saint-Moulin
// Traktor Bridge : native core, ANLZ0000.DAT and .EXT writer (what anlz.py builds)
// Included by tbcore.cpp. Big endian everywhere, section order from a rekordbox 6 export.

namespace {

typedef std::vector<uint8_t> Out;

inline void be16(Out& o, uint32_t v) { o.push_back(uint8_t(v >> 8)); o.push_back(uint8_t(v)); }
inline void be32(Out& o, uint32_t v) {
    o.push_back(uint8_t(v >> 24)); o.push_back(uint8_t(v >> 16)); o.push_back(uint8_t(v >> 8)); o.push_back(uint8_t(v));
}
inline void tag4(Out& o, const std::string& t) { o.insert(o.end(), t.begin(), t.begin() + 4); }
inline void zeros(Out& o, size_t n) { o.insert(o.end(), n, 0); }

// name, head and data: the section as tag() writes it
Out section(const std::string& name, const Out& head, const Out& data) {
    Out o;
    tag4(o, name);
    be32(o, uint32_t(12 + head.size()));
    be32(o, uint32_t(12 + head.size() + data.size()));
    o.insert(o.end(), head.begin(), head.end());
    o.insert(o.end(), data.begin(), data.end());
    return o;
}

Out pmai(const std::vector<Out>& sections) {
    size_t body = 0;
    for (const Out& s : sections) body += s.size();
    Out o;
    tag4(o, HS("PMAI"));
    be32(o, 28); be32(o, uint32_t(28 + body)); be32(o, 1); be32(o, 0x10000); be32(o, 0x10000); be32(o, 0);
    for (const Out& s : sections) o.insert(o.end(), s.begin(), s.end());
    return o;
}

struct Wave {
    const float* low;
    const float* mid;
    const float* high;
    int64_t n;
};

inline float mx(float a, float b) { return a > b ? a : b; }
inline float top_of(const Wave& w, int64_t i) { return mx(mx(w.low[i], w.mid[i]), w.high[i]); }

// numpy float32 rounding, half to even
inline float rint32(float v) { return std::nearbyintf(v); }

// height 0-31 and whiteness 0-7 per column, brighter when the highs dominate
Out mono(const Wave& w) {
    Out o(size_t(w.n));
    for (int64_t i = 0; i < w.n; i++) {
        float top = top_of(w, i);
        float ratio = top > 0.01f ? w.high[i] / top : 1.0f;
        uint32_t h = uint8_t(rint32(31.0f * top)), wh = uint8_t(rint32(7.0f * ratio));
        o[size_t(i)] = uint8_t((wh << 5) | h);
    }
    return o;
}

Out pwav(const Wave& w) {
    Out head; be32(head, uint32_t(w.n)); be32(head, 0x10000);
    return section(HS("PWAV"), head, mono(w));
}

Out pwv2(const Wave& w) {
    Out head, data(size_t(w.n));
    be32(head, uint32_t(w.n)); be32(head, 0x10000);
    for (int64_t i = 0; i < w.n; i++) data[size_t(i)] = uint8_t(rint32(15.0f * top_of(w, i)));
    return section(HS("PWV2"), head, data);
}

Out pwv3(const Wave& w) {
    Out head; be32(head, 1); be32(head, uint32_t(w.n)); be16(head, 150); be16(head, 0);
    return section(HS("PWV3"), head, mono(w));
}

Out pwv5(const Wave& w) {
    Out head, data;
    be32(head, 2); be32(head, uint32_t(w.n)); be16(head, 150); be16(head, K32(0x0305));
    for (int64_t i = 0; i < w.n; i++) {
        float top = top_of(w, i);
        bool on = top > 0.01f;
        float safe = on ? top : 1.0f;
        uint16_t r = on ? uint16_t(rint32(7.0f * w.low[i] / safe)) : 0;
        uint16_t g = on ? uint16_t(rint32(7.0f * w.mid[i] / safe)) : 0;
        uint16_t b = on ? uint16_t(rint32(7.0f * w.high[i] / safe)) : 0;
        uint16_t word = uint16_t((r << 13) | (g << 10) | (b << 7) | (uint16_t(rint32(31.0f * top)) << 2));
        be16(data, word);
    }
    return section(HS("PWV5"), head, data);
}

Out pwv4(const Wave& w) {
    Out head, data;
    be32(head, 6); be32(head, uint32_t(w.n)); be32(head, 0);
    for (int64_t i = 0; i < w.n; i++) {
        uint8_t lo = uint8_t(rint32(127.0f * w.low[i])), mi = uint8_t(rint32(127.0f * w.mid[i])),
                hi = uint8_t(rint32(127.0f * w.high[i]));
        uint8_t top = lo > mi ? lo : mi;
        if (hi > top) top = hi;
        // the players draw from bytes 3-5 (red, green, blue), 0-2 get the overall level
        const uint8_t col[6] = {top, top, top, lo, mi, hi};
        data.insert(data.end(), col, col + 6);
    }
    return section(HS("PWV4"), head, data);
}

Out ppth(const char* path, uint32_t len) {
    Out raw;
    for (uint32_t i = 0; i < len;) {                    // UTF-8 to UTF-16 big endian
        const uint8_t* p = reinterpret_cast<const uint8_t*>(path);
        uint32_t c = p[i], need = 0;
        if (c < 0x80) need = 0;
        else if ((c >> 5) == 6) { c &= 0x1F; need = 1; }
        else if ((c >> 4) == 14) { c &= 0x0F; need = 2; }
        else if ((c >> 3) == 30) { c &= 0x07; need = 3; }
        else throw Failure();
        for (uint32_t k = 1; k <= need; k++) {
            if (i + k >= len || (p[i + k] & 0xC0) != 0x80) throw Failure();
            c = (c << 6) | (p[i + k] & 0x3F);
        }
        i += need + 1;
        if (c >= 0x10000) {
            c -= 0x10000;
            be16(raw, 0xD800 + (c >> 10));
            be16(raw, 0xDC00 + (c & 0x3FF));
        } else {
            be16(raw, c);
        }
    }
    be16(raw, 0);
    Out head; be32(head, uint32_t(raw.size()));
    return section(HS("PPTH"), head, raw);
}

Out pvbr(uint32_t frames) {
    // 400 byte offsets for VBR seeking, zero is fine, the player rebuilds them
    Out head, data;
    be32(head, 0);
    zeros(data, 1600);
    be32(data, frames);
    return section(HS("PVBR"), head, data);
}

Out pqtz(double bpm, double duration, double anchor) {
    uint32_t tempo = round_even(bpm * 100);
    Out data;
    uint32_t count = 0;
    if (bpm > 0 && duration != 0) {
        double step = 60000.0 / bpm;
        long long back = (long long)std::floor(anchor / step);
        double first = anchor - double(back) * step;
        if (tempo > 0xFFFF) throw Failure();
        for (long long i = 0; first + double(i) * step < duration * 1000; i++) {
            long long m = ((i - back) % 4 + 4) % 4;
            be16(data, uint32_t(m + 1));
            be16(data, tempo);
            be32(data, round_even(first + double(i) * step));
            count++;
        }
    }
    Out head; be32(head, 0); be32(head, K32(0x80000)); be32(head, count);
    return section(HS("PQTZ"), head, data);
}

}  // namespace
