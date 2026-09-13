# StyleMate visual specification

The interface follows two generated concept screens saved under `design/`.

## Design system

- Background: true white `#FFFFFF`; no gradients.
- Ink: `#111111`; muted copy `#737782`; rules `#DFE2E8`.
- Accent: electric cobalt `#1248F5`; pale selected surface `#EEF2FF`.
- Typography: modern system grotesk for UI chrome; Georgia/Noto Serif SC accent for editorial titles.
- Container model: open editorial canvas with dividers and rails, not nested cards.
- Radius: 7–12px, reserved for controls and media.
- Motion: short hover lift only; disabled under reduced-motion preference.

## Locked first-viewport copy

- StyleMate
- 从一件单品，开始三种可能
- 上传你衣橱里的一件单品，AI 会识别它，并为场景、天气与偏好生成完整搭配。
- 拖入照片，或点击选择
- 今天准备去哪？
- 更偏爱哪种风格？
- 生成我的穿搭
- 未设置 API Key？可先体验 Demo 模式

## Core states

1. Upload and preference selection.
2. Loading: garment analysis → outfit planning → optional image generation.
3. Results: source garment rail plus three comparable looks with explanations and feedback.
