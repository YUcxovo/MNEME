# MNEME Bachelor Thesis Final Writing and Polishing Checklist

本清单综合以下约束：

- 教授对两轮 thesis draft 的现场反馈，尤其是最新的逐页结构、UI/UX、Backend、Testing 与实验真实性意见；
- `GENERAL_AGENTS.md`、`THESIS_HINTS.md` 与 `MNEME/docs/latex_new/` 中导师调整后的 thesis template；
- MNEME 前期 proposal、slides、mid-term report、设计材料和实验材料；
- 项目已经确认的写作、事实边界与实验诚信原则。

本清单用于最终全文审阅。检查必须逐段完成，关键词搜索只能作为辅助，不能替代阅读。

---

## 0. 使用方式

- [ ] 以最新 `docs` 论文为唯一正文基线。
- [ ] 发生冲突时依次采用：教授反馈与官方模板、原始实验与运行证据、当前实现、已核实的课程材料、论文大纲、其他当前文档、历史 proposal/report/slides、通用写作建议。
- [ ] 教授明确要求复用既有课程作业时，直接使用原作业页面、原图、可编辑源文件或高清截图；不得仅为统一风格、美化或重排而生成内容替代图。
- [ ] 对冲突作出记录并说明处理依据，不静默选用更方便的材料。
- [ ] 每轮只处理一种问题：结构、事实、实验、语言、引用或排版。
- [ ] 修改前确认该段属于谁的事实范围。
- [ ] 修改后重新阅读完整段落及其前后段，避免局部修改破坏上下文。
- [ ] 将每项实质性陈述在内部识别为 Historical Design、Observed、Implemented、Measured、Outside Scope 或 Limited，不把这些内部标签写进正文，也不暗中提升证据等级。
- [ ] 所有新增数字先核对原始 CSV、JSON、测试报告或参与者记录。
- [ ] 所有新增技术描述先核对实际实现和公开接口。
- [ ] 最终由作者逐章人工确认，不能仅依赖自动检查。

---

## 1. 提交阻断项

以下任一项未通过，论文不能提交。

- [ ] 官方模板已有的 chapter、section 和 subsection 名称、层级与顺序，以及封面、摘要、目录、附录等必要结构均不被删改、合并、拆分或重排；模板中的示例或引导占位文字由正式论文内容替换，并只在原有结构内部按需增加少量、实质性的下级小标题。
- [ ] 论文标题严格使用 “MNEME: A Mobile-Native AI Research Agent for Continuous Literature Understanding”。
- [ ] 主体论文使用英文，中文仅出现在模板要求的中文或双语位置。
- [ ] Background、Problem Statement、Existing Solutions、Proposed Solution 的顺序正确。
- [ ] Design Specification、App Design、Development and Testing、Conclusions 的内容放置正确。
- [ ] 全文不存在编造、补齐、猜测或无法追溯的实验数据。
- [ ] 全文不存在把测试夹具、静态原型或缓存结果描述为真实在线生成的情况。
- [ ] 全文不存在把单次观测写成统计分布或一般性能结论的情况。
- [ ] 全文不存在把模拟器结果推广到所有 Android 设备的情况。
- [ ] 全文不存在把客户端图谱渲染结果写成图谱算法质量的情况。
- [ ] 全文不存在 branch、commit、PR、issue、merge、milestone 或内部协作过程。
- [ ] 全文不存在“之前讨论过”“proposal 中写过”“根据本地材料”“earlier draft”等元讨论。
- [ ] 全文不存在尚未完成却被写成已经完成的 feature 或实验。
- [ ] 每项工程事实和实验结果均由对应 domain owner 从原始证据确认；其他成员只能指出疑点，不能代替负责人认证真实性。
- [ ] 所有结论的强度均不超过实验和引用能够支持的范围。
- [ ] 每项主要 technical challenge 至少对应一项真实、保留且边界明确的实验结果。
- [ ] Abstract、Testing Results、结果表和 Main Conclusions 只使用已经完成的证据。
- [ ] 正文、图表、附录、摘要和致谢中均不存在成员分工、负责人姓名、sign-off 请求或写作协作说明。
- [ ] LaTeX 能够从干净环境完整编译，正文、参考文献、图表和附录均正常生成。

