# BVH to FBX for UE5 — Blender Plugin

[![GitHub release](https://img.shields.io/github/v/release/Mmitekk/bvh-to-fbx-ue5-blender-plugin?include_prereleases)](https://github.com/Mmitekk/bvh-to-fbx-ue5-blender-plugin/releases)
[![Blender](https://img.shields.io/badge/Blender-4.0%2B-orange)](https://www.blender.org/)
[![Unreal Engine](https://img.shields.io/badge/UE-5.0%2B-blue)](https://www.unrealengine.com/)

A Blender addon that converts BVH motion capture files to FBX animation for **Unreal Engine 5**, with **Root Motion preservation** and automatic bone retargeting onto the UE5 Quinn skeleton.

---

## 🇬🇧 English

### Features

- **BVH → FBX conversion** with automatic skeleton retargeting onto the UE5 Quinn (mannequin) bone hierarchy
- **Root Motion preservation** — the root bone translation is extracted from BVH Hips displacement and baked into the UE5 `root` bone, so animations work correctly with UE5's Root Motion system
- **Multiple BVH naming conventions** supported: standard BVH (SOMA/Kimodo), Mixamo (`mixamorig:` prefix)
- **Comprehensive bone mapping** — over 70 bone name mappings covering spine, head, arms, fingers, legs, and toes
- **World-space rotation delta retargeting** — computes rotation deltas from BVH rest pose and applies them to UE5 rest pose for accurate pose transfer
- **Scale factor control** for Root Motion translation (e.g., BVH centimeters → UE5 meters with scale 0.01)
- **Auto-export** FBX after retargeting, with UE5-compatible export settings
- **In-Blender auto-update system** — check for new versions on GitHub, select a version, and install it directly from the addon panel

### Installation

**Option A — Install from ZIP (recommended):**

1. Download `bvh_to_fbx_ue5_addon.zip` from [Releases](https://github.com/Mmitekk/bvh-to-fbx-ue5-blender-plugin/releases) (the file labeled "Blender Addon ZIP")
2. Open Blender → **Edit** → **Preferences** → **Add-ons** → **Install...**
3. Select the downloaded `.zip` file
4. Enable the addon **"BVH to FBX for UE5"**
5. The panel appears in the 3D Viewport sidebar under the **BVH2FBX** tab (press `N` to open the sidebar)

> ⚠️ **Do NOT download the repository ZIP ("Source code")** — it won't install in Blender because the addon file is nested inside a subfolder. Use the **Blender Addon ZIP** asset from the release instead.

**Option B — Install from .py file:**

1. Download `bvh_to_fbx_ue5_addon.py` from [Releases](https://github.com/Mmitekk/bvh-to-fbx-ue5-blender-plugin/releases)
2. Open Blender → **Edit** → **Preferences** → **Add-ons** → **Install...**
3. Select the downloaded `.py` file
4. Enable the addon **"BVH to FBX for UE5"**

### Usage

1. **Import the UE5 skeleton** — Import your `SKM_Quinn_Simple.FBX` (or any UE5-compatible skeleton) into Blender using **File → Import → FBX**
2. **Select the skeleton armature** in the viewport
3. **Open the BVH2FBX panel** (press `N` → **BVH2FBX** tab)
4. **Set the BVH file path** — browse to your `.bvh` motion capture file
5. **Set the output FBX path** — where the converted animation will be saved
6. **Adjust settings**:
   - **Scale Factor**: `1.0` = no scaling, `0.01` = convert BVH centimeters to UE5 meters
   - **Use Selected Armature**: enabled by default, uses the currently selected armature
   - **Auto Export**: automatically exports FBX after retargeting
7. **Click "Конвертировать BVH → FBX"** (the Convert button)
8. **Import the output FBX into UE5** — in Unreal Engine, import the FBX with **Import Animation** checked and **Use Default Skeleton** set to your Quinn skeleton

### Root Motion in UE5

After importing the FBX into UE5:
1. Open the imported Animation Sequence
2. In the Asset Details, find **Root Motion** section
3. Enable **Enable Root Motion Translation**
4. The root bone will carry the translation from the original BVH motion capture

### Auto-Update System

The addon includes a built-in update system that checks GitHub for new releases:

1. Open the **"Обновление плагина"** (Plugin Update) sub-panel in the BVH2FBX tab
2. Click **"Проверить обновления"** (Check for Updates) to fetch available versions from GitHub
3. Select a version from the list
4. Click the install button to download and replace the addon file
5. **Restart Blender** to apply the update

### Bone Mapping Reference

The addon maps BVH bone names to UE5 Quinn bone names using the following conventions:

| BVH Bone | UE5 Bone |
|----------|----------|
| Hips | pelvis |
| Spine / Spine1 | spine_01 |
| Spine2 | spine_02 |
| Spine3 / Chest | spine_03 / spine_04 |
| Neck | neck_01 |
| Head | head |
| LeftShoulder | clavicle_l |
| LeftArm | upperarm_l |
| LeftForeArm | lowerarm_l |
| LeftHand | hand_l |
| LeftUpLeg / LeftLeg | thigh_l |
| LeftShin / LeftLeg | calf_l |
| LeftFoot | foot_l |
| LeftToeBase | ball_l |
| (and mirror for right side) | |

Mixamo naming is also supported (e.g., `mixamorig:Hips` → `pelvis`).

### Requirements

- Blender 4.0 or later (compatible with Blender 5.x)
- Internet connection (for the auto-update feature only)

### Troubleshooting

- **"BVH armature has no animation"** — the BVH file may be corrupt or have no motion data
- **"Это не BVH файл!"** — make sure you selected a `.bvh` file, not an `.fbx` file
- **Zero-length bone warnings** — these are normal for BVH end-effector bones (finger tips, toe ends, head end) and can be safely ignored
- **Incorrect bone rotations** — try adjusting the scale factor or ensure the reference skeleton is properly oriented

---

## 🇷🇺 Русский

### Возможности

- **Конвертация BVH → FBX** с автоматическим ретаргетингом скелета на иерархию костей UE5 Quinn (манекен)
- **Сохранение Root Motion** — перемещение корневой кости извлекается из смещения BVH Hips и запекается в кость `root` UE5, поэтому анимации корректно работают с системой Root Motion в UE5
- **Поддержка различных соглашений об именах BVH**: стандартный BVH (SOMA/Kimodo), Mixamo (префикс `mixamorig:`)
- **Расширенное отображение костей** — более 70 соответствий имён костей, покрывающих позвоночник, голову, руки, пальцы, ноги и стопы
- **Ретаргетинг через мировые дельты вращений** — вычисляются дельты вращений от позы покоя BVH и применяются к позе покоя UE5 для точной передачи поз
- **Управление масштабом** Root Motion (например, BVH сантиметры → UE5 метры с масштабом 0.01)
- **Автоэкспорт** FBX после ретаргетинга с настройками, совместимыми с UE5
- **Система автообновления внутри Blender** — проверка новых версий на GitHub, выбор версии и установка прямо из панели аддона

### Установка

**Способ A — Установка из ZIP (рекомендуется):**

1. Скачайте `bvh_to_fbx_ue5_addon.zip` из [Релизов](https://github.com/Mmitekk/bvh-to-fbx-ue5-blender-plugin/releases) (файл с меткой "Blender Addon ZIP")
2. Откройте Blender → **Правка** → **Настройки** → **Аддоны** → **Установить...**
3. Выберите скачанный файл `.zip`
4. Включите аддон **"BVH to FBX for UE5"**
5. Панель появится в боковой панели 3D Viewport во вкладке **BVH2FBX** (нажмите `N` для открытия боковой панели)

> ⚠️ **НЕ скачивайте ZIP репозитория ("Source code")** — он не установится в Blender, потому что файл аддона находится внутри подпапки. Используйте **Blender Addon ZIP** из релиза.

**Способ B — Установка из .py файла:**

1. Скачайте `bvh_to_fbx_ue5_addon.py` из [Релизов](https://github.com/Mmitekk/bvh-to-fbx-ue5-blender-plugin/releases)
2. Откройте Blender → **Правка** → **Настройки** → **Аддоны** → **Установить...**
3. Выберите скачанный файл `.py`
4. Включите аддон **"BVH to FBX for UE5"**

### Использование

1. **Импортируйте скелет UE5** — импортируйте файл `SKM_Quinn_Simple.FBX` (или любой совместимый с UE5 скелет) в Blender через **Файл → Импорт → FBX**
2. **Выберите арматуру скелета** в окне просмотра
3. **Откройте панель BVH2FBX** (нажмите `N` → вкладка **BVH2FBX**)
4. **Укажите путь к BVH файлу** — выберите файл `.bvh` захвата движения
5. **Укажите путь к выходному FBX** — куда будет сохранена сконвертированная анимация
6. **Настройте параметры**:
   - **Масштаб Root Motion**: `1.0` = без масштабирования, `0.01` = конвертация сантиметров BVH в метры UE5
   - **Использовать выбранную арматуру**: включено по умолчанию, использует текущую выбранную арматуру
   - **Автоэкспорт FBX**: автоматически экспортирует FBX после ретаргетинга
7. **Нажмите кнопку "Конвертировать BVH → FBX"**
8. **Импортируйте выходной FBX в UE5** — в Unreal Engine импортируйте FBX с включённой опцией **Import Animation** и выберите скелет Quinn

### Root Motion в UE5

После импорта FBX в UE5:
1. Откройте импортированную Animation Sequence
2. В Asset Details найдите раздел **Root Motion**
3. Включите **Enable Root Motion Translation**
4. Корневая кость будет содержать перемещение из исходного захвата движения BVH

### Система автообновления

Аддон включает встроенную систему обновлений, проверяющую GitHub на наличие новых релизов:

1. Откройте подпанель **"Обновление плагина"** во вкладке BVH2FBX
2. Нажмите **"Проверить обновления"** для загрузки списка доступных версий с GitHub
3. Выберите версию из списка
4. Нажмите кнопку установки для скачивания и замены файла аддона
5. **Перезапустите Blender** для применения обновления

### Таблица соответствия костей

Аддон сопоставляет имена костей BVH с именами костей UE5 Quinn:

| Кость BVH | Кость UE5 |
|-----------|-----------|
| Hips | pelvis |
| Spine / Spine1 | spine_01 |
| Spine2 | spine_02 |
| Spine3 / Chest | spine_03 / spine_04 |
| Neck | neck_01 |
| Head | head |
| LeftShoulder | clavicle_l |
| LeftArm | upperarm_l |
| LeftForeArm | lowerarm_l |
| LeftHand | hand_l |
| LeftUpLeg / LeftLeg | thigh_l |
| LeftShin / LeftLeg | calf_l |
| LeftFoot | foot_l |
| LeftToeBase | ball_l |
| (и зеркально для правой стороны) | |

Именование Mixamo также поддерживается (например, `mixamorig:Hips` → `pelvis`).

### Системные требования

- Blender 4.0 или новее (совместим с Blender 5.x)
- Интернет-соединение (только для функции автообновления)

### Решение проблем

- **"BVH armature has no animation"** — BVH файл может быть повреждён или не содержать данных движения
- **"Это не BVH файл!"** — убедитесь, что выбран файл `.bvh`, а не `.fbx`
- **Предупреждения о нулевой длине костей** — это нормально для костей-концевиков BVH (кончики пальцев, носки, конец головы), их можно игнорировать
- **Неправильные вращения костей** — попробуйте изменить масштабный коэффициент или убедитесь, что референсный скелет правильно ориентирован

---

## License

MIT License — see [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request on [GitHub](https://github.com/Mmitekk/bvh-to-fbx-ue5-blender-plugin).
