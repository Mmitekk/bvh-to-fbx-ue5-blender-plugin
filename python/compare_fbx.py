#!/usr/bin/env python3
"""
FBX Structure Comparison Tool
=============================
Compares two FBX files in detail to find why one imports into UE5 and the other doesn't.

Uses FBXReader from bvh_to_fbx_ue5.py to parse both files.
"""

import sys
import os

# Add the script's directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bvh_to_fbx_ue5 import FBXReader

FILE1_PATH = "/home/z/my-project/upload/TP_Echo_Walk_Fwd.FBX"
FILE2_PATH = "/home/z/my-project/download/ElderlyWalk_Quinn_v5.fbx"

FILE1_LABEL = "File1 (WORKS)"
FILE2_LABEL = "File2 (UNKNOWN)"

diffs_found = 0


def diff(section, val1, val2):
    """Print a difference if values differ."""
    global diffs_found
    if val1 != val2:
        diffs_found += 1
        print(f"[DIFF] Section: {section}")
        print(f"  {FILE1_LABEL}: {val1}")
        print(f"  {FILE2_LABEL}: {val2}")
        print()


def diff_list(section, label1, items1, label2, items2):
    """Compare two lists/sets, reporting missing/extra items."""
    global diffs_found
    set1 = set(items1) if not isinstance(items1, set) else items1
    set2 = set(items2) if not isinstance(items2, set) else items2

    only_in_1 = set1 - set2
    only_in_2 = set2 - set1

    if only_in_1 or only_in_2:
        diffs_found += 1
        print(f"[DIFF] Section: {section}")
        if only_in_1:
            print(f"  Only in {label1}: {sorted(only_in_1)}")
        if only_in_2:
            print(f"  Only in {label2}: {sorted(only_in_2)}")
        print()


def fmt_val(v):
    """Format a property value for display."""
    if isinstance(v, (bytes, bytearray)):
        return f"<bytes len={len(v)}>"
    if isinstance(v, list):
        if len(v) > 10:
            return f"[{v[0]}, {v[1]}, ... ] (len={len(v)})"
        return str(v)
    if isinstance(v, float):
        return f"{v:.6g}"
    return str(v)


def fmt_props(props):
    """Format a list of (type, value) property tuples for display."""
    parts = []
    for tc, val in props:
        parts.append(f"({tc},{fmt_val(val)})")
    return " ".join(parts)