---

## 2. 论文定位与读者

- [ ] 全文按照 bachelor thesis 写作，不采用中期报告、技术报告或工程日志口吻。
- [ ] 假定读者第一次接触 MNEME，也没有看过团队讨论。
- [ ] 全文以已经完成的研究工作、系统方法和实验证据为主线；限制用于准确界定结论，不抢占摘要、章节开头、结果分析或结论的中心句。
- [ ] 结果段落先陈述观察到的成功、改进或已验证机制，再说明异常、失败和适用范围。
- [ ] 研究问题、术语、方法、系统流程和实验条件均在首次出现时解释。
- [ ] 每个章节都能回答“为什么需要这一章”和“它怎样推进论文论证”。
- [ ] 文章从研究问题出发，技术设计和实验服务于研究问题。
- [ ] 不通过堆叠功能列表代替技术贡献。
- [ ] 不通过罗列代码模块代替系统方法说明。
- [ ] 正文优先解释读者需要理解的技术关系。
- [ ] 复现细节放入适当的 Methods、Testing Tool 或 Appendix。

---

## 3. 模板与篇幅

- [ ] 标题、章节名称和组织顺序与官方模板一致。
- [ ] 不新增会改变模板主结构、替代模板已有标题或重新定义章节任务的新 chapter、section 或 subsection。
- [ ] 当原有一节确实过长、内部包含多个完整且相对独立的论证单元时，可以增加少量下级小标题；每个新增标题都应承载多段连贯正文或一个完整的方法/实验单元，而不是只带领一小段。
- [ ] 优先使用连贯段落和自然过渡；不连续堆叠 `subsubsection`、`\paragraph` 或粗体段首标签，不把每个观点、参数、图表或实验步骤都单独做成标题。
- [ ] 英文摘要基本填满一页，内容自然，不靠重复或放大字号补齐。
- [ ] 最终成稿以约 100 个 compiled pages 为整体目标而非硬性逐章配额；正文、附录和模板前后置部分的比例服务于论证与可读性。
- [ ] 页数增长来自技术解释、实验方法、结果分析、文献讨论和限制。
- [ ] 不用重复文字、超大图片、空白页或无意义表格填充篇幅。
- [ ] `Main Conclusions` 保持简洁，目标约一页。
- [ ] `Discussions` 承担深入解释、限制和研究问题回应。
- [ ] `Outlook` 简洁陈述有学术意义的后续研究、扩展和更广验证，不写工程 backlog、尚待合并功能或未完成任务。

---

## 4. Abstract

- [ ] 摘要说明传统研究工作流或领域背景。
- [ ] 摘要明确现有解决方案及其不足。
- [ ] 摘要清楚陈述本文解决的问题。
- [ ] 摘要说明 MNEME 提出的核心方法和技术设计。
- [ ] 摘要报告最重要的真实实验结果。
- [ ] 摘要给出与证据强度一致的结论。
- [ ] 摘要不出现代码、仓库、材料包、commit 或内部开发状态。
- [ ] 摘要不使用 “local evidence package”“inspected repository”“earlier draft”等审计语言。
- [ ] 摘要不把全部篇幅用于限制声明；限制集中在结果和结论附近。
- [ ] 中英文摘要在问题、方法、结果和结论上相互一致。
- [ ] 中英文摘要中的数字完全一致。
- [ ] 关键词能够代表研究问题和核心技术。

---

## 5. Chapter 1: Introduction

### Background

- [ ] 先介绍科研文献发现、阅读、验证和管理的实际背景。
- [ ] 传统工作方式、现有工具和移动场景的关系解释充分。
- [ ] 读者在看到 MNEME 专有术语前已经理解研究背景。
- [ ] Background 为问题建立必要背景，但不为了页数重复产品和技术介绍。
- [ ] 不在开头直接堆叠未解释的技术挑战或系统模块。

### Problem Statement

- [ ] 问题陈述清楚回答“具体困难是什么”和“为什么值得解决”。
- [ ] Problem Statement 采用 Problem → developed Challenge paragraphs → Research Questions 的顺序，整体约两页而非继续扩张。
- [ ] Problem Statement 不以公式开场，不提前报告访谈数据、系统结果或 Evaluation Approach。
- [ ] 每项 technical challenge 都有现实动机和技术原因。
- [ ] challenge 数量由证据决定，不为形成整齐列表而强行拆分。
- [ ] challenge 与后续方法和实验能够一一对应。
- [ ] 不把 feature 名称直接当作 research problem。

