---
name: drawio-flowchart
description: 根据流程图文字描述，自动生成标准工程风格的 .drawio 流程图文件。当用户要求创建 drawio 流程图、生成处理流程、把文字步骤转成流程图、输出 .drawio 文件时，必须使用此技能。支持开始/结束、处理节点、输入输出节点、分组框、正交箭头连接，且输入输出节点数量按描述动态生成。
---

# DrawIO 流程图技能

## 目标

把用户提供的文字流程描述转换成可直接打开的 `.drawio` XML 文件。

默认产出风格：
- 黑白单色
- 无填充
- 细线条
- 正交连线
- A4 竖版

只有在用户明确提出其他风格时，才偏离这些默认值。

## 何时使用

以下请求必须触发此技能：
- “根据这段步骤生成 drawio”
- “帮我画处理流程图”
- “把这段流程说明转成 .drawio 文件”
- “创建可编辑的 draw.io 流程图”

## 资源

- 标准参考文件：`references/example.drawio`

只有在需要核对节点坐标写法、分组框 parent 层级或连线 points 写法时，再读取参考文件，不要默认整份加载。

## 输出要求

- 产出完整 `.drawio` XML，而不是伪代码或片段
- 文件名优先使用用户指定名称
- 用户未指定输出路径时，在当前工作目录生成 `.drawio` 文件
- 如果当前环境有专用文件展示工具，再用该工具给用户返回文件；没有则直接告知生成路径

## 工作流程

### 1. 解析描述

先把用户描述整理成下面 5 类对象：
- 输入节点
- 主流程节点
- 分组框及其子节点
- 输出节点
- 开始和结束节点

如果用户描述不完整，但主流程顺序是明确的，可以自行补出最小可用布局，不必为轻微缺项停住。

### 2. 确定节点类型

节点映射规则：

| 节点类型 | 形状 | 说明 |
| --- | --- | --- |
| 开始/结束 | `ellipse;aspect=fixed` | 固定为圆角起止节点 |
| 处理步骤 | 普通矩形 | 算法、处理、判断后的结果处理节点 |
| 输入/输出 | `shape=parallelogram;perimeter=parallelogramPerimeter;fixedSize=1` | 数据、文件、产品、结果 |
| 分组框 | 普通大矩形 + `verticalAlign=top` | 作为容器，子节点放在内部 |

## 版式规范

### 视觉风格

- 页面：A4 竖版，`pageWidth=827`，`pageHeight=1169`
- 线宽：统一 `strokeWidth=2`
- 阴影：关闭，`shadow=0`
- 对齐：节点文字水平垂直居中
- 背景：白色，无纹理

### 主流程布局

- 主流程从上到下排布
- 主链节点之间默认垂直间距 `30`
- 开始节点固定在最上方
- 结束节点固定在最下方
- 主流程节点按画布中心线水平居中

可用默认公式：

```text
START.y = 170
PROC_1.y = START.y + 47 + 30
PROC_n.y = PROC_(n-1).y + PROC_(n-1).height + 30
END.y = PROC_last.y + PROC_last.height + 30
node.x = 587 - node.width / 2
```

### 输入节点布局

- 输入节点放在主目标处理节点左侧
- 多个输入节点垂直排列
- 输入节点整体垂直中心与目标处理节点中心对齐
- 输入节点数量不限

默认公式：

```text
merge_x = target_proc_left_x - 30
input_block_top_y = target_proc_center_y - total_input_height / 2
INPUT_i.x = merge_x - INPUT_i.width - 20
INPUT_i.y = input_block_top_y + i * (INPUT_i.height + 15)
```

### 输出节点布局

- 输出节点放在最后一个主处理节点右侧
- 多个输出节点垂直排列
- 输出节点整体垂直中心与最后处理节点中心对齐
- 输出节点数量不限

默认公式：

```text
turn_x = proc_last.x + proc_last.width + 30
OUTPUT_i.x = turn_x + 10
OUTPUT_i.y = output_block_top_y + i * (OUTPUT_i.height + 20)
```

### 分组框布局

- 分组框标题放顶部
- 子节点 `parent` 必须设为分组框 id
- 分组框内连线 `parent` 也必须设为分组框 id
- 分组框宽高由内部子节点反推，不要写死成明显过宽的尺寸

## 尺寸规则

节点尺寸按文本自适应，不要随意写死过宽值。

建议估算：
- 中文字符宽约 `14px`
- 英文、数字宽约 `8px`
- 节点宽 = 最长行估算宽度 + `50px` 内边距，最小 `160px`
- 节点高 = 行数 × `24px` + `30px` 内边距，最小 `50px`
- 平行四边形高度默认 `39px`

分组框建议估算：
- 宽 = 左边距 `30` + 子节点宽与间距总和 + 右边距 `30`
- 高 = 子节点最大高度 + 上边距 `35` + 下边距 `20`

## 连线规则

### 强制规则

所有连线都必须满足：
- 使用 `edgeStyle=orthogonalEdgeStyle`
- 使用 `orthogonalLoop=1`
- 显式写出 `exitX`、`exitY`、`entryX`、`entryY`
- 禁止斜线
- 禁止曲线

禁止：
- `edgeStyle=none`
- `curved=1`
- 省略入口或出口锚点

### 输入连接

- 单输入：输入节点右侧直接连到目标处理节点左侧
- 多输入：先用无箭头竖向对齐线汇合，再从汇合点水平连到目标处理节点

实现要求：
- 多输入时，对齐线使用 `endArrow=none`
- 汇合到主节点的最后一条线使用箭头

### 输出连接

- 单输出：最后处理节点右侧直接连到输出节点左侧
- 多输出：先从最后处理节点右侧引一条无箭头线到折点，再从折点分别连向各输出节点

实现要求：
- 主节点到折点：`endArrow=none`
- 折点到每个输出节点：使用箭头
- 需要拐弯时，在 `mxGeometry` 中显式写 `sourcePoint` 和 `points`

## XML 生成要求

生成完整结构，至少包含：

```xml
<mxfile host="app.diagrams.net" version="29.6.1">
  <diagram id="UNIQUE_ID" name="流程图">
    <mxGraphModel page="1" pageScale="1" pageWidth="827" pageHeight="1169" shadow="0">
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
```

生成顺序：
1. 先定义所有节点
2. 再定义所有连线
3. 最后检查 `parent`、`source`、`target`、`points` 是否完整

## 细节约束

- 节点标签换行使用 `&#xa;`
- XML 中 `<` 写成 `&lt;`，`>` 写成 `&gt;`
- 每个 `mxCell id` 都必须唯一
- id 使用语义化命名，例如 `START`、`PROC_1`、`INPUT_2`、`GROUP_QC`、`SUB_QC_1`
- 如果用户提供的是流程说明而不是文件名，可以用简短中文或拼音主题生成文件名

## 最终检查

交付前检查：
- 是否为完整 `.drawio` 文件
- 是否所有连线都是正交线
- 是否输入输出节点数量与描述一致
- 是否存在错误的父子层级
- 是否存在明显过宽、过高或重叠布局
- 是否保留黑白工程风格
