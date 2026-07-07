# 论文评测协议

ABI 论文评测比较四种从相同仓库上下文生成有效生物信息流程计划的方式：

1. README/手动 CLI。
2. 直接 Python API。
3. 通用 LLM tool-calling。
4. ABI 介导的规划与执行。

冻结的任务矩阵位于 `bench/paper_tasks/tasks.yaml`。指标定义位于
`bench/paper_tasks/metrics_schema.yaml`，包括计划有效性、命令正确性、
dry-run 成功、溯源完整度、人工干预次数，以及到达有效计划的时间。

所有评测臂都从同一个干净 checkout 开始，并且只能使用任务文件中声明的输入。
dry-run 输出 JSON 是评分的权威执行轨迹。只要评测者需要修正命令、补充遗漏参数，
或解释失败计划，就应计为一次人工干预。

生成产物应写入已忽略的结果目录，例如 `/tmp/abi-paper-*` 或 `results/`；
仓库中只提交基准定义和最终指标表。
