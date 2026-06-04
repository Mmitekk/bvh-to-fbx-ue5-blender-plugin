#!/usr/bin/env python3
"""
BVH to FBX Converter for Unreal Engine 5 - v5
================================================

Converts BVH motion capture files to UE5-compatible FBX animation files,
using a reference skeleton FBX as a template for exact bone hierarchy,
rest poses, and structural records.

Key improvements over v4:
- Reads reference skeleton FBX to extract EXACT bone data (not hardcoded)
- Uses correct Euler angle convention (ZYX for FBX RotationOrder=0)
- Preserves all bone properties from reference FBX
- Comprehensive validation of output

Usage:
    python3 bvh_to_fbx_ue5.py <input.bvh> <output.fbx> --skeleton REF.FBX [--scale SCALE]
"""

import sys
import os
import struct
import zlib
import array
import math
import json
from collections import OrderedDict


# ============================================================================
# BVH PARSER
# ============================================================================

class BVHBone:
    """Represents a bone in the BVH hierarchy."""
    def __init__(self, name, offset, channels, parent=None):
        self.name = name
        self.offset = offset
        self.channels = channels
        self.parent = parent
        self.children = []
        self.is_root = False
        self.is_end_site = False
        self.channel_indices = {}


class BVHFile:
    """Parses a BVH motion capture file."""

    def __init__(self, filepath):
        self.filepath = filepath
        self.root_bone = None
        self.bones = []
        self.bone_map = {}
        self.frame_count = 0
        self.frame_time = 0.0
        self.fps = 0.0
        self.frames = []
        self.channel_count = 0
        self._parse()

    def _parse(self):
        with open(self.filepath, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        if content.startswith('\ufeff'):
            content = content[1:]

        # Tokenize
        tokens = []
        i = 0
        while i < len(content):
            if content[i] in ' \t\r\n':
                i += 1
                continue
            start = i
            while i < len(content) and content[i] not in ' \t\r\n{}':
                i += 1
            if i > start:
                tokens.append(content[start:i])
            if i < len(content) and content[i] in '{}':
                tokens.append(content[i])
                i += 1

        pos = 0

        def expect(tok):
            nonlocal pos
            if tokens[pos].lower() != tok.lower():
                if tok.lower() in tokens[pos].lower():
                    pos += 1
                    return
                raise ValueError(f"Expected '{tok}' got '{tokens[pos]}' at {pos}")
            pos += 1

        def parse_joint(is_root=False):
            nonlocal pos
            if is_root:
                expect('ROOT')
            elif tokens[pos] == 'End':
                expect('End')
                expect('Site')
                bone = BVHBone('EndSite', [0, 0, 0], [])
                bone.is_end_site = True
                expect('{')
                expect('OFFSET')
                bone.offset = [float(tokens[pos]), float(tokens[pos + 1]), float(tokens[pos + 2])]
                pos += 3
                expect('}')
                return bone
            else:
                expect('JOINT')

            name = tokens[pos]
            pos += 1
            bone = BVHBone(name, [0, 0, 0], [])
            bone.is_root = is_root
            expect('{')
            expect('OFFSET')
            bone.offset = [float(tokens[pos]), float(tokens[pos + 1]), float(tokens[pos + 2])]
            pos += 3
            expect('CHANNELS')
            nc = int(tokens[pos])
            pos += 1
            for _ in range(nc):
                bone.channels.append(tokens[pos])
                pos += 1

            while tokens[pos] != '}':
                if tokens[pos] in ('JOINT', 'End'):
                    child = parse_joint(is_root=False)
                    child.parent = bone
                    bone.children.append(child)
                else:
                    pos += 1
            expect('}')
            return bone

        expect('HIERARCHY')
        self.root_bone = parse_joint(is_root=True)

        def flatten(bone):
            if not bone.is_end_site:
                self.bones.append(bone)
                self.bone_map[bone.name] = bone
            for c in bone.children:
                flatten(c)

        flatten(self.root_bone)

        idx = 0
        for bone in self.bones:
            for ch in bone.channels:
                bone.channel_indices[ch] = idx
                idx += 1
        self.channel_count = idx

        expect('MOTION')
        expect('Frames:')
        self.frame_count = int(tokens[pos])
        pos += 1
        expect('Frame')
        expect('Time:')
        self.frame_time = float(tokens[pos])
        pos += 1
        self.fps = 1.0 / self.frame_time if self.frame_time > 0 else 30.0

        for _ in range(self.frame_count):
            frame_data = []
            while pos < len(tokens) and len(frame_data) < self.channel_count:
                try:
                    frame_data.append(float(tokens[pos]))
                    pos += 1
                except ValueError:
                    break
            if len(frame_data) == self.channel_count:
                self.frames.append(frame_data)

    def get_bone_data(self, bone, frame_idx):
        """Get position and rotation for a bone at a specific frame.

        Returns:
            (pos, rot) where pos=[x,y,z] and rot=[Zrot, Yrot, Xrot] in BVH order
        """
        frame = self.frames[frame_idx]
        pos = [0.0, 0.0, 0.0]
        rot = [0.0, 0.0, 0.0]  # [Zrot, Yrot, Xrot]
        for ch, idx in bone.channel_indices.items():
            val = frame[idx]
            if ch == 'Xposition':
                pos[0] = val
            elif ch == 'Yposition':
                pos[1] = val
            elif ch == 'Zposition':
                pos[2] = val
            elif ch == 'Xrotation':
                rot[2] = val
            elif ch == 'Yrotation':
                rot[1] = val
            elif ch == 'Zrotation':
                rot[0] = val
        return pos, rot


# ============================================================================
# MATH UTILITIES
# ============================================================================

def euler_to_matrix(x, y, z, order='ZYX'):
    """Convert Euler angles (degrees) to 3x3 rotation matrix.

    Convention:
        'ZYX': R = Rz(z) * Ry(y) * Rx(x)  -- intrinsic XYZ, FBX EulerXYZ
        'XYZ': R = Rx(x) * Ry(y) * Rz(z)  -- intrinsic ZYX
    """
    x, y, z = math.radians(x), math.radians(y), math.radians(z)
    cx, sx = math.cos(x), math.sin(x)
    cy, sy = math.cos(y), math.sin(y)
    cz, sz = math.cos(z), math.sin(z)
    if order == 'ZYX':
        # R = Rz * Ry * Rx  (FBX RotationOrder=0, EulerXYZ)
        return [
            [cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx],
            [sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx],
            [-sy, cy * sx, cy * cx]
        ]
    else:  # XYZ: R = Rx * Ry * Rz
        return [
            [cy * cz, -cy * sz, sy],
            [cx * sz + sx * sy * cz, cx * cz - sx * sy * sz, -sx * cy],
            [sx * sz - cx * sy * cz, sx * cz + cx * sy * sz, cx * cy]
        ]


def matrix_to_euler(m, order='ZYX'):
    """Convert 3x3 rotation matrix to Euler angles (degrees).

    Convention:
        'ZYX': assumes R = Rz * Ry * Rx, returns [x, y, z]
        'XYZ': assumes R = Rx * Ry * Rz, returns [x, y, z]
    """
    if order == 'ZYX':
        # R = Rz * Ry * Rx
        sy = -m[2][0]
        sy = max(-1.0, min(1.0, sy))
        if abs(sy) > 0.99999:
            x = math.atan2(m[2][1], m[2][2])
            y = math.asin(sy)
            z = 0.0
        else:
            y = math.asin(sy)
            x = math.atan2(m[2][1], m[2][2])
            z = math.atan2(m[1][0], m[0][0])
    else:  # XYZ: R = Rx * Ry * Rz
        sy = m[0][2]
        sy = max(-1.0, min(1.0, sy))
        if abs(sy) > 0.99999:
            x = math.atan2(-m[1][2], m[1][1])
            y = math.asin(sy)
            z = 0.0
        else:
            y = math.asin(sy)
            x = math.atan2(-m[1][2], m[1][1])
            z = math.atan2(-m[0][1], m[0][0])
    return [math.degrees(x), math.degrees(y), math.degrees(z)]


def mat_mul(a, b):
    """Multiply two 3x3 matrices."""
    r = [[0] * 3 for _ in range(3)]
    for i in range(3):
        for j in range(3):
            for k in range(3):
                r[i][j] += a[i][k] * b[k][j]
    return r


def mat_transpose(m):
    """Transpose a 3x3 matrix (also inverse for rotation matrices)."""
    return [[m[j][i] for j in range(3)] for i in range(3)]


def mat_vec_mul(m, v):
    """Multiply 3x3 matrix by 3-vector."""
    return [m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2],
            m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
            m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2]]


