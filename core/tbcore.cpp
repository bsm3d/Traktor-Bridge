// Benoit Saint-Moulin
// Traktor Bridge : native core, DeviceSQL page layout (export.pdb) and waveform bands
//
// Same results as export/cdj/devicesql.py (build), pdbwrite.py (rows), anlz.py and analysis.py,
// which stay as the reference and the fallback when this library is absent. The tests
// compare the two byte for byte. Plain C interface for ctypes, no exception crosses it,
// the caller owns every buffer.

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <string>
#include <unordered_map>
#include <vector>

#include "hide.h"

#if defined(_WIN32)
#define TB_API extern "C" __declspec(dllexport)
#else
#define TB_API extern "C" __attribute__((visibility("default")))
#endif

namespace {

// ============================================================
// Little endian writers
// ============================================================

inline void put16(uint8_t* b, size_t off, uint32_t v) {
    b[off] = uint8_t(v);
    b[off + 1] = uint8_t(v >> 8);
}

inline void put32(uint8_t* b, size_t off, uint32_t v) {
    b[off] = uint8_t(v);
    b[off + 1] = uint8_t(v >> 8);
    b[off + 2] = uint8_t(v >> 16);
    b[off + 3] = uint8_t(v >> 24);
}

// ============================================================
// DeviceSQL pages
// ============================================================

const uint32_t PAGE = 4096;
const uint32_t HEAD = 0x28;
const uint32_t HEAP = PAGE - HEAD;
const int N_TABLES = 20;
const uint32_t INDEX_SLOTS = (PAGE - HEAD - 40) / 4;

inline bool indexed(int kind) { return kind == 0 || kind == 19; }

// bytes taken at the page end by the row index: groups of 16 offsets plus two u16 masks
inline uint32_t index_size(uint32_t n) {
    uint32_t full = n / 16, rest = n % 16;
    return full * 36 + (rest ? 4 + 2 * rest : 0);
}

struct Row {
    const uint8_t* p;
    uint32_t len;
};

// consecutive rows of one data page
struct Chunk {
    uint32_t first, count;
};

bool pack_rows(const std::vector<Row>& rows, std::vector<Chunk>& pages) {
    uint32_t cur = 0, used = 0, start = 0;
    for (uint32_t i = 0; i < rows.size(); i++) {
        uint32_t len = rows[i].len;
        if (len + index_size(1) > HEAP) return false;
        if (cur && used + len + index_size(cur + 1) > HEAP) {
            pages.push_back({start, cur});
            start = i;
            cur = 0;
            used = 0;
        }
        cur++;
        used += len;
    }
    if (cur) pages.push_back({start, cur});
    return true;
}

void data_page(uint8_t* buf, uint32_t idx, uint32_t kind, uint32_t nxt, uint32_t seq,
               const Row* rows, uint32_t n, bool shift) {
    std::memset(buf, 0, PAGE);
    std::vector<uint32_t> offs(n);
    uint32_t pos = 0;
    for (uint32_t i = 0; i < n; i++) {
        std::memcpy(buf + HEAD + pos, rows[i].p, rows[i].len);
        if (shift) put16(buf, HEAD + pos + 2, i * 0x20);
        offs[i] = pos;
        pos += rows[i].len;
    }
    for (uint32_t g = 0; g < n; g += 16) {
        uint32_t base = PAGE - (g / 16) * 36;
        uint32_t cnt = n - g < 16 ? n - g : 16;
        uint32_t mask = (1u << cnt) - 1;
        // present rows, then rows touched by the last write, same thing for a fresh file
        put16(buf, base - 4, mask);
        put16(buf, base - 2, mask);
        for (uint32_t k = 0; k < cnt; k++) put16(buf, base - 6 - 2 * k, offs[g + k]);
    }
    uint32_t packed = n | (n << 13);
    put32(buf, 0, 0);
    put32(buf, 4, idx);
    put32(buf, 8, kind);
    put32(buf, 12, nxt);
    put32(buf, 16, seq);
    put32(buf, 20, 0);
    buf[0x18] = uint8_t(packed);
    buf[0x19] = uint8_t(packed >> 8);
    buf[0x1a] = uint8_t(packed >> 16);
    buf[0x1b] = indexed(int(kind)) ? 0x34 : 0x24;
    put16(buf, 0x1c, HEAP - pos - index_size(n));
    put16(buf, 0x1e, pos);
    put16(buf, 0x20, n);
    put16(buf, 0x22, 0);
    put16(buf, 0x24, 0);
    put16(buf, 0x26, 0);
}

void index_page(uint8_t* buf, uint32_t idx, uint32_t kind, uint32_t nxt, uint32_t seq,
                const std::vector<uint32_t>& entries_in) {
    // a big table has more data pages than slots, the players find them through the
    // page chain anyway, so the list stops when the page is full
    uint32_t n = entries_in.size() < INDEX_SLOTS ? uint32_t(entries_in.size()) : INDEX_SLOTS;
    std::memset(buf, 0, PAGE);
    put32(buf, 0, 0);
    put32(buf, 4, idx);
    put32(buf, 8, kind);
    put32(buf, 12, nxt);
    put32(buf, 16, seq);
    buf[0x1b] = 0x64;
    put16(buf, 0x1c, 0);
    put16(buf, 0x1e, 0);
    put16(buf, 0x20, K32(0x1FFF));
    put16(buf, 0x22, K32(0x1FFF));
    put16(buf, 0x24, INDEX_SLOTS);
    put16(buf, 0x26, n ? 1 : 0);
    put32(buf, HEAD, idx);
    put32(buf, HEAD + 4, nxt);
    put32(buf, HEAD + 8, K32(0x03FFFFFF));
    put32(buf, HEAD + 12, 0);
    put16(buf, HEAD + 16, n);
    put16(buf, HEAD + 18, K32(0x1FFF));
    uint32_t pos = HEAD + 20;
    for (uint32_t i = 0; i < n; i++, pos += 4) put32(buf, pos, entries_in[i]);
    while (pos < PAGE - 20) {
        put32(buf, pos, K32(0x1FFFFFF8u));
        pos += 4;
    }
}

}  // namespace

