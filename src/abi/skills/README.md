# AutoPlasm Skills 详细说明

`skills/` 目录是 AutoPlasm 的工具使用契约。它面向两类读者：

- 人类维护者：确认每个工具的用途、输入、输出、资源要求和失败排查方式。
- agent 智能体：在修改配置、生成计划、执行 dry-run、解释 provenance 或排查失败时，按统一规则调用 AutoPlasm CLI。

## 安装 Skills 到 Claude Code

```bash
# 安装所有 skills 到 ~/.claude/skills/abi/
abi install-skills

# 自定义目标目录
abi install-skills --target /path/to/skills

# 覆盖已有文件
abi install-skills --force
```

安装后，Claude Code 会自动加载 skills 目录中的所有 SKILL.md 文件。

## 0. Agent Skills

| 文件 | 用途 |
| --- | --- |
| `abi_agent/SKILL.md` | **ABI CLI agent skill** — 教 agent 如何使用 pip 安装后的 `abi` 命令（含 --output-json、MCP、OpenAI tools 等传输方式）。 |
| `autoplasm_agent/SKILL.md` | 仓库级 operator skill，说明 agent 如何在源码开发模式下使用 CLI、配置、registry、资源检查和 provenance。

Python pipeline 的权威入口是 `plugins/metagenomic_plasmid/pipeline_dag.yaml`、
`plugins/metagenomic_plasmid/tool_registry.yaml`、`plugins/metagenomic_plasmid/tool_contracts/`
以及 `src/abi/executor.py` 的运行时契约校验。Markdown skill 文件负责把同一份契约写清楚，避免 agent 手工拼接不可追踪的命令。

## 1. 文件类型

| 文件 | 用途 |
| --- | --- |
| `autoplasm_agent/SKILL.md` | 仓库级 operator skill，说明 agent 如何安全使用 CLI、配置、registry、资源检查和 provenance。 |
| `{tool}/SKILL.md` | 每个注册外部工具一份 skill，说明工具何时被选中、需要哪些输入、在哪个 mamba 环境运行、命令模板如何渲染、失败时如何排查。 |
| `README.md` | 当前文件，作为 skills 目录的维护说明、详细索引和同步清单。 |

## 2. Agent 使用总原则

agent 处理 AutoPlasm 任务时必须保留这个控制路径：

```text
validate-sample-sheet
check-tools
check-resources
plan
dry-run
inspect provenance
run
report
```

除非正在调试单个失败步骤，否则不要直接运行 fastp、MEGAHIT、geNomad 等工具。直接运行会绕过 `commands.tsv`、stdout/stderr、资源状态和标准表记录。

dry-run 只证明 planner、命令模板和 provenance 可以生成。真实生物信息学结论必须来自 `run` 产生的工具输出、标准表和报告。
即使某个组件工具有文献支持，也不能直接声称整条 ABI 工作流已被科学验证；
整条路线的验证要求见 `docs/workflow_validation.md`。

## 3. 每个工具 skill 的必需结构

每个 `{tool}/SKILL.md` 应包含以下小节：

| 小节 | 必须说明的内容 |
| --- | --- |
| `Purpose` | 工具在 AutoPlasm 中解决什么问题。 |
| `When to Use` | 哪些平台、步骤或配置会选择该工具。 |
| `Inputs` | registry 输入、命令模板参数和上游步骤提供的字段。 |
| `Outputs` | 工具原始输出、标准化输出和 provenance 日志位置。 |
| `Environment` | 对应 `envs/*.yml`、runtime env_name、executable 和本地 `.mamba` 解析规则。 |
| `Command Template` | 与 `plugins/metagenomic_plasmid/tool_registry.yaml` 完全一致的 command template。 |
| `Auto-selection Rules` | default/optional、required/recommended、平台路由和限制。 |
| `Interactive Parameters` | 用户需要选择或确认的阈值、数据库、模型、策略或跳过逻辑。 |
| `Failure Handling` | 真实运行前检查项，以及失败后查看 `commands.tsv` 和 step logs 的顺序。 |
| `Normalization` | 原始输出如何归一化到 `tables/*.tsv` 或稳定下游路径。 |
| `Agent Usage Notes` | agent 不应绕过 CLI、不能夸大 dry-run、需要先更新配置再执行计划。 |
| `Example` | 推荐 dry-run、run 或 report 示例。 |

如果某个工具需要大型数据库、模型、参考图、索引或特殊输入，必须在 `Inputs`、`Interactive Parameters` 和 `Failure Handling` 中重复明确，而不是只写在示例里。

## 4. 当前工具 skill 索引