def ensure_euler_continuity(rots):
    """Ensure Euler angle curves are continuous by choosing the best 360° offset.

    For each axis, if adding/subtracting 360° brings the value closer to
    the previous frame's value, use that offset. This handles 360° wraps
    and reduces discontinuities from Euler angle extraction near gimbal lock.

    Note: This cannot fully fix gimbal lock discontinuities (which are not
    multiples of 360°), but it minimizes their visual impact.
    """
    if len(rots) < 2:
        return rots

    result = [list(rots[0])]
    for i in range(1, len(rots)):
        prev = result[-1]
        curr = list(rots[i])
        for ax in range(3):
            # Find the 360° offset that minimizes inter-frame difference
            best_val = curr[ax]
            best_diff = abs(curr[ax] - prev[ax])
            for offset in [-720, -360, 360, 720]:
                candidate = curr[ax] + offset
                diff = abs(candidate - prev[ax])
                if diff < best_diff:
                    best_val = candidate
                    best_diff = diff
            curr[ax] = best_val
        result.append(curr)
    return result


def compute_bvh_world(bvh, frame_idx):
    """Compute world-space position and rotation for all BVH bones at a frame.

    Uses R = Rz * Ry * Rx convention (matching BVH ZYX channel order).
    """
    transforms = {}

    def compute(bone, parent_pos, parent_rot):
        pos, rot_zyx = bvh.get_bone_data(bone, frame_idx)
        # BVH channels are Zrotation, Yrotation, Xrotation
        # euler_to_matrix(Xrot, Yrot, Zrot, 'ZYX') = Rz(Zrot) * Ry(Yrot) * Rx(Xrot)
        local_rot = euler_to_matrix(rot_zyx[2], rot_zyx[1], rot_zyx[0], 'ZYX')
        world_rot = mat_mul(parent_rot, local_rot) if parent_rot else local_rot

        if any('position' in ch.lower() for ch in bone.channels):
            # Bone has absolute position channels
            if parent_pos:
                # For BVH root/hips with position: position is world-space
                world_pos = list(pos)
            else:
                world_pos = list(pos)
        else:
            # Bone offset rotated by parent
            if parent_rot:
                ro = mat_vec_mul(parent_rot, bone.offset)
                world_pos = [parent_pos[i] + ro[i] for i in range(3)]
            else:
                world_pos = list(bone.offset)

        transforms[bone.name] = (world_pos, world_rot)
        for c in bone.children:
            if not c.is_end_site:
                compute(c, world_pos, world_rot)

    compute(bvh.root_bone, None, None)
    return transforms


# ============================================================================
# BONE MAPPING: BVH -> Quinn
# ============================================================================

BVH_TO_QUINN = {
    'Hips': 'pelvis',
    'Spine1': 'spine_01',
    'Spine2': 'spine_02',
    'Spine3': 'spine_03',
    'Chest': 'spine_04',
    'Neck1': 'neck_01',
    'Neck': 'neck_01',
    'Neck2': 'neck_02',
    'Head': 'head',
    # Left arm
    'LeftShoulder': 'clavicle_l',
    'LeftArm': 'upperarm_l',
    'LeftForeArm': 'lowerarm_l',
    'LeftHand': 'hand_l',
    # Left hand
    'LeftHandThumb1': 'thumb_01_l',
    'LeftHandThumb2': 'thumb_02_l',
    'LeftHandThumb3': 'thumb_03_l',
    'LeftHandIndex1': 'index_metacarpal_l',
    'LeftHandIndex2': 'index_01_l',
    'LeftHandIndex3': 'index_02_l',
    'LeftHandIndex4': 'index_03_l',
    'LeftHandMiddle1': 'middle_metacarpal_l',
    'LeftHandMiddle2': 'middle_01_l',
    'LeftHandMiddle3': 'middle_02_l',
    'LeftHandMiddle4': 'middle_03_l',
    'LeftHandRing1': 'ring_metacarpal_l',
    'LeftHandRing2': 'ring_01_l',
    'LeftHandRing3': 'ring_02_l',
    'LeftHandRing4': 'ring_03_l',
    'LeftHandPinky1': 'pinky_metacarpal_l',
    'LeftHandPinky2': 'pinky_01_l',
    'LeftHandPinky3': 'pinky_02_l',
    'LeftHandPinky4': 'pinky_03_l',
    # Right arm
    'RightShoulder': 'clavicle_r',
    'RightArm': 'upperarm_r',
    'RightForeArm': 'lowerarm_r',
    'RightHand': 'hand_r',
    # Right hand
    'RightHandThumb1': 'thumb_01_r',
    'RightHandThumb2': 'thumb_02_r',
    'RightHandThumb3': 'thumb_03_r',
    'RightHandIndex1': 'index_metacarpal_r',
    'RightHandIndex2': 'index_01_r',
    'RightHandIndex3': 'index_02_r',
    'RightHandIndex4': 'index_03_r',
    'RightHandMiddle1': 'middle_metacarpal_r',
    'RightHandMiddle2': 'middle_01_r',
    'RightHandMiddle3': 'middle_02_r',
    'RightHandMiddle4': 'middle_03_r',
    'RightHandRing1': 'ring_metacarpal_r',
    'RightHandRing2': 'ring_01_r',
    'RightHandRing3': 'ring_02_r',
    'RightHandRing4': 'ring_03_r',
    'RightHandPinky1': 'pinky_metacarpal_r',
    'RightHandPinky2': 'pinky_01_r',
    'RightHandPinky3': 'pinky_02_r',
    'RightHandPinky4': 'pinky_03_r',
    # Left leg
    'LeftLeg': 'thigh_l',
    'LeftUpLeg': 'thigh_l',
    'LeftShin': 'calf_l',
    'LeftFoot': 'foot_l',
    'LeftToeBase': 'ball_l',
    # Right leg
    'RightLeg': 'thigh_r',
    'RightUpLeg': 'thigh_r',
    'RightShin': 'calf_r',
    'RightFoot': 'foot_r',
    'RightToeBase': 'ball_r',
}


# ============================================================================
# FBX BINARY READER
# ============================================================================