// ============================================================
// export.pdb
// ============================================================

namespace {

// One table as the builder sees it: row pointers or a finished static page.
struct Source {
    std::vector<Row> rows;
    const uint8_t* stat = nullptr;
    bool shifted = false;
};

// Writes the file to out when cap is big enough. Returns its size, 0 when a row does not
// fit in a page.
int64_t build_file(const std::vector<Source>& src, uint8_t* out, int64_t cap) {
    struct Table {
        bool has = false, is_static = false;
        std::vector<Chunk> pages;
        std::vector<uint32_t> numbers;
    };
    std::vector<Table> tab(N_TABLES);
    for (int t = 0; t < N_TABLES; t++) {
        Table& T = tab[t];
        if (src[t].stat) {
            T.has = T.is_static = true;
            T.numbers.push_back(2 + 2 * t);
            continue;
        }
        if (src[t].rows.empty()) continue;
        if (!pack_rows(src[t].rows, T.pages)) return 0;
        T.has = true;
        T.numbers.push_back(2 + 2 * t);
    }

    uint32_t last = 2 * N_TABLES;
    for (int t = 0; t < N_TABLES; t++) {
        Table& T = tab[t];
        if (!T.has || T.is_static) continue;
        for (size_t i = 1; i < T.pages.size(); i++) T.numbers.push_back(++last);
    }

    uint32_t nxt_free = last + 1;
    uint32_t empty_cand[N_TABLES];
    for (int t = 0; t < N_TABLES; t++) {
        if (tab[t].has) empty_cand[t] = nxt_free++;
        else empty_cand[t] = 2 + 2 * t;
    }

    int64_t total = int64_t(last + 1) * PAGE;
    if (cap < total) return total;
    std::memset(out, 0, size_t(total));

    uint32_t seq = 1;
    for (int t = 0; t < N_TABLES; t++) {
        Table& T = tab[t];
        if (!T.has) continue;
        size_t count = T.is_static ? 1 : T.pages.size();
        for (size_t i = 0; i < count; i++) {
            seq++;
            uint32_t follow = i + 1 < T.numbers.size() ? T.numbers[i + 1] : empty_cand[t];
            uint8_t* dst = out + size_t(T.numbers[i]) * PAGE;
            if (T.is_static) {
                std::memcpy(dst, src[t].stat, PAGE);
                put32(dst, 0x04, T.numbers[i]);
                put32(dst, 0x0c, follow);
                put32(dst, 0x10, seq);
            } else {
                data_page(dst, T.numbers[i], uint32_t(t), follow, seq, &src[t].rows[T.pages[i].first],
                          T.pages[i].count, src[t].shifted);
            }
        }
    }

    for (int t = 0; t < N_TABLES; t++) {
        std::vector<uint32_t> entries;
        if (indexed(t) && tab[t].has)
            for (uint32_t n : tab[t].numbers) entries.push_back(n << 3);
        uint32_t s = entries.empty() ? 1 : seq + 1;
        index_page(out + size_t(1 + 2 * t) * PAGE, 1 + 2 * t, uint32_t(t), 2 + 2 * t, s, entries);
    }
    seq += 2;

    uint8_t* head = out;
    put32(head, 0, 0);
    put32(head, 4, PAGE);
    put32(head, 8, N_TABLES);
    put32(head, 12, nxt_free);
    put32(head, 16, 5);
    put32(head, 20, seq);
    put32(head, 24, 0);
    for (int t = 0; t < N_TABLES; t++) {
        uint32_t lastpg = tab[t].has ? tab[t].numbers.back() : uint32_t(1 + 2 * t);
        put32(head, 28 + 16 * t, uint32_t(t));
        put32(head, 32 + 16 * t, empty_cand[t]);
        put32(head, 36 + 16 * t, uint32_t(1 + 2 * t));
        put32(head, 40 + 16 * t, lastpg);
    }
    return total;
}

}  // namespace

