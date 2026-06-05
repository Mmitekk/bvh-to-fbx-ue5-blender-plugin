bl_info = {
    "name": "BVH to FBX for UE5",
    "author": "BVH2FBX Converter",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > BVH2FBX",
    "description": "Конвертация BVH motion capture в FBX анимацию для Unreal Engine 5 с сохранением Root Motion",
    "category": "Animation",
}

import bpy
import os
import math
from collections import OrderedDict

# ============================================================================
# BVH PARSER (standalone, no external deps)
# ============================================================================

class BVHBone:
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
        frame = self.frames[frame_idx]
        pos = [0.0, 0.0, 0.0]
        rot = [0.0, 0.0, 0.0]
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
    x, y, z = math.radians(x), math.radians(y), math.radians(z)
    cx, sx = math.cos(x), math.sin(x)
    cy, sy = math.cos(y), math.sin(y)
    cz, sz = math.cos(z), math.sin(z)
    if order == 'ZYX':
        return [
            [cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx],
            [sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx],
            [-sy, cy * sx, cy * cx]
        ]
    else:
        return [
            [cy * cz, -cy * sz, sy],
            [cx * sz + sx * sy * cz, cx * cz - sx * sy * sz, -sx * cy],
            [sx * sz - cx * sy * cz, sx * cz + cx * sy * sz, cx * cy]
        ]


def matrix_to_euler(m, order='ZYX'):
    if order == 'ZYX':
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
    else:
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
    r = [[0] * 3 for _ in range(3)]
    for i in range(3):
        for j in range(3):
            for k in range(3):
                r[i][j] += a[i][k] * b[k][j]
    return r


def mat_transpose(m):
    return [[m[j][i] for j in range(3)] for i in range(3)]


def mat_vec_mul(m, v):
    return [m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2],
            m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
            m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2]]


def ensure_euler_continuity(rots):
    if len(rots) < 2:
        return rots
    result = [list(rots[0])]
    for i in range(1, len(rots)):
        prev = result[-1]
        curr = list(rots[i])
        for ax in range(3):
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
    transforms = {}

    def compute(bone, parent_pos, parent_rot):
        pos, rot_zyx = bvh.get_bone_data(bone, frame_idx)
        local_rot = euler_to_matrix(rot_zyx[2], rot_zyx[1], rot_zyx[0], 'ZYX')
        world_rot = mat_mul(parent_rot, local_rot) if parent_rot else local_rot

        if any('position' in ch.lower() for ch in bone.channels):
            world_pos = list(pos)
        else:
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
# BONE MAPPING
# ============================================================================

BVH_TO_UE5 = {
    'Hips': 'pelvis',
    'Spine1': 'spine_01',
    'Spine2': 'spine_02',
    'Spine3': 'spine_03',
    'Chest': 'spine_04',
    'Neck1': 'neck_01',
    'Neck': 'neck_01',
    'Neck2': 'neck_02',
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
    'LeftLeg': 'thigh_l',
    'LeftUpLeg': 'thigh_l',
    'LeftShin': 'calf_l',
    'LeftFoot': 'foot_l',
    'LeftToeBase': 'ball_l',
    'RightLeg': 'thigh_r',
    'RightUpLeg': 'thigh_r',
    'RightShin': 'calf_r',
    'RightFoot': 'foot_r',
    'RightToeBase': 'ball_r',
}


# ============================================================================
# BLENDER RETARGETING
# ============================================================================

