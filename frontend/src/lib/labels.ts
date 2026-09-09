/* 中文显示标签映射 —— 后端状态/枚举值 → 界面中文 */

export const STATUS_ZH: Record<string, string> = {
  COMPLETED: "已完成",
  RUNNING: "运行中",
  PENDING: "等待中",
  FAILED: "失败",
  PLANNING: "规划中",
  WRITING: "写作中",
};

export const TASK_TYPE_ZH: Record<string, string> = {
  survey: "综述",
  search: "检索",
  analyze: "分析",
  plan: "规划",
  write: "写作",
  evaluate: "评估",
  retrieve: "检索",
  summarize: "总结",
};

export const EVENT_TYPE_ZH: Record<string, string> = {
  TASK_START: "任务开始",
  TASK_END: "任务完成",
  TOOL_CALL: "工具调用",
  TOOL_RESULT: "工具结果",
  REFLECTION: "反思",
  REPLAN: "重规划",
  EVALUATION: "评估",
  REPORT_GENERATED: "报告生成",
  ERROR: "错误",
  AGENT_START: "开始",
  AGENT_END: "结束",
  STAGE: "阶段",
};

export const AGENT_ZH: Record<string, string> = {
  planner: "规划器",
  researcher: "研究员",
  retriever: "检索器",
  analyst: "分析师",
  critic: "评审",
  writer: "写作者",
  evaluator: "评估器",
  system: "系统",
  workflow: "工作流",
  tool: "工具",
  knowledge: "知识库",
  // 后端事件中的首字母大写形式
  System: "系统",
  Planner: "规划器",
  Researcher: "研究员",
  Retriever: "检索器",
  Analyst: "分析师",
  Critic: "评审",
  Writer: "写作者",
  Evaluator: "评估器",
  Knowledge: "知识库",
};

export const DOC_STATUS_ZH: Record<string, string> = {
  INDEXED: "已索引",
  EMBEDDING: "嵌入中",
  CHUNKING: "分块中",
  PARSING: "解析中",
  UPLOADING: "上传中",
  FAILED: "失败",
};

export function zh(map: Record<string, string>, key: string): string {
  return map[key] || key;
}