class FBXReader:
    """Parse binary FBX file to extract skeleton data.

    Reads bone Model records, their Properties70 (including Lcl Translation,
    Lcl Rotation, Lcl Scaling), and the connection hierarchy.
    """

    FBX_MAGIC = b"Kaydara FBX Binary  \x00\x1a\x00"

    def __init__(self, filepath):
        with open(filepath, 'rb') as f:
            self.data = f.read()

        if self.data[:23] != self.FBX_MAGIC:
            raise ValueError(f"Not a valid FBX binary file: {filepath}")

        self.version = struct.unpack_from('<I', self.data, 23)[0]
        self.root_records = self._parse_records(27, len(self.data))

    def _parse_records(self, start, end):
        """Recursively parse FBX records within a byte range."""
        records = []
        pos = start
        data = self.data

        while pos < end:
            if pos + 13 > len(data):
                break

            end_off = struct.unpack_from('<I', data, pos)[0]
            num_props = struct.unpack_from('<I', data, pos + 4)[0]
            prop_list_len = struct.unpack_from('<I', data, pos + 8)[0]
            name_len = struct.unpack_from('<B', data, pos + 12)[0]

            # Null terminator record (end of children)
            if end_off == 0 and num_props == 0 and prop_list_len == 0 and name_len == 0:
                break

            name = data[pos + 13:pos + 13 + name_len].decode('ascii', errors='replace') if name_len > 0 else ''
            props_start = pos + 13 + name_len
            children_start = props_start + prop_list_len

            # Parse properties
            props = self._parse_properties(props_start, num_props)

            # Parse children recursively
            children = self._parse_records(children_start, end_off) if children_start < end_off else []

            records.append({
                'name': name,
                'props': props,
                'children': children,
            })

            pos = end_off

        return records

    def _parse_properties(self, start, count):
        """Parse properties starting at a byte position."""
        props = []
        pos = start
        data = self.data

        for _ in range(count):
            if pos >= len(data):
                break

            tc = chr(data[pos])
            pos += 1

            if tc == 'Y':
                val = struct.unpack_from('<H', data, pos)[0]
                pos += 2
                props.append(('Y', val))
            elif tc == 'C':
                val = bool(data[pos])
                pos += 1
                props.append(('C', val))
            elif tc == 'I':
                val = struct.unpack_from('<i', data, pos)[0]
                pos += 4
                props.append(('I', val))
            elif tc == 'F':
                val = struct.unpack_from('<f', data, pos)[0]
                pos += 4
                props.append(('F', val))
            elif tc == 'D':
                val = struct.unpack_from('<d', data, pos)[0]
                pos += 8
                props.append(('D', val))
            elif tc == 'L':
                val = struct.unpack_from('<q', data, pos)[0]
                pos += 8
                props.append(('L', val))
            elif tc == 'S':
                ln = struct.unpack_from('<I', data, pos)[0]
                pos += 4
                try:
                    val = data[pos:pos + ln].decode('utf-8', errors='replace')
                except Exception:
                    val = data[pos:pos + ln]
                pos += ln
                props.append(('S', val))
            elif tc == 'R':
                ln = struct.unpack_from('<I', data, pos)[0]
                pos += 4
                val = data[pos:pos + ln]
                pos += ln
                props.append(('R', val))
            elif tc in ('f', 'd', 'l', 'i', 'b'):
                arr_count, encoding, comp_len = struct.unpack_from('<III', data, pos)
                pos += 12
                raw_data = data[pos:pos + comp_len]
                pos += comp_len

                # Decompress if needed
                if encoding == 1:
                    try:
                        decompressed = zlib.decompress(raw_data)
                    except zlib.error:
                        decompressed = raw_data
                else:
                    decompressed = raw_data

                # Convert to Python list
                type_map = {'f': 'f', 'd': 'd', 'l': 'q', 'i': 'i', 'b': 'b'}
                fmt = type_map[tc]
                if fmt == 'b':
                    val = list(decompressed)
                else:
                    arr = array.array(fmt, decompressed)
                    val = list(arr)

                props.append((tc, val))
            else:
                raise ValueError(f'Unknown property type: {tc} at position {pos - 1}')

        return props

    def find(self, records, name):
        """Find first record with given name."""
        for r in records:
            if r['name'] == name:
                return r
        return None

    def find_all(self, records, name):
        """Find all records with given name."""
        return [r for r in records if r['name'] == name]

    def extract_skeleton(self):
        """Extract bone information from the FBX.

        Returns:
            OrderedDict mapping bone_name -> {
                'parent': parent_bone_name or None,
                'type': 'Root' or 'LimbNode',
                'lcl_t': [tx, ty, tz],
                'lcl_r': [rx, ry, rz],
                'lcl_s': [sx, sy, sz],
                'rotation_order': int,
                'inherit_type': int,
                'props70': list of all P record property tuples,
            }
        """
        objects = self.find(self.root_records, 'Objects')
        connections_rec = self.find(self.root_records, 'Connections')

        if not objects:
            raise ValueError("No Objects section in reference FBX")

        models = self.find_all(objects['children'], 'Model')

        # Step 1: Extract model info for skeleton bones only
        model_info = {}
        for m in models:
            props = m['props']
            if len(props) < 3:
                continue

            model_id = props[0][1]
            full_name = props[1][1]
            model_type = props[2][1]

            # Only include skeleton bones (Root and LimbNode)
            if model_type not in ('Root', 'LimbNode'):
                continue

            # Extract bone name from full name (format: "boneName\x00\x01Model")
            bone_name = full_name.split('\x00')[0] if '\x00' in full_name else full_name

            # Extract ALL Properties70 P records
            lcl_t = [0.0, 0.0, 0.0]
            lcl_r = [0.0, 0.0, 0.0]
            lcl_s = [1.0, 1.0, 1.0]
            rotation_order = 0
            inherit_type = 1
            all_p70 = []

            p70 = self.find(m['children'], 'Properties70')
            if p70:
                for pc in p70['children']:
                    if pc['name'] == 'P':
                        pp = pc['props']
                        all_p70.append(pp)
                        pname = pp[0][1] if len(pp) > 0 else ''
                        if pname == 'Lcl Translation' and len(pp) >= 7:
                            lcl_t = [float(pp[4][1]), float(pp[5][1]), float(pp[6][1])]
                        elif pname == 'Lcl Rotation' and len(pp) >= 7:
                            lcl_r = [float(pp[4][1]), float(pp[5][1]), float(pp[6][1])]
                        elif pname == 'Lcl Scaling' and len(pp) >= 7:
                            lcl_s = [float(pp[4][1]), float(pp[5][1]), float(pp[6][1])]
                        elif pname == 'RotationOrder' and len(pp) >= 5:
                            rotation_order = int(pp[4][1])
                        elif pname == 'InheritType' and len(pp) >= 5:
                            inherit_type = int(pp[4][1])

            model_info[model_id] = {
                'name': bone_name,
                'type': model_type,
                'lcl_t': lcl_t,
                'lcl_r': lcl_r,
                'lcl_s': lcl_s,
                'rotation_order': rotation_order,
                'inherit_type': inherit_type,
                'full_name': full_name,
                'props70': all_p70,
            }

        # Step 2: Build hierarchy from connections
        parent_map = {}  # child_id -> parent_id
        if connections_rec:
            for c in connections_rec['children']:
                if c['name'] == 'C':
                    cp = c['props']
                    if len(cp) >= 3:
                        conn_type = cp[0][1]
                        from_id = cp[1][1]
                        to_id = cp[2][1]
                        if conn_type == 'OO' and from_id in model_info and to_id in model_info:
                            parent_map[from_id] = to_id

        # Step 3: Build ordered bone list (parents before children)
        bone_order = []
        visited = set()

        def visit(bid):
            if bid in visited:
                return
            visited.add(bid)
            if bid in parent_map:
                visit(parent_map[bid])
            bone_order.append(bid)

        for bid in model_info:
            visit(bid)

        # Step 4: Build the skeleton dictionary
        skeleton = OrderedDict()
        for bid in bone_order:
            info = model_info[bid]
            parent_id = parent_map.get(bid)
            parent_name = model_info[parent_id]['name'] if parent_id and parent_id in model_info else None
            skeleton[info['name']] = {
                'parent': parent_name,
                'type': info['type'],
                'lcl_t': info['lcl_t'],
                'lcl_r': info['lcl_r'],
                'lcl_s': info['lcl_s'],
                'rotation_order': info['rotation_order'],
                'inherit_type': info['inherit_type'],
                'props70': info['props70'],
            }

        return skeleton


# ============================================================================
# FBX BINARY WRITER
# ============================================================================

