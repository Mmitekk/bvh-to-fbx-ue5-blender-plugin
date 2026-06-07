bl_info = {
    "name": "BVH to FBX for UE5",
    "author": "BVH2FBX Converter v17.0",
    "version": (17, 0, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > BVH2FBX",
    "description": "BVH to FBX for UE5 with Root Motion",
    "category": "Animation",
    "tracker_url": "https://github.com/Mmitekk/bvh-to-fbx-ue5-blender-plugin",
}

import bpy
import os
import math
import mathutils
import json
import shutil
import tempfile
import urllib.request
import urllib.error
import ssl
from collections import OrderedDict

GITHUB_REPO = "Mmitekk/bvh-to-fbx-ue5-blender-plugin"
GITHUB_API_RELEASES = f"https://api.github.com/repos/{GITHUB_REPO}/releases"
ADDON_FILENAME = "bvh_to_fbx_ue5_addon.py"
CURRENT_VERSION = bl_info["version"]


def version_to_string(v):
    return ".".join(str(x) for x in v)


def string_to_version(s):
    parts = s.strip().lstrip("v").split(".")
    result = []
    for p in parts:
        try:
            result.append(int(p))
        except ValueError:
            result.append(0)
    while len(result) < 3:
        result.append(0)
    return tuple(result[:3])


def fetch_github_releases():
    ctx = ssl.create_default_context()
    try:
        req = urllib.request.Request(
            GITHUB_API_RELEASES,
            headers={"User-Agent": "BVH2FBX-Blender-Addon", "Accept": "application/vnd.github.v3+json"},
        )
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[BVH2FBX] Failed to fetch releases: {e}")
        return []


def find_asset_url(release, filename):
    for asset in release.get("assets", []):
        if asset.get("name") == filename:
            return asset.get("url") or asset.get("browser_download_url")
    return None


def download_file(url, dest_path):
    ctx = ssl.create_default_context()
    headers = {"User-Agent": "BVH2FBX-Blender-Addon"}
    if "api.github.com" in url and "/assets/" in url:
        headers["Accept"] = "application/octet-stream"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, context=ctx, timeout=60) as resp:
        with open(dest_path, "wb") as f:
            shutil.copyfileobj(resp, f)


def get_addon_install_path():
    return os.path.abspath(__file__)


# ============================================================================
# BONE MAPPINGS
# ============================================================================

BVH_TO_UE5 = {
    'Hips': 'pelvis', 'Spine': 'spine_01', 'Spine1': 'spine_02',
    'Spine2': 'spine_03', 'Spine3': 'spine_04', 'Chest': 'spine_04',
    'Neck': 'neck_01', 'Neck1': 'neck_02', 'Neck2': 'neck_03', 'Head': 'head',
    'LeftShoulder': 'clavicle_l', 'LeftArm': 'upperarm_l',
    'LeftForeArm': 'lowerarm_l', 'LeftHand': 'hand_l',
    'LeftHandThumb1': 'thumb_01_l', 'LeftHandThumb2': 'thumb_02_l', 'LeftHandThumb3': 'thumb_03_l',
    'LeftHandIndex1': 'index_metacarpal_l', 'LeftHandIndex2': 'index_01_l',
    'LeftHandIndex3': 'index_02_l', 'LeftHandIndex4': 'index_03_l',
    'LeftHandMiddle1': 'middle_metacarpal_l', 'LeftHandMiddle2': 'middle_01_l',
    'LeftHandMiddle3': 'middle_02_l', 'LeftHandMiddle4': 'middle_03_l',
    'LeftHandRing1': 'ring_metacarpal_l', 'LeftHandRing2': 'ring_01_l',
    'LeftHandRing3': 'ring_02_l', 'LeftHandRing4': 'ring_03_l',
    'LeftHandPinky1': 'pinky_metacarpal_l', 'LeftHandPinky2': 'pinky_01_l',
    'LeftHandPinky3': 'pinky_02_l', 'LeftHandPinky4': 'pinky_03_l',
    'RightShoulder': 'clavicle_r', 'RightArm': 'upperarm_r',
    'RightForeArm': 'lowerarm_r', 'RightHand': 'hand_r',
    'RightHandThumb1': 'thumb_01_r', 'RightHandThumb2': 'thumb_02_r', 'RightHandThumb3': 'thumb_03_r',
    'RightHandIndex1': 'index_metacarpal_r', 'RightHandIndex2': 'index_01_r',
    'RightHandIndex3': 'index_02_r', 'RightHandIndex4': 'index_03_r',
    'RightHandMiddle1': 'middle_metacarpal_r', 'RightHandMiddle2': 'middle_01_r',
    'RightHandMiddle3': 'middle_02_r', 'RightHandMiddle4': 'middle_03_r',
    'RightHandRing1': 'ring_metacarpal_r', 'RightHandRing2': 'ring_01_r',
    'RightHandRing3': 'ring_02_r', 'RightHandRing4': 'ring_03_r',
    'RightHandPinky1': 'pinky_metacarpal_r', 'RightHandPinky2': 'pinky_01_r',
    'RightHandPinky3': 'pinky_02_r', 'RightHandPinky4': 'pinky_03_r',
    'LeftUpLeg': 'thigh_l', 'LeftLeg': 'calf_l', 'LeftShin': 'calf_l',
    'LeftFoot': 'foot_l', 'LeftToeBase': 'ball_l', 'LeftToe': 'ball_l',
    'RightUpLeg': 'thigh_r', 'RightLeg': 'calf_r', 'RightShin': 'calf_r',
    'RightFoot': 'foot_r', 'RightToeBase': 'ball_r', 'RightToe': 'ball_r',
}

