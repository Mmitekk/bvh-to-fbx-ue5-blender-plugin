bl_info = {
    "name": "BVH to FBX for UE5",
    "author": "BVH2FBX Converter v6",
    "version": (6, 0, 0),
    "blender": (3, 0, 0),
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
            return asset.get("browser_download_url") or asset.get("url")
    return None


def download_file(url, dest_path):
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": "BVH2FBX-Blender-Addon"})
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
    """Auto-detect BVH coordinate system by analyzing bone offsets.

    BVH files store OFFSET values (relative bone positions) which reveal the
    coordinate system:
    - Y-up, -Z-forward (standard mocap): Hips offset ≈ (0, H, 0), LeftUpLeg ≈ (L, H, 0)
    - Z-up, Y-forward (Mixamo/game): Hips offset ≈ (0, 0, H), LeftUpLeg ≈ (L, 0, 0)

    Returns: (axis_forward, axis_up) strings for Blender's BVH importer
    """
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except Exception:
        return '-Z', 'Y'  # Default to standard

    # Find Hips OFFSET and LeftUpLeg OFFSET
    hips_offset = None
    left_upleg_offset = None

    lines = content.replace('\t', ' ').split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Find Hips joint
        if line.upper().startswith('JOINT') and 'HIPS' in line.upper():
            # Next lines should contain OFFSET
            for j in range(i + 1, min(i + 5, len(lines))):
                offset_line = lines[j].strip()
                if offset_line.upper().startswith('OFFSET'):
                    parts = offset_line.split()
                    try:
                        hips_offset = (float(parts[1]), float(parts[2]), float(parts[3]))
                    except (ValueError, IndexError):
                        pass
                    break

        # Find LeftUpLeg joint
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

    # Analyze: which axis is "up" (largest absolute value in Hips offset = height)?
    abs_hips = [abs(hips_offset[0]), abs(hips_offset[1]), abs(hips_offset[2])]
    up_axis_idx = abs_hips.index(max(abs_hips))

    if up_axis_idx == 1:
        # Y is up = standard BVH convention
        print(f"[BVH2FBX] Detected: Y-up (standard mocap) - Hips offset: {hips_offset}")
        return '-Z', 'Y'
    elif up_axis_idx == 2:
        # Z is up = game/Mixamo convention
        print(f"[BVH2FBX] Detected: Z-up (Mixamo/game) - Hips offset: {hips_offset}")
        # Determine forward axis from LeftUpLeg
        if left_upleg_offset:
            # In Z-up: LeftUpLeg should be to the left (+X or -X) with Z ≈ 0
            if abs(left_upleg_offset[1]) > abs(left_upleg_offset[0]) * 2:
                return 'Y', 'Z'  # Y-forward
            else:
                return '-Y', 'Z'  # -Y-forward
        return 'Y', 'Z'
    else:
        # X is up? Unusual but handle it
        print(f"[BVH2FBX] Detected: X-up (unusual) - Hips offset: {hips_offset}")
        return '-Z', 'X'


# ============================================================================
# BONE MATCHING UTILITIES
# ============================================================================

def find_bvh_for_target(bvh_bone_names, target_name, bone_map_dict):
    """Find the best matching BVH bone name for a target bone name."""
    for bvh_name, mapped_target in bone_map_dict.items():
        if mapped_target == target_name and bvh_name in bvh_bone_names:
            return bvh_name
    return None


def find_hips_bone(armature):
    """Find the Hips/pelvis bone in an armature."""
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
    """Get pose bones in parent-first hierarchical order."""
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
    """Find the root bone (bone with no parent)."""
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
    """Detect whether an armature is UE5 Quinn, Mixamo, or unknown.

    Returns: 'ue5', 'mixamo', or 'unknown'
    """
    bone_names = set(armature.pose.bones.keys())

    # Check for Mixamo prefix
    mixamorig_count = sum(1 for n in bone_names if n.startswith('mixamorig:'))
    if mixamorig_count > 5:
        return 'mixamo'

    # Check for UE5 Quinn bones
    ue5_markers = {'pelvis', 'spine_01', 'thigh_l', 'calf_l', 'upperarm_l'}
    ue5_match = len(ue5_markers & bone_names)
    if ue5_match >= 3:
        return 'ue5'

    return 'unknown'


def build_bone_map(bvh_armature, ref_armature, ref_skeleton_type):
    """Build bone mapping: ref_bone_name -> bvh_bone_name.

    For Mixamo target: direct name matching (1:1)
    For UE5 target: use BVH_TO_UE5 / MIXAMO_TO_UE5 lookup tables
    """
    bvh_bone_names = set(bvh_armature.pose.bones.keys())
    bone_map = {}

    if ref_skeleton_type == 'mixamo':
        # Direct name matching: BVH mixamorig:Name → ref mixamorig:Name
        # Also handle standard BVH names → mixamorig:Name
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
            # Finger mappings
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
            # Direct match: same name in BVH
            if pb.name in bvh_bone_names:
                bone_map[pb.name] = pb.name
            else:
                # Try standard → mixamorig mapping
                for std_name, mix_name in STANDARD_TO_MIXAMO.items():
                    if mix_name == pb.name and std_name in bvh_bone_names:
                        bone_map[pb.name] = std_name
                        break
    else:
        # UE5 or unknown: use lookup tables
        for pb in ref_armature.pose.bones:
            bvh_match = find_bvh_for_target(bvh_bone_names, pb.name, ALL_BVH_MAPS_UE5)
            if bvh_match:
                bone_map[pb.name] = bvh_match

    return bone_map


# ============================================================================
# RETARGETING ENGINE v6.0 — SIMPLE CONJUGATION FORMULA
# ============================================================================
# v6.0 RETARGETING APPROACH: Simple conjugation (no delta_parent.inverted())
#
# THE KEY FIX: The old hierarchical formula used:
#   pose_delta = ue5_rest.inverted() @ delta_parent.inverted() @ delta_bone @ ue5_rest
#
# This is WRONG because delta_parent.inverted() double-corrects for the parent's
# rotation change. Blender's pose evaluation already handles the parent chain when
# you set each bone's rotation_quaternion independently — each bone's local
# rotation is composed with its parent's world transform automatically.
#
# The CORRECT formula for ALL bones (root, children, everything) is the simple
# conjugation:
#   pose_delta = ref_rest.inverted() @ delta_bone @ ref_rest
#
# Where:
#   delta_bone = bvh_curr_world_rot @ bvh_ref_world_rot.inv()
#     — the armature-local (world-space within the armature) rotation delta
#   ref_rest = pb.bone.matrix_local.to_3x3()
#     — the target bone's T-pose orientation in armature-local space
#
# Why this works:
# 1. delta_bone represents the absolute rotation change of the BVH bone in
#    world/armature space
# 2. Conjugating by ref_rest.inv() ... ref_rest converts this delta into the
#    target bone's local space
# 3. Blender's pose system then correctly composes this with the parent chain
#    during evaluation — there is no need to manually subtract parent deltas
#
# Root bone handling:
# - Mixamo (root = Hips): Apply simple conjugation for rotation, transfer Hips
#   world displacement as root motion translation, apply forward direction correction
# - UE5 (root is separate "root" bone): Apply only root motion translation (no
#   rotation) to the root bone, all other bones use simple conjugation
#
# BVH source variants handled:
# - Standard BVH (LeftToeBase) and SOMA-style BVH (LeftToe) both map correctly
# - Mixamo BVH names (mixamorig:*) handled via STANDARD_TO_MIXAMO mapping

def retarget_animation(bvh_armature, ref_armature, scale_factor=1.0):
    """Retarget animation from BVH armature to reference armature.

    Strategy: SIMPLE CONJUGATION — same formula for ALL bones.
    For each frame and each mapped bone:
      1. Compute BVH armature-local delta: delta_bone = curr @ ref.inv()
      2. Convert delta to target bone's local space via conjugation:
         pose_delta = ref_rest.inv() @ delta_bone @ ref_rest
      3. Set pb.rotation_quaternion from pose_delta

    This approach works because Blender's pose evaluation automatically composes
    each bone's local rotation with its parent chain. The old hierarchical formula
    that used delta_parent.inverted() was double-correcting for parent rotation,
    producing incorrect results for child bones.

    Args:
        bvh_armature: Blender armature with BVH animation
        ref_armature: Blender armature (target skeleton) to animate
        scale_factor: Scale for root motion translation

    Returns:
        (action, stats_dict)
    """
    scene = bpy.context.scene
    I3 = mathutils.Matrix.Identity(3)
    I4 = mathutils.Matrix.Identity(4)

    # Detect target skeleton type
    ref_skeleton_type = detect_skeleton_type(ref_armature)
    print(f"[BVH2FBX] Target skeleton type: {ref_skeleton_type}")

    # Build bone mapping
    bone_map = build_bone_map(bvh_armature, ref_armature, ref_skeleton_type)

    # Get BVH animation info
    bvh_action = None
    if bvh_armature.animation_data and bvh_armature.animation_data.action:
        bvh_action = bvh_armature.animation_data.action

    if not bvh_action:
        return None, {"error": "BVH armature has no animation"}

    frame_start = int(bvh_action.frame_range[0])
    frame_end = int(bvh_action.frame_range[1])
    num_frames = frame_end - frame_start + 1

    # Find BVH Hips bone for root motion
    bvh_hips = find_hips_bone(bvh_armature)

    # Find root bone in target armature
    root_bone_name = find_root_bone(ref_armature)
    if not root_bone_name:
        return None, {"error": "No root bone found in reference armature"}

    # Check if root bone is mapped (e.g., Mixamo: Hips IS the root)
    root_is_mapped = root_bone_name in bone_map
    root_bvh_name = bone_map.get(root_bone_name)

    print(f"[BVH2FBX] Root bone: {root_bone_name} (mapped={root_is_mapped}, bvh={root_bvh_name})")

    # =========================================================================
    # STEP 1: Capture BVH reference pose at frame_start
    # =========================================================================
    scene.frame_set(frame_start)
    bpy.context.view_layer.update()

    bvh_ref_rot = {}
    bvh_ref_pos = {}
    for pb in bvh_armature.pose.bones:
        bvh_ref_rot[pb.name] = pb.matrix.to_3x3().copy()
        bvh_ref_pos[pb.name] = pb.matrix.translation.copy()

    # =========================================================================
    # STEP 2: Capture target rest pose (armature-local)
    # =========================================================================
    ref_rest_rot = {}
    for pb in ref_armature.pose.bones:
        ref_rest_rot[pb.name] = pb.bone.matrix_local.to_3x3().copy()

    # BVH Hips reference position for root motion
    bvh_hips_ref_pos = None
    if bvh_hips:
        bvh_hips_ref_pos = bvh_ref_pos.get(bvh_hips.name)

    # =========================================================================
    # STEP 3: Detect forward direction from BVH Hips displacement
    # =========================================================================
    forward_rotation = mathutils.Matrix.Identity(4)
    if bvh_hips and num_frames > 1:
        start_pos = bvh_ref_pos.get(bvh_hips.name, mathutils.Vector((0, 0, 0)))

        scene.frame_set(frame_end)
        bpy.context.view_layer.update()
        end_pos = bvh_hips.matrix.translation.copy()

        walk_dir = end_pos - start_pos
        walk_dir.z = 0

        if walk_dir.length > 0.001:
            walk_dir.normalize()
            target_dir = mathutils.Vector((0, -1, 0))  # UE5 forward = -Y

            dot = walk_dir.dot(target_dir)
            if dot < -0.9999:
                forward_rotation = mathutils.Matrix.Rotation(math.pi, 4, 'Z')
            elif dot < 0.9999:
                axis = walk_dir.cross(target_dir)
                if axis.length > 0.0001:
                    axis.normalize()
                    angle = math.acos(max(-1.0, min(1.0, dot)))
                    forward_rotation = mathutils.Matrix.Rotation(angle, 4, axis)

            print(f"[BVH2FBX] Walk direction: ({walk_dir.x:.3f}, {walk_dir.y:.3f}, {walk_dir.z:.3f})")
            dot_clamped = max(-1.0, min(1.0, dot))
            print(f"[BVH2FBX] Forward correction: {math.degrees(math.acos(dot_clamped)):.1f} degrees")

    # =========================================================================
    # STEP 4: Create new animation action on reference armature
    # =========================================================================
    if ref_armature.animation_data is None:
        ref_armature.animation_data_create()

    action_name = ref_armature.name + "_BVHAction"
    new_action = bpy.data.actions.new(action_name)
    ref_armature.animation_data.action = new_action

    scene.frame_start = 0
    scene.frame_end = num_frames - 1

    # =========================================================================
    # STEP 5: Switch to POSE mode and set rotation mode to QUATERNION
    # =========================================================================
    bpy.context.view_layer.objects.active = ref_armature
    bpy.ops.object.mode_set(mode='POSE')

    for pb in ref_armature.pose.bones:
        pb.rotation_mode = 'QUATERNION'

    # =========================================================================
    # STEP 6: Track which bones were mapped
    # =========================================================================
    mapped_bones = []
    unmapped_bones = []

    for pb in get_bones_in_hierarchy_order(ref_armature):
        if pb.name == root_bone_name and not root_is_mapped:
            continue  # Skip unmapped root (UE5 style)
        if pb.name in bone_map:
            mapped_bones.append(pb.name)
        elif pb.name != root_bone_name:
            unmapped_bones.append(pb.name)

    print(f"[BVH2FBX] Mapped {len(mapped_bones)} bones, unmapped {len(unmapped_bones)}")
    print(f"[BVH2FBX] Mapped: {mapped_bones}")
    if unmapped_bones:
        print(f"[BVH2FBX] Unmapped: {unmapped_bones}")

    # =========================================================================
    # STEP 7: Main retargeting loop — SIMPLE CONJUGATION FORMULA
    # =========================================================================
    # Diagnostic bones to log on the first frame (key bones for debugging)
    diagnostic_bones = ['Hips', 'Spine', 'Head', 'LeftUpLeg', 'LeftLeg',
                        'LeftFoot', 'LeftToeBase', 'LeftToe',
                        'mixamorig:Hips', 'mixamorig:Spine', 'mixamorig:Head',
                        'pelvis', 'spine_01', 'head', 'thigh_l', 'calf_l',
                        'foot_l', 'ball_l']

    for fi in range(num_frames):
        frame = frame_start + fi
        scene.frame_set(frame)
        bpy.context.view_layer.update()

        # --- Compute BVH armature-local deltas for all bones ---
        # delta_bone = curr_world_rot @ ref_world_rot.inv()
        # This is the absolute rotation change in armature-local (world) space
        bvh_delta = {}
        for pb in bvh_armature.pose.bones:
            curr = pb.matrix.to_3x3().copy()
            ref = bvh_ref_rot.get(pb.name, I3)
            bvh_delta[pb.name] = curr @ ref.inverted()

        # --- Diagnostic logging on first frame ---
        if fi == 0:
            print("[BVH2FBX] === DIAGNOSTIC: First frame delta values ===")
            for diag_name in diagnostic_bones:
                if diag_name in bvh_delta:
                    d = bvh_delta[diag_name]
                    q = d.to_quaternion()
                    angle = math.degrees(2 * math.acos(min(1.0, abs(q.w))))
                    print(f"  BVH delta '{diag_name}': quat=({q.x:.4f}, {q.y:.4f}, {q.z:.4f}, {q.w:.4f}) angle={angle:.1f}deg")
            # Also log ref_rest for a few target bones
            print("[BVH2FBX] === DIAGNOSTIC: Target rest rotations ===")
            for diag_name in diagnostic_bones:
                if diag_name in ref_rest_rot:
                    r = ref_rest_rot[diag_name]
                    rq = r.to_quaternion()
                    angle = math.degrees(2 * math.acos(min(1.0, abs(rq.w))))
                    print(f"  ref_rest '{diag_name}': quat=({rq.x:.4f}, {rq.y:.4f}, {rq.z:.4f}, {rq.w:.4f}) angle={angle:.1f}deg")
            # Log pose_delta for mapped bones on first frame
            print("[BVH2FBX] === DIAGNOSTIC: First frame pose_delta (simple conjugation) ===")
            for ref_name, bvh_name in bone_map.items():
                if bvh_name in bvh_delta and ref_name in ref_rest_rot:
                    delta_bone = bvh_delta[bvh_name]
                    ref_rest = ref_rest_rot[ref_name]
                    pose_delta = ref_rest.inverted() @ delta_bone @ ref_rest
                    pq = pose_delta.to_quaternion()
                    angle = math.degrees(2 * math.acos(min(1.0, abs(pq.w))))
                    print(f"  pose_delta '{ref_name}' <- '{bvh_name}': quat=({pq.x:.4f}, {pq.y:.4f}, {pq.z:.4f}, {pq.w:.4f}) angle={angle:.1f}deg")

        # --- Handle root bone ---
        root_pb = ref_armature.pose.bones.get(root_bone_name)
        if root_pb:
            if root_is_mapped and root_bvh_name:
                # Root IS a mapped bone (e.g., Mixamo: Hips = root)
                # Apply the same simple conjugation formula for rotation
                delta_root = bvh_delta.get(root_bvh_name, I3)
                root_rest = ref_rest_rot.get(root_bone_name, I3)

                # Simple conjugation formula (same for ALL bones)
                pose_delta = root_rest.inverted() @ delta_root @ root_rest
                q = pose_delta.to_quaternion()
                if q.w < 0:
                    q = -q
                root_pb.rotation_quaternion = q

                # Root motion translation from Hips displacement
                if bvh_hips and bvh_hips_ref_pos:
                    hips_pos = bvh_hips.matrix.translation
                    disp = hips_pos - bvh_hips_ref_pos
                    disp_corrected = forward_rotation @ disp
                    root_pb.location = disp_corrected * scale_factor
                else:
                    root_pb.location = (0, 0, 0)
            else:
                # Root NOT mapped (UE5 style) — only translation, no rotation
                if bvh_hips and bvh_hips_ref_pos:
                    hips_pos = bvh_hips.matrix.translation
                    disp = hips_pos - bvh_hips_ref_pos
                    disp_corrected = forward_rotation @ disp
                    root_pb.location = disp_corrected * scale_factor
                else:
                    root_pb.location = (0, 0, 0)
                root_pb.rotation_quaternion = (1, 0, 0, 0)

            root_pb.keyframe_insert(data_path='location', frame=fi, group=root_bone_name)
            root_pb.keyframe_insert(data_path='rotation_quaternion', frame=fi, group=root_bone_name)

        # --- Retarget each reference bone in hierarchy order ---
        for pb in get_bones_in_hierarchy_order(ref_armature):
            if pb.name == root_bone_name:
                continue  # Already handled above

            bvh_name = bone_map.get(pb.name)

            if bvh_name and bvh_name in bvh_armature.pose.bones:
                # MAPPED BONE: Simple conjugation formula
                # THE KEY FIX: No delta_parent.inverted()!
                # Blender's pose evaluation handles the parent chain automatically.
                # We only need to convert the armature-local delta into the target
                # bone's local space via conjugation:
                #   pose_delta = ref_rest.inv() @ delta_bone @ ref_rest
                delta_bone = bvh_delta.get(bvh_name, I3)
                ref_rest = ref_rest_rot.get(pb.name, I3)

                pose_delta = ref_rest.inverted() @ delta_bone @ ref_rest

                q = pose_delta.to_quaternion()
                if q.w < 0:
                    q = -q
                pb.rotation_quaternion = q
                pb.location = (0, 0, 0)
            else:
                # UNMAPPED BONE: Keep rest pose
                pb.rotation_quaternion = (1, 0, 0, 0)
                pb.location = (0, 0, 0)

            pb.keyframe_insert(data_path='rotation_quaternion', frame=fi, group=pb.name)
            pb.keyframe_insert(data_path='location', frame=fi, group=pb.name)

    bpy.ops.object.mode_set(mode='OBJECT')

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
        "forward_correction": "Yes" if forward_rotation != I4 else "No",
    }

    return new_action, stats


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
            bpy.ops.object.select_all(action='DESELECT')
            bvh_armature.select_set(True)
            bpy.ops.object.delete()
            if orig_action and ref_armature.animation_data:
                ref_armature.animation_data.action = orig_action
            return {'CANCELLED'}

        if action is None:
            error = stats.get('error', 'Unknown error')
            self.report({'ERROR'}, f"Ретаргетинг не удался: {error}")
            bpy.ops.object.select_all(action='DESELECT')
            bvh_armature.select_set(True)
            bpy.ops.object.delete()
            return {'CANCELLED'}

        # Step 3: Clean up - remove BVH armature
        bpy.ops.object.select_all(action='DESELECT')
        bvh_armature.select_set(True)
        bpy.ops.object.delete()

        # Step 4: Make reference armature active
        bpy.ops.object.select_all(action='DESELECT')
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
                     f"Готово! Скелет: {skel}, Костей: {total}, Сопоставлено: {mapped}, "
                     f"Кадров: {stats.get('frame_count', 0)}, "
                     f"Root Motion: {root_motion} (bone: {root_name}, mapped: {root_mapped}), "
                     f"Коррекция направления: {fwd_corr}")

        return {'FINISHED'}


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

            self.report({'INFO'}, f"Обновлено до {target_tag}! Перезапустите Blender.")
            props.update_status = f"Обновлено до {target_tag}! Перезапустите Blender."

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
            layout.label(text=f"BVH оси: up={axis_up}, fwd={axis_fwd}", icon='ORIENTATION_GLOBAL')
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

        layout.operator("bvh2fbx.check_updates", icon='URL')

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