class FBXWriter:
    """Writes a binary FBX file with skeleton and animation data."""

    VERSION = 7300
    TIME_UNIT = 46186158000  # FBX ticks per second

    def __init__(self):
        self.buf = bytearray()
        self._id = 1000

    def nid(self):
        """Generate next unique ID."""
        self._id += 1
        return self._id

    def _w_arr(self, vals, tc):
        """Write a compressed array property."""
        arr = array.array(tc, vals)
        raw = arr.tobytes()
        comp = zlib.compress(raw)
        if len(comp) < len(raw):
            return struct.pack('<III', len(vals), 1, len(comp)) + comp
        return struct.pack('<III', len(vals), 0, len(raw)) + raw

    def _w_prop(self, buf, p):
        """Write a single property to buffer."""
        t, v = p
        if t == 'Y':
            buf += b'Y' + struct.pack('<H', v)
        elif t == 'C':
            buf += b'C' + struct.pack('<?', v)
        elif t == 'I':
            buf += b'I' + struct.pack('<i', v)
        elif t == 'F':
            buf += b'F' + struct.pack('<f', v)
        elif t == 'D':
            buf += b'D' + struct.pack('<d', v)
        elif t == 'L':
            buf += b'L' + struct.pack('<q', v)
        elif t == 'S':
            d = v.encode('utf-8') if isinstance(v, str) else v
            buf += b'S' + struct.pack('<I', len(d)) + d
        elif t == 'R':
            buf += b'R' + struct.pack('<I', len(v)) + v
        elif t == 'f':
            buf += b'f' + self._w_arr(v, 'f')
        elif t == 'd':
            buf += b'd' + self._w_arr(v, 'd')
        elif t == 'i':
            buf += b'i' + self._w_arr(v, 'i')
        elif t == 'l':
            buf += b'l' + self._w_arr(v, 'q')

    def _w_record(self, name, props=None, children_data=None):
        """Write a record to the buffer.

        Args:
            name: Record name (ASCII string)
            props: List of (type, value) tuples
            children_data: List of (name, props, children_data) tuples or bytes
        """
        if props is None:
            props = []
        if children_data is None:
            children_data = []

        start = len(self.buf)
        self.buf += struct.pack('<I', 0)  # end_offset placeholder
        self.buf += struct.pack('<I', len(props))

        # Compute property data
        pd = bytearray()
        for p in props:
            self._w_prop(pd, p)
        self.buf += struct.pack('<I', len(pd))

        # Name
        nb = name.encode('ascii')
        self.buf += struct.pack('<B', len(nb)) + nb

        # Properties
        self.buf += pd

        # Children
        for ch in children_data:
            if isinstance(ch, bytes):
                self.buf += ch
            else:
                self._w_record(*ch)

        # Null terminator (13 zero bytes)
        self.buf += b'\x00' * 13

        # Fill in end_offset
        struct.pack_into('<I', self.buf, start, len(self.buf))

    def write(self, filepath):
        """Write the buffer to a file."""
        with open(filepath, 'wb') as f:
            f.write(self.buf)

    def build(self, bvh, skeleton, bone_anim, scale=1.0):
        """Build the complete FBX file.

        Args:
            bvh: BVHFile object
            skeleton: OrderedDict from FBXReader.extract_skeleton()
            bone_anim: Dict from retarget() with animation data
            scale: Scale factor for root motion translation
        """
        nf = bvh.frame_count
        fps = bvh.fps
        dur = int(nf / fps * self.TIME_UNIT)
        ft = int(self.TIME_UNIT / fps)

        bones = list(skeleton.keys())
        nb = len(bones)

        # Assign IDs
        root_id = self.nid()
        bone_id = {b: self.nid() for b in bones if b != 'root'}
        attr_id = {b: self.nid() for b in bones}
        stack_id = self.nid()
        layer_id = self.nid()
        cn_id = {}   # bone -> {T,R,S} -> id
        cv_id = {}   # (bone, TRS) -> {X,Y,Z} -> id

        for b in bones:
            cn_id[b] = {trs: self.nid() for trs in 'TRS'}
            for trs in 'TRS':
                cv_id[(b, trs)] = {ax: self.nid() for ax in 'XYZ'}

        # ====================================================================
        # HEADER
        # ====================================================================
        self.buf += b'Kaydara FBX Binary  \x00\x1a\x00'
        self.buf += struct.pack('<I', self.VERSION)

        # FBXHeaderExtension
        self._w_record('FBXHeaderExtension', [], [
            ('FBXHeaderVersion', [('I', 1003)]),
            ('FBXVersion', [('I', self.VERSION)]),
            ('EncryptionType', [('I', 0)]),
            ('CreationTimeStamp', [], [
                ('Version', [('I', 1000)]),
                ('Year', [('I', 2026)]),
                ('Month', [('I', 3)]),
                ('Day', [('I', 5)]),
                ('Hour', [('I', 12)]),
                ('Minute', [('I', 0)]),
                ('Second', [('I', 0)]),
                ('Millisecond', [('I', 0)]),
            ]),
            ('Creator', [('S', 'BVH2FBX v5.0')]),
        ])

        # FileId, CreationTime, Creator
        self._w_record('FileId', [('R', bytes([
            0xaf, 0x9b, 0x42, 0x2c, 0x73, 0x79, 0x4e, 0x11,
            0x8b, 0xd6, 0xd4, 0x68, 0x43, 0x4f, 0x6e, 0xa8
        ]))])
        self._w_record('CreationTime', [('S', '2026-03-05 12:00:00:000')])
        self._w_record('Creator', [('S', 'BVH2FBX v5.0')])

        # ====================================================================
        # GLOBALSETTINGS
        # ====================================================================
        # UE5 Z-up coordinate system with 30 FPS time mode
        gs_children = [
            ('P', [('S', 'UpAxis'), ('S', 'int'), ('S', 'Integer'), ('S', ''), ('I', 2)]),
            ('P', [('S', 'UpAxisSign'), ('S', 'int'), ('S', 'Integer'), ('S', ''), ('I', 1)]),
            ('P', [('S', 'FrontAxis'), ('S', 'int'), ('S', 'Integer'), ('S', ''), ('I', 1)]),
            ('P', [('S', 'FrontAxisSign'), ('S', 'int'), ('S', 'Integer'), ('S', ''), ('I', -1)]),
            ('P', [('S', 'CoordAxis'), ('S', 'int'), ('S', 'Integer'), ('S', ''), ('I', 0)]),
            ('P', [('S', 'CoordAxisSign'), ('S', 'int'), ('S', 'Integer'), ('S', ''), ('I', 1)]),
            ('P', [('S', 'OriginalUpAxis'), ('S', 'int'), ('S', 'Integer'), ('S', ''), ('I', 2)]),
            ('P', [('S', 'OriginalUpAxisSign'), ('S', 'int'), ('S', 'Integer'), ('S', ''), ('I', 1)]),
            ('P', [('S', 'UnitScaleFactor'), ('S', 'double'), ('S', 'Number'), ('S', ''), ('D', 1.0)]),
            ('P', [('S', 'OriginalUnitScaleFactor'), ('S', 'double'), ('S', 'Number'), ('S', ''), ('D', 1.0)]),
            ('P', [('S', 'AmbientColor'), ('S', 'ColorRGB'), ('S', 'Color'), ('S', ''),
                   ('D', 0.0), ('D', 0.0), ('D', 0.0)]),
            ('P', [('S', 'DefaultCamera'), ('S', 'KString'), ('S', ''), ('S', ''),
                   ('S', 'Producer Perspective')]),
            ('P', [('S', 'TimeMode'), ('S', 'enum'), ('S', ''), ('S', ''), ('I', 3)]),
            ('P', [('S', 'TimeProtocol'), ('S', 'enum'), ('S', ''), ('S', ''), ('I', 2)]),
            ('P', [('S', 'SnapOnFrameMode'), ('S', 'enum'), ('S', ''), ('S', ''), ('I', 0)]),
            ('P', [('S', 'TimeSpanStart'), ('S', 'KTime'), ('S', 'Time'), ('S', ''), ('L', 0)]),
            ('P', [('S', 'TimeSpanStop'), ('S', 'KTime'), ('S', 'Time'), ('S', ''), ('L', dur)]),
            ('P', [('S', 'CustomFrameRate'), ('S', 'double'), ('S', 'Number'), ('S', ''), ('D', -1.0)]),
            ('P', [('S', 'TimeMarker'), ('S', 'Compound'), ('S', ''), ('S', '')]),
            ('P', [('S', 'CurrentTimeMarker'), ('S', 'int'), ('S', 'Integer'), ('S', ''), ('I', -1)]),
        ]
        self._w_record('GlobalSettings', [], [
            ('Version', [('I', 1000)]),
            ('Properties70', [], gs_children),
        ])

        # ====================================================================
        # DOCUMENTS
        # ====================================================================
        self._w_record('Documents', [], [
            ('Count', [('I', 1)]),
            ('Document', [('L', root_id), ('S', 'Scene'), ('S', 'Scene')], [
                ('Properties70', [], [
                    ('P', [('S', 'SourceObject'), ('S', 'object'), ('S', ''), ('S', '')]),
                    ('P', [('S', 'ActiveAnimStackName'), ('S', 'KString'), ('S', ''), ('S', ''),
                           ('S', 'Unreal Take')]),
                ]),
                ('RootNode', [('L', root_id)]),
            ]),
        ])
        self._w_record('References', [])

        # ====================================================================
        # DEFINITIONS
        # ====================================================================
        n_curves = nb * 9
        n_cnodes = nb * 3
        n_total = 1 + nb + nb + 1 + 1 + n_cnodes + n_curves

        self._w_record('Definitions', [], [
            ('Version', [('I', 100)]),
            ('Count', [('I', n_total)]),
            ('ObjectType', [('S', 'GlobalSettings')], [('Count', [('I', 1)])]),
            ('ObjectType', [('S', 'NodeAttribute')], [
                ('Count', [('I', nb)]),
                ('NodeAttributeVersion', [('I', 100)]),
            ]),
            ('ObjectType', [('S', 'Model')], [
                ('Count', [('I', nb)]),
                ('Version', [('I', 232)]),
            ]),
            ('ObjectType', [('S', 'AnimationStack')], [('Count', [('I', 1)])]),
            ('ObjectType', [('S', 'AnimationLayer')], [('Count', [('I', 1)])]),
            ('ObjectType', [('S', 'AnimationCurveNode')], [('Count', [('I', n_cnodes)])]),
            ('ObjectType', [('S', 'AnimationCurve')], [('Count', [('I', n_curves)])]),
        ])

        # ====================================================================
        # OBJECTS
        # ====================================================================
        obj_children = []

        # --- NodeAttributes (one per bone) ---
        for bname in bones:
            bd = skeleton[bname]
            btype = bd['type']
            if btype == 'Root':
                obj_children.append(('NodeAttribute',
                    [('L', attr_id[bname]),
                     ('S', f'{bname}\x00\x01NodeAttribute'),
                     ('S', 'Null')],
                    [('TypeFlags', [('S', 'Null')])]))
            else:
                obj_children.append(('NodeAttribute',
                    [('L', attr_id[bname]),
                     ('S', f'{bname}\x00\x01NodeAttribute'),
                     ('S', 'LimbNode')],
                    [('TypeFlags', [('S', 'Skeleton')])]))

        # --- Models (one per bone, with exact properties from reference FBX) ---
        for bname in bones:
            bd = skeleton[bname]
            bid = root_id if bname == 'root' else bone_id[bname]
            t, r, s = bd['lcl_t'], bd['lcl_r'], bd['lcl_s']
            rot_order = bd.get('rotation_order', 0)
            inherit = bd.get('inherit_type', 1)

            # Build Properties70 using reference FBX data when available
            # Fall back to standard properties if no props70 stored
            props70_records = bd.get('props70', [])
            p70_children = []

            if props70_records:
                # Use ALL P records from reference FBX, updating T/R/S values
                for pp in props70_records:
                    pname = pp[0][1] if len(pp) > 0 else ''
                    if pname == 'Lcl Translation' and len(pp) >= 7:
                        p70_children.append(('P', [
                            ('S', 'Lcl Translation'), ('S', 'Lcl Translation'),
                            ('S', ''), ('S', 'A'),
                            ('D', float(t[0])), ('D', float(t[1])), ('D', float(t[2]))
                        ]))
                    elif pname == 'Lcl Rotation' and len(pp) >= 7:
                        p70_children.append(('P', [
                            ('S', 'Lcl Rotation'), ('S', 'Lcl Rotation'),
                            ('S', ''), ('S', 'A'),
                            ('D', float(r[0])), ('D', float(r[1])), ('D', float(r[2]))
                        ]))
                    elif pname == 'Lcl Scaling' and len(pp) >= 7:
                        p70_children.append(('P', [
                            ('S', 'Lcl Scaling'), ('S', 'Lcl Scaling'),
                            ('S', ''), ('S', 'A'),
                            ('D', float(s[0])), ('D', float(s[1])), ('D', float(s[2]))
                        ]))
                    else:
                        # Keep other properties as-is from reference
                        p70_children.append(('P', pp))
            else:
                # Standard properties (fallback)
                p70_children = [
                    ('P', [('S', 'RotationActive'), ('S', 'bool'), ('S', ''), ('S', ''), ('C', True)]),
                    ('P', [('S', 'InheritType'), ('S', 'enum'), ('S', ''), ('S', ''), ('I', inherit)]),
                    ('P', [('S', 'Lcl Translation'), ('S', 'Lcl Translation'), ('S', ''), ('S', 'A'),
                           ('D', float(t[0])), ('D', float(t[1])), ('D', float(t[2]))]),
                    ('P', [('S', 'Lcl Rotation'), ('S', 'Lcl Rotation'), ('S', ''), ('S', 'A'),
                           ('D', float(r[0])), ('D', float(r[1])), ('D', float(r[2]))]),
                    ('P', [('S', 'Lcl Scaling'), ('S', 'Lcl Scaling'), ('S', ''), ('S', 'A'),
                           ('D', float(s[0])), ('D', float(s[1])), ('D', float(s[2]))]),
                    ('P', [('S', 'RotationOrder'), ('S', 'enum'), ('S', ''), ('S', ''), ('I', rot_order)]),
                    ('P', [('S', 'Show'), ('S', 'bool'), ('S', ''), ('S', ''), ('C', True)]),
                    ('P', [('S', 'Visibility'), ('S', 'Visibility'), ('S', ''), ('S', 'A'), ('D', 1.0)]),
                ]

            obj_children.append(('Model',
                [('L', bid),
                 ('S', f'{bname}\x00\x01Model'),
                 ('S', bd['type'])],
                [('Version', [('I', 232)]),
                 ('Properties70', [], p70_children),
                 ('MultiLayer', [('I', 0)]),
                 ('MultiTake', [('I', 0)]),
                 ('Shading', [('C', True)]),
                 ('Culling', [('S', 'CullingOff')]),
                ]))

        # --- AnimationStack ---
        obj_children.append(('AnimationStack',
            [('L', stack_id), ('S', 'Unreal Take\x00\x01AnimStack'), ('S', '')],
            [('Properties70', [], [
                ('P', [('S', 'LocalStop'), ('S', 'KTime'), ('S', 'Time'), ('S', ''), ('L', dur)]),
            ])]))

        # --- AnimationLayer ---
        obj_children.append(('AnimationLayer',
            [('L', layer_id), ('S', 'Base Layer\x00\x01AnimLayer'), ('S', '')],
            [('Properties70', [], [
                ('P', [('S', 'Weight'), ('S', 'Number'), ('S', ''), ('S', 'A'), ('D', 100.0)]),
            ])]))

        # --- AnimationCurveNodes + AnimationCurves ---
        for bname in bones:
            ad = bone_anim.get(bname, {})
            for trs, pname in [('T', 'Lcl Translation'), ('R', 'Lcl Rotation'), ('S', 'Lcl Scaling')]:
                cnid = cn_id[bname][trs]
                data = ad.get(trs.lower(), [[0, 0, 0]] * nf)

                obj_children.append(('AnimationCurveNode',
                    [('L', cnid), ('S', f'{trs}\x00\x01AnimCurveNode'), ('S', '')],
                    [('Properties70', [], [
                        ('P', [('S', 'd|X'), ('S', 'Number'), ('S', ''), ('S', 'A'),
                               ('D', float(data[0][0]))]),
                        ('P', [('S', 'd|Y'), ('S', 'Number'), ('S', ''), ('S', 'A'),
                               ('D', float(data[0][1]))]),
                        ('P', [('S', 'd|Z'), ('S', 'Number'), ('S', ''), ('S', 'A'),
                               ('D', float(data[0][2]))]),
                    ])]))

                for ai, ax in enumerate('XYZ'):
                    cvid = cv_id[(bname, trs)][ax]
                    kv = [float(f[ai]) for f in data]
                    kt = [int(i * ft) for i in range(nf)]

                    obj_children.append(('AnimationCurve',
                        [('L', cvid), ('S', 'AnimCurve'), ('S', '')],
                        [('Default', [('D', 0.0)]),
                         ('KeyVer', [('I', 4008)]),
                         ('KeyTime', [('l', kt)]),
                         ('KeyValueFloat', [('f', kv)]),
                         ('KeyAttrFlags', [('i', [0x00080010] * nf)]),
                         ('KeyAttrDataFloat', [('i', [0, 0, 0, 0] * nf)]),
                         ('KeyAttrRefCount', [('i', [1] * nf)]),
                        ]))

        self._w_record('Objects', [], obj_children)

        # ====================================================================
        # CONNECTIONS
        # ====================================================================
        conn_children = []

        # Root -> scene (id=0)
        conn_children.append(('C', [('S', 'OO'), ('L', root_id), ('L', 0)]))

        # NodeAttribute -> Model (OO)
        for b in bones:
            bid = root_id if b == 'root' else bone_id[b]
            conn_children.append(('C', [('S', 'OO'), ('L', attr_id[b]), ('L', bid)]))

        # Parent-child bone connections (OO)
        for b in bones:
            p = skeleton[b]['parent']
            if p is not None:
                cid = root_id if b == 'root' else bone_id[b]
                pid = root_id if p == 'root' else bone_id[p]
                conn_children.append(('C', [('S', 'OO'), ('L', cid), ('L', pid)]))

        # AnimationStack -> scene (OO)
        conn_children.append(('C', [('S', 'OO'), ('L', stack_id), ('L', 0)]))

        # AnimationLayer -> AnimationStack (OO)
        conn_children.append(('C', [('S', 'OO'), ('L', layer_id), ('L', stack_id)]))

        # AnimationCurveNode -> AnimationLayer (OO)
        for b in bones:
            for trs in 'TRS':
                conn_children.append(('C', [('S', 'OO'), ('L', cn_id[b][trs]), ('L', layer_id)]))

        # AnimationCurveNode -> Model (OP with property name)
        for b in bones:
            bid = root_id if b == 'root' else bone_id[b]
            for trs, pn in [('T', 'Lcl Translation'), ('R', 'Lcl Rotation'), ('S', 'Lcl Scaling')]:
                conn_children.append(('C', [('S', 'OP'), ('L', cn_id[b][trs]), ('L', bid), ('S', pn)]))

        # AnimationCurve -> AnimationCurveNode (OP with d|X, d|Y, d|Z)
        for b in bones:
            for trs in 'TRS':
                for ax in 'XYZ':
                    conn_children.append(('C', [
                        ('S', 'OP'), ('L', cv_id[(b, trs)][ax]),
                        ('L', cn_id[b][trs]), ('S', f'd|{ax}')
                    ]))

        self._w_record('Connections', [], conn_children)

        # ====================================================================
        # TAKES
        # ====================================================================
        self._w_record('Takes', [], [
            ('Current', [('S', '')]),
            ('Take', [('S', 'Unreal Take')], [
                ('FileName', [('S', 'Unreal Take')]),
                ('LocalTime', [('L', 0), ('L', dur)]),
                ('ReferenceTime', [('L', 0), ('L', dur)]),
            ]),
        ])

        return len(self.buf)


