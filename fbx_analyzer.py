#!/usr/bin/env python3
"""
FBX Binary Format Analyzer for UE5 files - Ultra-optimized v4.
Never decompresses array data. Gets keyframe counts from array headers only.
"""

import struct
import zlib
import sys
import time
from collections import defaultdict

FBX_MAGIC = b"Kaydara FBX Binary  \x00\x1a\x00"

class FBXAnalyzer:
    def __init__(self, filepath):
        with open(filepath, "rb") as f:
            self.data = f.read()
        self.version = struct.unpack_from('<I', self.data, 23)[0]
        self.root = self._parse_tree(27, len(self.data))

    def _parse_tree(self, start, end):
        data = self.data
        pos = start
        children = []
        while pos < end:
            if pos + 13 > len(data): break
            end_off, num_props, prop_list_len, name_len = struct.unpack_from('<IIIB', data, pos)
            if end_off == 0 and num_props == 0 and prop_list_len == 0 and name_len == 0: break
            name = data[pos+13:pos+13+name_len].decode('ascii', errors='replace') if name_len > 0 else ''
            props_start = pos + 13 + name_len
            children_start = props_start + prop_list_len
            sub = self._parse_tree(children_start, end_off) if children_start < end_off else []
            children.append({'name': name, 'end': end_off, 'nprops': num_props,
                           'plen': prop_list_len, 'pstart': props_start, 'ch': sub})
            pos = end_off
        return children

    def _read_prop_at(self, pos):
        """Read a single property, return (type_code, value, next_pos). Arrays return count only."""
        data = self.data
        tc = chr(data[pos]); pos += 1
        if tc == 'Y': return 'Y', struct.unpack_from('<H', data, pos)[0], pos+2
        elif tc == 'C': return 'C', bool(data[pos]), pos+1
        elif tc == 'I': return 'I', struct.unpack_from('<i', data, pos)[0], pos+4
        elif tc == 'F': return 'F', struct.unpack_from('<f', data, pos)[0], pos+4
        elif tc == 'D': return 'D', struct.unpack_from('<d', data, pos)[0], pos+8
        elif tc == 'L': return 'L', struct.unpack_from('<q', data, pos)[0], pos+8
        elif tc == 'S':
            ln = struct.unpack_from('<I', data, pos)[0]; pos += 4
            try: v = data[pos:pos+ln].decode('utf-8', errors='replace')
            except: v = data[pos:pos+ln]
            return 'S', v, pos+ln
        elif tc == 'R':
            ln = struct.unpack_from('<I', data, pos)[0]; pos += 4
            return 'R', data[pos:pos+ln], pos+ln
        elif tc in ('f', 'd', 'l', 'i', 'b'):
            count, encoding, comp_len = struct.unpack_from('<III', data, pos); pos += 12
            # Skip the compressed/raw data entirely, just return count
            return tc, f"array<{count},{encoding},{comp_len}>", pos + comp_len
        else:
            raise ValueError(f'Unknown type: {tc} at {pos-1}')

    def get_props(self, node):
        """Parse all properties for a node. Arrays return metadata strings."""
        pos = node['pstart']
        num = node['nprops']
        props = []
        for _ in range(num):
            tc, val, pos = self._read_prop_at(pos)
            props.append((tc, val))
        return props

    def get_prop_array_count(self, node, prop_index):
        """Get the count of an array property without decompressing."""
        data = self.data
        pos = node['pstart']
        for i in range(prop_index + 1):
            tc = chr(data[pos]); pos += 1
            if tc in ('Y',): pos += 2
            elif tc in ('C',): pos += 1
            elif tc in ('I', 'F'): pos += 4
            elif tc in ('D', 'L'): pos += 8
            elif tc in ('S', 'R'):
                ln = struct.unpack_from('<I', data, pos)[0]; pos += 4 + ln
            elif tc in ('f', 'd', 'l', 'i', 'b'):
                if i == prop_index:
                    count = struct.unpack_from('<I', data, pos)[0]
                    return count
                _, _, comp_len = struct.unpack_from('<III', data, pos); pos += 12 + comp_len
            else:
                raise ValueError(f'Unknown type: {tc}')
        return 0

    def find(self, nodes, name):
        for n in nodes:
            if n['name'] == name: return n
        return None

    def find_all(self, nodes, name):
        return [n for n in nodes if n['name'] == name]


