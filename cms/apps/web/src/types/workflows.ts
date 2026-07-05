export type WorkflowExecutionStatus =
  "CREATED" | "RUNNING" | "SUCCESS" | "FAILED" | "WARNING" | "PAUSED" | "KILLED";

export interface TaskRun {
  task_id: string;
  status: WorkflowExecutionStatus;
  started: string | null;
  ended: string | null;
  outputs: Record<string, unknown>;
}

export interface WorkflowStatus {
  execution_id: string;
  flow_id: string;
  status: WorkflowExecutionStatus;
  started: string;
  ended: string | null;
  inputs: Record<string, unknown>;
  outputs: Record<string, unknown>;
  task_runs: TaskRun[];
}

export interface FlowSummary {
  id: string;
  namespace: string;
  description: string | null;
  is_template: boolean;
  revision: number;
  has_schedule: boolean;
}

export interface WorkflowListResponse {
  flows: FlowSummary[];
}

export interface LogEntry {
  timestamp: string;
  level: string;
  message: string;
  task_id: string | null;
}

export interface ExecutionLogsResponse {
  execution_id: string;
  logs: LogEntry[];
}
