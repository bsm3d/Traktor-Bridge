// Benoit Saint-Moulin
// Traktor Bridge : native core, ANLZ cue sections and the two files
// Included by tbcore.cpp after anlz.inc.

extern "C" {

struct TbWave {
    const float* low;
    const float* mid;
    const float* high;
    int64_t n;
};

struct TbCue {
    int32_t hotcue;
    double start, length;
    uint32_t name_off, name_len;       // UTF-8 slice of the names blob, already stripped
    uint32_t color_id, rgb;            // rekordbox colour id 1-8 (0 none) and its 0xRRGGBB
};

}

namespace {

uint32_t cue_slot(const TbCue& c) { return c.hotcue >= 0 ? uint32_t(c.hotcue) + 1 : 0; }

Out pcpt(const TbCue& c) {
    bool loop = c.length > 0;
    Out o;
    tag4(o, HS("PCPT"));
    be32(o, 28); be32(o, 56); be32(o, cue_slot(c)); be32(o, 0); be32(o, 0x10000);
    be16(o, 0xFFFF); be16(o, 0xFFFF);
    o.push_back(loop ? 2 : 1); o.push_back(0);
    be16(o, 1000);
    be32(o, round_even(c.start > 0 ? c.start : 0.0));
    be32(o, loop ? round_even(c.start + c.length) : 0xFFFFFFFFu);
    zeros(o, 16);
    return o;
}

Out pcp2(const TbCue& c, const char* names) {
    bool loop = c.length > 0;
    Out com;
    if (c.name_len) {
        Out raw;
        const uint8_t* p = reinterpret_cast<const uint8_t*>(names + c.name_off);
        uint32_t len = c.name_len;
        for (uint32_t i = 0; i < len;) {
            uint32_t ch = p[i], need = 0;
            if (ch < 0x80) need = 0;
            else if ((ch >> 5) == 6) { ch &= 0x1F; need = 1; }
            else if ((ch >> 4) == 14) { ch &= 0x0F; need = 2; }
            else if ((ch >> 3) == 30) { ch &= 0x07; need = 3; }
            else throw Failure();
            for (uint32_t k = 1; k <= need; k++) {
                if (i + k >= len || (p[i + k] & 0xC0) != 0x80) throw Failure();
                ch = (ch << 6) | (p[i + k] & 0x3F);
            }
            i += need + 1;
            if (ch >= 0x10000) {
                ch -= 0x10000;
                be16(raw, 0xD800 + (ch >> 10));
                be16(raw, 0xDC00 + (ch & 0x3FF));
            } else {
                be16(raw, ch);
            }
        }
        be16(raw, 0);
        com = raw;
    }
    Out o;
    tag4(o, HS("PCP2"));
    be32(o, 16); be32(o, uint32_t(0x2C + com.size() + 4)); be32(o, cue_slot(c));
    o.push_back(loop ? 2 : 1); o.push_back(0);
    be16(o, 1000);
    be32(o, round_even(c.start > 0 ? c.start : 0.0));
    be32(o, loop ? round_even(c.start + c.length) : 0);
    o.push_back(uint8_t(c.color_id)); zeros(o, 7);
    be16(o, 0); be16(o, 0); be32(o, uint32_t(com.size()));
    o.insert(o.end(), com.begin(), com.end());
    o.push_back(0); o.push_back(uint8_t(c.rgb >> 16)); o.push_back(uint8_t(c.rgb >> 8)); o.push_back(uint8_t(c.rgb));
    return o;
}

// hot cues first (kind 1), then the memory cues (kind 0)
std::vector<Out> cue_lists(const TbCue* hot, uint32_t nhot, const TbCue* mem, uint32_t nmem,
                           const char* names, bool ext) {
    std::vector<Out> out;
    for (int pass = 0; pass < 2; pass++) {
        const TbCue* cues = pass == 0 ? hot : mem;
        uint32_t n = pass == 0 ? nhot : nmem;
        uint32_t kind = pass == 0 ? 1 : 0;
        Out head, data;
        if (ext) {
            be32(head, kind); be16(head, n); be16(head, 0);
            for (uint32_t i = 0; i < n; i++) {
                Out c = pcp2(cues[i], names);
                data.insert(data.end(), c.begin(), c.end());
            }
            out.push_back(section(HS("PCO2"), head, data));
        } else {
            be32(head, kind); be16(head, 0); be16(head, n); be32(head, 0xFFFFFFFFu);
            for (uint32_t i = 0; i < n; i++) {
                Out c = pcpt(cues[i]);
                data.insert(data.end(), c.begin(), c.end());
            }
            out.push_back(section(HS("PCOB"), head, data));
        }
    }
    return out;
}

void append(std::vector<Out>& v, const std::vector<Out>& more) { v.insert(v.end(), more.begin(), more.end()); }

}  // namespace

// Both files of a track. wave: the detail resolution, w400 / w100 / w1200 the other ones.
// sizes[0] and sizes[1] get the sizes of the DAT and the EXT, the files are written to
// dat / ext when they fit. Returns 0 on success, -1 for a value out of range.
TB_API int32_t tb_anlz_build(const char* path, uint32_t path_len, double bpm, double duration,
                             double anchor, uint32_t frames, const TbCue* hot, uint32_t nhot,
                             const TbCue* mem, uint32_t nmem, const char* names,
                             const TbWave* detail, const TbWave* w400, const TbWave* w100,
                             const TbWave* w1200, uint8_t* dat, int64_t dat_cap, uint8_t* ext,
                             int64_t ext_cap, int64_t* sizes) {
    try {
        Wave d = {detail->low, detail->mid, detail->high, detail->n};
        Wave a = {w400->low, w400->mid, w400->high, w400->n};
        Wave b = {w100->low, w100->mid, w100->high, w100->n};
        Wave c = {w1200->low, w1200->mid, w1200->high, w1200->n};

        std::vector<Out> dsec = {ppth(path, path_len), pvbr(frames), pqtz(bpm, duration, anchor), pwav(a), pwv2(b)};
        append(dsec, cue_lists(hot, nhot, mem, nmem, names, false));
        Out dfile = pmai(dsec);

        std::vector<Out> esec = {ppth(path, path_len), pwv3(d)};
        append(esec, cue_lists(hot, nhot, mem, nmem, names, false));
        append(esec, cue_lists(hot, nhot, mem, nmem, names, true));
        esec.push_back(pwv5(d));
        esec.push_back(pwv4(c));
        Out efile = pmai(esec);

        sizes[0] = int64_t(dfile.size());
        sizes[1] = int64_t(efile.size());
        if (dat_cap >= sizes[0]) std::memcpy(dat, dfile.data(), dfile.size());
        if (ext_cap >= sizes[1]) std::memcpy(ext, efile.data(), efile.size());
        return 0;
    } catch (...) {
        return -1;
    }
}