MIXAMO_TO_UE5 = {
    'mixamorig:Hips': 'pelvis', 'mixamorig:Spine': 'spine_01',
    'mixamorig:Spine1': 'spine_02', 'mixamorig:Spine2': 'spine_03',
    'mixamorig:Neck': 'neck_01', 'mixamorig:Head': 'head',
    'mixamorig:LeftShoulder': 'clavicle_l', 'mixamorig:LeftArm': 'upperarm_l',
    'mixamorig:LeftForeArm': 'lowerarm_l', 'mixamorig:LeftHand': 'hand_l',
    'mixamorig:RightShoulder': 'clavicle_r', 'mixamorig:RightArm': 'upperarm_r',
    'mixamorig:RightForeArm': 'lowerarm_r', 'mixamorig:RightHand': 'hand_r',
    'mixamorig:LeftUpLeg': 'thigh_l', 'mixamorig:LeftLeg': 'calf_l',
    'mixamorig:LeftFoot': 'foot_l', 'mixamorig:LeftToeBase': 'ball_l',
    'mixamorig:RightUpLeg': 'thigh_r', 'mixamorig:RightLeg': 'calf_r',
    'mixamorig:RightFoot': 'foot_r', 'mixamorig:RightToeBase': 'ball_r',
}

ALL_BVH_MAPS_UE5 = OrderedDict()
ALL_BVH_MAPS_UE5.update(BVH_TO_UE5)
ALL_BVH_MAPS_UE5.update(MIXAMO_TO_UE5)


# ============================================================================
# BVH AXIS AUTO-DETECTION
# ============================================================================

