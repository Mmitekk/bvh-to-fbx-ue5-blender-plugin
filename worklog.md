# Worklog — BVH to FBX Converter for UE5

---
Task ID: 1
Agent: Main Agent
Task: Create BVH to FBX converter plugin for Unreal Engine 5 with root motion preservation

Work Log:
- Analyzed uploaded BVH file (78 bones, 180 frames, 30 FPS, Root+Hips hierarchy)
- Analyzed MD handoff document from previous agent (detailed project history)
- Discovered bpy (Blender Python API) is NOT available in this environment
- Discovered fbxsdk is NOT available for pip install
- Studied the FBX 7300 binary format in detail by parsing reference FBX files
- Analyzed SKM_Quinn_Simple.FBX (skeleton, 89 bones) and TP_Echo_Walk_Fwd.FBX (animation reference)
- Key discovery: Model names use "\x00\x01" separator (e.g., "root\x00\x01Model")
- Key discovery: BVH Root bone has NO position animation — Hips carries the motion data
- Key discovery: Reference FBX has unique NodeAttribute per bone
- Key discovery: Animation structure is T/R/S CurveNodes with X/Y/Z Curves per bone

Stage Summary:
- Built BVH parser that handles the specific BVH format
- Built FBX binary writer from scratch (v4 first, then v5)
- v4 used hardcoded bone transforms (incorrect)
- v5 reads reference skeleton FBX for exact bone data
- Root motion extraction from Hips world position displacement
- Coordinate conversion: BVH (Y-up) → UE5 (Z-up)
- Retargeting: rotation difference from BVH rest pose applied to Quinn rest pose
- Output: Quinn_ElderlyWalk_Fwd.fbx (1,451,462 bytes)
- All 7 validation checks passed
- Script: /home/z/my-project/python/bvh_to_fbx_ue5.py

---
Task ID: 2
Agent: Main Agent (continuation)
Task: Fix UE5 FBX import compatibility and create Blender Add-on

Work Log:
- Ran v5 converter and verified all 7 checks pass
- Deep-compared output FBX with reference TP_Echo_Walk_Fwd.FBX (which UE5 imports correctly)
- Found 2 CRITICAL issues causing UE5 import failure:
  1. AnimationCurve tangent format: KeyVer=4008 (per-key) vs UE5 expects KeyVer=4009 (per-curve)
  2. Root bone NodeAttribute type: 'Null' vs UE5 expects 'Root' with TypeFlags=Null,Skeleton,Root
- Fixed AnimationCurve format: KeyVer=4009, KeyAttrFlags=0x2108, KeyAttrDataFloat=4 floats, KeyAttrRefCount=1 int
- Fixed Root NodeAttribute: type='Root', TypeFlags=['Null','Skeleton','Root']
- Verified all format fields now match reference FBX exactly
- Created Blender Add-on plugin: bvh_to_fbx_ue5_addon.py
- Add-on features: BVH import, retargeting to selected armature, FBX export for UE5, UI panel in sidebar
- Output file: ElderlyWalk_Quinn_v6.fbx (1,409,832 bytes, 1376.8 KB)

Stage Summary:
- Fixed the 2 critical FBX format issues that prevented UE5 import
- AnimationCurve format now matches UE5's expected KeyVer=4009 per-curve tangent format
- Root NodeAttribute now matches UE5's expected Root type with proper TypeFlags
- Created standalone Python converter script (bvh_to_fbx_ue5.py) with all fixes
- Created Blender Add-on (bvh_to_fbx_ue5_addon.py) for GUI-based workflow
- Files: /home/z/my-project/python/bvh_to_fbx_ue5.py, /home/z/my-project/download/bvh_to_fbx_ue5_addon.py