def retarget_in_blender(bvh, ref_armature, scale=1.0):
    """Retarget BVH animation onto the reference armature in Blender.

    Returns:
        Dict mapping bone_name -> {'translation': [...], 'rotation': [...], 'scaling': [...]}
    """
    nf = bvh.frame_count
    ba = {}

    # Build reverse map
    q2b = {}
    for bn, qn in BVH_TO_UE5.items():
        q2b.setdefault(qn, []).append(bn)

    # Precompute BVH world transforms for all frames
    all_frames = []
    for fi in range(nf):
        all_frames.append(compute_bvh_world(bvh, fi))

    # Get reference armature bone rest data
    ref_bones = {}
    for pb in ref_armature.pose.bones:
        ref_bones[pb.name] = pb

    # Compute reference armature rest rotations
    qr_world = {}

    def _compute_ref_world(bname, parent_wr=None):
        if parent_wr is None:
            parent_wr = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
        pb = ref_bones.get(bname)
        if pb is None:
            return
        lr = [math.degrees(a) for a in pb.rotation_euler]
        lm = euler_to_matrix(lr[0], lr[1], lr[2], 'ZYX')
        wr = mat_mul(parent_wr, lm)
        qr_world[bname] = wr
        for child in pb.children:
            _compute_ref_world(child.name, wr)

    root_pb = None
    for pb in ref_armature.pose.bones:
        if pb.parent is None:
            root_pb = pb
            break
    if root_pb:
        _compute_ref_world(root_pb.name)

    # Find BVH Hips bone for root motion
    bvh_hips = None
    for bn in ('Hips', 'hip', 'Pelvis', 'pelvis', 'mixamorig:Hips'):
        if bn in bvh.bone_map:
            bvh_hips = bvh.bone_map[bn]
            break
    if bvh_hips is None and bvh.root_bone.children:
        bvh_hips = bvh.root_bone.children[0]

    hips_rest_pos = None
    if bvh_hips:
        hips_rest_pos = all_frames[0][bvh_hips.name][0]

    # BVH rest transforms
    rest = all_frames[0] if all_frames else {}

    # Process each reference bone
    for pb in ref_armature.pose.bones:
        bname = pb.name
        trans_list = []
        rots_list = []
        scals_list = []

        bvh_names = q2b.get(bname, [])
        bvh_bone = bvh.bone_map.get(bvh_names[0]) if bvh_names else None

        for fi in range(nf):
            if bvh_hips and bname == root_pb.name if root_pb else False:
                # Root motion
                if bvh_hips and bvh_hips.name in all_frames[fi]:
                    hp = all_frames[fi][bvh_hips.name][0]
                    if hips_rest_pos:
                        dx = (hp[2] - hips_rest_pos[2]) * scale
                        dy = (hp[0] - hips_rest_pos[0]) * scale
                        dz = (hp[1] - hips_rest_pos[1]) * scale
                        trans_list.append([dx, dy, dz])
                    else:
                        trans_list.append([0.0, 0.0, 0.0])
                else:
                    trans_list.append([0.0, 0.0, 0.0])
                rots_list.append([0.0, 0.0, 0.0])
                scals_list.append([1.0, 1.0, 1.0])

            elif bvh_bone and bvh_bone.name in all_frames[fi]:
                wt = all_frames[fi]
                wp, wr_bvh = wt[bvh_bone.name]

                if bvh_bone.parent and bvh_bone.parent.name in wt:
                    pp, pr = wt[bvh_bone.parent.name]
                else:
                    pr = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]

                pri = mat_transpose(pr)
                lr = mat_mul(pri, wr_bvh)

                rwp, rwr = rest[bvh_bone.name]
                if bvh_bone.parent and bvh_bone.parent.name in rest:
                    rpp, rpr = rest[bvh_bone.parent.name]
                else:
                    rpr = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
                rpri = mat_transpose(rpr)
                rlr = mat_mul(rpri, rwr)

                rlri = mat_transpose(rlr)
                rdiff = mat_mul(rlri, lr)

                qrl = euler_to_matrix(
                    math.degrees(pb.rotation_euler[0]),
                    math.degrees(pb.rotation_euler[1]),
                    math.degrees(pb.rotation_euler[2]),
                    'ZYX'
                )
                qnew = mat_mul(qrl, rdiff)
                euler = matrix_to_euler(qnew, 'ZYX')

                rots_list.append(euler)
                lcl_t = [pb.location[0], pb.location[1], pb.location[2]]
                trans_list.append(lcl_t)
                scals_list.append([1.0, 1.0, 1.0])
            else:
                lr = [math.degrees(a) for a in pb.rotation_euler]
                rots_list.append(lr)
                lcl_t = [pb.location[0], pb.location[1], pb.location[2]]
                trans_list.append(lcl_t)
                scals_list.append([1.0, 1.0, 1.0])

        ba[bname] = {
            'translation': trans_list,
            'rotation': ensure_euler_continuity(rots_list),
            'scaling': scals_list,
        }

    return ba


def apply_animation_to_blender(ref_armature, bone_anim, bvh_fps=30.0):
    """Apply retargeted animation data to the Blender armature."""
    nf = len(next(iter(bone_anim.values()))['rotation'])
    scene = bpy.context.scene

    # Set frame range
    scene.frame_start = 0
    scene.frame_end = nf - 1
    scene.render.fps = int(bvh_fps)

    # Create action
    action_name = ref_armature.name + "_Action"
    action = bpy.data.actions.new(action_name)
    if ref_armature.animation_data is None:
        ref_armature.animation_data_create()
    ref_armature.animation_data.action = action

    # Apply keyframes
    for pb in ref_armature.pose.bones:
        ba = bone_anim.get(pb.name)
        if ba is None:
            continue

        bone_path = f'pose.bones["{pb.name}"]'

        for fi in range(nf):
            # Translation
            t = ba['translation'][fi]
            pb.location = (t[0], t[1], t[2])
            pb.keyframe_insert(data_path='location', frame=fi, group=pb.name)

            # Rotation
            r = ba['rotation'][fi]
            pb.rotation_euler = (math.radians(r[0]), math.radians(r[1]), math.radians(r[2]))
            pb.keyframe_insert(data_path='rotation_euler', frame=fi, group=pb.name)

            # Scale
            s = ba['scaling'][fi]
            pb.scale = (s[0], s[1], s[2])
            pb.keyframe_insert(data_path='scale', frame=fi, group=pb.name)

    return action


