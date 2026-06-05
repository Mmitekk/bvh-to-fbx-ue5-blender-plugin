bl_info = {
    "name": "BVH to FBX for UE5",
    "author": "BVH2FBX Converter v3",
    "version": (3, 3, 0),
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

CURRENT_VERSION = bl_info["version"]  # (3, 3, 0)


def version_to_string(v):
    """Convert version tuple to string like '3.3.0'."""
    return ".".join(str(x) for x in v)


def string_to_version(s):
    """Convert version string like '3.3.0' to tuple (3, 3, 0)."""
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
    """Fetch list of releases from GitHub API."""
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
    """Find download URL for a specific file in release assets."""
    for asset in release.get("assets", []):
        if asset.get("name") == filename:
            return asset.get("browser_download_url") or asset.get("url")
    return None


def download_file(url, dest_path):
    """Download a file from URL to dest_path."""
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": "BVH2FBX-Blender-Addon"})
    with urllib.request.urlopen(req, context=ctx, timeout=60) as resp:
        with open(dest_path, "wb") as f:
            shutil.copyfileobj(resp, f)


def get_addon_install_path():
    """Get the path where the addon .py file is currently installed."""
    return os.path.abspath(__file__)


# ============================================================================
# BONE MAPPING: BVH bone names -> UE5 Quinn bone names
# ============================================================================
# IMPORTANT: Order matters for find_bvh_for_ue5() which returns first match.
# We put the most specific/important mapping first to avoid duplicates winning.

BVH_TO_UE5 = {
    # Spine (FIXED: Spine1->spine_02, Spine2->spine_03)
    'Hips': 'pelvis',
    'Spine': 'spine_01',
    'Spine1': 'spine_02',
    'Spine2': 'spine_03',
    'Spine3': 'spine_04',
    'Chest': 'spine_04',
    # Neck & Head
    'Neck': 'neck_01',
    'Neck1': 'neck_02',
    'Neck2': 'neck_03',
    'Head': 'head',
    # Left Arm
    'LeftShoulder': 'clavicle_l',
    'LeftArm': 'upperarm_l',
    'LeftForeArm': 'lowerarm_l',
    'LeftHand': 'hand_l',
    # Left Fingers
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
    # Right Arm
    'RightShoulder': 'clavicle_r',
    'RightArm': 'upperarm_r',
    'RightForeArm': 'lowerarm_r',
    'RightHand': 'hand_r',
    # Right Fingers
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
    # Left Leg (FIXED: LeftLeg->calf_l, NOT thigh_l)
    'LeftUpLeg': 'thigh_l',
    'LeftLeg': 'calf_l',
    'LeftShin': 'calf_l',
    'LeftFoot': 'foot_l',
    'LeftToeBase': 'ball_l',
    # Right Leg (FIXED: RightLeg->calf_r, NOT thigh_r)
    'RightUpLeg': 'thigh_r',
    'RightLeg': 'calf_r',
    'RightShin': 'calf_r',
    'RightFoot': 'foot_r',
    'RightToeBase': 'ball_r',
}

# Mixamo naming convention
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

# Combine all mappings (standard first, then mixamo)
ALL_BVH_MAPS = OrderedDict()
ALL_BVH_MAPS.update(BVH_TO_UE5)
ALL_BVH_MAPS.update(MIXAMO_TO_UE5)


# ============================================================================
# BONE MATCHING UTILITIES
# ============================================================================

def find_bvh_for_ue5(bvh_bone_names, ue5_name):
    """Find the best matching BVH bone name for a UE5 bone name.

    Returns the FIRST mapping that matches and exists in the BVH armature.
    Since ALL_BVH_MAPS is ordered, more specific mappings come first.
    """
    for bvh_name, mapped_ue5 in ALL_BVH_MAPS.items():
        if mapped_ue5 == ue5_name and bvh_name in bvh_bone_names:
            return bvh_name
    return None


def find_hips_bone(armature):
    """Find the Hips/pelvis bone in an armature."""
    candidates = ['Hips', 'hips', 'hip', 'Pelvis', 'pelvis', 'mixamorig:Hips']
    for name in candidates:
        if name in armature.pose.bones:
            return armature.pose.bones[name]
    # Fallback: find bone with many children (likely the hips)
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
    """Find the root bone (bone with no parent) in the armature.

    Does NOT modify the skeleton - just finds an existing root bone.
    Returns the bone name or None.
    """
    # Prefer bones named 'root' or 'Root'
    for candidate in ['root', 'Root']:
        if candidate in armature.pose.bones:
            pb = armature.pose.bones[candidate]
            if pb.parent is None:
                return candidate

    # Otherwise, find any bone with no parent
    for pb in armature.pose.bones:
        if pb.parent is None:
            return pb.name

    return None


# ============================================================================
# RETARGETING ENGINE v3.3 — COMPLETE REWRITE
# ============================================================================
# Key fixes over v3.2:
# 1. BVH rest pose captured from edit bones (pb.bone.matrix_local),
#    NOT from animated first frame
# 2. Bone mapping fixed: LeftLeg->calf_l, Spine1->spine_02, etc.
# 3. Unmapped bone world rotation computed using local rest rotation,
#    NOT world rest rotation (fixes hierarchy corruption)
# 4. Root motion with automatic forward direction detection
# 5. Animation applied directly to original armature (mesh stays bound)
# 6. No skeleton modifications (no adding Root bone)

def retarget_animation(bvh_armature, ref_armature, scale_factor=1.0):
    """Retarget animation from BVH armature to reference (UE5) armature.

    Strategy: World-space rotation delta matching with proper rest pose handling.
    For each frame and each mapped bone:
      1. Compute BVH bone's world rotation delta from EDIT MODE rest pose
      2. Apply same delta to UE5 bone's EDIT MODE rest pose
      3. Convert to local rotation relative to parent's animated rotation
    Root motion: extracted from BVH Hips displacement with auto forward detection

    Args:
        bvh_armature: Blender armature with BVH animation
        ref_armature: Blender armature (UE5 skeleton) to animate
        scale_factor: Scale for root motion translation

    Returns:
        (action, stats_dict)
    """
    scene = bpy.context.scene

    # Get BVH animation info
    bvh_action = None
    if bvh_armature.animation_data and bvh_armature.animation_data.action:
        bvh_action = bvh_armature.animation_data.action

    if not bvh_action:
        return None, {"error": "BVH armature has no animation"}

    frame_start = int(bvh_action.frame_range[0])
    frame_end = int(bvh_action.frame_range[1])
    num_frames = frame_end - frame_start + 1

    # Build bone mapping: ref_bone_name -> bvh_bone_name
    bvh_bone_names = set(bvh_armature.pose.bones.keys())
    bone_map = {}  # ref_name -> bvh_name

    for pb in ref_armature.pose.bones:
        bvh_match = find_bvh_for_ue5(bvh_bone_names, pb.name)
        if bvh_match:
            bone_map[pb.name] = bvh_match

    # Find BVH Hips bone for root motion
    bvh_hips = find_hips_bone(bvh_armature)

    # Find root bone in UE5 armature (DO NOT MODIFY SKELETON)
    root_bone_name = find_root_bone(ref_armature)
    if not root_bone_name:
        return None, {"error": "No root bone found in reference armature"}

    # -------------------------------------------------------------------------
    # Store REST POSE data from EDIT BONES
    # This is the CRITICAL fix: we use pb.bone.matrix_local which gives
    # the actual rest pose (edit mode) matrix, NOT the animated first frame.
    # -------------------------------------------------------------------------
    # BVH rest pose world matrices (from edit bones)
    bvh_rest_world = {}
    for pb in bvh_armature.pose.bones:
        # pb.bone.matrix_local is the bone's rest matrix in armature-local space
        # Multiply by armature's world matrix to get world-space rest pose
        bvh_rest_world[pb.name] = (bvh_armature.matrix_world @ pb.bone.matrix_local).copy()

    # UE5 rest pose world matrices (from edit bones)
    ref_rest_world = {}
    for pb in ref_armature.pose.bones:
        ref_rest_world[pb.name] = (ref_armature.matrix_world @ pb.bone.matrix_local).copy()

    # UE5 rest LOCAL rotation matrices (relative to parent's rest)
    # This is needed for unmapped bones to correctly compute their animated world rotation
    ref_rest_local_rot = {}  # bone_name -> 3x3 rotation relative to parent rest
    for pb in ref_armature.pose.bones:
        if pb.parent:
            parent_rest_world_3x3 = ref_rest_world[pb.parent.name].to_3x3()
            bone_rest_world_3x3 = ref_rest_world[pb.name].to_3x3()
            ref_rest_local_rot[pb.name] = parent_rest_world_3x3.inverted() @ bone_rest_world_3x3
        else:
            ref_rest_local_rot[pb.name] = ref_rest_world[pb.name].to_3x3()

    # BVH Hips rest world position for root motion baseline
    bvh_hips_rest_pos = None
    if bvh_hips and bvh_hips.name in bvh_rest_world:
        bvh_hips_rest_pos = bvh_rest_world[bvh_hips.name].translation.copy()

    # -------------------------------------------------------------------------
    # Detect forward direction from BVH Hips displacement
    # The character should walk along UE5's forward direction.
    # In Blender, UE5 characters typically face -Y.
    # We compute the net walking direction from BVH and rotate
    # the root motion to align with -Y.
    # -------------------------------------------------------------------------
    forward_rotation = mathutils.Matrix.Identity(4)
    if bvh_hips and num_frames > 1:
        # Sample first and last frames to get walking direction
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
            # UE5 forward in Blender is -Y
            target_dir = mathutils.Vector((0, -1, 0))

            # Compute rotation from walk_dir to target_dir
            dot = walk_dir.dot(target_dir)
            if dot < -0.9999:
                # Nearly opposite: 180 degree rotation around Z
                forward_rotation = mathutils.Matrix.Rotation(math.pi, 4, 'Z')
            elif dot < 0.9999:
                axis = walk_dir.cross(target_dir)
                if axis.length > 0.0001:
                    axis.normalize()
                    angle = math.acos(max(-1.0, min(1.0, dot)))
                    forward_rotation = mathutils.Matrix.Rotation(angle, 4, axis)

            print(f"[BVH2FBX] Walk direction: ({walk_dir.x:.3f}, {walk_dir.y:.3f}, {walk_dir.z:.3f})")
            print(f"[BVH2FBX] Applied forward correction: {math.degrees(math.acos(max(-1.0, min(1.0, dot)))):.1f} degrees")

    # -------------------------------------------------------------------------
    # Create new animation action on reference armature
    # -------------------------------------------------------------------------
    if ref_armature.animation_data is None:
        ref_armature.animation_data_create()

    action_name = ref_armature.name + "_BVHAction"
    new_action = bpy.data.actions.new(action_name)
    ref_armature.animation_data.action = new_action

    scene.frame_start = 0
    scene.frame_end = num_frames - 1

    # -------------------------------------------------------------------------
    # Switch to POSE mode and set rotation mode
    # -------------------------------------------------------------------------
    bpy.context.view_layer.objects.active = ref_armature
    bpy.ops.object.mode_set(mode='POSE')

    for pb in ref_armature.pose.bones:
        pb.rotation_mode = 'YZX'

    # -------------------------------------------------------------------------
    # Track which bones were mapped
    # -------------------------------------------------------------------------
    mapped_bones = []
    unmapped_bones = []

    for pb in get_bones_in_hierarchy_order(ref_armature):
        if pb.name == root_bone_name:
            continue
        if pb.name in bone_map:
            mapped_bones.append(pb.name)
        else:
            unmapped_bones.append(pb.name)

    print(f"[BVH2FBX] Mapped {len(mapped_bones)} bones, unmapped {len(unmapped_bones)}")
    print(f"[BVH2FBX] Mapped: {mapped_bones}")

    # -------------------------------------------------------------------------
    # Main retargeting loop
    # -------------------------------------------------------------------------
    for fi in range(num_frames):
        frame = frame_start + fi
        scene.frame_set(frame)
        bpy.context.view_layer.update()

        # --- Root Motion ---
        root_pb = ref_armature.pose.bones.get(root_bone_name)
        if root_pb and bvh_hips:
            hips_world_pos = bvh_hips.matrix.translation
            if bvh_hips_rest_pos:
                disp = hips_world_pos - bvh_hips_rest_pos
                # Apply forward direction correction
                disp_corrected = forward_rotation @ disp
                root_pb.location = disp_corrected * scale_factor
            else:
                root_pb.location = (0, 0, 0)

            # Root bone only carries translation, no rotation
            root_pb.rotation_euler = (0, 0, 0)
            root_pb.keyframe_insert(data_path='location', frame=fi, group=root_bone_name)
            root_pb.keyframe_insert(data_path='rotation_euler', frame=fi, group=root_bone_name)
        elif root_pb:
            root_pb.location = (0, 0, 0)
            root_pb.rotation_euler = (0, 0, 0)
            root_pb.keyframe_insert(data_path='location', frame=fi, group=root_bone_name)
            root_pb.keyframe_insert(data_path='rotation_euler', frame=fi, group=root_bone_name)

        # --- Retarget each reference bone in hierarchy order ---
        # Track animated world ROTATIONS (3x3) for correct parent-child computation
        ref_animated_world_rot = {}

        # Root bone's animated world rotation = its rest world rotation
        # (root has identity or near-identity rotation, no rotation animation)
        if root_bone_name in ref_rest_world:
            ref_animated_world_rot[root_bone_name] = ref_rest_world[root_bone_name].to_3x3().copy()
        else:
            ref_animated_world_rot[root_bone_name] = mathutils.Matrix.Identity(3)

        for pb in get_bones_in_hierarchy_order(ref_armature):
            if pb.name == root_bone_name:
                continue

            bvh_name = bone_map.get(pb.name)
            parent_name = pb.parent.name if pb.parent else root_bone_name

            # Get parent's animated world rotation
            parent_rot = ref_animated_world_rot.get(parent_name, mathutils.Matrix.Identity(3))

            if bvh_name and bvh_name in bvh_armature.pose.bones:
                # ---- MAPPED BONE: retarget from BVH ----
                bvh_pb = bvh_armature.pose.bones[bvh_name]

                # BVH bone's world rotation at this frame (animated)
                bvh_world_rot = bvh_pb.matrix.to_3x3()

                # BVH bone's REST world rotation (from edit bones, not animated frame!)
                bvh_rest_rot = bvh_rest_world.get(bvh_name,
                    mathutils.Matrix.Identity(4)).to_3x3()

                # UE5 bone's REST world rotation (from edit bones)
                ref_rest_rot = ref_rest_world.get(pb.name,
                    mathutils.Matrix.Identity(4)).to_3x3()

                # Rotation delta: how much BVH bone rotated FROM ITS REST POSE
                # This is the key fix: we use the actual rest pose, not frame_start
                delta = bvh_world_rot @ bvh_rest_rot.inverted()

                # Apply same delta to UE5 rest rotation
                desired_world_rot = delta @ ref_rest_rot

                # Convert to local rotation (relative to animated parent)
                local_rot = parent_rot.inverted() @ desired_world_rot

                # Set the pose bone rotation
                local_euler = local_rot.to_euler('YZX')
                pb.rotation_euler = local_euler
                pb.location = (0, 0, 0)

                # Store animated world rotation for children
                ref_animated_world_rot[pb.name] = (parent_rot @ local_rot).copy()

            else:
                # ---- UNMAPPED BONE: keep rest pose ----
                pb.rotation_euler = (0, 0, 0)
                pb.location = (0, 0, 0)

                # CRITICAL FIX: Use LOCAL rest rotation (relative to parent rest),
                # NOT world rest rotation. Using world rest rotation here was
                # breaking the hierarchy because it doesn't account for parent
                # animation correctly.
                #
                # World rotation of unmapped bone = parent_animated_rot @ local_rest_rot
                # NOT = parent_animated_rot @ bone_world_rest_rot
                local_rest_rot = ref_rest_local_rot.get(pb.name,
                    mathutils.Matrix.Identity(3))

                ref_animated_world_rot[pb.name] = (parent_rot @ local_rest_rot).copy()

            # Keyframe rotation and location
            pb.keyframe_insert(data_path='rotation_euler', frame=fi, group=pb.name)
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
        "forward_correction": "Yes" if forward_rotation != mathutils.Matrix.Identity(4) else "No",
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
        return props.bvh_filepath and context.active_object and context.active_object.type == 'ARMATURE'

    def execute(self, context):
        props = context.scene.bvh2fbx_props

        # Validate BVH file
        if not os.path.isfile(props.bvh_filepath):
            self.report({'ERROR'}, f"BVH файл не найден: {props.bvh_filepath}")
            return {'CANCELLED'}

        # Verify it's actually a BVH file (not FBX or other)
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
        if props.use_selected_armature and context.active_object and context.active_object.type == 'ARMATURE':
            ref_armature = context.active_object
        else:
            for obj in context.scene.objects:
                if obj.type == 'ARMATURE':
                    ref_armature = obj
                    break

        if ref_armature is None:
            self.report({'ERROR'}, "В сцене нет арматуры! Импортируйте скелет UE5 первым.")
            return {'CANCELLED'}

        # Store original action to restore if needed
        orig_action = None
        if ref_armature.animation_data and ref_armature.animation_data.action:
            orig_action = ref_armature.animation_data.action

        # Step 1: Import BVH using Blender's built-in importer
        self.report({'INFO'}, "Импорт BVH файла...")
        try:
            bpy.ops.object.select_all(action='DESELECT')
            bpy.ops.import_anim.bvh(
                filepath=props.bvh_filepath,
                target='ARMATURE',
                rotate_mode='NATIVE',
                axis_forward='-Z',
                axis_up='Y',
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

        # Step 2: Retarget animation DIRECTLY to original armature
        # (No duplication - mesh stays bound to original armature)
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
            # Restore original action
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

        # Step 4: Make reference armature the active object
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
        fwd_corr = stats.get('forward_correction', '?')
        self.report({'INFO'},
                     f"Готово! Костей: {total}, Сопоставлено: {mapped}, "
                     f"Кадров: {stats.get('frame_count', 0)}, "
                     f"Root Motion: {root_motion} (bone: {root_name}), "
                     f"Коррекция направления: {fwd_corr}")

        return {'FINISHED'}


class BVH2FBX_OT_import_skeleton(bpy.types.Operator):
    bl_idname = "bvh2fbx.import_skeleton"
    bl_label = "Импортировать скелет UE5"
    bl_description = "Импортировать скелетную сетку UE5 (FBX) как референсный скелет"
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
    """Check GitHub for available plugin updates."""
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
            self.report({'WARNING'}, "Не удалось получить список релизов. Проверьте подключение к интернету.")
            return {'CANCELLED'}

        # Build enum items for version selector
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
                label = f"{tag} — {name} (source)"
                enum_items.append((tag, label, f"Release {tag} (source archive)"))

        if not enum_items:
            props.update_status = "Релизы не найдены"
            self.report({'INFO'}, "Релизы не найдены на GitHub.")
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
            self.report({'INFO'}, f"Новая версия доступна: {latest_tag} (текущая: {version_to_string(current)})")
        else:
            props.update_status = f"Установлена последняя версия ({version_to_string(current)})"
            self.report({'INFO'}, f"У вас последняя версия: {version_to_string(current)}")

        return {'FINISHED'}


class BVH2FBX_OT_install_update(bpy.types.Operator):
    """Install a selected version from GitHub releases."""
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

        self.report({'INFO'}, f"Загрузка версии {target_tag}...")

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
                self.report({'INFO'}, "Загрузка архива исходного кода...")
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
                        self.report({'ERROR'}, f"Файл {ADDON_FILENAME} не найден в архиве релиза")
                        shutil.rmtree(tmp_dir, ignore_errors=True)
                        return {'CANCELLED'}

                asset_url = None

            except Exception as e:
                self.report({'ERROR'}, f"Ошибка загрузки архива: {e}")
                return {'CANCELLED'}

        current_addon_path = get_addon_install_path()
        backup_path = current_addon_path + ".backup"
        new_addon_path = current_addon_path + ".new"

        try:
            if asset_url:
                tmp_dir = tempfile.mkdtemp(prefix="bvh2fbx_update_")
                tmp_file = os.path.join(tmp_dir, ADDON_FILENAME)
                self.report({'INFO'}, f"Скачивание {ADDON_FILENAME}...")
                download_file(asset_url, tmp_file)
                shutil.copy2(tmp_file, new_addon_path)
            else:
                extracted = os.path.join(tmp_dir, ADDON_FILENAME)
                shutil.copy2(extracted, new_addon_path)

            shutil.copy2(current_addon_path, backup_path)
            shutil.move(new_addon_path, current_addon_path)

            self.report({'INFO'}, f"Обновление до {target_tag} установлено! Перезапустите Blender для применения.")
            props.update_status = f"Обновлено до {target_tag}! Перезапустите Blender."

        except Exception as e:
            if os.path.exists(backup_path):
                try:
                    shutil.move(backup_path, current_addon_path)
                except Exception:
                    pass
            self.report({'ERROR'}, f"Ошибка установки обновления: {e}")
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
        description="Путь к выходному FBX файлу для UE5",
        subtype='FILE_PATH',
        default="",
    )

    scale_factor: bpy.props.FloatProperty(
        name="Масштаб Root Motion",
        description="Масштабный коэффициент для Root Motion (1.0 = без изменения, 0.01 = BVH cm в UE5 m)",
        default=1.0,
        min=0.0001,
        max=100.0,
    )

    use_selected_armature: bpy.props.BoolProperty(
        name="Использовать выбранную арматуру",
        description="Использовать текущую выбранную арматуру вместо поиска в сцене",
        default=True,
    )

    auto_export: bpy.props.BoolProperty(
        name="Автоэкспорт FBX",
        description="Автоматически экспортировать FBX после конвертации",
        default=True,
    )

    # --- Update system properties ---
    available_versions: bpy.props.CollectionProperty(type=BVH2FBX_VersionItem)

    selected_version_index: bpy.props.IntProperty(
        name="Выбранная версия",
        description="Индекс выбранной версии из списка доступных",
        default=-1,
    )

    update_status: bpy.props.StringProperty(
        name="Статус обновления",
        description="Текущий статус проверки обновлений",
        default=f"Текущая версия: {version_to_string(CURRENT_VERSION)}",
    )


# ============================================================================
# UI PANELS
# ============================================================================

class BVH2FBX_PT_main(bpy.types.Panel):
    bl_label = "BVH в FBX для UE5"
    bl_idname = "BVH2FBX_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "BVH2FBX"

    def draw(self, context):
        layout = self.layout
        props = context.scene.bvh2fbx_props

        # BVH input
        box = layout.box()
        box.label(text="Входной BVH файл", icon='FILE')
        box.prop(props, "bvh_filepath", text="")

        # Validate BVH file
        if props.bvh_filepath:
            if not os.path.isfile(props.bvh_filepath):
                box.label(text="Файл НЕ НАЙДЕН!", icon='ERROR')
            else:
                try:
                    with open(props.bvh_filepath, 'r', encoding='utf-8', errors='replace') as f:
                        first_line = f.readline().strip()
                    if first_line.upper() != 'HIERARCHY':
                        box.label(text=f"Это НЕ BVH файл! ({first_line[:30]})", icon='ERROR')
                    else:
                        box.label(text="BVH файл OK", icon='CHECKMARK')
                except:
                    box.label(text="Ошибка чтения файла", icon='ERROR')

        # Reference skeleton info
        armature = None
        if props.use_selected_armature and context.active_object and context.active_object.type == 'ARMATURE':
            armature = context.active_object
        else:
            for obj in context.scene.objects:
                if obj.type == 'ARMATURE':
                    armature = obj
                    break

        box = layout.box()
        box.label(text="Скелет UE5 (референс)", icon='ARMATURE_DATA')
        if armature:
            box.label(text=f"Арматура: {armature.name}", icon='BONE_DATA')
            root_name = find_root_bone(armature)
            if root_name:
                box.label(text=f"Root кость: {root_name}", icon='CON_ROTLIKE')
            else:
                box.label(text="Root кость: НЕ НАЙДЕНА!", icon='ERROR')
        else:
            box.label(text="Арматура НЕ выбрана!", icon='ERROR')

        box.prop(props, "use_selected_armature")

        # Output settings
        box = layout.box()
        box.label(text="Выходной FBX", icon='FILE_TICK')
        box.prop(props, "output_filepath", text="")
        box.prop(props, "auto_export")

        # Root motion scale
        box = layout.box()
        box.label(text="Root Motion", icon='CON_LOCLIKE')
        box.prop(props, "scale_factor")

        # Convert button
        layout.separator()
        can_convert = (
            props.bvh_filepath
            and os.path.isfile(props.bvh_filepath)
            and armature is not None
        )
        row = layout.row(align=True)
        row.enabled = can_convert
        row.scale_y = 1.5
        row.operator("bvh2fbx.convert", icon='PLAY')

        # Version info
        layout.separator()
        box = layout.box()
        box.label(text=f"Версия: {version_to_string(CURRENT_VERSION)}", icon='INFO')


class BVH2FBX_PT_updates(bpy.types.Panel):
    bl_label = "Обновления"
    bl_idname = "BVH2FBX_PT_updates"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "BVH2FBX"
    bl_parent_id = "BVH2FBX_PT_main"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        props = context.scene.bvh2fbx_props

        # Status
        layout.label(text=props.update_status, icon='INFO')

        # Check updates button
        layout.operator("bvh2fbx.check_updates", icon='URL')

        # Version list
        if len(props.available_versions) > 0:
            layout.template_list(
                "UI_UL_list", "bvh2fbx_versions",
                props, "available_versions",
                props, "selected_version_index",
                rows=3,
            )

            # Install button
            row = layout.row()
            row.operator("bvh2fbx.install_update", icon='FILE_REFRESH')


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
    BVH2FBX_PT_main,
    BVH2FBX_PT_updates,
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