### Existing Solutions and Their Drawbacks

- [ ] 搜索、文献管理、AI 阅读工具、推荐和图谱工具均被准确介绍。
- [ ] 产品功能事实由官方网站支持。
- [ ] 方法、效果和局限由学术文献支持。
- [ ] 竞品分析解释比较维度及其与用户需求的关系。
- [ ] 不使用产品宣传文字证明产品有效。
- [ ] 不制造“所有现有工具都失败”的夸大叙述。

### Proposed Solution

- [ ] 清楚说明 MNEME 提出什么。
- [ ] 核心技术思想得到解释，不能只列组件名称。
- [ ] Research Questions 与 Problem Statement 对齐。
- [ ] Contributions 与实际实现和实验对齐。
- [ ] Thesis Structure 只简洁说明章节安排。
- [ ] 删除对材料来源、仓库检查和写作过程的说明。

---

## 6. Chapter 2: Design Specification

### Customer Requirements

- [ ] 说明用户研究的目标和设计原则。
- [ ] 解释 interview questionnaire 各问题组的目的。
- [ ] 交代参与者人数、背景范围、访谈形式和大致时长。
- [ ] 说明采集了哪些数据以及如何整理。
- [ ] 不将十人样本写成人群统计结论。

### Affinity Map

- [ ] 解释 affinity map 的编码和聚类方法。
- [ ] 图中颜色、字母、编号和区域均有明确含义。
- [ ] 删除或解释重复、无意义的 ABCD 类标签。
- [ ] 图中文字在正常 PDF 缩放下清晰可读。
- [ ] 图片使用当前能够获得的最高分辨率。
- [ ] 只保留两至三张最有解释力的 affinity-map 图，并优先使用课程作业中的原图或忠实高清截取，而不是重新生成同义图。
- [ ] 正文解释主要模式，不能只放图。

### Customer Profile and Value Proposition

- [ ] Customer profile 由访谈结果支持。
- [ ] 人数和观察次数区分清楚。
- [ ] Value proposition 与实际问题和需求对应。
- [ ] Storyboard 以读者能够理解的故事顺序说明产品设想。
- [ ] Value Proposition 和 Storyboard 优先复用已核实的课程作业内容，并在不改变模板主结构的前提下放入最合适的既有 section；若内容较长，可使用少量实质性下级小标题组织。
- [ ] 图注不提 proposal、slides 或材料来源。

### Competitor Analysis

- [ ] 使用清晰、可解释的比较维度。
- [ ] 表格或图片优于大段产品功能堆砌时，采用表格或图片。
- [ ] 产品网页仅支持产品功能事实。
- [ ] 增加足够的同行评审文献作为方法和局限依据。
- [ ] 每组比较后说明它如何影响 MNEME 的设计。

---

## 7. Chapter 3: App Design

### Storymap and Features

- [ ] Story map 作为正式图片进入正文。
- [ ] Story map 字体清楚，用户目标、活动和 feature 层次可辨。
- [ ] 正文解释 story map 的阅读方式。
- [ ] feature 与用户需求和后续 acceptance criteria 相连。
- [ ] 不将 story map 当作实现完成度证据。
- [ ] 主文只展开 core features，Storymap and Features 保持约两页的解释尺度，不恢复完整功能目录。

### Acceptance Criteria

- [ ] 每项 criterion 有明确前提、动作和可观察结果。
- [ ] criterion 描述系统行为，不描述内部任务分工。
- [ ] Chapter 4 中存在对应的测试或明确限制。
- [ ] 表格使用清晰分组和视觉分隔。

### Engine Architecture

- [ ] 架构图清楚展示客户端、后端、数据与 AI 流程。
- [ ] 解释各层责任及跨层数据流。
- [ ] 技术 challenge 与所提出的机制明确对应。
- [ ] Chapter 3 只保留 high-level architecture、design trade-offs 与 public boundaries；算法、公式、伪代码、参数、队列内部和 runtime mechanics 移至 Chapter 4 Back-end Development。
- [ ] 流程图中的框不是大段正文的替代品。
- [ ] 架构说明只交代影响用户可见设计的失败状态和边界，不展开底层恢复实现。