以下索引来自当前 `plugins/metagenomic_plasmid/tool_registry.yaml` 和 `autoplasm list-tools` 输出。

| 工具 | 类别 | 默认状态 | 必需性 | 运行环境 | Skill |
| --- | --- | --- | --- | --- | --- |
| `fastp` | `qc` | default | required | `autoplasm-qc` | [fastp](fastp/SKILL.md) |
| `fastqc` | `qc` | default | recommended | `autoplasm-qc` | [fastqc](fastqc/SKILL.md) |
| `multiqc` | `qc` | default | recommended | `autoplasm-qc` | [multiqc](multiqc/SKILL.md) |
| `nanoplot` | `qc` | default | recommended | `autoplasm-qc` | [nanoplot](nanoplot/SKILL.md) |
| `filtlong` | `qc` | default | recommended | `autoplasm-qc` | [filtlong](filtlong/SKILL.md) |
| `hifiadapterfilt` | `qc` | default | recommended | `autoplasm-qc` | [hifiadapterfilt](hifiadapterfilt/SKILL.md) |
| `megahit` | `assembly` | default | required | `autoplasm-assembly` | [megahit](megahit/SKILL.md) |
| `metaspades` | `assembly` | optional | required | `autoplasm-assembly` | [metaspades](metaspades/SKILL.md) |
| `metaflye` | `assembly` | default | required | `autoplasm-assembly` | [metaflye](metaflye/SKILL.md) |
| `hifiasm_meta` | `assembly` | default | recommended | `autoplasm-assembly` | [hifiasm_meta](hifiasm_meta/SKILL.md) |
| `opera_ms` | `assembly` | default | required | `autoplasm-assembly` | [opera_ms](opera_ms/SKILL.md) |
| `quast` | `assembly_qc` | default | recommended | `autoplasm-assembly` | [quast](quast/SKILL.md) |
| `genomad` | `plasmid_detection` | default | required | `autoplasm-plasmid-detect` | [genomad](genomad/SKILL.md) |
| `plasme` | `plasmid_detection` | optional | recommended | `autoplasm-plasmid-detect` | [plasme](plasme/SKILL.md) |
| `plasx` | `plasmid_detection` | optional | recommended | `autoplasm-plasmid-detect` | [plasx](plasx/SKILL.md) |
| `plasmaag` | `plasmid_binning` | optional | recommended | `autoplasm-plasmid-binning` | [plasmaag](plasmaag/SKILL.md) |
| `gplas2` | `plasmid_binning` | optional | recommended | `autoplasm-plasmid-binning` | [gplas2](gplas2/SKILL.md) |
| `plasmidfinder` | `typing` | optional | recommended | `autoplasm-annotation` | [plasmidfinder](plasmidfinder/SKILL.md) |
| `mob_typer` | `typing` | optional | recommended | `autoplasm-annotation` | [mob_suite](mob_suite/SKILL.md) |
| `copla` | `typing` | optional | recommended | `autoplasm-annotation` | [copla](copla/SKILL.md) |
| `plasmidhostfinder` | `host_prediction` | optional | recommended | `autoplasm-annotation` | [plasmidhostfinder](plasmidhostfinder/SKILL.md) |
| `kraken2` | `host_prediction` | optional | recommended | `autoplasm-stats` | [kraken2](kraken2/SKILL.md) |
| `metaphlan` | `host_prediction` | reads default | recommended | `autoplasm-stats` | [metaphlan](metaphlan/SKILL.md) |
| `bakta` | `annotation` | default | recommended | `autoplasm-annotation` | [bakta](bakta/SKILL.md) |
| `abricate` | `annotation` | default | recommended | `autoplasm-annotation` | [abricate](abricate/SKILL.md) |
| `amrfinderplus` | `annotation` | default | recommended | `autoplasm-annotation` | [amrfinderplus](amrfinderplus/SKILL.md) |
| `mob_suite` | `annotation` | optional | recommended | `autoplasm-annotation` | [mob_suite](mob_suite/SKILL.md) |
| `isescan` | `annotation` | default | recommended | `autoplasm-annotation` | [isescan](isescan/SKILL.md) |
| `integronfinder` | `annotation` | default | recommended | `autoplasm-integronfinder` | [integronfinder](integronfinder/SKILL.md) |
| `bowtie2` | `abundance` | default | required | `autoplasm-abundance` | [bowtie2](bowtie2/SKILL.md) |
| `minimap2` | `abundance` | default | required | `autoplasm-abundance` | [minimap2](minimap2/SKILL.md) |
| `samtools` | `abundance` | default | required | `autoplasm-abundance` | [samtools](samtools/SKILL.md) |
| `coverm` | `abundance` | default | recommended | `autoplasm-abundance` | [coverm](coverm/SKILL.md) |
| `blast` | `comparative_genomics` | optional | recommended | `autoplasm-annotation` | [blast](blast/SKILL.md) |
| `mmseqs2` | `comparative_genomics` | optional | recommended | `autoplasm-annotation` | [mmseqs2](mmseqs2/SKILL.md) |
| `mummer` | `comparative_genomics` | optional | recommended | `autoplasm-annotation` | [mummer](mummer/SKILL.md) |
| `clinker` | `comparative_genomics` | optional | recommended | `autoplasm-visualization` | [clinker](clinker/SKILL.md) |
| `fastspar` | `network` | default | recommended | `autoplasm-stats` | [fastspar](fastspar/SKILL.md) |
| `report_markdown` | `report` | default | recommended | `autoplasm-base` | [report_markdown](report_markdown/SKILL.md) |

