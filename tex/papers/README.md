# 小天体探测、表面重建与观测规划文献库

整理日期：2026-10-01。实际目录为 `tex/papers/`。

**当前包含 40 份 PDF：39 篇独立论文、1 份非论文参考表；另保留 5 篇全文待补文献的书目条目。** 39 篇本地论文均在下文给出研究问题、创新点与贡献、方法、验证结果与适用边界，并按七个主题分类。记录依据本地全文的摘要、方法、实验或任务设计、讨论与结论；关键表格、架构图和公式已对照页面核查。“创新点与贡献”按原文的具体成果归纳，任务说明和综述的贡献与新算法区分。全文待补条目不列为已完成全文阅读。

## 文件与书目规范

- 文件统一使用 `正式发表年 - 完整英文题名.pdf`；只有预印本的文献采用本地预印本年份。中文论文采用期刊给出的英文题名，并在逐篇记录中补充中文题名。
- 文件名中的冒号、路径斜杠等 Windows 禁用字符用 ` - ` 或 `-` 代替；保留正文、图表和已有仓库封面，PDF 内容不重新排版。
- 同一论文的不同版本以题名、作者、发表信息、摘要及方法/结果判定，优先保留正式期刊版；独立会议论文与后续扩展论文分别保留。此次未发现字节完全相同的 PDF，合并的是内容对应的作者稿与期刊版。
- 书目按“作者，年份，期刊/会议，卷期与页码或文章编号”记录，并附 DOI/正式来源。已有 BibTeX 键与 `../references.bib` 对齐；索引中的 `—` 表示当前该文件未对应已有引用键。
- 页码均从本地 PDF 第 1 页起计，包含仓库封面；因此可能与正文印刷页码不同。SPG 为立体摄影测量，SPC 为立体光度测量，SfM 为运动恢复结构，NBV 为下一最佳视角，DTM 为数字地形模型，GSD 为地面采样间距。

### 本次改名与版本归并

| 原文件/版本 | 处理后的文件 | 依据 |
| --- | --- | --- |
| `Autonomous_Imaging_and_Mapping_of_Small_Bodies_Using_Deep_Reinforcement_Learning.pdf` | [Autonomous Imaging and Mapping of Small Bodies Using Deep Reinforcement Learning](<2019 - Autonomous Imaging and Mapping of Small Bodies Using Deep Reinforcement Learning.pdf>) | Chan 与 Agha-Mohammadi，IEEE Aerospace 2019，补齐年份并统一分隔符。 |
| `piccinin-lavagna-2020-deep-reinforcement-learning-approach-for-small-bodies-shape-reconstruction-enhancement (1).pdf` | [Deep Reinforcement Learning approach for Small Bodies Shape Reconstruction Enhancement](<2020 - Deep Reinforcement Learning approach for Small Bodies Shape Reconstruction Enhancement.pdf>) | AIAA SciTech 2020，paper 2020-1909；去掉下载后缀。 |
| `2024 - Integrating One-Shot View Planning with a Single Next-Best View via Long-Tail Multiview Sampling.pdf` | [Integrating One-Shot View Planning with a Single Next-Best View via Long-Tail Multiview Sampling](<2025 - Integrating One-Shot View Planning with a Single Next-Best View via Long-Tail Multiview Sampling.pdf>) | 2024 年接受/上线，正式 T-RO 第 41 卷为 2025 年，按正式卷年命名。 |
| `意大利 2022 ICARUS 1-s2.0-S1270963821007343-main.pdf` 与同题标准文件名作者稿 | [Deep Reinforcement Learning-based policy for autonomous imaging planning of small celestial bodies mapping](<2022 - Deep Reinforcement Learning-based policy for autonomous imaging planning of small celestial bodies mapping.pdf>) | 两份题名、作者、摘要、方法和结果对应同一论文；保留 12 页正式期刊版，归并 42 页作者稿。实际期刊为 Aerospace Science and Technology，原 ICARUS 标签有误。 |

原始作者稿和旧 README 已备份至 `../.research/papers/backup/`，不计入本目录文献数。2019、2020、2022 年强化学习文章的动作空间、验证内容和发表记录不同，作为三篇独立研究保留。原 README 指向不存在的 `notes/` 和 `manuscript_references.md` 的链接已替换为本文内的详细记录。既有 [67P/Rosetta 文献对照](67P_Rosetta_References.md) 保留为专题补充。

## 分类总览

每篇论文按主要研究目标归入一个主类，交叉主题用逐篇记录的标签表达。计数仅包括已取得全文的 39 篇论文。