### API Design

- [ ] 说明 API 在整个系统设计中的作用。
- [ ] API 表格展示输入、输出和关键语义。
- [ ] 不把所有 endpoint 逐行抄成接口文档。
- [ ] 重点说明身份、版本、异步状态、幂等性和错误边界。
- [ ] API 与 Android 状态流和后端机制一致。

### UI/UX Design

- [ ] 使用真实设计稿、原型图或 Android 截图。
- [ ] 静态 prototype 与真实 Android implementation 清楚区分。
- [ ] 图片不使用全是文字的伪流程图。
- [ ] 截图中的文字、按钮和状态能够看清。
- [ ] 设计选择与访谈或 usability finding 对应。
- [ ] 不把设计修改写成已经证明的可用性提升。
- [ ] 叙事明确形成 Initial UI/UX Design → formative testing → identified problems → design adjustments；真实 App Development 与 Final Product UI 放在 Chapter 4 Front-end Development。

### Usability Testing

- [ ] 明确测试对象是 prototype 还是实际产品。
- [ ] 说明参与者、任务、成功标准和记录方式。
- [ ] 报告任务级结果，不只报告总百分比。
- [ ] 缺失的参与者级时间、点击和观察记录明确说明。
- [ ] 2/5 图谱任务结果被如实保留。
- [ ] Open Paper、选中状态和操作提示被描述为设计响应。
- [ ] 没有后续用户测试时，不声称设计已经解决问题。

---

## 8. Chapter 4: Development and Testing

### Technical Development

- [ ] Front-end 和 back-end 部分解释技术机制及其设计理由。
- [ ] 只写对读者有用的技术细节。
- [ ] 不记录开发分支、合并状态、commit 或责任人。
- [ ] feature 有实际实现证据后才能写成实现。
- [ ] 算法、架构、状态机和跨层流程有足够技术深度。
- [ ] 关键机制的输入、输出、边界条件和失败模式得到解释。
- [ ] 公式、伪代码、流程图、表格与正文按解释需要组合使用；伪代码是允许且有助于表达多样性的算法说明形式，但必须由前置动机、符号/输入输出说明和后续解释承接，不能替代正文论证或变成参数清单。
- [ ] 每段伪代码与实现或正式设计一致，具有清晰 caption/label，并在正文中被引用和解释；无需为了形式统一而把所有算法都改写成同一种表示。
- [ ] Front-end Development 展示并解释真实最终产品 UI，不以静态 prototype 代替最终应用截图。
- [ ] Back-end Development 接收从 Chapter 3 移出的算法、公式、实现流程、接口机制和参数；导师口头建议的约 10–20 页是合理深度参考，不是填充配额。

### Testing Tool and Protocol

- [ ] 每组实验说明研究问题或测试目标。
- [ ] 环境、输入、样本数量、warm-up 和成功条件明确。
- [ ] 指标定义出现在结果前。
- [ ] controlled、live、cached、fixture、offline 和 failure 条件明确区分。
- [ ] 仿真器、真实后端和模型配置的作用边界明确。
- [ ] 正文不记录不必要的完整 commit hash。
- [ ] 复现需要的完整 manifest 放在附录或保留的实验产物中。

### Results

- [ ] Testing 部分同时包含方法、结果和分析。
- [ ] 每个表格或图之前说明为什么需要它。
- [ ] 每个表格或图之后解释最重要的观察。
- [ ] 负面结果、失败案例和 null result 如实保留。
- [ ] 不用“all tests passed”替代具体条件和样本数量。
- [ ] 不把代码覆盖率当作语义正确性的证明。
- [ ] Feature acceptance 与 Performance Testing 分开；验收表至少包含 Feature、Test task、Expected result、Actual result 和 Status，并能追溯到截图或运行记录。

### Android and UI Evaluation