## 5. 平台到工具的默认路线

| 平台 | QC | Assembly | Plasmid detection | Host evidence | Annotation/typing | Abundance |
| --- | --- | --- | --- | --- | --- | --- |
| `illumina` | `fastp`, `fastqc`, `multiqc` | `megahit` by default, `metaspades` optional | `genomad` | `metaphlan` | `bakta`, `amrfinderplus`, `abricate`, `isescan`, `integronfinder` | `bowtie2`, `samtools`, `coverm` |
| `ont` | `nanoplot`, `filtlong`, `multiqc` | `metaflye` | `genomad` | `metaphlan --long_reads` | same annotation defaults | `minimap2`, `samtools`, `coverm` |
| `pacbio_hifi` | `hifiadapterfilt`, `multiqc` | `hifiasm_meta` | `genomad` | `metaphlan --long_reads` | same annotation defaults | `minimap2` with `map-hifi`, `samtools`, `coverm` |
| `hybrid` | short-read QC plus long-read QC | `opera_ms` | `genomad` | `metaphlan` on short reads | same annotation defaults | short and long tracks are recorded separately |
| `assembly` | skipped | skipped | `genomad` | explicit config only | configured typing/annotation tools | skipped unless reads and abundance module are configured |

## 6. 常见真实运行资源

Tool availability only proves that the executable can be resolved. Real runs often need resource paths:

| 工具 | 常见必填资源或参数 |
| --- | --- |
| `genomad` | `resources.genomad.database` |
| `plasme` | PLASMe database |
| `plasx` | annotations, gene calls, model |
| `plasmidfinder` | PlasmidFinder database |
| `plasmidhostfinder` | host prediction database/model |
| `mob_suite` | MOB-suite database directory |
| `bakta` | Bakta database, light database is enough for smoke testing |
| `copla` | `refgraph`, `reflist` |
| `blast` | BLAST database |
| `mmseqs2` | MMseqs2 database |
| `kraken2` | Kraken2 database |
| `mummer` | reference plasmid FASTA |
| `clinker` | annotated GenBank files |

Missing resources should be fixed in project config. Do not edit generated provenance to hide missing inputs.

## 7. 更新规则

When changing a registry entry:

1. Update `plugins/metagenomic_plasmid/tool_registry.yaml`.
2. Update the matching `plugins/metagenomic_plasmid/tool_contracts/{tool}.yaml`.
3. Update the matching `{tool}/SKILL.md`.
4. Update `envs/*.yml` if executable availability changes.
5. Run `autoplasm list-tools` and check the table still matches this README.

When changing CLI behavior:

1. Update [../../../README.md](../../../README.md).
2. Update [../../../docs/agent_usage.md](../../../docs/agent_usage.md).
3. Update [autoplasm_agent/SKILL.md](autoplasm_agent/SKILL.md).
4. Update affected tool skills when inputs, outputs, command templates, resources, or normalization behavior changes.

When adding a new tool skill:

1. Add an entry to `plugins/metagenomic_plasmid/tool_registry.yaml`.
2. Add or update the matching environment YAML.
3. Create `{tool}/SKILL.md` using the required section structure above.
4. Add parser/normalization notes if the tool feeds `tables/*.tsv`.
5. Add or update tests and fixtures when output parsing is implemented.

## 8. 验证命令

Use these after documentation or skill updates:

```bash
PYTHONPATH=src python -m abi.autoplasm.cli --help
PYTHONPATH=src python -m abi.autoplasm.cli list-tools --config examples/config_minimal.yaml
PYTHONPATH=src python -m abi.autoplasm.cli dry-run --config examples/config_minimal.yaml
git diff --check
```