def pv(props, i, default=None):
    if i < len(props): return props[i][1]
    return default

def cn(s):
    if isinstance(s, str) and "::" in s:
        return s.split("::")[-1]
    return s or ""


def analyze(filepath):
    t0 = time.time()
    print(f"\n{'#'*80}")
    print(f"# ANALYZING: {filepath}")
    print(f"{'#'*80}")

    a = FBXAnalyzer(filepath)
    root = a.root
    print(f"  FBX Version: {a.version} | Records: {sum(1 for _ in iter_records(root))} | Parse time: {time.time()-t0:.2f}s")

    # A) Top-level structure
    print(f"\n{'='*60}")
    print("A) TOP-LEVEL STRUCTURE")
    print(f"{'='*60}")
    for top in root:
        ctypes = defaultdict(int)
        for c in top['ch']:
            ctypes[c['name']] += 1
        print(f"  [{top['name']}] → {len(top['ch'])} children: {dict(ctypes)}")

    # B) Objects
    print(f"\n{'='*60}")
    print("B) OBJECTS SECTION")
    print(f"{'='*60}")
    objects = a.find(root, "Objects")
    if not objects:
        print("  No Objects!")
        return

    tc = defaultdict(int)
    for c in objects['ch']:
        tc[c['name']] += 1
    print(f"  Object type counts: {dict(tc)}")

    models = a.find_all(objects['ch'], "Model")
    deformers = a.find_all(objects['ch'], "Deformer")
    anim_stacks = a.find_all(objects['ch'], "AnimationStack")
    anim_layers = a.find_all(objects['ch'], "AnimationLayer")
    anim_curve_nodes = a.find_all(objects['ch'], "AnimationCurveNode")
    anim_curves = a.find_all(objects['ch'], "AnimationCurve")

    # Models (bones)
    print(f"\n  ── Models: {len(models)} ──")
    bone_info = {}
    for m in models:
        p = a.get_props(m)
        nid = pv(p, 0)
        fname = pv(p, 1, "")
        mtype = pv(p, 2, "")
        name = cn(fname)
        lcl_t = lcl_r = None
        p70 = a.find(m['ch'], "Properties70")
        if p70:
            for pc in a.find_all(p70['ch'], "P"):
                pp = a.get_props(pc)
                pn = pv(pp, 0, "")
                if pn == "Lcl Translation" and len(pp) >= 7:
                    lcl_t = (pv(pp, 4), pv(pp, 5), pv(pp, 6))
                elif pn == "Lcl Rotation" and len(pp) >= 7:
                    lcl_r = (pv(pp, 4), pv(pp, 5), pv(pp, 6))
        bone_info[nid] = {"name": name, "type": mtype, "lcl_t": lcl_t, "lcl_r": lcl_r}

    # Print only LimbNode and Root types (actual bones)
    for nid, info in sorted(bone_info.items(), key=lambda x: (0 if x[1]['type'] in ('LimbNode','Root') else 1, x[1]['type'], x[1]['name'])):
        if info['type'] in ('LimbNode', 'Root'):
            t = f"T=({info['lcl_t'][0]:.4f},{info['lcl_t'][1]:.4f},{info['lcl_t'][2]:.4f})" if info['lcl_t'] else ""
            r = f"R=({info['lcl_r'][0]:.4f},{info['lcl_r'][1]:.4f},{info['lcl_r'][2]:.4f})" if info['lcl_r'] else ""
            print(f"    ID={nid} \"{info['name']}\" [{info['type']}] {t} {r}")
    # Summary for other types
    other_types = defaultdict(int)
    for nid, info in bone_info.items():
        if info['type'] not in ('LimbNode', 'Root'):
            other_types[f"{info['type']}:{info['name']}"] += 1
    if other_types:
        print(f"    Other models: {dict(other_types)}")

    # Deformers - just summary
    print(f"\n  ── Deformers: {len(deformers)} ──")
    dtype_counts = defaultdict(int)
    for d in deformers:
        p = a.get_props(d)
        dtype_counts[pv(p, 2, "?")] += 1
    print(f"    Types: {dict(dtype_counts)}")

    # AnimationStack
    print(f"\n  ── AnimationStack: {len(anim_stacks)} ──")
    for s in anim_stacks:
        p = a.get_props(s)
        nid = pv(p, 0)
        name = cn(pv(p, 1, ""))
        print(f"    ID={nid} \"{name}\"")
        p70 = a.find(s['ch'], "Properties70")
        if p70:
            for pc in a.find_all(p70['ch'], "P"):
                pp = a.get_props(pc)
                pn = pv(pp, 0, "")
                if pn in ("LocalStart", "LocalStop", "ReferenceStart", "ReferenceStop"):
                    print(f"      {pn} = {pv(pp, 4, '')}")

    # AnimationLayer
    print(f"\n  ── AnimationLayer: {len(anim_layers)} ──")
    for l in anim_layers:
        p = a.get_props(l)
        nid = pv(p, 0)
        name = cn(pv(p, 1, ""))
        print(f"    ID={nid} \"{name}\"")

    # AnimationCurveNode
    print(f"\n  ── AnimationCurveNode: {len(anim_curve_nodes)} ──")
    curve_node_map = {}
    for cn_rec in anim_curve_nodes:
        p = a.get_props(cn_rec)
        nid = pv(p, 0)
        cname = cn(pv(p, 1, ""))
        ctype = pv(p, 2, "")
        curve_node_map[nid] = {"name": cname, "type": ctype, "id": nid}
        extra = ""
        p70 = a.find(cn_rec['ch'], "Properties70")
        if p70:
            for pc in a.find_all(p70['ch'], "P"):
                pp = a.get_props(pc)
                pn = pv(pp, 0, "")
                p4 = pv(pp, 4, "")
                if p4 != "": extra += f" {pn}={p4}"
        print(f"    ID={nid} \"{cname}\" [{ctype}]{extra}")

    # AnimationCurve - get keyframe count from KeyTime child's first array prop
    print(f"\n  ── AnimationCurve: {len(anim_curves)} ──")
    curve_map = {}
    for c in anim_curves:
        p = a.get_props(c)
        nid = pv(p, 0)
        cname = cn(pv(p, 1, ""))

        # Get keyframe count by looking at KeyTime child's array count
        num_kf = 0
        for child in c['ch']:
            if child['name'] == "KeyTime":
                # KeyTime has one 'd' array prop. Read just the count from the header.
                if child['nprops'] > 0:
                    # Array header: type_byte(1) + count(4) + encoding(4) + comp_len(4)
                    # type byte at pstart
                    arr_type = chr(a.data[child['pstart']])
                    if arr_type == 'd':
                        count = struct.unpack_from('<I', a.data, child['pstart'] + 1)[0]
                        num_kf = count
                break

        curve_map[nid] = {"name": cname, "num_kf": num_kf, "id": nid}
        if num_kf > 0:
            print(f"    ID={nid} \"{cname}\" keyframes={num_kf}")
        else:
            print(f"    ID={nid} \"{cname}\" keyframes=0")

    # C) Connections
    print(f"\n{'='*60}")
    print("C) CONNECTIONS SECTION")
    print(f"{'='*60}")
    connections = a.find(root, "Connections")
    c_records = a.find_all(connections['ch'], "C") if connections else []
    print(f"  Total connections: {len(c_records)}")

    child_to_parent = defaultdict(list)
    parent_to_child = defaultdict(list)
    conn_types = defaultdict(int)
    for c in c_records:
        p = a.get_props(c)
        ctype = pv(p, 0, "")
        from_id = pv(p, 1)
        to_id = pv(p, 2)
        pname = pv(p, 3, "")
        conn_types[ctype] += 1
        child_to_parent[from_id].append((to_id, pname))
        parent_to_child[to_id].append((from_id, pname))

    print(f"  Connection types: {dict(conn_types)}")
    op_props = sorted(set(pv(a.get_props(c), 3, "") for c in c_records if pv(a.get_props(c), 0, "") == "OP"))
    print(f"  OP property names: {op_props}")

    model_map = {pv(a.get_props(m), 0): cn(pv(a.get_props(m), 1, "")) for m in models}

    # D) Pose
    print(f"\n{'='*60}")
    print("D) POSE SECTION")
    print(f"{'='*60}")
    poses = a.find_all(objects['ch'], "Pose")
    print(f"  Pose records: {len(poses)}")
    for p in poses:
        pp = a.get_props(p)
        nid = pv(pp, 0)
        pname = pv(pp, 1, "")
        ptype = pv(pp, 2, "")
        pose_nodes = a.find_all(p['ch'], "PoseNode")
        print(f"    ID={nid} \"{pname}\" Type={ptype} PoseNodes={len(pose_nodes)}")
        # Show a few example pose node IDs
        for pn in pose_nodes[:2]:
            pnp = a.get_props(pn)
            pn_node = pv(pnp, 0)
            # Find bone name from model_map
            bname = model_map.get(pn_node, "?")
            print(f"      Node={pn_node} ({bname})")
        if len(pose_nodes) > 2:
            print(f"      ... +{len(pose_nodes)-2} more")

    # E) GlobalSettings
    print(f"\n{'='*60}")
    print("E) GLOBALSETTINGS")
    print(f"{'='*60}")
    gs = a.find(root, "GlobalSettings")
    if gs:
        p70 = a.find(gs['ch'], "Properties70")
        if p70:
            for pc in a.find_all(p70['ch'], "P"):
                pp = a.get_props(pc)
                pn = pv(pp, 0, "")
                ptype = pv(pp, 1, "")
                vals = []
                for i in range(4, len(pp)):
                    v = pp[i][1]
                    vals.append(f"{v:.6f}" if isinstance(v, float) else str(v))
                print(f"    {pn} ({ptype}) = {', '.join(vals)}")

    # F) Animation Details
    print(f"\n{'='*60}")
    print("F) ANIMATION DATA DETAILS")
    print(f"{'='*60}")
    if not anim_curve_nodes:
        print("  No animation data (skeleton only)")
    else:
        bone_cns = defaultdict(list)
        for cn_id, cn_info in curve_node_map.items():
            for pid, pn in child_to_parent.get(cn_id, []):
                if pid in model_map:
                    bone_cns[pid].append({"cn_id": cn_id, "cn_name": cn_info["name"],
                                          "cn_type": cn_info["type"], "prop": pn})

        print(f"\n  Bones with animation: {len(bone_cns)}")
        for mid in sorted(bone_cns.keys(), key=lambda x: model_map.get(x, "")):
            bname = model_map.get(mid, f"?{mid}")
            cns = bone_cns[mid]
            print(f"\n    Bone \"{bname}\" (ID={mid}): {len(cns)} CurveNodes")
            for c in cns:
                curves = []
                for cid, cpn in parent_to_child.get(c["cn_id"], []):
                    if cid in curve_map:
                        curves.append(f"\"{curve_map[cid]['name']}\"({curve_map[cid]['num_kf']}kf via \"{cpn}\")")
                pstr = f"via \"{c['prop']}\"" if c['prop'] else "via OO"
                print(f"      AnimCurveNode \"{c['cn_name']}\" [{c['cn_type']}] {pstr}")
                for cs in curves:
                    print(f"        ← {cs}")

        print(f"\n  ── Structure Pattern ──")
        ctm = defaultdict(int)
        for cn_id in curve_node_map:
            for pid, pn in child_to_parent.get(cn_id, []):
                if pid in model_map:
                    ctm[pn if pn else "OO"] += 1
        print(f"  CurveNode→Model properties: {dict(sorted(ctm.items()))}")

        ctc = defaultdict(int)
        for cn_id in curve_node_map:
            for cid, cpn in parent_to_child.get(cn_id, []):
                if cid in curve_map:
                    ctc[cpn if cpn else "OO"] += 1
        print(f"  Curve→CurveNode properties: {dict(sorted(ctc.items()))}")

        cpb = defaultdict(int)
        for mid, cns in bone_cns.items():
            cpb[len(cns)] += 1
        print(f"  CurveNodes per bone: {dict(sorted(cpb.items()))}")

        # Detailed examples (first 2 bones)
        print(f"\n  ── Detailed Example Connections ──")
        shown = 0
        for cn_id, cn_info in curve_node_map.items():
            if shown >= 2: break
            pmods = [(pid, pn) for pid, pn in child_to_parent.get(cn_id, []) if pid in model_map]
            ccrvs = [(cid, cpn) for cid, cpn in parent_to_child.get(cn_id, []) if cid in curve_map]
            if pmods:
                print(f"    CurveNode \"{cn_info['name']}\" [{cn_info['type']}] (ID={cn_id})")
                for pid, pn in pmods:
                    print(f"      → Model \"{model_map[pid]}\" prop=\"{pn}\"")
                for cid, cpn in ccrvs:
                    print(f"      ← Curve \"{curve_map[cid]['name']}\" ({curve_map[cid]['num_kf']}kf) prop=\"{cpn}\"")
                shown += 1

    # G) Root bone / hierarchy
    print(f"\n{'='*60}")
    print("G) ROOT BONE / SKELETON HIERARCHY")
    print(f"{'='*60}")

    bids = set(bone_info.keys())
    bch = defaultdict(list)
    bpar = {}
    for bid in bids:
        for pid, pn in child_to_parent.get(bid, []):
            if pid in bids and pn == "":
                bpar[bid] = pid
                bch[pid].append(bid)

    roots = [bid for bid in bids if bid not in bpar]
    print(f"  Root bones (no parent): {len(roots)}")
    for rb in roots:
        info = bone_info[rb]
        t = f"T=({info['lcl_t'][0]:.4f},{info['lcl_t'][1]:.4f},{info['lcl_t'][2]:.4f})" if info['lcl_t'] else ""
        print(f"    ID={rb} \"{info['name']}\" [{info['type']}] {t}")

    def ptree(bid, indent=0):
        info = bone_info[bid]
        prefix = "    " + "│ " * indent
        t = ""
        if info['lcl_t']:
            t = f" T=({info['lcl_t'][0]:.2f},{info['lcl_t'][1]:.2f},{info['lcl_t'][2]:.2f})"
        print(f"{prefix}├─ {info['name']} [{info['type']}]{t}")
        for cid in sorted(bch.get(bid, []), key=lambda x: bone_info[x]['name']):
            ptree(cid, indent + 1)

    print(f"\n  Full bone hierarchy:")
    for rb in sorted(roots, key=lambda x: bone_info[x]['name']):
        ptree(rb)

    tcs = defaultdict(int)
    for info in bone_info.values():
        tcs[info['type']] += 1
    print(f"\n  Bone type summary: {dict(tcs)}")
    print(f"  Total: {len(bone_info)}")

    elapsed = time.time() - t0
    print(f"\n  Total analysis time: {elapsed:.2f}s")
    print(f"{'#'*80}")


def iter_records(nodes):
    for n in nodes:
        yield n
        yield from iter_records(n['ch'])


if __name__ == "__main__":
    for f in [
        "/home/z/my-project/upload/SKM_Quinn_Simple.FBX",
        "/home/z/my-project/upload/TP_Echo_Walk_Fwd.FBX",
    ]:
        analyze(f)