- [ ] cold start 与 foreground/resume 的定义准确。
- [ ] Android 无法确认 hot start 时不写成 hot-start benchmark。
- [ ] 状态转换时间不被写成网络端到端延迟。
- [ ] polling 时间包含轮询间隔时明确说明。
- [ ] DOM-ready 与 force-layout convergence 明确区分。
- [ ] 图谱渲染、节点选择和图谱算法质量明确区分。
- [ ] event queue、retry、duplicate 和 readback 的边界准确。
- [ ] live event digest 为空时如实说明。
- [ ] 两种 live-core UI trace 分开报告，不合并成一个分布。
- [ ] artifact reuse 与 Android local cache 明确区分。
- [ ] multi-seed 实验只支持记录到的 seed-to-graph 路径结论。
- [ ] Android 配置矩阵不用于未经控制的 CPU、RAM 或 API 因果比较。
- [ ] CPU×RAM 实验以独立 session 为分析单位。
- [ ] session 内重复测量不被当作独立设备样本。
- [ ] 未执行的最终产品后续用户研究不出现结果或完成暗示；正文也不出现其内部实验代号。

### Other Members' Evaluation

- [ ] AI/RAG、recommendation 和 graph algorithm 结果由对应负责人确认。
- [ ] Android 架构、UI、设备配置和移动实验由 Android domain owner 确认；backend/data/behavior/graph-platform 事实由相应 backend owner 确认。
- [ ] 不修改其他成员仍在运行的实验数据。
- [ ] 不用我们的 Android 结果补足其他模块缺失的质量结论。
- [ ] 跨模块结论明确指出每个证据来自哪一类实验。

---

## 9. 实验诚信与统计表达

- [ ] 每个正文数字都能追溯到保留的原始数据。
- [ ] 原始数据、分析脚本和生成图表之间没有手工改数。
- [ ] 失败样本没有被无说明地删除。
- [ ] warm-up 的处理在实验设计中预先说明。
- [ ] 缓存、持久化产物和 provider completion reuse 得到披露。
- [ ] 单次 UI trace 写成 acceptance observation，`n=1` 不报告 p95。
- [ ] 小样本 p95 等于最大值时能够正确解释，不用 percentile 营造不存在的统计稳定性。
- [ ] 不把不同实验条件的结果直接合并计算平均值。
- [ ] 不在小样本上进行无意义的显著性推断。
- [ ] 观察性结果使用 “observed”“indicates”“suggests”等有限措辞。
- [ ] 因果用语只用于受控且能够支持因果解释的设计。
- [ ] 结果不好、没有单调趋势或置信区间跨零时如实报告。
- [ ] 推荐、回答和图谱内容质量没有经过评价时不声称其有效。
- [ ] 用户研究结果不推广到一般人群。
- [ ] Provider model、token、latency 和 cost 由 AI domain owner 依据原始调用记录确认；模型存在或价格网页可访问不等于该次实验真实发生。
- [ ] Modeled cost estimate 与 measured spend 明确分开；若保留估算，必须给出有访问日期的一手价格、token accounting、调用路径假设、四舍五入规则和可复算脚本，否则删除。

---

## 10. 数字、单位与有效数字

- [ ] 原始实验文件保留完整精度。
- [ ] 正文通常显示 2–3 位有效数字。
- [ ] 不把毫秒数据无理由写到微秒级精度。
- [ ] 同一表格中的小数位和单位保持一致。
- [ ] 秒级等待优先用秒表示，避免出现难读的五位毫秒数。
- [ ] 百分比、比例和人数不混用。
- [ ] `5/5`、`21/25` 与 `84%` 的含义清楚。
- [ ] median、mean、p95、range 和 success rate 不混用。
- [ ] 图表与正文中的四舍五入结果一致。
- [ ] 四舍五入不改变成功数、样本量或结论方向。

---

## 11. References and Citations

