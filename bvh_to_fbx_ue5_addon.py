bl_info = {
    "name": "BVH to FBX for UE5",
    "author": "BVH2FBX Converter v18.0",
    "version": (18, 0, 0),
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
# RETARGETING ENGINE v18.0 — COPY TRANSFORMS CONSTRAINT (WORLD SPACE)
# ============================================================================
#
# WHY THIS WORKS WHEN ALL PREVIOUS VERSIONS FAILED:
#
# v1-v17 tried to manually compute the retargeting math. This ALWAYS failed
# because the Mixamo armature has RotX(90°) + Scale(0.01) on the OBJECT,
# making bone.matrix_local contain non-orthogonal matrices that break
# decompose() and quaternion extraction.
#
# v18 uses Blender's OWN constraint system. Copy Transforms with
# target_space='WORLD' and owner_space='WORLD' tells Blender:
#   "Make the Mixamo bone's world transform = BVH bone's world transform"
#
# Blender handles ALL coordinate space conversions internally, correctly
# accounting for object rotations, scales, and different rest poses.
# We then read the constrained pose_bone.matrix and extract the
# rotation_quaternion and location that would produce this result.
#
# No decompose(), no 3x3 normalization, no M_rel calculations.
# Blender does the math. We just bake the result.
#
# Blender 5.x compatible: NO action.fcurves access. Normalization is
# done inline during the bake loop.
#


def _norm_rot3(mat4):
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
    # STEP 1: Log armature object transforms (diagnostics)
    # =========================================================================
    M_bvh_obj = bvh_armature.matrix_world
    M_mix_obj = ref_armature.matrix_world
    bvh_euler = _norm_rot3(M_bvh_obj).to_euler()
    mix_euler = _norm_rot3(M_mix_obj).to_euler()
    print(f"[BVH2FBX] BVH obj rot: ({math.degrees(bvh_euler.x):.1f}, {math.degrees(bvh_euler.y):.1f}, {math.degrees(bvh_euler.z):.1f}) deg")
    print(f"[BVH2FBX] Mixamo obj rot: ({math.degrees(mix_euler.x):.1f}, {math.degrees(mix_euler.y):.1f}, {math.degrees(mix_euler.z):.1f}) deg")
    print(f"[BVH2FBX] BVH obj scale: ({bvh_armature.scale.x:.4f}, {bvh_armature.scale.y:.4f}, {bvh_armature.scale.z:.4f})")
    print(f"[BVH2FBX] Mixamo obj scale: ({ref_armature.scale.x:.4f}, {ref_armature.scale.y:.4f}, {ref_armature.scale.z:.4f})")

    # =========================================================================
    # STEP 2: Add Copy Transforms constraints (WORLD space)
    # =========================================================================
    # This is the CORE of v18. We add a Copy Transforms constraint to each
    # mapped Mixamo bone, targeting the corresponding BVH bone. In WORLD
    # space, Blender automatically handles:
    #   - Different armature object rotations (RotX(90°))
    #   - Different armature object scales (0.01)
    #   - Different bone rest poses
    #   - Different coordinate system orientations
    #
    # The constraint makes: Mixamo_bone_world = BVH_bone_world
    # And Blender computes the correct armature-local transform internally.
    # =========================================================================
    constraints_added = {}
    for ref_name, bvh_name in bone_map.items():
        if ref_name not in ref_armature.pose.bones:
            continue
        if bvh_name not in bvh_armature.pose.bones:
            continue

        ref_pb = ref_armature.pose.bones[ref_name]

        # Remove any existing BVH2FBX constraints
        for c in list(ref_pb.constraints):
            if c.name.startswith("BVH2FBX_"):
                ref_pb.constraints.remove(c)

        # Add Copy Transforms constraint
        ct = ref_pb.constraints.new('COPY_TRANSFORMS')
        ct.name = "BVH2FBX_RETARGET"
        ct.target = bvh_armature
        ct.subtarget = bvh_name
        ct.target_space = 'WORLD'
        ct.owner_space = 'WORLD'
        constraints_added[ref_name] = bvh_name

    print(f"[BVH2FBX] Added {len(constraints_added)} Copy Transforms constraints (WORLD space)")

    # =========================================================================
    # STEP 3: Detect forward direction from BVH animation
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
    # STEP 4: Bake — read constrained pose and store quaternion + location
    # =========================================================================
    # For each frame, we:
    #   1. Set the frame, update view_layer (evaluates constraints)
    #   2. Read ref_pb.matrix (constrained, in armature-local space)
    #   3. Compute matrix_basis = the transform that produces this result
    #   4. Extract rotation_quaternion and location
    #   5. Store in frame_data for later keyframing
    #
    # The relationship is:
    #   bone.matrix = bone.bone.matrix_local @ bone.matrix_basis   (root bone)
    #   bone.matrix = parent.matrix @ local_rest @ bone.matrix_basis  (child)
    #
    # So: matrix_basis = local_rest^(-1) @ parent^(-1) @ constrained_matrix
    # For root: matrix_basis = bone.matrix_local^(-1) @ constrained_matrix
    # =========================================================================
    frame_data = {}  # (ref_name, frame_idx) -> (quat, loc)
    first_root_loc = None
    prev_quat = {}

    for fi in range(num_frames):
        frame = frame_start + fi
        scene.frame_set(frame)
        bpy.context.view_layer.update()

        for ref_name in constraints_added:
            ref_pb = ref_armature.pose.bones[ref_name]

            # Read constrained matrix in armature-local space
            constrained_matrix = ref_pb.matrix.copy()

            # Compute matrix_basis (the animation channel value)
            if ref_pb.parent:
                parent_matrix = ref_pb.parent.matrix.copy()
                parent_rest = ref_pb.parent.bone.matrix_local
                bone_rest = ref_pb.bone.matrix_local
                local_rest = parent_rest.inverted() @ bone_rest
                try:
                    matrix_basis = local_rest.inverted() @ parent_matrix.inverted() @ constrained_matrix
                except Exception:
                    matrix_basis = mathutils.Matrix.Identity(4)
            else:
                bone_rest = ref_pb.bone.matrix_local
                try:
                    matrix_basis = bone_rest.inverted() @ constrained_matrix
                except Exception:
                    matrix_basis = mathutils.Matrix.Identity(4)

            # Extract rotation (normalize 3x3 part to remove any scale/shear)
            rot3 = matrix_basis.to_3x3()
            for i in range(3):
                length = rot3.col[i].length
                if length > 1e-10:
                    rot3.col[i] /= length
                else:
                    rot3.col[i] = [0, 0, 0]
                    rot3.col[i][i] = 1.0
            quat = rot3.to_quaternion()

            # Extract location
            loc = matrix_basis.translation.copy()

            # Quaternion sign consistency
            if ref_name in prev_quat:
                if quat.dot(prev_quat[ref_name]) < 0:
                    quat = -quat
            prev_quat[ref_name] = quat.copy()

            # Track first root location for normalization
            if ref_pb.parent is None and first_root_loc is None:
                first_root_loc = loc.copy()

            # Normalize root location (start at origin)
            if ref_pb.parent is None and first_root_loc is not None:
                loc = loc - first_root_loc
                loc = loc * scale_factor

            frame_data[(ref_name, fi)] = (quat, loc)

    print(f"[BVH2FBX] Baked {num_frames} frames from constraints")

    # =========================================================================
    # STEP 5: Remove all constraints
    # =========================================================================
    for ref_name in constraints_added:
        ref_pb = ref_armature.pose.bones[ref_name]
        for c in list(ref_pb.constraints):
            if c.name.startswith("BVH2FBX_"):
                ref_pb.constraints.remove(c)

    print("[BVH2FBX] Removed all constraints")

    # =========================================================================
    # STEP 6: Create action and keyframe stored data
    # =========================================================================
    for pb in ref_armature.pose.bones:
        pb.rotation_mode = 'QUATERNION'

    if ref_armature.animation_data is None:
        ref_armature.animation_data_create()
    old_action = ref_armature.animation_data.action
    if old_action:
        ref_armature.animation_data.action = None

    new_action = bpy.data.actions.new(ref_armature.name + "_BVHAction")
    ref_armature.animation_data.action = new_action

    # Compute forward correction in root bone local space
    F_local = None
    if forward_quat and root_bone_name in ref_armature.pose.bones:
        root_pb = ref_armature.pose.bones[root_bone_name]
        root_rest_rot = _norm_rot3(root_pb.bone.matrix_local)
        root_rest_q = root_rest_rot.to_quaternion()
        F_local = root_rest_q.inverted() @ forward_quat @ root_rest_q
        F_local.normalize()

    # Apply stored frame data and keyframe
    for fi in range(num_frames):
        for ref_name in constraints_added:
            if (ref_name, fi) not in frame_data:
                continue

            ref_pb = ref_armature.pose.bones[ref_name]
            quat, loc = frame_data[(ref_name, fi)]

            # Apply forward correction to root bone
            if ref_pb.parent is None and F_local is not None:
                quat = F_local @ quat
                quat.normalize()
                loc = F_local @ loc

            ref_pb.rotation_quaternion = quat
            if ref_pb.parent is None:
                ref_pb.location = loc
            else:
                ref_pb.location = mathutils.Vector((0, 0, 0))

            ref_pb.keyframe_insert(data_path='rotation_quaternion', frame=fi, group=ref_pb.name)
            ref_pb.keyframe_insert(data_path='location', frame=fi, group=ref_pb.name)

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
        "bake_method": "copy_transforms_v18",
    }


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
        self.report({'INFO'},
                     f"Done! v{version_to_string(CURRENT_VERSION)} {skel} {mapped}/{total} bones "
                     f"{frames} frames dir:{fwd}")
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
        layout.operator("bvh2fbx.convert", text="Convert BVH → FBX", icon='PLAY')
        layout.separator()

        # Skeleton import
        box2 = layout.box()
        box2.label(text="Import Reference Skeleton", icon='ARMATURE_DATA')
        box2.operator("bvh2fbx.import_skeleton", text="Import FBX Skeleton", icon='IMPORT')

        layout.separator()

        # Updates
        box3 = layout.box()
        box3.label(text=f"v{version_to_string(CURRENT_VERSION)} | Updates", icon='INFO')
        row = box3.row()
        row.operator("bvh2fbx.check_updates", text="Check", icon='LOOP_BACK')
        if props.available_versions:
            box3.prop(props, "selected_version_index", text="Version")
            box3.operator("bvh2fbx.install_update", text="Install", icon='IMPORT')
        if props.update_status:
            box3.label(text=props.update_status)


classes = (
    BVH2FBX_VersionItem,
    BVH2FBX_Properties,
    BVH2FBX_OT_convert,
    BVH2FBX_OT_import_skeleton,
    BVH2FBX_OT_check_updates,
    BVH2FBX_OT_install_update,
    BVH2FBX_PT_main,
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