def detect_bvh_axis_convention(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except Exception:
        return '-Z', 'Y'
    hips_offset = None
    left_upleg_offset = None
    lines = content.replace('\t', ' ').split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.upper().startswith('JOINT') and 'HIPS' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                offset_line = lines[j].strip()
                if offset_line.upper().startswith('OFFSET'):
                    parts = offset_line.split()
                    try:
                        hips_offset = (float(parts[1]), float(parts[2]), float(parts[3]))
                    except (ValueError, IndexError):
                        pass
                    break
        if line.upper().startswith('JOINT') and 'LEFTUPLEG' in line.upper().replace(' ', ''):
            for j in range(i + 1, min(i + 5, len(lines))):
                offset_line = lines[j].strip()
                if offset_line.upper().startswith('OFFSET'):
                    parts = offset_line.split()
                    try:
                        left_upleg_offset = (float(parts[1]), float(parts[2]), float(parts[3]))
                    except (ValueError, IndexError):
                        pass
                    break
        i += 1
    if hips_offset is None:
        return '-Z', 'Y'
    abs_hips = [abs(hips_offset[0]), abs(hips_offset[1]), abs(hips_offset[2])]
    up_axis_idx = abs_hips.index(max(abs_hips))
    if up_axis_idx == 1:
        print(f"[BVH2FBX] Detected: Y-up - Hips offset: {hips_offset}")
        return '-Z', 'Y'
    elif up_axis_idx == 2:
        print(f"[BVH2FBX] Detected: Z-up - Hips offset: {hips_offset}")
        if left_upleg_offset:
            return ('Y', 'Z') if abs(left_upleg_offset[1]) > abs(left_upleg_offset[0]) * 2 else ('-Y', 'Z')
        return 'Y', 'Z'
    else:
        return '-Z', 'X'


# ============================================================================
# BONE MATCHING
# ============================================================================

def find_bvh_for_target(bvh_bone_names, target_name, bone_map_dict):
    for bvh_name, mapped_target in bone_map_dict.items():
        if mapped_target == target_name and bvh_name in bvh_bone_names:
            return bvh_name
    return None


def find_hips_bone(armature):
    for name in ['Hips', 'hips', 'hip', 'Pelvis', 'pelvis', 'mixamorig:Hips']:
        if name in armature.pose.bones:
            return armature.pose.bones[name]
    for pb in armature.pose.bones:
        if pb.parent is not None and len(pb.children) > 2:
            return pb
    return None


def find_root_bone(armature):
    for candidate in ['root', 'Root']:
        if candidate in armature.pose.bones:
            pb = armature.pose.bones[candidate]
            if pb.parent is None:
                return candidate
    for pb in armature.pose.bones:
        if pb.parent is None:
            return pb.name
    return None


def detect_skeleton_type(armature):
    bone_names = set(armature.pose.bones.keys())
    if sum(1 for n in bone_names if n.startswith('mixamorig:')) > 5:
        return 'mixamo'
    if len({'pelvis', 'spine_01', 'thigh_l', 'calf_l', 'upperarm_l'} & bone_names) >= 3:
        return 'ue5'
    return 'unknown'


def build_bone_map(bvh_armature, ref_armature, ref_skeleton_type):
    bvh_bone_names = set(bvh_armature.pose.bones.keys())
    bone_map = {}
    if ref_skeleton_type == 'mixamo':
        STD2MIX = {
            'Hips': 'mixamorig:Hips', 'Spine': 'mixamorig:Spine',
            'Spine1': 'mixamorig:Spine1', 'Spine2': 'mixamorig:Spine2',
            'Neck': 'mixamorig:Neck', 'Neck1': 'mixamorig:Neck1',
            'Head': 'mixamorig:Head',
            'LeftShoulder': 'mixamorig:LeftShoulder', 'LeftArm': 'mixamorig:LeftArm',
            'LeftForeArm': 'mixamorig:LeftForeArm', 'LeftHand': 'mixamorig:LeftHand',
            'RightShoulder': 'mixamorig:RightShoulder', 'RightArm': 'mixamorig:RightArm',
            'RightForeArm': 'mixamorig:RightForeArm', 'RightHand': 'mixamorig:RightHand',
            'LeftUpLeg': 'mixamorig:LeftUpLeg', 'LeftLeg': 'mixamorig:LeftLeg',
            'LeftFoot': 'mixamorig:LeftFoot', 'LeftToeBase': 'mixamorig:LeftToeBase',
            'LeftToe': 'mixamorig:LeftToeBase',
            'RightUpLeg': 'mixamorig:RightUpLeg', 'RightLeg': 'mixamorig:RightLeg',
            'RightFoot': 'mixamorig:RightFoot', 'RightToeBase': 'mixamorig:RightToeBase',
            'RightToe': 'mixamorig:RightToeBase',
            'LeftHandThumb1': 'mixamorig:LeftHandThumb1', 'LeftHandThumb2': 'mixamorig:LeftHandThumb2',
            'LeftHandThumb3': 'mixamorig:LeftHandThumb3',
            'LeftHandIndex1': 'mixamorig:LeftHandIndex1', 'LeftHandIndex2': 'mixamorig:LeftHandIndex2',
            'LeftHandIndex3': 'mixamorig:LeftHandIndex3',
            'LeftHandMiddle1': 'mixamorig:LeftHandMiddle1', 'LeftHandMiddle2': 'mixamorig:LeftHandMiddle2',
            'LeftHandMiddle3': 'mixamorig:LeftHandMiddle3',
            'LeftHandRing1': 'mixamorig:LeftHandRing1', 'LeftHandRing2': 'mixamorig:LeftHandRing2',
            'LeftHandRing3': 'mixamorig:LeftHandRing3',
            'LeftHandPinky1': 'mixamorig:LeftHandPinky1', 'LeftHandPinky2': 'mixamorig:LeftHandPinky2',
            'LeftHandPinky3': 'mixamorig:LeftHandPinky3',
            'RightHandThumb1': 'mixamorig:RightHandThumb1', 'RightHandThumb2': 'mixamorig:RightHandThumb2',
            'RightHandThumb3': 'mixamorig:RightHandThumb3',
            'RightHandIndex1': 'mixamorig:RightHandIndex1', 'RightHandIndex2': 'mixamorig:RightHandIndex2',
            'RightHandIndex3': 'mixamorig:RightHandIndex3',
            'RightHandMiddle1': 'mixamorig:RightHandMiddle1', 'RightHandMiddle2': 'mixamorig:RightHandMiddle2',
            'RightHandMiddle3': 'mixamorig:RightHandMiddle3',
            'RightHandRing1': 'mixamorig:RightHandRing1', 'RightHandRing2': 'mixamorig:RightHandRing2',
            'RightHandRing3': 'mixamorig:RightHandRing3',
            'RightHandPinky1': 'mixamorig:RightHandPinky1', 'RightHandPinky2': 'mixamorig:RightHandPinky2',
            'RightHandPinky3': 'mixamorig:RightHandPinky3',
        }
        for pb in ref_armature.pose.bones:
            if pb.name in bvh_bone_names:
                bone_map[pb.name] = pb.name
            else:
                for std_name, mix_name in STD2MIX.items():
                    if mix_name == pb.name and std_name in bvh_bone_names:
                        bone_map[pb.name] = std_name
                        break
    else:
        for pb in ref_armature.pose.bones:
            bvh_match = find_bvh_for_target(bvh_bone_names, pb.name, ALL_BVH_MAPS_UE5)
            if bvh_match:
                bone_map[pb.name] = bvh_match
    return bone_map


# ============================================================================
# RETARGETING ENGINE v17.0 — 3x3 ROTATION + EXPLICIT M_rel FOR ROOT
# ============================================================================
#
# The KEY insight that was missing in ALL previous versions:
#
# bone.matrix is in armature-LOCAL space. The two armatures have DIFFERENT
# object transforms (BVH=identity, Mixamo=RotX(90)+Scale(0.01)). This means
# their armature-local spaces are different coordinate systems.
#
# For CHILD bones: M_rel cancels when computing local poses (proven).
# For ROOT bone: we MUST apply M_rel_rot (RotX(-90)) to convert BVH rotation
#   and location from Z-up BVH space to Y-up Mixamo armature space.
#
# Using 3x3 normalized rotation matrices avoids ALL decompose() issues
# with non-orthogonal matrices that plagued v4-v15.
#


def _norm_rot(mat4):
    """Extract normalized 3x3 rotation from 4x4, stripping scale/shear."""
    m = mat4.to_3x3()
    for i in range(3):
        length = m.col[i].length
        if length > 1e-10:
            m.col[i] /= length
        else:
            m.col[i] = [0, 0, 0]
            m.col[i][i] = 1.0
    return m


def retarget_animation(bvh_armature, ref_armature, scale_factor=1.0):
    scene = bpy.context.scene

    ref_skeleton_type = detect_skeleton_type(ref_armature)
    print(f"[BVH2FBX] Target skeleton type: {ref_skeleton_type}")

    bone_map = build_bone_map(bvh_armature, ref_armature, ref_skeleton_type)
    if not bone_map:
        return None, {"error": "No bones could be mapped"}

    bvh_action = None
    if bvh_armature.animation_data and bvh_armature.animation_data.action:
        bvh_action = bvh_armature.animation_data.action
    if not bvh_action:
        return None, {"error": "BVH armature has no animation"}

    frame_start = int(bvh_action.frame_range[0])
    frame_end = int(bvh_action.frame_range[1])
    num_frames = frame_end - frame_start + 1

    bvh_hips = find_hips_bone(bvh_armature)
    root_bone_name = find_root_bone(ref_armature)
    if not root_bone_name:
        return None, {"error": "No root bone found"}

    root_is_mapped = root_bone_name in bone_map
    root_bvh_name = bone_map.get(root_bone_name)
    print(f"[BVH2FBX] Root: {root_bone_name} (mapped={root_is_mapped}, bvh={root_bvh_name})")

    # =========================================================================
    # STEP 1: Compute M_rel_rot — the rotation that converts from BVH
    # armature-local space to Mixamo armature-local space.
    # This is the PURE ROTATION component (no scale) of:
    #   M_rel = M_mix_obj^-1 @ M_bvh_obj
    # =========================================================================
    M_bvh_obj = bvh_armature.matrix_world
    M_mix_obj = ref_armature.matrix_world
    # Extract 3x3 normalized rotation from each object's world matrix
    bvh_obj_rot3 = _norm_rot(M_bvh_obj)
    mix_obj_rot3 = _norm_rot(M_mix_obj)
    # M_rel_rot converts BVH armature-local rotation to Mixamo armature-local rotation
    M_rel_rot = mix_obj_rot3.inverted() @ bvh_obj_rot3

    # Log diagnostics
    rel_euler = M_rel_rot.to_euler()
    print(f"[BVH2FBX] M_rel_rot (BVH->Mix armature space): "
          f"({math.degrees(rel_euler.x):.1f}, {math.degrees(rel_euler.y):.1f}, {math.degrees(rel_euler.z):.1f}) deg")

    bvh_euler = bvh_obj_rot3.to_euler()
    mix_euler = mix_obj_rot3.to_euler()
    print(f"[BVH2FBX] BVH obj rot: ({math.degrees(bvh_euler.x):.1f}, {math.degrees(bvh_euler.y):.1f}, {math.degrees(bvh_euler.z):.1f}) deg")
    print(f"[BVH2FBX] Mixamo obj rot: ({math.degrees(mix_euler.x):.1f}, {math.degrees(mix_euler.y):.1f}, {math.degrees(mix_euler.z):.1f}) deg")
    print(f"[BVH2FBX] BVH obj scale: ({bvh_armature.scale.x:.4f}, {bvh_armature.scale.y:.4f}, {bvh_armature.scale.z:.4f})")
    print(f"[BVH2FBX] Mixamo obj scale: ({ref_armature.scale.x:.4f}, {ref_armature.scale.y:.4f}, {ref_armature.scale.z:.4f})")

    # =========================================================================
    # STEP 2: Compute Mixamo local rest rotations (3x3 normalized)
    # =========================================================================
    mix_rest_rot = {}
    mix_rest_loc = {}
    for pb in ref_armature.pose.bones:
        mix_rest_rot[pb.name] = _norm_rot(pb.bone.matrix_local)
        mix_rest_loc[pb.name] = pb.bone.matrix_local.translation.copy()

    mix_local_rest_rot = {}
    mix_local_rest_rot_inv = {}
    for pb in ref_armature.pose.bones:
        if pb.parent:
            p_inv = mix_rest_rot[pb.parent.name].inverted()
            mix_local_rest_rot[pb.name] = p_inv @ mix_rest_rot[pb.name]
        else:
            mix_local_rest_rot[pb.name] = mix_rest_rot[pb.name].copy()
        mix_local_rest_rot_inv[pb.name] = mix_local_rest_rot[pb.name].inverted()

    # BVH rest rotations
    bvh_rest_rot = {}
    for pb in bvh_armature.pose.bones:
        bvh_rest_rot[pb.name] = _norm_rot(pb.bone.matrix_local)

    # =========================================================================
    # STEP 3: Compute location scale ratio
    # =========================================================================
    bvh_root_height = 1.0
    if root_bvh_name and root_bvh_name in bvh_rest_rot:
        bvh_pb_r = bvh_armature.pose.bones.get(root_bvh_name)
        if bvh_pb_r:
            bvh_root_height = bvh_pb_r.bone.matrix_local.translation.length
            if bvh_root_height < 0.001:
                bvh_root_height = 1.0

    mix_root_height = 1.0
    if root_bone_name in mix_rest_loc:
        mix_root_height = mix_rest_loc[root_bone_name].length
        if mix_root_height < 0.001:
            mix_root_height = 1.0

    loc_scale = mix_root_height / bvh_root_height
    print(f"[BVH2FBX] Location scale: {loc_scale:.6f} (BVH height={bvh_root_height:.4f}, Mix height={mix_root_height:.4f})")

    # =========================================================================
    # STEP 4: Diagnose rest pose rotation angles
    # =========================================================================
    print("[BVH2FBX] === Rest Rotation Angles ===")
    for ref_name, bvh_name in sorted(bone_map.items()):
        if ref_name in mix_local_rest_rot and bvh_name in bvh_rest_rot:
            bvh_pb_c = bvh_armature.pose.bones.get(bvh_name)
            if bvh_pb_c and bvh_pb_c.parent:
                bvh_p_inv = bvh_rest_rot[bvh_pb_c.parent.name].inverted()
                bvh_lr = bvh_p_inv @ bvh_rest_rot[bvh_name]
            else:
                bvh_lr = bvh_rest_rot[bvh_name]
            Q = mix_local_rest_rot_inv[ref_name] @ bvh_lr
            q = Q.to_quaternion()
            angle = 2 * math.acos(min(1.0, abs(q.w))) * 180.0 / math.pi
            marker = " <<<" if angle > 60 else ""
            print(f"  {bvh_name:25s} -> {ref_name:30s}: {angle:6.1f} deg{marker}")

    # =========================================================================
    # STEP 5: Detect forward direction
    # =========================================================================
    forward_quat = None
    forward_angle = 0.0
    if bvh_hips and num_frames > 1:
        scene.frame_set(frame_start)
        bpy.context.view_layer.update()
        start_pos = bvh_hips.matrix.translation.copy()
        scene.frame_set(frame_end)
        bpy.context.view_layer.update()
        end_pos = bvh_hips.matrix.translation.copy()
        walk_dir = end_pos - start_pos
        walk_dir.z = 0
        if walk_dir.length > 0.001:
            walk_dir.normalize()
            target_dir = mathutils.Vector((0, -1, 0))
            dot = max(-1.0, min(1.0, walk_dir.dot(target_dir)))
            if dot < -0.9999:
                forward_quat = mathutils.Quaternion((0, 0, 1), math.pi)
                forward_angle = 180.0
            elif dot < 0.9999:
                axis = walk_dir.cross(target_dir)
                if axis.length > 0.0001:
                    axis.normalize()
                    forward_quat = mathutils.Quaternion(axis, math.acos(dot))
                    forward_angle = math.degrees(math.acos(dot))
            if forward_quat:
                print(f"[BVH2FBX] Walk dir: ({walk_dir.x:.3f}, {walk_dir.y:.3f}, {walk_dir.z:.3f}), correction: {forward_angle:.1f} deg")

    # =========================================================================
    # STEP 6: Prepare Mixamo armature
    # =========================================================================
    try:
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
    except Exception:
        pass

    for pb in ref_armature.pose.bones:
        pb.rotation_mode = 'QUATERNION'

    if ref_armature.animation_data is None:
        ref_armature.animation_data_create()
    old_action = ref_armature.animation_data.action
    if old_action:
        ref_armature.animation_data.action = None

    new_action = bpy.data.actions.new(ref_armature.name + "_BVHAction")
    ref_armature.animation_data.action = new_action

    # Forward correction in root bone local space
    F_local = None
    if forward_quat and root_bone_name in mix_rest_rot:
        root_rest_q = mix_rest_rot[root_bone_name].to_quaternion()
        F_local = root_rest_q.inverted() @ forward_quat @ root_rest_q
        F_local.normalize()

    # =========================================================================
    # STEP 7: BAKE
    # =========================================================================
    identity_quat = mathutils.Quaternion((1, 0, 0, 0))
    zero_vec = mathutils.Vector((0, 0, 0))
    prev_quat = {}

    for fi in range(num_frames):
        frame = frame_start + fi
        scene.frame_set(frame)
        bpy.context.view_layer.update()

        for ref_name, bvh_name in bone_map.items():
            if ref_name not in ref_armature.pose.bones:
                continue
            if bvh_name not in bvh_armature.pose.bones:
                continue

            ref_pb = ref_armature.pose.bones[ref_name]
            bvh_pb = bvh_armature.pose.bones[bvh_name]

            # BVH bone pose rotation (3x3 normalized)
            bvh_pose_rot = _norm_rot(bvh_pb.matrix)
            # BVH bone pose location (armature-local)
            bvh_pose_loc = bvh_pb.matrix.translation.copy()

            if bvh_pb.parent:
                # CHILD BONE: M_rel cancels for local pose computation
                bvh_parent_rot_inv = _norm_rot(bvh_pb.parent.matrix).inverted()
                bvh_local_rot = bvh_parent_rot_inv @ bvh_pose_rot
            else:
                # ROOT BONE: apply M_rel_rot to convert from BVH space to Mixamo space
                bvh_local_rot = M_rel_rot @ bvh_pose_rot

            # Compute channel rotation
            rest_inv = mix_local_rest_rot_inv.get(ref_name)
            if rest_inv is None:
                continue

            mix_channel_rot = rest_inv @ bvh_local_rot
            mix_quat = mix_channel_rot.to_quaternion()

            if mix_quat.magnitude > 0.0001:
                mix_quat.normalize()
            else:
                mix_quat = identity_quat.copy()

            # Quaternion sign consistency
            if ref_name in prev_quat:
                if mix_quat.dot(prev_quat[ref_name]) < 0:
                    mix_quat = -mix_quat
            prev_quat[ref_name] = mix_quat.copy()

            # Compute channel location
            if ref_pb.parent is None:
                # ROOT BONE: convert BVH location to Mixamo armature space
                # 1. Apply M_rel_rot to convert Z-up BVH -> Y-up Mixamo
                # 2. Scale by loc_scale to match Mixamo proportions
                # 3. Compute delta from rest position
                mix_target_loc = M_rel_rot @ bvh_pose_loc * loc_scale
                mix_rest_root_loc = mix_rest_loc[root_bone_name]
                # Channel loc = rest_rot_inv @ (target_loc - rest_loc)
                mix_root_rest_rot_inv = mix_rest_rot[root_bone_name].inverted()
                mix_loc = mix_root_rest_rot_inv @ (mix_target_loc - mix_rest_root_loc)
                mix_loc *= scale_factor

                # Apply forward correction
                if F_local is not None:
                    mix_quat = F_local @ mix_quat
                    mix_quat.normalize()
                    mix_loc = F_local @ mix_loc
            else:
                # CHILD BONE: location always (0,0,0)
                mix_loc = zero_vec.copy()

            ref_pb.rotation_quaternion = mix_quat
            ref_pb.location = mix_loc

        for ref_pb in ref_armature.pose.bones:
            ref_pb.keyframe_insert(data_path='rotation_quaternion', frame=fi, group=ref_pb.name)
            ref_pb.keyframe_insert(data_path='location', frame=fi, group=ref_pb.name)

    print(f"[BVH2FBX] Baked {num_frames} frames, {len(bone_map)} bone pairs")

    # =========================================================================
    # STEP 8: Normalize root location (start at origin)
    # =========================================================================
    _normalize_root_location(ref_armature, root_bone_name, new_action)

    scene.frame_start = 0
    scene.frame_end = num_frames - 1

    mapped = [n for n in bone_map if n in ref_armature.pose.bones]
    unmapped = [pb.name for pb in ref_armature.pose.bones if pb.name not in bone_map and pb.name != root_bone_name]
    print(f"[BVH2FBX] Mapped {len(mapped)}, unmapped {len(unmapped)}")

    return new_action, {
        "total_bones": len(ref_armature.pose.bones),
        "mapped_bones": len(mapped),
        "unmapped_bones": unmapped,
        "frame_count": num_frames,
        "fps": scene.render.fps,
        "has_root_motion": bvh_hips is not None,
        "root_bone_name": root_bone_name,
        "root_is_mapped": root_is_mapped,
        "skeleton_type": ref_skeleton_type,
        "forward_correction": f"{forward_angle:.1f} deg" if forward_quat else "No",
        "bake_method": "rot3x3_mrel_v17",
        "loc_scale": f"{loc_scale:.6f}",
    }


def _normalize_root_location(ref_armature, root_bone_name, action):
    """Offset root bone location so first frame starts at (0,0,0)."""
    loc_dp = f'pose.bones["{root_bone_name}"].location'
    loc_curves = {}
    for fc in action.fcurves:
        if fc.data_path == loc_dp:
            loc_curves[fc.array_index] = fc

    if not loc_curves:
        return

    min_frame = None
    for fc in loc_curves.values():
        if fc.keyframe_points:
            f = fc.keyframe_points[0].co[0]
            if min_frame is None or f < min_frame:
                min_frame = f
    if min_frame is None:
        return

    first_loc = mathutils.Vector((0, 0, 0))
    for idx, fc in loc_curves.items():
        for kp in fc.keyframe_points:
            if abs(kp.co[0] - min_frame) < 0.5:
                first_loc[idx] = kp.co[1]
                break

    if first_loc.length < 0.0001:
        print("[BVH2FBX] Root location already at origin")
        return

    print(f"[BVH2FBX] Root offset: ({first_loc.x:.6f}, {first_loc.y:.6f}, {first_loc.z:.6f})")
    for idx, fc in loc_curves.items():
        for kp in fc.keyframe_points:
            kp.co[1] -= first_loc[idx]
            if kp.handle_left:
                kp.handle_left[1] -= first_loc[idx]
            if kp.handle_right:
                kp.handle_right[1] -= first_loc[idx]
    for fc in action.fcurves:
        fc.update()
    print("[BVH2FBX] Root location normalized")


# ============================================================================
# OPERATORS
# ============================================================================

class BVH2FBX_OT_convert(bpy.types.Operator):
    bl_idname = "bvh2fbx.convert"
    bl_label = "Convert BVH to FBX"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        props = context.scene.bvh2fbx_props
        if not props.bvh_filepath:
            return False
        if context.active_object and context.active_object.type == 'ARMATURE':
            return True
        for obj in context.scene.objects:
            if obj.type == 'ARMATURE':
                return True
        return False

    def execute(self, context):
        props = context.scene.bvh2fbx_props
        print(f"[BVH2FBX] === Conversion started: v{version_to_string(CURRENT_VERSION)} ===")
        print(f"[BVH2FBX] Addon file: {__file__}")

        if not os.path.isfile(props.bvh_filepath):
            self.report({'ERROR'}, f"BVH file not found: {props.bvh_filepath}")
            return {'CANCELLED'}

        try:
            with open(props.bvh_filepath, 'r', encoding='utf-8', errors='replace') as f:
                first_line = f.readline().strip()
                if first_line.upper() != 'HIERARCHY':
                    self.report({'ERROR'}, f"Not a BVH file! First line: '{first_line[:50]}'")
                    return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"Read error: {e}")
            return {'CANCELLED'}

        ref_armature = None
        if context.active_object and context.active_object.type == 'ARMATURE':
            ref_armature = context.active_object
        else:
            for obj in context.scene.objects:
                if obj.type == 'ARMATURE':
                    ref_armature = obj
                    break

        if ref_armature is None:
            self.report({'ERROR'}, "No armature in scene!")
            return {'CANCELLED'}

        orig_action = None
        if ref_armature.animation_data and ref_armature.animation_data.action:
            orig_action = ref_armature.animation_data.action

        axis_forward, axis_up = detect_bvh_axis_convention(props.bvh_filepath)

        try:
            if bpy.context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.select_all(action='DESELECT')
            bpy.ops.import_anim.bvh(
                filepath=props.bvh_filepath, target='ARMATURE',
                rotate_mode='NATIVE', axis_forward=axis_forward, axis_up=axis_up,
            )
        except Exception as e:
            self.report({'ERROR'}, f"BVH import error: {e}")
            return {'CANCELLED'}

        bvh_armature = None
        for obj in context.selected_objects:
            if obj.type == 'ARMATURE':
                bvh_armature = obj
                break
        if bvh_armature is None:
            self.report({'ERROR'}, "BVH armature not found after import!")
            return {'CANCELLED'}

        try:
            action, stats = retarget_animation(bvh_armature, ref_armature, props.scale_factor)
        except Exception as e:
            import traceback
            self.report({'ERROR'}, f"Retarget error: {e}\n{traceback.format_exc()}")
            _safe_delete(bvh_armature)
            if orig_action and ref_armature.animation_data:
                ref_armature.animation_data.action = orig_action
            return {'CANCELLED'}

        if action is None:
            self.report({'ERROR'}, f"Retarget failed: {stats.get('error', '?')}")
            _safe_delete(bvh_armature)
            return {'CANCELLED'}

        _safe_delete(bvh_armature)

        try:
            if bpy.context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass
        try:
            for obj in context.scene.objects:
                obj.select_set(False)
        except Exception:
            pass
        ref_armature.select_set(True)
        context.view_layer.objects.active = ref_armature

        if props.output_filepath and props.auto_export:
            try:
                bpy.ops.export_scene.fbx(
                    filepath=props.output_filepath, use_selection=True,
                    global_scale=1.0, apply_scale_options='FBX_SCALE_NONE',
                    axis_forward='-Z', axis_up='Z', object_types={'ARMATURE'},
                    use_armature_deform_only=False, add_leaf_bones=False,
                    primary_bone_axis='Y', secondary_bone_axis='X',
                    armature_nodetype='ROOT', bake_anim=True,
                    bake_anim_use_all_bones=True, bake_anim_step=1.0,
                    bake_anim_simplify_factor=0.0, use_metadata=True,
                )
            except Exception as e:
                self.report({'WARNING'}, f"FBX export failed: {e}")

        skel = stats.get('skeleton_type', '?')
        mapped = stats.get('mapped_bones', 0)
        total = stats.get('total_bones', 0)
        frames = stats.get('frame_count', 0)
        fwd = stats.get('forward_correction', '?')
        ls = stats.get('loc_scale', '?')
        self.report({'INFO'},
                     f"Done! v{version_to_string(CURRENT_VERSION)} {skel} {mapped}/{total} bones "
                     f"{frames} frames dir:{fwd} scale:{ls}")
        return {'FINISHED'}