- [ ] 每条引用真实存在，标题、作者、年份和 venue 正确。
- [ ] 技术方法和效果结论优先引用同行评审论文或权威技术来源。
- [ ] 产品功能引用官方网站。
- [ ] 产品帮助页面不用于证明产品质量或用户效果。
- [ ] 产品文档不成为参考文献的主要组成。
- [ ] Background、Existing Solutions 和 Discussion 有足够学术文献。
- [ ] 每个重要事实或外部方法都有紧邻的引用。
- [ ] 引用确实支持其所在句子的具体主张。
- [ ] 重要外部主张已核对来源中的具体段落或页码，不能只核对标题、摘要或书目信息。
- [ ] 不使用只与关键词相关、但不支持该结论的文献。
- [ ] 网页引用包含有效 URL 和访问日期。
- [ ] 动态产品名称、功能、模型标识和价格在提交前重新核验，避免沿用已更名产品或过期定价。
- [ ] DOI、arXiv、会议版本和期刊版本不混写。
- [ ] 同一篇工作的版本信息保持一致。
- [ ] 参考文献列表中没有正文未引用的无关条目。
- [ ] 正文没有缺失的引用键或问号引用。

---

## 12. Figures

- [ ] 导师指定复用的 affinity map、value proposition、storyboard 与 UI/UX 课程材料优先使用原图、原页面或忠实高清截取；不得用生成式重绘替代原始作业证据。
- [ ] 系统架构、算法流程和实验结果图必须来自真实设计/实现或可复算数据，不使用生成图代替证据。
- [ ] 图像采用可获得的最高分辨率。
- [ ] PDF 中的图中文字在正常阅读尺寸下清晰。
- [ ] 亲和图、story map、架构图、流程图和实验图均有实际解释作用。
- [ ] 不使用整张图几乎全是段落文字的设计。
- [ ] 流程图突出节点、数据和方向。
- [ ] 架构图突出系统边界和责任。
- [ ] 实验图使用可区分且色盲友好的配色。
- [ ] 颜色不是唯一的信息编码方式。
- [ ] 图中缩写、字母和符号均有定义。
- [ ] Caption 可以脱离内部讨论独立理解。
- [ ] Caption 不出现 “adapted from the proposal/slides/report”。
- [ ] 静态 prototype 截图明确标注其证据范围。
- [ ] Android 截图不被描述为设计稿。
- [ ] 图像来源和版权要求得到满足。
- [ ] 正文在图前引入、图后解释。

---

## 13. Tables

- [ ] 只在精确比较、映射或多维结果确有需要时使用表格。
- [ ] 不因“减少表格”而删除必要的 requirements、feature-acceptance 或结果表；milestone 不得进入正式论文。
- [ ] 不用表格重复正文已经清楚说明的简单信息。
- [ ] 使用 booktabs 或同等清晰的视觉结构。
- [ ] 行组之间有小标题、空行或适当横线。
- [ ] 列标题、单位和样本量清楚。
- [ ] 表格能够在一页宽度内阅读。
- [ ] 不出现密集、无断点、难以追踪的长表。
- [ ] 连续多页只有表格时重新检查浮动位置和必要性。
- [ ] Caption 说明实验条件和结论边界。
- [ ] 表格中的数据与正文及原始结果一致。

---

## 14. 段落与小节

- [ ] 每段有明确中心句。
- [ ] 每段包含足够的证据、解释或技术展开。
- [ ] 一句话段落只用于必要的过渡或强调。
- [ ] 一页大致包含少量实质段落，避免大量碎段；“约三段一页”仅作可读性参考。
- [ ] 不把一个完整论点拆成连续五六个短段。
- [ ] 一个 section 至少完成问题、方法或证据、解释这条逻辑链。
- [ ] 内容不足的小 subsection 被合并或改为自然段首主题句。
- [ ] 不为增加标题数量而拆分内容。
- [ ] 段落之间存在明确逻辑关系。
- [ ] 相邻章节有自然过渡。
- [ ] 不反复总结刚刚已经说过的内容。
- [ ] 正文以完整、连贯的学术段落推进；bullet list 仅用于确实可枚举且比 prose 更清楚的内容，不用项目符号代替论证。

---

## 15. 语言与非 AI 化表达

