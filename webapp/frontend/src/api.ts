// 백엔드 API 타입 & 호출 헬퍼

export interface ColumnMeta {
  col: string;
  label: string;
  numeric: boolean;
}

export interface FilterMeta {
  col: string;
  label: string;
  type: "select" | "range";
}

export interface TableMeta {
  name: string;
  label: string;
  icon: string;
  count: number;
  columns: ColumnMeta[];
  search: string[];
  filters: FilterMeta[];
  sort: { col: string; order: string };
}

export interface OptionItem {
  value: string;
  label: string;
  count: number;
}

export interface DataResponse {
  total: number;
  page: number;
  page_size: number;
  pages: number;
  columns: ColumnMeta[];
  rows: Record<string, any>[];
}

export interface Summary {
  cards: { name: string; label: string; icon: string; count: number }[];
  by_region: { key: string; label: string; count: number }[];
  by_industry: { label: string; count: number }[];
}

async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `요청 실패 (${res.status})`);
  }
  return res.json();
}

export const api = {
  tables: () => getJSON<TableMeta[]>("/api/tables"),
  summary: () => getJSON<Summary>("/api/summary"),
  options: (table: string, col: string) =>
    getJSON<OptionItem[]>(`/api/options/${table}/${encodeURIComponent(col)}`),
  data: (table: string, params: URLSearchParams) =>
    getJSON<DataResponse>(`/api/data/${table}?${params.toString()}`),
};
