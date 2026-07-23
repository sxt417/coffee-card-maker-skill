# Flavor Semantic Color Field 2.0 视觉验收规范

## 最高原则

把所有风味组织成一个完整的感官色彩场，不把每个风味画成一个颜色光斑。主风味决定母色、最大面积和视觉重心，其余风味按权重衰减融入。

## 必须呈现

- 柔焦摄影、透明材料、液态颜料、光学折射和大型网格渐变的结合感。
- `soft organic continuous atmospheric abstract sensory editorial premium`。
- 1 个整体底色，2–4 个主要大色域，1–2 个低识别度抽象形态，0–2 个局部高光。
- 形态不完整、不闭合、超大、被裁切、与色场融合；不成为前景对象。
- 出现花香时，使用宽而模糊、断续且不闭合的花瓣边缘带建立抽象轮廓。轮廓必须可感知，不得退化为无结构色雾；也不得变成细线描边或完整花头。
- 当用户明确拒绝背景线痕或花瓣轮廓时，使用 `surfaces_only`：关闭边缘带，只保留模糊、超大、裁切的花瓣内部曲面。
- 画布 3:4，默认 1080 × 1440；所有文字白色、水平居中。
- 中文标题只在语义单元之间换行；处理法和品种词不得拆字，例如禁止 `日｜晒`、`水｜洗`、`原生｜种`。

## 数值边界

- blur radius: `canvas_width × 0.08–0.22`
- transition width: `>= canvas_width × 0.10`
- shape opacity: `0.18–0.72`
- highlight opacity: `0.08–0.35`
- grain opacity: `0.015–0.045`
- hard-edge ratio: `<= 0.03`
- dark-area ratio: `<= 0.18`
- color coherence: `>= 0.75`
- flavor fidelity: `>= 0.80`
- floral semantic contour score: `>= 0.75`
- floral contour peak alpha: `>= 0.16`
- floral contour coverage: `>= 0.025`
- floral contour lightness delta: `>= 0.07`
- floral contour effective contrast (`peak alpha × lightness delta`): `>= 0.05`

## Airy mesh 高明度空气网格

`airy_mesh` 不是把现有画面整体漂白。它以风味 `highlight` 构成高明度底层，以 5–7 个超大边缘锚点组织 `body` 大色域，并将 `core` 限制为局部轻锚点；画面保留 20%–35% 的风味高光呼吸区。锚点必须彼此覆盖、中心多在画布外、过渡宽且连续，不能形成独立圆形光斑。

- field blur: `canvas_width × 0.18–0.30`
- median luma: `0.68–0.86`
- high-key area (`luma > 0.78`): `0.04–0.76`
- breathing area: `0.16–0.42`
- breathing center strength: `>= 0.35`
- median saturation: `0.10–0.38`
- low-frequency gradient P95: `<= 0.035`
- grain opacity: `0.012–0.022`

## 禁止项

- 多个模糊圆点、独立径向光斑、等大色块或平均分布。
- 完整水果、完整花朵、叶片图标、食品插画、贴纸、卡通、线稿、闭合轮廓和清晰描边。
- 已识别花香却只呈现无结构的色雾，或轮廓在 `soft` 模式下完全消失。
- 小径向渐变点、硬几何块、尖锐色带、细波纹、条纹、彩虹渐变、高频噪声和超过 6 个碎片。
- 混色发灰、互补色变脏、大面积近黑、次要风味抢占主视觉。

## 自动重生条件

画面过碎、色块过多、出现圆形光斑或线条、颜色平均分配、主风味不突出、画面发灰、形态过于具象、边缘过硬或色彩缺少融合时，必须重新生成。
