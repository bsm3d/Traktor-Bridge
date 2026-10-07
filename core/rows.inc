// Benoit Saint-Moulin
// Traktor Bridge : native core, export.pdb rows (what pdbwrite.py builds)
// Included by tbcore.cpp, after build_file.

namespace {

typedef std::vector<uint8_t> Bytes;

// UTF-8 to UTF-16 little endian, surrogate pairs above the BMP like Python's utf-16-le
bool utf16le(const char* s, uint32_t n, Bytes& out) {
    const uint8_t* p = reinterpret_cast<const uint8_t*>(s);
    for (uint32_t i = 0; i < n;) {
        uint32_t c = p[i], need = 0;
        if (c < 0x80) need = 0;
        else if ((c >> 5) == 6) { c &= 0x1F; need = 1; }
        else if ((c >> 4) == 14) { c &= 0x0F; need = 2; }
        else if ((c >> 3) == 30) { c &= 0x07; need = 3; }
        else return false;
        for (uint32_t k = 1; k <= need; k++) {
            if (i + k >= n || (p[i + k] & 0xC0) != 0x80) return false;
            c = (c << 6) | (p[i + k] & 0x3F);
        }
        i += need + 1;
        if (c >= 0x10000) {
            c -= 0x10000;
            uint32_t hi = 0xD800 + (c >> 10), lo = 0xDC00 + (c & 0x3FF);
            out.push_back(uint8_t(hi)); out.push_back(uint8_t(hi >> 8));
            out.push_back(uint8_t(lo)); out.push_back(uint8_t(lo >> 8));
        } else {
            out.push_back(uint8_t(c)); out.push_back(uint8_t(c >> 8));
        }
    }
    return true;
}

bool is_ascii(const char* s, uint32_t n) {
    for (uint32_t i = 0; i < n; i++)
        if (uint8_t(s[i]) >= 0x80) return false;
    return true;
}

struct Failure {};     // thrown inside the builders, caught at the C boundary

// A fixed part followed by strings, long strings on a 4 byte boundary
struct RowB {
    Bytes buf;
    explicit RowB(size_t fixed) : buf(fixed, 0) {}
    void w8(size_t o, uint32_t v) { buf[o] = uint8_t(v); }
    void w16(size_t o, uint32_t v) { put16(buf.data(), o, v); }
    void w32(size_t o, uint32_t v) { put32(buf.data(), o, v); }
    // position of the string, as the offset the row stores
    uint32_t put(const char* s, uint32_t n) {
        Bytes b;
        bool is_long = false;
        if (n == 0) {
            b.push_back(0x03);
        } else if (is_ascii(s, n)) {
            if (n <= 126) {
                b.push_back(uint8_t(((n + 1) << 1) | 1));
                b.insert(b.end(), s, s + n);
            } else {
                is_long = true;
                if (n + 4 > 0xFFFF) throw Failure();
                b.push_back(0x40); b.push_back(uint8_t(n + 4)); b.push_back(uint8_t((n + 4) >> 8)); b.push_back(0);
                b.insert(b.end(), s, s + n);
            }
        } else {
            is_long = true;
            Bytes raw;
            if (!utf16le(s, n, raw) || raw.size() + 4 > 0xFFFF) throw Failure();
            b.push_back(0x90); b.push_back(uint8_t(raw.size() + 4)); b.push_back(uint8_t((raw.size() + 4) >> 8)); b.push_back(0);
            b.insert(b.end(), raw.begin(), raw.end());
        }
        if (is_long)
            while (buf.size() % 4) buf.push_back(0);
        uint32_t pos = uint32_t(buf.size());
        buf.insert(buf.end(), b.begin(), b.end());
        return pos;
    }
    Bytes done() {
        while (buf.size() % 4) buf.push_back(0);
        return buf;
    }
};

inline uint32_t u32of(double v) {
    if (!(v >= 0) || v > 4294967295.0) throw Failure();
    return uint32_t(v);
}

// Python's round(): half to even, which is what nearbyint does in the default mode
inline uint32_t round_even(double v) { return u32of(std::nearbyint(v)); }

// name -> id in order of first use, the way rekordbox numbers them
struct Lookup {
    std::vector<std::string> names;
    std::vector<uint32_t> owners;      // album artist id, albums only
    std::unordered_map<std::string, uint32_t> ids;
    uint32_t get(const std::string& key, uint32_t owner = 0, bool owned = false) {
        if (key.empty()) return 0;
        std::string k = owned ? key + '\0' + std::to_string(owner) : key;
        auto it = ids.find(k);
        if (it != ids.end()) return it->second;
        uint32_t id = uint32_t(ids.size()) + 1;
        ids.emplace(k, id);
        names.push_back(key);
        owners.push_back(owner);
        return id;
    }
};

std::string color_name(int i) {
    switch (i) {
        case 0: return HS("Pink");
        case 1: return HS("Red");
        case 2: return HS("Orange");
        case 3: return HS("Yellow");
        case 4: return HS("Green");
        case 5: return HS("Aqua");
        case 6: return HS("Blue");
        default: return HS("Purple");
    }
}

Bytes id_name(uint32_t i, const std::string& name) {
    RowB r(4);
    r.w32(0, i);
    r.put(name.data(), uint32_t(name.size()));
    return r.done();
}

enum { S_TITLE, S_ARTIST, S_ALBUM_ARTIST, S_ALBUM, S_GENRE, S_LABEL, S_REMIXER, S_COMPOSER,
       S_COMMENT, S_KEY, S_ADDED, S_PATH, S_ANLZ, S_BASE };

}  // namespace

