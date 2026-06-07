bl_info = {
    "name": "BVH to FBX for UE5",
    "author": "BVH2FBX Converter v14.0",
    "version": (14, 0, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > BVH2FBX",
    "description": "Конвертация BVH motion capture в FBX анимацию для Unreal Engine 5 с сохранением Root Motion",
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

# ============================================================================
# UPDATE SYSTEM CONSTANTS
# ============================================================================

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
            data = json.loads(resp.read().decode("utf-8"))
        return data
    except Exception as e:
        print(f"[BVH2FBX] Failed to fetch releases: {e}")
        return []


def find_asset_url(release, filename):
    for asset in release.get("assets", []):
        if asset.get("name") == filename:
            # Prefer API URL which supports auth headers for private repos
            return asset.get("url") or asset.get("browser_download_url")
    return None


def download_file(url, dest_path):
    ctx = ssl.create_default_context()
    headers = {"User-Agent": "BVH2FBX-Blender-Addon"}
    # GitHub API asset URLs require Accept header for binary download
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

# Standard BVH → UE5 Quinn
BVH_TO_UE5 = {
    'Hips': 'pelvis',
    'Spine': 'spine_01',
    'Spine1': 'spine_02',
    'Spine2': 'spine_03',
    'Spine3': 'spine_04',
    'Chest': 'spine_04',
    'Neck': 'neck_01',
    'Neck1': 'neck_02',
    'Neck2': 'neck_03',
    'Head': 'head',
    'LeftShoulder': 'clavicle_l',
    'LeftArm': 'upperarm_l',
    'LeftForeArm': 'lowerarm_l',
    'LeftHand': 'hand_l',
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
    'RightShoulder': 'clavicle_r',
    'RightArm': 'upperarm_r',
    'RightForeArm': 'lowerarm_r',
    'RightHand': 'hand_r',
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
    'LeftUpLeg': 'thigh_l',
    'LeftLeg': 'calf_l',
    'LeftShin': 'calf_l',
    'LeftFoot': 'foot_l',
    'LeftToeBase': 'ball_l',
    'LeftToe': 'ball_l',
    'RightUpLeg': 'thigh_r',
    'RightLeg': 'calf_r',
    'RightShin': 'calf_r',
    'RightFoot': 'foot_r',
    'RightToeBase': 'ball_r',
    'RightToe': 'ball_r',
}

# Mixamo → UE5 Quinn
MIXAMO_TO_UE5 = {
    'mixamorig:Hips': 'pelvis',
    'mixamorig:Spine': 'spine_01',
    'mixamorig:Spine1': 'spine_02',
    'mixamorig:Spine2': 'spine_03',
    'mixamorig:Neck': 'neck_01',
    'mixamorig:Head': 'head',
    'mixamorig:LeftShoulder': 'clavicle_l',
    'mixamorig:LeftArm': 'upperarm_l',
    'mixamorig:LeftForeArm': 'lowerarm_l',
    'mixamorig:LeftHand': 'hand_l',
    'mixamorig:RightShoulder': 'clavicle_r',
    'mixamorig:RightArm': 'upperarm_r',
    'mixamorig:RightForeArm': 'lowerarm_r',
    'mixamorig:RightHand': 'hand_r',
    'mixamorig:LeftUpLeg': 'thigh_l',
    'mixamorig:LeftLeg': 'calf_l',
    'mixamorig:LeftFoot': 'foot_l',
    'mixamorig:LeftToeBase': 'ball_l',
    'mixamorig:RightUpLeg': 'thigh_r',
    'mixamorig:RightLeg': 'calf_r',
    'mixamorig:RightFoot': 'foot_r',
    'mixamorig:RightToeBase': 'ball_r',
}

# Combined UE5 mapping (standard first, then mixamo)
ALL_BVH_MAPS_UE5 = OrderedDict()
ALL_BVH_MAPS_UE5.update(BVH_TO_UE5)
ALL_BVH_MAPS_UE5.update(MIXAMO_TO_UE5)


# ============================================================================
# BVH AXIS AUTO-DETECTION
# ============================================================================

def detect_bvh_axis_convention(filepath):
    """Auto-detect BVH coordinate system by analyzing bone offsets."""
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
        print("[BVH2FBX] Could not detect axis convention - using default Y-up")
        return '-Z', 'Y'

    abs_hips = [abs(hips_offset[0]), abs(hips_offset[1]), abs(hips_offset[2])]
    up_axis_idx = abs_hips.index(max(abs_hips))

    if up_axis_idx == 1:
        print(f"[BVH2FBX] Detected: Y-up (standard mocap) - Hips offset: {hips_offset}")
        return '-Z', 'Y'
    elif up_axis_idx == 2:
        print(f"[BVH2FBX] Detected: Z-up (Mixamo/game) - Hips offset: {hips_offset}")
        if left_upleg_offset:
            if abs(left_upleg_offset[1]) > abs(left_upleg_offset[0]) * 2:
                return 'Y', 'Z'
            else:
                return '-Y', 'Z'
        return 'Y', 'Z'
    else:
        print(f"[BVH2FBX] Detected: X-up (unusual) - Hips offset: {hips_offset}")
        return '-Z', 'X'


# ============================================================================
# BONE MATCHING UTILITIES
# ============================================================================

def find_bvh_for_target(bvh_bone_names, target_name, bone_map_dict):
    for bvh_name, mapped_target in bone_map_dict.items():
        if mapped_target == target_name and bvh_name in bvh_bone_names:
            return bvh_name
    return None


def find_hips_bone(armature):
    candidates = ['Hips', 'hips', 'hip', 'Pelvis', 'pelvis',
                  'mixamorig:Hips']
    for name in candidates:
        if name in armature.pose.bones:
            return armature.pose.bones[name]
    for pb in armature.pose.bones:
        if pb.parent is not None and len(pb.children) > 2:
            return pb
    return None


def get_bones_in_hierarchy_order(armature):
    ordered = []
    visited = set()

    def visit(pb):
        if pb.name in visited:
            return
        visited.add(pb.name)
        ordered.append(pb)
        for child in sorted(pb.children, key=lambda c: c.name):
            visit(child)

    for pb in armature.pose.bones:
        if pb.parent is None:
            visit(pb)
    return ordered


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
    mixamorig_count = sum(1 for n in bone_names if n.startswith('mixamorig:'))
    if mixamorig_count > 5:
        return 'mixamo'
    ue5_markers = {'pelvis', 'spine_01', 'thigh_l', 'calf_l', 'upperarm_l'}
    ue5_match = len(ue5_markers & bone_names)
    if ue5_match >= 3:
        return 'ue5'
    return 'unknown'


def build_bone_map(bvh_armature, ref_armature, ref_skeleton_type):
    bvh_bone_names = set(bvh_armature.pose.bones.keys())
    bone_map = {}

    if ref_skeleton_type == 'mixamo':
        STANDARD_TO_MIXAMO = {
            'Hips': 'mixamorig:Hips',
            'Spine': 'mixamorig:Spine',
            'Spine1': 'mixamorig:Spine1',
            'Spine2': 'mixamorig:Spine2',
            'Neck': 'mixamorig:Neck',
            'Neck1': 'mixamorig:Neck1',
            'Head': 'mixamorig:Head',
            'LeftShoulder': 'mixamorig:LeftShoulder',
            'LeftArm': 'mixamorig:LeftArm',
            'LeftForeArm': 'mixamorig:LeftForeArm',
            'LeftHand': 'mixamorig:LeftHand',
            'RightShoulder': 'mixamorig:RightShoulder',
            'RightArm': 'mixamorig:RightArm',
            'RightForeArm': 'mixamorig:RightForeArm',
            'RightHand': 'mixamorig:RightHand',
            'LeftUpLeg': 'mixamorig:LeftUpLeg',
            'LeftLeg': 'mixamorig:LeftLeg',
            'LeftFoot': 'mixamorig:LeftFoot',
            'LeftToeBase': 'mixamorig:LeftToeBase',
            'LeftToe': 'mixamorig:LeftToeBase',
            'RightUpLeg': 'mixamorig:RightUpLeg',
            'RightLeg': 'mixamorig:RightLeg',
            'RightFoot': 'mixamorig:RightFoot',
            'RightToeBase': 'mixamorig:RightToeBase',
            'RightToe': 'mixamorig:RightToeBase',
            'LeftHandThumb1': 'mixamorig:LeftHandThumb1',
            'LeftHandThumb2': 'mixamorig:LeftHandThumb2',
            'LeftHandThumb3': 'mixamorig:LeftHandThumb3',
            'LeftHandIndex1': 'mixamorig:LeftHandIndex1',
            'LeftHandIndex2': 'mixamorig:LeftHandIndex2',
            'LeftHandIndex3': 'mixamorig:LeftHandIndex3',
            'LeftHandMiddle1': 'mixamorig:LeftHandMiddle1',
            'LeftHandMiddle2': 'mixamorig:LeftHandMiddle2',
            'LeftHandMiddle3': 'mixamorig:LeftHandMiddle3',
            'LeftHandRing1': 'mixamorig:LeftHandRing1',
            'LeftHandRing2': 'mixamorig:LeftHandRing2',
            'LeftHandRing3': 'mixamorig:LeftHandRing3',
            'LeftHandPinky1': 'mixamorig:LeftHandPinky1',
            'LeftHandPinky2': 'mixamorig:LeftHandPinky2',
            'LeftHandPinky3': 'mixamorig:LeftHandPinky3',
            'RightHandThumb1': 'mixamorig:RightHandThumb1',
            'RightHandThumb2': 'mixamorig:RightHandThumb2',
            'RightHandThumb3': 'mixamorig:RightHandThumb3',
            'RightHandIndex1': 'mixamorig:RightHandIndex1',
            'RightHandIndex2': 'mixamorig:RightHandIndex2',
            'RightHandIndex3': 'mixamorig:RightHandIndex3',
            'RightHandMiddle1': 'mixamorig:RightHandMiddle1',
            'RightHandMiddle2': 'mixamorig:RightHandMiddle2',
            'RightHandMiddle3': 'mixamorig:RightHandMiddle3',
            'RightHandRing1': 'mixamorig:RightHandRing1',
            'RightHandRing2': 'mixamorig:RightHandRing2',
            'RightHandRing3': 'mixamorig:RightHandRing3',
            'RightHandPinky1': 'mixamorig:RightHandPinky1',
            'RightHandPinky2': 'mixamorig:RightHandPinky2',
            'RightHandPinky3': 'mixamorig:RightHandPinky3',
        }

        for pb in ref_armature.pose.bones:
            if pb.name in bvh_bone_names:
                bone_map[pb.name] = pb.name
            else:
                for std_name, mix_name in STANDARD_TO_MIXAMO.items():
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
# RETARGETING ENGINE v14.0 — CONSTRAINT-BASED BAKE
# ============================================================================
#
# WHY v4-v13 ALL FAILED (manual quaternion math):
#
# Every version from v4 to v13 tried to compute retargeting with manual
# quaternion/matrix formulas. Despite the math being theoretically correct,
# the results were always distorted because:
#
# 1. Extracting quaternions from matrices via decompose() loses precision
# 2. Quaternion sign ambiguity causes interpolation artifacts
# 3. The formula mix_quat = Q @ bvh_quat is correct per-bone in isolation
#    but accumulated error propagates down the parent chain
# 4. Q=106.8° for Hips means a HUGE rotation correction that amplifies
#    any numerical imprecision
#
# THE v14.0 APPROACH — CONSTRAINT-BASED BAKE:
#
# Instead of manual math, we use Blender's own constraint system:
# 1. Add Copy Rotation constraint (WORLD→WORLD) on each Mixamo bone
#    targeting the corresponding BVH bone
# 2. Add Copy Location constraint (WORLD→WORLD) for the root bone
# 3. Blender's depsgraph evaluates constraints in correct parent→child
#    order, handling ALL coordinate space conversions automatically
# 4. We read the VISUAL (constrained) result and bake to keyframes
# 5. Remove constraints after baking
#
# This is exactly how professional retargeting tools work (Rokoko,
# Expy Kit, Blender's own NLA bake system).
#


def retarget_animation(bvh_armature, ref_armature, scale_factor=1.0):
    """Retarget animation using constraint-based bake (v14.0).

    Uses Blender's Copy Rotation/Location constraints with WORLD→WORLD
    space to transfer animation from BVH to target skeleton. Blender's
    depsgraph handles all coordinate space conversions automatically.

    Args:
        bvh_armature: Blender armature with BVH animation
        ref_armature: Blender armature (target skeleton) to animate
        scale_factor: Scale for root motion translation

    Returns:
        (action, stats_dict)
    """
    scene = bpy.context.scene

    # Detect target skeleton type
    ref_skeleton_type = detect_skeleton_type(ref_armature)
    print(f"[BVH2FBX] Target skeleton type: {ref_skeleton_type}")

    # Build bone mapping: ref_bone_name -> bvh_bone_name
    bone_map = build_bone_map(bvh_armature, ref_armature, ref_skeleton_type)

    if not bone_map:
        return None, {"error": "No bones could be mapped between armatures"}

    # Get BVH animation info
    bvh_action = None
    if bvh_armature.animation_data and bvh_armature.animation_data.action:
        bvh_action = bvh_armature.animation_data.action

    if not bvh_action:
        return None, {"error": "BVH armature has no animation"}

    frame_start = int(bvh_action.frame_range[0])
    frame_end = int(bvh_action.frame_range[1])
    num_frames = frame_end - frame_start + 1

    # Find BVH Hips bone for forward direction detection
    bvh_hips = find_hips_bone(bvh_armature)

    # Find root bone in target armature
    root_bone_name = find_root_bone(ref_armature)
    if not root_bone_name:
        return None, {"error": "No root bone found in reference armature"}

    root_is_mapped = root_bone_name in bone_map
    root_bvh_name = bone_map.get(root_bone_name)

    print(f"[BVH2FBX] Root bone: {root_bone_name} (mapped={root_is_mapped}, bvh={root_bvh_name})")

    # =========================================================================
    # STEP 1: Detect forward direction from BVH Hips displacement
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
        walk_dir.z = 0  # Ignore vertical component

        if walk_dir.length > 0.001:
            walk_dir.normalize()
            # In Blender Z-up, Mixamo characters face -Y
            target_dir = mathutils.Vector((0, -1, 0))

            dot = walk_dir.dot(target_dir)
            dot = max(-1.0, min(1.0, dot))

            if dot > 0.9999:
                pass  # Already facing the right direction
            elif dot < -0.9999:
                forward_quat = mathutils.Quaternion((0, 0, 1), math.pi)
                forward_angle = 180.0
            else:
                axis = walk_dir.cross(target_dir)
                if axis.length > 0.0001:
                    axis.normalize()
                    angle = math.acos(dot)
                    forward_quat = mathutils.Quaternion(axis, angle)
                    forward_angle = math.degrees(angle)

            if forward_quat:
                print(f"[BVH2FBX] Walk direction: ({walk_dir.x:.3f}, {walk_dir.y:.3f}, {walk_dir.z:.3f})")
                print(f"[BVH2FBX] Forward correction: {forward_angle:.1f} degrees")

    # =========================================================================
    # STEP 2: Prepare Mixamo armature
    # =========================================================================
    try:
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
    except Exception:
        pass

    # Set rotation mode to QUATERNION for all bones
    for pb in ref_armature.pose.bones:
        pb.rotation_mode = 'QUATERNION'

    # Clear any existing animation on ref armature
    if ref_armature.animation_data is None:
        ref_armature.animation_data_create()

    old_action = ref_armature.animation_data.action
    if old_action:
        ref_armature.animation_data.action = None

    action_name = ref_armature.name + "_BVHAction"
    new_action = bpy.data.actions.new(action_name)
    ref_armature.animation_data.action = new_action

    # =========================================================================
    # STEP 3: Add Copy Rotation/Location constraints
    # =========================================================================
    # Using WORLD→WORLD space: Blender's depsgraph evaluates constraints
    # in correct parent→child order, automatically handling all coordinate
    # space conversions. This is the same approach used by Rokoko Studio
    # and other professional retargeting tools.
    constraints_added = []  # List of (pose_bone, constraint_name) for cleanup

    for ref_name, bvh_name in bone_map.items():
        if ref_name not in ref_armature.pose.bones:
            continue
        if bvh_name not in bvh_armature.pose.bones:
            continue

        ref_pb = ref_armature.pose.bones[ref_name]

        # Add Copy Rotation constraint
        cr = ref_pb.constraints.new('COPY_ROTATION')
        cr.target = bvh_armature
        cr.subtarget = bvh_name
        cr.target_space = 'WORLD'
        cr.owner_space = 'WORLD'
        cr.use_x = True
        cr.use_y = True
        cr.use_z = True
        cr.mix_mode = 'REPLACE'
        constraints_added.append((ref_pb, cr.name))

        # For root bone, also add Copy Location constraint
        if ref_pb.parent is None:
            cl = ref_pb.constraints.new('COPY_LOCATION')
            cl.target = bvh_armature
            cl.subtarget = bvh_name
            cl.target_space = 'WORLD'
            cl.owner_space = 'WORLD'
            cl.use_x = True
            cl.use_y = True
            cl.use_z = True
            cl.mix_mode = 'REPLACE'
            constraints_added.append((ref_pb, cl.name))

    print(f"[BVH2FBX] Added {len(constraints_added)} constraints for {len(bone_map)} bone pairs")

    # =========================================================================
    # STEP 4: Bake animation frame by frame
    # =========================================================================
    # For each frame, evaluate the depsgraph (which applies constraints),
    # then read the VISUAL (constrained) bone transforms and bake to keyframes.
    identity_quat = mathutils.Quaternion((1, 0, 0, 0))
    zero_vec = mathutils.Vector((0, 0, 0))

    # Pre-compute Mixamo rest matrices for extracting basis from constrained pose
    mix_local_rest = {}
    for pb in ref_armature.pose.bones:
        if pb.parent:
            mix_local_rest[pb.name] = (
                pb.parent.bone.matrix_local.inverted() @ pb.bone.matrix_local
            )
        else:
            mix_local_rest[pb.name] = pb.bone.matrix_local.copy()

    # Track previous quaternion per bone for sign consistency
    prev_quat = {}

    for fi in range(num_frames):
        frame = frame_start + fi
        scene.frame_set(frame)

        # Evaluate depsgraph to apply constraints
        depsgraph = bpy.context.evaluated_depsgraph_get()
        eval_ref = ref_armature.evaluated_get(depsgraph)

        for ref_pb in ref_armature.pose.bones:
            eval_pb = eval_ref.pose.bones.get(ref_pb.name)

            if eval_pb and ref_pb.name in bone_map:
                # Extract bone-local basis rotation from the constrained pose.
                # The constrained pose gives us the correct world-space rotation.
                # We need to convert it back to bone-local space for keyframing.
                if ref_pb.parent is None:
                    # Root bone: basis = rest^-1 @ constrained_matrix
                    rest_mat = ref_pb.bone.matrix_local
                    basis_mat = rest_mat.inverted() @ eval_pb.matrix
                    mix_loc, mix_quat, _ = basis_mat.decompose()
                else:
                    # Child bone: need parent's constrained matrix
                    eval_parent = eval_ref.pose.bones.get(ref_pb.parent.name)
                    if eval_parent:
                        local_visual = eval_parent.matrix.inverted() @ eval_pb.matrix
                    else:
                        local_visual = eval_pb.matrix.copy()
                    local_rest = mix_local_rest.get(ref_pb.name, ref_pb.bone.matrix_local)
                    basis_mat = local_rest.inverted() @ local_visual
                    mix_loc, mix_quat, _ = basis_mat.decompose()

                # Normalize quaternion
                if mix_quat.magnitude > 0.0001:
                    mix_quat = mix_quat.normalized()
                else:
                    mix_quat = identity_quat.copy()

                # Ensure consistent quaternion sign across frames
                # to prevent interpolation artifacts (taking the "long way")
                if ref_pb.name in prev_quat:
                    if mix_quat.dot(prev_quat[ref_pb.name]) < 0:
                        mix_quat = -mix_quat
                prev_quat[ref_pb.name] = mix_quat.copy()

                ref_pb.rotation_quaternion = mix_quat

                if ref_pb.parent is None:
                    # Root bone: apply scale and forward correction later
                    ref_pb.location = mix_loc * scale_factor
                else:
                    ref_pb.location = zero_vec.copy()
            else:
                ref_pb.rotation_quaternion = identity_quat.copy()
                ref_pb.location = zero_vec.copy()

            # Keyframe
            ref_pb.keyframe_insert(
                data_path='rotation_quaternion', frame=fi, group=ref_pb.name
            )
            ref_pb.keyframe_insert(
                data_path='location', frame=fi, group=ref_pb.name
            )

    print(f"[BVH2FBX] Baked {num_frames} frames for {len(bone_map)} bone pairs")

    # =========================================================================
    # STEP 5: Remove constraints
    # =========================================================================
    for ref_pb, cr_name in constraints_added:
        if cr_name in ref_pb.constraints:
            ref_pb.constraints.remove(ref_pb.constraints[cr_name])

    print(f"[BVH2FBX] Removed {len(constraints_added)} constraints")

    # =========================================================================
    # STEP 6: Apply forward rotation to root bone keyframes
    # =========================================================================
    if forward_quat and root_bone_name and root_bone_name in ref_armature.pose.bones:
        root_rest_quat = ref_armature.pose.bones[root_bone_name].bone.matrix_local.to_quaternion()
        # Convert forward_quat from armature space to root bone local space
        F_local = root_rest_quat.inverted() @ forward_quat @ root_rest_quat
        F_local.normalize()

        # Apply F_local to root bone's rotation and location keyframes
        rot_data_path = f'pose.bones["{root_bone_name}"].rotation_quaternion'
        loc_data_path = f'pose.bones["{root_bone_name}"].location'

        for fcurve in new_action.fcurves:
            if fcurve.data_path == rot_data_path:
                # Apply rotation to quaternion keyframes
                for kp in fcurve.keyframe_points:
                    # We need all 4 quaternion components to apply the rotation
                    # This is done per-component below
                    pass
            elif fcurve.data_path == loc_data_path:
                # Apply rotation to location keyframes
                idx = fcurve.array_index
                for kp in fcurve.keyframe_points:
                    loc = mathutils.Vector((0, 0, 0))
                    # Read all 3 location components at this frame
                    for other_fcurve in new_action.fcurves:
                        if other_fcurve.data_path == loc_data_path:
                            for other_kp in other_fcurve.keyframe_points:
                                if abs(other_kp.co[0] - kp.co[0]) < 0.5:
                                    loc[other_fcurve.array_index] = other_kp.co[1]
                                    break
                    # Rotate the location vector
                    rotated_loc = F_local @ loc
                    kp.co[1] = rotated_loc[idx]
                    if kp.handle_left:
                        kp.handle_left[1] = rotated_loc[idx]
                    if kp.handle_right:
                        kp.handle_right[1] = rotated_loc[idx]

        # Apply rotation to quaternion keyframes (need all 4 components)
        rot_curves = {}
        for fcurve in new_action.fcurves:
            if fcurve.data_path == rot_data_path:
                rot_curves[fcurve.array_index] = fcurve

        if len(rot_curves) == 4:
            # Get all frame numbers
            frames = set()
            for fcurve in rot_curves.values():
                for kp in fcurve.keyframe_points:
                    frames.add(int(round(kp.co[0])))

            for frame in sorted(frames):
                # Read current quaternion
                q = mathutils.Quaternion((1, 0, 0, 0))
                for idx, fcurve in rot_curves.items():
                    for kp in fcurve.keyframe_points:
                        if abs(kp.co[0] - frame) < 0.5:
                            q[idx] = kp.co[1]
                            break

                # Apply forward rotation
                q = F_local @ q
                q.normalize()

                # Write back
                for idx, fcurve in rot_curves.items():
                    for kp in fcurve.keyframe_points:
                        if abs(kp.co[0] - frame) < 0.5:
                            kp.co[1] = q[idx]
                            break

        for fcurve in new_action.fcurves:
            fcurve.update()

        print(f"[BVH2FBX] Forward rotation applied to root bone keyframes")

    # =========================================================================
    # STEP 7: Normalize root bone location (start at origin)
    # =========================================================================
    if root_bone_name in ref_armature.pose.bones:
        _normalize_root_location(ref_armature, root_bone_name, new_action)

    # Set scene frame range
    scene.frame_start = 0
    scene.frame_end = num_frames - 1

    # Stats
    mapped_bones = [n for n in bone_map if n in ref_armature.pose.bones]
    unmapped_bones = [
        pb.name for pb in ref_armature.pose.bones
        if pb.name not in bone_map and pb.name != root_bone_name
    ]

    print(f"[BVH2FBX] Mapped {len(mapped_bones)} bones, unmapped {len(unmapped_bones)}")

    stats = {
        "total_bones": len(ref_armature.pose.bones),
        "mapped_bones": len(mapped_bones),
        "unmapped_bones": unmapped_bones,
        "frame_count": num_frames,
        "fps": scene.render.fps,
        "has_root_motion": bvh_hips is not None,
        "root_bone_name": root_bone_name,
        "root_is_mapped": root_is_mapped,
        "skeleton_type": ref_skeleton_type,
        "forward_correction": f"{forward_angle:.1f} deg" if forward_quat else "No",
        "bake_method": "constraint_bake_v14",
    }

    return new_action, stats


def _normalize_root_location(ref_armature, root_bone_name, action):
    """Offset root bone location so the first frame starts at (0,0,0)."""
    loc_data_path = f'pose.bones["{root_bone_name}"].location'

    loc_curves = {}
    for fcurve in action.fcurves:
        if fcurve.data_path == loc_data_path:
            loc_curves[fcurve.array_index] = fcurve

    if not loc_curves:
        print(f"[BVH2FBX] No location curves found for root bone '{root_bone_name}'")
        return

    # Get the first frame's location values
    min_frame = None
    for fcurve in loc_curves.values():
        if fcurve.keyframe_points:
            first_kp_frame = fcurve.keyframe_points[0].co[0]
            if min_frame is None or first_kp_frame < min_frame:
                min_frame = first_kp_frame

    if min_frame is None:
        return

    first_loc = mathutils.Vector((0, 0, 0))
    for idx, fcurve in loc_curves.items():
        for kp in fcurve.keyframe_points:
            if abs(kp.co[0] - min_frame) < 0.5:
                first_loc[idx] = kp.co[1]
                break

    if first_loc.length < 0.0001:
        print(f"[BVH2FBX] Root bone location already at origin, no normalization needed")
        return

    print(f"[BVH2FBX] Root bone first frame location offset: ({first_loc.x:.4f}, {first_loc.y:.4f}, {first_loc.z:.4f})")

    # Subtract first frame offset from all keyframes
    for idx, fcurve in loc_curves.items():
        for kp in fcurve.keyframe_points:
            kp.co[1] -= first_loc[idx]
            if kp.handle_left:
                kp.handle_left[1] -= first_loc[idx]
            if kp.handle_right:
                kp.handle_right[1] -= first_loc[idx]

    for fcurve in action.fcurves:
        fcurve.update()

    print(f"[BVH2FBX] Normalized root bone location (first frame now at origin)")


# ============================================================================
# BLENDER OPERATORS — CONVERSION
# ============================================================================

class BVH2FBX_OT_convert(bpy.types.Operator):
    bl_idname = "bvh2fbx.convert"
    bl_label = "Конвертировать BVH в FBX"
    bl_description = "Импортировать BVH, заретаргетить на текущий скелет и экспортировать FBX для UE5"
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

        # Print version for debugging - confirms which version is actually running
        print(f"[BVH2FBX] === Conversion started: v{version_to_string(CURRENT_VERSION)} ===")

        # Validate BVH file
        if not os.path.isfile(props.bvh_filepath):
            self.report({'ERROR'}, f"BVH файл не найден: {props.bvh_filepath}")
            return {'CANCELLED'}

        try:
            with open(props.bvh_filepath, 'r', encoding='utf-8', errors='replace') as f:
                first_line = f.readline().strip()
                if first_line.upper() != 'HIERARCHY':
                    self.report({'ERROR'},
                        f"Это не BVH файл! Первая строка: '{first_line[:50]}'. "
                        f"Выберите файл .bvh, а не .fbx")
                    return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"Ошибка чтения файла: {e}")
            return {'CANCELLED'}

        # Find reference armature
        ref_armature = None
        if context.active_object and context.active_object.type == 'ARMATURE':
            ref_armature = context.active_object
        else:
            for obj in context.scene.objects:
                if obj.type == 'ARMATURE':
                    ref_armature = obj
                    break

        if ref_armature is None:
            self.report({'ERROR'}, "В сцене нет арматуры! Импортируйте скелет первым.")
            return {'CANCELLED'}

        # Detect target skeleton type
        skel_type = detect_skeleton_type(ref_armature)
        self.report({'INFO'}, f"Обнаружен тип скелета: {skel_type}")

        # Store original action
        orig_action = None
        if ref_armature.animation_data and ref_armature.animation_data.action:
            orig_action = ref_armature.animation_data.action

        # Auto-detect BVH axis convention
        axis_forward, axis_up = detect_bvh_axis_convention(props.bvh_filepath)
        self.report({'INFO'}, f"BVH оси: forward={axis_forward}, up={axis_up}")

        # Step 1: Import BVH with auto-detected axis settings
        self.report({'INFO'}, "Импорт BVH файла...")
        try:
            # Ensure we're in OBJECT mode before import
            if bpy.context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.select_all(action='DESELECT')
            bpy.ops.import_anim.bvh(
                filepath=props.bvh_filepath,
                target='ARMATURE',
                rotate_mode='NATIVE',
                axis_forward=axis_forward,
                axis_up=axis_up,
            )
        except Exception as e:
            self.report({'ERROR'}, f"Ошибка импорта BVH: {e}")
            return {'CANCELLED'}

        # Find the imported BVH armature
        bvh_armature = None
        for obj in context.selected_objects:
            if obj.type == 'ARMATURE':
                bvh_armature = obj
                break

        if bvh_armature is None:
            self.report({'ERROR'}, "BVH armature не найдена после импорта!")
            return {'CANCELLED'}

        self.report({'INFO'}, f"BVH импортирован: {bvh_armature.name} ({len(bvh_armature.pose.bones)} костей)")

        # Step 2: Retarget animation
        bvh_action = bvh_armature.animation_data.action if bvh_armature.animation_data else None
        frame_count = int(bvh_action.frame_range[1] - bvh_action.frame_range[0] + 1) if bvh_action else 0

        self.report({'INFO'}, f"Ретаргетинг BVH ({len(bvh_armature.pose.bones)} костей, {frame_count} кадров)...")

        try:
            action, stats = retarget_animation(
                bvh_armature,
                ref_armature,
                scale_factor=props.scale_factor
            )
        except Exception as e:
            import traceback
            self.report({'ERROR'}, f"Ошибка ретаргетинга: {e}\n{traceback.format_exc()}")
            # Context-safe cleanup: avoid bpy.ops in error handler
            _safe_delete_object(bvh_armature)
            if orig_action and ref_armature.animation_data:
                ref_armature.animation_data.action = orig_action
            return {'CANCELLED'}

        if action is None:
            error = stats.get('error', 'Unknown error')
            self.report({'ERROR'}, f"Ретаргетинг не удался: {error}")
            _safe_delete_object(bvh_armature)
            return {'CANCELLED'}

        # Step 3: Clean up - remove BVH armature
        _safe_delete_object(bvh_armature)

        # Step 4: Make reference armature active
        try:
            if bpy.context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass
        # Context-safe deselect: avoid bpy.ops.object.select_all which
        # fails with RuntimeError in Blender 5.1 when context is incorrect
        try:
            for obj in context.scene.objects:
                obj.select_set(False)
        except Exception:
            pass
        ref_armature.select_set(True)
        context.view_layer.objects.active = ref_armature

        # Step 5: Export FBX if output path specified
        if props.output_filepath and props.auto_export:
            self.report({'INFO'}, f"Экспорт FBX: {props.output_filepath}...")
            try:
                bpy.ops.export_scene.fbx(
                    filepath=props.output_filepath,
                    use_selection=True,
                    global_scale=1.0,
                    apply_scale_options='FBX_SCALE_NONE',
                    axis_forward='-Z',
                    axis_up='Z',
                    object_types={'ARMATURE'},
                    use_armature_deform_only=False,
                    add_leaf_bones=False,
                    primary_bone_axis='Y',
                    secondary_bone_axis='X',
                    armature_nodetype='ROOT',
                    bake_anim=True,
                    bake_anim_use_all_bones=True,
                    bake_anim_step=1.0,
                    bake_anim_simplify_factor=0.0,
                    use_metadata=True,
                )
                self.report({'INFO'}, f"FBX экспортирован: {props.output_filepath}")
            except Exception as e:
                self.report({'WARNING'}, f"Экспорт FBX не удался: {e}")

        # Report results
        mapped = stats.get('mapped_bones', 0)
        total = stats.get('total_bones', 0)
        root_motion = "Да" if stats.get('has_root_motion') else "Нет"
        root_name = stats.get('root_bone_name', '?')
        root_mapped = "Да" if stats.get('root_is_mapped') else "Нет"
        fwd_corr = stats.get('forward_correction', '?')
        skel = stats.get('skeleton_type', '?')
        self.report({'INFO'},
                     f"Готово! v{version_to_string(CURRENT_VERSION)} Скелет: {skel}, Костей: {total}, Сопоставлено: {mapped}, "
                     f"Кадров: {stats.get('frame_count', 0)}, "
                     f"Root Motion: {root_motion} (bone: {root_name}), "
                     f"Направление: {fwd_corr}")

        return {'FINISHED'}


def _safe_delete_object(obj):
    """Delete an object safely without relying on bpy.ops (context-safe)."""
    try:
        # Deselect everything first
        for o in bpy.data.objects:
            o.select_set(False)
        obj.select_set(True)
        bpy.ops.object.delete(use_global=False)
    except Exception:
        # If bpy.ops fails, try removing from scene directly
        try:
            for scene in bpy.data.scenes:
                if obj.name in scene.collection.objects:
                    scene.collection.objects.unlink(obj)
            bpy.data.objects.remove(obj, do_unlink=True)
        except Exception as e:
            print(f"[BVH2FBX] Warning: could not delete {obj.name}: {e}")


class BVH2FBX_OT_import_skeleton(bpy.types.Operator):
    bl_idname = "bvh2fbx.import_skeleton"
    bl_label = "Импортировать скелет"
    bl_description = "Импортировать скелетную сетку (FBX) как референсный скелет (UE5 Quinn или Mixamo)"
    bl_options = {'REGISTER', 'UNDO'}

    filepath: bpy.props.StringProperty(subtype='FILE_PATH')

    def execute(self, context):
        if not os.path.isfile(self.filepath):
            self.report({'ERROR'}, f"Файл не найден: {self.filepath}")
            return {'CANCELLED'}

        try:
            bpy.ops.import_scene.fbx(
                filepath=self.filepath,
                use_anim=False,
                ignore_leaf_bones=False,
                automatic_bone_orientation=False,
            )
            self.report({'INFO'}, f"Скелет импортирован: {self.filepath}")
        except Exception as e:
            self.report({'ERROR'}, f"Ошибка импорта: {e}")
            return {'CANCELLED'}

        return {'FINISHED'}


# ============================================================================
# BLENDER OPERATORS — UPDATE SYSTEM
# ============================================================================

class BVH2FBX_OT_check_updates(bpy.types.Operator):
    bl_idname = "bvh2fbx.check_updates"
    bl_label = "Проверить обновления"
    bl_description = "Проверить GitHub на наличие новых версий плагина"
    bl_options = {'REGISTER'}

    def execute(self, context):
        props = context.scene.bvh2fbx_props
        self.report({'INFO'}, "Проверка обновлений...")
        releases = fetch_github_releases()

        if not releases:
            props.update_status = "Нет связи с GitHub"
            self.report({'WARNING'}, "Не удалось получить список релизов.")
            return {'CANCELLED'}

        enum_items = []
        for rel in releases:
            tag = rel.get("tag_name", "")
            name = rel.get("name", tag)
            has_asset = any(a.get("name") == ADDON_FILENAME for a in rel.get("assets", []))
            if has_asset:
                label = f"{tag} — {name}"
                enum_items.append((tag, label, f"Release {tag}"))

        if not enum_items:
            for rel in releases:
                tag = rel.get("tag_name", "")
                name = rel.get("name", tag)
                enum_items.append((tag, f"{tag} — {name} (source)", f"Release {tag}"))

        if not enum_items:
            props.update_status = "Релизы не найдены"
            return {'CANCELLED'}

        props.available_versions.clear()
        for tag, label, desc in enum_items:
            item = props.available_versions.add()
            item.tag = tag
            item.label = label
            item.description = desc

        latest_tag = enum_items[0][0]
        latest_ver = string_to_version(latest_tag)
        current = CURRENT_VERSION

        if latest_ver > current:
            props.update_status = f"Доступно обновление: {latest_tag}"
        else:
            props.update_status = f"Установлена последняя версия ({version_to_string(current)})"

        return {'FINISHED'}


class BVH2FBX_OT_install_update(bpy.types.Operator):
    bl_idname = "bvh2fbx.install_update"
    bl_label = "Установить обновление"
    bl_description = "Скачать и установить выбранную версию плагина из GitHub"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        props = context.scene.bvh2fbx_props
        return len(props.available_versions) > 0 and props.selected_version_index >= 0

    def execute(self, context):
        props = context.scene.bvh2fbx_props

        if props.selected_version_index < 0 or props.selected_version_index >= len(props.available_versions):
            self.report({'ERROR'}, "Выберите версию для установки")
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
            self.report({'ERROR'}, f"Релиз {target_tag} не найден на GitHub")
            return {'CANCELLED'}

        asset_url = find_asset_url(target_release, ADDON_FILENAME)

        if not asset_url:
            zipball_url = target_release.get("zipball_url")
            if not zipball_url:
                self.report({'ERROR'}, f"Не найден файл {ADDON_FILENAME} в релизе {target_tag}")
                return {'CANCELLED'}

            try:
                tmp_dir = tempfile.mkdtemp(prefix="bvh2fbx_update_")
                zip_path = os.path.join(tmp_dir, "source.zip")
                download_file(zipball_url, zip_path)

                import zipfile
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    addon_found = False
                    for info in zf.infolist():
                        if info.filename.endswith(ADDON_FILENAME) and not info.is_dir():
                            with zf.open(info) as src, open(os.path.join(tmp_dir, ADDON_FILENAME), 'wb') as dst:
                                dst.write(src.read())
                            addon_found = True
                            break
                    if not addon_found:
                        self.report({'ERROR'}, f"Файл {ADDON_FILENAME} не найден в архиве")
                        shutil.rmtree(tmp_dir, ignore_errors=True)
                        return {'CANCELLED'}
                asset_url = None
            except Exception as e:
                self.report({'ERROR'}, f"Ошибка загрузки: {e}")
                return {'CANCELLED'}

        current_addon_path = get_addon_install_path()
        backup_path = current_addon_path + ".backup"
        new_addon_path = current_addon_path + ".new"

        try:
            if asset_url:
                tmp_dir = tempfile.mkdtemp(prefix="bvh2fbx_update_")
                tmp_file = os.path.join(tmp_dir, ADDON_FILENAME)
                download_file(asset_url, tmp_file)
                shutil.copy2(tmp_file, new_addon_path)
            else:
                extracted = os.path.join(tmp_dir, ADDON_FILENAME)
                shutil.copy2(extracted, new_addon_path)

            shutil.copy2(current_addon_path, backup_path)
            shutil.move(new_addon_path, current_addon_path)

            # Try to reload the addon without restarting Blender.
            # Do NOT use bpy.ops.preferences.addon_disable/enable because
            # disabling the currently-running addon can crash Blender.
            # Instead, use importlib.reload which is safer.
            try:
                import importlib
                import sys
                addon_module_name = __name__
                if addon_module_name in sys.modules:
                    importlib.reload(sys.modules[addon_module_name])
                self.report({'INFO'}, f"Обновлено до {target_tag}! Перезапустите Blender для полного применения.")
                props.update_status = f"Обновлено до {target_tag}! Перезапустите Blender."
            except Exception as reload_err:
                self.report({'INFO'}, f"Обновлено до {target_tag}! Перезапустите Blender для применения.")
                props.update_status = f"Обновлено до {target_tag}! Перезапустите Blender."
                print(f"[BVH2FBX] Reload note: {reload_err}. Manual restart needed.")

        except Exception as e:
            if os.path.exists(backup_path):
                try:
                    shutil.move(backup_path, current_addon_path)
                except Exception:
                    pass
            self.report({'ERROR'}, f"Ошибка установки: {e}")
            return {'CANCELLED'}
        finally:
            if 'tmp_dir' in locals():
                shutil.rmtree(tmp_dir, ignore_errors=True)
            if os.path.exists(new_addon_path):
                os.remove(new_addon_path)
            if os.path.exists(backup_path) and props.update_status.startswith("Обновлено"):
                try:
                    os.remove(backup_path)
                except Exception:
                    pass

        return {'FINISHED'}


# ============================================================================
# PROPERTIES
# ============================================================================

class BVH2FBX_VersionItem(bpy.types.PropertyGroup):
    tag: bpy.props.StringProperty(name="Tag", default="")
    label: bpy.props.StringProperty(name="Label", default="")
    description: bpy.props.StringProperty(name="Description", default="")


class BVH2FBX_Properties(bpy.types.PropertyGroup):
    bvh_filepath: bpy.props.StringProperty(
        name="BVH файл",
        description="Путь к BVH файлу motion capture",
        subtype='FILE_PATH',
        default="",
    )

    output_filepath: bpy.props.StringProperty(
        name="Выходной FBX",
        description="Путь к выходному FBX файлу",
        subtype='FILE_PATH',
        default="",
    )

    scale_factor: bpy.props.FloatProperty(
        name="Масштаб Root Motion",
        description="Масштабный коэффициент для Root Motion (1.0 = без изменения)",
        default=1.0,
        min=0.0001,
        max=100.0,
    )

    auto_export: bpy.props.BoolProperty(
        name="Автоэкспорт FBX",
        description="Автоматически экспортировать FBX после конвертации",
        default=False,
    )

    update_status: bpy.props.StringProperty(
        name="Статус обновления",
        default="",
    )

    available_versions: bpy.props.CollectionProperty(
        type=BVH2FBX_VersionItem,
    )

    selected_version_index: bpy.props.IntProperty(
        name="Версия",
        default=-1,
    )


# ============================================================================
# UI PANELS
# ============================================================================

class BVH2FBX_PT_main_panel(bpy.types.Panel):
    bl_label = "BVH → FBX для UE5"
    bl_idname = "BVH2FBX_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "BVH2FBX"

    def draw(self, context):
        layout = self.layout
        props = context.scene.bvh2fbx_props

        # File selection
        box = layout.box()
        box.label(text="Файлы", icon='FILE_FOLDER')
        box.prop(props, "bvh_filepath")
        box.prop(props, "output_filepath")
        box.prop(props, "scale_factor")
        box.prop(props, "auto_export")

        # Convert button
        layout.separator()
        layout.operator("bvh2fbx.convert", icon='PLAY')


class BVH2FBX_PT_info_panel(bpy.types.Panel):
    bl_label = "Информация"
    bl_idname = "BVH2FBX_PT_info_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "BVH2FBX"
    bl_parent_id = "BVH2FBX_PT_main_panel"

    def draw(self, context):
        layout = self.layout
        props = context.scene.bvh2fbx_props

        # Detect skeleton type
        armature = None
        if context.active_object and context.active_object.type == 'ARMATURE':
            armature = context.active_object
        else:
            for obj in context.scene.objects:
                if obj.type == 'ARMATURE':
                    armature = obj
                    break

        if armature:
            skel_type = detect_skeleton_type(armature)
            skel_names = {'ue5': 'UE5 Quinn', 'mixamo': 'Mixamo', 'unknown': 'Неизвестный'}
            layout.label(text=f"Скелет: {skel_names.get(skel_type, skel_type)}", icon='ARMATURE_DATA')
            layout.label(text=f"Костей: {len(armature.pose.bones)}")
        else:
            layout.label(text="Арматура не найдена", icon='ERROR')

        # BVH axis info
        if props.bvh_filepath and os.path.isfile(props.bvh_filepath):
            axis_fwd, axis_up = detect_bvh_axis_convention(props.bvh_filepath)
            layout.label(text=f"BVH оси: up={axis_up}, fwd={axis_fwd}", icon='WORLD')
        else:
            layout.label(text="BVH не выбран", icon='QUESTION')


class BVH2FBX_PT_update_panel(bpy.types.Panel):
    bl_label = "Обновления"
    bl_idname = "BVH2FBX_PT_update_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "BVH2FBX"
    bl_parent_id = "BVH2FBX_PT_main_panel"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        props = context.scene.bvh2fbx_props

        layout.label(text=f"Версия: {version_to_string(CURRENT_VERSION)}")

        layout.operator("bvh2fbx.check_updates", icon='WORLD')

        if props.update_status:
            layout.label(text=props.update_status)

        if len(props.available_versions) > 0:
            layout.prop(props, "selected_version_index", text="Версия")
            layout.operator("bvh2fbx.install_update", icon='IMPORT')


# ============================================================================
# REGISTRATION
# ============================================================================

classes = (
    BVH2FBX_VersionItem,
    BVH2FBX_Properties,
    BVH2FBX_OT_convert,
    BVH2FBX_OT_import_skeleton,
    BVH2FBX_OT_check_updates,
    BVH2FBX_OT_install_update,
    BVH2FBX_PT_main_panel,
    BVH2FBX_PT_info_panel,
    BVH2FBX_PT_update_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.bvh2fbx_props = bpy.props.PointerProperty(type=BVH2FBX_Properties)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.bvh2fbx_props


if __name__ == "__main__":
    register()
