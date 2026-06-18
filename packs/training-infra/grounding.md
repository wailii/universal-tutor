# 对标锚点清单 · 训推/调度

本文件是 `training-infra` 包专属的「业界对标」检索锚点。通用的对标**纪律**（必须联网、严禁编造、优先一手来源、以出处评分）见 `references/grounding_protocol.md`；本文件只给**这门课该对标谁**。

学到相关节点时，至少覆盖以下与该节点相关的几个。这是锚点不是封顶，搜到更新的实践就用更新的。

## 调度 / 集群底座（经典与开源）
- Google Borg / Omega（集群管理与调度的奠基论文）
- Kubernetes；批调度 Volcano、Kueue
- Microsoft Singularity（面向 DL 的全局调度论文）
- Slurm（HPC 经典）、Ray（分布式应用/调度）
- YARN（大数据调度的对照）

## 推理引擎 / 推理优化
- vLLM（PagedAttention 论文是必读锚点）
- SGLang、TensorRT-LLM、Hugging Face TGI
- 关键技术：continuous batching、量化(INT8/FP8/INT4)、投机解码、PD（prefill/decode）分离

## 训练框架 / 大规模训练
- Megatron-LM、DeepSpeed（ZeRO 系列论文）、PyTorch FSDP
- 并行策略：DP / TP / PP / SP 的取舍

## 国内顶尖同类平台（实战对标，必须能说出差异点）
- 阿里云 PAI + 灵骏（智算集群）
- 华为云 ModelArts
- 百度百舸（AIHC）
- 火山引擎（字节）机器学习平台 / veMLP
- 商汤 大装置 SenseCore
- 腾讯云 TI 平台
- 智源 FlagOpen / FlagScale（重点对标其开源训练栈）

## 研究机构 / 前沿基础设施（拔高视野）
- 各家大模型公司公开的训练基础设施实践（技术博客为主）

## 对标这一环要逼出什么（产品判断，不是功能罗列）
- 同一个问题，不同平台的**产品决策为什么不同**？背后是用户群差异还是技术路线差异？
- 哪些是**行业共识的标准做法**，哪些还是**各家在博弈的开放问题**？
- 如果要做这个平台，**抄谁、避开谁的坑、在哪做差异化**？