- [ ] 用语简洁、专业、朴素。
- [ ] 删除宣传式、夸张或无法证明的形容词。
- [ ] 谨慎使用 robust、comprehensive、novel、groundbreaking、crucial 等词。
- [ ] 避免连续堆叠四五个名词、形容词或抽象概念。
- [ ] 避免机械的 “First, Second, Third” 排比。
- [ ] 避免每个问题都强行拆成三点。
- [ ] 避免反复使用 “not X but Y”“rather than”“not merely”等二元对立句式。
- [ ] 避免 “This section will discuss…” 等元叙述。
- [ ] 避免 “It is important to note that…” 等空洞开头。
- [ ] 避免 “adapted from…” 等内部来源说明。
- [ ] 避免过量破折号、分号和括号插入语。
- [ ] 句子长度自然变化，连续句不呈现机械节奏。
- [ ] 技术术语保持一致，不为避免重复而随意换同义词。
- [ ] MNEME、briefing、paper revision、citation graph、live backend、cache 等术语全篇一致。
- [ ] 英式与美式拼写选择一种并保持一致。
- [ ] 缩写首次出现时给出全称。
- [ ] 文件名不以全大写形式进入正文。
- [ ] 不使用内部 class、script 或测试方法名替代学术描述。
- [ ] 不泄露 prompt、AI 协作过程或内部审阅讨论。

---

## 16. 技术细节与工程细节边界

### 应当保留

- [ ] 技术 challenge 的原因和边界。
- [ ] proposed algorithm 或机制的核心思想。
- [ ] 数据模型、状态机、算法流程和关键公式。
- [ ] 客户端、后端和 AI pipeline 的责任边界。
- [ ] API contract、幂等性、版本身份和失败恢复。
- [ ] 实验协议、成功标准、指标和限制。
- [ ] 对实验观察的技术解释。

### 应当删除或移出正文

- [ ] branch、commit、PR、issue 和 merge 状态。
- [ ] 谁批准、谁等待谁、谁负责合并。
- [ ] milestone 或内部任务编号。
- [ ] 临时 demo 配置和排障过程。
- [ ] “仓库里已经有代码所以算完成”等内部判断。
- [ ] 没有帮助读者理解方法的文件路径和类名。
- [ ] 为严谨而插入、却会打断主线的协作细节。

---

## 17. Cross-Chapter Consistency

- [ ] 标题、研究问题和贡献在 Abstract、Introduction 和 Conclusion 中一致。
- [ ] Chapter 2 的需求能够在 Chapter 3 找到设计响应。
- [ ] Chapter 3 的 acceptance criteria 能够在 Chapter 4 找到测试或限制。
- [ ] Chapter 4 的结果能够在 Chapter 5 得到准确解释。
- [ ] 同一 feature 的完成状态在不同章节一致。
- [ ] 同一实验的样本量、数字和条件在全文一致。
- [ ] prototype、Android client 和 backend 的状态不混淆。
- [ ] fixed-seed、multi-seed、controlled 和 warm-path 实验不混淆。
- [ ] 研究贡献不在不同章节中反复扩大。
- [ ] Limitations 不与正文中的强结论冲突。

---

## 18. Conclusions

- [ ] Discussions 按研究问题解释结果。
- [ ] Discussions 包含成功、失败、null result 和限制。
- [ ] Discussions 与 Main Conclusions 先回答“本文做到了什么”，再用简洁、具体的文字限定“证据支持到哪里”。
- [ ] Main Conclusions 只总结已经得到证据支持的贡献。
- [ ] Main Conclusions 约一页，不重复全部实验表格。
- [ ] Outlook 只包含有学术意义的 future work，不使用内部实验代号或工程待办清单。
- [ ] 未实现 feature 不被包装为完成的贡献。
- [ ] 未执行的最终产品用户研究只作为更广验证方向，不以内部实验代号出现。
- [ ] 不在 Conclusion 首次引入新实验或新算法。
- [ ] Conclusion 不出现项目管理、仓库或协作信息。

---

## 19. Appendix and Reproducibility

- [ ] Appendix 只承载正文不宜展开的复现细节。
- [ ] 原始数据、环境、样本数和成功条件能够追溯。
- [ ] Appendix 不用于隐藏正文必须解释的方法。
- [ ] Appendix 表格与 Chapter 4 数字一致。
- [ ] Authentication token、API key 和个人信息未被保留。
- [ ] 参与者隐私和匿名化要求得到满足。
- [ ] 未经明确授权，不向外部服务上传未公开论文、私人笔记、参与者记录或完整语料。
- [ ] 未收集的数据不以空模板暗示已经存在。
- [ ] Appendix 同样不得出现 commits、branches、milestones、成员分工、负责人姓名、sign-off 或进度记录。