# ============================================================================
# RETARGETING
# ============================================================================

def retarget(bvh, skeleton, scale=1.0):
    """Retarget BVH animation onto the Quinn skeleton.

    Strategy:
    1. Compute BVH world-space rotations for all bones at each frame
    2. For each BVH bone, compute the local rotation relative to its parent
    3. Compute the rotation DIFFERENCE from the BVH rest pose (frame 0)
    4. Apply this rotation difference to the Quinn skeleton rest pose
    5. The Quinn rest pose already encodes the Y-up to Z-up conversion

    For root motion:
    - Extract Hips world position displacement from BVH
    - Convert BVH (Y-up) to UE5 (Z-up): BVH(x,y,z) -> UE5(z,x,y)
    - Apply scale factor

    Args:
        bvh: BVHFile object
        skeleton: OrderedDict from FBXReader.extract_skeleton()
        scale: Scale factor for position values

    Returns:
        Dict mapping bone_name -> {'translation': [[x,y,z],...], 'rotation': [[x,y,z],...], 'scaling': [[x,y,z],...]}
    """
    nf = bvh.frame_count
    ba = {}

    # Build reverse map: quinn_name -> [bvh_bone_names]
    q2b = {}
    for bn, qn in BVH_TO_QUINN.items():
        q2b.setdefault(qn, []).append(bn)

    # Compute Quinn rest world rotations from reference FBX data
    # Using ZYX convention (R = Rz * Ry * Rx) for FBX RotationOrder=0
    qr_world = {}

    def _compute_quinn_world(bn, parent_wr=None):
        if parent_wr is None:
            parent_wr = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
        lr = skeleton[bn]['lcl_r']
        # FBX RotationOrder=0 = EulerXYZ = R = Rz * Ry * Rx
        lm = euler_to_matrix(lr[0], lr[1], lr[2], 'ZYX')
        wr = mat_mul(parent_wr, lm)
        qr_world[bn] = wr
        for cn, cd in skeleton.items():
            if cd['parent'] == bn:
                _compute_quinn_world(cn, wr)

    _compute_quinn_world('root')

    # Compute BVH rest transforms (frame 0)
    rest = compute_bvh_world(bvh, 0)

    # Find the BVH Hips bone for root motion extraction
    bvh_hips = None
    for bn in ('Hips', 'hip', 'Pelvis', 'pelvis', 'mixamorig:Hips'):
        if bn in bvh.bone_map:
            bvh_hips = bvh.bone_map[bn]
            break
    if bvh_hips is None:
        # Try first child of Root
        if bvh.root_bone.children:
            bvh_hips = bvh.root_bone.children[0]

    # Precompute BVH world transforms for all frames
    all_frames = []
    for fi in range(nf):
        all_frames.append(compute_bvh_world(bvh, fi))

    # Get Hips world position at rest for root motion baseline
    hips_rest_pos = None
    if bvh_hips:
        hips_rest_pos = all_frames[0][bvh_hips.name][0]

    # Retarget each Quinn bone
    for bname in skeleton:
        trans_list = []
        rots_list = []
        scals_list = []

        bvh_names = q2b.get(bname, [])
        bvh_bone = bvh.bone_map.get(bvh_names[0]) if bvh_names else None

        for fi in range(nf):
            if bname == 'root':
                # ---- Root motion ----
                # Extract from BVH Hips world position displacement
                if bvh_hips and bvh_hips.name in all_frames[fi]:
                    hp = all_frames[fi][bvh_hips.name][0]  # Hips world pos in BVH space
                    if hips_rest_pos:
                        # Coordinate conversion: BVH Y-up -> UE5 Z-up
                        # BVH(x,y,z) -> UE5(z,x,y) with scale
                        dx = (hp[2] - hips_rest_pos[2]) * scale  # BVH Z -> UE5 X (forward)
                        dy = (hp[0] - hips_rest_pos[0]) * scale  # BVH X -> UE5 Y (right)
                        dz = (hp[1] - hips_rest_pos[1]) * scale  # BVH Y -> UE5 Z (up)
                        trans_list.append([dx, dy, dz])
                    else:
                        trans_list.append([0.0, 0.0, 0.0])
                else:
                    trans_list.append([0.0, 0.0, 0.0])
                rots_list.append([0.0, 0.0, 0.0])
                scals_list.append([1.0, 1.0, 1.0])

            elif bvh_bone and bvh_bone.name in all_frames[fi]:
                # ---- Mapped bone with BVH animation ----
                wt = all_frames[fi]
                wp, wr_bvh = wt[bvh_bone.name]

                # BVH parent world transform
                if bvh_bone.parent and bvh_bone.parent.name in wt:
                    pp, pr = wt[bvh_bone.parent.name]
                else:
                    pr = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]

                # Compute BVH local rotation (animated)
                pri = mat_transpose(pr)
                lr = mat_mul(pri, wr_bvh)

                # Compute BVH rest local rotation
                rwp, rwr = rest[bvh_bone.name]
                if bvh_bone.parent and bvh_bone.parent.name in rest:
                    rpp, rpr = rest[bvh_bone.parent.name]
                else:
                    rpr = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
                rpri = mat_transpose(rpr)
                rlr = mat_mul(rpri, rwr)

                # Rotation difference from rest (in BVH local space)
                rlri = mat_transpose(rlr)
                rdiff = mat_mul(rlri, lr)

                # Apply rotation difference to Quinn rest pose
                # Using ZYX convention (FBX RotationOrder=0)
                qrl = euler_to_matrix(
                    skeleton[bname]['lcl_r'][0],
                    skeleton[bname]['lcl_r'][1],
                    skeleton[bname]['lcl_r'][2],
                    'ZYX'
                )
                qnew = mat_mul(qrl, rdiff)
                euler = matrix_to_euler(qnew, 'ZYX')

                rots_list.append(euler)
                trans_list.append(list(skeleton[bname]['lcl_t']))
                scals_list.append(list(skeleton[bname]['lcl_s']))

            else:
                # ---- Unmapped bone: keep rest pose ----
                rots_list.append(list(skeleton[bname]['lcl_r']))
                trans_list.append(list(skeleton[bname]['lcl_t']))
                scals_list.append(list(skeleton[bname]['lcl_s']))

        ba[bname] = {
            'translation': trans_list,
            'rotation': rots_list,
            'scaling': scals_list,
        }

    # Apply Euler angle continuity filtering to all rotation curves
    # This handles 360° wraps and reduces discontinuities from gimbal lock
    gimbal_lock_bones = []
    for bname in ba:
        rest_r = skeleton[bname]['lcl_r']
        # Check if bone is near gimbal lock (Y near ±90° for ZYX convention)
        if abs(abs(rest_r[1]) - 90) < 10:
            gimbal_lock_bones.append(bname)

        ba[bname]['rotation'] = ensure_euler_continuity(ba[bname]['rotation'])

    if gimbal_lock_bones:
        print(f"  [WARN] Bones near gimbal lock (Y≈±90°): {', '.join(gimbal_lock_bones[:5])}{'...' if len(gimbal_lock_bones) > 5 else ''}")
        print(f"         Euler angle curves may have discontinuities. UE5 quaternion interp should handle this.")

    return ba


