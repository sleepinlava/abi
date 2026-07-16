# ABI 真实生物学数据验证集规划

> 日期：2026-07-15  
> 目标：使用论文公开的原始测序数据验证 ABI 的真实执行、结果正确性和论文级生物学结论复现能力。  
> 原则：只将原论文、SRA/ENA/GEO/BioProject 和作者维护的数据仓库作为事实来源。

## 1. 结论先行

“用 ABI 重跑论文数据，并和原文结果对比”的方向是正确的，但它主要证明的是 **validity（结果可信）**，还不能单独证明 **utility（ABI 比手工流程更有用）**。建议把实验拆成两条证据链：

1. **生物学有效性**：ABI 能否在相同数据上恢复已知的样本分组、关键物种/基因/通路方向、已知 MLST/AMR/质粒或病毒结果。
2. **系统实用性**：相对于手工执行或通用 agent，ABI 是否减少人工步骤和失败次数，并提供更完整的计划、版本、资源清单、溯源、标准表和报告。

第一轮不应直接下载每篇论文的全量数据。推荐顺序是：

1. `wgs_bacteria`：6 个 ST93 MRSA isolate，约 1.64 GB，最适合第一个真实 E2E。
2. `metagenomic_plasmid`：单个真实 human-gut plasmidome，约 1.98 GiB，有论文定义的 74-plasmid 参考集。
3. `rnaseq_expression`：8 个 airway Dex/untreated 样本，验证差异表达方向，同时暴露 donor blocking 缺口。
4. `amplicon_16s`：先跑 DADA2 Extreme mock，再跑 Baxter CRC 平衡子队列。
5. `viral_viwrap`：本轮不做独立的生物学结果复现；只保留 ABI 适配层的轻量验收。
6. `easymetagenome`：先跑 mock，再跑 Zeller CRC 10+10 子队列。
7. 暂缓 `metatranscriptomics` 的论文级复现；当前实现不具备典型群落宏转录组所需的多物种功能统计。

## 2. 当前 ABI 能力边界

仓库当前有七个声明式分析类型。正式 runtime lock 覆盖六条已配置路线，`viral_viwrap` 仍被排除在正式 release scope 之外。这里的“已配置”不等于“已完成真实论文数据的生物学验证”。

| 分析类型 | 当前直接输出 | 真实论文比较的适配度 | 本轮定位 |
| --- | --- | --- | --- |
| `amplicon_16s` | ASV、SINTAX taxonomy、alpha/beta diversity | 高，但需匹配 primer 和 taxonomy DB | P0 |
| `rnaseq_expression` | STAR、featureCounts、DESeq2 | 高；支持显式加性 DESeq2 设计（Airway 固定为 `~ donor + condition`） | P0 |
| `wgs_bacteria` | SPAdes、Prokka、MLST、AMRFinderPlus | 高，但没有 core-SNP phylogeny | P0 |
| `metagenomic_plasmid` | 质粒检测/重建/分型/注释/AMR/宿主等 | 高，但完整路线资源重 | P0/P1 |
| `easymetagenome` | Kraken2/Bracken taxonomy、HUMAnN functions | 高，数据库版本会强烈影响结果 | P1 |
| `metatranscriptomics` | fastp → STAR/HISAT2 → featureCounts | 低；当前更接近“单参考表达计数” | P2/能力缺口 |
| `viral_viwrap` | ViWrap taxonomy、host、abundance 等 | 与上游 ViWrap 论文高度匹配 | 本轮排除生物学 benchmark，仅做适配层门禁 |

两个必须在实验前冻结的边界：

- `rnaseq_expression` 现支持以 `differential_expression.design` 传递 DESeq2 加性设计公式；Airway 将固定为 `~ donor + condition`。交互项、连续协变量和复杂批次设计尚未经过真实论文数据验收；即使控制 donor，也不应把不同 reference、aligner 与统计实现得到的精确显著基因数作为硬门槛。
- `metatranscriptomics` 目前只有单参考基因组比对和 featureCounts，没有典型群落宏转录组的 rRNA 去除、多物种/基因家族参考、通路定量、跨样本统计和 metagenome–metatranscriptome 联合分析。

## 3. 推荐数据集总表

表中的存储量来自官方项目记录或原论文；“计算负担”是为排期提供的工程估算，不是来源记录中的精确 benchmark。