extern "C" {

struct TbTrack {
    uint32_t id, art, size, samplerate, bitrate, track_no, disc_no, plays, year, color, rating, ftype;
    double bpm, duration;
    uint32_t off[14], len[14];
};

struct TbNode {
    uint32_t parent, sort, id, folder, off, len;
};

struct TbEntry {
    uint32_t pos, tid, me;
};

}

// The whole export.pdb from flat track and playlist arrays. Strings are UTF-8 slices of
// blob. today: the date string. stat: the 20 static pages or null. Returns the size, 0
// when a row does not fit in a page, -1 when a value is out of range or a string cannot
// be written.
TB_API int64_t tb_pdb_write(const TbTrack* tr, uint32_t ntr, const char* blob, const char* today,
                            uint32_t today_len, const TbNode* nodes, uint32_t nnodes,
                            const TbEntry* entries, uint32_t nentries,
                            const uint8_t* const* stat, uint8_t* out, int64_t cap) {
    try {
        auto str = [&](uint32_t off, uint32_t len) { return std::string(blob + off, len); };
        std::string today_s(today, today_len);
        Lookup artists, albums, genres, labels, keysl;
        std::vector<Bytes> track_rows;
        std::vector<uint32_t> art_ids;

        for (uint32_t n = 0; n < ntr; n++) {
            const TbTrack& t = tr[n];
            auto S = [&](int k) { return str(t.off[k], t.len[k]); };
            uint32_t a = artists.get(S(S_ARTIST));
            uint32_t aa = artists.get(S(S_ALBUM_ARTIST));
            if (!aa) aa = a;
            std::string album_name = S(S_ALBUM);
            uint32_t album = album_name.empty() ? 0 : albums.get(album_name, aa, true);
            uint32_t genre = genres.get(S(S_GENRE));
            uint32_t label = labels.get(S(S_LABEL));
            uint32_t remixer = artists.get(S(S_REMIXER));
            uint32_t composer = artists.get(S(S_COMPOSER));
            uint32_t key = keysl.get(S(S_KEY));

            uint32_t secs = round_even(t.duration);
            if (t.disc_no > 0xFFFF || t.plays > 0xFFFF || t.year > 0xFFFF || t.color > 0xFF
                || t.ftype > 0xFFFF || secs > 0xFFFF)
                throw Failure();
            RowB r(0x88);
            r.w16(0x00, 0x24); r.w16(0x02, 0);
            r.w32(0x04, K32(0x000C0700)); r.w32(0x08, t.samplerate); r.w32(0x0c, composer);
            r.w32(0x10, t.size); r.w32(0x14, 0); r.w32(0x18, K32(0xC25930BF));
            r.w32(0x1c, t.art); r.w32(0x20, key); r.w32(0x24, 0); r.w32(0x28, label);
            r.w32(0x2c, remixer); r.w32(0x30, t.bitrate);
            r.w32(0x34, t.track_no); r.w32(0x38, round_even(t.bpm * 100)); r.w32(0x3c, genre);
            r.w32(0x40, album); r.w32(0x44, a); r.w32(0x48, t.id);
            r.w16(0x4c, t.disc_no); r.w16(0x4e, t.plays); r.w16(0x50, t.year); r.w16(0x52, 16);
            r.w16(0x54, secs); r.w16(0x56, 41);
            r.w8(0x58, t.color); r.w8(0x59, t.rating < 5 ? t.rating : 5);
            r.w16(0x5a, t.ftype); r.w16(0x5c, 3);

            std::string added = S(S_ADDED);
            if (added.empty()) added = today_s;
            std::string strs[21] = {"", "", HS("2"), HS("2"), "", "", HS("ON"), HS("ON"), "", "", added, "", "", "",
                                    S(S_ANLZ), today_s, S(S_COMMENT), S(S_TITLE), "", S(S_BASE), S(S_PATH)};
            for (int i = 0; i < 21; i++) {
                uint32_t pos = r.put(strs[i].data(), uint32_t(strs[i].size()));
                if (pos > 0xFFFF) throw Failure();
                r.w16(0x5e + 2 * i, pos);
            }
            track_rows.push_back(r.done());
            if (t.art) art_ids.push_back(t.art);
        }
        std::sort(art_ids.begin(), art_ids.end());
        art_ids.erase(std::unique(art_ids.begin(), art_ids.end()), art_ids.end());

        std::vector<Bytes> genre_rows, artist_rows, album_rows, label_rows, key_rows, color_rows,
            art_rows, tree_rows, entry_rows;
        for (size_t i = 0; i < genres.names.size(); i++) genre_rows.push_back(id_name(uint32_t(i + 1), genres.names[i]));
        for (size_t i = 0; i < labels.names.size(); i++) label_rows.push_back(id_name(uint32_t(i + 1), labels.names[i]));
        for (size_t i = 0; i < artists.names.size(); i++) {
            RowB r(10);
            r.w16(0, 0x60); r.w16(2, 0); r.w32(4, uint32_t(i + 1)); r.w8(8, 3); r.w8(9, 0);
            uint32_t pos = r.put(artists.names[i].data(), uint32_t(artists.names[i].size()));
            if (pos > 0xFF) throw Failure();
            r.w8(9, pos);
            artist_rows.push_back(r.done());
        }
        for (size_t i = 0; i < albums.names.size(); i++) {
            RowB r(22);
            r.w16(0, 0x80); r.w16(2, 0); r.w32(4, 0); r.w32(8, albums.owners[i]); r.w32(12, uint32_t(i + 1));
            r.w32(16, 0); r.w8(20, 3); r.w8(21, 0);
            uint32_t pos = r.put(albums.names[i].data(), uint32_t(albums.names[i].size()));
            if (pos > 0xFF) throw Failure();
            r.w8(21, pos);
            album_rows.push_back(r.done());
        }
        for (size_t i = 0; i < keysl.names.size(); i++) {
            RowB r(8);
            r.w32(0, uint32_t(i + 1)); r.w32(4, uint32_t(i + 1));
            r.put(keysl.names[i].data(), uint32_t(keysl.names[i].size()));
            key_rows.push_back(r.done());
        }
        for (int i = 0; i < 8; i++) {
            RowB r(8);
            r.w32(0, 0); r.w8(4, uint32_t(i + 1)); r.w16(5, uint32_t(i + 1)); r.w8(7, 0);
            std::string cn = color_name(i);
            r.put(cn.data(), uint32_t(cn.size()));
            color_rows.push_back(r.done());
        }
        for (uint32_t a : art_ids)
            art_rows.push_back(id_name(a, HS("/PIONEER/Artwork/00001/a") + std::to_string(a) + HS(".jpg")));
        for (uint32_t i = 0; i < nnodes; i++) {
            const TbNode& n = nodes[i];
            RowB r(20);
            r.w32(0, n.parent); r.w32(4, 0); r.w32(8, n.sort); r.w32(12, n.id); r.w32(16, n.folder ? 1 : 0);
            r.put(blob + n.off, n.len);
            tree_rows.push_back(r.done());
        }
        for (uint32_t i = 0; i < nentries; i++) {
            Bytes b(12, 0);
            put32(b.data(), 0, entries[i].pos);
            put32(b.data(), 4, entries[i].tid);
            put32(b.data(), 8, entries[i].me);
            entry_rows.push_back(b);
        }

        // kinds: TRACKS 0, GENRES 1, ARTISTS 2, ALBUMS 3, LABELS 4, KEYS 5, COLORS 6,
        // PL_TREE 7, PL_ENTRIES 8, ARTWORK 13
        std::vector<Source> src(N_TABLES);
        auto add = [&](int kind, const std::vector<Bytes>& rows) {
            for (const Bytes& b : rows) src[kind].rows.push_back({b.data(), uint32_t(b.size())});
        };
        add(0, track_rows); add(1, genre_rows); add(2, artist_rows); add(3, album_rows);
        add(4, label_rows); add(5, key_rows); add(6, color_rows); add(7, tree_rows);
        add(8, entry_rows); add(13, art_rows);
        src[0].shifted = src[2].shifted = src[3].shifted = true;
        for (int t = 0; t < N_TABLES; t++) src[t].stat = stat[t];
        return build_file(src, out, cap);
    } catch (...) {
        return -1;
    }
}