def main():
    global diffs_found

    print("=" * 80)
    print("FBX STRUCTURE COMPARISON")
    print("=" * 80)
    print(f"File 1 (WORKS in UE5): {FILE1_PATH}")
    print(f"File 2 (UNKNOWN):      {FILE2_PATH}")
    print()

    # ------------------------------------------------------------------
    # Parse both files
    # ------------------------------------------------------------------
    print("Parsing File 1...")
    fbx1 = FBXReader(FILE1_PATH)
    print(f"  Version: {fbx1.version}, Top-level records: {len(fbx1.root_records)}")

    print("Parsing File 2...")
    fbx2 = FBXReader(FILE2_PATH)
    print(f"  Version: {fbx2.version}, Top-level records: {len(fbx2.root_records)}")
    print()

    # ==================================================================
    # A. FBX VERSION
    # ==================================================================
    print("=" * 60)
    print("A. FBX VERSION")
    print("=" * 60)
    diff("FBX Version", fbx1.version, fbx2.version)
    if fbx1.version == fbx2.version:
        print(f"  Both: {fbx1.version}")

    # ==================================================================
    # B. TOP-LEVEL RECORD STRUCTURE
    # ==================================================================
    print()
    print("=" * 60)
    print("B. TOP-LEVEL RECORD STRUCTURE")
    print("=" * 60)

    top_names1 = [r['name'] for r in fbx1.root_records]
    top_names2 = [r['name'] for r in fbx2.root_records]

    print(f"  {FILE1_LABEL} top-level sections: {top_names1}")
    print(f"  {FILE2_LABEL} top-level sections: {top_names2}")
    diff_list("Top-level sections", FILE1_LABEL, top_names1, FILE2_LABEL, top_names2)

    # Also check the order
    if top_names1 != top_names2:
        shared = set(top_names1) & set(top_names2)
        order1 = [n for n in top_names1 if n in shared]
        order2 = [n for n in top_names2 if n in shared]
        if order1 != order2:
            print(f"[DIFF] Section: Top-level section ORDER")
            print(f"  {FILE1_LABEL} order: {order1}")
            print(f"  {FILE2_LABEL} order: {order2}")
            print()
            diffs_found += 1

    # ==================================================================
    # C. GLOBALSETTINGS
    # ==================================================================
    print()
    print("=" * 60)
    print("C. GLOBALSETTINGS")
    print("=" * 60)

    gs1 = fbx1.find(fbx1.root_records, 'GlobalSettings')
    gs2 = fbx2.find(fbx2.root_records, 'GlobalSettings')

    def extract_gs_version(gs):
        if not gs:
            return None
        for c in gs['children']:
            if c['name'] == 'Version':
                return c['props'][0][1] if c['props'] else None
        return None

    diff("GlobalSettings Version", extract_gs_version(gs1), extract_gs_version(gs2))

    def extract_global_props(gs):
        """Extract all Properties70 P records from GlobalSettings."""
        props = {}
        if not gs:
            return props
        p70 = fbx1.find(gs['children'], 'Properties70') if gs == gs1 else fbx2.find(gs['children'], 'Properties70')
        if not p70:
            # Try the other reader
            p70 = fbx2.find(gs['children'], 'Properties70') if gs == gs2 else fbx1.find(gs['children'], 'Properties70')
        if p70:
            for pc in p70['children']:
                if pc['name'] == 'P' and len(pc['props']) >= 1:
                    pname = pc['props'][0][1]
                    props[pname] = pc['props']
        return props

    # Use the correct reader for each file
    def extract_global_props_for(gs_rec, reader):
        """Extract all Properties70 P records from GlobalSettings."""
        props = {}
        if not gs_rec:
            return props
        p70 = reader.find(gs_rec['children'], 'Properties70')
        if p70:
            for pc in p70['children']:
                if pc['name'] == 'P' and len(pc['props']) >= 1:
                    pname = pc['props'][0][1]
                    props[pname] = pc['props']
        return props

    gp1 = extract_global_props_for(gs1, fbx1)
    gp2 = extract_global_props_for(gs2, fbx2)

    all_gp_keys = sorted(set(gp1.keys()) | set(gp2.keys()))

    # Key settings that UE5 cares about
    CRITICAL_GLOBAL = ['UpAxis', 'UpAxisSign', 'FrontAxis', 'FrontAxisSign',
                       'CoordAxis', 'CoordAxisSign', 'OriginalUpAxis',
                       'OriginalUpAxisSign', 'UnitScaleFactor',
                       'OriginalUnitScaleFactor', 'TimeMode', 'TimeProtocol',
                       'TimeSpanStart', 'TimeSpanStop', 'CustomFrameRate']

    for key in all_gp_keys:
        p1 = gp1.get(key)
        p2 = gp2.get(key)
        if p1 is None:
            diffs_found += 1
            print(f"[DIFF] GlobalSettings Property: {key}")
            print(f"  {FILE1_LABEL}: MISSING")
            print(f"  {FILE2_LABEL}: {fmt_props(p2)}")
            print()
        elif p2 is None:
            diffs_found += 1
            print(f"[DIFF] GlobalSettings Property: {key}")
            print(f"  {FILE1_LABEL}: {fmt_props(p1)}")
            print(f"  {FILE2_LABEL}: MISSING")
            print()
        else:
            # Compare the values (skip type strings, focus on the actual values)
            # Properties format: P(name, type1, type2, type3, ...values)
            vals1 = [fmt_val(v) for t, v in p1[4:]]  # skip name + 3 type fields
            vals2 = [fmt_val(v) for t, v in p2[4:]]
            marker = " *** CRITICAL ***" if key in CRITICAL_GLOBAL else ""
            if vals1 != vals2:
                diffs_found += 1
                print(f"[DIFF] GlobalSettings Property: {key}{marker}")
                print(f"  {FILE1_LABEL}: {vals1}")
                print(f"  {FILE2_LABEL}: {vals2}")
                print()
            else:
                if key in CRITICAL_GLOBAL:
                    print(f"  [OK] {key} = {vals1}")

    # ==================================================================
    # D. OBJECTS SECTION STRUCTURE - COUNT OF EACH OBJECT TYPE
    # ==================================================================
    print()
    print("=" * 60)
    print("D. OBJECTS SECTION - OBJECT TYPE COUNTS")
    print("=" * 60)

    def count_object_types(reader, root_records):
        """Count each object type in the Objects section."""
        objects = reader.find(root_records, 'Objects')
        counts = {}
        if objects:
            for child in objects['children']:
                name = child['name']
                counts[name] = counts.get(name, 0) + 1
        return counts

    ot1 = count_object_types(fbx1, fbx1.root_records)
    ot2 = count_object_types(fbx2, fbx2.root_records)

    print(f"  {FILE1_LABEL} object counts: {dict(sorted(ot1.items()))}")
    print(f"  {FILE2_LABEL} object counts: {dict(sorted(ot2.items()))}")
    print()

    all_obj_types = sorted(set(ot1.keys()) | set(ot2.keys()))
    for ot in all_obj_types:
        c1 = ot1.get(ot, 0)
        c2 = ot2.get(ot, 0)
        diff(f"Objects count: {ot}", c1, c2)

    # ==================================================================
    # E. POSE RECORDS (CRITICAL FOR UE5)
    # ==================================================================
    print()
    print("=" * 60)
    print("E. POSE RECORDS *** CRITICAL FOR UE5 ***")
    print("=" * 60)

    def extract_poses(reader, root_records):
        """Extract all Pose records."""
        objects = reader.find(root_records, 'Objects')
        if not objects:
            return []
        poses = reader.find_all(objects['children'], 'Pose')
        result = []
        for pose in poses:
            info = {
                'props': pose['props'],
                'child_names': [c['name'] for c in pose['children']],
                'num_children': len(pose['children']),
            }
            # Extract Type from props if available
            for p in pose['props']:
                if len(p) >= 2 and p[0] == 'S':
                    info['type_str'] = p[1]
                    break
            result.append(info)
        return result

    poses1 = extract_poses(fbx1, fbx1.root_records)
    poses2 = extract_poses(fbx2, fbx2.root_records)

    print(f"  {FILE1_LABEL} Pose records: {len(poses1)}")
    for i, p in enumerate(poses1):
        print(f"    Pose[{i}]: props={fmt_props(p['props'])}, sub-records={p['child_names']}, count={p['num_children']}")

    print(f"  {FILE2_LABEL} Pose records: {len(poses2)}")
    for i, p in enumerate(poses2):
        print(f"    Pose[{i}]: props={fmt_props(p['props'])}, sub-records={p['child_names']}, count={p['num_children']}")

    if len(poses1) != len(poses2):
        print()
        print("  *** CRITICAL DIFFERENCE: Pose/BindPose record count mismatch! ***")
        if len(poses1) == 0:
            print("  File1 (WORKS) has NO Pose records - interesting, may not be required for animation-only import")
        if len(poses2) == 0:
            print("  File2 (UNKNOWN) has NO Pose records - this MAY cause issues if UE5 expects BindPose")

    # Detailed Pose comparison if both have poses
    if poses1 and poses2:
        print()
        print("  --- Detailed Pose comparison ---")
        # Compare first pose from each
        p1 = poses1[0]
        p2 = poses2[0]
        diff("Pose[0] props", fmt_props(p1['props']), fmt_props(p2['props']))
        diff("Pose[0] sub-record names", p1['child_names'], p2['child_names'])

        # Check for BindPose specifically
        def find_bindpose_type(poses):
            for p in poses:
                for prop in p['props']:
                    if len(prop) >= 2 and prop[0] == 'S' and 'BindPose' in str(prop[1]):
                        return str(prop[1])
            return None

        bp1 = find_bindpose_type(poses1)
        bp2 = find_bindpose_type(poses2)
        diff("BindPose type string", bp1, bp2)

    # ==================================================================
    # F. MODEL RECORDS
    # ==================================================================
    print()
    print("=" * 60)
    print("F. MODEL RECORDS - SUB-RECORD STRUCTURE")
    print("=" * 60)

    def extract_models(reader, root_records):
        """Extract Model records with their sub-record structure."""
        objects = reader.find(root_records, 'Objects')
        if not objects:
            return []
        models = reader.find_all(objects['children'], 'Model')
        result = []
        for m in models:
            props = m['props']
            model_id = props[0][1] if len(props) > 0 else '?'
            full_name = props[1][1] if len(props) > 1 else '?'
            model_type = props[2][1] if len(props) > 2 else '?'
            bone_name = full_name.split('\x00')[0] if '\x00' in str(full_name) else str(full_name)

            child_names = [c['name'] for c in m['children']]

            result.append({
                'id': model_id,
                'name': bone_name,
                'type': model_type,
                'child_names': child_names,
                'children': m['children'],
                'full_name': full_name,
            })
        return result

    models1 = extract_models(fbx1, fbx1.root_records)
    models2 = extract_models(fbx2, fbx2.root_records)

    print(f"  {FILE1_LABEL}: {len(models1)} Model records")
    print(f"  {FILE2_LABEL}: {len(models2)} Model records")
    print()

    # Compare sub-record structure of Model records
    # Get the set of unique sub-record name patterns
    def get_model_sub_record_patterns(models):
        """Get unique sets of sub-record names across all models."""
        patterns = {}
        for m in models:
            key = tuple(sorted(m['child_names']))
            if key not in patterns:
                patterns[key] = []
            patterns[key].append(m['name'])
        return patterns

    pat1 = get_model_sub_record_patterns(models1)
    pat2 = get_model_sub_record_patterns(models2)

    print("  Model sub-record patterns (File1):")
    for pat, names in pat1.items():
        print(f"    {list(pat)} -> {names[:3]}{'...' if len(names) > 3 else ''} ({len(names)} models)")

    print("  Model sub-record patterns (File2):")
    for pat, names in pat2.items():
        print(f"    {list(pat)} -> {names[:3]}{'...' if len(names) > 3 else ''} ({len(names)} models)")

    # Compare specific sub-record details for first model of each type
    print()
    print("  --- Comparing first Root model ---")
    root1 = [m for m in models1 if m['type'] == 'Root']
    root2 = [m for m in models2 if m['type'] == 'Root']
    if root1 and root2:
        diff("Root Model child_names", root1[0]['child_names'], root2[0]['child_names'])

        # Compare Version sub-record
        for r, label in [(root1[0], FILE1_LABEL), (root2[0], FILE2_LABEL)]:
            ver_rec = None
            for c in r['children']:
                if c['name'] == 'Version':
                    ver_rec = c
                    break
            if ver_rec:
                print(f"  {label} Root Model Version: {fmt_props(ver_rec['props'])}")

        # Compare MultiLayer, MultiTake, Shading, Culling
        for subname in ['Version', 'MultiLayer', 'MultiTake', 'Shading', 'Culling']:
            sv1 = None
            sv2 = None
            for c in root1[0]['children']:
                if c['name'] == subname:
                    sv1 = c
                    break
            for c in root2[0]['children']:
                if c['name'] == subname:
                    sv2 = c
                    break
            v1_str = fmt_props(sv1['props']) if sv1 else "MISSING"
            v2_str = fmt_props(sv2['props']) if sv2 else "MISSING"
            diff(f"Root Model {subname}", v1_str, v2_str)

    print()
    print("  --- Comparing first LimbNode model ---")
    limb1 = [m for m in models1 if m['type'] == 'LimbNode']
    limb2 = [m for m in models2 if m['type'] == 'LimbNode']
    if limb1 and limb2:
        diff("LimbNode Model[0] name", limb1[0]['name'], limb2[0]['name'])
        diff("LimbNode Model[0] child_names", limb1[0]['child_names'], limb2[0]['child_names'])

        # Compare Version sub-record
        for subname in ['Version', 'MultiLayer', 'MultiTake', 'Shading', 'Culling']:
            sv1 = None
            sv2 = None
            for c in limb1[0]['children']:
                if c['name'] == subname:
                    sv1 = c
                    break
            for c in limb2[0]['children']:
                if c['name'] == subname:
                    sv2 = c
                    break
            v1_str = fmt_props(sv1['props']) if sv1 else "MISSING"
            v2_str = fmt_props(sv2['props']) if sv2 else "MISSING"
            diff(f"LimbNode Model[0] {subname}", v1_str, v2_str)

    # ==================================================================
    # G. NODEATTRIBUTE RECORDS
    # ==================================================================
    print()
    print("=" * 60)
    print("G. NODEATTRIBUTE RECORDS")
    print("=" * 60)

    def extract_node_attrs(reader, root_records):
        """Extract NodeAttribute records."""
        objects = reader.find(root_records, 'Objects')
        if not objects:
            return []
        nas = reader.find_all(objects['children'], 'NodeAttribute')
        result = []
        for na in nas:
            props = na['props']
            na_id = props[0][1] if len(props) > 0 else '?'
            full_name = props[1][1] if len(props) > 1 else '?'
            na_type = props[2][1] if len(props) > 2 else '?'
            bone_name = full_name.split('\x00')[0] if '\x00' in str(full_name) else str(full_name)

            child_names = [c['name'] for c in na['children']]
            child_details = {}
            for c in na['children']:
                child_details[c['name']] = fmt_props(c['props'])

            result.append({
                'id': na_id,
                'name': bone_name,
                'type': na_type,
                'child_names': child_names,
                'child_details': child_details,
            })
        return result

    nas1 = extract_node_attrs(fbx1, fbx1.root_records)
    nas2 = extract_node_attrs(fbx2, fbx2.root_records)

    print(f"  {FILE1_LABEL}: {len(nas1)} NodeAttribute records")
    print(f"  {FILE2_LABEL}: {len(nas2)} NodeAttribute records")
    print()

    # Compare patterns
    def get_na_patterns(nas):
        patterns = {}
        for na in nas:
            key = (na['type'], tuple(sorted(na['child_names'])))
            if key not in patterns:
                patterns[key] = []
            patterns[key].append(na['name'])
        return patterns

    na_pat1 = get_na_patterns(nas1)
    na_pat2 = get_na_patterns(nas2)

    print("  NodeAttribute patterns (File1):")
    for (na_type, children), names in na_pat1.items():
        print(f"    type={na_type}, sub-records={list(children)} -> {names[:3]}... ({len(names)} attrs)")

    print("  NodeAttribute patterns (File2):")
    for (na_type, children), names in na_pat2.items():
        print(f"    type={na_type}, sub-records={list(children)} -> {names[:3]}... ({len(names)} attrs)")

    # Compare TypeFlags detail
    print()
    print("  --- TypeFlags comparison ---")
    for na_list, label in [(nas1, FILE1_LABEL), (nas2, FILE2_LABEL)]:
        type_flags = set()
        for na in na_list:
            tf = na['child_details'].get('TypeFlags', 'MISSING')
            type_flags.add((na['type'], tf))
        print(f"  {label} TypeFlags variants:")
        for na_type, tf in sorted(type_flags):
            print(f"    {na_type} -> TypeFlags={tf}")

    # ==================================================================
    # H. ANIMATIONCURVENODE
    # ==================================================================
    print()
    print("=" * 60)
    print("H. ANIMATIONCURVENODE")
    print("=" * 60)

    def extract_curve_nodes(reader, root_records):
        """Extract AnimationCurveNode records."""
        objects = reader.find(root_records, 'Objects')
        if not objects:
            return []
        cnodes = reader.find_all(objects['children'], 'AnimationCurveNode')
        result = []
        for cn in cnodes:
            props = cn['props']
            cn_id = props[0][1] if len(props) > 0 else '?'
            full_name = props[1][1] if len(props) > 1 else '?'
            cn_type = props[2][1] if len(props) > 2 else '?'
            bone_name = full_name.split('\x00')[0] if '\x00' in str(full_name) else str(full_name)

            child_names = [c['name'] for c in cn['children']]
            child_details = {}
            for c in cn['children']:
                child_details[c['name']] = fmt_props(c['props'])

            result.append({
                'id': cn_id,
                'name': bone_name,
                'type': cn_type,
                'child_names': child_names,
                'child_details': child_details,
            })
        return result

    cn1 = extract_curve_nodes(fbx1, fbx1.root_records)
    cn2 = extract_curve_nodes(fbx2, fbx2.root_records)

    print(f"  {FILE1_LABEL}: {len(cn1)} AnimationCurveNode records")
    print(f"  {FILE2_LABEL}: {len(cn2)} AnimationCurveNode records")
    print()

    # Compare first few curve nodes in detail
    def show_curve_node_samples(cnodes, label, count=3):
        print(f"  {label} - first {min(count, len(cnodes))} AnimationCurveNodes:")
        for i, cn in enumerate(cnodes[:count]):
            print(f"    [{i}] name={cn['name']}, type={cn['type']}, sub-records={cn['child_names']}")
            for sr_name, sr_val in cn['child_details'].items():
                print(f"        {sr_name}: {sr_val}")

    show_curve_node_samples(cn1, FILE1_LABEL)
    show_curve_node_samples(cn2, FILE2_LABEL)

    # Compare child record patterns
    cn_pat1 = set(tuple(sorted(cn['child_names'])) for cn in cn1)
    cn_pat2 = set(tuple(sorted(cn['child_names'])) for cn in cn2)
    diff_list("AnimationCurveNode sub-record patterns", FILE1_LABEL, cn_pat1, FILE2_LABEL, cn_pat2)

    # ==================================================================
    # I. ANIMATIONCURVE
    # ==================================================================
    print()
    print("=" * 60)
    print("I. ANIMATIONCURVE")
    print("=" * 60)

    def extract_curves(reader, root_records):
        """Extract AnimationCurve records."""
        objects = reader.find(root_records, 'Objects')
        if not objects:
            return []
        curves = reader.find_all(objects['children'], 'AnimationCurve')
        result = []
        for cv in curves:
            props = cv['props']
            cv_id = props[0][1] if len(props) > 0 else '?'
            full_name = props[1][1] if len(props) > 1 else '?'
            cv_type = props[2][1] if len(props) > 2 else '?'
            bone_name = full_name.split('\x00')[0] if '\x00' in str(full_name) else str(full_name)

            child_names = [c['name'] for c in cv['children']]
            child_details = {}
            for c in cv['children']:
                # For arrays, show type and length
                detail_parts = []
                for tc, val in c['props']:
                    if isinstance(val, list):
                        detail_parts.append(f"({tc}, array len={len(val)})")
                    else:
                        detail_parts.append(f"({tc}, {fmt_val(val)})")
                child_details[c['name']] = " ".join(detail_parts)

            result.append({
                'id': cv_id,
                'name': bone_name,
                'type': cv_type,
                'child_names': child_names,
                'child_details': child_details,
                'raw_children': cv['children'],
            })
        return result

    cv1 = extract_curves(fbx1, fbx1.root_records)
    cv2 = extract_curves(fbx2, fbx2.root_records)

    print(f"  {FILE1_LABEL}: {len(cv1)} AnimationCurve records")
    print(f"  {FILE2_LABEL}: {len(cv2)} AnimationCurve records")
    print()

    # Compare sub-record structure
    def show_curve_samples(curves, label, count=3):
        print(f"  {label} - first {min(count, len(curves))} AnimationCurves:")
        for i, cv in enumerate(curves[:count]):
            print(f"    [{i}] name={cv['name']}, sub-records={cv['child_names']}")
            for sr_name, sr_val in cv['child_details'].items():
                print(f"        {sr_name}: {sr_val}")

    show_curve_samples(cv1, FILE1_LABEL)
    show_curve_samples(cv2, FILE2_LABEL)

    # Compare the set of sub-record patterns
    cv_pat1 = set(tuple(sorted(cv['child_names'])) for cv in cv1)
    cv_pat2 = set(tuple(sorted(cv['child_names'])) for cv in cv2)
    diff_list("AnimationCurve sub-record patterns", FILE1_LABEL, cv_pat1, FILE2_LABEL, cv_pat2)

    # Deep compare first curve's data format
    if cv1 and cv2:
        print()
        print("  --- Deep comparison of first AnimationCurve ---")
        # KeyVer
        for curves, label in [(cv1, FILE1_LABEL), (cv2, FILE2_LABEL)]:
            for c in curves[0]['raw_children']:
                if c['name'] == 'KeyVer':
                    print(f"  {label} KeyVer: {fmt_props(c['props'])}")
                elif c['name'] == 'KeyTime':
                    for tc, val in c['props']:
                        if isinstance(val, list):
                            print(f"  {label} KeyTime: type={tc}, array_len={len(val)}, first_3={val[:3]}")
                        else:
                            print(f"  {label} KeyTime: type={tc}, val={fmt_val(val)}")
                elif c['name'] == 'KeyValueFloat':
                    for tc, val in c['props']:
                        if isinstance(val, list):
                            print(f"  {label} KeyValueFloat: type={tc}, array_len={len(val)}, first_3={val[:3]}")
                        else:
                            print(f"  {label} KeyValueFloat: type={tc}, val={fmt_val(val)}")
                elif c['name'] == 'KeyValueDouble':
                    for tc, val in c['props']:
                        if isinstance(val, list):
                            print(f"  {label} KeyValueDouble: type={tc}, array_len={len(val)}, first_3={val[:3]}")
                        else:
                            print(f"  {label} KeyValueDouble: type={tc}, val={fmt_val(val)}")
                elif c['name'] == 'KeyAttrFlags':
                    for tc, val in c['props']:
                        if isinstance(val, list):
                            print(f"  {label} KeyAttrFlags: type={tc}, array_len={len(val)}, first_3={val[:3]}")
                        else:
                            print(f"  {label} KeyAttrFlags: type={tc}, val={fmt_val(val)}")
                elif c['name'] == 'KeyAttrDataFloat':
                    for tc, val in c['props']:
                        if isinstance(val, list):
                            print(f"  {label} KeyAttrDataFloat: type={tc}, array_len={len(val)}, first_3={val[:3]}")
                        else:
                            print(f"  {label} KeyAttrDataFloat: type={tc}, val={fmt_val(val)}")

        # Check: does File1 use KeyValueFloat or KeyValueDouble?
        kv_float_1 = any('KeyValueFloat' in cv['child_names'] for cv in cv1)
        kv_double_1 = any('KeyValueDouble' in cv['child_names'] for cv in cv1)
        kv_float_2 = any('KeyValueFloat' in cv['child_names'] for cv in cv2)
        kv_double_2 = any('KeyValueDouble' in cv['child_names'] for cv in cv2)

        diff("AnimationCurve uses KeyValueFloat", kv_float_1, kv_float_2)
        diff("AnimationCurve uses KeyValueDouble", kv_double_1, kv_double_2)

        # Check: Default values in curves
        def check_curve_defaults(curves, label):
            defaults = set()
            for cv in curves:
                for c in cv['raw_children']:
                    if c['name'] == 'Default':
                        defaults.add(fmt_props(c['props']))
            return defaults

        cd1 = check_curve_defaults(cv1, FILE1_LABEL)
        cd2 = check_curve_defaults(cv2, FILE2_LABEL)
        diff_list("AnimationCurve Default values", FILE1_LABEL, cd1, FILE2_LABEL, cd2)

    # ==================================================================
    # J. CONNECTIONS
    # ==================================================================
    print()
    print("=" * 60)
    print("J. CONNECTIONS")
    print("=" * 60)

    def extract_connections(reader, root_records):
        """Extract all connection records."""
        conn_rec = reader.find(root_records, 'Connections')
        if not conn_rec:
            return []
        conns = []
        for c in conn_rec['children']:
            if c['name'] == 'C':
                props = c['props']
                conn_type = props[0][1] if len(props) > 0 else '?'
                from_id = props[1][1] if len(props) > 1 else '?'
                to_id = props[2][1] if len(props) > 2 else '?'
                prop_name = props[3][1] if len(props) > 3 else None
                conns.append({
                    'type': conn_type,
                    'from': from_id,
                    'to': to_id,
                    'prop': prop_name,
                })
        return conns

    conns1 = extract_connections(fbx1, fbx1.root_records)
    conns2 = extract_connections(fbx2, fbx2.root_records)

    print(f"  {FILE1_LABEL}: {len(conns1)} connections")
    print(f"  {FILE2_LABEL}: {len(conns2)} connections")
    print()

    # Count connection types
    def count_conn_types(conns):
        counts = {}
        for c in conns:
            key = c['type']
            counts[key] = counts.get(key, 0) + 1
        return counts

    ct1 = count_conn_types(conns1)
    ct2 = count_conn_types(conns2)
    print(f"  {FILE1_LABEL} connection types: {dict(sorted(ct1.items()))}")
    print(f"  {FILE2_LABEL} connection types: {dict(sorted(ct2.items()))}")

    all_conn_types = sorted(set(ct1.keys()) | set(ct2.keys()))
    for ct in all_conn_types:
        diff(f"Connection type count: {ct}", ct1.get(ct, 0), ct2.get(ct, 0))

    # Check for OP connections (property connections for animation)
    op_conns1 = [c for c in conns1 if c['type'] == 'OP']
    op_conns2 = [c for c in conns2 if c['type'] == 'OP']
    print()
    print(f"  {FILE1_LABEL} OP connections (property links): {len(op_conns1)}")
    if op_conns1:
        print(f"    Sample: from={op_conns1[0]['from']} to={op_conns1[0]['to']} prop={op_conns1[0]['prop']}")
    print(f"  {FILE2_LABEL} OP connections (property links): {len(op_conns2)}")
    if op_conns2:
        print(f"    Sample: from={op_conns2[0]['from']} to={op_conns2[0]['to']} prop={op_conns2[0]['prop']}")

    # Check for OO connections pattern
    oo_conns1 = [c for c in conns1 if c['type'] == 'OO']
    oo_conns2 = [c for c in conns2 if c['type'] == 'OO']
    print()
    print(f"  {FILE1_LABEL} OO connections (object links): {len(oo_conns1)}")
    print(f"  {FILE2_LABEL} OO connections (object links): {len(oo_conns2)}")

    # ==================================================================
    # K. DEFINITIONS SECTION
    # ==================================================================
    print()
    print("=" * 60)
    print("K. DEFINITIONS SECTION")
    print("=" * 60)

    def extract_definitions(reader, root_records):
        """Extract Definitions section details."""
        defs = reader.find(root_records, 'Definitions')
        if not defs:
            return {}
        result = {}
        for c in defs['children']:
            if c['name'] == 'Version':
                result['Version'] = c['props'][0][1] if c['props'] else None
            elif c['name'] == 'Count':
                result['Count'] = c['props'][0][1] if c['props'] else None
            elif c['name'] == 'ObjectType':
                ot_name = c['props'][0][1] if len(c['props']) > 0 else '?'
                ot_info = {}
                for sc in c['children']:
                    if sc['name'] == 'Count':
                        ot_info['Count'] = sc['props'][0][1] if sc['props'] else None
                    elif sc['name'] == 'Version':
                        ot_info['Version'] = sc['props'][0][1] if sc['props'] else None
                    elif sc['name'] == 'NodeAttributeVersion':
                        ot_info['NodeAttributeVersion'] = sc['props'][0][1] if sc['props'] else None
                    else:
                        ot_info[sc['name']] = fmt_props(sc['props'])
                result[ot_name] = ot_info
        return result

    defs1 = extract_definitions(fbx1, fbx1.root_records)
    defs2 = extract_definitions(fbx2, fbx2.root_records)

    # Compare version and count
    diff("Definitions Version", defs1.get('Version'), defs2.get('Version'))
    diff("Definitions Count", defs1.get('Count'), defs2.get('Count'))

    # Compare ObjectType entries
    all_ot = sorted(set(defs1.keys()) | set(defs2.keys()) - {'Version', 'Count'})
    for ot in all_ot:
        d1 = defs1.get(ot, {})
        d2 = defs2.get(ot, {})
        if not d1 and not d2:
            continue
        if not d1:
            diffs_found += 1
            print(f"[DIFF] Definitions ObjectType: {ot}")
            print(f"  {FILE1_LABEL}: MISSING")
            print(f"  {FILE2_LABEL}: {d2}")
            print()
            continue
        if not d2:
            diffs_found += 1
            print(f"[DIFF] Definitions ObjectType: {ot}")
            print(f"  {FILE1_LABEL}: {d1}")
            print(f"  {FILE2_LABEL}: MISSING")
            print()
            continue
        # Compare each field
        if not isinstance(d1, dict):
            d1 = {'value': d1}
        if not isinstance(d2, dict):
            d2 = {'value': d2}
        for field in sorted(set(d1.keys()) | set(d2.keys())):
            v1 = d1.get(field)
            v2 = d2.get(field)
            diff(f"Definitions {ot}.{field}", v1, v2)

    # ==================================================================
    # L. DOCUMENTS SECTION
    # ==================================================================
    print()
    print("=" * 60)
    print("L. DOCUMENTS SECTION")
    print("=" * 60)

    def extract_documents(reader, root_records):
        """Extract Documents section details."""
        docs = reader.find(root_records, 'Documents')
        if not docs:
            return None
        result = {'child_names': [c['name'] for c in docs['children']]}
        for c in docs['children']:
            if c['name'] == 'Count':
                result['Count'] = c['props'][0][1] if c['props'] else None
            elif c['name'] == 'Document':
                doc_info = {
                    'props': fmt_props(c['props']),
                    'child_names': [sc['name'] for sc in c['children']],
                }
                # Extract sub-details
                for sc in c['children']:
                    if sc['name'] == 'Properties70':
                        p70_details = []
                        for pc in sc['children']:
                            if pc['name'] == 'P':
                                p70_details.append(fmt_props(pc['props']))
                        doc_info['Properties70'] = p70_details
                    elif sc['name'] == 'RootNode':
                        doc_info['RootNode'] = fmt_props(sc['props'])
                result['Document'] = doc_info
        return result

    docs1 = extract_documents(fbx1, fbx1.root_records)
    docs2 = extract_documents(fbx2, fbx2.root_records)

    def show_docs(docs, label):
        if not docs:
            print(f"  {label}: MISSING")
            return
        print(f"  {label}: child_names={docs.get('child_names')}")
        if 'Count' in docs:
            print(f"    Count: {docs['Count']}")
        if 'Document' in docs:
            d = docs['Document']
            print(f"    Document props: {d['props']}")
            print(f"    Document child_names: {d['child_names']}")
            if 'Properties70' in d:
                for p in d['Properties70']:
                    print(f"      P: {p}")
            if 'RootNode' in d:
                print(f"    RootNode: {d['RootNode']}")

    show_docs(docs1, FILE1_LABEL)
    show_docs(docs2, FILE2_LABEL)

    # Compare documents
    if docs1 and docs2:
        diff("Documents Count", docs1.get('Count'), docs2.get('Count'))
        if 'Document' in docs1 and 'Document' in docs2:
            d1 = docs1['Document']
            d2 = docs2['Document']
            diff("Document props", d1['props'], d2['props'])
            diff("Document child_names", d1['child_names'], d2['child_names'])
            if 'Properties70' in d1 and 'Properties70' in d2:
                diff("Document Properties70", d1['Properties70'], d2['Properties70'])
            elif 'Properties70' in d1 or 'Properties70' in d2:
                diff("Document Properties70 presence",
                     "present" if 'Properties70' in d1 else "missing",
                     "present" if 'Properties70' in d2 else "missing")

    # ==================================================================
    # SUMMARY
    # ==================================================================
    print()
    print("=" * 80)
    print(f"SUMMARY: {diffs_found} differences found")
    print("=" * 80)

    # Final critical assessment
    print()
    print("=" * 80)
    print("CRITICAL ASSESSMENT FOR UE5 COMPATIBILITY")
    print("=" * 80)

    # Re-check key issues
    issues = []

    # 1. Pose/BindPose
    if len(poses1) > 0 and len(poses2) == 0:
        issues.append("CRITICAL: File1 has Pose records but File2 does NOT. Missing BindPose can cause UE5 skeleton import failure.")
    elif len(poses1) == 0 and len(poses2) == 0:
        issues.append("INFO: Neither file has Pose records. Animation-only import may work without BindPose.")
    elif len(poses2) > 0 and len(poses1) == 0:
        issues.append("NOTE: File2 has Pose records but File1 does not. This is unlikely to be the problem.")

    # 2. FBX version
    if fbx1.version != fbx2.version:
        issues.append(f"WARNING: FBX versions differ ({fbx1.version} vs {fbx2.version}). UE5 prefers version 7300-7700.")

    # 3. GlobalSettings differences
    critical_gs_diffs = []
    for key in CRITICAL_GLOBAL:
        v1 = gp1.get(key)
        v2 = gp2.get(key)
        if v1 and v2:
            vals1 = [fmt_val(v) for t, v in v1[4:]]
            vals2 = [fmt_val(v) for t, v in v2[4:]]
            if vals1 != vals2:
                critical_gs_diffs.append(f"{key}: {vals1} vs {vals2}")
    if critical_gs_diffs:
        issues.append(f"WARNING: GlobalSettings differences: {', '.join(critical_gs_diffs)}")

    # 4. Model sub-record structure
    if pat1.keys() != pat2.keys():
        issues.append(f"WARNING: Model sub-record patterns differ. File1 patterns: {list(pat1.keys())}, File2 patterns: {list(pat2.keys())}")

    # 5. AnimationCurve format
    if cv1 and cv2:
        has_float1 = any('KeyValueFloat' in cv['child_names'] for cv in cv1)
        has_double1 = any('KeyValueDouble' in cv['child_names'] for cv in cv1)
        has_float2 = any('KeyValueFloat' in cv['child_names'] for cv in cv2)
        has_double2 = any('KeyValueDouble' in cv['child_names'] for cv in cv2)
        if has_float1 != has_float2 or has_double1 != has_double2:
            issues.append(f"WARNING: AnimationCurve value type differs. File1: float={has_float1} double={has_double1}, File2: float={has_float2} double={has_double2}")

    # 6. AnimationCurve tangent format (MOST CRITICAL)
    if cv1 and cv2:
        # Check KeyAttrFlags length: per-curve (1) vs per-key (N)
        flags_len1 = None
        flags_len2 = None
        for c in cv1[0]['raw_children']:
            if c['name'] == 'KeyAttrFlags':
                for tc, val in c['props']:
                    if isinstance(val, list):
                        flags_len1 = len(val)
        for c in cv2[0]['raw_children']:
            if c['name'] == 'KeyAttrFlags':
                for tc, val in c['props']:
                    if isinstance(val, list):
                        flags_len2 = len(val)
        if flags_len1 == 1 and flags_len2 and flags_len2 > 1:
            issues.append(f"CRITICAL: AnimationCurve tangent format differs! File1 uses PER-CURVE tangent data (KeyAttrFlags len=1), File2 uses PER-KEY tangent data (KeyAttrFlags len={flags_len2}). UE5/FBX SDK expects per-curve format (KeyVer 4009). File2's per-key format (KeyVer 4008) may be INCOMPATIBLE with UE5.")

        # Check KeyAttrDataFloat type
        kadf_type1 = None
        kadf_type2 = None
        kadf_len1 = None
        kadf_len2 = None
        for c in cv1[0]['raw_children']:
            if c['name'] == 'KeyAttrDataFloat':
                for tc, val in c['props']:
                    if isinstance(val, list):
                        kadf_type1 = tc
                        kadf_len1 = len(val)
        for c in cv2[0]['raw_children']:
            if c['name'] == 'KeyAttrDataFloat':
                for tc, val in c['props']:
                    if isinstance(val, list):
                        kadf_type2 = tc
                        kadf_len2 = len(val)
        if kadf_type1 != kadf_type2 or (kadf_len1 and kadf_len2 and kadf_len1 <= 4 and kadf_len2 > 4):
            issues.append(f"CRITICAL: KeyAttrDataFloat format differs! File1: type={kadf_type1}, len={kadf_len1} (per-curve), File2: type={kadf_type2}, len={kadf_len2} (per-key). This is a MAJOR format incompatibility.")

    # 7. NodeAttribute root type
    na_root1 = [na for na in nas1 if na['name'] == 'root']
    na_root2 = [na for na in nas2 if na['name'] == 'root']
    if na_root1 and na_root2:
        if na_root1[0]['type'] != na_root2[0]['type']:
            issues.append(f"WARNING: Root bone NodeAttribute type differs. File1: type='{na_root1[0]['type']}', File2: type='{na_root2[0]['type']}'. UE5 may need 'Root' type for root bone.")

    # 8. AnimationCurveNode naming
    if cn1 and cn2:
        cn_names1_sample = set(cn['name'] for cn in cn1[:10])
        cn_names2_sample = set(cn['name'] for cn in cn2[:10])
        if cn_names1_sample != cn_names2_sample:
            issues.append(f"INFO: AnimationCurveNode naming differs. File1: {sorted(cn_names1_sample)}, File2: {sorted(cn_names2_sample)}. This affects how curves are linked but may not break import if connections are correct.")

    # 9. AnimationCurve record name
    if cv1 and cv2:
        cv_name1 = cv1[0]['name']
        cv_name2 = cv2[0]['name']
        if cv_name1 != cv_name2:
            issues.append(f"INFO: AnimationCurve name differs. File1: '{cv_name1}', File2: '{cv_name2}'. File1 (working) uses empty string, which is standard FBX SDK output.")

    # 10. KeyVer difference
    if cv1 and cv2:
        kv1 = None
        kv2 = None
        for c in cv1[0]['raw_children']:
            if c['name'] == 'KeyVer':
                kv1 = c['props'][0][1] if c['props'] else None
        for c in cv2[0]['raw_children']:
            if c['name'] == 'KeyVer':
                kv2 = c['props'][0][1] if c['props'] else None
        if kv1 != kv2:
            issues.append(f"WARNING: AnimationCurve KeyVer differs. File1: {kv1}, File2: {kv2}. KeyVer 4009 = per-curve tangent mode, KeyVer 4008 = per-key tangent mode. This correlates with the tangent format difference above.")

    # 11. Definitions PropertyTemplate
    has_pt1 = any('PropertyTemplate' in (defs1.get(ot, {}) if isinstance(defs1.get(ot, {}), dict) else {}) for ot in defs1 if ot not in ('Version', 'Count'))
    has_pt2 = any('PropertyTemplate' in (defs2.get(ot, {}) if isinstance(defs2.get(ot, {}), dict) else {}) for ot in defs2 if ot not in ('Version', 'Count'))
    if has_pt1 and not has_pt2:
        issues.append(f"INFO: File1 has PropertyTemplate in Definitions ObjectTypes but File2 does not. PropertyTemplates are optional but help UE5 understand object schemas.")

    # 12. Document ActiveAnimStackName
    if docs1 and docs2 and 'Document' in docs1 and 'Document' in docs2:
        p70_1 = docs1['Document'].get('Properties70', [])
        p70_2 = docs2['Document'].get('Properties70', [])
        stack_name1 = None
        stack_name2 = None
        for p in p70_1:
            if 'ActiveAnimStackName' in p:
                # Extract the value part
                parts = p.split()
                stack_name1 = parts[-1] if parts else None
        for p in p70_2:
            if 'ActiveAnimStackName' in p:
                parts = p.split()
                stack_name2 = parts[-1] if parts else None
        if stack_name1 != stack_name2:
            issues.append(f"INFO: Document ActiveAnimStackName differs. File1: '{stack_name1}', File2: '{stack_name2}'. File2 has explicit name 'Unreal Take' which should work with UE5.")

    if issues:
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
    else:
        print("  No critical issues found - files appear structurally similar.")

    print()
    return diffs_found


if __name__ == '__main__':
    main()