| 优先级 | 工作流 | 数据集与 accession | 生物样本与规模 | 可与论文对比的终点 | 估算负担 | 主要风险 |
| --- | --- | --- | --- | --- | --- | --- |
| P0-control | `amplicon_16s` | DADA2 Extreme，[SRR2990088](https://www.ncbi.nlm.nih.gov/sra/SRX1478507) | 27 个已知肠道菌株，2,040,485 个 MiSeq 2×251 read pairs、约 678 MB | ASV precision/recall、低丰度菌株恢复、假阳性序列数 | <1 GB；单机小时级 | V4 primer，不是自然群落；必须覆盖配置中的 primer override |
| P0/P1 | `amplicon_16s` | Baxter CRC，[SRP062005](https://www.ncbi.nlm.nih.gov/sra/?term=SRP062005) / [PRJNA290926](https://www.ncbi.nlm.nih.gov/bioproject/290926) | 490 份 stool；官方项目约 544 experiments、15 Gbases、10.2 GB；MiSeq V4 PE | CRC 相关 taxa 方向、alpha/beta、组间分离；第二阶段才重建分类模型 | 子集低；全量低至中 | ABI 无 RF+FIT 模型；SINTAX/数据库变化限制 species-level 一致性 |
| P0 | `rnaseq_expression` | Airway，[GSE52778](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE52778) / SRP033351 / PRJNA229998 | 4 donors × untreated/Dex/albuterol/Dex+albuterol，16 个 75-bp PE libraries；先跑 Dex/untreated 8 个 | Dex 响应基因方向、排名和重叠；GEO 提供 FPKM 与 Dex-vs-untreated 文件 | 人类 STAR：约 32–48 GB RAM；8–16 CPU；半天级 | 原文用 hg19+TopHat/Cuffdiff；虽控制 donor，仍不能要求精确复现 316 genes |
| P1 | `rnaseq_expression` | Mammary gland，[GSE60450](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE60450) / SRP045534 / PRJNA258286 | 12 个 mouse samples；6 groups × 2 replicates；每样本 20–25M 100-bp PE fragments | 与作者公开 featureCounts 矩阵的基因计数相关性；luminal/basal 和发育阶段 marker 方向 | 约 240–300M fragments；mouse STAR 约 32 GB RAM | 每组 n=2；当前 ABI 只宜做预先定义的两组比较，不宜一次声称复现完整 2×3 factorial model |
| P0 | `wgs_bacteria` | ST93 MRSA，[PRJNA286158](https://www.ncbi.nlm.nih.gov/bioproject/286158) | 6 个 *S. aureus* PE WGS experiments，3 Gbases、约 1.64 GB | 6/6 MLST=ST93、`mecA`/MRSA AMR、assembly/annotation 指标 | 低；16 GB RAM 单机数小时 | ABI 没有 core-SNP tree，不能复现论文“不是近期暴发”的最终流行病学结论 |
| P1 | `wgs_bacteria` | Multiplex MinION *K. pneumoniae*，[PRJNA351909](https://www.ncbi.nlm.nih.gov/bioproject/351909) | 12 isolate 论文集；项目含 59 SRA experiments、38 Gbases、约 22 GB；17 complete assemblies | Illumina-only assembly 与完成基因组的长度、覆盖、contiguity、MLST/AMR concordance | 选 2 isolate 为中低；全量中 | ABI 是 short-read SPAdes，不能要求 closed genome；完整参考仍适合作为 assembly identity truth |
| P0-control | `easymetagenome` | Human-gut mock，[PRJNA747117](https://www.ncbi.nlm.nih.gov/bioproject/747117)（相关 shotgun/amplicon 数据见论文记录） | 定义明确的人肠道 mock；项目 141 experiments、325 Gbases、约 0.15 TB；只选 1–2 个 shotgun runs | taxon presence/absence、相对丰度误差、假阳性、HUMAnN 合理性 | 单 run 中等；数据库磁盘占用通常高于 reads | 项目包含多种实验条件，必须在 manifest 中固定具体 run，不能整项目盲下 |
| P1 | `easymetagenome` | Zeller CRC，[ERP005534 / PRJEB6070](https://www.ncbi.nlm.nih.gov/bioproject/266076) | 原论文 discovery cohort 156 人；当前归档项目聚合量约 0.77 TB，必须按 metadata 过滤 | CRC taxa 方向；fiber degradation 降低；host carbohydrate/amino-acid 与 LPS metabolism 增强；组间分离 | 10 CRC+10 control 为中；全队列高 | ABI 不含论文 classifier/FOBT；数据库和方法差异使精确 abundance/p-value 不可作硬门槛 |
| P0 | `metagenomic_plasmid` | SCAPP human-gut plasmidome，[SRR11038083](https://www.ebi.ac.uk/ena/browser/view/SRR11038083) / PRJNA605251 | 18.6M PE150 pairs，4.59 Gbases、约 1.98 GiB | 基于 PLSDB v.2018-12-05 和样本 contigs 动态筛选的 74 个 reference plasmids；论文 P/R/F1；circularity、replication/MOB 和 AMR 功能证据 | 低至中；完整 AutoPlasm route 仍可能需 64–128 GB RAM | 作者未单独发布 74 条静态 FASTA；必须冻结旧版 PLSDB 并重建 truth，不能用新版数据库代替 |
| P1-flagship | `metagenomic_plasmid` | PlasMAAG hospital sewage，[PRJEB85938](https://www.ebi.ac.uk/ena/browser/view/PRJEB85938) | 5 个 Danish hospital sewage 含 short-read metagenome、metaplasmidome 和 long reads；另有 24 个 Spanish short-read samples | 多模态支持的 plasmid bins、跨样本 reconstruction、与论文 assemblies 的 sequence overlap | 高；建议 128–256 GB RAM；先 1 个 Danish sample | 新数据且规模大；必须固定论文 assembly archive、数据库与 geNomad threshold |
| Optional-deferred | `viral_viwrap` | ViWrap Guaymas Basin，[SRR3577362](https://www.ebi.ac.uk/ena/browser/view/SRR3577362)；相关 MAG [PRJNA522654](https://www.ncbi.nlm.nih.gov/bioproject/PRJNA522654) | 171.6M PE reads，34.67 Gbases、约 30.5 GiB；论文使用 scaffold/read 子集和 98 MAG host DB | 仅在未来需要认证 ViWrap 部署时，复现 taxonomy/host/AMG 和 abundance | 原论文 20 threads 约 14h；数据库体积远大于 reads | 本轮不下载；当前不在正式 release lock，且 exact subset、random seed 和数据库 snapshot 未冻结 |
| P2-gap | `metatranscriptomics` | Matched gut meta'omics，[PRJNA188481](https://www.ncbi.nlm.nih.gov/bioproject/188481) | 8 subjects，多种保存方法，56 experiments、124 Gbases、约 0.11 TB | 原文：保存方式间高一致性；<5% transcripts 受保存影响；ribosome/methanogenesis 上、sporulation/amino-acid biosynthesis 下 | 单 frozen run smoke 中等；全量高 | 当前 ABI 无法生成论文所需群落 taxonomy/functions 与 DNA–RNA 联合统计；只可作 mapping/count plausibility |

## 4. 各工作流的推荐实验设计

### 4.1 `amplicon_16s`

#### 阶段 A：算法阳性对照

先跑 DADA2 Extreme。原始 DADA2 论文说明该样本含 27 个菌株，丰度跨多个数量级，多个目标序列只差一个碱基，并使用高重叠 MiSeq paired-end reads；这使它比“能否生成表格”更适合验证 ABI 的 merge、dereplication、UNOISE3 和 taxonomy 路线。[原论文及参考结果](https://pmc.ncbi.nlm.nih.gov/articles/PMC4927377/)

建议断言：

- raw、trimmed、merged read 数量守恒且方向合理；
- 对论文提供的 expected sequences 计算 ASV precision、recall、F1；
- 分别记录“未检出低丰度真菌株”和“额外 ASV”，而不是只比较 ASV 总数；
- 用 V4 的真实 primer 覆盖 ABI 自定义 primer 路径，不使用 V3–V4 默认值冒充兼容。

#### 阶段 B：真实临床队列

Baxter 等对 stool V4 16S 数据建立 CRC/adenoma 检测模型，并公开了 raw FASTQ 和完整分析代码。[原论文](https://pmc.ncbi.nlm.nih.gov/articles/PMC4823848/)

- Pilot：从 metadata 冻结 20 carcinoma/advanced adenoma + 20 normal，按年龄/性别尽量平衡。
- Flagship：全 490 subjects。
- 第一阶段比较 *Fusobacterium nucleatum*、*Parvimonas micra*、*Peptostreptococcus stomatis* 等 CRC 相关 taxa 的效应方向，Lachnospiraceae 的相反方向，以及 beta-diversity/group separation。
- 论文报告的模型 sensitivity 不是现有 ABI `amplicon_16s` 的输出；只有加入并验证同款 model 后，才比较 91.7% cancer/45.5% adenoma 等 headline 指标。

### 4.2 `rnaseq_expression`

#### 阶段 A：Airway Dex/untreated

GEO 明确提供 4 donors × 4 treatments 的 75-bp paired-end 数据、全样本 FPKM matrix 和 Dex-vs-untreated 结果。[GEO record](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE52778)；[原论文](https://doi.org/10.1371/journal.pone.0099625)

首轮只用 untreated 与 Dex 的 8 个 libraries：

- 比较每个样本 featureCounts 与 GEO 表达矩阵的 Spearman 相关；
- 对 DUSP1、KLF15、PER1、TSC22D3、C7、CCDC69、CRISPLD2 等 sentinel genes 比较 log2FC 方向；
- 报告 ABI significant gene set 与论文 316 genes 的 overlap、Jaccard、rank correlation，但不要求等于 316；
- 明示 hg19/TopHat/Cuffdiff 与新 reference/STAR/featureCounts/DESeq2 的方法差异。

Airway 运行将固定使用 `~ donor + condition`，以控制四位 donor 的配对差异。该公式已在云端 `rnaseq` 环境以独立 800-gene smoke matrix 运行通过；论文级比较仍以方向、排名、overlap 和计数相关为主，因为 hg19/TopHat/Cuffdiff 与 GRCh37.75/STAR/featureCounts/DESeq2 不会给出可逐项等同的 p-value/FDR。

#### 阶段 B：GSE60450 独立复核

GSE60450 是 12 个 mouse mammary samples，作者的公开教程说明每样本 20–25M 个 100-bp paired-end fragments，并直接提供 featureCounts count matrix。[GEO record](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE60450)；[作者计数与实验说明](https://bioinf.wehi.edu.au/edgeR/MiMB2016/index.html)

它适合作为“计数量化是否一致”的独立数据集，但完整实验是 cell type × developmental stage。当前 ABI 先做预注册的两组对比；支持 factorial design 后再重跑完整模型。

### 4.3 `wgs_bacteria`

#### 阶段 A：ST93 MRSA 小型 E2E

官方项目只有 6 个 paired-end WGS experiments、约 1.64 GB。原论文确认这些研究 isolate 为 ST93 MRSA，并用更大区域参考集的 core-SNP tree 判断它们不构成近期单克隆暴发。[官方 BioProject](https://www.ncbi.nlm.nih.gov/bioproject/286158)；[原论文](https://pmc.ncbi.nlm.nih.gov/articles/PMC5359412/)

ABI 本轮应验证：

- 6/6 `mlst` 为 ST93；
- AMRFinderPlus 检出 `mecA` 及与 MRSA 一致的 beta-lactam resistance evidence；
- assembly total length、N50、contig count、Prokka CDS/rRNA/tRNA 数在合理范围；
- 对 assembly 做 reference coverage/ANI 或 QUAST 扩展比较。

ABI 当前不产生 core-SNP phylogeny，因此不能声称复现论文的“not an outbreak”结论。这个限制本身应进入报告。

#### 阶段 B：有完成基因组 truth 的 *K. pneumoniae*

Wick 等用 Illumina+ONT 完成了 12 个 *K. pneumoniae* isolate，所有 chromosome 均得到完整 circular assembly，并公开 reads、complete assemblies 和 replicate-level统计。[原论文](https://pmc.ncbi.nlm.nih.gov/articles/PMC5695209/)；[官方项目](https://www.ncbi.nlm.nih.gov/bioproject/351909)

选两个基因组结构复杂度不同的 isolate 作为 pilot，比较 ABI short-read SPAdes contigs 对 complete chromosome/plasmids 的 recall、misassembly 和 gene/AMR/MLST concordance。不要把 short-read 未闭环本身判为 ABI 失败。

### 4.4 `easymetagenome`

#### 阶段 A：定义 mock

先从 human-gut mock 项目中固定 1–2 个 shotgun runs。该类 mock 有已知 strain membership 和预期比例，适合把 extraction bias、sequencing bias 与 bioinformatics bias 分开。[官方项目](https://www.ncbi.nlm.nih.gov/bioproject/747117)；[原始 reference-material 论文](https://pmc.ncbi.nlm.nih.gov/articles/PMC8941912/)

至少比较：

- 预期 species 的 precision/recall；
- 预期与 ABI abundance 的 Aitchison 或 rank correlation；
- 低丰度成员检出限和未预期 taxa；
- HUMAnN pathway 只做合理性检查，不把 mock 中未直接测量的 pathway abundance 当作绝对 truth。

#### 阶段 B：Zeller CRC shotgun

Zeller 等对 156 名参与者的 fecal shotgun metagenomes 分析了 CRC taxonomic markers 和功能转变，并公开 ERP005534 及补充 abundance tables。[原论文与补充数据](https://pmc.ncbi.nlm.nih.gov/articles/PMC4299606/)

- Pilot：预注册 10 CRC + 10 tumor-free controls，按项目 metadata 固定 run accession。
- Flagship：完整 discovery cohort，而不是当前 BioProject 中后来聚合的全部 1,515 experiments。
- Taxonomy：比较差异方向、effect-size rank、top-k overlap 和 group separation。
- Function：比较 fiber degradation、host carbohydrate/amino-acid utilization、LPS metabolism 的方向和 pathway rank。
- 不比较论文 classifier 或 FIT-combination sensitivity，除非 ABI 增加同款模型并独立验证。

### 4.5 `metagenomic_plasmid`

#### 阶段 A：SCAPP real plasmidome

SCAPP 论文同时提供真实 human-gut plasmidome 和基于 PLSDB 的可评分参考。SRR11038083 为 18,616,649 PE150 pairs；论文参考集包含 74 个 plasmids，median 2.1 kb。[原论文](https://doi.org/10.1186/s40168-021-01068-z)；[ENA run](https://www.ebi.ac.uk/ena/browser/view/SRR11038083)

这 74 条不是论文仓库中的静态 truth FASTA。原方法使用 `PLSDB v.2018-12-05`，将 metaSPAdes contigs 与数据库比对，选出被 contigs 覆盖超过 90% 长度的质粒，才得到 74 条 gold standard。作者 GitHub 仓库只发布了软件、PSG 数据和小型测试 fixture，没有这 74 条的 accession/FASTA 清单。因此，本项的 truth readiness gate 是：找到并校验该 PLSDB 快照，按补充方法重建后冻结 accession、FASTA 和 checksum；在此之前不宣称已完成 74-plasmid 精确复现。

推荐双轨评分：

1. **reference-based**：对 74 个参考质粒计算 nucleotide-level precision/recall/F1、完整度和 duplication。
2. **evidence-based**：对 reference 未覆盖的预测，统计 circularity、replication/MOB/oriT、plasmid-associated genes、AMR genes 和 read coverage consistency。

论文中 SCAPP 输出 82 个预测，P/R/F1 为 17.1/35.9/23.1%；还发现 6 个 resistance genes，60/77 个有功能注释的 genes 属于 plasmid-associated functions。ABI 可以将这些作为方向性参照，但不应要求所有工具和数据库版本产生完全相同的计数。

#### 阶段 B：多模态 hospital sewage flagship

PlasMAAG 论文公开 5 个 Danish hospital sewage samples 的 short-read metagenome、metaplasmidome 和 long-read metagenome，以及 24 个 Spanish short-read samples；这正好为 AutoPlasm 的 detection、reconstruction、cross-sample clustering 和 long-read evidence 提供外部支持。[原论文及数据说明](https://www.nature.com/articles/s41587-026-03005-7)；[ENA project](https://www.ebi.ac.uk/ena/browser/view/PRJEB85938)

首轮只选 1 个 Danish sample，并冻结论文公开的 assembly archive。全量 29 samples 应放在 128–256 GB RAM 的独立旗舰实验，不与 P0 调试混跑。

### 4.6 `viral_viwrap`（本轮仅保留适配层门禁）

ViWrap 是 ABI 封装的现有上游软件，`viwrap_compat` 将它作为单个外部黑盒步骤调用，ABI 不重写其内部算法。因此，本轮可以跳过“重新证明 ViWrap 算法本身有效”的论文级复现，将时间和存储用于 ABI 自有或深度编排的工作流。

但不能把 ViWrap 插件完全跳过。每次发布仍保留以下低成本门禁：

- 插件可发现，manifest、DAG、schema 和 tool contract 通过静态校验；
- `plan`/`dry-run` 能产生正确的 ViWrap 1.3.1 命令，输入和输出路径边界正确；
- 用冻结的小型输出 fixture 验证 summary 解析、artifact manifest、标准表和报告；
- 对缺少可执行程序、13 个配套 Conda 环境或 8 类数据库的情况明确 fail，不得 silent skip。

2026-07-15 的代码门禁中，ViWrap 单元、兼容 runner 和 CLI 发现相关的 22 个定向测试均通过。云端当前只有插件 manifest 和 DAG，尚未部署 ViWrap 可执行程序、多环境集和数据库 bundle；它继续排除在正式 runtime lock 外。因此本轮不下载 Guaymas Basin reads 或 ViWrap 数据库。

以下内容仅作为未来将 `viral_viwrap` 纳入正式 release scope 时的备选验收，不属于当前批次。

最合适的候选不是任意 virome，而是 ViWrap 原论文的 Guaymas Basin 示例，因为它和 ABI wrapper 的方法边界最接近。[原论文](https://doi.org/10.1002/imt2.118)

论文以 18,000 scaffolds、10%/15% read subsets 和 98 MAG host DB 为输入，得到 124 viral scaffolds、91 viruses/vMAGs、27 taxonomy、11 hosts、9 families、约 20.4% total relative abundance 和 23 AMG KOs。验收应包含：

- exact sequence/ID overlap；
- taxonomy 与 host assignment overlap；
- count/abundance 的预定义容差；
- 未匹配结果按数据库变化、subset 变化、软件版本变化分类。

只有在 `viral_viwrap` 正式数据库 bundle 和 runtime lock 进入 release scope 时，才启动该实验并将其纳入 release certification。

### 4.7 `metatranscriptomics`（能力缺口验证）

Franzosa 等的 matched gut metagenome/metatranscriptome 是一个很好的目标数据集：8 subjects、三种保存条件，并有清楚的功能结论。[原论文](https://pubmed.ncbi.nlm.nih.gov/24843156/)；[官方 BioProject](https://www.ncbi.nlm.nih.gov/bioproject/188481)

但当前 ABI 无法直接产生这些结论。现阶段最多可以用一个 frozen RNA run 做：

- fastp read survival；
- 对预定义 concatenated microbial references 的 mapping rate；
- featureCounts 是否产生非空、可复现的 gene counts。

这些只证明执行链能运行，不能称为“宏转录组论文复现”。进入论文级复现前至少需要：rRNA depletion/filtering、多物种或 gene-family reference、HUMAnN/KO/pathway quantification、跨样本 normalization/statistics，以及 matched metagenome–metatranscriptome comparison。

## 5. 统一验收框架

每个数据集都应保存一份版本化的 `dataset_manifest`，包含：paper DOI、BioProject/study/run accessions、sample→condition 映射、FASTQ checksum、library layout、primer/read length、reference/annotation、数据库版本、纳入/排除规则和论文 truth table。

### Level 0：数据与执行完整性

- accession 和样本 metadata 可追溯；
- checksum、R1/R2 配对、read count、read length 通过；
- ABI 成功产生标准表、报告、日志和 provenance；
- 无 silent skip、空表伪成功或未记录的 fallback。

### Level 1：组件级 truth

- Mock：precision、recall、F1、abundance error；
- WGS：MLST、AMR、assembly/reference coverage、annotation；
- Plasmid/virus：sequence overlap、circularity、taxonomy/host/function evidence；
- RNA-seq：sample-level count correlation、mapping rate、sentinel genes。

### Level 2：论文级生物学方向

- effect direction concordance；
- log2FC/abundance effect 的 Spearman correlation；
- top-k overlap、Jaccard、rank-biased overlap；
- alpha/beta 或 PCA/PCoA group separation；
- pathway/taxon/gene-set enrichment direction。

### Level 3：ABI 实用性

在相同输入和硬件上，与“手工 scripted pipeline”及“通用 agent”比较：

- 首次成功所需 wall time；
- 人工操作数与澄清次数；
- 失败恢复时间和可诊断性；
- 是否记录 tool/database/reference 版本和 checksum；
- 标准表、methods、limitations 和可复现 report 的完整度；
- 重跑一致性和无意参数漂移。

## 6. 不应采用的错误验收方式

- 不要求不同 aligner、denoiser、taxonomy DB 或 reference build 产生完全相同的 p-value、ASV、gene 或 species 数。
- 不把“论文 headline classifier accuracy”归因给只输出 abundance table 的 ABI workflow。
- 不把 short-read assembly 未闭环判为 WGS pipeline 错误。
- 不把 PLSDB 未命中的 novel plasmid 直接全部算作 false positive。
- 不把 metatranscriptomics 的 STAR+featureCounts 成功运行描述为群落功能结论已复现。
- 不从大型 BioProject 随意抽取 run；pilot subset 必须在执行前按 metadata 预注册并冻结。

## 7. 建议的执行批次与退出门槛

| 批次 | 数据 | 进入下一批的最低门槛 |
| --- | --- | --- |
| Batch 0 | DADA2 Extreme + existing synthetic fixtures | manifest/QC 全绿；mock truth 可计算；无空表伪成功 |
| Batch 1 | PRJNA286158 + SRR11038083 | 6/6 ST93；MRSA evidence；plasmid reference/evidence 双轨评分完成 |
| Batch 2 | GSE52778 8 samples + Baxter 20/20 | sentinel direction 预注册完成；16S group/taxa 方向可解释；限制写入报告 |
| Batch 3 | Zeller 10/10 | taxonomy/function 的容差标准通过；资源 manifest 固定 |
| Batch 4 | 各 flagship full cohort | 小队列阈值已冻结；不得看到全量结果后再修改主要终点 |

每个批次完成后应产生：输入 manifest、ABI resolved config、执行与资源 provenance、机器可读 comparison table、图表、偏差解释、pass/fail summary 和一页式结论。只有当小数据的生物学验收和失败诊断均稳定后，才值得支付全量队列的存储与计算成本。

## 8. 2026-07-16 云端数据准备快照

统一数据根为 `/root/autodl-tmp/abi-real-data`，位于云主机大数据盘，而不是系统盘。最新检查时数据盘剩余约 138 GB。

### 8.1 DADA2 Extreme

- `SRR2990088_1.fastq.gz` 和 `SRR2990088_2.fastq.gz` 已下载完成；
- ENA 官方 MD5 全部通过，`gzip -t` 通过；
- R1/R2 均为 8,161,940 行，即各 2,040,485 条 FASTQ records，双端数量一致；
- ABI sample sheet 以 `check_files=True` 解析成功；
- RDP v16 SINTAX 数据库位于 `resources/autoplasm/amplicon_taxonomy/rdp_16s_v16.fa`，检出 13,212 条有效 `;tax=` 注释序列；
- cutadapt 5.2、vsearch 2.31.0、MAFFT 7.526 和 FastTree 2.2.0 均已在声明的 `amplicon` Conda 环境中定位；
- 真实配置位于 `configs/dada2_extreme.yaml`，SHA-256 为 `157fefb0a9b2a411812e9ce9a934e681c023ce276e1f03b54e98291206afc5cb`；
- 9 步 execution plan 已在 `results/dada2_extreme/execution_plan.json` 生成，实际 R1/R2、V4 primer override、taxonomy DB 和 diversity script 路径均已绑定；
- ABI dry-run 返回 `status=success`，产生 `commands.tsv`、`resolved_inputs.tsv`、`resources.json`、`tool_versions.tsv`、`methods.md`、`run_summary.json` 和 HTML/Markdown 报告。
- 首次真实运行在 FastTree 前暴露了通用路径传播缺陷：已存在的 `combined.fasta` 被错误地传播给本应读取 `aligned.fasta` 的建树步骤；该问题已以回归测试修复。
- 完整重试使用 `configs/dada2_extreme_retry.yaml`（SHA-256 `0d18b11ef468354cfb3bb50c07fa3f3caa6703f57a1c8a4b8348b06018e8bf83`）并写入独立的 `results/dada2_extreme_retry/`；9/9 步均返回成功，生成 26 个 ASV、26 条 taxonomy、26 条对齐序列、1,377-byte Newick 树、alpha diversity 和 HTML/Markdown 报告；ABI 结果目录在允许单样本 beta-diversity 及禁用 OTU 表为空的条件下验证通过。

ENA 中的首条 R1/R2 序列均不以 515F/806R primer 开头，和已去 primer 的归档 reads 一致。因此真实运行中 cutadapt 应作为无损通过步骤，并将 read retention 作为门禁，不强行二次裁剪。

Stanford PURL 元数据已确认官方 `Extreme_Data.zip` 大小为 6,008,820 bytes，MD5 为 `6d4d04222c8f85126e5a736d180eaa3b`。云主机能访问 PURL 元数据域，但到 `stacks.stanford.edu:443` 的 IPv4 二进制下载在直连、aria2 和云端网络加速三种方式下均停在 0 bytes。为避免伪 truth，不使用非官方镜像替代；精确 ASV truth 评分暂缓，但不阻断原始输入、真实执行和产物完整性验证。

### 8.2 ST93 MRSA 与 SCAPP

- `PRJNA286158` 的 6 个 paired-end runs 已生成 12 文件 ENA MD5 清单和 6 样本 ABI sample sheet；
- `SRR11038083` 已生成双端 ENA MD5 清单和 ABI plasmid sample sheet；
- `PRJNA286158` 的 12 个 FASTQ 已全部通过 ENA 官方 MD5，`gzip -t` 通过，且 `.download_verified` 标记已存在；ABI 以 `check_files=True` 解析出 6 个 paired samples；
- WGS 真实配置已冻结为 `configs/wgs_st93_mrsa.yaml`（SHA-256 `b2bfbf970bf45cfdd1af06f7595fc230d9aedccd8ed8e6bd2d333d699a2714e5`）；其 30 步计划正确覆盖 6 个样本和 fastp、SPAdes、Prokka、MLST、AMRFinderPlus 五个阶段；
- WGS `dry-run` 返回 `status=success`，写出 plan、commands、resolved inputs、tool versions、methods、环境和报告等 provenance；以 ABI 实际激活方式检查时，fastp 1.3.5、SPAdes 4.3.0、Prokka 1.15.6、MLST 2.35.0、AMRFinderPlus 4.2.7 均可启动，AMRFinder 数据库版本为 `2026-05-15.1`；
- 真实 WGS 配置使用独立输出目录 `configs/wgs_st93_mrsa_real.yaml`，已再次通过 30 步文件预检并启动；它保留原始已验收 sample sheet，不覆盖 dry-run 证据目录。
- 云端实际可用硬件为 16 vCPU / 120 GB RAM（而非宿主机展示的 128 CPU / 约 1 TiB）。首次真实运行的 SPAdes 未显式传递内存上限，工具按 250 GB 默认值估计后其子进程收到 `SIGKILL`；该失败输出已保留作 provenance，不能据此归因于 reads 损坏。
- ABI 的 `wgs_bacteria` 现将 `assembly.memory_gb` 作为可配置参数，默认 80 GB，并渲染为 SPAdes `-m`。云端重跑配置 `configs/wgs_st93_mrsa_retry.yaml`（SHA-256 `87dfed18f0df6ca350e97cbefff20aaf3821e32910ca8a44f3063b2f2aa90142`）使用单样本串行、8 threads、80 GB 上限和独立结果目录；预检命令已确认 `spades.py … -t 8 -m 80`。首个样本 SRR2057030 已成功生成约 2.8 MB 的 `contigs.fasta`，越过了原先失败阶段，后续样本的线程提升须以本次的实际峰值和完成时间为依据。
- SRR2057030 已完成五个真实工具阶段：MLST 返回 *S. aureus* ST93；AMRFinderPlus 检出 `mecA`（668/668 aa、100% coverage、100% identity）及 methicillin beta-lactam resistance evidence，符合该 ST93 MRSA 验证集的预注册生物学预期。该结果是单样本早期核对，6/6 一致性仍待其余样本完成后报告。
- 重跑进行中时，已完成的 SRR2057030、SRR2057031、SRR2057032 和 SRR2057035 均为 MLST ST93，且均有 `mecA` 100% coverage/identity 调用；这是 4/6 的中间结果，不能提前表述为最终 6/6 结论。
- 重跑于 2026-07-17 01:18:34 完成，`run_summary/progress` 记录为 `success`、30/30 steps、0 failed。`abi validate-result --require-nonempty-tables` 返回 `valid=true`：6 行 assembly、6 行 MLST、145 行 AMR 及其余非空标准表与全部必要 provenance/report artifacts 均通过。6/6 样本均为 *S. aureus* ST93，且每例 `mecA` 都是 100% coverage、100% identity；这完成了本批预注册的 WGS MLST 与 MRSA AMR 端点验证。

WGS 最终报告应采用下列图标 scorecard，而非一个脱离 truth 定义的“总正确率”：

| 图标 | 验证端点 | 结果 | 含义 |
| --- | --- | --- | --- |
| ✅ | 工作流执行 | 30/30 steps，0 failed | 工程 E2E 成功 |
| ✅ | 结果完整性 | `validate-result` valid | 产物、标准表、provenance 与报告齐全 |
| 🧬 | MLST 一致性 | 6/6 ST93 | 与论文给出的 ST93 isolate 属性一致 |
| 🛡️ | MRSA AMR 证据 | 6/6 `mecA` exact | 与 MRSA beta-lactam resistance 预期一致 |
| ⏳ | core-SNP 流行病学结论 | 未评估 | 当前 WGS workflow 不含 core-SNP tree，不能据此复现“非近期暴发”结论 |
- `SRR11038083` 的 R1/R2 已全部通过 ENA 官方 MD5 和 `gzip -t`，并于 2026-07-16 重新写入 `.download_verified` 标记；首次失败日志来自 R1 尚未写完时的并发校验，不能作为数据损坏证据；
- 当前实际占用约为 ST93 1.9 GB、SCAPP 2.0 GB，已无 `.aria2` 部分文件；
- SCAPP 官方 supplementary PDF 和 simulation-reference TSV 已下载，并在 `references/scapp/SHA256SUMS` 中冻结。

SCAPP 74-plasmid 评分集的 **数据库前提已 ready，但 truth 重建尚未完成**：已获得并冻结 PLSDB v2018-12-05 FASTA（14,739 条序列），其 SHA-256 `46c74eaa6f953896422cb5465a88008e0f72af2f36fa5bfcdc2521638c4d461e` 已在云端复核通过。下一步必须严格按原文：将样本 contigs 与该快照比对，选取 contig 覆盖超过 90% 长度的质粒，得到并冻结 74 条（或可审计的实际重建数）reference truth。仅有数据库快照不等价于已完成 74 条 reference-based 精确复现。

### 8.3 Airway RNA-seq 对照资源

已从 NCBI GEO 官方目录下载并验证三份原文对照文件，均位于云端大数据盘
`/root/autodl-tmp/abi-real-data/references/airway_gse52778/`：

- `GSE52778_series_matrix.txt.gz`：SHA-256 `67db46e962f795b9dd61fa6b4279f2678c6b2b9bf1df035fbc22fcf81b5e879e`；
- `GSE52778_All_Sample_FPKM_Matrix.txt.gz`：SHA-256 `e7e54e8f564d417b47843e82c2a7140b92a783d6b5078816bae15d07fca126f6`；
- `GSE52778_Dex_vs_Untreated_gene_exp.diff.gz`：SHA-256 `6c6ca5ce509e98ea9d5fb9aef698b2a0fbf4c778997c7ceaf95a42cbf15eb63f`。

三者均通过 `gzip -t`；差异表含 gene ID、log2 fold change、p/q value 和显著性标签，可在 ABI 的原始 FASTQ 重跑完成后建立方向、排名和重叠的 comparison table。ENA 官方 metadata 已确认不含 albuterol 的 8 个预注册 paired-end runs 是 SRR1039508/09、SRR1039512/13、SRR1039516/17、SRR1039520/21，分别覆盖四位 donor 的 untreated 与 Dex 条件。

这 8 个 run 的 ENA `fastq_ftp`、官方 MD5、文件字节数及 sample title 已冻结至 `ena_airway_dex_untreated_runs.tsv`（SHA-256 `cb702a2aea539d13c31eb0bcd480599f54980c71f5b556be89ad528e2758b864`）；16 个 FASTQ 合计 25,023,315,748 bytes（23.30 GiB）。筛选显式排除 `Alb` 与 `Alb_Dex`，并验证最终恰好为 8 个 run。原始 FASTQ 下载应在 GRCh37.75 FASTA/GTF 与 STAR index 准备完成后执行，以避免在 133 GB 可用盘上留下无法立即运行的大型中间数据。

当前云端 `star_index` 是 *E. coli* 参考（约 48 MB），并非 Airway 所需的人类参考；因此原始 FASTQ 与人类 GRCh37.75 STAR index 必须作为下一阶段成套准备。不能在该资源缺失时把 GEO 对照表或错误物种索引当作 RNA-seq E2E 成功证据。

### 8.4 ViWrap 决策

ViWrap 本轮不下载论文 reads 或数据库 bundle，不做独立的上游算法生物学复现。只保留 ABI wrapper 的插件发现、命令构建、输出解析、报告和缺失资源报错门禁。当日 22 个定向测试均通过。

## 9. 实时验证记分卡（截至 2026-07-17）

不使用脱离 truth 定义的单一“正确率”。图标分别表示工程执行、输入/产物完整性、可比较的生物学终点和明确未覆盖的边界；`⏳` 不计为失败，也不应被表述为已验证。

| 工作流与数据集 | 执行与完整性 | 生物学比较 | 当前结论 |
| --- | --- | --- | --- |
| 16S DADA2 Extreme（SRR2990088） | ✅ 9/9 steps；26 ASV、taxonomy、树和报告均非空；FASTQ ENA MD5/gzip 通过 | ⏳ 官方 `Extreme_Data.zip` truth 因云端网络无法下载，未计算 ASV P/R/F1 | 工程真实 E2E 通过；精确 mock truth 待官方文件可达后补算 |
| WGS ST93 MRSA（PRJNA286158） | ✅ 30/30 steps、`validate-result` 有效、标准表和 provenance 完整 | 🧬 6/6 MLST=ST93；🛡️ 6/6 `mecA` 100% coverage/identity | 本批预注册的 WGS MLST/MRSA 端点通过；⏳ 不含 core-SNP tree，未复现流行病学结论 |
| SCAPP plasmidome（SRR11038083） | ✅ 原始 FASTQ ENA MD5/gzip 通过；PLSDB v2018-12-05 FASTA SHA-256 已验证；Bakta v6 light 精确预检通过 | ⏳ 仍须按原文 contig-coverage 规则重建并冻结 74-plasmid truth | retry6 运行中；只有全流程成功并完成 truth/evidence 双轨评分后，才可报告论文级复现 |
| Airway RNA-seq（GSE52778，Dex/untreated） | ✅ 16 个预注册 FASTQ ENA MD5/gzip 通过；GEO FPKM 与差异表已冻结；`~ donor + condition` smoke 通过 | ⏳ 人类 GRCh37.75 STAR index 与真实 8-sample 运行尚未完成 | 不得把 GEO 对照表或合成 smoke 表述为 FASTQ E2E 成功 |
| ViWrap | ✅ ABI 适配层 22 个定向测试通过 | ⏳ 不进行上游算法论文复现 | 保持 release scope 外，等待独立多环境与数据库 bundle 部署 |

### 9.1 云端恢复后的顺序

1. 用 SCAPP `final.contigs.fa` 完成 Bakta v6 light 的真实预检（不得跳过 tRNA 检测）；成功后以新结果目录运行 retry6。
2. 校验完整 Bakta v6 下载的官方 MD5、解压和实际注释，再把 canonical 数据库链接从 light 切换到已验证的 full。
3. 建立 GRCh37.75 STAR index，运行 8 个 Airway FASTQ，并用冻结的 GEO `Dex_vs_Untreated` 表输出方向、排名、重叠和计数一致性图。
4. 获得官方 DADA2 truth，并按已验证的 PLSDB v2018-12-05 快照重建 74-plasmid truth 后，补充精确 P/R/F1；此前只报告 evidence-based 结果和未覆盖项。