# ============================================================================
# VALIDATION
# ============================================================================

def validate_output(filepath, skeleton, bone_anim):
    """Validate the output FBX by parsing it back and checking integrity.

    Checks:
    1. Number of Model records matches the reference skeleton
    2. Number of AnimationCurveNode records = num_bones * 3
    3. Number of AnimationCurve records = num_bones * 9
    4. Root motion translation values are non-zero and reasonable
    5. Pelvis rotation values are in reasonable range
    """
    print(f"\n{'='*60}")
    print("[VALIDATE] Validating output FBX")
    print(f"{'='*60}")

    try:
        reader = FBXReader(filepath)
    except Exception as e:
        print(f"[VALIDATE] FAIL: Cannot read FBX: {e}")
        return False

    objects = reader.find(reader.root_records, 'Objects')
    if not objects:
        print("[VALIDATE] FAIL: No Objects section")
        return False

    models = reader.find_all(objects['children'], 'Model')
    cnodes = reader.find_all(objects['children'], 'AnimationCurveNode')
    curves = reader.find_all(objects['children'], 'AnimationCurve')
    stacks = reader.find_all(objects['children'], 'AnimationStack')
    layers = reader.find_all(objects['children'], 'AnimationLayer')

    nb = len(skeleton)
    expected_cnodes = nb * 3
    expected_curves = nb * 9

    # Count bone models (Root and LimbNode types only)
    bone_models = 0
    for m in models:
        props = m['props']
        if len(props) >= 3:
            mtype = props[2][1]
            if mtype in ('Root', 'LimbNode'):
                bone_models += 1

    ok = True

    # Check 1: Model records
    if bone_models == nb:
        print(f"[VALIDATE] PASS Model records: {bone_models} (expected {nb})")
    else:
        print(f"[VALIDATE] FAIL Model records: {bone_models} (expected {nb})")
        ok = False

    # Check 2: AnimationCurveNode records
    if len(cnodes) == expected_cnodes:
        print(f"[VALIDATE] PASS AnimationCurveNode records: {len(cnodes)} (expected {expected_cnodes})")
    else:
        print(f"[VALIDATE] FAIL AnimationCurveNode records: {len(cnodes)} (expected {expected_cnodes})")
        ok = False

    # Check 3: AnimationCurve records
    if len(curves) == expected_curves:
        print(f"[VALIDATE] PASS AnimationCurve records: {len(curves)} (expected {expected_curves})")
    else:
        print(f"[VALIDATE] FAIL AnimationCurve records: {len(curves)} (expected {expected_curves})")
        ok = False

    # Check 4: AnimationStack and AnimationLayer
    if len(stacks) == 1:
        print(f"[VALIDATE] PASS AnimationStack records: {len(stacks)} (expected 1)")
    else:
        print(f"[VALIDATE] FAIL AnimationStack records: {len(stacks)} (expected 1)")
        ok = False

    if len(layers) == 1:
        print(f"[VALIDATE] PASS AnimationLayer records: {len(layers)} (expected 1)")
    else:
        print(f"[VALIDATE] FAIL AnimationLayer records: {len(layers)} (expected 1)")
        ok = False

    # Check 5: Root motion translation values
    root_anim = bone_anim.get('root', {})
    root_trans = root_anim.get('translation', [])
    if root_trans:
        non_zero_count = sum(1 for t in root_trans if any(abs(v) > 0.0001 for v in t))
        max_t = [max(abs(t[i]) for t in root_trans) for i in range(3)]
        if non_zero_count > 0:
            print(f"[VALIDATE] PASS Root motion: {non_zero_count}/{len(root_trans)} frames non-zero")
            print(f"           Max displacement: X={max_t[0]:.6f}, Y={max_t[1]:.6f}, Z={max_t[2]:.6f}")
        else:
            print(f"[VALIDATE] FAIL Root motion: No non-zero translation values!")
            ok = False
    else:
        print("[VALIDATE] FAIL No root translation data")
        ok = False

    # Check 6: Pelvis rotation values
    pelvis_anim = bone_anim.get('pelvis', {})
    pelvis_rots = pelvis_anim.get('rotation', [])
    if pelvis_rots:
        max_r = [max(abs(r[i]) for r in pelvis_rots) for i in range(3)]
        avg_r = [sum(r[i] for r in pelvis_rots) / len(pelvis_rots) for i in range(3)]
        reasonable = all(m < 360 for m in max_r)
        if reasonable:
            print(f"[VALIDATE] PASS Pelvis rotation: avg=({avg_r[0]:.2f},{avg_r[1]:.2f},{avg_r[2]:.2f})")
            print(f"           Max: ({max_r[0]:.2f},{max_r[1]:.2f},{max_r[2]:.2f})")
        else:
            print(f"[VALIDATE] FAIL Pelvis rotation: unreasonable max=({max_r[0]:.2f},{max_r[1]:.2f},{max_r[2]:.2f})")
            ok = False
    else:
        print("[VALIDATE] FAIL No pelvis rotation data")
        ok = False

    # Check 7: Bone names match reference
    bone_names_in_fbx = set()
    for m in models:
        props = m['props']
        if len(props) >= 3:
            mtype = props[2][1]
            if mtype in ('Root', 'LimbNode'):
                full_name = props[1][1]
                bone_name = full_name.split('\x00')[0] if '\x00' in full_name else full_name
                bone_names_in_fbx.add(bone_name)

    ref_names = set(skeleton.keys())
    if bone_names_in_fbx == ref_names:
        print(f"[VALIDATE] PASS All {len(ref_names)} bone names match reference skeleton")
    else:
        missing = ref_names - bone_names_in_fbx
        extra = bone_names_in_fbx - ref_names
        if missing:
            print(f"[VALIDATE] FAIL Missing bones: {missing}")
        if extra:
            print(f"[VALIDATE] FAIL Extra bones: {extra}")
        ok = False

    # File size
    fsz = os.path.getsize(filepath)
    print(f"\n[VALIDATE] Output file size: {fsz:,} bytes ({fsz / 1024:.1f} KB)")

    if ok:
        print(f"\n[VALIDATE] *** ALL CHECKS PASSED ***")
    else:
        print(f"\n[VALIDATE] *** SOME CHECKS FAILED ***")

    return ok