def _safe_delete(obj):
    try:
        for o in bpy.data.objects:
            o.select_set(False)
        obj.select_set(True)
        bpy.ops.object.delete(use_global=False)
    except Exception:
        try:
            for scene in bpy.data.scenes:
                if obj.name in scene.collection.objects:
                    scene.collection.objects.unlink(obj)
            bpy.data.objects.remove(obj, do_unlink=True)
        except Exception:
            pass


class BVH2FBX_OT_import_skeleton(bpy.types.Operator):
    bl_idname = "bvh2fbx.import_skeleton"
    bl_label = "Import Skeleton"
    bl_options = {'REGISTER', 'UNDO'}
    filepath: bpy.props.StringProperty(subtype='FILE_PATH')

    def execute(self, context):
        if not os.path.isfile(self.filepath):
            self.report({'ERROR'}, f"File not found: {self.filepath}")
            return {'CANCELLED'}
        try:
            bpy.ops.import_scene.fbx(filepath=self.filepath, use_anim=False,
                                      ignore_leaf_bones=False, automatic_bone_orientation=False)
        except Exception as e:
            self.report({'ERROR'}, f"Import error: {e}")
            return {'CANCELLED'}
        return {'FINISHED'}


class BVH2FBX_OT_check_updates(bpy.types.Operator):
    bl_idname = "bvh2fbx.check_updates"
    bl_label = "Check Updates"
    bl_options = {'REGISTER'}

    def execute(self, context):
        props = context.scene.bvh2fbx_props
        releases = fetch_github_releases()
        if not releases:
            props.update_status = "No GitHub connection"
            return {'CANCELLED'}
        items = []
        for rel in releases:
            tag = rel.get("tag_name", "")
            name = rel.get("name", tag)
            if any(a.get("name") == ADDON_FILENAME for a in rel.get("assets", [])):
                items.append((tag, f"{tag} — {name}", f"Release {tag}"))
        if not items:
            props.update_status = "No releases found"
            return {'CANCELLED'}
        props.available_versions.clear()
        for tag, label, desc in items:
            item = props.available_versions.add()
            item.tag = tag
            item.label = label
            item.description = desc
        latest_ver = string_to_version(items[0][0])
        if latest_ver > CURRENT_VERSION:
            props.update_status = f"Update available: {items[0][0]}"
        else:
            props.update_status = f"Latest installed ({version_to_string(CURRENT_VERSION)})"
        return {'FINISHED'}