// Per table t (0..19): rows[t] / lens[t] / counts[t] the row blobs back to back and their
// lengths, stat[t] a finished 4096 byte data page or null, shifted[t] non zero for the
// tables whose rows carry the 0x20 stride. Writes the file to out when cap is big enough.
// Returns its size, 0 when a row does not fit in a page.
TB_API int64_t tb_pdb_build(const uint8_t* const* rows, const uint32_t* const* lens,
                            const uint32_t* counts, const uint8_t* const* stat,
                            const uint8_t* shifted, uint8_t* out, int64_t cap) {
    std::vector<Source> src(N_TABLES);
    for (int t = 0; t < N_TABLES; t++) {
        src[t].stat = stat[t];
        src[t].shifted = shifted[t] != 0;
        if (stat[t] || !counts[t]) continue;
        const uint8_t* p = rows[t];
        for (uint32_t i = 0; i < counts[t]; i++) {
            src[t].rows.push_back({p, lens[t][i]});
            p += lens[t][i];
        }
    }
    return build_file(src, out, cap);
}

#include "rows.inc"
#include "anlz.inc"
#include "anlz_build.inc"

// ============================================================
// Waveform bands
// ============================================================

// Mono and 1/FOLD rate in one pass: the sum of w consecutive samples, in the same order
// and float precision as the numpy version, then times 1/w. Returns the sample count.
TB_API int64_t tb_fold(const float* y, int64_t len, int32_t w, float* out) {
    if (w <= 0) return 0;
    int64_t n = len / w;
    float inv = float(1.0 / w);
    for (int64_t i = 0; i < n; i++) {
        const float* a = y + i * w;
        float s = a[0];
        for (int32_t k = 1; k < w; k++) s += a[k];
        out[i] = s * inv;
    }
    return n;
}

namespace {

// second order section, direct form II transposed, the layout scipy.signal.sosfilt uses
struct Biquad {
    double b0, b1, b2, a1, a2, z0 = 0, z1 = 0;
    explicit Biquad(const double* s) : b0(s[0]), b1(s[1]), b2(s[2]), a1(s[4]), a2(s[5]) {}
    inline double run(double x) {
        double y = b0 * x + z0;
        z0 = b1 * x - a1 * y + z1;
        z1 = b2 * x - a2 * y;
        return y;
    }
};

}  // namespace

// Peak |value| of the low, mid and high band for every column, normalised on the loudest
// of the three. y: mono signal, lo / hi: one section each (6 doubles, b0 b1 b2 a0 a1 a2).
// Column c covers samples [c*per, (c+1)*per) with per = len / cols, the tail is dropped.
// Returns 0 when the arguments cannot work.
TB_API int32_t tb_bands(const float* y, int64_t len, const double* lo, const double* hi,
                        int64_t cols, float* out_lo, float* out_mid, float* out_high) {
    if (cols <= 0 || len < cols) return 0;
    int64_t per = len / cols;
    Biquad f_lo(lo), f_hi(hi);
    float top = 0.0f;
    for (int64_t c = 0; c < cols; c++) {
        float pl = 0, pm = 0, ph = 0;
        for (int64_t i = c * per, e = i + per; i < e; i++) {
            float x = y[i];
            float l = float(f_lo.run(double(x)));
            float h = float(f_hi.run(double(x)));
            float m = x - l - h;
            float al = std::fabs(l), am = std::fabs(m), ah = std::fabs(h);
            if (al > pl) pl = al;
            if (am > pm) pm = am;
            if (ah > ph) ph = ah;
        }
        out_lo[c] = pl;
        out_mid[c] = pm;
        out_high[c] = ph;
        if (pl > top) top = pl;
        if (pm > top) top = pm;
        if (ph > top) top = ph;
    }
    if (top == 0.0f) top = 1.0f;
    for (int64_t c = 0; c < cols; c++) {
        float a = out_lo[c] / top, b = out_mid[c] / top, d = out_high[c] / top;
        out_lo[c] = a > 1.0f ? 1.0f : a;
        out_mid[c] = b > 1.0f ? 1.0f : b;
        out_high[c] = d > 1.0f ? 1.0f : d;
    }
    return 1;
}

TB_API int32_t tb_version() { return 2; }
