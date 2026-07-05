export type BriefPlatform =
  "jira" | "asana" | "monday" | "clickup" | "trello" | "notion" | "wrike" | "basecamp";

export type BriefConnectionStatus = "connected" | "syncing" | "error" | "disconnected";

export type BriefItemStatus = "open" | "in_progress" | "done" | "cancelled";

export type BriefResourceType = "excel" | "translation" | "design" | "document" | "image" | "other";

export interface BriefConnection {
  id: number;
  name: string;
  platform: BriefPlatform;
  status: BriefConnectionStatus;
  project_url: string;
  credential_last4: string;
  project_id: number | null;
  project_name: string | null;
  last_synced_at: string | null;
  items_count: number;
  created_at: string;
  updated_at: string;
}

export interface BriefResource {
  id: number;
  type: BriefResourceType;
  filename: string;
  url: string;
  size_bytes: number | null;
}

export interface BriefAttachment {
  id: number;
  filename: string;
  url: string;
  size_bytes: number;
}

export interface BriefItem {
  id: number;
  connection_id: number;
  external_id: string;
  title: string;
  status: BriefItemStatus;
  assignees: string[];
  due_date: string | null;
  labels: string[];
  thumbnail_url: string | null;
  resources: BriefResource[];
  platform?: BriefPlatform;
  connection_name?: string;
  client_name?: string;
  created_at: string;
  updated_at: string;
}

export interface BriefDetail extends BriefItem {
  description: string;
  attachments: BriefAttachment[];
  priority: string | null;
}

export interface BriefConnectionCreate {
  name: string;
  platform: BriefPlatform;
  project_url: string;
  credentials: Record<string, string>;
  project_id: number | null;
}

export interface BriefImportRequest {
  brief_item_ids: number[];
  project_name: string;
}