class BVH2FBX_OT_install_update(bpy.types.Operator):
    bl_idname = "bvh2fbx.install_update"
    bl_label = "Install Update"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        props = context.scene.bvh2fbx_props
        return len(props.available_versions) > 0 and props.selected_version_index >= 0

    def execute(self, context):
        props = context.scene.bvh2fbx_props
        if props.selected_version_index < 0 or props.selected_version_index >= len(props.available_versions):
            return {'CANCELLED'}
        selected = props.available_versions[props.selected_version_index]
        target_tag = selected.tag
        releases = fetch_github_releases()
        target_release = None
        for rel in releases:
            if rel.get("tag_name") == target_tag:
                target_release = rel
                break
        if not target_release:
            self.report({'ERROR'}, f"Release {target_tag} not found")
            return {'CANCELLED'}
        asset_url = find_asset_url(target_release, ADDON_FILENAME)
        if not asset_url:
            self.report({'ERROR'}, f"No asset in {target_tag}")
            return {'CANCELLED'}

        current_path = get_addon_install_path()
        backup_path = current_path + ".backup"
        new_path = current_path + ".new"
        tmp_dir = tempfile.mkdtemp(prefix="bvh2fbx_")
        try:
            tmp_file = os.path.join(tmp_dir, ADDON_FILENAME)
            download_file(asset_url, tmp_file)
            shutil.copy2(current_path, backup_path)
            shutil.copy2(tmp_file, new_path)
            shutil.move(new_path, current_path)
            try:
                import importlib, sys
                if __name__ in sys.modules:
                    importlib.reload(sys.modules[__name__])
            except Exception:
                pass
            props.update_status = f"Updated to {target_tag}! RESTART BLENDER!"
            self.report({'INFO'}, f"Updated to {target_tag}! RESTART BLENDER!")
        except Exception as e:
            if os.path.exists(backup_path):
                shutil.move(backup_path, current_path)
            self.report({'ERROR'}, f"Install error: {e}")
            return {'CANCELLED'}
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            if os.path.exists(new_path):
                os.remove(new_path)
        return {'FINISHED'}