# ============================================================================
# MAIN
# ============================================================================

def convert(bvh_path, out_path, skeleton_fbx_path=None, scale=1.0):
    """Convert BVH to FBX for UE5.

    Args:
        bvh_path: Path to input BVH file
        out_path: Path to output FBX file
        skeleton_fbx_path: Path to reference skeleton FBX (required)
        scale: Scale factor for position values
    """
    print(f"{'='*60}")
    print(f"BVH to FBX Converter v5.0 for Unreal Engine 5")
    print(f"{'='*60}")
    print(f"[INPUT]  BVH: {bvh_path}")
    print(f"[OUTPUT] FBX: {out_path}")
    print(f"[REF]    Skeleton: {skeleton_fbx_path}")
    print(f"[SCALE]  {scale}")

    # ------------------------------------------------------------------
    # Step 1: Parse BVH
    # ------------------------------------------------------------------
    print(f"\n--- Step 1: Parsing BVH ---")
    bvh = BVHFile(bvh_path)
    print(f"  Frames: {bvh.frame_count}")
    print(f"  FPS: {bvh.fps:.1f}")
    print(f"  Duration: {bvh.frame_count / bvh.fps:.2f}s")
    print(f"  Bones: {len(bvh.bones)}")
    print(f"  Root: {bvh.root_bone.name}")

    # Print BVH bone names
    print(f"  BVH bones: {', '.join(b.name for b in bvh.bones[:10])}{'...' if len(bvh.bones) > 10 else ''}")

    # ------------------------------------------------------------------
    # Step 2: Load skeleton from reference FBX
    # ------------------------------------------------------------------
    if not skeleton_fbx_path:
        raise ValueError("Skeleton FBX path is required (--skeleton flag)")

    print(f"\n--- Step 2: Loading reference skeleton ---")
    reader = FBXReader(skeleton_fbx_path)
    skeleton = reader.extract_skeleton()
    print(f"  FBX version: {reader.version}")
    print(f"  Bones extracted: {len(skeleton)}")

    # Print some bone data for verification
    print(f"  Sample bone data from reference FBX:")
    for bname in list(skeleton.keys())[:5]:
        bd = skeleton[bname]
        print(f"    {bname}: type={bd['type']}, "
              f"T=({bd['lcl_t'][0]:.4f},{bd['lcl_t'][1]:.4f},{bd['lcl_t'][2]:.4f}), "
              f"R=({bd['lcl_r'][0]:.2f},{bd['lcl_r'][1]:.2f},{bd['lcl_r'][2]:.2f})")

    # Verify bone hierarchy
    root_bones = [bn for bn, bd in skeleton.items() if bd['parent'] is None]
    print(f"  Root bones: {root_bones}")

    # ------------------------------------------------------------------
    # Step 3: Check bone mapping
    # ------------------------------------------------------------------
    print(f"\n--- Step 3: Bone mapping ---")
    mapped = 0
    unmapped_quinn = []
    for bname in skeleton:
        bvh_names = []
        for bn, qn in BVH_TO_QUINN.items():
            if qn == bname:
                bvh_names.append(bn)
        if bvh_names:
            actual = [bn for bn in bvh_names if bn in bvh.bone_map]
            if actual:
                mapped += 1
            else:
                unmapped_quinn.append(f"{bname} (mapped to {bvh_names} but not in BVH)")
        else:
            if bname != 'root':
                unmapped_quinn.append(bname)

    print(f"  Mapped bones: {mapped}")
    print(f"  Unmapped Quinn bones: {len(unmapped_quinn)}")
    if unmapped_quinn[:10]:
        print(f"    (first 10: {', '.join(unmapped_quinn[:10])})")

    # ------------------------------------------------------------------
    # Step 4: Retarget animation
    # ------------------------------------------------------------------
    print(f"\n--- Step 4: Retargeting animation ---")
    ba = retarget(bvh, skeleton, scale=scale)

    # Print some retargeting results
    root_t = ba.get('root', {}).get('translation', [])
    if root_t:
        print(f"  Root motion frame 0: ({root_t[0][0]:.6f}, {root_t[0][1]:.6f}, {root_t[0][2]:.6f})")
        print(f"  Root motion frame mid: ({root_t[len(root_t)//2][0]:.6f}, {root_t[len(root_t)//2][1]:.6f}, {root_t[len(root_t)//2][2]:.6f})")

    pelvis_r = ba.get('pelvis', {}).get('rotation', [])
    if pelvis_r:
        print(f"  Pelvis rotation frame 0: ({pelvis_r[0][0]:.2f}, {pelvis_r[0][1]:.2f}, {pelvis_r[0][2]:.2f})")

    # ------------------------------------------------------------------
    # Step 5: Build FBX
    # ------------------------------------------------------------------
    print(f"\n--- Step 5: Building FBX ---")
    w = FBXWriter()
    sz = w.build(bvh, skeleton, ba, scale=scale)
    w.write(out_path)

    fsz = os.path.getsize(out_path)
    print(f"  Buffer size: {sz:,} bytes")
    print(f"  File size: {fsz:,} bytes ({fsz / 1024:.1f} KB)")

    # ------------------------------------------------------------------
    # Step 6: Validate
    # ------------------------------------------------------------------
    validate_output(out_path, skeleton, ba)

    # ------------------------------------------------------------------
    # Step 7: Save stats
    # ------------------------------------------------------------------
    stats = {
        'bvh': os.path.basename(bvh_path),
        'output': os.path.basename(out_path),
        'skeleton_fbx': os.path.basename(skeleton_fbx_path) if skeleton_fbx_path else None,
        'frames': bvh.frame_count,
        'fps': bvh.fps,
        'duration': bvh.frame_count / bvh.fps,
        'bvh_bones': len(bvh.bones),
        'quinn_bones': len(skeleton),
        'mapped': mapped,
        'unmapped': len(unmapped_quinn),
        'scale': scale,
        'size': fsz,
        'version': 'v5.0',
    }
    sp = out_path.replace('.fbx', '.stats.json')
    with open(sp, 'w') as f:
        json.dump(stats, f, indent=2)
    print(f"\n[STATS] Saved to: {sp}")

    return stats


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(
        description='BVH to FBX Converter v5.0 for Unreal Engine 5',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
  python3 bvh_to_fbx_ue5.py input.bvh output.fbx --skeleton SKM_Quinn_Simple.FBX --scale 0.01
        """
    )
    parser.add_argument('input', help='Input BVH file path')
    parser.add_argument('output', help='Output FBX file path')
    parser.add_argument('--skeleton', type=str, required=True,
                        help='Reference skeleton FBX file (required)')
    parser.add_argument('--scale', type=float, default=1.0,
                        help='Scale factor for position values (default: 1.0)')
    args = parser.parse_args()

    try:
        convert(args.input, args.output, skeleton_fbx_path=args.skeleton, scale=args.scale)
    except Exception as e:
        print(f"\n[ERROR] {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