| 类别 | 数量 | 范围 | 论文索引 |
| --- | ---: | --- | --- |
| [A．形状重建与影像处理](#category-a) | 7 | SPG、SPC、SfM、联合估计、匹配对筛选和多任务形状模型。 | [P02](#p02)、[P03](#p03)、[P04](#p04)、[P19](#p19)、[P20](#p20)、[P25](#p25)、[P35](#p35) |
| [B．测绘需求、质量验证与地形科学](#category-b) | 6 | 任务地形产品、精度评价、真值检验，以及形状和地形的科学应用。 | [P08](#p08)、[P11](#p11)、[P13](#p13)、[P16](#p16)、[P17](#p17)、[P22](#p22) |
| [C．通用主动重建与视角规划](#category-c) | 6 | 机器人场景中的信息路径规划、NBV、一次性视角集合与隐式重建。 | [P09](#p09)、[P12](#p12)、[P18](#p18)、[P21](#p21)、[P23](#p23)、[P27](#p27) |
| [D．小天体自主成像与观测规划](#category-d) | 5 | 面向小天体的拍摄时机、SPC 约束、鲁棒观测组合和载荷计划生成。 | [P07](#p07)、[P10](#p10)、[P14](#p14)、[P30](#p30)、[P38](#p38) |
| [E．任务设计与科学运行](#category-e) | 8 | Rosetta、Psyche、Hera、Lucy 的任务架构、观测时序、仿真和地面运行。 | [P01](#p01)、[P05](#p05)、[P15](#p15)、[P26](#p26)、[P28](#p28)、[P29](#p29)、[P31](#p31)、[P33](#p33) |
| [F．自主光学导航与着陆轨迹](#category-f) | 4 | 联合建图导航、地标匹配、抗扰着陆和导航观测驱动的轨迹设计。 | [P06](#p06)、[P24](#p24)、[P36](#p36)、[P37](#p37) |
| [G．任务级轨迹与协同探测](#category-g) | 3 | 任务分配和转移轨迹综述，以及侦察、交会、撞击偏转与伴随观测。 | [P32](#p32)、[P34](#p34)、[P39](#p39) |

## 全部本地论文索引

按年份和题名排序。点击题名打开 PDF，点击编号进入逐篇阅读。

| 编号 | 年份 | 论文 / 本地 PDF | 主类 | BibTeX 键 |
| --- | --- | --- | --- | --- |
| [P01](#p01) | 2007 | [The Rosetta Mission - Flying Towards the Origin of the Solar System](<2007 - The Rosetta Mission - Flying Towards the Origin of the Solar System.pdf>) | E | `glassmeier2007rosetta` |
| [P02](#p02) | 2008 | [Characterizing and navigating small bodies with imaging data](<2008 - Characterizing and navigating small bodies with imaging data.pdf>) | A | `gaskell2008` |
| [P03](#p03) | 2015 | [Shape model, reference system definition, and cartographic mapping standards for comet 67P-Churyumov-Gerasimenko - Stereo-photogrammetric analysis of Rosetta-OSIRIS image data](<2015 - Shape model, reference system definition, and cartographic mapping standards for comet 67P-Churyumov-Gerasimenko - Stereo-photogrammetric analysis of Rosetta-OSIRIS image data.pdf>) | A | `preusker2015` |
| [P04](#p04) | 2017 | [The global meter-level shape model of comet 67P-Churyumov-Gerasimenko](<2017 - The global meter-level shape model of comet 67P-Churyumov-Gerasimenko.pdf>) | A | `preusker2017` |
| [P05](#p05) | 2017 | [The Rosetta mission orbiter science overview - the comet phase](<2017 - The Rosetta mission orbiter science overview - the comet phase.pdf>) | E | `taylor2017rosetta` |
| [P06](#p06) | 2018 | [Autonomous Small Body Mapping and Spacecraft Navigation Via Real-Time SPC-SLAM](<2018 - Autonomous Small Body Mapping and Spacecraft Navigation Via Real-Time SPC-SLAM.pdf>) | F | `baldini2018` |
| [P07](#p07) | 2019 | [Autonomous Imaging and Mapping of Small Bodies Using Deep Reinforcement Learning](<2019 - Autonomous Imaging and Mapping of Small Bodies Using Deep Reinforcement Learning.pdf>) | D | — |
| [P08](#p08) | 2019 | [Shape of (101955) Bennu indicative of a rubble pile with internal stiffness](<2019 - Shape of (101955) Bennu indicative of a rubble pile with internal stiffness.pdf>) | B | — |
| [P09](#p09) | 2020 | [An Efficient Sampling-Based Method for Online Informative Path Planning in Unknown Environments](<2020 - An Efficient Sampling-Based Method for Online Informative Path Planning in Unknown Environments.pdf>) | C | `schmid2020` |
| [P10](#p10) | 2020 | [Deep Reinforcement Learning approach for Small Bodies Shape Reconstruction Enhancement](<2020 - Deep Reinforcement Learning approach for Small Bodies Shape Reconstruction Enhancement.pdf>) | D | — |
| [P11](#p11) | 2020 | [Digital terrain mapping by the OSIRIS-REx mission](<2020 - Digital terrain mapping by the OSIRIS-REx mission.pdf>) | B | `barnouin2020` |
| [P12](#p12) | 2020 | [PC-NBV - A Point Cloud Based Deep Network for Efficient Next Best View Planning](<2020 - PC-NBV - A Point Cloud Based Deep Network for Efficient Next Best View Planning.pdf>) | C | `zeng2020` |
| [P13](#p13) | 2021 | [Validation of Stereophotoclinometric Shape Models of Asteroid (101955) Bennu during the OSIRIS-REx Mission](<2021 - Validation of Stereophotoclinometric Shape Models of Asteroid (101955) Bennu during the OSIRIS-REx Mission.pdf>) | B | `alasad2021` |
| [P14](#p14) | 2022 | [Deep Reinforcement Learning-based policy for autonomous imaging planning of small celestial bodies mapping](<2022 - Deep Reinforcement Learning-based policy for autonomous imaging planning of small celestial bodies mapping.pdf>) | D | `piccinin2022` |
| [P15](#p15) | 2022 | [Operations for Autonomous Spacecraft](<2022 - Operations for Autonomous Spacecraft.pdf>) | E | `castano2022` |
| [P16](#p16) | 2022 | [Practical Stereophotoclinometry for Modeling Shape and Topography on Planetary Missions](<2022 - Practical Stereophotoclinometry for Modeling Shape and Topography on Planetary Missions.pdf>) | B | `palmer2022` |
| [P17](#p17) | 2022 | [Quality Assessment of Stereophotoclinometry as a Shape Modeling Method Using a Synthetic Asteroid](<2022 - Quality Assessment of Stereophotoclinometry as a Shape Modeling Method Using a Synthetic Asteroid.pdf>) | B | `weirich2022` |
| [P18](#p18) | 2022 | [SCONE - Surface Coverage Optimization in Unknown Environments by Volumetric Integration](<2022 - SCONE - Surface Coverage Optimization in Unknown Environments by Volumetric Integration.pdf>) | C | `guedon2022` |
| [P19](#p19) | 2023 | [High-resolution shape models of Phobos and Deimos from stereophotoclinometry](<2023 - High-resolution shape models of Phobos and Deimos from stereophotoclinometry.pdf>) | A | `ernst2023` |
| [P20](#p20) | 2023 | [Stereophotoclinometry on the OSIRIS-REx Mission - Mathematics and Methods](<2023 - Stereophotoclinometry on the OSIRIS-REx Mission - Mathematics and Methods.pdf>) | A | `gaskell2023` |
| [P21](#p21) | 2024 | [Active Implicit Reconstruction Using One-Shot View Planning](<2024 - Active Implicit Reconstruction Using One-Shot View Planning.pdf>) | C | `hu2024` |
| [P22](#p22) | 2024 | [Detection and characterization of icy cavities on the nucleus of comet 67P-Churyumov-Gerasimenko](<2024 - Detection and characterization of icy cavities on the nucleus of comet 67P-Churyumov-Gerasimenko.pdf>) | B | `lamy2024cavities` |
| [P23](#p23) | 2024 | [GenNBV - Generalizable Next-Best-View Policy for Active 3D Reconstruction](<2024 - GenNBV - Generalizable Next-Best-View Policy for Active 3D Reconstruction.pdf>) | C | `chen2024` |
| [P24](#p24) | 2025 | [A Desensitized Trajectory Optimization Method for Landing of Small Bodies](<2025 - A Desensitized Trajectory Optimization Method for Landing of Small Bodies.pdf>) | F | — |
| [P25](#p25) | 2025 | [A Rapid Method for Matching Pair Determination from Disordered and Massive Asteroid Images](<2025 - A Rapid Method for Matching Pair Determination from Disordered and Massive Asteroid Images.pdf>) | A | — |
| [P26](#p26) | 2025 | [Hera CubeSats Mission Planning and Payloads Operations Concept for Didymos Binary Asteroid Characterization](<2025 - Hera CubeSats Mission Planning and Payloads Operations Concept for Didymos Binary Asteroid Characterization.pdf>) | E | — |
| [P27](#p27) | 2025 | [Integrating One-Shot View Planning with a Single Next-Best View via Long-Tail Multiview Sampling](<2025 - Integrating One-Shot View Planning with a Single Next-Best View via Long-Tail Multiview Sampling.pdf>) | C | `pan2025` |
| [P28](#p28) | 2025 | [Lucy's Donaldjohanson Encounter Science Planning and Sequencing](<2025 - Lucy's Donaldjohanson Encounter Science Planning and Sequencing.pdf>) | E | — |
| [P29](#p29) | 2025 | [Lucy's Encounter with Dinkinesh](<2025 - Lucy's Encounter with Dinkinesh.pdf>) | E | — |
| [P30](#p30) | 2025 | [Observation Planning Methods Under Modeling Constraints of Small Celestial Bodies](<2025 - Observation Planning Methods Under Modeling Constraints of Small Celestial Bodies.pdf>) | D | `wang2025` |
| [P31](#p31) | 2025 | [Psyche Mission Description and Design Rationale](<2025 - Psyche Mission Description and Design Rationale.pdf>) | E | `polanskey2025` |
| [P32](#p32) | 2025 | [Research Progress on Trajectory Optimization of Space Target Cooperative Detection](<2025 - Research Progress on Trajectory Optimization of Space Target Cooperative Detection.pdf>) | G | — |
| [P33](#p33) | 2025 | [Simulating Lucy's Flybys of Its Target Trojan Asteroids](<2025 - Simulating Lucy's Flybys of Its Target Trojan Asteroids.pdf>) | E | `salmon2025` |
| [P34](#p34) | 2025 | [Space Mission Options for Reconnaissance and Mitigation of Asteroid 2024 YR4](<2025 - Space Mission Options for Reconnaissance and Mitigation of Asteroid 2024 YR4.pdf>) | G | — |
| [P35](#p35) | 2025 | [Stereophotoclinometry Revisited](<2025 - Stereophotoclinometry Revisited.pdf>) | A | `driver2025` |
| [P36](#p36) | 2025 | [Surface Reconstruction Techniques for Asteroid Missions and the Applications in Autonomous Optical Navigation](<2025 - Surface Reconstruction Techniques for Asteroid Missions and the Applications in Autonomous Optical Navigation.pdf>) | F | — |
| [P37](#p37) | 2026 | [A Navigation Observation-Driven Trajectory Planning Method for Asteroid Landing](<2026 - A Navigation Observation-Driven Trajectory Planning Method for Asteroid Landing.pdf>) | F | — |
| [P38](#p38) | 2026 | [SB-ObsGen - A Framework for Flyby Small Body Observation Plan Generation Using LLMs and Physics-Informed Tools](<2026 - SB-ObsGen - A Framework for Flyby Small Body Observation Plan Generation Using LLMs and Physics-Informed Tools.pdf>) | D | `sbobsgen2026` |
| [P39](#p39) | 2026 | [Trajectory Optimization for Asteroid Kinetic Impact and Proximity Observation Under Orbital Deflection Constraints](<2026 - Trajectory Optimization for Asteroid Kinetic Impact and Proximity Observation Under Orbital Deflection Constraints.pdf>) | G | — |

## 方法之间的关键区别

以下对照帮助选取适合的基线和指标；依据对应本地论文的方法与实验。

| 研究线索 | 决策/估计对象 | 核心评价 | 阅读时应区分 |
| --- | --- | --- | --- |
| SPC/SPG：[P02](#p02)、[P03](#p03)、[P20](#p20)、[P35](#p35) | 地形、反照率、相机位姿、光照等 | 几何/光度一致性与重建产品 | 重建求解器与主动观测规划器承担不同任务。 |
| 模型质量：[P13](#p13)、[P17](#p17) | 已生成形状的验证 | 内部残差、sigma/FormU、OLA 或合成真值误差 | GSD、内部一致性、绝对精度和配准后误差分别报告。 |
| 通用视角规划：[P09](#p09)、[P12](#p12)、[P18](#p18)、[P21](#p21)、[P23](#p23)、[P27](#p27) | 路径、单个视角或整组视角 | 新增覆盖、重建质量、移动与拍摄成本 | RGB-D/点云和自由空间运动假设需要适配小天体的动力学与日照。 |
| 小天体 DRL：[P07](#p07)、[P10](#p10)、[P14](#p14) | 前者含推力/拍摄/下传，后两者主要为二值拍摄时机 | 几何映射奖励；2020 年另验证合成图像点云 | 几何评分提升与 SPC 高程误差下降不是同一个结论。 |
| SPC 组合规划：[P30](#p30) | 离散位置及每个位置的拍摄动作 | 满足几何和次数条件的面覆盖、动作/位置成本、扰动稳健性 | 有效面覆盖尚需由真实重建精度进一步检验。 |
| 任务序列：[P31](#p31)、[P33](#p33)、[P38](#p38) | 轨道阶段、指令/载荷活动、时间线 | 可执行性、观测窗口、分辨率覆盖、资源和参考计划一致性 | 任务计划验证与局部模型精度优化应各自建立指标。 |

## 逐篇阅读

<a id="category-a"></a>

### A．形状重建与影像处理

SPG、SPC、SfM、联合估计、匹配对筛选和多任务形状模型。

<a id="p02"></a>

#### P02．Characterizing and navigating small bodies with imaging data

**文献信息：** Gaskell 等，2008，Meteoritics & Planetary Science 43(6):1049–1061。[发表/来源入口](https://doi.org/10.1111/j.1945-5100.2008.tb00692.x)；[本地 PDF](<2008 - Characterizing and navigating small bodies with imaging data.pdf>)（14 页）。 引用键：`gaskell2008`。

**主类与标签：** A．形状重建与影像处理；SPC；maplet；反照率；地标导航。

- **研究问题：** 如何在小天体影像分辨率、视角和光照不断变化的情况下，同时恢复局部地形、全局形状与相机/探测器状态，并让这些产品支持导航和科学分析。
- **创新点与贡献：** 系统化说明立体几何与光度地形恢复的互补作用：立体观测提供空间锚定，明暗信息恢复细节。把带地形和反照率的局部地标图与全局形状、图像配准和导航状态相连接，是后续 SPC 方法与任务应用的重要基础。
- **方法：** 建立局部 L-maps/maplets，利用多幅图像中地标位置、反射亮度及不同照明方向估计位置、坡度与反照率；迭代修正地形、地标向量、相机位置和姿态，再将局部地图融合为全局模型，并通过相关匹配开展地标导航。
- **验证与边界：** 讨论 Eros、Itokawa 等目标的建模，以及地形、坡度、引力和表面物质分析。高分辨率细节仍依赖合适的光照和可靠的几何锚定；不能只凭单幅图像明暗恢复无歧义的绝对高程，也不能把重建方法本身视为观测规划器。
- **原文定位：** PDF 第 3–8 页局部地图、全局模型及估计方法，第 9–13 页科学和导航应用；第 1 页为仓库封面。

<a id="p03"></a>

#### P03．Shape model, reference system definition, and cartographic mapping standards for comet 67P-Churyumov-Gerasimenko - Stereo-photogrammetric analysis of Rosetta-OSIRIS image data

**文献信息：** Preusker 等，2015，Astronomy & Astrophysics 583:A33。[发表/来源入口](https://doi.org/10.1051/0004-6361/201526349)；[本地 PDF](<2015 - Shape model, reference system definition, and cartographic mapping standards for comet 67P-Churyumov-Gerasimenko - Stereo-photogrammetric analysis of Rosetta-OSIRIS image data.pdf>)（21 页）。 引用键：`preusker2015`。

**主类与标签：** A．形状重建与影像处理；67P；SPG；SHAP4S；光束法平差；参考系。

- **研究问题：** Rosetta 初期 OSIRIS 影像怎样形成具有明确精度和坐标定义的 67P 形状模型，以及如何为后续测绘、地名和数据配准建立统一参考系。
- **创新点与贡献：** 生成 SHAP4S 高分辨率立体摄影测量模型，并联合讨论旋转参数、Cheops 参考系及不规则双叶彗核的制图规范；贡献同时包括几何产品和可复用的坐标/测绘标准。
- **方法：** 使用 2014 年 8–9 月的两百余幅 NAC 图像，进行连接点匹配、光束法平差以改善相机位置和指向，再用立体交会生成三维点与三角网；通过旋转参数试探和拟合改善一致性，定义本体坐标系与经纬度表达。
- **验证与边界：** 模型约含 1600 万三角面，横向采样约 2 m，垂向精度达分米量级；当时主要覆盖北半球及约 70% 表面，未观测区域需插补。覆盖、精度与体积估计受到南半球缺测限制，不能把 SHAP4S 当作均匀实测的完整全球模型。
- **原文定位：** PDF 第 4–5 页 §2 方法，第 6–10 页 §4 模型结果，第 11–14 页参考系和制图；前 2 页为仓库资料。

<a id="p04"></a>

#### P04．The global meter-level shape model of comet 67P-Churyumov-Gerasimenko

**文献信息：** Preusker 等，2017，Astronomy & Astrophysics 607:L1。[发表/来源入口](https://doi.org/10.1051/0004-6361/201731798)；[本地 PDF](<2017 - The global meter-level shape model of comet 67P-Churyumov-Gerasimenko.pdf>)（6 页）。 引用键：`preusker2017`。

**主类与标签：** A．形状重建与影像处理；67P；SPG；SHAP7；全球覆盖；多时相。

- **研究问题：** 怎样利用 Rosetta 后续、不同季节和照明条件的图像，补齐早期 67P 模型的南半球缺测并获得全球米级形状产品。
- **创新点与贡献：** 发布 SHAP7，把 SHAP4S 的局部/半球覆盖扩展为更完整的全球模型，并提升几何采样；同时说明跨时段建模与表面变化研究之间的关系。
- **方法：** 选用 2014 年 8 月至 2016 年 2 月的 1500 余幅 OSIRIS NAC 图像，按立体组合处理连接点、相机外方位与密集三维点，融合局部立体结果并网格化；针对不同区域的可见性和照明选择补充图像。
- **验证与边界：** 模型约含 4400 万三角面，横向分辨率约 1–1.5 m、垂向精度为分米量级，所得体积约 18.56 km³。它融合了不同时期影像，部分区域使用近日点后的数据补齐；分析局部形变时应核对区域影像时间，不能假定全部网格代表同一瞬时表面。
- **原文定位：** PDF 第 3–4 页 §2–3 数据与方法，第 5 页结果和总结；第 1 页为仓库封面。

<a id="p19"></a>

#### P19．High-resolution shape models of Phobos and Deimos from stereophotoclinometry

**文献信息：** Ernst 等，2023，Earth, Planets and Space 75:103。[发表/来源入口](https://doi.org/10.1186/s40623-023-01814-7)；[本地 PDF](<2023 - High-resolution shape models of Phobos and Deimos from stereophotoclinometry.pdf>)（35 页）。 引用键：`ernst2023`。

**主类与标签：** A．形状重建与影像处理；Phobos；Deimos；SPC；多任务配准；地形产品。

- **研究问题：** 如何将跨任务、跨年代、分辨率和相机条件不同的火星卫星图像合成一致的高分辨率形状与地形产品，尤其改善 Deimos 既有模型的细节。
- **创新点与贡献：** 整合 Viking 1/2、Phobos 2、MGS、Mars Express 和 MRO 数据，提供两颗卫星的全球形状、区域地形和相关几何产品；Deimos 模型首次达到可清楚解析部分地质特征的水平。
- **方法：** 以 SPC 配准和处理多源影像，迭代修正相机/SPICE 几何并生成局部 maplets，再融合全球三角网与区域 DTM；同时输出反照率、改进的几何内核及坡度等派生产品，分别评价一致性、精密度和定位精度。
- **验证与边界：** Phobos 使用 2382 幅图像，全球 GSD 约 18 m、约 1200 万面；Deimos 使用 332 幅、约 20 m、约 300 万面。论文区分估计的精度和精密度：Phobos 约 36 m/4 m，Deimos 已建模半球约 65 m/9 m；Deimos 的 9 m 仅由 sigma 推得，原文指出其可靠性有限。未充分观测区域不能套用已建模半球的质量数字。
- **原文定位：** PDF 第 2–15 页数据与方法，第 16–31 页模型及地形结果，第 32–33 页总结。

<a id="p20"></a>

#### P20．Stereophotoclinometry on the OSIRIS-REx Mission - Mathematics and Methods

**文献信息：** Gaskell 等，2023，The Planetary Science Journal 4(4):63。[发表/来源入口](https://doi.org/10.3847/PSJ/acc4b9)；[本地 PDF](<2023 - Stereophotoclinometry on the OSIRIS-REx Mission - Mathematics and Methods.pdf>)（16 页）。 引用键：`gaskell2023`。

**主类与标签：** A．形状重建与影像处理；SPC 数学；最小二乘；相机状态；SPC/OLA 融合。

- **研究问题：** 怎样准确描述 OSIRIS-REx 所用 SPC 的数学对象、观测方程和迭代求解方式，并理解局部地形、全局形状、相机状态及激光约束如何耦合。
- **创新点与贡献：** 系统展开实际 SPC 的数学与方法，解释为何把庞大的联合问题分成相互更新的局部地形、地标向量及航天器状态求解，并讨论激光数据融合与尺度修正。
- **方法：** 以相机投影、图像亮度和反射模型建立约束，用立体几何确定空间位置、光度信息确定反照率和坡度，再积分地形；交替进行最小二乘更新，将 2.5D maplets 汇入 ICQ 等全局表示，并通过 OLA 或轮廓补充约束。
- **验证与边界：** 依据 Bennu 任务说明各种估计量和产品之间的关系。局部高度场与全局三维网格有不同表达限制，光照方向不足也会导致某些坡度分量约束弱；该文是重建求解基础，尚未给出把观测组合直接优化为高程误差最小的规划器。
- **原文定位：** PDF 第 3–13 页 §2–6 观测模型、估计、全局产品和激光融合；第 1 页为仓库封面。

<a id="p25"></a>

#### P25．A Rapid Method for Matching Pair Determination from Disordered and Massive Asteroid Images

中文题名：一种海量无序小行星遥感影像匹配对快速确定方法。

**文献信息：** 张九江等，2025，深空探测学报 12(5):542–556。[发表/来源入口](https://doi.org/10.3724/j.issn.2096-9287.2025.20250007)；[本地 PDF](<2025 - A Rapid Method for Matching Pair Determination from Disordered and Massive Asteroid Images.pdf>)（16 页）。

**主类与标签：** A．形状重建与影像处理；海量影像；匹配对；KD-tree；SPICE；SPC 图像筛选。

- **研究问题：** 面对无序、数量很大的小行星影像，如何快速筛出可能重叠的匹配对，并处理图像中心落在背景、目标仅局部入镜等导致的定位失败。
- **创新点与贡献：** 提出基于表面投影中心与三维 KD-tree 的候选匹配对搜索；对无法使用原图中心定位的影像构造有效像素的虚拟中心，并扩展到 SPC 适用观测筛选。
- **方法：** 利用 ISIS/PDS 数据、SPICE 与相机模型获取图像几何；正常图像取中心射线表面交点，异常图像通过灰度阈值与有效像素采样求虚拟中心再投影。按图像尺寸、分辨率及重叠要求确定搜索半径，用 KD-tree 建立匹配对关系，再按几何约束筛选 SPC 影像。
- **验证与边界：** 在 Bennu、Vesta、Ryugu 数据上比较匹配对正确性、耗时、平差残差及正射/DEM 产品。它加速的是候选配对与筛选，仍需后续特征匹配和几何校验；中心邻近是重叠的近似判据，不等同于全局最优观测组合或新的深度特征匹配器。
- **原文定位：** PDF 第 4–6 页 §1 方法，第 7–14 页数据集和实验；本地正文为英文，前置资料含中文题名。

<a id="p35"></a>

#### P35．Stereophotoclinometry Revisited

**文献信息：** Driver、Vaughan、Cheng、Ansar、Christian、Tsiotras，2025，arXiv:2504.08252v1。[发表/来源入口](https://arxiv.org/abs/2504.08252)；[本地 PDF](<2025 - Stereophotoclinometry Revisited.pdf>)（45 页）。 引用键：`driver2025`。

**主类与标签：** A．形状重建与影像处理；PhoMo；光度法；SfM；因子图；联合优化；Dawn。

- **研究问题：** 传统 SPC 的几何与光度求解能否通过统一优化和自动特征流程改进，减少手工局部地图处理，并同时校正姿态、地形、光照与反射参数。
- **创新点与贡献：** 提出 Photometry from Motion（PhoMo），把稠密特征、SfM 初始化及光度因子图结合，联合估计相机位姿、地标位置、太阳方向、法向与反照率/反射参数。
- **方法：** 采用深度特征匹配和 GTSfM 等几何前端建立初始重建；在 MAP/非线性最小二乘中加入投影、像素光度、法向与邻域几何及平滑约束，使用 Lunar–Lambert/Akimov 等反射模型，以 GTSAM/Levenberg–Marquardt 迭代优化。
- **验证与边界：** 使用 Dawn 对 Vesta Cornelia 和 Ceres Ahuna Mons、Ikapati 的真实图像，比较重渲染误差/PSNR及与 SPG/SPC 表面的关系。改善光度重现并不自动证明绝对高程更准，仍受初始化、反射模型和观测几何影响；本地为预印本，且研究重建求解而非主动选视角。
- **原文定位：** PDF 第 8–19 页 §IV 方法，第 19–32 页 §V–VI 实验与讨论，第 33 页结论，第 35–37 页导数补充。

<a id="category-b"></a>

### B．测绘需求、质量验证与地形科学

任务地形产品、精度评价、真值检验，以及形状和地形的科学应用。

<a id="p08"></a>

#### P08．Shape of (101955) Bennu indicative of a rubble pile with internal stiffness

**文献信息：** Barnouin 等，2019，Nature Geoscience 12:247–252。[发表/来源入口](https://doi.org/10.1038/s41561-019-0330-x)；[本地 PDF](<2019 - Shape of (101955) Bennu indicative of a rubble pile with internal stiffness.pdf>)（9 页）。

**主类与标签：** B．测绘需求、质量验证与地形科学；Bennu；SPC；OLA；碎石堆；内部刚度。

- **研究问题：** Bennu 的陀螺形、山脊、沟槽和坡面运动如何约束其形成演化及内部结构；碎石堆天体能否在没有任何内部强度的条件下维持这些形态。
- **创新点与贡献：** 通过高分辨率全球形状和地形特征推断 Bennu 虽然具有碎石堆结构，却存在内部摩擦或黏聚所提供的刚度，并把形态与历史快速自转及质量迁移联系起来。创新主要是形状支持的科学解释。
- **方法：** 利用 1500 余幅 OCAMS 图像开展 SPC，形成 v20 形状模型，辅以 OLA 测量检验；分析赤道隆起、连接两极的高地/山脊、沟槽和坡度，与旋转及颗粒天体形态机制比较。
- **验证与边界：** 观测形态支持碎石堆且具有一定内部强度的解释，但并非直接测得完整内部结构或唯一确定强度参数。Methods 明确采用 v20；模型的精确输入数 1560 张由后续验证论文表 1 给出。引用文中具体数值时还应核对作者更正版本。
- **原文定位：** PDF 第 1–5 页科学结果和讨论，第 7 页 Methods；Bennu 模型版本统计见本 README 附录。

<a id="p11"></a>

#### P11．Digital terrain mapping by the OSIRIS-REx mission

**文献信息：** Barnouin 等，2020，Planetary and Space Science 180:104764。[发表/来源入口](https://doi.org/10.1016/j.pss.2019.104764)；[本地 PDF](<2020 - Digital terrain mapping by the OSIRIS-REx mission.pdf>)（16 页）。 引用键：`barnouin2020`。

**主类与标签：** B．测绘需求、质量验证与地形科学；OSIRIS-REx；DTM；SPC；OLA；采样区选择。

- **研究问题：** OSIRIS-REx 如何把导航、接触采样安全和地质研究的需求，转化为不同尺度的 Bennu 数字地形产品，并组织相机与激光高度计数据的建模流程。
- **创新点与贡献：** 给出任务级、多尺度 DTM 生产和验证方案，将 SPC 与 OLA 两条数据链、全球/局部地形和派生产品统一到任务需求中，强调从接近阶段到候选采样区的逐级细化。
- **方法：** 从远距离轮廓建立初始形状，生成低分辨率 maplets；随着新图像进入，迭代改善形状、相机几何和旋转状态，再细化全球/区域 DTM。对 OLA 点云进行分区、配准和地形生成，并派生坡度、引力及导航/安全分析产品。
- **验证与边界：** 通过任务前仿真测试、误差预算和处理规划说明产品可满足的尺度及用途。论文重点是测绘链与需求实现，不是学习型观测规划；同一任务中的 maplet 采样间距、影像 GSD 和高程精度须分别报告。其 §3.1 支持已有模型作为后续精细重建初值。
- **原文定位：** PDF 第 2–10 页 §2–4 需求与建模链，第 6 页 §3.1 递进流程，第 12–14 页派生产品。

<a id="p13"></a>

#### P13．Validation of Stereophotoclinometric Shape Models of Asteroid (101955) Bennu during the OSIRIS-REx Mission

**文献信息：** Al Asad 等，2021，The Planetary Science Journal 2(2):82。[发表/来源入口](https://doi.org/10.3847/PSJ/abe4dc)；[本地 PDF](<2021 - Validation of Stereophotoclinometric Shape Models of Asteroid (101955) Bennu during the OSIRIS-REx Mission.pdf>)（16 页）。 引用键：`alasad2021`。

**主类与标签：** B．测绘需求、质量验证与地形科学；Bennu；SPC 质量验证；OLA；内部一致性；版本演进。

- **研究问题：** SPC 模型在真实任务中没有完整表面真值时，怎样确认几何精度与导航可用性，并判断不同版本的改进是否可信。
- **创新点与贡献：** 建立多证据验证框架，把输入观测条件、图像一致性、内部几何残差和独立 OLA 数据结合；记录 Bennu 多个正式模型的输入数量、采样和验证统计，避免只用单一内部指标代表真实误差。
- **方法：** 检查图像覆盖和几何；将形状渲染结果与检验图像比较轮廓、关键点和尺度；计算 maplet 的立体残差 RMS、重叠 maplets 的顶点高度离散 sigma，并分析相机位置修正；用 OLA 点到模型距离进行独立外部校验。
- **验证与边界：** 比较 v07 至 v42 等模型，确认任务地形产品的质量并展示迭代改进。RMS 和 sigma 是不同内部指标，不能互相替代或直接等同绝对高程误差；各版 OLA 验证使用当时可用的数据。图 4 还显示 v20 maplets 保留在 v42 中；完整版本表保留在附录。
- **原文定位：** PDF 第 5 页 §3 更新方式，第 6 页表 1，第 9 页图 4，第 10–12 页验证方法和 OLA 比较；前 2 页为仓库资料。

<a id="p16"></a>

#### P16．Practical Stereophotoclinometry for Modeling Shape and Topography on Planetary Missions

**文献信息：** Palmer 等，2022，The Planetary Science Journal 3(5):102。[发表/来源入口](https://doi.org/10.3847/PSJ/ac460f)；[本地 PDF](<2022 - Practical Stereophotoclinometry for Modeling Shape and Topography on Planetary Missions.pdf>)（16 页）。 引用键：`palmer2022`。

**主类与标签：** B．测绘需求、质量验证与地形科学；实用 SPC；操作流程；maplet；观测几何；人工干预。

- **研究问题：** 如何把 SPC 数学原理落实为任务中可持续生产的地形流程，特别是初始模型、图像筛选、地图维护和质量控制怎样影响最终产品。
- **创新点与贡献：** 系统描述行星任务中的实际 SPC 操作经验，展示从粗模型到精细区域地图的完整流程，并给出互补照明和视角的观测建议；补足仅说明算法公式而缺少工程执行细节的问题。
- **方法：** 先建立轮廓形状和地标，再进行图像配准、局部 albedo/slope 估计与坡度积分，迭代修正相机和地标；逐步增加或细化 maplets，整合 bigmaps 与全球模型。建议用约 30° emission 的四个方位地形图像，加低 incidence 的反照率图像形成互补约束。
- **验证与边界：** 结合 Bennu 等任务说明方法可以支持形状、地形和导航，但实际处理仍需图像质量检查、参数调整及人工处理异常。上述观测组合是操作建议，不能机械解释为任何地形只需五张图就能达到指定精度；生产周期与自动化程度亦受任务和数据条件影响。
- **原文定位：** PDF 第 3–11 页 §3 实际处理步骤，第 11–15 页任务规划、导航与应用。

<a id="p17"></a>

#### P17．Quality Assessment of Stereophotoclinometry as a Shape Modeling Method Using a Synthetic Asteroid

**文献信息：** Weirich 等，2022，The Planetary Science Journal 3(5):103。[发表/来源入口](https://doi.org/10.3847/PSJ/ac46d2)；[本地 PDF](<2022 - Quality Assessment of Stereophotoclinometry as a Shape Modeling Method Using a Synthetic Asteroid.pdf>)（13 页）。 引用键：`weirich2022`。

**主类与标签：** B．测绘需求、质量验证与地形科学；SPC；合成真值；FormU；误差校准；Bennu。

- **研究问题：** SPC 内部不确定度能否反映真实地形误差，以及在真实表面不可完全测得时怎样校准模型质量指标。
- **创新点与贡献：** 构造具有已知几何与反照率的合成小行星，按任务观测条件生成图像，再完整重建并与真值比较；将内部 FormU 指标与实际三维误差联系，而不只报告拟合残差。
- **方法：** 在 Bennu 式形状上生成陨石坑、巨石和反照率变化，模拟相机轨迹、光照及状态误差，按 SPC 流程制作 75 cm 和 35 cm 任务产品；计算地图内部指标，进行模型配准/ICP 后与真值比较三维偏差，分析整体位置漂移和局部形状误差。
- **验证与边界：** 优化后两类模型三维 RMS 误差约 13 cm、10 cm，对应 FormU 约 12 cm、10 cm，本试验中二者在约两倍范围内一致。这是特定合成场景的经验校准，不是任意观测下的误差保证；配准移除了整体坐标偏移，产品名称也不等于其高程精度。
- **原文定位：** PDF 第 3–8 页 §2 合成与重建，第 9–11 页结果分析，第 12 页结论；第 1 页为仓库封面。

<a id="p22"></a>

#### P22．Detection and characterization of icy cavities on the nucleus of comet 67P-Churyumov-Gerasimenko

**文献信息：** Lamy、Faury、Romeuf、Groussin，2024，MNRAS 531:2494–2516。[发表/来源入口](https://doi.org/10.1093/mnras/stae1290)；[本地 PDF](<2024 - Detection and characterization of icy cavities on the nucleus of comet 67P-Churyumov-Gerasimenko.pdf>)（23 页）。 引用键：`lamy2024cavities`。

**主类与标签：** B．测绘需求、质量验证与地形科学；67P；冰质空腔；高分辨率地形；阴影；热环境。

- **研究问题：** 67P 表面的冰质空腔是否提供浅表以下物质的直接观察窗口，其形状、冰含量、日照历史和活动之间存在什么关系。
- **创新点与贡献：** 识别和刻画三处冰质空腔，把超高分辨率地形、立体显示、光谱/反射特征及局部光热环境结合起来，研究空腔暴露的地下物质和可能的活动机制。
- **方法：** 分析 2016 年 4 月 9–10 日高分辨率图像和立体组合，使用约 1.33 亿三角面的 67P-133M 摄影测量模型提取剖面、壁面及深度；通过可见光颜色/反射分析估计冰与暗物质混合，再以地形遮挡和太阳几何计算日照、温度与长期阴影。
- **验证与边界：** 研究空腔深度约 20–47 m、冰质亮斑尺度约 15–30 m，讨论冰长期保存与短时底部照明引发活动的可能联系。冰含量依赖混合模型，喷流归因和保存机制是观测约束下的解释；这篇是地形科学应用，不是主动观测优化。预印本题名使用 characterisation，文件按正式题名命名。
- **原文定位：** PDF 第 2–7 页 §2–4 数据与空腔，第 8–18 页光照、光谱及讨论，第 19 页结论。

<a id="category-c"></a>

### C．通用主动重建与视角规划

机器人场景中的信息路径规划、NBV、一次性视角集合与隐式重建。

<a id="p09"></a>

#### P09．An Efficient Sampling-Based Method for Online Informative Path Planning in Unknown Environments

**文献信息：** Schmid 等，2020，IEEE Robotics and Automation Letters 5(2):1500–1507。[发表/来源入口](https://doi.org/10.1109/LRA.2020.2969191)；[本地 PDF](<2020 - An Efficient Sampling-Based Method for Online Informative Path Planning in Unknown Environments.pdf>)（8 页）。 引用键：`schmid2020`。

**主类与标签：** C．通用主动重建与视角规划；信息路径规划；RRT*；TSDF；未知环境；在线树更新。

- **研究问题：** 在未知环境中，如何兼顾探索新区域、改善已建表面的质量和飞行代价，并避免每获得一次新观测就重新执行代价高昂的全局规划。
- **创新点与贡献：** 提出可持续维护的信息轨迹树，把候选路径的收益、成本及局部重连用于在线决策；设计与测量对重建贡献有关的收益，使规划既关注未知空间，也关注已有但质量不足的表面。
- **方法：** 以 RRT* 风格扩展和重连轨迹树，执行选中分支后重新设根，保留未执行部分并局部更新收益；在 TSDF 地图中结合射线投射、表面距离和已有测量权重估计新观测价值，按路径收益/成本选择并调整规划范围。
- **验证与边界：** 在探索和表面重建仿真及真实微型飞行器实验中验证在线效率与建图效果。收益衡量 TSDF 测量贡献，并未建模小天体 SPC 的太阳方位、光度退化或轨道动力学；迁移到小天体需重定义收益、可行轨迹和观测约束。
- **原文定位：** PDF 第 3–4 页轨迹树和收益函数，第 5–8 页实验及结论。

<a id="p12"></a>

#### P12．PC-NBV - A Point Cloud Based Deep Network for Efficient Next Best View Planning

**文献信息：** Zeng、Zhao、Liu，2020，IEEE/RSJ IROS:7050–7057。[发表/来源入口](https://doi.org/10.1109/IROS45743.2020.9340916)；[本地 PDF](<2020 - PC-NBV - A Point Cloud Based Deep Network for Efficient Next Best View Planning.pdf>)（8 页）。 引用键：`zeng2020`。

**主类与标签：** C．通用主动重建与视角规划；PC-NBV；点云；监督学习；离散视角；多视图。

- **研究问题：** 在只看到物体部分点云时，如何快速评估下一视角的新增表面覆盖，减少体素化和逐候选视角射线计算的在线开销。
- **创新点与贡献：** 直接用局部点云和已选视角状态预测全部候选视角收益；提出无需修改网络或重新训练的多视角扩展，使单视角收益网络能够一次选择一组视角。
- **方法：** 从完整三维模型虚拟扫描生成部分点云与真实新增覆盖标签；通过点特征提取、全局池化、视角状态拼接和自注意力融合，回归候选收益，以 MSE 训练。多视角时每选一个视角就更新二值视角状态，在点云暂不更新的情况下反复预测。
- **验证与边界：** 在 ShapeNet 已见/未见类别、ABC 和扫描模型上比较覆盖效率，并检验噪声敏感性及多视角性能。输出来自固定离散视角集合，指标是点云覆盖增益；不包含连续位姿控制、照明互补或 SPC 高程误差。实验使用的扫描模型也不等同于真实机器人全流程部署。
- **原文定位：** PDF 第 3–4 页训练标签、网络和多视角策略，第 5–7 页实验。

<a id="p18"></a>

#### P18．SCONE - Surface Coverage Optimization in Unknown Environments by Volumetric Integration

**文献信息：** Guédon、Monasse、Lepetit，2022，NeurIPS 35。[发表/来源入口](https://arxiv.org/abs/2208.10449)；[本地 PDF](<2022 - SCONE - Surface Coverage Optimization in Unknown Environments by Volumetric Integration.pdf>)（13 页）。 引用键：`guedon2022`。

**主类与标签：** C．通用主动重建与视角规划；SCONE；占据概率；可见性；体积积分；自由视角。

- **研究问题：** 在环境几何未知、尺度较大且存在遮挡时，如何估计任意候选相机的新表面覆盖，而非只对已见点或固定物体视角评分。
- **创新点与贡献：** 将未知表面的覆盖收益近似写成体积积分，联合学习占据概率和视角可见性，通过蒙特卡洛积分评分；使表面覆盖估计适用于更复杂场景及灵活相机位置。
- **方法：** 从部分点云提取多尺度局部和全局特征，预测空间占据概率；据此偏置采样代理点，融合几何与历史相机方向信息，预测用球谐展开表示的可见性函数；对代理点的占据/可见贡献积分，选择高新增覆盖视角并迭代更新。
- **验证与边界：** 在复杂三维场景的探索/重建基准中评估覆盖效率与泛化能力。方法依赖深度/点云输入及学习到的几何先验，积分关系有其近似和正则性条件；它预测覆盖，不直接计算光度地形精度，也不提供航天器可执行轨道或安全保证。
- **原文定位：** PDF 第 3–6 页积分关系与网络，第 7–10 页实验及分析。

<a id="p21"></a>

#### P21．Active Implicit Reconstruction Using One-Shot View Planning

**文献信息：** Hu、Pan、Jin、Popović、Bennewitz，2024，IEEE ICRA:12477–12483。[发表/来源入口](https://doi.org/10.1109/ICRA57147.2024.10611542)；[本地 PDF](<2024 - Active Implicit Reconstruction Using One-Shot View Planning.pdf>)（7 页）。 引用键：`hu2024`。

**主类与标签：** C．通用主动重建与视角规划；AIR-OSVP；隐式重建；一次性规划；集合覆盖；Transformer。

- **研究问题：** 初始观测稀疏且移动/拍摄预算有限时，如何减少逐次 NBV 引起的反复移动，同时得到较完整的物体重建。
- **创新点与贡献：** 将 POCO 隐式表面恢复与一次性视角集合预测结合，让稀疏观测形成更完整的规划依据；以集合覆盖标签训练网络，并把视角集合与执行路径组织起来。
- **方法：** 用预训练 POCO 将部分点云转成连续占据场并生成稠密表面；用完整训练模型及多视角一致性筛除预测离群点，构造最低视角数集合覆盖问题并用 Gurobi 求标签。PoinTr 点云 Transformer 与视角状态 Transformer 融合后预测视角掩码，使用加权交叉熵；对选中视角求短访问路径并局部避障。
- **验证与边界：** 在物体重建实验中比较视角数、移动和质量，说明预算受限时的优势。候选集是离散的，隐式补全包含模型先验，未实际观测的细节不能自动视为实测几何；网络目标也不是 SPC 的高程误差或受太阳照明约束的轨道设计。
- **原文定位：** PDF 第 3–4 页重建、集合覆盖与网络（图 4），第 5–6 页实验。

<a id="p23"></a>

#### P23．GenNBV - Generalizable Next-Best-View Policy for Active 3D Reconstruction

**文献信息：** Chen、Li、Wang、Xue、Pang，2024，IEEE/CVF CVPR:16436–16445。[发表/来源入口](https://doi.org/10.1109/CVPR52733.2024.01555)；[本地 PDF](<2024 - GenNBV - Generalizable Next-Best-View Policy for Active 3D Reconstruction.pdf>)（10 页）。 引用键：`chen2024`。

**主类与标签：** C．通用主动重建与视角规划；GenNBV；PPO；连续五维动作；占据图；跨域泛化。

- **研究问题：** 如何让 NBV 策略在未知物体和跨场景数据上泛化，并允许相机在自由空间中移动而非局限在固定候选半球。
- **创新点与贡献：** 将几何占据、图像语义和历史动作融合为策略状态，学习连续位置加 yaw/pitch 的五维视角动作；借助并行仿真训练，增强对未见对象和不同数据域的适应性。
- **方法：** 用深度射线更新未知/自由/占据空间的概率网格，提取灰度图像历史特征与动作嵌入，输入随机策略网络；通过 Isaac Gym 并行环境和 PPO 学习。奖励为相邻时刻真实表面覆盖率增量，并对碰撞及过多关键帧施加惩罚。
- **验证与边界：** 用 Houses3K 训练，在未见 Houses3K、OmniObject3D、Objaverse 和 Replica 等数据上评估覆盖和泛化。其覆盖分母来自训练/测试模型的真实占据体素，碰撞惩罚不等于严格安全约束；这里的五维自由动作、RGB-D 成像和覆盖奖励也不能直接代表小天体 SPC 任务。
- **原文定位：** PDF 第 3–5 页 §3 状态、动作和奖励，第 6–8 页实验；第 5 页可直接核查覆盖奖励定义。

<a id="p27"></a>

#### P27．Integrating One-Shot View Planning with a Single Next-Best View via Long-Tail Multiview Sampling

**文献信息：** Pan 等，2025，IEEE Transactions on Robotics 41:394–414。[发表/来源入口](https://doi.org/10.1109/TRO.2024.3507993)；[本地 PDF](<2025 - Integrating One-Shot View Planning with a Single Next-Best View via Long-Tail Multiview Sampling.pdf>)（21 页）。 引用键：`pan2025`。

**主类与标签：** C．通用主动重建与视角规划；MA-SCVP；单次 NBV；一次性规划；长尾采样；集合覆盖。

- **研究问题：** 仅凭初始部分观测直接预测整个视角集合容易受信息不足影响，而逐次 NBV 又会增加移动成本；怎样结合两者并改善训练数据在重建早期阶段的代表性。
- **创新点与贡献：** 提出先执行一个有信息量的 NBV，再一次性预测剩余视角的 MA-SCVP；设计长尾多视角采样，加强少量初始观测阶段的训练，减轻均匀采样中过多“接近完整重建”样本造成的偏差。
- **方法：** 以 PC-NBV 选择额外观测，将更新后的体素/视角状态送入集合预测网络；从虚拟扫描形成多视角部分观测，按覆盖变化构造长尾采样。对剩余可见表面求最小集合覆盖标签，训练多标签视角预测；规划选中视角的访问路径并使用局部避障。
- **验证与边界：** 在仿真和真实机器人实验中比较重建完整性、视角数与移动，报告相应设置下约 45% 的移动减少。依赖固定离散候选视角，覆盖对象是这些视角可见表面的并集，底部等不可见区域不在同一保证中。本地稿于 2024 年接受，正式卷年为 2025，文件已据此改名。
- **原文定位：** PDF 第 4–10 页 §III–IV 方法（第 7–8 页长尾采样），第 11–17 页实验，第 17–18 页候选空间等补充说明。

<a id="category-d"></a>

### D．小天体自主成像与观测规划

面向小天体的拍摄时机、SPC 约束、鲁棒观测组合和载荷计划生成。

<a id="p07"></a>

#### P07．Autonomous Imaging and Mapping of Small Bodies Using Deep Reinforcement Learning

**文献信息：** Chan、Agha-Mohammadi，2019，IEEE Aerospace Conference:1–12。[发表/来源入口](https://doi.org/10.1109/AERO.2019.8742147)；[本地 PDF](<2019 - Autonomous Imaging and Mapping of Small Bodies Using Deep Reinforcement Learning.pdf>)（12 页）。

**主类与标签：** D．小天体自主成像与观测规划；POMDP；REINFORCE；轨道动作；拍摄/下传；OSIM。

- **研究问题：** 在未知形状和有限资源条件下，探测器如何同时决定轨道动作、成像与数据下传，以获取适合建图的图像并控制距离和推进使用。
- **创新点与贡献：** 把小天体主动建图扩展为含动力学、相机存储和通信状态的 POMDP；相较仅规划拍摄时机，更明确地纳入六轴推力、成像和下传动作，并开发高吞吐 OSIM 仿真环境支撑训练。
- **方法：** 状态包含相对运动、目标旋转、地图几何及相机/通信信息，动作由六轴推力开关、拍摄和下传组成；奖励覆盖、emission/太阳方位多样性及合适 incidence，同时惩罚推进和超出距离范围。用 REINFORCE 与两层全连接策略网络学习，C++/OpenGL 仿真通过 Python 接口提供训练交互。
- **验证与边界：** 在 Mithra、Toutatis 模型上与随机动作和固定/随机轨道方案比较，并讨论复杂约束和策略迁移。奖励中的映射质量是 SPC 几何代理，推力惩罚也未等同完整燃料状态；仿真成功尚不构成严格飞行安全或真实高程精度保证。与 2020/2022 年仅选拍摄时机的研究分别保留。
- **原文定位：** PDF 第 3–5 页 §3 POMDP，第 5–6 页 §4 OSIM/训练，第 7–9 页实验与集成讨论，第 10 页总结。

<a id="p10"></a>

#### P10．Deep Reinforcement Learning approach for Small Bodies Shape Reconstruction Enhancement

**文献信息：** Piccinin、Lavagna，2020，AIAA SciTech，paper 2020-1909。[发表/来源入口](https://doi.org/10.2514/6.2020-1909)；[本地 PDF](<2020 - Deep Reinforcement Learning approach for Small Bodies Shape Reconstruction Enhancement.pdf>)（18 页）。

**主类与标签：** D．小天体自主成像与观测规划；DQN；固定飞掠；二值拍摄；合成影像；点云检验。

- **研究问题：** 给定小天体飞掠轨迹和固定目标指向时，怎样在存储和图像数量约束下选取更有价值的成像时刻，以及几何评分改善能否转化成实际点云收益。
- **创新点与贡献：** 采用 DQN 学习拍摄/不拍摄策略，并以真实图像处理步骤验证策略选择的图像，而不仅停留在覆盖评分；用有限统计状态压缩高维地图与观测历史。
- **方法：** 将存储进度、局部/全局地图质量、光照和历史角度信息压缩为 12 个统计状态，动作仅为二值曝光；用与 SPC 几何及观测次数有关的映射指数训练 DQN。在 67P 固定双曲飞掠上，用 POV-Ray 生成图像，提取匹配特征并按已知相对位姿三角化，与均匀时序比较。
- **验证与边界：** 示例中 DRL 采集 33 张图像，目标约 30 张；剔除离群后得到 938 个三角化点，均匀方案为 162 个。结果支持改善可匹配稀疏点云，但不等于完整 SPC 地形误差下降，亦不含自由轨道/姿态控制。是独立会议论文，保留以体现后续 2022 年工作的演进。
- **原文定位：** PDF 第 7–14 页 §IV–V 问题与学习，第 14–16 页 §VI 图像处理检验，第 16 页总结。

<a id="p14"></a>

#### P14．Deep Reinforcement Learning-based policy for autonomous imaging planning of small celestial bodies mapping

**文献信息：** Piccinin、Lunghi、Lavagna，2022，Aerospace Science and Technology 120:107224。[发表/来源入口](https://doi.org/10.1016/j.ast.2021.107224)；[本地 PDF](<2022 - Deep Reinforcement Learning-based policy for autonomous imaging planning of small celestial bodies mapping.pdf>)（12 页）。 引用键：`piccinin2022`。

**主类与标签：** D．小天体自主成像与观测规划；NFQ/DQN；POMDP；SPC 几何评分；存储约束；跨目标泛化。

- **研究问题：** 给定相对运动和相机指向时，如何在周期性存储/下传限制内自主决定是否拍照，并使成像时机策略对天体形状、轨道、旋转及导航误差具有适应能力。
- **创新点与贡献：** 构建面向 SPC 的资源感知拍摄策略，比较 NFQ 与 DQN，并系统检验跨目标、几何变化和状态不确定性的泛化；用压缩状态降低决策网络规模。
- **方法：** 使用 12 个统计状态概括存储进度、图像数、可见/光照情况、局部和全局映射质量及历史 incidence/emission/方位变化；动作只有拍摄或不拍摄，不控制相对位姿。把各面图像数量与几何质量组合为映射指数，以归一化增量奖励有效拍摄、惩罚全阴影或超额成像；训练标量 Q 网络并周期性清空存储。
- **验证与边界：** 在 Eros 训练，在 Eros、Itokawa、Bennu、67P 及不同视场、轨道倾角、距离、自转和导航误差下评估映射评分、图像使用和计算开销。评分不是实测 SPC 高程误差，泛化也限于所测设置。本条保留正式期刊版；与同题作者稿按同一论文合并，原非标准文件名中的 ICARUS 为误标。
- **原文定位：** PDF 第 3–6 页 §3–4 状态、评分和学习，第 7–11 页 §5–6 实验与总结。

<a id="p30"></a>

#### P30．Observation Planning Methods Under Modeling Constraints of Small Celestial Bodies

中文题名：小天体建模约束条件下的观测规划方法研究。

**文献信息：** 王睿、郭良库、赵巍、刘鹏，2025，空间控制技术与应用 51(5):38–47。[发表/来源入口](https://doi.org/10.3969/j.issn.1674-1579.2025.05.004)；[本地 PDF](<2025 - Observation Planning Methods Under Modeling Constraints of Small Celestial Bodies.pdf>)（10 页）。 引用键：`wang2025`。

**主类与标签：** D．小天体自主成像与观测规划；SPC 约束；遗传算法；爬山法；鲁棒规划；对偶采样。

- **研究问题：** 已有远距离粗形状时，如何选择近距离拍摄位置和时刻，使更多表面满足 SPC 观测条件，同时减少拍摄位置/动作，并抵抗探测器位置和指向扰动。
- **创新点与贡献：** 将位置选择与每个位置的拍摄动作联合编码，以 SPC 有效面覆盖定义收益；用遗传算法加局部爬山改进组合，进一步把扰动仿真和降低采样方差的对偶变量采样纳入鲁棒评价。
- **方法：** 在固定高度的离散半球位置集上，以 P×A 二值矩阵表示位置/时刻动作；由粗三角网、自转和太阳/相机几何判断有效观测。采用入射角 10°–75°、发射角 25°–50°、相位角 30°–75°及每面至少 10 次有效成像等条件；适应度权衡位置数、动作数和覆盖下限。经选择、交叉、变异后，在邻近位置爬山，再以含位姿扰动的采样评估鲁棒性。
- **验证与边界：** 在小天体模型和多次扰动试验中比较普通/鲁棒方案，目标覆盖下限为 90%。位置数和动作数作为成本代理，尚未直接优化真实燃料消耗或完整下传动力学；有效三角面数量也尚未经实际 SPC 重建误差闭环验证。是本库与小天体 SPC 观测组合最直接相关的规划研究之一。
- **原文定位：** PDF 第 2–4 页 §1 编码、约束和遗传/爬山法，第 4–6 页 §2 扰动与鲁棒采样，第 7–8 页试验。

<a id="p38"></a>

#### P38．SB-ObsGen - A Framework for Flyby Small Body Observation Plan Generation Using LLMs and Physics-Informed Tools

**文献信息：** Li 等，2026，Aerospace 13(5):474。[发表/来源入口](https://doi.org/10.3390/aerospace13050474)；[本地 PDF](<2026 - SB-ObsGen - A Framework for Flyby Small Body Observation Plan Generation Using LLMs and Physics-Informed Tools.pdf>)（32 页）。 引用键：`sbobsgen2026`。

**主类与标签：** D．小天体自主成像与观测规划；SB-ObsGen；LLM；物理工具；飞掠；计划校验；多载荷。

- **研究问题：** 如何把小天体机会飞掠的科学目标、异构载荷规则和任务约束自动转为完整观测计划，并降低 LLM 生成内容在物理与资源条件上失效的概率。
- **创新点与贡献：** 提出 Generate + Optimize 框架，结合语言模型的目标解析/结构化生成与确定性物理工具，分层验证并把失败原因反馈给模型迭代修订。
- **方法：** 通过目标数据检索和轨道传播，计算距离、相位角和太阳避让窗口并求交集；以约定结构生成观测、姿态和时间线。先检查基本字段、时间窗和科学持续时间，再核查姿态冲突、动作遗漏、功率/时长及观测角，最后合并相邻载荷活动和减少姿态切换，返回结构化问题供再次优化。
- **验证与边界：** 在 80 个场景上比较多个模型及经典方案，进行模块消融，最佳配置与参考计划的一致性超过 85%。该数值是计划/参考一致性，不能解释为飞行成功率或表面重建精度；框架主要处理载荷活动排程，尚未直接优化局部 SPC 模型误差。
- **原文定位：** PDF 第 7–14 页 §3 框架与分层校验，第 15–25 页 §4 实验，第 26–27 页讨论与结论。

<a id="category-e"></a>

### E．任务设计与科学运行

Rosetta、Psyche、Hera、Lucy 的任务架构、观测时序、仿真和地面运行。

<a id="p01"></a>

#### P01．The Rosetta Mission - Flying Towards the Origin of the Solar System

**文献信息：** Glassmeier 等，2007，Space Science Reviews 128:1–21。[发表/来源入口](https://doi.org/10.1007/s11214-006-9140-8)；[本地 PDF](<2007 - The Rosetta Mission - Flying Towards the Origin of the Solar System.pdf>)（21 页）。 引用键：`glassmeier2007rosetta`。

**主类与标签：** E．任务设计与科学运行；Rosetta；任务架构；彗星伴飞；Philae。

- **研究问题：** 如何通过近距离、长时间的彗星观测和原位测量，研究太阳系原始物质、彗核组成及接近日照时的活动演化；怎样把这些科学目标落实为一次可执行的深空任务。
- **创新点与贡献：** 给出轨道器长期伴飞与 Philae 着陆器协同工作的总体架构，将彗核、尘埃、气体和等离子体测量组合成完整科学方案。价值在于任务设计与科学需求的系统说明，而非提出新的形状重建或优化算法。
- **方法：** 从科学问题推导载荷和观测项目，介绍轨道器与着陆器的实验分工；通过行星重力辅助、巡航休眠、低光照太阳能供电和彗星交会后的分阶段运行组织任务，同时安排小行星飞掠观测。
- **验证与边界：** 论文是任务实施前的设计说明，展示工程与科学方案的可行性和预期成果。文中的时间表、目标参数及预期测量能力应按 2007 年方案理解，不能当作后续飞行结果。适合作为小天体任务背景和长期观测需求的依据。
- **原文定位：** PDF 第 3–8 页任务与轨道器设计，第 9–16 页着陆器及目标，第 19–20 页科学目标与总结。

<a id="p05"></a>

#### P05．The Rosetta mission orbiter science overview - the comet phase

**文献信息：** Taylor 等，2017，Philosophical Transactions of the Royal Society A 375:20160262。[发表/来源入口](https://doi.org/10.1098/rsta.2016.0262)；[本地 PDF](<2017 - The Rosetta mission orbiter science overview - the comet phase.pdf>)（16 页）。 引用键：`taylor2017rosetta`。

**主类与标签：** E．任务设计与科学运行；Rosetta；彗星科学；任务阶段；多载荷。

- **研究问题：** Rosetta 彗星阶段的运行如何支撑各类科学观测，以及长期伴飞给彗核、彗发、尘埃、气体和等离子体研究带来了哪些整体认识。
- **创新点与贡献：** 把轨道器科学成果与接近、测绘、着陆支持、近日点伴飞、延长任务和末期下降联系起来，提供跨载荷、跨阶段的任务科学综述。贡献是成果和运行经验的整合，不是新的导航估计器。
- **方法：** 按任务时间线梳理观测阶段和关键操作，再按彗核性质、气体与尘埃组成、活动机制及等离子体环境归纳多载荷研究；结合轨道距离、季节变化和任务运行约束解释数据取得的背景。
- **验证与边界：** 总结真实 Rosetta 数据揭示的复杂形状、组成与活动演化，并讨论仍待解决的问题。属于综述性证据，具体形状精度、仪器误差或局部地质结论应追溯其引用的原始研究；本地文件为作者预印本，书目信息采用正式期刊版本。
- **原文定位：** PDF 第 2–8 页任务过程与主要科学成果，第 8 页起结论及后续问题。

<a id="p15"></a>

#### P15．Operations for Autonomous Spacecraft

**文献信息：** Castano 等，2022，IEEE Aerospace Conference:1–20。[发表/来源入口](https://doi.org/10.1109/AERO53065.2022.9843352)；[本地 PDF](<2022 - Operations for Autonomous Spacecraft.pdf>)（21 页）。 引用键：`castano2022`。

**主类与标签：** E．任务设计与科学运行；自主航天器；地面运行；意图表达；可解释性；用户研究。

- **研究问题：** 当星上系统能够自主决定观测活动，而地面存在长时延和有限遥测时，操作员怎样表达科学意图、预测可能结果并理解实际执行行为。
- **创新点与贡献：** 把自主能力对应的地面运行问题具体化，提出目标与约束表达、候选结果预览、遥测解释等工具和工作流，并通过操作员参与的用户研究评估其价值。重点是人机协同与运行设计。
- **方法：** 以假想海王星/海卫一飞掠任务为场景，将科学目标转成星上可理解的任务和约束；提供规划与仿真界面查看多个可能执行结果，依据有限遥测重建自主状态和决策原因，再开展用户操作与反馈评估。
- **验证与边界：** 给出原型工具和用户研究所揭示的有效交互及改进需求。场景与研究并非自主系统的实际深空飞行验证，也未提出专门的 NBV 或 SPC 误差优化算法；可用于设计观测规划系统的计划检查、解释和人工监督接口。
- **原文定位：** PDF 第 2–13 页 §2–5 场景、工具与工作流，第 14–16 页 §6 用户研究。

<a id="p26"></a>

#### P26．Hera CubeSats Mission Planning and Payloads Operations Concept for Didymos Binary Asteroid Characterization

**文献信息：** Annat 等，2025，18th SpaceOps，paper 523。[发表/来源入口](https://publications.spaceops.org/2025/download_by_id.php?id=0523)；[本地 PDF](<2025 - Hera CubeSats Mission Planning and Payloads Operations Concept for Didymos Binary Asteroid Characterization.pdf>)（20 页）。

**主类与标签：** E．任务设计与科学运行；Hera；Juventas；Milani；双小行星；载荷运行；分级计划。

- **研究问题：** Hera 携带的两颗 CubeSat 在未知形状、弱引力和太阳辐射压显著的双小行星附近，如何兼顾安全轨迹、雷达/光谱观测与地面和母船的运行约束。
- **创新点与贡献：** 给出 Juventas 与 Milani 的完整载荷运行概念，连接分离、试运行、远近距离观测和末期处置；阐明从长期到极短期计划逐级细化及多方协作的机制。
- **方法：** 将 Juventas 的 JuRa 雷达需求映射到自稳定晨昏轨道和着陆阶段，将 Milani ASPECT 光谱要求映射到不同距离和相位角的飞掠观测；在规划中考虑姿态、功率、通信/星间链路、机动和观测时间，并分层更新运行计划。
- **验证与边界：** 展示任务基线与规划职责分工，强调抵达后根据目标知识修订计划的必要性。论文为 2025 年任务设计，不是已完成的近距离飞行成果；也未给出可直接复用的全局视角优化算法。适合提取多载荷、母船/子星协同的现实约束。
- **原文定位：** PDF 第 5–14 页 §3–4 任务阶段和载荷运行，第 15–19 页 §5 规划机制。

<a id="p28"></a>

#### P28．Lucy's Donaldjohanson Encounter Science Planning and Sequencing

**文献信息：** Birath 等，2025，18th SpaceOps，paper 533。[发表/来源入口](https://publications.spaceops.org/2025/download_by_id.php?id=0533)；[本地 PDF](<2025 - Lucy's Donaldjohanson Encounter Science Planning and Sequencing.pdf>)（9 页）。

**主类与标签：** E．任务设计与科学运行；Lucy；Donaldjohanson；科学序列；TPFG；约束检查。

- **研究问题：** 如何把 Lucy 对 Donaldjohanson 的短时飞掠科学需求，转成跨仪器、可检查并可上传执行的观测序列，同时为后续 Trojan 飞掠演练运行链。
- **创新点与贡献：** 介绍由科学团队和运行团队共同维护的计划生成与审核流程，配套网页时间线、仪器约束检查和图像清单审计，减少复杂序列的人工核对负担。
- **方法：** 从测量技术和科学活动计划出发，通过 TPFG 生成载荷时间线，组织科学操作中心与任务运行方之间的审查和交接；结合约束检查器、STK 可视化、SESS 仿真和测试指令负载检查可见性、执行时间及仪器活动。
- **验证与边界：** 论文展示接近飞掠时的规划与测试实践，属于科学序列工程流程。虽发表于 2025 年会议，其主要叙述形成于当年 4 月飞掠之前，不能把预期观测直接当作飞掠后的实测结果；可支持观测计划如何走向可执行指令的讨论。
- **原文定位：** PDF 第 3–8 页 §4–7 科学计划、工具、检查及序列实施。

<a id="p29"></a>

#### P29．Lucy's Encounter with Dinkinesh

**文献信息：** Keeney 等，2025，18th SpaceOps，paper 540。[发表/来源入口](https://publications.spaceops.org/2025/download_by_id.php?id=0540)；[本地 PDF](<2025 - Lucy's Encounter with Dinkinesh.pdf>)（4 页）。

**主类与标签：** E．任务设计与科学运行；Lucy；Dinkinesh；终端跟踪；真实飞掠；数据链。

- **研究问题：** 临时加入的 Dinkinesh 飞掠，怎样在有限准备时间内检验 Lucy 的目标跟踪、仪器观测和数据处理，为主要 Trojan 飞掠降低运行风险。
- **创新点与贡献：** 报告一次真实飞掠对从计划、上传、终端跟踪到数据下载和归档的端到端验证，并总结临时目标带来的流程经验；同时记录意外发现的 Selam 接触双体。
- **方法：** 利用现有任务架构快速制定飞掠活动和仪器配置，实施终端目标跟踪及成像/光谱采集，随后完成下传、标定、分析与 PDS 归档，检查指向、观测执行和科学数据质量。
- **验证与边界：** 基于 2023 年 11 月 1 日实际飞掠，表明系统能够完成计划并揭示此前未知的目标结构。贡献是运行验证和科学发现，既不是新的形状重建求解器，也不能仅凭一次成功飞掠推导任意目标下的观测精度保证。
- **原文定位：** PDF 第 1–3 页 §2–5 规划、执行、数据处理及经验。

<a id="p31"></a>

#### P31．Psyche Mission Description and Design Rationale

**文献信息：** Polanskey 等，2025，Space Science Reviews 221:95。[发表/来源入口](https://doi.org/10.1007/s11214-025-01218-x)；[本地 PDF](<2025 - Psyche Mission Description and Design Rationale.pdf>)（82 页）。 引用键：`polanskey2025`。

**主类与标签：** E．任务设计与科学运行；Psyche；测绘轨道；SPG/SPC；未知目标；运行与资源。

- **研究问题：** Psyche 的形状、引力和自转环境尚不完全确定时，怎样设计巡航、科学轨道及观测运行，满足地形、磁场、元素与引力测量需求。
- **创新点与贡献：** 说明从科学需求到多高度轨道、载荷运行及数据系统的设计逻辑；利用分阶段且可调整的轨道/观测顺序适应未知目标和季节光照，并明确测绘几何与资源之间的折中。
- **方法：** 构建 A/B/C/D 不同高度的科学轨道阶段，并可将 B 分为 B1/B2 调整观测季节；联合成像、磁力计、伽马/中子和引力需求安排姿态与时间。地形成像采用两组各四个方向的固定离轴姿态，以 CKVIEW 按表面位置统计满足条件的图像；结合供电、存储、下传和运行周期审查方案。
- **验证与边界：** 给出可追溯的需求、设计和预期覆盖，解释为何需要冗余和分阶段观测。八个固定姿态不等于对每轮模型误差自适应优化；图像数和几何满足性也不等于已验证的实际高程精度。本文为 2025 年设计文献，科学轨道结果仍属预期。
- **原文定位：** PDF 第 20–28 页 §3 科学需求，第 30–52 页 §4 任务设计（第 40–41 页成像姿态/几何检查），第 53–69 页运行，第 70–75 页数据系统。

<a id="p33"></a>

#### P33．Simulating Lucy's Flybys of Its Target Trojan Asteroids

**文献信息：** Salmon、Kaufmann、Levison，2025，18th SpaceOps，paper 549。[发表/来源入口](https://publications.spaceops.org/2025/download_by_id.php?id=0549)；[本地 PDF](<2025 - Simulating Lucy's Flybys of Its Target Trojan Asteroids.pdf>)（6 页）。 引用键：`salmon2025`。

**主类与标签：** E．任务设计与科学运行；Lucy；SESS；SPICE；指令回放；Monte Carlo；覆盖风险。

- **研究问题：** Lucy 飞掠只有短暂观测窗口且目标知识存在误差时，如何检查一套指令序列能否达到表面覆盖与分辨率要求，并量化指向或触发时刻错误的风险。
- **创新点与贡献：** 构建 SESS 仿真工具，在指令级回放中区别真实轨迹与探测器所知星历，联系终端跟踪、基于距离触发的活动及累计表面质量；用 Monte Carlo 评估计划对不确定性的稳健性。
- **方法：** Python 工具通过 SPICE 回放航天器、平台和仪器指向及 L’Ralph 扫描镜，使用椭球或 DSK 表面进行可见性/光照计算，结合投影、曲率、抖动和拖影估算分辨率。累计每个表面单元的最佳分辨率；随机扰动目标形状、自转、交会和知识星历等，重复模拟（示例 1000 次）。
- **验证与边界：** 展示计划满足覆盖要求的统计情况及知识误差导致的漏拍/错时风险。SESS 是计划验证器而非自动 NBV 生成器；基于近似形状的预测地图不等于实际 SPC 地形精度，但其“真值/知识分开”的设计很适合检验观测规划的执行鲁棒性。
- **原文定位：** PDF 第 3–4 页 §2 仿真，第 5 页 §3 Monte Carlo，第 6 页总结。

<a id="category-f"></a>

### F．自主光学导航与着陆轨迹

联合建图导航、地标匹配、抗扰着陆和导航观测驱动的轨迹设计。

<a id="p06"></a>

#### P06．Autonomous Small Body Mapping and Spacecraft Navigation Via Real-Time SPC-SLAM

**文献信息：** Baldini、Harvard、Chung、Nesnas、Bhaskaran，2018，69th IAC，IAC-18.C1.6.11。[发表/来源入口](https://authors.library.caltech.edu/records/2v2h8-jda31)；[本地 PDF](<2018 - Autonomous Small Body Mapping and Spacecraft Navigation Via Real-Time SPC-SLAM.pdf>)（11 页）。 引用键：`baldini2018`。

**主类与标签：** F．自主光学导航与着陆轨迹；SPC-SLAM；SfM；联合估计；尺度恢复。

- **研究问题：** 探测器如何利用连续图像，在小天体形状和旋转状态未知时联合建图、估计相对运动，并将视觉结果恢复到可用于导航的物理尺度。
- **创新点与贡献：** 提出 SPC-SLAM 自主建图导航框架，把图像几何、天体旋转、尺度和质心轨迹估计放在同一处理链中。正文的主要验证围绕特征重建与优化展开，标题中的实时 SPC-SLAM 代表总体框架和发展方向。
- **方法：** 先提取和匹配多视图特征，以 SfM 恢复相机运动和尺度不定的表面；从相机相对旋转推断天体旋转，再结合已知/测得的探测器轨迹，通过优化恢复度量尺度和天体质心运动。
- **验证与边界：** 使用仿 Rosetta 几何的 67P 合成图像及噪声试验评估形状和状态估计。验证依赖探测器位置/轨迹信息，其来源可为地面跟踪等；论文将进一步实时化和减少地面依赖列为后续工作，尚不能据此认定完整系统已经实现无地面支持的星上闭环运行。
- **原文定位：** PDF 第 5–7 页 §3 方法，第 8–10 页 §4 仿真结果，第 10 页结论。

<a id="p24"></a>

#### P24．A Desensitized Trajectory Optimization Method for Landing of Small Bodies

中文题名：小天体着陆抗扰轨迹优化方法。

**文献信息：** 朱轩廷、刘延杰、彭菲，2025，深空探测学报 12(1):31–38。[发表/来源入口](https://doi.org/10.15982/j.issn.2096-9287.2025.20240026)；[本地 PDF](<2025 - A Desensitized Trajectory Optimization Method for Landing of Small Bodies.pdf>)（9 页）。

**主类与标签：** F．自主光学导航与着陆轨迹；小天体着陆；抗扰优化；协方差传播；高斯伪谱法。

- **研究问题：** 小天体重力、自转、推力和初始状态不确定时，如何在燃料消耗与着陆末端位置/速度分散之间设计折中轨迹。
- **创新点与贡献：** 把状态误差的线性协方差传播纳入轨迹优化，将末端状态方差作为抗扰目标，从而在设计阶段降低对不确定参数的敏感性。
- **方法：** 建立名义动力学和协方差传播方程，将协方差独立分量增广为优化状态；以推进剂消耗和终端位置/速度方差的加权组合作为目标，施加终端位置、零速度、推力及质量约束；用高斯伪谱离散和 GPOPS-II/SNOPT 求解，再进行随机误差仿真。
- **验证与边界：** 以 433 Eros 着陆为例，与燃料最优方案比较，考察开环和带反馈时的末端误差与燃料代价。抗扰收益需要额外燃料，依赖线性误差传播和给定误差模型；此处优化的是轨迹执行不确定性，并未显式以图像地标可观性或导航估计信息量为目标。
- **原文定位：** PDF 第 3–5 页 §1–2 动力学与抗扰求解，第 6–8 页数值结果。

<a id="p36"></a>

#### P36．Surface Reconstruction Techniques for Asteroid Missions and the Applications in Autonomous Optical Navigation

中文题名：小天体表面重建技术及在自主光学导航中的应用。

**文献信息：** 田启航、刘一武、王立等，2025，中国空间科学技术 45(5):75–90。[发表/来源入口](https://doi.org/10.16708/j.cnki.1000-758X.2025.0098)；[本地 PDF](<2025 - Surface Reconstruction Techniques for Asteroid Missions and the Applications in Autonomous Optical Navigation.pdf>)（16 页）。

**主类与标签：** F．自主光学导航与着陆轨迹；SfM/SPC；地标库；ICQ；频域掩膜 NCC；星上导航。

- **研究问题：** 怎样将地面表面重建产品压缩并转化为可上传的导航先验，让星上有限算力下的图像匹配形成可靠的相对视线测量。
- **创新点与贡献：** 串联 SfM 全局形状/自转恢复、SPC 局部地图和自主光学导航；用 ICQ 表示降低模型上传量，以频域掩膜 NCC 加快局部图像相关匹配。
- **方法：** 地面估计形状、自转与局部 maplets 并建立地标库；远距离阶段用紧凑 ICQ 全局模型按预测几何渲染，与实拍图像相关求中心视线。接近后按预计飞行高度挑选合适地图，渲染局部地标，用 FFT 实现带有效区域掩膜的归一化互相关，再将偏移转成导航测量。
- **验证与边界：** 使用 Bennu 实测影像、外场沙盘和仿真数据验证；报告 ICQ 数据量约为传统网格的 20%、视线精度约目标像素直径的 3%，频域匹配约十倍加速（均针对文中设置）。地面模型和上传先验仍是处理链组成，不能视为完整星上自主 SPC 更新。
- **原文定位：** PDF 第 3–7 页 §1–3 重建与导航，第 8–14 页 §4 实验，第 14–15 页总结。

<a id="p37"></a>

#### P37．A Navigation Observation-Driven Trajectory Planning Method for Asteroid Landing

中文题名：导航观测驱动的小行星着陆轨迹规划方法。

**文献信息：** 沈心怡、葛丹桐、梁子璇、朱圣英，2026，深空探测学报 13(1):50–57。[发表/来源入口](https://doi.org/10.3724/j.issn.2096-9287.2025.20250049)；[本地 PDF](<2026 - A Navigation Observation-Driven Trajectory Planning Method for Asteroid Landing.pdf>)（9 页）。

**主类与标签：** F．自主光学导航与着陆轨迹；着陆轨迹；导航地标；K-means；Bezier；观测/燃料折中。

- **研究问题：** 表面可用导航特征分布不均时，怎样让着陆轨迹经过更利于光学观测的区域，而不是只满足动力学和燃料最优。
- **创新点与贡献：** 把已知地标分布引入着陆轨迹设计，通过聚类和曲线路点生成，将“更多导航观测”转成可由轨迹优化实现的空间约束。
- **方法：** 对表面特征进行 K-means 聚类并用肘部法选择数量；参考初始能量最优轨迹的平面投影，选择特征较集中的方向，用起点、聚类中心和终点构造 Bezier 曲线并采样路点；在 Eros 多面体引力模型中求带路点、着陆位置和零末速约束的三维最优轨迹。
- **验证与边界：** 比较单/多路点方案的可观测特征数与推进剂质量分数，表明增加观测需要燃料折中。可观测特征数量是导航收益代理，未等同于滤波协方差或实测定位误差；方法依赖预先已知的地标，适用于利用地图导航而非发现未知表面的完整主动重建。
- **原文定位：** PDF 第 3–5 页 §2 规划（第 4–5 页聚类与路点），第 5–7 页 §3 仿真。

<a id="category-g"></a>

### G．任务级轨迹与协同探测

任务分配和转移轨迹综述，以及侦察、交会、撞击偏转与伴随观测。

<a id="p32"></a>

#### P32．Research Progress on Trajectory Optimization of Space Target Cooperative Detection

中文题名：空间目标协同探测轨迹优化研究进展。

**文献信息：** 张众、宝音贺西、李俊峰，2025，深空探测学报 12(1):3–14。[发表/来源入口](https://doi.org/10.15982/j.issn.2096-9287.2025.20240041)；[本地 PDF](<2025 - Research Progress on Trajectory Optimization of Space Target Cooperative Detection.pdf>)（13 页）。

**主类与标签：** G．任务级轨迹与协同探测；协同探测；轨迹优化综述；最优控制；任务分配；机器学习。

- **研究问题：** 多航天器对多个空间目标开展探测时，怎样同时处理目标分配、访问顺序、时间、轨迹和控制，以及不同优化技术适用于哪些问题层级。
- **创新点与贡献：** 提供协同探测轨迹优化的方法分类和应用梳理，连接组合任务规划与连续轨迹控制；总结高维全局优化、自主设计和实时求解的挑战。其贡献属于综述和问题组织。
- **方法：** 从最优控制的直接/间接法、遗传/差分进化/蚁群等智能优化、树搜索及机器学习辅助方法归纳研究；区分离散目标和序列、连续转移时刻与状态、末层控制变量，并以空间碎片、对地观测、小天体探测和在轨服务等场景比较。
- **验证与边界：** 论文汇总已有研究，没有提供新的统一求解器或独立性能基准。机器学习可用于代价预测、初值或策略，但代理误差和动力学可行性仍需检查。适合作为任务级协同优化的文献入口，不能直接代替局部表面重建收益模型。
- **原文定位：** PDF 第 3–9 页 §1–4 方法与场景，第 10 页展望和结论。

<a id="p34"></a>

#### P34．Space Mission Options for Reconnaissance and Mitigation of Asteroid 2024 YR4

**文献信息：** Barbee 等，2025，arXiv:2509.12351v1。[发表/来源入口](https://arxiv.org/abs/2509.12351)；[本地 PDF](<2025 - Space Mission Options for Reconnaissance and Mitigation of Asteroid 2024 YR4.pdf>)（45 页）。

**主类与标签：** G．任务级轨迹与协同探测；2024 YR4；任务机会；侦察；飞掠/交会；任务权衡。

- **研究问题：** 在论文所采用的 2024 YR4 轨道和物理知识条件下，哪些任务机会可用于快速侦察、精化目标参数或缓解潜在威胁，时间和推进能力如何限制这些选择。
- **创新点与贡献：** 将侦察与缓解任务放在同一机会分析中，比较新研航天器和现有航天器改任务、飞掠和交会、不同推进与转移路径的时效及能力边界。
- **方法：** 基于当时星历和目标参数开展任务机会搜索，比较发射能力、化学/太阳电推进、深空机动与重力辅助；按飞行时间、C3、速度增量、到达质量和可观测性分析不同任务及任务组合的可行性。
- **验证与边界：** 给出特定假设下的发射/到达窗口和任务权衡。可行性依赖当时轨道、尺寸/质量和工程能力假设，不能当作目标最新风险通报；本文也没有求解精细表面观测顺序或 SPC 误差优化。涉及缓解措施的结论应理解为该论文的任务层级分析。
- **原文定位：** PDF 第 17–36 页 §3 任务方案，第 37–41 页 §4–5 讨论与结论。

<a id="p39"></a>

#### P39．Trajectory Optimization for Asteroid Kinetic Impact and Proximity Observation Under Orbital Deflection Constraints

中文题名：考虑轨道偏转约束的小行星动能撞击与近距离探测轨迹优化。

**文献信息：** 宋昱岐、黄兴宏、李海洋等，2026，深空探测学报 13(3):261–275。[发表/来源入口](https://doi.org/10.3724/j.issn.2096-9287.2026.20250122)；[本地 PDF](<2026 - Trajectory Optimization for Asteroid Kinetic Impact and Proximity Observation Under Orbital Deflection Constraints.pdf>)（16 页）。

**主类与标签：** G．任务级轨迹与协同探测；2024 YR4；撞击偏转；伴随观测；窗口筛选；引力辅助。

- **研究问题：** 怎样把轨道偏转效果与近距离观测条件同时用于撞击和探测任务的窗口筛选、发射/交会机会及转移轨迹设计。
- **创新点与贡献：** 将不同撞击几何的偏转效果映射与观测相位约束结合，连接目标轨道传播、任务窗口和撞击器/观测器的转移机会，形成协同任务分析链。
- **方法：** 采用高精度多体轨道传播及初始误差试验，在速度–法向–副法向坐标中分析速度增量方向/大小和撞击时间对偏转距离的影响；结合太阳–目标–探测器几何筛选有效窗口，再搜索直接及含一次到多次重力辅助的撞击、飞掠和交会转移轨迹。
- **验证与边界：** 以论文采用的 2024 YR4 参数展示满足偏转和观测要求的窗口及任务权衡。结论依赖星历、质量和动量传递假设，目标风险应按最新数据另行核验；观测约束主要是任务窗口/几何层级，尚未涉及逐区域拍摄序列或 SPC 精度闭环。
- **原文定位：** PDF 第 3–4 页 §1 轨道传播，第 5–11 页 §2 偏转与窗口，第 12–14 页 §3 轨迹和总结。

## 全文待补文献（5 篇）

以下沿用既有书目信息，仅根据题名标记相关主题。当前目录没有对应 PDF，因此不提供经过全文核查的创新点、方法细节或实验结论，也不计入上述分类数量。

| 年份 | 文献与来源 | 发表信息 | 相关主题 | BibTeX 键 |
| --- | --- | --- | --- | --- |
| 2016 | [The global shape, density and rotation of Comet 67P/Churyumov-Gerasimenko from preperihelion Rosetta/OSIRIS observations](https://doi.org/10.1016/j.icarus.2016.05.002) | Jorda 等，Icarus 277:257–278 | A/B：形状、自转与密度 | `jorda2016` |
| 2016 | [A homogeneous nucleus for comet 67P/Churyumov–Gerasimenko from its gravity field](https://doi.org/10.1038/nature16535) | Pätzold 等，Nature 530:63–65 | B：引力、密度与内部结构 | `patzold2016` |
| 2023 | [A new shape model of the bilobate comet 67P/Churyumov-Gerasimenko](https://doi.org/10.1016/j.icarus.2023.115566) | Chen 等，Icarus 401:115566 | A：67P 形状模型 | `chen2023shape` |
| 2024 | [Sensitivity Testing of Stereophotoclinometry for the OSIRIS-REx Mission. I. Accuracy and Errors of Digital Terrain Models](https://doi.org/10.3847/PSJ/ad1c63) | Palmer 等，The Planetary Science Journal 5(2):46 | B：SPC 精度与误差 | `palmer2024accuracy` |
| 2024 | [Sensitivity Testing of Stereophotoclinometry for the OSIRIS-REx Mission. II. Effective Observation Geometry for Digital Terrain Modeling](https://doi.org/10.3847/PSJ/ad17c4) | Palmer 等，The Planetary Science Journal 5(2):47 | B/D：SPC 观测几何 | `palmer2024geometry` |

## 非论文参考资料（1 份）

### R01．OCAMS Operations Timeline (Reference Sheet)

[本地 PDF](<2021 - OCAMS Operations Timeline (Reference Sheet).pdf>)（11 页）。本地资料标题/元数据为 `observation_key_ocams_20210726`；文件中的 2021 表示该参考表的整理版本，不作为学术论文发表年。

- **内容与用途：** 按任务阶段、日期、图像数量及活动说明记录 OCAMS 运行，从巡航检查/标定、接近和 Bennu 测绘到离开前观测；可用来查观测获取时序。
- **资料方法：** 时间线/活动表汇编，没有独立研究问题、新算法或实验创新点。
- **使用边界：** 含暗场、恒星、标定及其他活动；拍摄总数不是某个 SPC 模型的输入数，表中也未逐张标注各模型是否使用该图像。原始发布来源在本地资料中未明确，引用时应说明它是辅助参考表。
- **原文定位：** PDF 第 1–11 页整表。

## 附录：Bennu SPC 模型的递进关系与图像数量

### 结论：已有模型持续细化，同时存在并行建模

**后续建模会利用已有的模型成果和新增影像继续改进；但不能把所有版本号连成一条严格的父子链，也不能假设后一版保留前一版的全部原始影像。** 模型版本、观测阶段和一次新增数据集并非一一对应。

| 证据来源 | 原文位置（页码从 1 起） | 支持的结论 |
| --- | --- | --- |
| [Barnouin 等，2020：Digital terrain mapping](<2020 - Digital terrain mapping by the OSIRIS-REx mission.pdf>) | §3.1，PDF/正文第 6 页 | 先用远距离低分辨率影像中的轮廓建立初始形状，再生成低分辨率 DTMs/maplets；获得更多影像后改进形状、自转轴方向和自转速率，这些改进结果作为后续生成更精细 DTMs 的起始模型。 |
| [Al Asad 等，2021：Validation](<2021 - Validation of Stereophotoclinometric Shape Models of Asteroid (101955) Bennu during the OSIRIS-REx Mission.pdf>) | 引言末段及 §3，PDF 第 5 页／正文第 3 页 | 更新有三种来源：新增观测数据、对已有 SPC 解继续处理、团队内部独立并行建模。Palmer/Weirich（P/W）与 Gaskell（G）两组同时生成模型，使用的代码版本、参数、迭代次数及输入数据存在差异。 |
| 同上 | 图 4 图注，PDF 第 9 页／正文第 7 页 | 明确说明 v20 的 maplets 也存在于 v42，只是在图中被更高分辨率 maplets 遮住。这直接证明两个正式模型之间存在地形产品的继承。 |
| [Barnouin 等，2019：Shape of Bennu](<2019 - Shape of (101955) Bennu indicative of a rubble pile with internal stiffness.pdf>) | Methods，PDF 第 7 页 | 早期科学分析采用 v20，影像数量表述为超过 1,500 张；与 2021 年验证论文表 1 的精确计数 1,560 张相符。 |

可将总体过程概括为：**远距离轮廓初始模型 → 低分辨率 maplets → 利用新增影像和已有解迭代更新 → 更精细的全球及局部地形产品**。这是方法流程示意，不表示每一对相邻版本号均有已经证明的直接继承关系。

### 各模型实际使用的 OCAMS 图像数量

以下逐项摘录自 Al Asad 等（2021）**表 1**。日期为模型日期；图像数量是对应模型的输入数量，不是该阶段新拍摄的数量。GSD 是覆盖全球的 maplets 的采样间距。

| 模型 | 模型日期 | 建模组 | Maplet GSD（m） | 输入图像数（张） |
| --- | --- | --- | --- | ---: |
| v07 | 2018-11-23 | P/W | 1.20 | 294 |
| v10 | 2018-12-06 | P/W | 0.75 | 649 |
| v14 | 2018-12-27 | P/W | 0.35 | 1,560 |
| v19 | 2019-01-17 | G | 0.35 | 4,240 |
| v20 | 2019-01-21 | P/W | 0.35 | 1,560 |
| v28 | 2019-04-14 | G | 0.35 | 16,161 |
| v32 | 2019-06-03 | P/W | 0.35 | 10,088 |
| v42 | 2019-08-28 | P/W | 0.14 | 10,722 |

解释与引用时需保留以下口径：

- **v20：1,560 张；v42：10,722 张。** 两者分别是满足任务“75 cm 形状模型”和“35 cm 形状模型”要求的正式模型；这两个任务产品名称不要与表中的 0.35 m、0.14 m maplet GSD 混用。对应说明见 §4.1–4.2。
- v14 与 v20 的数量相同，但计数相同本身不能证明它们使用完全相同的影像清单；也不能据此断言两个模型没有变化。
- v28 的 16,161 张与 v42 的 10,722 张来自不同建模组的版本。版本号增大不意味着图像数必然增加，或输入集合一定包含此前所有影像。
- **不能把各行相加作为全任务 SPC 影像总量，也不能把相邻行之差当作某阶段新增的建模影像数。** 这些数字没有提供各版本影像集合的交集/并集信息。v42 的 10,722 张仅是该版本的输入数，不能扩展为包含所有局部建模与后续导航产品的全任务去重总数。
- [OCAMS Operations Timeline（2021）](<2021 - OCAMS Operations Timeline (Reference Sheet).pdf>)记录观测活动及拍摄情况，可辅助判断数据获取阶段；该表没有逐张标注影像是否被某一 SPC 模型采用，不能直接用拍摄总数代替建模输入数。

可用于论文的审慎表述：

> OSIRIS-REx 对 Bennu 的 SPC 建模随观测数据的积累逐步细化，利用已有形状解与地形小块构建更高分辨率的模型，并由不同团队并行生成和验证若干版本。两个正式全球模型 v20 与 v42 分别采用 1,560 和 10,722 张 OCAMS 影像；v42 保留了 v20 的地形小块，并增加更高分辨率的地形表示。

这段表述主要引用 Barnouin 等（2020，§3.1）与 Al Asad 等（2021，表 1、图 4）；2019 年形状论文可作为 v20 科学应用的补充来源。

## 面向当前研究的阅读路径

1. **建立重建与误差基础：** [P02](#p02) → [P20](#p20) → [P16](#p16)，再读 [P13](#p13)、[P17](#p17)，明确观测约束、重建变量和可验证的误差指标。
2. **比较观测规划决策：** [P07](#p07) → [P10](#p10) → [P14](#p14) → [P30](#p30)，分别考察联合轨道动作、二值曝光和位置/时间组合。
3. **借鉴通用主动重建：** [P09](#p09)、[P12](#p12)、[P18](#p18)、[P21](#p21)、[P23](#p23)、[P27](#p27)，重点比较信息收益、候选空间、在线反馈及移动成本。
4. **补齐工程约束与验证：** [P31](#p31)、[P26](#p26)、[P28](#p28)、[P33](#p33)、[P38](#p38)，提取载荷、太阳、资源、指令和知识误差的具体限制。

由这些文献形成的可检验研究方向是：将已有模型及新观测带来的实际地形误差改善，与 SPC 几何互补性、拍摄/移动成本和执行扰动共同纳入闭环规划。该方向是本库阅读后的综合判断，不能作为某一篇论文已经实现的结论。