# ============================================================================
# PROPERTIES & PANELS
# ============================================================================

class BVH2FBX_VersionItem(bpy.types.PropertyGroup):
    tag: bpy.props.StringProperty(default="")
    label: bpy.props.StringProperty(default="")
    description: bpy.props.StringProperty(default="")


class BVH2FBX_Properties(bpy.types.PropertyGroup):
    bvh_filepath: bpy.props.StringProperty(name="BVH File", subtype='FILE_PATH', default="")
    output_filepath: bpy.props.StringProperty(name="Output FBX", subtype='FILE_PATH', default="")
    scale_factor: bpy.props.FloatProperty(name="Root Motion Scale", default=1.0, min=0.0001, max=100.0)
    auto_export: bpy.props.BoolProperty(name="Auto Export FBX", default=False)
    update_status: bpy.props.StringProperty(default="")
    available_versions: bpy.props.CollectionProperty(type=BVH2FBX_VersionItem)
    selected_version_index: bpy.props.IntProperty(default=-1)


class BVH2FBX_PT_main(bpy.types.Panel):
    bl_label = "BVH → FBX for UE5"
    bl_idname = "BVH2FBX_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "BVH2FBX"

    def draw(self, context):
        layout = self.layout
        props = context.scene.bvh2fbx_props
        box = layout.box()
        box.prop(props, "bvh_filepath")
        box.prop(props, "output_filepath")
        box.prop(props, "scale_factor")
        box.prop(props, "auto_export")
        layout.separator()
        layout.operator("bvh2fbx.convert", icon='PLAY')

        # Version display
        layout.label(text=f"v{version_to_string(CURRENT_VERSION)}")


class BVH2FBX_PT_update(bpy.types.Panel):
    bl_label = "Updates"
    bl_idname = "BVH2FBX_PT_update"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "BVH2FBX"
    bl_parent_id = "BVH2FBX_PT_main"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        props = context.scene.bvh2fbx_props
        layout.operator("bvh2fbx.check_updates", icon='WORLD')
        if props.update_status:
            layout.label(text=props.update_status)
        if len(props.available_versions) > 0:
            layout.prop(props, "selected_version_index", text="Version")
            layout.operator("bvh2fbx.install_update", icon='IMPORT')


classes = (
    BVH2FBX_VersionItem,
    BVH2FBX_Properties,
    BVH2FBX_OT_convert,
    BVH2FBX_OT_import_skeleton,
    BVH2FBX_OT_check_updates,
    BVH2FBX_OT_install_update,
    BVH2FBX_PT_main,
    BVH2FBX_PT_update,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.bvh2fbx_props = bpy.props.PointerProperty(type=BVH2FBX_Properties)
    print(f"[BVH2FBX] Registered v{version_to_string(CURRENT_VERSION)} from {__file__}")


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.bvh2fbx_props


if __name__ == "__main__":
    register()
