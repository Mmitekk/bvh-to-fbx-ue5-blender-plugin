---
Task ID: 3
Agent: Main Agent
Task: Complete rewrite of BVH→FBX Blender addon (v2) for UE5 with root motion

Work Log:
- Analyzed previous addon issues: custom BVH parser caused "Expected HIERARCHY got Kaydara" error
- Analyzed BVH file structure: Root+Hips hierarchy, 78 bones, 180 frames, 30 FPS
- Analyzed Quinn skeleton: 89 bones with existing 'root' bone (type=Root) at top
- Rewrote addon from scratch with Blender's built-in BVH importer
- World-space rotation delta retargeting with hierarchical processing
- Root motion via existing 'root' bone (detects automatically)
- Correct FBX export settings for UE5

Stage Summary:
- New addon: /home/z/my-project/download/bvh_to_fbx_ue5_addon.py (866 lines)
- Key fix: No more custom BVH parser
- Key fix: Validates BVH file type before processing
- Key fix: Uses existing Quinn 'root' bone for root motion