# ============================================================================
# BLENDER OPERATOR
# ============================================================================

class BVH2FBX_OT_convert(bpy.types.Operator):
    bl_idname = "bvh2fbx.convert"
    bl_label = "Конвертировать BVH → FBX"
    bl_description = "Импортировать BVH, заретаргетить на текущий скелет и экспортировать FBX для UE5"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        props = context.scene.bvh2fbx_props
        return props.bvh_filepath and props.output_filepath

    def execute(self, context):
        props = context.scene.bvh2fbx_props

        # Validate BVH file
        if not os.path.isfile(props.bvh_filepath):
            self.report({'ERROR'}, f"BVH файл не найден: {props.bvh_filepath}")
            return {'CANCELLED'}

        # Parse BVH
        self.report({'INFO'}, "Парсинг BVH файла...")
        try:
            bvh = BVHFile(props.bvh_filepath)
        except Exception as e:
            self.report({'ERROR'}, f"Ошибка парсинга BVH: {e}")
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

        self.report({'INFO'}, f"Ретаргетинг BVH ({len(bvh.bones)} костей, {bvh.frame_count} кадров) на {ref_armature.name}...")

        # Retarget
        try:
            bone_anim = retarget_in_blender(bvh, ref_armature, scale=props.scale_factor)
        except Exception as e:
            self.report({'ERROR'}, f"Ошибка ретаргетинга: {e}")
            return {'CANCELLED'}

        # Apply animation to Blender armature
        self.report({'INFO'}, "Применение анимации в Blender...")
        apply_animation_to_blender(ref_armature, bone_anim, bvh_fps=bvh.fps)

        # Export FBX if output path specified
        if props.output_filepath and props.auto_export:
            self.report({'INFO'}, f"Экспорт FBX: {props.output_filepath}...")
            try:
                bpy.ops.export_scene.fbx(
                    filepath=props.output_filepath,
                    use_selection=False,
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

        mapped = sum(1 for bn in BVH_TO_UE5 if bn in bvh.bone_map)
        self.report({'INFO'},
                     f"Готово! BVH: {len(bvh.bones)} костей, {bvh.frame_count} кадров @ {bvh.fps:.0f} FPS. "
                     f"Сопоставлено костей: {mapped}")

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
# PROPERTIES
# ============================================================================

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
        name="Масштаб",
        description="Масштабный коэффициент для Root Motion (0.01 для UE5 cm→m)",
        default=0.01,
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


# ============================================================================
# UI PANEL
# ============================================================================

class BVH2FBX_PT_main(bpy.types.Panel):
    bl_label = "BVH → FBX для UE5"
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

        # Reference skeleton info
        armature = None
        if props.use_selected_armature and context.active_object and context.active_object.type == 'ARMATURE':
            armature = context.active_object
        else:
            for obj in context.scene.objects:
                if obj.type == 'ARMATURE':
                    armature = obj
                    break

        if armature:
            box.label(text=f"Скелет: {armature.name}", icon='ARMATURE_DATA')
            bone_count = len(armature.data.bones)
            box.label(text=f"  Костей: {bone_count}")
        else:
            box.label(text="Скелет НЕ НАЙДЕН!", icon='ERROR')
            box.label(text="  Импортируйте FBX скелет UE5")

        # Output
        box = layout.box()
        box.label(text="Выходной FBX", icon='EXPORT')
        box.prop(props, "output_filepath", text="")

        # Settings
        box = layout.box()
        box.label(text="Настройки", icon='SETTINGS')
        box.prop(props, "scale_factor")
        box.prop(props, "use_selected_armature")
        box.prop(props, "auto_export")

        # Convert button
        layout.separator()
        layout.scale_y = 1.5
        layout.operator("bvh2fbx.convert", icon='PLAY')

        # Info
        if props.bvh_filepath and os.path.isfile(props.bvh_filepath):
            try:
                bvh = BVHFile(props.bvh_filepath)
                box = layout.box()
                box.label(text="Информация о BVH:", icon='INFO')
                box.label(text=f"  Костей: {len(bvh.bones)}")
                box.label(text=f"  Кадров: {bvh.frame_count}")
                box.label(text=f"  FPS: {bvh.fps:.1f}")
                box.label(text=f"  Длительность: {bvh.frame_count / bvh.fps:.2f}с")
                root = bvh.root_bone.name
                has_pos = any('position' in ch.lower() for ch in bvh.root_bone.channels)
                box.label(text=f"  Root: {root} (root motion: {'Да' if has_pos else 'Нет'})")
            except Exception:
                pass


# ============================================================================
# REGISTRATION
# ============================================================================

classes = (
    BVH2FBX_Properties,
    BVH2FBX_OT_convert,
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