---

## 20. 最终 PDF 视觉检查

- [ ] 从封面到最后一页逐页查看。
- [ ] 目录页码和章节链接正确。
- [ ] 英文摘要视觉上基本填满一页。
- [ ] 正文到 Conclusion 接近目标篇幅。
- [ ] 没有空白页、孤立标题或单独一行的段落。
- [ ] 没有连续两页只有图片且缺少解释。
- [ ] 没有一页堆叠过多表格。
- [ ] 图表没有超出页边距。
- [ ] 字体、字号和行距符合模板。
- [ ] 图中最小文字可以阅读。
- [ ] 表格列没有溢出或压缩到不可读。
- [ ] Caption 与图表保持在合理位置。
- [ ] 参考文献没有断裂 URL 或异常换行。
- [ ] 无未解析引用、问号引用或重复 hyperlink anchor。
- [ ] 无新增 overfull box；已有警告逐项判断是否可接受。
- [ ] PDF 中无低清、拉伸或裁切错误的图片。

---

## 21. 最终全文审阅顺序

### Pass 1: Template and Structure

- [ ] 对照官方模板逐章检查标题和内容归属。
- [ ] 检查摘要、Introduction、Conclusion 的研究主线。
- [ ] 检查正文篇幅和章节比例。

### Pass 2: Factual and Technical Audit

- [ ] 对照最新实现检查技术描述。
- [ ] 对照实验产物检查所有数字。
- [ ] 对照责任边界检查其他成员内容。

### Pass 3: Paragraph-by-Paragraph Reading

- [ ] 每段由外部读者视角阅读。
- [ ] 检查术语定义、逻辑、重复和内部信息。
- [ ] 检查短段、碎段和过多小标题。

### Pass 4: Claims and References

- [ ] 每个重要主张检查证据强度。
- [ ] 每个引用检查是否真正支持该句。
- [ ] 补足学术文献，控制产品网页比例。

### Pass 5: Experiments and Statistics

- [ ] 检查实验条件、样本单位和结论边界。
- [ ] 统一有效数字、单位和统计名称。
- [ ] 检查失败和 null result 是否保留。

### Pass 6: Figures and Tables

- [ ] 检查图片质量、标签、caption 和正文解释。
- [ ] 检查表格必要性、可读性和浮动位置。
- [ ] 检查整页视觉密度。

### Pass 7: Language Polish

- [ ] 删除 AI 式套话、排比和二元对立句式。
- [ ] 统一术语、拼写和语气。
- [ ] 朗读关键段落检查节奏和可理解性。

### Pass 8: Independent External Review

- [ ] 由没有参与前期讨论的独立读者或隔离上下文评审者阅读。
- [ ] 重点询问哪里 confusing、哪里像内部记录、哪里缺少定义。
- [ ] 独立评审不得看到内部讨论作为解释材料。
- [ ] 根据意见修改后重新运行阻断项检查。

### Pass 9: Final Build and Human Sign-off

- [ ] 干净编译最终 PDF。
- [ ] 逐页视觉检查。
- [ ] 各技术负责人确认其事实和实验。
- [ ] 负责人确认必须对应到 source/configuration/raw output/computation，而不是只回复“看起来没问题”。
- [ ] 所有定量结论和跨模块解释至少经过第二位相关成员人工核对。
- [ ] Hanyang 完成统一阅读体验审查。
- [ ] 全体作者阅读并承担最终文本责任。

---

## 22. 最终通过标准

论文只有在以下条件同时满足时才视为完成：

- [ ] 外部学者能够从头理解问题、方法、系统和实验。
- [ ] 全文符合官方模板。
- [ ] 技术内容充分，工程管理信息已清除。
- [ ] 所有实验真实、可追溯、解释有限且准确。
- [ ] 图表清晰，正文对其进行解释。
- [ ] 引用可靠，产品网页没有取代学术文献。
- [ ] 语言简洁、专业、自然，无明显 AI 模板痕迹。
- [ ] 正文篇幅、摘要和 Conclusion 满足教授要求。
- [ ] 独立外部审阅未发现阻断性 confusing 表达。
- [ ] 最终 PDF 编译和视觉检查通过。
